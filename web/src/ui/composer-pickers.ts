import { Check, ChevronDown, Folder, FolderOpen, ImagePlus, Plus, Play, Search, ShieldCheck, Trash2, Zap } from "lucide";
import { ApiError, api } from "../api";
import { loadStatus, setYolo, state, toast, update, useWorkspace } from "../store";
import type { WsItem } from "../types";
import { h, icon } from "./dom";
import { setup } from "./setup";
import { artifactView } from "./artifact";

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
  const imageBtn = h("button", { class: "pk-btn", attrs: { type: "button", title: "添加图片", "aria-label": "添加图片" } }, icon(ImagePlus, 16));
  const permLabel = h("span", { class: "pk-label" });
  const wsBtn = h("button", { class: "pk-btn", attrs: { type: "button", "aria-haspopup": "listbox" } },
    icon(Folder, 15), wsLabel, icon(ChevronDown, 14, "pk-chev"));
  const permBtn = h("button", { class: "pk-btn", attrs: { type: "button", "aria-haspopup": "listbox" } },
    icon(ShieldCheck, 15), permLabel, icon(ChevronDown, 14, "pk-chev"));
  const wsMenu = h("div", { class: "pk-menu", attrs: { role: "listbox" } });
  const permMenu = h("div", { class: "pk-menu pk-menu-perm", attrs: { role: "listbox" } });
  const el = h("div", { class: "composer-pickers" },
    imageBtn,
    h("button", {class:"pk-btn", attrs:{type:"button",title:"在线预览当前项目","aria-label":"在线预览当前项目"}, onclick:() => {
      if (state.current?.workspaceId) artifactView.request(state.current.workspaceId,"index.html","preview");
      else toast("先打开一个会话，再预览对应项目");
    }}, icon(Play,15), h("span",{class:"pk-label"},"在线预览")),
    h("div", { class: "pk-wrap" }, wsBtn, wsMenu), h("div", { class: "pk-wrap" }, permBtn, permMenu));
  imageBtn.addEventListener("click", () => window.dispatchEvent(new Event("spark:add-image")));

  const yolo = () => (state.current ? state.current.yolo : state.newSession.yolo);
  const bypass = () => (state.current ? state.current.bypass : state.newSession.bypass);
  const mode = () => bypass() ? "bypass" : yolo() ? "auto" : "default";
  const wsName = () => (state.current?.workspace ?? state.status?.workspace ?? "选择工作空间");

  function close() {
    open = null;
    wsMenu.classList.remove("open");
    permMenu.classList.remove("open");
    wsBtn.setAttribute("aria-expanded", "false");
    permBtn.setAttribute("aria-expanded", "false");
  }

  // ---------------- 工作空间 ----------------
  let wsListEl: HTMLElement | null = null;  // 删除后要就地重画列表

  function renderItems(list: HTMLElement) {
    const q = query.trim().toLowerCase();
    const shown = items.filter((i) => i.ready && (!q || i.name.toLowerCase().includes(q)));
    list.replaceChildren(...(shown.length === 0
      ? [h("div", { class: "pk-empty" }, "没有匹配的工作空间")]
      : shown.map((it) => h("div", { class: ["pk-item", it.name === wsName() && "on"] },
        h("button", { class: "pk-item-main", attrs: { type: "button", role: "option" }, onclick: () => choose(it) },
          icon(it.git ? Folder : Folder, 16), h("span", { class: "pk-item-name" }, it.name),
          it.name === wsName() && icon(Check, 14, "pk-check")),
        !it.builtin && h("button", {
          class: "pk-del", attrs: { type: "button", title: `删除「${it.name}」`, "aria-label": `删除「${it.name}」` },
          onclick: (e: MouseEvent) => { e.stopPropagation(); void removeWorkspace(it); },
        }, icon(Trash2, 13))))));
  }

  /** 删工作空间 = 删节点上那份副本（本地原文件夹不动）。当前对话正在用的不给删 */
  async function removeWorkspace(it: WsItem) {
    if (it.builtin) return;
    if (state.current?.live && state.current.workspaceId === it.id) {
      toast("这个对话正在这个工作空间里干活，先换个工作空间或删掉对话", "error");
      return;
    }
    if (!window.confirm(`删除「${it.name}」？节点上的这份副本会一起删掉（你本地的原文件夹不受影响）。`)) return;
    try {
      await api.deleteWorkspace(it.id);
      const l = await api.workspaces();
      items = l.workspaces;
      activeId = l.active_workspace;
      await loadStatus();  // 删的是当前工作区时，后端已切回 demo，标签要跟着变
      if (wsListEl) renderItems(wsListEl);
      sync();
      toast(`已删除「${it.name}」`);
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "删除失败，再试一次", "error");
    }
  }

  function buildWsMenu() {
    const list = h("div", { class: "pk-list" });
    wsListEl = list;
    const input = h("input", { class: "pk-search", attrs: { placeholder: "搜索工作空间", spellcheck: "false", "aria-label": "搜索工作空间" } }) as HTMLInputElement;
    input.value = query;
    input.addEventListener("input", () => { query = input.value; renderItems(list); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing) (list.querySelector(".pk-item-main") as HTMLElement | null)?.click();
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
    await useWorkspace(it.id, it.name);
  }

  // ---------------- 权限 ----------------
  function buildPermMenu() {
    const opt = (value: string, title: string, text: string) =>
      h("button", { class: ["pk-item", "pk-perm", mode() === value && "on", value !== "default" && "danger"], attrs: { type: "button", role: "option" },
        onclick: () => { close(); if (value === "bypass" && !bypass()) confirmBypass(); else void setPerm(value); } },
      icon(value === "default" ? ShieldCheck : Zap, 16), h("span", { class: "pk-item-name" }, h("b", null, title), h("span", { class: "pk-desc" }, text)),
      mode() === value && icon(Check, 14, "pk-check"));
    permMenu.replaceChildren(
      opt("default", "默认权限", "按 JEV 判断，需要时向你确认。"),
      opt("auto", "全自动", "由 JEV 自动决定，可能拦截写操作。"),
      opt("bypass", "Bypass", "跳过执行门控与逐次确认，自动执行所有可用工具。"));
  }

  function confirmBypass() {
    const cancel = h("button", { class: "btn delete-session-cancel", onclick: () => dialog.close() }, "取消");
    const dialog = h("dialog", { class: "delete-session-dialog", attrs: { "aria-labelledby": "bypass-title" } },
      h("div", { class: "delete-session-card" },
        h("div", { class: "delete-session-icon" }, icon(Zap, 20)),
        h("h2", { attrs: { id: "bypass-title" } }, "开启 Bypass 模式？"),
        h("p", { class: "delete-session-description" }, "模型调用可用工具时，将跳过技能白名单、JEV 执行判断和逐次确认，包括命令、文件编辑、删除及 Linear 等外部写入。已等待的确认也会自动同意。"),
        h("p", { class: "delete-session-description" }, "操作可能覆盖文件或修改外部数据。沙箱隔离、路径边界及集成范围仍有效。此设置会保存在当前会话中，可随时切回默认权限。"),
        h("div", { class: "delete-session-actions" }, cancel,
          h("button", { class: "btn delete-session-submit", onclick: () => { dialog.close(); void setPerm("bypass"); } }, "确认开启 Bypass"))));
    dialog.addEventListener("close", () => dialog.remove());
    document.body.append(dialog);
    (dialog as HTMLDialogElement).showModal();
    cancel.focus();
  }

  async function setPerm(value: string) {
    const on = value === "auto", bypassOn = value === "bypass";
    if (state.current?.live) await setYolo(on, bypassOn);
    else update((s) => { s.newSession.yolo = on; s.newSession.bypass = bypassOn; });
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
    permLabel.textContent = bypass() ? "Bypass" : yolo() ? "全自动" : "默认权限";
    permBtn.classList.toggle("danger", yolo() || bypass());
    permBtn.disabled = !!state.current && !state.current.live;
    wsBtn.disabled = false;
  }

  sync();
  return { el, sync };
}
