"""OpenShell 沙箱（假 CLI）与网页预览：隔离头、令牌授权、越界与同步回工作区的边界。"""
import http.client
import io
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from agent.sandbox import OpenShellSandbox, SandboxError
from agent.tools import build_registry
from agent.tools.base import ToolContext, ToolError
from agent.tools.sandbox import run_in_sandbox

from test_server import call, login, running  # noqa: F401
from test_workspaces import make_zip


# ---------------- 沙箱（假的 openshell） ----------------
class FakeCli:
    """按 openshell 的真实语义模拟：upload 目录 → 目标目录/<目录名>；download 目录 → 目标里直接是内容。"""

    def __init__(self, tmp: Path, alive=True, exec_effect=None, exec_rc=0, exec_out="ok", evil_tar=False):
        self.evil_tar = evil_tar
        self.remote = tmp / "remote"
        self.remote.mkdir()
        self.calls: list[list[str]] = []
        self.alive, self.exec_effect, self.exec_rc, self.exec_out = alive, exec_effect, exec_rc, exec_out

    def _path(self, p: str) -> Path:
        return self.remote / p.lstrip("/")

    def __call__(self, argv, **kw):
        assert kw.get("stdin") == subprocess.DEVNULL  # 永远不能等交互输入
        self.calls.append(argv[1:])
        a = argv[1:]
        ok = subprocess.CompletedProcess(argv, 0, "", "")
        if a[:2] == ["sandbox", "exec"]:
            cmd = a[a.index("--") + 1:]
            if cmd == ["true"]:
                return subprocess.CompletedProcess(argv, 0 if self.alive else 1, "", "")
            if cmd[:2] == ["sh", "-c"] and "tar czf" in cmd[2]:       # 打包结果（排除依赖目录）
                remote = self._path(cmd[2].split("mkdir -p ")[1].split("/pull")[0])
                (remote / "pull").mkdir(parents=True, exist_ok=True)
                with tarfile.open(remote / "pull" / "out.tgz", "w:gz") as tar:
                    for f in sorted((remote / "w").rglob("*")):
                        rel = f.relative_to(remote / "w")
                        if f.is_file() and not any(x in (".git", "node_modules", ".venv") for x in rel.parts):
                            tar.add(f, "./" + rel.as_posix())
                    if self.evil_tar:
                        for name, kind in (("../../escape.txt", "file"), ("link", "sym")):
                            info = tarfile.TarInfo(name)
                            if kind == "sym":
                                info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
                                tar.addfile(info)
                            else:
                                data = b"pwn"
                                info.size = len(data)
                                tar.addfile(info, io.BytesIO(data))
                return ok
            if cmd[:2] == ["sh", "-c"]:                             # 清掉上次的源码，保留 node_modules / .venv
                remote = self._path(cmd[2].split("mkdir -p ")[1].split("/w")[0])
                (remote / "w").mkdir(parents=True, exist_ok=True)
                for child in (remote / "w").iterdir():
                    if child.name not in ("node_modules", ".venv"):
                        shutil.rmtree(child) if child.is_dir() else child.unlink()
                shutil.rmtree(remote / "pull", ignore_errors=True)
                return ok
            wd = self._path(a[a.index("--workdir") + 1])
            if self.exec_effect:
                self.exec_effect(wd)
            return subprocess.CompletedProcess(argv, self.exec_rc, self.exec_out, "")
        if a[:2] == ["sandbox", "upload"]:
            src, dest = Path(a[3]), self._path(a[4])
            shutil.copytree(src, dest / src.name, dirs_exist_ok=True)
            return ok
        if a[:2] == ["sandbox", "download"]:
            shutil.copytree(self._path(a[3]), a[4], dirs_exist_ok=True)
            return ok
        if a[:2] == ["sandbox", "create"]:
            self.alive = True
            return ok
        return ok


@pytest.fixture
def ws(tmp_path):
    d = tmp_path / "ws"
    (d / "src").mkdir(parents=True)
    (d / "app.py").write_text("print(1)\n")
    (d / "src" / "u.py").write_text("X = 1\n")
    (d / "node_modules" / "big").mkdir(parents=True)
    (d / "node_modules" / "big" / "x.js").write_text("// dep")
    (d / ".git").mkdir()
    (d / ".git" / "config").write_text("[core]")
    return d


