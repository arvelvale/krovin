"""全自动（yolo）模式：不再等人点同意，但技能白名单、外部写的 JEV 拦截仍然有效。"""
import threading

from agent.gate import ConfirmRequest, ToolGate
from agent.config import Thresholds
from agent.tools.base import Permission, Tool

from conftest import FakeDecision, noul_ans
from test_server import call, login, read_sse, running  # noqa: F401  复用真实 HTTP 夹具
from test_server import gate_low


def tool(perm):
    return Tool("t", "d", {}, perm, lambda a, c: "ok")


def make_gate(in_scope, collateral=0.05, yolo=False, asked=None):
    def fn(name, q, state):
        return noul_ans(in_scope if name == "in_scope" else collateral) if name in ("in_scope", "collateral") else None
    gate = ToolGate(Thresholds(), FakeDecision(fn), lambda req: (asked.append(req) or True) if asked is not None else True)
    gate.yolo = yolo
    return gate


def test_yolo_skips_confirmation_but_keeps_hard_limits():
    asked = []
    # 平时：JEV 觉得像跑偏 → 要问用户
    g = make_gate(0.3, yolo=False, asked=asked).check(tool(Permission.WRITE_LOCAL), {}, allowed=True, goal="", request="r")
    assert g.decision == "confirm" and len(asked) == 1
    # 全自动：不问，直接执行，并标记 auto
    asked.clear()
    g = make_gate(0.3, yolo=True, asked=asked).check(tool(Permission.WRITE_LOCAL), {}, allowed=True, goal="", request="r")
    assert g.decision == "allow" and g.auto and g.execute and not asked
    # 外部写：平时一律问；全自动不问
    g = make_gate(0.9, yolo=True, asked=asked).check(tool(Permission.EXTERNAL), {}, allowed=True, goal="", request="r")
    assert g.decision == "allow" and g.auto and not asked
    # 硬边界 1：技能没授权的工具照样拒绝
    g = make_gate(0.9, yolo=True).check(tool(Permission.WRITE_LOCAL), {}, allowed=False, goal="", request="r")
    assert g.decision == "deny" and not g.execute
    # 硬边界 2：外部写 JEV 判定与请求不符，全自动也拦截
    g = make_gate(0.1, yolo=True).check(tool(Permission.EXTERNAL), {}, allowed=True, goal="", request="r")
    assert g.decision == "deny"
    # 只读工具与 JEV 不可用时也不受影响
    assert make_gate(0.9, yolo=True).check(tool(Permission.READ), {}, allowed=True, goal="", request="r").decision == "allow"


def test_http_yolo_turn_runs_without_confirmation(running, cfg):
    app, port = running
    cookie = login(port)
    sid = call(port, "POST", "/api/sessions", {"yolo": True}, cookie=cookie)[1]["id"]
    assert call(port, "GET", f"/api/sessions/{sid}", cookie=cookie)[1]["yolo"] is True
    threading.Timer(0.3, lambda: call(port, "POST", f"/api/sessions/{sid}/turn", {"text": "把 total 改一下"},
                                      cookie=cookie)).start()
    events = read_sse(port, sid, cookie, {"turn_done"})
    kinds = [k for k, _ in events]
    assert "confirm" not in kinds
    gates = [d["data"] for k, d in events if k == "trace" and d["type"] == "tool.gate"]
    assert gates and gates[0]["auto"] is True and gates[0]["decision"] == "allow"
    assert "or 0" in (cfg.workspace / "app.py").read_text(encoding="utf-8")


def test_toggle_yolo_approves_pending_and_traces(running):
    app, port = running
    cookie = login(port)
    sid = call(port, "POST", "/api/sessions", {}, cookie=cookie)[1]["id"]
    s = app.live[sid]
    assert call(port, "PATCH", f"/api/sessions/{sid}", {"yolo": "x"}, cookie=cookie)[1]["yolo"] is True  # 布尔化
    assert call(port, "PATCH", f"/api/sessions/{sid}", {"yolo": False}, cookie=cookie)[1]["yolo"] is False
    types = [e["type"] for e in s.agent.trace.events] if hasattr(s.agent.trace, "events") else None
    if types is not None:
        assert types.count("mode.change") == 2
    # 已经弹出来等着的确认：开全自动等于同意
    done = threading.Event()
    result = {}

    def ask():
        result["ok"] = s._confirm(ConfirmRequest("edit_file", "write_local", {}, "r", 0.3))
        done.set()

    threading.Thread(target=ask, daemon=True).start()
    for _ in range(50):
        if s.pending:
            break
        threading.Event().wait(0.05)
    assert s.pending
    call(port, "PATCH", f"/api/sessions/{sid}", {"yolo": True}, cookie=cookie)
    assert done.wait(3) and result["ok"] is True
