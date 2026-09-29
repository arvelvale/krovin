"""工作区 / 笔记库管理与集成设置：导入、浏览、改动清单、越界与凭据防护、经 HTTP 的完整流程。"""
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from agent.integrations import IntegrationError, IntegrationStore
from agent.workspaces import WorkspaceError, WorkspaceStore

from test_server import TOKEN, call, login, running  # noqa: F401  复用真实 HTTP 夹具


def make_zip(files: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture
def store(tmp_path):
    demo_ws, demo_vault = tmp_path / "demo-ws", tmp_path / "demo-vault"
    demo_ws.mkdir()
    demo_vault.mkdir()
    return WorkspaceStore(tmp_path / "var", lambda: {"workspace": demo_ws, "vault": demo_vault})


def git_log(path: Path) -> str:
    return subprocess.run(["git", "log", "--oneline"], cwd=path, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def test_create_empty_and_name_rules(store):
    v = store.create_empty("我的项目")
    assert v["ready"] and v["git"] and v["kind"] == "workspace"
    assert (store.path(v["id"]) / "README.md").exists() and "初始化" in git_log(store.path(v["id"]))
    with pytest.raises(WorkspaceError):
        store.create_empty("我的项目")       # 同名
    with pytest.raises(WorkspaceError):
        store.create_empty("../evil")        # 名字里不许有路径
    assert [w["id"] for w in store.list("workspace")][0] == "demo"


def test_import_zip_strips_top_dir_git_and_junk(store):
    data = make_zip({
        "proj/app.py": "print(1)\n", "proj/sub/util.py": "x = 1\n",
        "proj/.git/config": "[core]\n\tfsmonitor = evil\n", "proj/node_modules/lib/index.js": "//",
    })
    v = store.import_zip("导入测试", data)
    root = store.path(v["id"])
    assert (root / "app.py").read_text() == "print(1)\n" and (root / "sub" / "util.py").exists()
    assert not (root / "node_modules").exists()
    assert "evil" not in (root / ".git" / "config").read_text()  # 上传里自带的 .git 被丢弃，节点上重新 init
    assert [w["name"] for w in store.list("workspace")][-1] == "导入测试"


def test_import_zip_rejects_zip_slip_and_cleans_up(store):
    with pytest.raises(WorkspaceError):
        store.import_zip("坏包", make_zip({"a/../../../escape.txt": "x", "a/ok.txt": "y"}))
    assert not any(d["name"] == "坏包" for d in store.list("workspace"))
    assert not (store.data_dir / "escape.txt").exists()
    with pytest.raises(WorkspaceError):
        store.import_zip("不是zip", b"hello")


def test_folder_upload_flow(store):
    wid = store.begin_upload("逐个上传")["id"]
    assert not next(w for w in store._items if w["id"] == wid).get("base")
    store.put_file(wid, "src/main.py", b"print('hi')\n")
    store.put_file(wid, "node_modules/x.js", b"skip")   # 被跳过
    with pytest.raises(WorkspaceError):
        store.put_file(wid, "../../escape.txt", b"x")
    view = store.finish_upload(wid)
    assert view["ready"]
    assert store.read(wid, "src/main.py")["text"] == "print('hi')\n"
    with pytest.raises(WorkspaceError):
        store.put_file(wid, "late.py", b"x")            # 收尾后不能再传


def test_browse_read_and_path_guard(store):
    v = store.import_zip("浏览", make_zip({"a.py": "line1\nline2\n", "img.bin": b"\x00\x01\x02", "d/e.txt": "e"}))
    wid = v["id"]
    names = {(e["name"], e["type"]) for e in store.tree(wid)}
    assert ("a.py", "file") in names and ("d", "dir") in names and (".git", "dir") not in names
    assert store.tree(wid, "d")[0]["name"] == "e.txt"
    assert store.read(wid, "a.py")["text"].startswith("line1")
    assert store.read(wid, "img.bin")["binary"] is True
    for bad in ("../../etc/passwd", "/etc/passwd", "..\\..\\x"):
        with pytest.raises(WorkspaceError):
            store.read(wid, bad)
    with pytest.raises(WorkspaceError):
        store.tree(wid, "../..")


def test_changes_against_import_snapshot(store):
    wid = store.import_zip("改动", make_zip({"a.py": "1\n", "b.py": "2\n", "c.py": "3\n"}))["id"]
    root = store.path(wid)
    assert store.changes(wid)["changes"] == []
    (root / "a.py").write_text("changed\n")
    (root / "b.py").unlink()
    (root / "new.py").write_text("new\n")
    got = {c["path"]: c["status"] for c in store.changes(wid)["changes"]}
    assert got == {"a.py": "modified", "b.py": "deleted", "new.py": "added"}
    # agent 提交之后，相对导入快照的改动仍然算得出来
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"], cwd=root, check=True)
    assert {c["path"]: c["status"] for c in store.changes(wid)["changes"]} == got


def test_zip_download_excludes_git(store):
    wid = store.import_zip("打包", make_zip({"a.py": "1\n"}))["id"]
    names = zipfile.ZipFile(io.BytesIO(store.zip_bytes(wid))).namelist()
    assert names == ["a.py"]


def test_delete_only_registered(store, tmp_path):
    wid = store.create_empty("删我")["id"]
    root = store.path(wid)
    store.delete(wid)
    assert not root.exists() and not any(w["id"] == wid for w in store.list("workspace"))
    with pytest.raises(WorkspaceError):
        store.delete("demo")


@pytest.mark.parametrize("url", [
    "http://github.com/a/b.git", "ssh://git@github.com/a/b.git", "file:///etc", "https://user:tok@github.com/a/b.git",
    "https://127.0.0.1/a.git", "https://192.168.1.5/a.git", "https://localhost/a.git", "https://nas.local/a.git",
])
def test_clone_rejects_unsafe_urls(store, url):
    with pytest.raises(WorkspaceError):
        store.clone("坏地址", url)
    assert not any(d["name"] == "坏地址" for d in store.list("workspace"))


def test_clone_token_goes_through_env_not_argv(store, monkeypatch):
    store.token_for = lambda host: "ghp_SECRET123" if host == "github.com" else ""
    real, seen = subprocess.run, {}

    def spy(argv, **kw):
        if argv[1] != "clone":
            return real(argv, **kw)
        seen["argv"], seen["env"] = argv, kw["env"]
        dest = Path(kw["cwd"]) / argv[-1]
        dest.mkdir(parents=True)
        real(["git", "init", "-q"], cwd=dest, check=True)
        real(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"],
             cwd=dest, check=True)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("agent.workspaces.subprocess.run", spy)
    store.clone("私有仓库", "https://github.com/acme/private.git")
    assert not any("SECRET123" in a for a in seen["argv"])          # 令牌不进命令行（ps 看得到）
    assert seen["env"]["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert seen["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_clone_error_redacts_token(store, monkeypatch):
    store.token_for = lambda host: "ghp_SECRET123"

    def boom(argv, **kw):
        return subprocess.CompletedProcess(argv, 128, "", "fatal: auth failed for ghp_SECRET123")

    monkeypatch.setattr("agent.workspaces.subprocess.run", boom)
    with pytest.raises(WorkspaceError) as exc:
        store.clone("泄露测试", "https://github.com/acme/private.git")
    assert "SECRET123" not in str(exc.value) and "***" in str(exc.value)
    assert not any(d["name"] == "泄露测试" for d in store.list("workspace"))


# ---------------- 集成设置 ----------------
def test_integrations_never_return_secrets(cfg, tmp_path):
    st = IntegrationStore(tmp_path / "i.json")
    st.set_linear({"api_key": "lin_api_SECRET", "team_key": "abc", "project_name": ""})
    st.set_token("https://GitHub.com/x", "ghp_TOKEN")
    st.set_git({"user_name": "晨熠", "user_email": "a@b.c"})
    st.apply(cfg)
    assert cfg.linear_key == "lin_api_SECRET" and cfg.linear_team_key == "ABC" and cfg.linear_project_name == ""
    assert (cfg.git_name, cfg.git_email) == ("晨熠", "a@b.c")
    pub = json.dumps(st.public(cfg), ensure_ascii=False)
    assert "SECRET" not in pub and "ghp_TOKEN" not in pub
    assert st.public(cfg)["git"]["hosts"] == ["github.com"] and st.git_token("github.com") == "ghp_TOKEN"
    # 重启后还在；清除后恢复演示配置
    st2 = IntegrationStore(tmp_path / "i.json")
    st2.clear_linear()
    st2.apply(cfg)
    assert cfg.linear_key_override == "" and cfg.linear_team_key == "DAY" and cfg.linear_project_name == "演示"


def test_integrations_validation(tmp_path):
    st = IntegrationStore(tmp_path / "i.json")
    with pytest.raises(IntegrationError):
        st.set_linear({"team_key": "DAY"})                       # 没有 Key
    with pytest.raises(IntegrationError):
        st.set_git({"user_name": "只有名字", "user_email": ""})
    with pytest.raises(IntegrationError):
        st.set_git({"user_name": "a", "user_email": "bad"})
    with pytest.raises(IntegrationError):
        st.set_token("github.com", "has space")
    with pytest.raises(IntegrationError):
        st.set_token("not a host!", "tok")


# ---------------- 经 HTTP 的完整流程 ----------------
def test_http_workspace_flow_and_session_uses_active(running, cfg):
    app, port = running
    cookie = login(port)
    assert call(port, "GET", "/api/workspaces")[0] == 401
    status, listing, _ = call(port, "GET", "/api/workspaces", cookie=cookie)
    assert status == 200 and listing["active_workspace"] == "demo"

    z = make_zip({"proj/app.py": "def f():\n    return 1\n", "proj/README.md": "# hi\n"})
    status, body, _ = call(port, "POST", "/api/workspaces/upload?name=%E4%B8%8A%E4%BC%A0%E6%B5%8B%E8%AF%95&kind=workspace",
                           cookie=cookie, ctype="application/zip", raw=z)
    assert status == 201, body
    wid = body["created"]["id"]

    assert call(port, "GET", f"/api/workspaces/{wid}/tree", cookie=cookie)[1]["entries"][0]["name"] == "app.py"
    status, f, _ = call(port, "GET", f"/api/workspaces/{wid}/file?path=app.py", cookie=cookie)
    assert status == 200 and "return 1" in f["text"]
    assert call(port, "GET", f"/api/workspaces/{wid}/file?path=../../x", cookie=cookie)[0] == 400
    assert call(port, "GET", "/api/workspaces/..%2Fetc/tree", cookie=cookie)[0] == 400

    assert call(port, "POST", f"/api/workspaces/{wid}/activate", {}, cookie=cookie)[1]["active_workspace"] == wid
    _, st, _ = call(port, "GET", "/api/status", cookie=cookie)
    assert st["workspace"] == "上传测试" and st["workspace_resettable"] is False
    assert call(port, "POST", "/api/demo/reset", {}, cookie=cookie)[0] == 409   # 真实工作区不允许被「重置」

    status, s, _ = call(port, "POST", "/api/sessions", {"use_jev": False}, cookie=cookie)
    assert status == 201
    assert app.live[s["id"]].agent.cfg.workspace == app.workspaces.path(wid)
    # 显式指定工作区、指定不存在的工作区
    assert call(port, "POST", "/api/sessions", {"workspace": "demo"}, cookie=cookie)[0] == 201
    assert call(port, "POST", "/api/sessions", {"workspace": "nope"}, cookie=cookie)[0] == 400

    # 删除当前选中的 → 自动回到演示
    assert call(port, "DELETE", f"/api/workspaces/{wid}", cookie=cookie)[1]["active_workspace"] == "demo"


def test_http_raw_is_download_not_inline(running):
    app, port = running
    cookie = login(port)
    wid = app.workspaces.import_zip("xss", make_zip({"evil.html": "<script>alert(1)</script>"}))["id"]
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", f"/api/workspaces/{wid}/raw?path=evil.html", headers={"Cookie": cookie})
    r = conn.getresponse()
    r.read()
    assert r.status == 200 and r.getheader("Content-Type") == "application/octet-stream"
    assert "attachment" in r.getheader("Content-Disposition") and r.getheader("X-Content-Type-Options") == "nosniff"


def test_http_integrations_flow(running, monkeypatch):
    app, port = running
    cookie = login(port)
    status, pub, _ = call(port, "GET", "/api/integrations", cookie=cookie)
    assert status == 200 and pub["onboarded"] is False and pub["linear"]["demo"] is True

    # Linear 连不上 → 不保存
    monkeypatch.setattr(app, "linear_client", lambda *a, **k: type("C", (), {"_resolve": lambda s: (_ for _ in ()).throw(
        __import__("agent.tools.base", fromlist=["ToolError"]).ToolError("找不到团队 ZZZ"))})())
    status, err, _ = call(port, "PUT", "/api/integrations/linear",
                          {"api_key": "lin_api_X", "team_key": "zzz"}, cookie=cookie)
    assert status == 400 and "ZZZ" in err["error"]
    assert call(port, "GET", "/api/integrations", cookie=cookie)[1]["linear"]["demo"] is True

    monkeypatch.setattr(app, "linear_client", lambda *a, **k: type("C", (), {"_resolve": lambda s: None})())
    status, pub, _ = call(port, "PUT", "/api/integrations/linear",
                          {"api_key": "lin_api_X", "team_key": "abc", "project_name": ""}, cookie=cookie)
    assert status == 200 and pub["linear"] == {"configured": True, "source": "panel", "team_key": "ABC",
                                                "project_name": "", "demo": False}
    assert "lin_api_X" not in json.dumps(pub)
    assert app.cfg.linear_key == "lin_api_X"

    status, pub, _ = call(port, "PUT", "/api/integrations/git/tokens/github.com", {"token": "ghp_T"}, cookie=cookie)
    assert pub["git"]["hosts"] == ["github.com"] and "ghp_T" not in json.dumps(pub)
    assert call(port, "PUT", "/api/integrations/onboarded", {"done": True}, cookie=cookie)[1]["onboarded"] is True
    assert call(port, "DELETE", "/api/integrations/linear", cookie=cookie)[1]["linear"]["demo"] is True


def test_session_uses_active_vault_and_git_identity(running, cfg):
    app, port = running
    cookie = login(port)
    vid = app.workspaces.import_zip("我的笔记", make_zip({"Vault/周会.md": "# 周会\n"}), kind="vault")["id"]
    assert call(port, "POST", f"/api/workspaces/{vid}/activate", {}, cookie=cookie)[1]["active_vault"] == vid
    call(port, "PUT", "/api/integrations/git", {"user_name": "晨熠", "user_email": "a@b.c"}, cookie=cookie)
    _, s, _ = call(port, "POST", "/api/sessions", {"use_jev": False}, cookie=cookie)
    agent = app.live[s["id"]].agent
    assert agent.ctx.vault == app.workspaces.path(vid, "vault") and (agent.ctx.vault / "周会.md").exists()
    assert agent.ctx.git_identity == ("晨熠", "a@b.c")
    # 笔记库只能设给 vault、工作区只能设给 workspace，不能串
    wid = app.workspaces.create_empty("普通项目")["id"]
    assert (call(port, "POST", f"/api/workspaces/{wid}/activate", {}, cookie=cookie)[1]["active_vault"]) == vid


def test_linear_scope_team_vs_project():
    from agent.tools.base import ToolError
    from agent.tools.linear import LinearClient

    def fake(project_name, issue):
        lc = LinearClient("k", "DAY", project_name)
        lc._team, lc._project_id = {"id": "T1", "states": {"nodes": []}}, ("P1" if project_name else "")
        lc.gql = lambda q, v=None: {"issue": issue}
        return lc

    # 选了项目：只认该项目里的 issue
    assert fake("P", {"identifier": "DAY-1", "project": {"id": "P1"}, "team": {"id": "T1"}}).issue("DAY-1")
    with pytest.raises(ToolError):
        fake("P", {"identifier": "DAY-2", "project": {"id": "OTHER"}, "team": {"id": "T1"}}).issue("DAY-2")
    # 没选项目：放宽到团队，团队外仍拒绝
    assert fake("", {"identifier": "DAY-3", "project": None, "team": {"id": "T1"}}).issue("DAY-3")
    with pytest.raises(ToolError):
        fake("", {"identifier": "ENG-9", "project": None, "team": {"id": "T2"}}).issue("ENG-9")
    assert fake("", {}).scope_filter() == {"team": {"id": {"eq": "T1"}}}
    assert fake("P", {}).scope_filter() == {"project": {"id": {"eq": "P1"}}}
