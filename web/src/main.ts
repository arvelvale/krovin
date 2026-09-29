import { Menu, PanelRight, Sparkles } from "lucide";
import "./styles.css";
import "./glass.css";
import "./motion.css";
import { checkAuth, loadStatus, openSession, state, subscribe, update } from "./store";
import { renderMessages } from "./ui/chat";
import { createComposer } from "./ui/composer";
import { h, icon, mount } from "./ui/dom";
import { renderDrawer } from "./ui/drawer";
import { renderLogin } from "./ui/login";
import { createModelSettings } from "./ui/models";
import { setup } from "./ui/setup";
import { renderSidebar } from "./ui/sidebar";
import { renderTracePanel } from "./ui/trace";
import { installInteractionMotion } from "./ui/interaction-motion";
import { installSelectionMotion } from "./ui/selection-motion";
import { installRubberSegments } from "./ui/rubber-segments";
import { installGlassSurfaces } from "./ui/glass-surfaces";

import { installMicroBackground } from "./ui/micro-background";

const disposeBackground = installMicroBackground();
if (import.meta.hot) import.meta.hot.dispose(disposeBackground);

const root = document.getElementById("app")!;
const disposeMotion = installInteractionMotion(root);
if (import.meta.hot) import.meta.hot.dispose(disposeMotion);
const selectionMotion = installSelectionMotion(root);
if (import.meta.hot) import.meta.hot.dispose(selectionMotion.dispose);
const rubberSegments = installRubberSegments(root);
if (import.meta.hot) import.meta.hot.dispose(rubberSegments.dispose);
const glassSurfaces = installGlassSurfaces(root);
if (import.meta.hot) import.meta.hot.dispose(glassSurfaces.dispose);

// 布局骨架只建一次；各区域在状态变化时整块重绘（输入框除外，见 composer.ts）
const sidebar = h("aside", { class: "sidebar", attrs: { "aria-label": "会话与设置" } });
const header = h("header", { class: "chat-head" });
const messages = h("div", { class: "messages" });
const composer = createComposer();
const modelSettings = createModelSettings();
let lastDrawer: string | null = null;
let lastMemoryTab = state.memoryTab;
const panel = h("aside", { class: "panel", attrs: { "aria-label": "决策与工作记忆" } });
const overlay = h("div", { class: "overlay-root" });
const toastBox = h("div", { class: "toast-root", attrs: { "aria-live": "polite" } });
const shell = h("div", { class: "shell" },
  h("button", { class: "navigation-scrim", attrs: { tabindex: "-1", "aria-label": "收起导航" },
    onclick: () => update((s) => { s.sidebarOpen = false; s.mobileView = "chat"; }) }),
  sidebar,
  h("main", { class: "chat" }, header, messages, composer.el),
  panel,
  overlay,
  toastBox);

function renderHeader(): (HTMLElement | null)[] {
  const cur = state.current;
  const title = cur ? (state.sessions.find((x) => x.id === cur.id)?.title ?? "新对话") : "工作空间";
  return [
    h("button", { class: "icon-btn only-mobile", title: "会话列表", onclick: () => update((s) => (s.sidebarOpen = true)) }, icon(Menu, 18)),
    h("div", { class: "chat-title" },
      h("span", { class: "header-symbol" }, icon(Sparkles, 16)),
      h("div", { class: "title-group" }, h("span", { class: "header-eyebrow" }, "KROVIN / WORKSPACE"), h("span", { class: "title-text" }, title))),
    h("button", {
      class: ["icon-btn only-narrow", state.mobileView === "trace" && "on"], title: "决策轨迹",
      onclick: () => update((s) => (s.mobileView = s.mobileView === "trace" ? "chat" : "trace")),
    }, icon(PanelRight, 18)),
  ];
}

let lastTurnCount = -1;

