"""会话检查点与旧 JSONL 归档恢复；绝不重放工具副作用。"""
import json
import os


def records(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # 进程中断时最后一行可能只写了一半
    return out


def save(agent):
    path = agent.archive.path.parent / "checkpoint.json"
    data = {"messages": agent.conv.messages, "turns": agent.conv.turns,
            "summaries": agent.conv.summaries, "seq": agent.conv._seq,
            "working": agent.working.to_dict()}
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def restore(agent):
    run = agent.archive.path.parent
    # 修复断电/强制退出留下的半行，避免下一次追加与半行粘在一起。
    for path in (run / "trace.jsonl", run / "archive.jsonl"):
        if path.exists():
            raw = path.read_bytes()
            if raw and not raw.endswith(b"\n"):
                tail = raw.rsplit(b"\n", 1)[-1]
                try:
                    json.loads(tail)
                    path.write_bytes(raw + b"\n")
                except (ValueError, UnicodeDecodeError):
                    path.write_bytes(raw[:len(raw) - len(tail)])
    events = records(run / "trace.jsonl")
    agent.trace.turn = max((e.get("turn", 0) for e in events), default=0)
    agent.trace._seq = max((e.get("seq", 0) for e in events), default=0)
    try:
        checkpoint = json.loads((run / "checkpoint.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        checkpoint = {}
    agent.conv.messages = checkpoint.get("messages", [])
    agent.conv.turns = checkpoint.get("turns", [])
    agent.conv.summaries = checkpoint.get("summaries", [])
    agent.conv._seq = checkpoint.get("seq", 0)
    agent.working.update(**checkpoint.get("working", {}))
    for rec in records(run / "archive.jsonl"):
        if rec.get("kind") != "msg":
            continue
        seq = int(rec["id"][1:])
        if seq <= agent.conv._seq:
            continue
        msg = rec["payload"]["message"]
        agent.conv.messages.append(msg)
        agent.conv.turns.append(rec["payload"]["turn"])
        agent.conv._seq = seq
    # 旧版本没有检查点，从有成功结果的 update_plan 恢复工作记忆。
    calls = {}
    for msg in agent.conv.messages:
        for call in msg.get("tool_calls") or []:
            calls[call["id"]] = call
        call = calls.get(msg.get("tool_call_id"))
        if not checkpoint and call and call["function"]["name"] == "update_plan" and msg.get("content", "").startswith("工作记忆已更新"):
            try:
                args = json.loads(call["function"]["arguments"])
                agent.working.update(**{k: v for k, v in args.items() if k in ("goal", "constraints", "todo", "evidence")})
            except (ValueError, TypeError):
                pass
    # 为中断批次里缺结果的调用补齐协议，不执行调用，也不假定它没有发生。
    messages, turns = [], []
    source = list(zip(agent.conv.messages, agent.conv.turns))
    i = 0
    while i < len(source):
        msg, turn = source[i]
        messages.append(msg); turns.append(turn)
        i += 1
        if msg.get("tool_calls"):
            results = {}
            while i < len(source) and source[i][0].get("role") == "tool":
                result, _ = source[i]
                results[result["tool_call_id"]] = result
                i += 1
            for call in msg["tool_calls"]:
                messages.append(results.get(call["id"], {"role": "tool", "tool_call_id": call["id"],
                    "content": "执行期间服务中断，结果未完整保存，实际是否已生效未知。继续前先读取文件或查询外部状态，禁止直接重复写入。"}))
                turns.append(turn)
    agent.conv.messages, agent.conv.turns = messages, turns
    if events and events[-1]["type"] != "turn.end":
        agent.conv.add({"role": "user", "content": "（系统提示）上一轮因服务中断而停止。保留已完成操作，先核对当前文件和外部状态，再接续用户请求。"}, agent.trace.turn)
    save(agent)