def make_sandbox(tmp_path, **kw):
    cli = FakeCli(tmp_path, **kw)
    return OpenShellSandbox(cli="openshell", image="img", policy=tmp_path / "none.yaml", runner=cli), cli


def test_run_syncs_only_added_and_modified(tmp_path, ws):
    def effect(wd: Path):
        assert (wd / "app.py").exists() and not (wd / ".git").exists() and not (wd / "node_modules").exists()
        (wd / "app.py").write_text("print(2)\n")          # 修改
        (wd / "out").mkdir()
        (wd / "out" / "result.txt").write_text("done")     # 新增
        (wd / "src" / "u.py").unlink()                     # 删除：不同步
    sb, cli = make_sandbox(tmp_path, exec_effect=effect, exec_out="hello")
    r = sb.run("python3 app.py", ws, timeout=30, tag="t1")
    assert r.exit_code == 0 and r.output == "hello"
    assert sorted(r.changed) == [("added", "out/result.txt"), ("modified", "app.py")]
    assert (ws / "app.py").read_text() == "print(2)\n" and (ws / "out" / "result.txt").read_text() == "done"
    assert (ws / "src" / "u.py").exists()                   # 沙箱里删了，工作区里还在
    assert (ws / ".git" / "config").exists() and (ws / "node_modules" / "big" / "x.js").exists()
    verbs = [c[:2] for c in cli.calls]
    assert ["sandbox", "upload"] in verbs and ["sandbox", "download"] in verbs
    # 命令用 --timeout 限时，并且是 bash -lc 一整条
    run_call = next(c for c in cli.calls if "--workdir" in c)
    assert run_call[run_call.index("--timeout") + 1] == "30" and run_call[-3:] == ["bash", "-lc", "python3 app.py"]


def test_run_skips_symlink_and_escape_paths(tmp_path, ws):
    def effect(wd: Path):
        (wd / "ok.txt").write_text("fine")
        try:
            (wd / "link").symlink_to("/etc/passwd")
        except OSError:
            pass  # Windows 上没权限建符号链接，跳过这一条
        (wd / "big.bin").write_bytes(b"0" * (6 * 1024 * 1024))
    sb, _ = make_sandbox(tmp_path, exec_effect=effect)
    r = sb.run("x", ws, tag="t2")
    assert ("added", "ok.txt") in r.changed and not (ws / "link").exists() and not (ws / "big.bin").exists()
    assert r.skipped >= 1


def test_node_modules_persist_in_sandbox_but_never_sync_back(tmp_path, ws):
    def install(wd: Path):
        (wd / "node_modules" / "left-pad").mkdir(parents=True)
        (wd / "node_modules" / "left-pad" / "index.js").write_text("module.exports=1")
        (wd / "dist").mkdir()
        (wd / "dist" / "index.html").write_text("<h1>built</h1>")
    sb, cli = make_sandbox(tmp_path, exec_effect=install)
    r = sb.run("npm install && npx vite build", ws, tag="t5")
    assert ("added", "dist/index.html") in r.changed                        # 构建产物回到工作区
    assert not (ws / "node_modules" / "left-pad").exists()                # 依赖留在沙箱里，不回到工作区
    kept = tmp_path / "remote" / "sandbox" / "work" / "t5" / "w" / "node_modules" / "left-pad" / "index.js"
    assert kept.exists()
    # 第二次调用：源码被清掉重传，但 node_modules 还在
    seen = {}
    sb2 = OpenShellSandbox(cli="openshell", image="img", policy=tmp_path / "none.yaml", runner=cli)
    cli.exec_effect = lambda wd: seen.update(nm=(wd / "node_modules" / "left-pad" / "index.js").exists(), app=(wd / "app.py").exists())
    sb2.run("ls", ws, tag="t5")
    assert seen == {"nm": True, "app": True}


def test_untrusted_tar_members_are_skipped(tmp_path, ws):
    sb, _ = make_sandbox(tmp_path, evil_tar=True, exec_effect=lambda wd: (wd / "ok.txt").write_text("fine"))
    r = sb.run("x", ws, tag="t6")
    assert ("added", "ok.txt") in r.changed
    assert not (ws / "link").exists() and not (tmp_path / "escape.txt").exists() and not (ws.parent / "escape.txt").exists()
    assert all(p != "escape.txt" for _, p in r.changed)


