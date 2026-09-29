"""确认卡的人话说明、全自动由 JEV 代决定、会话改名与删除。"""
from pathlib import Path

from agent.config import Thresholds
from agent.describe import describe_action, explain_verdict
from agent.gate import ToolGate
from agent.skills import SkillScript
from agent.tools.base import Permission, Tool

from conftest import FakeDecision, noul_ans
from test_server import call, login, running  # noqa: F401


def test_describe_common_actions(tmp_path):
    (tmp_path / "old.py").write_text("x")
    assert describe_action("write_file", {"path": "old.py", "content": "a\nb\n"}, workspace=tmp_path).startswith("覆盖文件 old.py")
    assert describe_action("write_file", {"path": "new.py", "content": "a"}, workspace=tmp_path).startswith("新建文件 new.py")
    s = describe_action("edit_file", {"path": "a.py", "old": "sum(xs)", "new": "sum(xs) or 0"})
    assert "a.py" in s and "sum(xs)" in s and "换成" in s
    assert "提交改动" in describe_action("git_commit", {"message": "修复精度"}) and "全部" in describe_action("git_commit", {"message": "x"})
    assert describe_action("git_branch", {"name": "fix/x"}) == "新建并切换到分支 fix/x"
    assert "沙箱" in describe_action("run_in_sandbox", {"command": "node a.js"})
    assert describe_action("linear_update_issue", {"identifier": "DAY-298", "state": "Done", "comment": "已修复"}) \
        == "在 Linear 上对 DAY-298 把状态改为「Done」，添加评论 「已修复」"
    assert "新建 issue" in describe_action("linear_create_issue", {"title": "补测试", "parent": "DAY-1"})
    assert "调用 mystery" in describe_action("mystery", {"a": 1})


def test_describe_skill_script_uses_declared_description():
    scripts = {"implement-change": {"test_report.py": SkillScript("test_report.py", "运行测试并汇总失败用例", "write_local")}}
    s = describe_action("run_skill_script", {"skill": "implement-change", "script": "test_report.py", "args": []}, scripts=scripts)
    assert "implement-change" in s and "test_report.py" in s and "运行测试并汇总失败用例" in s
    # 脚本表里查不到也不能崩
    assert "x.py" in describe_action("run_skill_script", {"skill": "s", "script": "x.py"}, scripts={})


def test_verdict_wording():
    kw = dict(fallback=False, scope_threshold=0.5, collateral_threshold=0.5)
    assert "Linear" in explain_verdict("external", 0.9, 0.1, **kw)
    assert "越界风险 60%" in explain_verdict("write_local", 0.9, 0.6, **kw)
    v = explain_verdict("write_local", 0.42, 0.17, **kw)
    assert "42%" in v and "没发现会误伤" in v
    assert "不可用" in explain_verdict("write_local", None, None, **{**kw, "fallback": True})


def make_gate(scope, collateral, yolo, asked):
    fn = lambda name, q, state: noul_ans(scope if name == "in_scope" else collateral) if name in ("in_scope", "collateral") else None  # noqa: E731
    g = ToolGate(Thresholds(), FakeDecision(fn), lambda req: (asked.append(req) or True))
    g.yolo = yolo
    return g


def tool(perm):
    return Tool("edit_file", "d", {}, perm, lambda a, c: "ok")


def test_yolo_lets_jev_decide_instead_of_asking():
    asked = []
    # 关联度一般、没有越界风险：全自动放行；不问人
    g = make_gate(0.42, 0.17, True, asked).check(tool(Permission.WRITE_LOCAL), {}, allowed=True, goal="", request="r")
    assert g.decision == "allow" and g.auto and "42%" in g.reason and not asked
    # 有越界风险：全自动由 JEV 拦截，同样不问人
    g = make_gate(0.9, 0.8, True, asked).check(tool(Permission.WRITE_LOCAL), {}, allowed=True, goal="", request="r")
    assert g.decision == "deny" and g.auto and not g.execute and not asked
    # 没开全自动：这两种都要问人，并且确认请求里带着人话说明
    g = make_gate(0.42, 0.17, False, asked).check(tool(Permission.WRITE_LOCAL), {"path": "a"}, allowed=True, goal="",
                                                 request="r", summary="修改文件 a")
    assert g.decision == "confirm" and len(asked) == 1
    assert asked[0].summary == "修改文件 a" and "关联度一般" in asked[0].verdict


