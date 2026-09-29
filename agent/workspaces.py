"""工作区与笔记库管理：新建、克隆、上传导入、浏览文件、把改动带回本地。

节点上的面板看不到用户电脑的磁盘，所以「选一个本地文件夹」的做法是：
  · 浏览器把文件夹（或 zip）上传到节点，落在 <data_dir>/workspaces/<id>/，之后 agent 就在这份副本上改；
  · 改完在面板里看改动清单，Chrome / Edge 可以一键写回原文件夹，其它浏览器下载 zip；
  · 或者干脆给 git 仓库地址，节点自己克隆（私有仓库用「集成设置」里的令牌）。
笔记库（Obsidian）走同一套机制，kind="vault"，agent 对它只读。

安全约束：
  · 只认注册表里的 id，路径一律经 safe_path 限制在该目录内；
  · 导入时丢弃上传内容里自带的 .git（里面的 hooks / config 会在节点上被 git 执行），改成节点上新 init；
  · 克隆只允许 https，网址里不许夹凭据，不许指向本机或内网地址；令牌走环境变量，不进命令行，报错里会抹掉。
"""
from __future__ import annotations

import base64
import io
import ipaddress
import json
import os
import re
import shutil
import stat
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from .tools.base import ToolError, safe_path

KINDS = ("workspace", "vault")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".DS_Store"}
MAX_TOTAL = 200 * 1024 * 1024     # 单个工作区导入的总大小
MAX_FILES = 8000
MAX_VIEW = 200 * 1024             # 面板里预览一个文件最多读多少
IDENT = ["-c", "user.name=dgx-agent", "-c", "user.email=dgx-agent@localhost"]
NAME_OK = re.compile(r"^[\w\-. 一-鿿]{1,40}$")


class WorkspaceError(Exception):
    """给面板直接显示的错误。"""


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")  # id 只用 ASCII，URL 里不用转义
    return (s or "ws")[:24]


def _rmtree(path: Path) -> None:
    def onerror(func, p, _exc):  # Windows 上 .git 里的文件是只读的
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=onerror)


def _check_clone_url(url: str) -> tuple[str, str]:
    u = urlparse(url.strip())
    if u.scheme != "https" or not u.hostname:
        raise WorkspaceError("只支持 https 地址，例如 https://github.com/owner/repo.git")
    if u.username or u.password:
        raise WorkspaceError("网址里不要带用户名或令牌：令牌请填在「集成设置 → Git」里")
    host = u.hostname.lower()
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise WorkspaceError("不允许指向本机或内网地址")
    except ValueError:
        if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
            raise WorkspaceError("不允许指向本机或内网地址")
    return url.strip(), host


