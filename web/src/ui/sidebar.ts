import { Brain, CircleDot, FolderGit2, LogOut, Plug, Plus, Sparkles, RotateCcw, SlidersHorizontal, X } from "lucide";
import { when } from "../format";
import { createSession, logout, openSession, resetDemo, setMemoryTab, state, update } from "../store";
import { h, icon } from "./dom";
import { setup } from "./setup";

const SERVICE_ROWS: { key: "local" | "backup" | "cloud" | "jev" | "linear"; label: string }[] = [
  { key: "local", label: "主力" },
  { key: "backup", label: "备用" },
  { key: "cloud", label: "难题" },
  { key: "jev", label: "JEV 决策" },
  { key: "linear", label: "Linear" },
];

let newSessionSwitchMotion: "on" | "off" | null = null;

function newSessionPanel(): HTMLElement {
  const ns = state.newSession;
  const switchMotion = newSessionSwitchMotion;
  newSessionSwitchMotion = null;
  return h("div", { class: "popover" },
    h("div", { class: "popover-row" },
      h("div", { class: "popover-label" }, "JEV 决策层"),
      h("button", {
        class: ["switch", ns.useJev && "on", switchMotion && `switch-motion-${switchMotion}`],
        attrs: { role: "switch", "aria-checked": String(ns.useJev), "aria-label": "新对话启用 JEV 决策层" },
        onclick: () => {
          newSessionSwitchMotion = state.newSession.useJev ? "off" : "on";
          update((s) => { s.newSession.useJev = !s.newSession.useJev; });
        },
      }, h("span", { class: "knob" }))),
    h("div", { class: "popover-row" },
      h("div", { class: "popover-label" }, "全自动", h("span", { class: "muted small" }, "　写操作不再等你确认")),
      h("button", {
        class: ["switch", ns.yolo && "on"],
        attrs: { role: "switch", "aria-checked": String(ns.yolo), "aria-label": "新对话启用全自动模式" },
        onclick: () => update((s) => { s.newSession.yolo = !s.newSession.yolo; }),
      }, h("span", { class: "knob" }))),
    h("div", { class: "popover-row col" },
      h("div", { class: "popover-label" }, "模型档位"),
      h("div", { class: "rubber-slot rubber-slot--popover", attrs: { "data-rubber-segment": "new-session-tier" } })),
    h("div", { class: "popover-actions" },
      h("button", { class: "btn ghost", onclick: () => update((s) => (s.newSessionOpen = false)) }, "取消"),
      h("button", { class: "btn primary", onclick: () => void createSession() }, "开始对话")));
}

export function renderSidebar(): HTMLElement {
  if (!state.newSessionOpen) newSessionSwitchMotion = null;
  const st = state.status;
  const sessions = state.sessions;
  return h("div", { class: "sidebar-inner" },
    h("div", { class: "brand" },
      h("div", { class: "brand-mark" }, icon(Sparkles, 20)),
      h("div", null, h("div", { class: "brand-name" }, "KROVIN"), h("div", { class: "brand-sub" }, "你的开发流助手")),
      h("button", { class: "icon-btn only-mobile", title: "收起", onclick: () => update((s) => (s.sidebarOpen = false)) },
        icon(X, 16))),
    h("div", { class: "new-wrap" },
      h("button", { class: "btn primary block", attrs: { "aria-expanded": String(state.newSessionOpen) }, onclick: () => update((s) => (s.newSessionOpen = !s.newSessionOpen)) },
        icon(Plus, 16), "新对话"),
      state.newSessionOpen && newSessionPanel()),
    h("div", { class: "side-label" }, "最近对话", h("span", null, String(sessions.length))),
    h("div", { class: "session-list", attrs: { "data-selection-group": "sessions" } },
      sessions.length === 0
        ? h("div", { class: "side-empty" }, "还没有会话，新建一个试试")
        : sessions.map((x) =>
            h("button", {
              class: ["session-item", state.current?.id === x.id && "active"], attrs: { "data-selection-key": x.id },
              onclick: () => void openSession(x.id),
            },
            h("div", { class: "session-title" }, x.live && h("span", { class: "dot run", title: "在线" }), x.title),
            h("div", { class: "session-meta" }, `${x.turns} 轮 · ${when(x.updated)}`)))),
    h("div", { class: "side-foot" },
      h("button", { class: "side-link", onclick: () => { update((s) => (s.drawer = "memory")); void setMemoryTab(state.memoryTab); } },
        icon(Brain, 16), "长期记忆",
        h("span", { class: "count" }, String([...state.memories.values()].filter((m) => m.status === "pending").length || ""))),
      h("button", { class: "side-link", onclick: () => update((s) => (s.drawer = "models")) },
        icon(SlidersHorizontal, 16), "模型设置"),
      h("button", { class: "side-link", onclick: () => setup.request("workspace") },
        icon(FolderGit2, 16), "工作区与文件"),
      h("button", { class: "side-link", onclick: () => setup.request("integrations") },
        icon(Plug, 16), "集成设置"),
      h("div", { class: "services" },
        h("div", { class: "service-heading" }, "连接状态", h("span", null, "DGX SPARK")),
        SERVICE_ROWS.map(({ key, label }) => {
          const svc = st?.services[key];
          const cls = !svc ? "off" : svc.ok ? (key === "backup" ? "idle" : "run") : "warn";
          const priv = svc?.private === undefined ? "" : svc.private ? " · 私有" : " · 外部";
          const status = !svc ? "未连接" : svc.ok ? (key === "backup" ? "备用就绪" : "在线") : "异常";
          return h("div", { class: "service", title: `${status} · ${svc?.model ?? ""}${priv}`, attrs: { "aria-label": `${label}：${status}，${svc?.model ?? ""}` } },
            h("span", { class: `dot ${cls}` }), h("span", { class: "service-label" }, label),
            h("span", { class: "service-model" }, svc?.model ?? "…"));
        })),
      st && h("div", { class: "workspace", title: "agent 操作的仓库（点名字切换 / 查看文件）" },
        icon(st.workspace_ready ? FolderGit2 : CircleDot, 14),
        h("button", { class: "link ws-name-link", onclick: () => setup.request("workspace") }, st.workspace),
        !st.workspace_ready && h("span", { class: "warn-text" }, "未生成"),
        st.workspace_resettable && h("button", {
          class: "link reset", title: "把演示仓库恢复到初始状态（带着 DAY-298 的 bug）", onclick: () => void resetDemo(),
        }, icon(RotateCcw, 12), "重置")),
      h("button", { class: "side-link subtle", onclick: () => void logout() }, icon(LogOut, 14), "退出登录")));
}