function render(): void {
  const reading = Boolean(state.authed && state.current &&
    (state.current.turns.size > 0 || state.current.pendingInput));
  document.body.classList.toggle("workspace-reading", reading);
  if (state.authed === null) {
    mount(root, h("div", { class: "boot" }, h("div", { class: "empty-mark" }, icon(Sparkles, 28)), "正在连接你的工作空间…"));
    selectionMotion.sync();
    rubberSegments.sync();
    glassSurfaces.sync();
    return;
  }
  if (!state.authed) {
    if (!root.querySelector(".login")) mount(root, renderLogin());
    selectionMotion.sync();
    rubberSegments.sync();
    glassSurfaces.sync();
    return;
  }
  if (!root.contains(shell)) mount(root, shell);
  shell.classList.toggle("sidebar-open", state.sidebarOpen);
  shell.classList.toggle("show-trace", state.mobileView === "trace");

  // 重绘前记住是否贴着底部，重绘后保持
  const nearBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 80;
  const panelScroll = panel.querySelector(".panel-scroll")?.scrollTop ?? 0;
  const sessionScroll = sidebar.querySelector(".session-list")?.scrollTop ?? 0;
  mount(sidebar, renderSidebar());
  const sessionList = sidebar.querySelector(".session-list");
  if (sessionList) sessionList.scrollTop = sessionScroll;
  mount(header, ...renderHeader());
  mount(messages, renderMessages());
  mount(panel, renderTracePanel());
  const ps = panel.querySelector(".panel-scroll");
  if (ps) ps.scrollTop = panelScroll;
  const turnCount = state.current?.turns.size ?? 0;
  if (turnCount > 0 || state.current?.pendingInput) {
    if (nearBottom || turnCount !== lastTurnCount) messages.scrollTop = messages.scrollHeight;
  } else if (turnCount !== lastTurnCount) messages.scrollTop = 0;
  lastTurnCount = turnCount;
  // 模型设置里有输入框，只在打开时挂一次，之后的全局重绘不碰它
  if (state.drawer === "setup") {
    if (lastDrawer !== "setup") {
      setup.open();
      mount(overlay, setup.el);
    }
  } else if (state.drawer === "models") {
    if (lastDrawer === "setup") setup.close();
    if (lastDrawer !== "models") {
      modelSettings.open();
      mount(overlay, modelSettings.el);
    }
  } else {
    if (lastDrawer === "models") modelSettings.close();
    if (lastDrawer === "setup") setup.close();
    const memoryScroll = state.drawer === "memory" && lastDrawer === "memory" && state.memoryTab === lastMemoryTab
      ? overlay.querySelector<HTMLElement>(".drawer-body")?.scrollTop ?? 0
      : 0;
    mount(overlay, renderDrawer());
    if (state.drawer === "memory") {
      const memoryBody = overlay.querySelector<HTMLElement>(".drawer-body");
      if (memoryBody) memoryBody.scrollTop = memoryScroll;
      lastMemoryTab = state.memoryTab;
    }
  }
  lastDrawer = state.drawer;
  mount(toastBox, state.toast && h("div", { class: `toast ${state.toast.kind}` }, state.toast.text));
  composer.sync();
  selectionMotion.sync();
  rubberSegments.sync();
  glassSurfaces.sync();
}

subscribe(render);
render();

void checkAuth().then(async () => {
  if (!state.authed) return;
  const fromHash = decodeURIComponent(location.hash.slice(1));
  const target = state.sessions.find((x) => x.id === fromHash) ?? state.sessions.find((x) => x.live);
  if (target) await openSession(target.id);
  // 首次进入：引导接上自己的工作区 / Linear / Git / 笔记库（可跳过，用演示环境）
  if (state.status && state.status.onboarded === false) setup.request("workspace", true);
});

// 服务状态每 30 秒刷新一次（本地模型可能被重启）
window.setInterval(() => state.authed && void loadStatus(), 30_000);
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") update((s) => { s.drawer = null; s.newSessionOpen = false; s.sidebarOpen = false; s.mobileView = "chat"; });
});
