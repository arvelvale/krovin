import {
  ArrowUpRight, Bot, Check, ChevronRight, Cloud, Code2, Cpu, GitPullRequest, ListChecks, LoaderCircle, Mic, ShieldAlert, Sparkles, Sun, TriangleAlert, X,
} from "lucide";
import { ms, num, PERMISSION_LABEL, TIER_LABEL } from "../format";
import { answerConfirm, createSession, selectTurn, sortedTurns, state, type Current } from "../store";
import type { ConfirmItem, Turn } from "../types";
import { h, icon } from "./dom";
import { markdown } from "./markdown";

const SUGGESTIONS = [
  { title: "准备站会", hint: "把昨天的进展，整理成今天的起点", icon: Sun, color: "amber", text: "待会开站会，帮我理一下昨天干了啥今天干啥" },
  { title: "修复一个 Bug", hint: "读懂代码，修复问题，补齐测试", icon: Code2, color: "blue", text: "把 DAY-298 金额累加精度的 bug 修掉，记得补测试" },
  { title: "整理会议待办", hint: "从讨论到清晰、可执行的任务", icon: ListChecks, color: "teal", text: "把昨天周会纪要里的待办整理成 Linear 任务提案，先给我看看" },
  { title: "审查代码", hint: "再多一双眼睛，关注改动与约定", icon: GitPullRequest, color: "violet", text: "帮我 review 一下当前分支，看有没有违反 AGENTS.md" },
];

/** 一轮当前在干什么（给进行中的轮次一句人话） */
function progressText(t: Turn): string {
  const last = t.events[t.events.length - 1];
  if (!last) return "收到，正在准备";
  const steps = t.events.filter((e) => e.type === "llm.call").length;
  switch (last.type) {
    case "turn.start": return "正在挑选合适的技能";
    case "skill.select": return "正在决定交给主力还是难题模型";
    case "route.model": return "正在翻相关的长期记忆";
    case "memory.recall": return "模型开始思考了";
    case "llm.start": return `第 ${last.data.step} 步 · ${last.data.endpoint} 正在处理任务`;
    case "llm.call": {
      const calls: string[] = last.data.tool_calls ?? [];
      return calls.length ? `第 ${steps} 步 · 正在执行 ${calls.join("、")}` : `第 ${steps} 步 · 正在整理回复`;
    }
    case "tool.gate": return last.data.decision === "confirm" ? "等你确认一个写操作" : `正在执行 ${last.data.tool}${last.data.auto ? "（全自动）" : ""}`;
    case "tool.call": return `已执行 ${last.data.tool}，正在查看结果`;
    case "context.compress": return "上下文有点长，正在压缩";
    case "route.escalate": return `换到 ${last.data.to} 模型继续`;
    case "memory.write": return "正在记下值得记住的事";
    case "subagent.start": return "子助手正在并行调查";
    case "guard.drift": return "最近几步有点跑偏，已提醒模型回到计划";
    case "subagent.end": return "子助手交回了结论";
    default: return "进行中";
  }
}

/** 只展示已发生的决策和模型实际返回的内容；等待中的模型内部过程不可观测。 */
function activityItem(t: Turn, e: Turn["events"][number], running: boolean): HTMLElement | null {
  const d = e.data;
  let title = "";
  let detail = "";
  switch (e.type) {
    case "skill.select":
      title = `技能：${(d.selected ?? []).join("、") || "本轮不用技能"}`;
      detail = String(d.reason ?? "");
      break;
    case "route.model":
      title = `模型：${d.model ?? d.endpoint ?? d.tier}`;
      detail = String(d.reason ?? "");
      break;
    case "memory.recall":
      title = `记忆：选入原文 ${(d.full ?? []).length} 条、摘要 ${(d.brief ?? []).length} 条`;
      break;
    case "llm.start":
      if (t.events.some((ev) => ev.type === "llm.call" && ev.data.step === d.step)) return null;
      title = `第 ${d.step} 步：正在等待 ${d.endpoint} 返回`;
      detail = "模型返回后会显示其提供的思考内容。";
      break;
    case "llm.call": {
      const thought = t.reasoning.find((item) => item.step === d.step);
      const calls = (d.tool_calls ?? []) as string[];
      return h("li", { class: "activity-item" },
        h("strong", null, `第 ${d.step} 步：模型已返回`, calls.length ? `，准备调用 ${calls.join("、")}` : ""),
        thought
          ? h("details", { class: "model-reasoning", attrs: { open: running && e === [...t.events].reverse().find((ev) => ev.type === "llm.call") } },
            h("summary", null, `查看模型返回的思考 · ${thought.model}${thought.truncated ? "（内容过长，已截取）" : ""}`),
            h("pre", null, thought.text))
          : h("span", { class: "activity-detail" }, "这个模型没有返回思考正文。"));
    }
    case "tool.gate":
      title = `工具判断：${d.tool} · ${d.decision === "confirm" ? "等待确认" : d.decision === "deny" ? "未放行" : "已放行"}`;
      detail = String(d.reason ?? "");
      break;
    case "tool.call":
      title = `${d.ok ? "已执行" : "执行失败"}：${d.tool}`;
      break;
    case "context.compress":
      title = "正在整理较长的对话上下文";
      break;
    case "route.escalate":
      title = `模型切换：${d.from} → ${d.to}`;
      detail = String(d.reason ?? "");
      break;
    case "subagent.start":
      title = `子助手开始：${d.description}`;
      break;
    case "subagent.end":
      title = `子助手${d.ok ? "完成" : "未完成"}：${d.description}`;
      break;
    case "error":
      title = d.handled ? "遇到问题，已自动处理" : "遇到问题";
      detail = String(d.message ?? "");
      break;
    default:
      return null;
  }
  return h("li", { class: "activity-item" }, h("strong", null, title), detail && h("span", { class: "activity-detail" }, detail));
}

