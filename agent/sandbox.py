"""代码执行沙箱：NVIDIA OpenShell（节点上的网关 + 容器沙箱，策略见 sandbox/policy.yaml）。

为什么要有它：`run_command` 只能跑白名单里的测试命令，跑不了「一个 Python 贪吃蛇 / Node 脚本 / 任意验证」。
沙箱把任意代码关在一个没有网络、系统目录只读、只有 /sandbox 可写、以非 root 运行的容器里，所以可以放开命令范围。

一次调用的流程（openshell CLI，全部走本机网关，约几十毫秒）：
  1. 把工作区复制一份到临时目录（丢掉 .git、node_modules 等，限大小）→ upload 到 /sandbox/work/w
  2. 在 /sandbox/work/w 里执行命令（--timeout 由我们给）
  3. download 回来，和上传前逐文件比哈希，新增 / 修改的文件写回工作区（路径过 safe_path，不跟符号链接）

刻意的取舍：
  · 沙箱里删除文件不会同步回工作区（只增改，不删），避免一条 rm 误伤真实工作区；
  · 沙箱是全局共享的一个（spark-devflow），调用串行加锁；不同会话各用自己的 /sandbox/work/<标识>；
  · openshell 不可用时（开发机、网关没起）工具直接报错让模型换路，不影响其它功能。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .tools.base import ToolError, safe_path, subprocess_env

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = "ghcr.io/nvidia/openshell-community/sandboxes/base:latest"
NAME = "spark-devflow"
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".DS_Store"}
MAX_FILE = 5 * 1024 * 1024
MAX_TOTAL = 60 * 1024 * 1024
MAX_FILES = 3000
MAX_BACK = 400          # 单次最多写回多少个文件


class SandboxError(ToolError):
    """沙箱不可用或执行失败（给模型看，不含堆栈）。"""


@dataclass
class SandboxResult:
    output: str
    exit_code: int
    changed: list[tuple[str, str]]     # (added|modified, 相对路径)
    skipped: int = 0                   # 没写回的（超限 / 越界 / 符号链接）
    seconds: float = 0.0


def _sha(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(root: Path):
    """相对路径 → 绝对路径；跳过依赖目录、符号链接。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not (Path(dirpath) / d).is_symlink()]
        for name in filenames:
            p = Path(dirpath) / name
            if p.is_symlink() or name in SKIP_DIRS:
                continue
            yield p.relative_to(root).as_posix(), p


