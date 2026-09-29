import { Brain, CircleDot, FolderGit2, LogOut, Pencil, Plug, Plus, RotateCcw, SlidersHorizontal, Trash2, X } from "lucide";
import { when } from "../format";
import { createSession, deleteSession, logout, openSession, renameSession, resetDemo, setMemoryTab, state, update } from "../store";
import { h, icon } from "./dom";
import { logoMark } from "./logo";
import type { SessionSummary } from "../types";
import { setup } from "./setup";
import { api } from "../api";

const SERVICE_ROWS: { key: "local" | "backup" | "cloud" | "jev" | "linear"; label: string }[] = [
  { key: "local", label: "主力" },
  { key: "backup", label: "备用" },
  { key: "cloud", label: "难题" },
  { key: "jev", label: "JEV 决策" },
  { key: "linear", label: "Linear" },
];

let newSessionSwitchMotion: "on" | "off" | null = null;
let newSessionYoloSwitchMotion: "on" | "off" | null = null;
let deleteDialog: HTMLDialogElement | null = null;

function confirmDeleteSession(x: SessionSummary): void {
  if (deleteDialog) return;
  let deleteWorkspace = false;
  const description = h("p", { class: "delete-session-description", attrs: { id: "delete-session-description" } }, "正在检查关联文件…");
  const submit = h("button", { class: "btn delete-session-submit", attrs: { disabled: true }, onclick: () => {
    dialog.close();
    void deleteSession(x.id, deleteWorkspace);
  } }, "删除并清理");
  const cancel = h("button", { class: "btn delete-session-cancel", onclick: () => dialog.close() }, "取消");
  const dialog = h("dialog", {
    class: "delete-session-dialog",
    attrs: { "aria-labelledby": "delete-session-title", "aria-describedby": "delete-session-description" },
  },
  h("div", { class: "delete-session-card" },
    h("div", { class: "delete-session-icon" }, icon(Trash2, 20)),
    h("h2", { attrs: { id: "delete-session-title" } }, "删除这段对话？"),
    h("p", { class: "delete-session-name" }, x.title),
    description,
    h("div", { class: "delete-session-actions" },
      cancel,
      submit)));
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  dialog.addEventListener("close", () => { dialog.remove(); deleteDialog = null; });
  document.body.append(dialog);
  deleteDialog = dialog;
  dialog.showModal();
  cancel.focus();
  void api.sessionCleanup(x.id).then((plan) => {
    description.textContent = plan.description;
    deleteWorkspace = plan.delete_workspace;
    submit.disabled = false;
  }).catch((err) => { description.textContent = `无法检查清理范围：${err instanceof Error ? err.message : "请稍后重试"}`; });
}

// 正在改名的会话。草稿放在模块变量里：状态轮询触发的整块重绘不会把已经敲的字冲掉
let renaming: { id: string; draft: string } | null = null;

function sessionRow(x: SessionSummary): HTMLElement {
  const active = state.current?.id === x.id;
  if (renaming?.id === x.id) {
    const input = h("input", { class: "session-rename", attrs: { maxlength: "60", "aria-label": "会话名称", spellcheck: "false" } }) as HTMLInputElement;
    input.value = renaming.draft;
    const finish = (save: boolean) => {
      const draft = renaming?.draft.trim() ?? "";
      renaming = null;
      if (save && draft !== x.title) void renameSession(x.id, draft);
      else update(() => {});
    };
    input.addEventListener("input", () => { if (renaming) renaming.draft = input.value; });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing) finish(true);
      else if (e.key === "Escape") { e.stopPropagation(); finish(false); }
    });
    input.addEventListener("blur", () => { if (renaming?.id === x.id) finish(true); });
    input.addEventListener("click", (e) => e.stopPropagation());
    setTimeout(() => { input.focus(); input.select(); }, 0);
    return h("div", { class: ["session-item", "editing", active && "active"], attrs: { "data-selection-key": x.id } },
      input, h("div", { class: "session-meta" }, "回车保存 · Esc 取消 · 留空恢复默认名字"));
  }
  return h("div", {
    class: ["session-item", active && "active"], attrs: { "data-selection-key": x.id, role: "button", tabindex: "0" },
    onclick: () => void openSession(x.id),
    onkeydown: (e: KeyboardEvent) => { if (e.key === "Enter" && e.target === e.currentTarget) void openSession(x.id); },
  },
  h("div", { class: "session-title" }, x.live && h("span", { class: "dot run", title: "在线" }), x.title),
  h("div", { class: "session-meta" }, `${x.turns} 轮 · ${when(x.updated)}`),
  h("div", { class: "session-actions" },
    h("button", {
      class: "icon-btn tiny", title: "重命名", onclick: (e: MouseEvent) => {
        e.stopPropagation();
        renaming = { id: x.id, draft: x.custom ? x.title : x.title === "新对话" ? "" : x.title };
        update(() => {});
      },
    }, icon(Pencil, 13)),
    h("button", {
      class: "icon-btn tiny danger", title: "删除", onclick: (e: MouseEvent) => {
        e.stopPropagation();
        confirmDeleteSession(x);
      },
    }, icon(Trash2, 13))));
}

function newSessionPanel(): HTMLElement {
  const ns = state.newSession;
  const switchMotion = newSessionSwitchMotion;
  newSessionSwitchMotion = null;
  const yoloSwitchMotion = newSessionYoloSwitchMotion;
  newSessionYoloSwitchMotion = null;
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
        class: ["switch", ns.yolo && "on", yoloSwitchMotion && `switch-motion-${yoloSwitchMotion}`],
        attrs: { role: "switch", "aria-checked": String(ns.yolo), "aria-label": "新对话启用全自动模式" },
        onclick: () => {
          newSessionYoloSwitchMotion = state.newSession.yolo ? "off" : "on";
          update((s) => { s.newSession.yolo = !s.newSession.yolo; });
        },
      }, h("span", { class: "knob" }))),
    h("div", { class: "popover-row col" },
      h("div", { class: "popover-label" }, "模型档位"),
      h("div", { class: "rubber-slot rubber-slot--popover", attrs: { "data-rubber-segment": "new-session-tier" } })),
    h("div", { class: "popover-actions" },
      h("button", { class: "btn ghost", onclick: () => update((s) => (s.newSessionOpen = false)) }, "取消"),
      h("button", { class: "btn primary", onclick: () => void createSession() }, "开始对话")));
}

export function renderSidebar(): HTMLElement {
  if (!state.newSessionOpen) {
    newSessionSwitchMotion = null;
    newSessionYoloSwitchMotion = null;
  }
  const st = state.status;
  const sessions = state.sessions;
  return h("div", { class: "sidebar-inner" },
    h("div", { class: "brand" },
      h("div", { class: "brand-mark" }, logoMark(22)),
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
        : sessions.map(sessionRow)),
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