function activityCard(t: Turn, running: boolean): HTMLElement | null {
  const items = t.events.map((e) => activityItem(t, e, running)).filter(Boolean) as HTMLElement[];
  if (!items.length) return null;
  return h("details", { class: "activity-card", attrs: { open: running } },
    h("summary", null, running ? "正在做什么 · 实时进展" : "执行进展与模型思考", h("span", null, `${items.length} 条记录`)),
    h("ol", { class: "activity-list" }, items));
}

function decisionStrip(t: Turn): HTMLElement | null {
  const sel = t.events.find((e) => e.type === "skill.select");
  const routes = t.events.filter((e) => e.type === "route.model" || e.type === "route.escalate");
  if (!sel && !routes.length) return null;
  const route = routes[routes.length - 1];
  const tier = route?.type === "route.escalate" ? (route.data.to === "cloud" ? "cloud" : "local") : route?.data.tier;
  const steps = t.events.filter((e) => e.type === "llm.call").length;
  const skills: string[] = sel?.data.selected ?? [];
  const gates = t.events.filter((e) => e.type === "tool.gate" && e.data.permission !== "read");
  const active = state.selectedTurn === t.n;
  return h("button", { class: ["strip", active && "active"], title: "在右侧查看这一轮的决策轨迹", onclick: () => selectTurn(t.n) },
    h("span", { class: "chip skill" }, icon(Sparkles, 13), skills.length ? skills.join(" + ") : "不用技能"),
    tier && h("span", { class: `chip tier ${tier}` }, icon(tier === "cloud" ? Cloud : Cpu, 13), TIER_LABEL[tier] ?? tier),
    steps > 0 && h("span", { class: "chip" }, `${steps} 步`),
    gates.length > 0 && h("span", { class: "chip" }, `${gates.length} 次写操作门控`),
    t.done?.latency !== undefined && h("span", { class: "chip" }, ms(t.done.latency * 1000)),
    sel?.fallback && h("span", { class: "chip warn" }, icon(TriangleAlert, 12), "降级"),
    h("span", { class: "strip-more" }, "轨迹", icon(ChevronRight, 13)));
}

function argPreview(c: ConfirmItem): HTMLElement {
  const a = c.arguments as Record<string, any>;
  const lines = (text: unknown, mark: string, cls: string, max = 14) => {
    const all = String(text ?? "").split("\n");
    const shown = all.slice(0, max).map((l) => h("div", { class: `diff-line ${cls}` }, `${mark} ${l}`));
    if (all.length > max) shown.push(h("div", { class: "diff-line more" }, `…还有 ${all.length - max} 行`));
    return shown;
  };
  if (c.tool === "edit_file")
    return h("div", { class: "args" }, h("div", { class: "args-path" }, a.path), h("div", { class: "diff" },
      lines(a.old, "−", "del"), lines(a.new, "+", "add")));
  if (c.tool === "write_file")
    return h("div", { class: "args" }, h("div", { class: "args-path" }, `${a.path}（整份写入）`),
      h("div", { class: "diff" }, lines(a.content, "+", "add")));
  if (c.tool === "run_command") return h("div", { class: "args" }, h("code", { class: "cmd" }, a.command));
  if (c.tool === "git_commit") return h("div", { class: "args" }, h("div", { class: "args-kv" }, "提交说明：", a.message));
  if (c.tool === "linear_create_issue")
    return h("div", { class: "args" }, h("div", { class: "args-kv strong" }, a.title),
      a.parent && h("div", { class: "args-kv" }, `父任务 ${a.parent}`),
      a.description && h("div", { class: "diff" }, lines(a.description, " ", "ctx", 10)));
  if (c.tool === "linear_update_issue")
    return h("div", { class: "args" }, h("div", { class: "args-kv strong" }, a.identifier),
      a.state && h("div", { class: "args-kv" }, `状态改为：${a.state}`),
      a.comment && h("div", { class: "diff" }, lines(a.comment, " ", "ctx", 8)));
  return h("div", { class: "args" }, h("pre", { class: "json" }, JSON.stringify(a, null, 2).slice(0, 1500)));
}