class OpenShellSandbox:
    def __init__(self, cli: str | None = None, image: str | None = None, policy: Path | None = None,
                 runner=subprocess.run):
        self.cli = cli or os.environ.get("AGENT_OPENSHELL") or shutil.which("openshell") \
            or str(Path.home() / "openshell" / "bin" / "openshell")
        self.image = image or os.environ.get("AGENT_SANDBOX_IMAGE", DEFAULT_IMAGE)
        self.policy = policy or ROOT / "sandbox" / "policy.yaml"
        self.name = NAME
        self._run = runner
        self._lock = threading.Lock()
        self._ok_until = 0.0

    # ---------------- CLI ----------------
    def _cli(self, *argv: str, timeout: float = 30) -> subprocess.CompletedProcess:
        try:
            return self._run([self.cli, *argv], capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=timeout, stdin=subprocess.DEVNULL, env=subprocess_env(**self._env()))
        except FileNotFoundError:
            raise SandboxError("沙箱不可用：没有找到 openshell 命令（节点上应在 ~/openshell/bin）")
        except subprocess.TimeoutExpired:
            raise SandboxError(f"沙箱命令超时：openshell {argv[0]} {argv[1] if len(argv) > 1 else ''}")

    @staticmethod
    def _env() -> dict[str, str]:
        # openshell 要从 HOME 下读网关配置；subprocess_env 已保留 HOME
        return {"OPENSHELL_GATEWAY": os.environ.get("OPENSHELL_GATEWAY", "")} if os.environ.get("OPENSHELL_GATEWAY") else {}

    def _alive(self) -> bool:
        p = self._cli("sandbox", "exec", "-n", self.name, "--timeout", "10", "--", "true", timeout=20)
        return p.returncode == 0

    def ensure(self) -> None:
        """沙箱在就用，不在（或没起来）就建。首次创建约几秒。"""
        if time.monotonic() < self._ok_until:
            return
        if not self._alive():
            self._cli("sandbox", "delete", self.name, timeout=30)  # 残骸（失败 / 已停止）先清掉，忽略结果
            argv = ["sandbox", "create", "--name", self.name, "--from", self.image, "--no-tty"]
            if self.policy.exists():
                argv += ["--policy", str(self.policy)]
            p = self._cli(*argv, timeout=180)
            if p.returncode != 0 and not self._alive():
                tail = (p.stderr or p.stdout).strip().splitlines()[-3:]
                raise SandboxError("沙箱创建失败：" + " ".join(tail)[:300])
            for _ in range(20):  # create 可能在 Ready 之前返回
                if self._alive():
                    break
                time.sleep(1)
            else:
                raise SandboxError("沙箱创建后一直没就绪")
        self._ok_until = time.monotonic() + 60

    def available(self) -> tuple[bool, str]:
        try:
            p = self._cli("status", timeout=10)
        except SandboxError as exc:
            return False, str(exc)
        return (p.returncode == 0, "" if p.returncode == 0 else "OpenShell 网关没有响应")

    # ---------------- 执行 ----------------
    def run(self, command: str, workspace: Path, *, timeout: int = 60, tag: str = "") -> SandboxResult:
        tag = tag or hashlib.sha1(str(workspace.resolve()).encode()).hexdigest()[:8]
        remote = f"/sandbox/work/{tag}"
        with self._lock, tempfile.TemporaryDirectory(prefix="spark-sbx-") as tmp:
            self.ensure()
            stage = Path(tmp) / "w"
            before = self._stage(workspace, stage)
            t0 = time.monotonic()
            self._cli("sandbox", "exec", "-n", self.name, "--timeout", "30", "--", "sh", "-c",
                      f"rm -rf {remote} && mkdir -p {remote}", timeout=45)
            up = self._cli("sandbox", "upload", self.name, str(stage), remote, timeout=120)
            if up.returncode != 0:
                raise SandboxError("上传工作区到沙箱失败：" + (up.stderr or up.stdout).strip()[-200:])
            workdir = f"{remote}/w"
            p = self._cli("sandbox", "exec", "-n", self.name, "--workdir", workdir, "--timeout", str(timeout), "--",
                          "bash", "-lc", command, timeout=timeout + 20)
            output = (p.stdout or "") + (("\n" + p.stderr) if p.stderr and p.stderr.strip() else "")
            changed, skipped = self._pull(workdir, workspace, Path(tmp) / "out", before)
            return SandboxResult(output.strip(), p.returncode, changed, skipped, time.monotonic() - t0)

    def _stage(self, workspace: Path, stage: Path) -> dict[str, str]:
        """复制一份精简的工作区（并记下每个文件的哈希，用来判断沙箱里改了什么）。"""
        stage.mkdir(parents=True)
        hashes: dict[str, str] = {}
        total = 0
        for rel, src in _walk(workspace):
            size = src.stat().st_size
            if size > MAX_FILE:
                continue
            total += size
            if len(hashes) >= MAX_FILES or total > MAX_TOTAL:
                raise SandboxError("工作区太大，没法放进沙箱（上限 3000 个文件 / 60MB）")
            dest = stage / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            hashes[rel] = _sha(src)
        return hashes

    def _pull(self, workdir: str, workspace: Path, out: Path, before: dict[str, str]) -> tuple[list[tuple[str, str]], int]:
        out.mkdir(parents=True, exist_ok=True)
        d = self._cli("sandbox", "download", self.name, workdir, str(out), timeout=120)
        if d.returncode != 0:
            raise SandboxError("从沙箱取回文件失败：" + (d.stderr or d.stdout).strip()[-200:])
        changed: list[tuple[str, str]] = []
        skipped = 0
        for rel, src in _walk(out):
            if src.stat().st_size > MAX_FILE:
                skipped += 1
                continue
            old = before.get(rel)
            if old is not None and old == _sha(src):
                continue
            if len(changed) >= MAX_BACK:
                skipped += 1
                continue
            try:
                dest = safe_path(workspace, rel)
            except ToolError:
                skipped += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            changed.append(("modified" if old is not None else "added", rel))
        return changed, skipped


_shared: OpenShellSandbox | None = None


def get_sandbox() -> OpenShellSandbox:
    global _shared
    if _shared is None:
        _shared = OpenShellSandbox()
    return _shared
