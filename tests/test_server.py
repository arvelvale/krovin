"""Web 后端：登录、会话、SSE、网页确认写操作、越权与越界防护。真实 HTTP，不访问外网。"""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from agent import server as srv
from agent.kernel import Agent
from agent.config import Endpoint

from conftest import FakeDecision, FakeLLM, noul_ans, reply

TOKEN = "test-token-123"


def gate_low(name, q, state):
    """技能选中 implement-change；门控 in_scope 0.3 → 需要网页确认。"""
    if name == "skill":
        probs = {k: 0.0 for k in q["criteria"]}
        probs["implement_change"] = 1.0
        return {"type": "choice", "choice": "implement_change", "confidence": 1.0, "probabilities": probs}
    if name in ("acts", "procedure", "fits_implement_change"):
        return noul_ans(0.9)
    if name == "prose":
        return noul_ans(0.1)
    if name == "in_scope":
        return noul_ans(0.3)
    if name == "collateral":
        return noul_ans(0.05)
    if name == "difficulty":
        return {"type": "choice", "choice": "simple", "confidence": 1.0,
                "probabilities": {"simple": 1.0, "moderate": 0.0, "hard": 0.0}}
    if name == "writes_code":
        return noul_ans(0.0)
    return None


@pytest.fixture
def running(cfg, monkeypatch):
    monkeypatch.setattr(srv.time, "sleep", lambda s: None)  # 登录失败的惩罚延时
    app = srv.App(cfg, TOKEN)

    def factory(cfg_, **kw):
        clients = {"local": FakeLLM("local", [
            reply(calls=[("edit_file", {"path": "app.py", "old": "sum(xs)", "new": "sum(xs) or 0"})]),
            reply("改好了"),
        ]), "backup": FakeLLM("backup"), "cloud": FakeLLM("cloud"), "vision": FakeLLM("vision")}
        agent = Agent(cfg_, decision=FakeDecision(gate_low), clients=clients, **kw)
        agent.router.healthy = lambda ep, ttl=60: True
        return agent

    app.agent_factory = factory
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.make_handler(app))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield app, httpd.server_address[1]
    httpd.shutdown()