function scoreRow(label: string, v: number | null, danger: boolean): HTMLElement {
  const pct = v === null ? 0 : Math.round(v * 100);
  return h("div", { class: "mini-score" },
    h("span", null, label),
    h("span", { class: "mini-track" }, h("span", { class: ["mini-fill", danger && "danger"], style: `width:${pct}%` })),
    h("span", { class: "mono" }, num(v)));
}

function confirmCard(c: ConfirmItem): HTMLElement {
  if (c.resolved) {
    const label = c.resolved.timeout ? "等太久没回应，已按拒绝处理" : c.resolved.approve ? "你同意了" : "你拒绝了";
    return h("div", { class: ["confirm-done", c.resolved.approve ? "yes" : "no"] },
      icon(c.resolved.approve ? Check : X, 14), `${label} · ${c.tool}`);
  }
  const external = c.permission === "external";
  return h("div", { class: ["confirm", external && "external"] },
    h("div", { class: "confirm-head" }, icon(ShieldAlert, 16),
      h("span", null, external ? "这个操作别人也能看到，确认一下" : "要改动文件，确认一下"),
      h("span", { class: "tag" }, PERMISSION_LABEL[c.permission] ?? c.permission)),
    h("div", { class: "confirm-tool" }, h("code", null, c.tool), h("span", { class: "confirm-reason" }, c.reason)),
    (c.in_scope !== null || c.collateral !== null) && h("div", { class: "confirm-scores" },
      scoreRow("合理步骤", c.in_scope, false), scoreRow("越界风险", c.collateral, true)),
    argPreview(c),
    h("div", { class: "confirm-actions" },
      h("button", { class: "btn ghost", onclick: () => void answerConfirm(c.id, false) }, "不行"),
      h("button", { class: "btn primary", onclick: () => void answerConfirm(c.id, true) }, "同意执行")));
}

function turnView(cur: Current, t: Turn, running: boolean): HTMLElement {
  const confirms = [...cur.confirms.values()].filter((c) => c.turn === t.n);
  return h("section", { class: "turn", dataset: { turn: String(t.n) } },
    t.input && h("div", { class: "msg user" }, h("div", { class: "bubble" },
      t.source === "voice" && h("span", { class: "voice-tag", title: "语音输入" }, icon(Mic, 12)), t.input)),
    decisionStrip(t),
    activityCard(t, running),
    confirms.map(confirmCard),
    t.reply
      ? h("div", { class: "msg bot" }, h("div", { class: "avatar" }, icon(Bot, 16)), markdown(t.reply))
      : running && h("div", { class: "progress" }, icon(LoaderCircle, 14, "spin"), progressText(t)));
}

function emptyState(cur: Current | null): HTMLElement {
  const skills = state.status?.skills ?? [];
  return h("div", { class: "empty" },
    h("div", { class: "welcome-kicker" }, icon(Sparkles, 14), "AGENTIC DEVELOPMENT · KROVIN"),
    h("h2", null, "让 ", h("em", null, "AI", h("span", { class: "ai-agents-word" }, " agents")), " 接手任务。", h("br"), h("span", null, "让每一步，清晰可见。")),
    h("p", null, "计划、代码、进展，都在一个对话里。", h("br"), "把下一件事交给 KROVIN，专注你的想法。"),
    (!cur || cur.live) && h("div", { class: "suggest" },
      SUGGESTIONS.map((item) => h("button", {
        class: "suggest-item", title: `${item.title}：填入输入框，确认后发送`,
        onclick: async (event: MouseEvent) => {
          const button = event.currentTarget as HTMLButtonElement;
          button.disabled = true;
          if (!state.current?.live) await createSession();
          if (state.current?.live) window.dispatchEvent(new CustomEvent("spark:compose", { detail: item.text }));
          button.disabled = false;
        },
      }, h("span", { class: `suggest-icon ${item.color}` }, icon(item.icon, 19)),
      h("span", { class: "suggest-copy" }, h("strong", null, item.title), h("span", null, item.hint)),
      icon(ArrowUpRight, 15, "suggest-arrow")))),
    skills.length > 0 && h("details", { class: "skill-library" },
      h("summary", null, icon(Sparkles, 13), `${skills.length} 项技能，随时待命`, icon(ChevronRight, 13)),
      h("div", { class: "skill-cloud" }, skills.map((s) => h("span", { class: "skill-pill", title: s.description }, s.name)))));
}

export function renderMessages(): HTMLElement {
  const cur = state.current;
  const turns = sortedTurns(cur);
  if (!cur || (!turns.length && !cur.pendingInput)) return emptyState(cur);
  const lastN = turns.length ? turns[turns.length - 1].n : 0;
  return h("div", { class: "messages-inner" },
    turns.map((t) => turnView(cur, t, cur.busy && t.n === lastN && !t.done)),
    cur.pendingInput && h("section", { class: "turn" },
      h("div", { class: "msg user" }, h("div", { class: "bubble" }, cur.pendingInput.text)),
      h("div", { class: "progress" }, icon(LoaderCircle, 14, "spin"), "收到，正在准备")),
    cur.stream === "reconnecting" && h("div", { class: "banner" }, "和面板后端的连接断了，正在重连…"));
}
