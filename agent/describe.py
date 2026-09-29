"""把一次工具调用翻译成人话：确认卡上写「要做什么」，而不是工具名加一坨 JSON。

只用模板，不调模型：确认卡是安全边界，说明必须确定、和实际参数一一对应，不能让另一个模型再「转述」一遍。
参数原文仍然保留（卡片里折叠着，想核对可以展开）。
"""
from __future__ import annotations

from pathlib import Path


def _clip(text, n: int = 60) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= n else s[:n] + "…"


def _quote(text, n: int = 60) -> str:
    return f"「{_clip(text, n)}」"


def describe_action(tool: str, args: dict, *, workspace: Path | None = None, scripts: dict | None = None) -> str:
    """一句话说清这次调用要做什么。scripts：本轮命中技能的脚本表 {技能: {脚本名: SkillScript}}。"""
    a = args or {}
    if tool == "write_file":
        path = str(a.get("path", "?"))
        exists = bool(workspace and path and (workspace / path).exists())
        lines = str(a.get("content", "")).count("\n") + 1 if a.get("content") else 0
        return f"{'覆盖' if exists else '新建'}文件 {path}（{lines} 行）"
    if tool == "edit_file":
        return f"修改文件 {a.get('path', '?')}：把 {_quote(a.get('old', ''), 50)} 换成 {_quote(a.get('new', ''), 50)}"
    if tool == "run_command":
        return f"在工作区运行命令：{_clip(a.get('command', ''), 100)}"
    if tool == "run_in_sandbox":
        return f"在隔离沙箱里运行：{_clip(a.get('command', ''), 100)}（没有网络；运行产生或修改的文件会同步回工作区）"
    if tool == "run_skill_script":
        skill, name = str(a.get("skill", "?")), str(a.get("script", "?"))
        spec = ((scripts or {}).get(skill) or {}).get(name)
        what = f"：{spec.description}" if spec is not None and getattr(spec, "description", "") else ""
        extra = f"，参数 {_clip(' '.join(map(str, a.get('args') or [])), 60)}" if a.get("args") else ""
        return f"运行「{skill}」技能自带的脚本 {name}{what}{extra}"
    if tool == "git_commit":
        paths = a.get("paths") or []
        scope = f"（只提交 {_clip('、'.join(paths), 60)}）" if paths else "（提交全部改动）"
        return f"提交改动 {_quote(a.get('message', ''), 60)}{scope}"
    if tool == "git_branch":
        return f"新建并切换到分支 {a.get('name', '?')}"
    if tool == "linear_update_issue":
        parts = []
        if a.get("state"):
            parts.append(f"把状态改为「{a['state']}」")
        if a.get("comment"):
            parts.append(f"添加评论 {_quote(a['comment'], 60)}")
        return f"在 Linear 上对 {a.get('identifier', '?')} " + ("，".join(parts) or "做更新")
    if tool == "linear_create_issue":
        parent = f"，作为 {a['parent']} 的子任务" if a.get("parent") else ""
        return f"在 Linear 上新建 issue {_quote(a.get('title', ''), 50)}{parent}"
    shown = "，".join(f"{k}={_clip(v, 30)}" for k, v in list((a or {}).items())[:3])
    return f"调用 {tool}" + (f"（{shown}）" if shown else "")


def explain_verdict(permission: str, in_scope: float | None, collateral: float | None, *, fallback: bool,
                    scope_threshold: float, collateral_threshold: float) -> str:
    """JEV 的判断，用人话说：为什么这一步需要（或不需要）你点头。"""
    if permission == "external":
        return "这会改动 Linear 上别人也看得到的内容，按规则每一次都要你确认。"
    if fallback or (in_scope is None and collateral is None):
        return "JEV 暂时不可用，没法自动判断这一步是否合理，所以交给你确认。"
    if collateral is not None and collateral >= collateral_threshold:
        return f"JEV 担心这一步可能改到与你的请求无关的内容（越界风险 {collateral:.0%}），请你看一眼。"
    if in_scope is not None and in_scope < scope_threshold:
        return (f"JEV 觉得这一步和你的请求关联度一般（{in_scope:.0%}，低于放行线 {scope_threshold:.0%}），"
                "但没发现会误伤无关内容，请你确认是否需要。")
    return "JEV 认为这一步合理。"