def call(port, method, path, body=None, cookie="", ctype="application/json", raw=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Cookie": cookie} if cookie else {}
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    if data is not None:
        headers["Content-Type"] = ctype
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    payload = resp.read()
    try:
        parsed = json.loads(payload) if payload else None
    except json.JSONDecodeError:
        parsed = payload.decode("utf-8", "replace")
    return resp.status, parsed, resp.getheader("Set-Cookie") or ""


def login(port) -> str:
    status, _, set_cookie = call(port, "POST", "/api/login", {"token": TOKEN})
    assert status == 200 and "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie
    return set_cookie.split(";")[0]


def test_auth_required(running):
    _, port = running
    assert call(port, "GET", "/api/status")[0] == 401
    assert call(port, "POST", "/api/login", {"token": "wrong"})[0] == 401
    assert call(port, "GET", "/api/status", cookie="dgx_session=forged")[0] == 401
    cookie = login(port)
    status, data, _ = call(port, "GET", "/api/status", cookie=cookie)
    assert status == 200 and {"local", "cloud", "jev", "linear"} <= set(data["services"])
    assert any(s["name"] == "implement-change" for s in data["skills"])


def test_image_upload_turn_history_and_auth(running):
    app, port = running
    app.cfg.vision = Endpoint("vision", "http://127.0.0.1:2/v1", "qwen3.8:27b")
    cookie = login(port)
    sid = call(port, "POST", "/api/sessions", {"tier": "local"}, cookie=cookie)[1]["id"]
    path = f"/api/sessions/{sid}/images"
    png = b"\x89PNG\r\n\x1a\n" + b"test-image"
    assert call(port, "POST", path, raw=png, ctype="image/png")[0] == 401
    assert call(port, "POST", path, raw=b"invalid", ctype="image/png", cookie=cookie)[0] == 400
    status, uploaded, _ = call(port, "POST", path, raw=png, ctype="image/png", cookie=cookie)
    assert status == 201
    image_id = uploaded["id"]
    assert call(port, "GET", f"{path}/{image_id}")[0] == 401
    assert call(port, "POST", f"/api/sessions/{sid}/turn", {"images": ["i-" + "0" * 32]}, cookie=cookie)[0] == 400
    app.live[sid].agent.clients["vision"].script = [reply("我看到了图片")]
    assert call(port, "POST", f"/api/sessions/{sid}/turn", {"images": [image_id]}, cookie=cookie)[0] == 202
    for _ in range(1000):
        if not app.live[sid].busy:
            break
        threading.Event().wait(0.01)
    assert not app.live[sid].busy
    hist = call(port, "GET", f"/api/sessions/{sid}", cookie=cookie)[1]
    assert hist["messages"][0]["images"] == [image_id]
    assert hist["events"][0]["data"]["images"] == [image_id]
    received = app.live[sid].agent.clients["vision"].received
    assert received and received[0][-1]["content"][1]["type"] == "image_url"
    assert "base64" not in str(hist)


def test_json_only_and_bad_ids(running):
    _, port = running
    cookie = login(port)
    assert call(port, "POST", "/api/sessions", raw=b"use_jev=1", ctype="application/x-www-form-urlencoded",
                cookie=cookie)[0] == 415
    assert call(port, "GET", "/api/sessions/..%2F..%2Fetc", cookie=cookie)[0] == 400
    assert call(port, "GET", "/api/sessions/s-does-not-exist", cookie=cookie)[0] == 404


def read_sse(port, sid, cookie, stop_kinds, answer=None, limit=200):
    """读 SSE 直到收到 stop_kinds 里任一事件；answer(kind, data) 可在收到事件时发请求。"""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", f"/api/sessions/{sid}/stream", headers={"Cookie": cookie})
    resp = conn.getresponse()
    assert resp.status == 200 and resp.getheader("Content-Type").startswith("text/event-stream")
    got, kind = [], None
    for _ in range(limit * 3):
        line = resp.fp.readline().decode("utf-8").rstrip("\n")
        if line.startswith("event: "):
            kind = line[7:]
        elif line.startswith("data: ") and kind:
            data = json.loads(line[6:])
            got.append((kind, data))
            if answer:
                answer(kind, data)
            if kind in stop_kinds:
                break
    conn.close()
    return got


def test_turn_with_web_confirmation(running, cfg):
    app, port = running
    cookie = login(port)
    status, data, _ = call(port, "POST", "/api/sessions", {"use_jev": True, "tier": "auto"}, cookie=cookie)
    sid = data["id"]
    assert status == 201 and sid in app.live

    result = {}

    def start_turn():
        result["turn"] = call(port, "POST", f"/api/sessions/{sid}/turn", {"text": "把 total 改一下"}, cookie=cookie)

    def on_event(kind, data):
        if kind == "confirm":
            assert data["tool"] == "edit_file" and data["in_scope"] == pytest.approx(0.3)
            assert call(port, "POST", f"/api/sessions/{sid}/confirm", {"id": data["id"], "approve": True},
                        cookie=cookie)[0] == 200

    threading.Timer(0.3, start_turn).start()
    events = read_sse(port, sid, cookie, {"turn_done"}, on_event)
    kinds = [k for k, _ in events]
    assert result["turn"][0] == 202
    assert "confirm" in kinds and "confirm_resolved" in kinds and "working" in kinds
    trace_types = [d["type"] for k, d in events if k == "trace"]
    assert trace_types[0] == "turn.start" and "tool.gate" in trace_types
    done = dict(events)["turn_done"]
    assert done["reply"] == "改好了" and done["skills"] == ["implement-change"]
    assert "or 0" in (cfg.workspace / "app.py").read_text(encoding="utf-8")

    status, hist, _ = call(port, "GET", f"/api/sessions/{sid}", cookie=cookie)
    assert hist["live"] and not hist["busy"]
    assert [m["role"] for m in hist["messages"]] == ["user", "assistant"]
    assert any(e["type"] == "turn.end" for e in hist["events"])
    status, listing, _ = call(port, "GET", "/api/sessions", cookie=cookie)
    assert listing[0]["id"] == sid and listing[0]["title"] == "把 total 改一下" and listing[0]["live"]


def test_stop_turn_via_http(running, cfg):
    """运行中点「停止」：确认卡按拒绝处理，轮次在步边界收尾，不再调用模型。"""
    app, port = running
    cookie = login(port)
    sid = call(port, "POST", "/api/sessions", {"use_jev": True, "tier": "auto"}, cookie=cookie)[1]["id"]
    calls = {"n": 0}
    base_calls = len(app.live[sid].agent.clients["local"].received)

    def on_event(kind, data):
        if kind == "confirm":
            # 确认卡弹出的这一刻用户点了「停止」：卡按拒绝，内核步边界收尾
            status, body, _ = call(port, "POST", f"/api/sessions/{sid}/stop", {}, cookie=cookie)
            assert status == 200 and body["stopped"] is True
        if kind == "trace" and data["type"] == "llm.start":
            calls["n"] += 1

    threading.Timer(0.3, lambda: call(port, "POST", f"/api/sessions/{sid}/turn",
                                      {"text": "把 total 改一下"}, cookie=cookie)).start()
    events = read_sse(port, sid, cookie, {"turn_done"}, on_event)
    done = dict(events)["turn_done"]
    assert done["stopped"] == "stopped" and "已停止" in done["reply"]
    assert calls["n"] == 1  # 第一批工具之后没有再调模型
    assert "or 0" not in (cfg.workspace / "app.py").read_text(encoding="utf-8")  # 被拒了，没写进去
    trace_types = [data["type"] for kind, data in events if kind == "trace"]
    assert "turn.stop" in trace_types and trace_types[-1] == "turn.end"

    # 轮次已结束：再点停止返回 stopped=false，不报错
    status, body, _ = call(port, "POST", f"/api/sessions/{sid}/stop", {}, cookie=cookie)
    assert status == 200 and body["stopped"] is False
    # 没有这个在线会话：404
    assert call(port, "POST", "/api/sessions/s-not-live/stop", {}, cookie=cookie)[0] == 404


def test_reasoning_reaches_stream_and_history_without_entering_trace(running):
    app, port = running
    cookie = login(port)
    sid = call(port, "POST", "/api/sessions", {}, cookie=cookie)[1]["id"]
    app.live[sid].agent.clients["local"].script[0].reasoning = "先读取文件，再核对金额精度。 Bearer test-secret-token-12345"

    def on_event(kind, data):
        if kind == "confirm":
            call(port, "POST", f"/api/sessions/{sid}/confirm", {"id": data["id"], "approve": False}, cookie=cookie)

    threading.Timer(0.3, lambda: call(port, "POST", f"/api/sessions/{sid}/turn",
                                      {"text": "把 total 改一下"}, cookie=cookie)).start()
    streamed = read_sse(port, sid, cookie, {"turn_done"}, on_event)
    trace_types = [data["type"] for kind, data in streamed if kind == "trace"]
    assert trace_types.index("llm.start") < trace_types.index("llm.call")
    thought = next(data for kind, data in streamed if kind == "reasoning")
    assert thought["step"] == 1 and "先读取文件" in thought["text"]
    assert "test-secret-token-12345" not in thought["text"]

    status, history, _ = call(port, "GET", f"/api/sessions/{sid}", cookie=cookie)
    assert status == 200 and history["reasoning"] == [thought]
    assert all("先读取文件" not in json.dumps(event, ensure_ascii=False) for event in history["events"])


def test_busy_session_rejects_second_turn(running):
    app, port = running
    cookie = login(port)
    sid = call(port, "POST", "/api/sessions", {}, cookie=cookie)[1]["id"]
    app.live[sid].busy = True
    assert call(port, "POST", f"/api/sessions/{sid}/turn", {"text": "再来"}, cookie=cookie)[0] == 409
    assert call(port, "POST", f"/api/sessions/{sid}/turn", {"text": "  "}, cookie=cookie)[0] == 400


def test_confirm_unknown_id(running):
    _, port = running
    cookie = login(port)
    sid = call(port, "POST", "/api/sessions", {}, cookie=cookie)[1]["id"]
    assert call(port, "POST", f"/api/sessions/{sid}/confirm", {"id": "nope", "approve": True}, cookie=cookie)[0] == 404


def test_memory_endpoints(running):
    app, port = running
    cookie = login(port)
    m = app.memory.add("semantic", "fact", "金额按分存整数", status="pending")
    status, items, _ = call(port, "GET", "/api/memory?status=pending", cookie=cookie)
    assert [i["id"] for i in items] == [m.id]
    assert call(port, "POST", f"/api/memory/{m.id}/approve", {}, cookie=cookie)[1]["ok"]
    assert call(port, "DELETE", f"/api/memory/{m.id}", cookie=cookie)[1]["ok"]


def test_asr_without_key(running, monkeypatch):
    _, port = running
    monkeypatch.delenv("STEPFUN_API_KEY", raising=False)
    cookie = login(port)
    status, data, _ = call(port, "POST", "/api/asr?format=wav", raw=b"RIFF....", ctype="audio/wav", cookie=cookie)
    assert status == 502 and "STEPFUN_API_KEY" in data["error"]


def test_static_does_not_escape(running, monkeypatch, tmp_path):
    _, port = running
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>面板</html>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(srv, "DIST", dist)
    status, body, _ = call(port, "GET", "/../secret.txt")
    assert status == 200 and "secret" not in body and "面板" in body


def test_dev_no_auth_refuses_public_host(cfg):
    with pytest.raises(SystemExit, match="回环"):
        srv.serve(cfg, "0.0.0.0", 0, no_auth=True)


def test_startup_lines_show_real_public_address():
    lines = srv.startup_lines("0.0.0.0", 9000, "tok", False, "http://203.0.113.7:9006")
    assert lines[0].startswith("面板已启动：http://203.0.113.7:9006")
    assert "<公网地址>" not in "".join(lines) and any("注意" in l for l in lines)
    # 没给公网地址时不编一个出来，明确说去哪查
    assert "登录表" in srv.startup_lines("0.0.0.0", 9000, "tok", False)[0]
    assert srv.startup_lines("127.0.0.1", 9000, "tok", True)[0] == "面板已启动：http://127.0.0.1:9000"


# ---------------- 登录态持久化 ----------------
def test_login_survives_restart_without_storing_cookie(running, cfg):
    app, port = running
    cookie = login(port)
    value = cookie.split("=", 1)[1]
    stored = (cfg.data_dir / "web_sessions.json").read_text(encoding="utf-8")
    assert value not in stored  # 只存哈希
    restarted = srv.App(cfg, TOKEN)  # 模拟重启：新进程从文件读回登录态
    assert restarted.sessions.valid(value)


def test_changing_token_or_logout_invalidates(running, cfg):
    app, port = running
    cookie = login(port)
    value = cookie.split("=", 1)[1]
    assert not srv.App(cfg, "another-token").sessions.valid(value)  # 换口令 = 踢掉所有人
    call(port, "POST", "/api/logout", {}, cookie=cookie)
    assert call(port, "GET", "/api/status", cookie=cookie)[0] == 401
    assert not srv.App(cfg, TOKEN).sessions.valid(value)  # 退出也落盘了


def test_expired_session_rejected(cfg, monkeypatch):
    s = srv.WebSessions(cfg.data_dir / "web_sessions.json", TOKEN)
    value = s.create()
    monkeypatch.setattr(srv.time, "time", lambda: 10**12)  # 远在 7 天之后
    assert not s.valid(value)


def test_corrupt_session_file_is_ignored(cfg):
    path = cfg.data_dir / "web_sessions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{坏掉的", encoding="utf-8")
    s = srv.WebSessions(path, TOKEN)
    assert not s.valid("anything") and s.valid(s.create())