def test_creates_sandbox_when_missing_and_reports_errors(tmp_path, ws):
    sb, cli = make_sandbox(tmp_path, alive=False)
    sb.run("true", ws, tag="t3")
    assert ["sandbox", "create"] in [c[:2] for c in cli.calls]
    create = next(c for c in cli.calls if c[:2] == ["sandbox", "create"])
    assert "--from" in create and "--no-tty" in create

    def missing(*a, **k):
        raise FileNotFoundError
    sb2 = OpenShellSandbox(cli="nope", runner=missing)
    with pytest.raises(SandboxError) as e:
        sb2.run("x", ws)
    assert "openshell" in str(e.value)


def test_nonzero_exit_and_tool_output(tmp_path, ws):
    sb, _ = make_sandbox(tmp_path, exec_rc=1, exec_out="Traceback: boom")
    ctx = ToolContext(workspace=ws, vault=ws, working=None, sandbox=sb, sandbox_tag="t4")
    out = run_in_sandbox({"command": "python3 bad.py", "timeout": 999}, ctx)
    assert out.startswith("退出码 1") and "boom" in out
    with pytest.raises(ToolError):
        run_in_sandbox({}, ctx)


def test_tool_registered_as_write_local():
    t = build_registry().get("run_in_sandbox")
    assert t is not None and t.permission.value == "write_local"


# ---------------- 网页预览 ----------------
PAGE = "<!doctype html><script type='module' src='./app.js'></script><h1>贪吃蛇</h1>"


def raw_get(port, path, cookie=""):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path, headers={"Cookie": cookie} if cookie else {})
    r = conn.getresponse()
    body = r.read()
    return r.status, body, {k.lower(): v for k, v in r.getheaders()}


def test_preview_token_flow_and_isolation(running):
    app, port = running
    cookie = login(port)
    wid = app.workspaces.import_zip("贪吃蛇", make_zip({
        "index.html": PAGE, "app.js": "export const a = 1;", ".env": "SECRET=1", "css/s.css": "h1{color:red}",
        "sub/index.html": "<p>sub</p>"}))["id"]
    status, body, _ = call(port, "POST", f"/api/workspaces/{wid}/preview", {}, cookie=cookie)
    assert status == 200 and body["url"].startswith("/preview/") and body["url"].endswith("/")
    url = body["url"]

    # 预览地址不需要 cookie（sandbox iframe 是不透明源，带不上），靠令牌
    status, page, h = raw_get(port, url)
    assert status == 200 and "贪吃蛇".encode() in page and h["content-type"].startswith("text/html")
    assert "sandbox allow-scripts" in h["content-security-policy"] and "allow-same-origin" not in h["content-security-policy"]
    assert h["access-control-allow-origin"] == "*" and h["x-content-type-options"] == "nosniff"
    assert h["cache-control"] == "no-store"
    status, js, h = raw_get(port, url + "app.js")
    assert status == 200 and h["content-type"].startswith("text/javascript")
    assert raw_get(port, url + "css/s.css")[2]["content-type"].startswith("text/css")
    assert b"sub" in raw_get(port, url + "sub/")[1]              # 目录 → index.html
    # 隐藏文件、越界、假令牌都拿不到
    assert raw_get(port, url + ".env")[0] == 404
    assert raw_get(port, url + "..%2F..%2Fetc%2Fpasswd")[0] == 404
    assert raw_get(port, url + "%2e%2e/x")[0] == 404
    assert raw_get(port, "/preview/forged-token/index.html")[0] == 404
    # 只读：不接受写方法；令牌过期后失效
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", url + "index.html", headers={"Content-Length": "0"})  # 不带请求体：服务端回 405 不读体，带体时 Windows 上偶发连接重置
    assert conn.getresponse().status == 405
    token = url.split("/")[2]
    app.previews[token] = (wid, 0)
    assert raw_get(port, url)[0] == 404


def test_preview_requires_login_and_workspace_kind(running):
    app, port = running
    cookie = login(port)
    wid = app.workspaces.import_zip("p", make_zip({"index.html": "x"}))["id"]
    vid = app.workspaces.import_zip("v", make_zip({"a.md": "x"}), kind="vault")["id"]
    assert call(port, "POST", f"/api/workspaces/{wid}/preview", {})[0] == 401            # 发令牌要登录
    assert call(port, "POST", f"/api/workspaces/{vid}/preview", {}, cookie=cookie)[0] == 400  # 笔记库不预览
    assert call(port, "POST", "/api/workspaces/nope/preview", {}, cookie=cookie)[0] == 400