class WorkspaceStore:
    def __init__(self, data_dir: Path, demo_paths, *, token_for=None):
        """demo_paths：返回 {"workspace": 演示仓库, "vault": 演示纪要库} 的函数（跟着运行配置走）。"""
        self.data_dir = data_dir
        self.registry = data_dir / "workspaces.json"
        self.demo_paths = demo_paths
        self.token_for = token_for or (lambda host: "")  # host → 令牌（来自 IntegrationStore）
        self._lock = threading.Lock()
        self._items: list[dict] = self._load()
        self._uploads: dict[str, list[int]] = {}  # id → [文件数, 总字节]

    # ---------------- 注册表 ----------------
    def _load(self) -> list[dict]:
        try:
            data = json.loads(self.registry.read_text(encoding="utf-8"))
            return [d for d in data if isinstance(d, dict) and d.get("id")]
        except (OSError, json.JSONDecodeError):
            return []

    def _save(self) -> None:
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.registry.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._items, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.registry)

    def _root(self, kind: str) -> Path:
        return self.data_dir / ("vaults" if kind == "vault" else "workspaces")

    def _entry(self, wid: str) -> dict | None:
        return next((d for d in self._items if d["id"] == wid), None)

    def _builtin(self, wid: str, kind: str | None = None) -> dict | None:
        if wid != "demo":
            return None
        kinds = [kind] if kind else list(KINDS)
        return {"id": "demo", "kind": kinds[0], "name": "演示（tinyledger）" if kinds[0] == "workspace" else "演示纪要库",
                "source": "demo", "builtin": True}

    def get(self, wid: str, kind: str | None = None) -> dict:
        e = self._entry(wid) or self._builtin(wid, kind)
        if e is None or (kind and e["kind"] != kind):
            raise WorkspaceError("没有这个工作区")
        return e

    def path(self, wid: str, kind: str | None = None) -> Path:
        e = self.get(wid, kind)
        if e.get("builtin"):
            return Path(self.demo_paths()[kind or e["kind"]])
        return self._root(e["kind"]) / e["id"]

    def list(self, kind: str) -> list[dict]:
        out = [self._view(self._builtin("demo", kind))]  # type: ignore[arg-type]
        out += [self._view(d) for d in self._items if d["kind"] == kind]
        return out

    def _view(self, e: dict) -> dict:
        p = self.path(e["id"], e["kind"])
        return {"id": e["id"], "name": e["name"], "kind": e["kind"], "source": e.get("source", ""),
                "url": e.get("url", ""), "created": e.get("created"), "builtin": bool(e.get("builtin")),
                "ready": p.is_dir() and e.get("state") != "uploading",
                "git": (p / ".git").exists(), "syncable": bool(e.get("url"))}

    # ---------------- git ----------------
    def _git(self, cwd: Path, *argv: str, env: dict | None = None, timeout: int = 60, secret: str = "") -> str:
        full_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})}
        try:
            proc = subprocess.run(["git", *argv], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout, env=full_env)
        except FileNotFoundError:
            raise WorkspaceError("节点上没有 git")
        except subprocess.TimeoutExpired:
            raise WorkspaceError(f"git {argv[0]} 超时")
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout).strip()
            if secret:
                msg = msg.replace(secret, "***")
            raise WorkspaceError(f"git {argv[0]} 失败：{msg[-400:]}")
        return proc.stdout

    def _net_env(self, host: str) -> tuple[dict, str]:
        """克隆 / 拉取用的环境：令牌走 GIT_CONFIG_*（不进命令行），代理沿用面板进程的环境变量。"""
        env: dict[str, str] = {}
        token = self.token_for(host)
        if token:
            cred = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": f"http.https://{host}/.extraheader",
                        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {cred}"})
        return env, token

    def _snapshot(self, path: Path, message: str) -> str:
        """新导入 / 新建的目录：init + 提交一份快照，作为「改动」的比较基准。"""
        self._git(path, "init", "-q")
        self._git(path, "add", "-A")
        self._git(path, *IDENT, "commit", "-q", "--allow-empty", "-m", message)
        return self._git(path, "rev-parse", "HEAD").strip()

    # ---------------- 创建 ----------------
    def _new(self, name: str, kind: str, source: str, url: str = "") -> tuple[dict, Path]:
        if kind not in KINDS:
            raise WorkspaceError("kind 只能是 workspace 或 vault")
        name = (name or "").strip()
        if not NAME_OK.match(name):
            raise WorkspaceError("名字 1–40 个字：中文、字母、数字、空格和 - _ .")
        with self._lock:
            if any(d["kind"] == kind and d["name"] == name for d in self._items):
                raise WorkspaceError("已经有同名的了，换一个名字")
            wid = f"{_slug(name)}-{uuid.uuid4().hex[:4]}"
            entry = {"id": wid, "name": name, "kind": kind, "source": source, "url": url, "base": "",
                     "created": int(time.time()), "state": "uploading"}
            self._items.append(entry)
            self._save()
        path = self._root(kind) / wid
        path.mkdir(parents=True, exist_ok=True)
        return entry, path

    def _ready(self, entry: dict, base: str) -> dict:
        with self._lock:
            entry["base"], entry["state"] = base, "ready"
            self._save()
        return self._view(entry)

    def _abort(self, entry: dict) -> None:
        with self._lock:
            self._items = [d for d in self._items if d["id"] != entry["id"]]
            self._save()
        p = self._root(entry["kind"]) / entry["id"]
        if p.exists():
            _rmtree(p)

    def create_empty(self, name: str, kind: str = "workspace") -> dict:
        entry, path = self._new(name, kind, "empty")
        try:
            if kind == "workspace":
                (path / "README.md").write_text(f"# {entry['name']}\n\n在 DGX Spark 上创建的空工作区。\n", encoding="utf-8")
            return self._ready(entry, self._snapshot(path, "初始化工作区"))
        except Exception:
            self._abort(entry)
            raise

    def clone(self, name: str, url: str, kind: str = "workspace", branch: str = "") -> dict:
        url, host = _check_clone_url(url)
        if branch and not re.match(r"^[\w./-]{1,80}$", branch):
            raise WorkspaceError("分支名不合法")
        entry, path = self._new(name, kind, "clone", url)
        env, token = self._net_env(host)
        try:
            shutil.rmtree(path)  # git clone 要求目标不存在
            argv = ["clone", "-q", "--depth", "200", "--single-branch"]
            if branch:
                argv += ["--branch", branch]
            self._git(path.parent, *argv, "--", url, path.name, env=env, timeout=300, secret=token)
            return self._ready(entry, self._git(path, "rev-parse", "HEAD").strip())
        except Exception:
            self._abort(entry)
            raise

    def pull(self, wid: str) -> dict:
        e = self.get(wid)
        if not e.get("url"):
            raise WorkspaceError("这个工作区不是从 git 克隆来的，没有可同步的远端")
        _, host = _check_clone_url(e["url"])
        env, token = self._net_env(host)
        path = self.path(wid)
        if e["kind"] == "vault":  # 笔记库 agent 只读，直接和远端对齐
            self._git(path, "fetch", "-q", "--depth", "200", env=env, timeout=180, secret=token)
            self._git(path, "reset", "-q", "--hard", "FETCH_HEAD")
        else:
            self._git(path, "pull", "-q", "--ff-only", env=env, timeout=180, secret=token)
        return self._view(e)

    def import_zip(self, name: str, data: bytes, kind: str = "workspace") -> dict:
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise WorkspaceError("不是有效的 zip 文件")
        entry, path = self._new(name, kind, "upload")
        try:
            names = [i for i in zf.infolist() if not i.is_dir()]
            # 单一顶层目录（常见的「右键压缩文件夹」）时去掉这一层
            tops = {i.filename.replace("\\", "/").split("/")[0] for i in names}
            strip = len(tops) == 1 and all("/" in i.filename.replace("\\", "/") for i in names)
            total = count = 0
            for info in names:
                rel = info.filename.replace("\\", "/")
                if strip:
                    rel = rel.split("/", 1)[1]
                if not self._importable(rel):
                    continue
                count += 1
                total += info.file_size
                if count > MAX_FILES or total > MAX_TOTAL:
                    raise WorkspaceError("文件太多或太大（上限 8000 个文件 / 200MB），请先删掉依赖和构建产物再上传")
                dest = safe_path(path, rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
            if count == 0:
                raise WorkspaceError("zip 里没有可导入的文件")
            return self._ready(entry, self._snapshot(path, "导入本地文件夹"))
        except (ToolError, zipfile.BadZipFile) as exc:
            self._abort(entry)
            raise WorkspaceError(str(exc))
        except Exception:
            self._abort(entry)
            raise

    @staticmethod
    def _importable(rel: str) -> bool:
        parts = [p for p in rel.split("/") if p]
        return bool(parts) and not any(p in SKIP_DIRS for p in parts)

    # 浏览器逐个文件上传（选文件夹）：begin → put × N → finish
    def begin_upload(self, name: str, kind: str = "workspace") -> dict:
        entry, _ = self._new(name, kind, "upload")
        self._uploads[entry["id"]] = [0, 0]
        return {"id": entry["id"]}

    def put_file(self, wid: str, rel: str, data: bytes) -> None:
        e = self._entry(wid)
        if e is None or e.get("state") != "uploading" or wid not in self._uploads:
            raise WorkspaceError("这次上传已经结束或不存在")
        rel = rel.replace("\\", "/").lstrip("/")
        if not self._importable(rel):
            return
        stats = self._uploads[wid]
        stats[0] += 1
        stats[1] += len(data)
        if stats[0] > MAX_FILES or stats[1] > MAX_TOTAL:
            raise WorkspaceError("文件太多或太大（上限 8000 个文件 / 200MB）")
        try:
            dest = safe_path(self._root(e["kind"]) / wid, rel)
        except ToolError as exc:
            raise WorkspaceError(str(exc))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def finish_upload(self, wid: str) -> dict:
        e = self._entry(wid)
        if e is None or e.get("state") != "uploading" or wid not in self._uploads:
            raise WorkspaceError("这次上传已经结束或不存在")
        try:
            if self._uploads[wid][0] == 0:
                raise WorkspaceError("没有可导入的文件")
            view = self._ready(e, self._snapshot(self._root(e["kind"]) / wid, "导入本地文件夹"))
        except Exception:
            self._abort(e)
            raise
        finally:
            self._uploads.pop(wid, None)
        return view

    def abort_upload(self, wid: str) -> None:
        e = self._entry(wid)
        if e and e.get("state") == "uploading":
            self._uploads.pop(wid, None)
            self._abort(e)

    def delete(self, wid: str) -> None:
        e = self._entry(wid)
        if e is None:
            raise WorkspaceError("演示环境不能删除" if wid == "demo" else "没有这个工作区")
        root = self._root(e["kind"]).resolve()
        path = (root / wid).resolve()
        if path.parent != root or (root / wid).is_symlink():
            raise WorkspaceError("工作区路径越界，拒绝删除")
        if path.exists():
            _rmtree(path)
        self._uploads.pop(wid, None)
        with self._lock:
            self._items = [d for d in self._items if d["id"] != wid]
            self._save()

    # ---------------- 浏览 ----------------
    def tree(self, wid: str, sub: str = "") -> list[dict]:
        root = self.path(wid)
        try:
            base = safe_path(root, sub or ".")
        except ToolError as exc:
            raise WorkspaceError(str(exc))
        if not base.is_dir():
            raise WorkspaceError("目录不存在")
        rows = []
        for child in sorted(base.iterdir(), key=lambda c: (c.is_file(), c.name.lower())):
            if child.name == ".git":
                continue
            rows.append({"name": child.name, "type": "dir" if child.is_dir() else "file",
                         "size": child.stat().st_size if child.is_file() else 0})
            if len(rows) >= 500:
                break
        return rows

    def read(self, wid: str, rel: str) -> dict:
        try:
            p = safe_path(self.path(wid), rel)
        except ToolError as exc:
            raise WorkspaceError(str(exc))
        if not p.is_file():
            raise WorkspaceError("文件不存在")
        size = p.stat().st_size
        with open(p, "rb") as f:
            head = f.read(MAX_VIEW + 1)
        if b"\x00" in head[:4096]:
            return {"path": rel, "size": size, "binary": True, "text": "", "truncated": False}
        return {"path": rel, "size": size, "binary": False, "truncated": len(head) > MAX_VIEW,
                "text": head[:MAX_VIEW].decode("utf-8", errors="replace")}

    def raw(self, wid: str, rel: str) -> bytes:
        try:
            p = safe_path(self.path(wid), rel)
        except ToolError as exc:
            raise WorkspaceError(str(exc))
        if not p.is_file():
            raise WorkspaceError("文件不存在")
        if p.stat().st_size > 20 * 1024 * 1024:
            raise WorkspaceError("文件超过 20MB，请用 zip 下载")
        return p.read_bytes()

    def changes(self, wid: str) -> dict:
        """相对导入 / 克隆时那份快照，工作区里多了什么、改了什么、删了什么。"""
        e = self.get(wid)
        path = self.path(wid)
        if not (path / ".git").exists():
            return {"base": "", "changes": []}
        base = e.get("base") or "HEAD"
        out = self._git(path, "-c", "core.quotepath=off", "diff", "--name-status", "--no-renames", base)
        rows = {}
        for line in out.splitlines():
            code, _, name = line.partition("\t")
            if name:
                rows[name] = {"M": "modified", "A": "added", "D": "deleted"}.get(code[:1], "modified")
        for name in self._git(path, "-c", "core.quotepath=off", "ls-files", "--others", "--exclude-standard").splitlines():
            rows.setdefault(name, "added")
        return {"base": base[:8], "changes": [{"path": k, "status": v} for k, v in sorted(rows.items())][:500]}

    def zip_bytes(self, wid: str) -> bytes:
        path = self.path(wid)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            total = 0
            for p in sorted(path.rglob("*")):
                rel = p.relative_to(path)
                if p.is_dir() or ".git" in rel.parts or any(part in SKIP_DIRS for part in rel.parts):
                    continue
                total += p.stat().st_size
                if total > MAX_TOTAL:
                    raise WorkspaceError("超过 200MB，不打包下载")
                zf.write(p, rel.as_posix())
        return buf.getvalue()