# ---------------- 重置演示仓库 ----------------
def test_reset_demo_only_for_sandbox(running, cfg, tmp_path, monkeypatch):
    app, port = running
    cookie = login(port)
    # conftest 的工作区在 tmp_path/ws，不在 data_dir/workspace 下：必须拒绝，绝不能删
    assert (cfg.workspace / ".git").exists()
    status, body, _ = call(port, "POST", "/api/demo/reset", {}, cookie=cookie)
    assert status == 409 and "不是演示沙盒" in body["error"] and (cfg.workspace / ".git").exists()
    assert call(port, "GET", "/api/status", cookie=cookie)[1]["workspace_resettable"] is False


def test_reset_demo_rebuilds_sandbox(running, cfg):
    app, port = running
    cookie = login(port)
    cfg.workspace = cfg.data_dir / "workspace" / "tinyledger"
    status, body, _ = call(port, "POST", "/api/demo/reset", {}, cookie=cookie)
    assert status == 200 and body["workspace"] == "tinyledger"
    assert (cfg.workspace / "tinyledger" / "store.py").exists() and (cfg.workspace / ".git").exists()
    (cfg.workspace / "tinyledger" / "store.py").write_text("# 评委改坏了\n", encoding="utf-8")
    assert call(port, "POST", "/api/demo/reset", {}, cookie=cookie)[0] == 200
    assert "float" in (cfg.workspace / "tinyledger" / "store.py").read_text(encoding="utf-8")  # 回到带 bug 的起点

