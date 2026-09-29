import { Check, ChevronDown, Folder, FolderOpen, Plus, Search, ShieldCheck, Zap } from "lucide";
import { api } from "../api";
import { setYolo, state, toast, update, useWorkspace } from "../store";
import type { WsItem } from "../types";
import { h, icon } from "./dom";
import { setup } from "./setup";

/**
 * 输入框下面那一排：工作空间选择器 + 权限选择器（和 Codex 一样放在对话框下面）。
 * 菜单往上弹；打开时才拉一次工作区列表。搜索框在菜单里，所以菜单内容只在打开 / 自己操作时重建，
 * 不跟着全局重绘走（否则输入到一半会丢焦点）；外面的 sync() 只更新按钮上的文字。
 */
export function createComposerPickers(): { el: HTMLElement; sync: () => void } {
  let open: "ws" | "perm" | null = null;
  let items: WsItem[] = [];
  let activeId = "demo";
  let query = "";

  const wsLabel = h("span", { class: "pk-label" });
  const permLabel = h("span", { class: "pk-label" });
  const wsBtn = h("button", { class: "pk-btn", attrs: { type: "button", "aria-haspopup": "listbox" } },
    icon(Folder, 15), wsLabel, icon(ChevronDown, 14, "pk-chev"));
  const permBtn = h("button", { class: "pk-btn", attrs: { type: "button", "aria-haspopup": "listbox" } },
    icon(ShieldCheck, 15), permLabel, icon(ChevronDown, 14, "pk-chev"));
  const wsMenu = h("div", { class: "pk-menu", attrs: { role: "listbox" } });
  const permMenu = h("div", { class: "pk-menu pk-menu-perm", attrs: { role: "listbox" } });
  const el = h("div", { class: "composer-pickers" },
    h("div", { class: "pk-wrap" }, wsBtn, wsMenu), h("div", { class: "pk-wrap" }, permBtn, permMenu));

  const yolo = () => (state.current ? state.current.yolo : state.newSession.yolo);
  const wsName = () => (state.current?.workspace ?? state.status?.workspace ?? "选择工作空间");

  function close() {
    open = null;
    wsMenu.classList.remove("open");
    permMenu.classList.remove("open");
    wsBtn.setAttribute("aria-expanded", "false");
    permBtn.setAttribute("aria-expanded", "false");
  }

  // ---------------- 工作空间 ----------------
  function renderItems(list: HTMLElement) {
    const q = query.trim().toLowerCase();
    const shown = items.filter((i) => i.ready && (!q || i.name.toLowerCase().includes(q)));
    list.replaceChildren(...(shown.length === 0
      ? [h("div", { class: "pk-empty" }, "没有匹配的工作空间")]
      : shown.map((it) => h("button", { class: ["pk-item", it.name === wsName() && "on"], attrs: { type: "button", role: "option" }, onclick: () => choose(it) },
        icon(it.git ? Folder : Folder, 16), h("span", { class: "pk-item-name" }, it.name),
        it.name === wsName() && icon(Check, 14, "pk-check")))));
  }

  function buildWsMenu() {
    const list = h("div", { class: "pk-list" });
    const input = h("input", { class: "pk-search", attrs: { placeholder: "搜索工作空间", spellcheck: "false", "aria-label": "搜索工作空间" } }) as HTMLInputElement;
    input.value = query;
    input.addEventListener("input", () => { query = input.value; renderItems(list); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing) (list.querySelector(".pk-item") as HTMLElement | null)?.click();
    });
    renderItems(list);
    wsMenu.replaceChildren(
      h("div", { class: "pk-search-wrap" }, icon(Search, 15), input),
      list,
      h("div", { class: "pk-sep" }),
      h("button", { class: "pk-item", attrs: { type: "button" }, onclick: () => { close(); setup.request("workspace", false, { addMode: "empty" }); } },
        icon(Plus, 16), h("span", { class: "pk-item-name" }, "新建工作空间")),
      h("button", { class: "pk-item", attrs: { type: "button" }, onclick: () => { close(); setup.pickFolder(); } },
        icon(FolderOpen, 16), h("span", { class: "pk-item-name" }, "打开本地文件夹")),
      h("div", { class: "pk-note" }, "本地文件夹会上传到节点上的一份副本里改；改完可以在「工作区与文件」里写回或下载。"));
    setTimeout(() => input.focus(), 0);
  }

  async function toggleWs() {
    if (open === "ws") return close();
    close();
    open = "ws";
    query = "";
    wsMenu.classList.add("open");
    wsBtn.setAttribute("aria-expanded", "true");
    try {
      const l = await api.workspaces();
      items = l.workspaces;
      activeId = l.active_workspace;
    } catch { /* 拉不到就只显示已有的 */ }
    if (open === "ws") buildWsMenu();
  }

  async function choose(it: WsItem) {
    close();
    if (it.id === activeId && !state.current) return;
    if (state.current && it.name === wsName()) return;
    if (state.current && !window.confirm(`在新对话里使用「${it.name}」？当前对话保持不变。`)) return;
    await useWorkspace(it.id, it.name);
  }

  // ---------------- 权限 ----------------
  function buildPermMenu() {
    const opt = (on: boolean, title: string, text: string, danger = false) =>
      h("button", { class: ["pk-item", "pk-perm", yolo() === on && "on", danger && "danger"], attrs: { type: "button", role: "option" },
        onclick: () => { close(); void setPerm(on); } },
      icon(on ? Zap : ShieldCheck, 16), h("span", { class: "pk-item-name" }, h("b", null, title), h("span", { class: "pk-desc" }, text)),
      yolo() === on && icon(Check, 14, "pk-check"));
    permMenu.replaceChildren(
      opt(false, "默认权限", "写文件、提交、改 Linear 之前，按 JEV 的判断需要时会问你。"),
      opt(true, "全自动", "不再打扰你：原本要问你的，改由 JEV 自动决定（可能误伤无关内容的会被拦截）。", true));
  }

  async function setPerm(on: boolean) {
    if (state.current?.live) await setYolo(on);
    else update((s) => { s.newSession.yolo = on; });
    if (on) toast("全自动已开启：由 JEV 自动决定，不再打扰你");
  }

  function togglePerm() {
    if (open === "perm") return close();
    close();
    open = "perm";
    buildPermMenu();
    permMenu.classList.add("open");
    permBtn.setAttribute("aria-expanded", "true");
  }

  wsBtn.addEventListener("click", (e) => { e.stopPropagation(); void toggleWs(); });
  permBtn.addEventListener("click", (e) => { e.stopPropagation(); togglePerm(); });
  document.addEventListener("click", (e) => { if (open && !el.contains(e.target as Node)) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && open) { e.stopPropagation(); close(); } }, true);

  function sync() {
    wsLabel.textContent = wsName();
    wsBtn.title = state.current ? `这个对话在「${wsName()}」里操作；选别的会新开一个对话` : `新对话会在「${wsName()}」里操作`;
    permLabel.textContent = yolo() ? "全自动" : "默认权限";
    permBtn.classList.toggle("danger", yolo());
    permBtn.disabled = !!state.current && !state.current.live;
    wsBtn.disabled = false;
  }

  sync();
  return { el, sync };
}