def test_confirm_card_carries_summary_and_trace(running, cfg):
    import threading
    from test_server import read_sse
    app, port = running
    cookie = login(port)
    sid = call(port, "POST", "/api/sessions", {}, cookie=cookie)[1]["id"]
    seen = {}

    def on_event(kind, data):
        if kind == "confirm":
            seen.update(data)
            call(port, "POST", f"/api/sessions/{sid}/confirm", {"id": data["id"], "approve": True}, cookie=cookie)

    threading.Timer(0.3, lambda: call(port, "POST", f"/api/sessions/{sid}/turn", {"text": "把 total 改一下"},
                                      cookie=cookie)).start()
    events = read_sse(port, sid, cookie, {"turn_done"}, on_event)
    assert "app.py" in seen["summary"] and "sum(xs)" in seen["summary"]
    assert "关联度" in seen["verdict"] or "越界" in seen["verdict"] or "合理" in seen["verdict"]
    gates = [d["data"] for k, d in events if k == "trace" and d["type"] == "tool.gate"]
    assert gates and "app.py" in gates[0]["summary"]


def test_rename_and_delete_sessions(running, cfg):
    app, port = running
    cookie = login(port)
    sid = call(port, "POST", "/api/sessions", {}, cookie=cookie)[1]["id"]
    # 改名：在线会话、空白名字回退、超长截断
    assert call(port, "PATCH", f"/api/sessions/{sid}", {"title": "  我的\n会话  "}, cookie=cookie)[1]["title"] == "我的 会话"
    listing = call(port, "GET", "/api/sessions", cookie=cookie)[1]
    mine = next(x for x in listing if x["id"] == sid)
    assert mine["title"] == "我的 会话" and mine["custom"] is True
    assert len(call(port, "PATCH", f"/api/sessions/{sid}", {"title": "长" * 200}, cookie=cookie)[1]["title"]) == 60
    call(port, "PATCH", f"/api/sessions/{sid}", {"title": ""}, cookie=cookie)
    assert next(x for x in call(port, "GET", "/api/sessions", cookie=cookie)[1] if x["id"] == sid)["title"] == "新对话"
    # 改名不影响档位 / 全自动的原有 PATCH
    assert call(port, "PATCH", f"/api/sessions/{sid}", {"title": "a", "yolo": True}, cookie=cookie)[1]["yolo"] is True
    # 编号不合法
    assert call(port, "PATCH", "/api/sessions/..%2Fx", {"title": "a"}, cookie=cookie)[0] == 400
    assert call(port, "DELETE", "/api/sessions/..%2Fx", cookie=cookie)[0] == 400
    # 进行中不能删；结束后能删，目录和在线状态一起没
    app.live[sid].busy = True
    assert call(port, "DELETE", f"/api/sessions/{sid}", cookie=cookie)[0] == 409
    app.live[sid].busy = False
    run_dir = cfg.data_dir / "runs" / sid
    assert run_dir.exists()
    assert call(port, "DELETE", f"/api/sessions/{sid}", cookie=cookie)[0] == 200
    assert not run_dir.exists() and sid not in app.live
    assert call(port, "GET", f"/api/sessions/{sid}", cookie=cookie)[0] == 404
    assert call(port, "DELETE", f"/api/sessions/{sid}", cookie=cookie)[0] == 200   # 重复删除不报错
    assert call(port, "DELETE", "/api/sessions/s-20260101-000000-abcd", cookie=None or "")[0] == 401