def test_delete_session_cleans_exclusive_workspace_and_sandbox(running, monkeypatch):
    app, port = running
    cookie = login(port)
    wid = app.workspaces.create_empty('cleanup')['id']
    app.integrations.set_active('workspace', wid)
    s = app.new_session(True, 'local', wid)
    s.agent.trace.emit('tool.call', {'tool': 'run_in_sandbox', 'ok': True})
    root = app.workspaces.path(wid)
    cleaned = []
    monkeypatch.setattr(srv, 'get_sandbox', lambda: type('Sandbox', (), {'cleanup': lambda self, tag: cleaned.append(tag)})())
    plan = call(port, 'GET', f'/api/sessions/{s.id}/cleanup', cookie=cookie)[1]
    assert plan['delete_workspace'] is True and 'cleanup' in plan['description']
    code, result, _ = call(port, 'DELETE', f'/api/sessions/{s.id}', {'delete_workspace': True}, cookie)
    assert code == 200 and result['workspace_deleted'] is True
    assert cleaned == [s.id[-8:].replace('-', '')]
    assert not root.exists() and not (app.cfg.data_dir/'runs'/s.id).exists()
    assert app.integrations.active('workspace') == 'demo'


def test_delete_session_keeps_shared_workspace_and_rechecks_preview(running):
    app, port = running
    cookie = login(port)
    wid = app.workspaces.create_empty('shared')['id']
    first = app.new_session(True, 'local', wid)
    second = app.new_session(True, 'local', wid)
    app.live.pop(first.id)  # 重启后的历史会话也必须计入共享引用。
    root = app.workspaces.path(wid)
    plan = app.session_cleanup(first.id)
    assert plan['delete_workspace'] is False and '共用' in plan['description']
    app.delete_session(first.id, False)
    assert root.exists()
    # 之前显示保留的工作区，如今成为独占，必须重新确认，不能悄悄扩大删除范围。
    code, _, _ = call(port, 'DELETE', f'/api/sessions/{second.id}', {'delete_workspace': False}, cookie)
    assert code == 409 and root.exists()
    assert (app.cfg.data_dir/'runs'/second.id).exists()


