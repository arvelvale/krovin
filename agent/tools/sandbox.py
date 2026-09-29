"""在 OpenShell 沙箱里运行任意命令（见 agent/sandbox.py）。"""
from __future__ import annotations

from .base import Permission, Tool, ToolContext, arg, params


def run_in_sandbox(args: dict, ctx: ToolContext) -> str:
    command = str(arg(args, "command", required=True)).strip()
    timeout = min(max(int(arg(args, "timeout", 60)), 5), 300)
    if ctx.sandbox is None:
        from ..sandbox import get_sandbox  # 延迟导入：agent.sandbox 反过来要用 tools.base
        ctx.sandbox = get_sandbox()
    r = ctx.sandbox.run(command, ctx.workspace, timeout=timeout, tag=ctx.sandbox_tag)  # SandboxError 是 ToolError
    head = f"退出码 {r.exit_code}（{r.seconds:.1f}s）"
    if r.exit_code == 124 or "timed out" in r.output[-200:].lower():
        head += "，可能超时了"
    lines = [head, r.output or "（没有输出）"]
    if r.changed:
        lines.append("已同步回工作区：" + "、".join(f"{'新增' if k == 'added' else '修改'} {p}" for k, p in r.changed[:20])
                     + ("…" if len(r.changed) > 20 else ""))
    if r.skipped:
        lines.append(f"（另有 {r.skipped} 个文件太大或越界，没有同步回来）")
    return "\n".join(lines)


TOOLS = [
    Tool("run_in_sandbox",
         "在 OpenShell 沙箱里运行命令（bash）：网络仅限策略允许的软件源，系统目录只读、只有沙箱内的工作目录可写，Python 3.14 / Node 22 / git 可用。"
         "工作区会先复制进去，运行结束后新增或修改的文件同步回工作区（不同步删除）。"
         "可运行程序、测试和构建；npm/pip 软件源已配置，安装失败时报告实际错误。"
         "普通网页不走沙箱 curl，请用 fetch_webpage；成品页面用预览查看。",
         params({"command": {"type": "string", "description": "bash 命令，在工作区根目录执行"},
                 "timeout": {"type": "integer", "description": "秒，默认 60，最大 300"}}, ["command"]),
         Permission.WRITE_LOCAL, run_in_sandbox),
]