def test_cleanup_failure_preserves_session_and_workspace(running, monkeypatch):
    app, _ = running
    wid = app.workspaces.create_empty('retry')['id']
    s = app.new_session(True, 'local', wid)
    s.agent.trace.emit('tool.call', {'tool': 'run_in_sandbox', 'ok': True})
    def fail(self, tag):
        raise srv.SandboxError('cleanup failed')
    monkeypatch.setattr(srv, 'get_sandbox', lambda: type('Sandbox', (), {'cleanup': fail})())
    with pytest.raises(RuntimeError, match='会话尚未删除'):
        app.delete_session(s.id)
    assert s.id in app.live and app.workspaces.path(wid).exists()
    assert (app.cfg.data_dir/'runs'/s.id).exists()


def test_busy_and_demo_workspace_protected(running):
    app, _ = running
    s = app.new_session(True, 'local', 'demo')
    s.busy = True
    with pytest.raises(RuntimeError, match='进行中'):
        app.delete_session(s.id)
    s.busy = False
    assert app.session_cleanup(s.id)['delete_workspace'] is False
    app.delete_session(s.id)
    assert app.cfg.workspace.exists()

def test_history_resume_same_id_workspace_and_next_turn(running):
    app, port = running
    cookie=login(port)
    wid=app.workspaces.create_empty('resume-test')['id']
    s=app.new_session(True,'local',wid)
    s.agent.trace.turn=3
    s.agent.trace.emit('turn.start',{'input':'原任务'})
    s.agent.conv.add({'role':'user','content':'请记住原任务'},3)
    app.live.pop(s.id)
    code, data, _=call(port,'POST',f'/api/sessions/{s.id}/resume',{},cookie)
    assert code==200 and data['id']==s.id
    restored=app.live[s.id]
    assert restored.agent.cfg.workspace==app.workspaces.path(wid)
    assert restored.agent.trace.turn==3 and not restored.busy
    assert any(m.get('content')=='请记住原任务' for m in restored.agent.conv.messages)
    assert call(port,'POST',f'/api/sessions/{s.id}/resume',{},cookie)[0]==200
    assert app.live[s.id] is restored


def test_resume_refuses_missing_original_workspace(running):
    app, port=running
    cookie=login(port)
    wid=app.workspaces.create_empty('gone')['id']
    s=app.new_session(True,'local',wid)
    s.agent.trace.emit('turn.start',{'input':'x'})
    app.live.pop(s.id)
    app.workspaces.delete(wid)
    assert call(port,'POST',f'/api/sessions/{s.id}/resume',{},cookie)[0]==409
    assert s.id not in app.live


def test_bypass_http_persistence_and_switch(running):
    app, port = running
    cookie = login(port)
    sid = call(port, "POST", "/api/sessions", {"bypass": True}, cookie=cookie)[1]["id"]
    assert app.live[sid].agent.bypass
    assert call(port, "GET", f"/api/sessions/{sid}", cookie=cookie)[1]["bypass"]
    app.live.pop(sid)
    resumed = app.resume_session(sid)
    assert resumed.agent.bypass
    body = call(port, "PATCH", f"/api/sessions/{sid}", {"bypass": False, "yolo": True}, cookie=cookie)[1]
    assert not body["bypass"] and body["yolo"]
