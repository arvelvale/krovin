import {
  BookOpen, Check, ChevronLeft, CircleAlert, Download, File as FileIcon, Folder, FolderGit2, FolderPlus, GitBranch,
  KeyRound, LoaderCircle, Plug, RefreshCw, Trash2, Undo2, Upload, X,
} from "lucide";
import "../setup.css";
import { api, ApiError } from "../api";
import { loadStatus, toast, update } from "../store";
import type {
  IntegrationsView, LinearDiscover, WsChanges, WsChangeStatus, WsEntry, WsFile, WsItem, WsListing,
} from "../types";
import { h, icon, mount } from "./dom";

/**
 * 「工作区与集成」抽屉：选/建/克隆/导入工作区并看里面的文件，接自己的 Linear 和 Git，接笔记库（Obsidian）。
 * 首次进入时以向导形式打开（wizard），全部可以跳过、用演示环境。
 * 里面有输入框，所以和模型设置一样只建一次、自己管理重绘。
 */
export type SetupTab = "workspace" | "vault" | "integrations";
type AddMode = "upload" | "clone" | "empty";
type Kind = "workspace" | "vault";

const SOURCE_LABEL: Record<string, string> = { demo: "演示", empty: "空白", clone: "git 克隆", upload: "本地上传" };
const CHANGE_LABEL: Record<WsChangeStatus, string> = { modified: "修改", added: "新增", deleted: "删除" };
const SKIP_DIRS = new Set([".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".DS_Store"]);
const MAX_FILE = 20 * 1024 * 1024;
const MAX_FILES = 8000;

const errText = (e: unknown) => (e instanceof ApiError ? e.message : "出了点意外，稍后再试一次");
const fmtSize = (n: number) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`);
const relOf = (f: File) => ((f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name);

interface Browse {
  item: WsItem;
  path: string;
  entries: WsEntry[] | null;
  file: WsFile | null;
  changes: WsChanges | null;
  view: "files" | "changes";
  error: string;
}

export interface Setup {
  el: HTMLElement;
  open: () => void;
  close: () => void;
  /** 从别处（侧栏、首次进入）请求打开；真正的挂载由 main.ts 的重绘完成 */
  request: (tab: SetupTab, wizard?: boolean) => void;
}

export function createSetup(): Setup {
  let tab: SetupTab = "workspace";
  let wizard = false;
  let listing: WsListing | null = null;
  let integ: IntegrationsView | null = null;
  let loadError = "";
  let busy = "";
  let progressEl: HTMLElement | null = null;
  let addOpen = false;
  let addMode: AddMode = "upload";
  const form = { name: "", url: "", branch: "" };
  let browse: Browse | null = null;
  const lin = { key: "", found: null as LinearDiscover | null, team: "", project: "", busy: false };
  const git = { name: "", email: "", host: "github.com", token: "" };
  let pending: { tab: SetupTab; wizard: boolean } = { tab: "workspace", wizard: false };

  const title = h("h3", null, "工作区与集成");
  const sub = h("p", { class: "muted small" });
  const tabs = h("div", { class: "setup-tabs" });
  const banner = h("div");
  const body = h("div", { class: "drawer-body" });
  const foot = h("footer", { class: "wizard-foot" });
  const closeBtn = h("button", { class: "icon-btn", title: "关闭", onclick: () => close() }, icon(X, 16));
  const el = h("div", { class: "drawer-mask", onclick: (e: MouseEvent) => e.target === e.currentTarget && close() },
    h("aside", { class: "drawer wide setup-drawer", attrs: { role: "dialog", "aria-label": "工作区与集成" } },
      h("header", { class: "drawer-head" }, h("div", null, title, sub), closeBtn),
      tabs, banner, body, foot));

  const close = () => update((s) => (s.drawer = null));

  async function refresh() {
    try {
      [listing, integ] = await Promise.all([api.workspaces(), api.integrations()]);
      loadError = "";
    } catch (e) {
      loadError = errText(e);
    }
    render();
  }

  function applied(l: WsListing, msg: string) {
    listing = l;
    toast(msg);
    void loadStatus();
    render();
  }

  async function run(label: string, fn: () => Promise<void>) {
    busy = label;
    render();
    try {
      await fn();
    } catch (e) {
      toast(errText(e), "error");
    } finally {
      busy = "";
      progressEl = null;
      render();
    }
  }

  // ---------------- 通用小件 ----------------
  function field(label: string, input: HTMLElement, hint?: string | HTMLElement): HTMLElement {
    return h("label", { class: "field" }, h("span", { class: "field-label" }, label), input,
      hint && h("span", { class: "field-hint" }, hint));
  }
  function inp(get: () => string, set: (v: string) => void, attrs: Record<string, string> = {}): HTMLInputElement {
    const node = h("input", { class: "text-input", attrs: { spellcheck: "false", autocomplete: "off", ...attrs } });
    node.value = get();
    node.addEventListener("input", () => set(node.value));
    return node;
  }
  const spin = (on: boolean, node: Parameters<typeof icon>[0], size = 14) => icon(on ? LoaderCircle : node, size, on ? "spin" : "");

  // ---------------- 工作区 / 笔记库列表 ----------------
  function itemRow(it: WsItem, activeId: string): HTMLElement {
    const active = it.id === activeId;
    return h("div", { class: ["ws-row", active && "active"] },
      h("div", { class: "ws-main" },
        h("div", { class: "ws-name" }, icon(it.git ? FolderGit2 : Folder, 15), it.name,
          active && h("span", { class: "tag accent" }, "当前"),
          h("span", { class: "tag" }, SOURCE_LABEL[it.source] ?? it.source)),
        it.url && h("div", { class: "muted small mono ws-url" }, it.url)),
      h("div", { class: "ws-actions" },
        !active && h("button", { class: "btn sm", attrs: { disabled: !!busy || !it.ready }, onclick: () => void activate(it) },
          it.kind === "vault" ? "设为当前笔记库" : "设为当前"),
        h("button", { class: "btn ghost sm", onclick: () => void openBrowse(it) }, icon(Folder, 13), "查看文件"),
        it.syncable && h("button", { class: "btn ghost sm", attrs: { disabled: !!busy }, title: "从 git 远端拉取最新",
          onclick: () => void sync(it) }, spin(busy === `sync:${it.id}`, RefreshCw, 13), "同步"),
        !it.builtin && h("button", { class: "btn ghost sm danger", title: "删除", onclick: () => void remove(it) }, icon(Trash2, 13))));
  }

  async function activate(it: WsItem) {
    await run("activate", async () => {
      applied(await api.activateWorkspace(it.id), it.kind === "vault" ? `笔记库已切到「${it.name}」，新对话生效` : `工作区已切到「${it.name}」，新对话生效`);
    });
  }
  async function sync(it: WsItem) {
    await run(`sync:${it.id}`, async () => applied(await api.pullWorkspace(it.id), `「${it.name}」已同步到最新`));
  }
  async function remove(it: WsItem) {
    if (!window.confirm(`删除「${it.name}」？节点上的这份副本会一起删掉（你本地的原文件夹不受影响）。`)) return;
    await run("delete", async () => {
      applied(await api.deleteWorkspace(it.id), `已删除「${it.name}」`);
      if (browse?.item.id === it.id) browse = null;
    });
  }

  // ---------------- 添加 ----------------
  function addBox(kind: Kind): HTMLElement {
    if (!addOpen) {
      return h("button", { class: "btn sm", onclick: () => { addOpen = true; render(); } }, icon(FolderPlus, 14), kind === "vault" ? "接入笔记库" : "添加工作区");
    }
    const modes: [AddMode, string][] = kind === "vault"
      ? [["clone", "从 git 仓库同步"], ["upload", "上传文件夹 / zip"]]
      : [["upload", "导入本地文件夹"], ["clone", "克隆 git 仓库"], ["empty", "新建空白"]];
    if (!modes.some(([m]) => m === addMode)) addMode = modes[0][0];
    const submit = kind === "vault" ? "接入" : addMode === "empty" ? "创建" : addMode === "clone" ? "克隆" : "";
    return h("div", { class: "add-box" },
      h("div", { class: "seg small" }, modes.map(([m, label]) =>
        h("button", { class: ["seg-btn", addMode === m && "on"], onclick: () => { addMode = m; render(); } }, label))),
      field("名字", inp(() => form.name, (v) => (form.name = v), { placeholder: kind === "vault" ? "比如 我的笔记" : "比如 my-project", maxlength: "40" }),
        addMode === "upload" ? "留空则用文件夹名" : undefined),
      addMode === "clone" && field("仓库地址", inp(() => form.url, (v) => (form.url = v), { placeholder: "https://github.com/owner/repo.git", inputmode: "url" }),
        "只支持 https。私有仓库先到「集成」里填访问令牌。"),
      addMode === "clone" && field("分支（可选）", inp(() => form.branch, (v) => (form.branch = v), { placeholder: "默认分支", maxlength: "80" })),
      addMode === "upload" && uploadPickers(kind),
      h("div", { class: "form-actions" },
        h("span", { class: "spacer" }),
        h("button", { class: "btn ghost", attrs: { disabled: !!busy }, onclick: () => { addOpen = false; render(); } }, "取消"),
        addMode !== "upload" && h("button", { class: "btn primary", attrs: { disabled: !!busy }, onclick: () => void submitAdd(kind) },
          busy === "add" ? "处理中…" : submit)));
  }

  function uploadPickers(kind: Kind): HTMLElement {
    const folder = h("input", { attrs: { type: "file", webkitdirectory: true, multiple: true, hidden: true } }) as HTMLInputElement;
    folder.addEventListener("change", () => folder.files?.length && void uploadFolder([...folder.files], kind));
    const zip = h("input", { attrs: { type: "file", accept: ".zip,application/zip", hidden: true } }) as HTMLInputElement;
    zip.addEventListener("change", () => zip.files?.[0] && void uploadZip(zip.files[0], kind));
    progressEl = h("div", { class: "muted small progress-line" }, busy === "upload" ? "准备上传…" : "");
    return h("div", { class: "pick-box" },
      h("div", { class: "pick-btns" },
        h("button", { class: "btn", attrs: { disabled: !!busy }, onclick: () => folder.click() }, spin(busy === "upload", Upload), "选择文件夹…"),
        h("button", { class: "btn ghost", attrs: { disabled: !!busy }, onclick: () => zip.click() }, "选择 zip…"),
        folder, zip),
      progressEl,
      h("p", { class: "muted small note" },
        kind === "vault"
          ? "上传的是一次性快照，笔记更新后要重新上传；想自动同步请用 git 仓库（Obsidian Git 插件）。"
          : "浏览器读你选的文件夹并传到节点，agent 改的是节点上的副本；改完在「查看文件 → 改动」里写回本地或下载。依赖目录（node_modules 等）和上传里自带的 .git 会被丢掉。"));
  }

  async function submitAdd(kind: Kind) {
    await run("add", async () => {
      const l = await api.createWorkspace({
        name: form.name.trim() || (addMode === "clone" ? (form.url.split("/").pop() ?? "").replace(/\.git$/, "") : ""),
        kind, mode: addMode === "clone" ? "clone" : "empty", url: form.url.trim(), branch: form.branch.trim(),
      });
      finishAdd(l, kind);
    });
  }

  function finishAdd(l: WsListing, kind: Kind) {
    const made = l.created;
    form.name = form.url = form.branch = "";
    addOpen = false;
    applied(l, `已添加「${made?.name ?? ""}」`);
    if (made && window.confirm(`把「${made.name}」设为当前${kind === "vault" ? "笔记库" : "工作区"}吗？新对话会用它。`)) void activate(made);
  }

  async function uploadZip(file: File, kind: Kind) {
    await run("upload", async () => {
      const name = form.name.trim() || file.name.replace(/\.zip$/i, "");
      finishAdd(await api.uploadZip(name, kind, file), kind);
    });
  }

  async function uploadFolder(files: File[], kind: Kind) {
    const root = relOf(files[0]).split("/")[0];
    const keep = files.filter((f) => !relOf(f).split("/").some((p) => SKIP_DIRS.has(p)) && f.size <= MAX_FILE);
    if (!keep.length) return toast("这个文件夹里没有可上传的文件", "error");
    if (keep.length > MAX_FILES) return toast(`文件太多（${keep.length} 个，上限 ${MAX_FILES}）：先删掉依赖和构建产物，或者打成 zip 再传`, "error");
    const name = form.name.trim() || root;
    await run("upload", async () => {
      const { id } = await api.beginFolder(name, kind);
      let done = 0;
      const queue = [...keep];
      const note = () => { if (progressEl) progressEl.textContent = `上传中 ${done} / ${keep.length}`; };
      note();
      try {
        await Promise.all(Array.from({ length: 4 }, async () => {
          for (let f = queue.shift(); f; f = queue.shift()) {
            await api.putFile(id, relOf(f).split("/").slice(1).join("/"), f);
            done++;
            note();
          }
        }));
        finishAdd(await api.finishFolder(id), kind);
        if (keep.length < files.length) toast(`已跳过 ${files.length - keep.length} 个依赖 / 缓存 / 过大的文件`);
      } catch (e) {
        await api.deleteWorkspace(id).catch(() => {});  // 传一半失败：清掉半成品
        throw e;
      }
    });
  }

  // ---------------- 看文件 ----------------
  async function openBrowse(it: WsItem) {
    browse = { item: it, path: "", entries: null, file: null, changes: null, view: "files", error: "" };
    render();
    await loadDir("");
    void loadChanges();
  }
  async function loadDir(path: string) {
    const b = browse!;
    b.path = path; b.file = null; b.error = ""; b.view = "files";
    try {
      b.entries = (await api.wsTree(b.item.id, path)).entries;
    } catch (e) {
      b.error = errText(e);
    }
    render();
  }
  async function loadFile(path: string) {
    const b = browse!;
    b.error = "";
    try {
      b.file = await api.wsFile(b.item.id, path);
    } catch (e) {
      b.error = errText(e);
    }
    render();
  }
  async function loadChanges() {
    const b = browse;
    if (!b) return;
    try {
      b.changes = await api.wsChanges(b.item.id);
    } catch { /* 改动清单只是辅助信息 */ }
    render();
  }

  function crumbs(b: Browse): HTMLElement {
    const parts = (b.file ? b.file.path : b.path).split("/").filter(Boolean);
    return h("div", { class: "crumbs" },
      h("button", { class: "link", onclick: () => void loadDir("") }, b.item.name),
      parts.map((p, i) => {
        const upto = parts.slice(0, i + 1).join("/");
        const isFile = !!b.file && i === parts.length - 1;
        return [h("span", { class: "muted" }, "/"),
          isFile ? h("span", null, p) : h("button", { class: "link", onclick: () => void loadDir(upto) }, p)];
      }));
  }

  function codeView(f: WsFile): HTMLElement {
    if (f.binary) return h("p", { class: "muted drawer-empty" }, `二进制文件（${fmtSize(f.size)}），不预览`);
    const lines = f.text.split("\n");
    if (lines.length && lines[lines.length - 1] === "") lines.pop();
    return h("div", { class: "code" },
      h("pre", { class: "gutter" }, lines.map((_, i) => i + 1).join("\n")),
      h("pre", { class: "src" }, f.text));
  }

  function joinPath(dir: string, name: string) { return dir ? `${dir}/${name}` : name; }

  function browsePage(): HTMLElement[] {
    const b = browse!;
    const n = b.changes?.changes.length ?? 0;
    const canWriteBack = b.item.source === "upload" && "showDirectoryPicker" in window;
    return [
      h("button", { class: "back", onclick: () => { browse = null; render(); } }, icon(ChevronLeft, 16), "返回列表"),
      h("div", { class: "browse-bar" },
        h("div", { class: "seg small" },
          h("button", { class: ["seg-btn", b.view === "files" && "on"], onclick: () => { b.view = "files"; render(); } }, "文件"),
          b.item.kind === "workspace" && h("button", { class: ["seg-btn", b.view === "changes" && "on"], onclick: () => { b.view = "changes"; void loadChanges(); } },
            n ? `改动 ${n}` : "改动")),
        h("span", { class: "spacer" }),
        h("a", { class: "btn ghost sm", attrs: { href: api.wsZipUrl(b.item.id), download: "" }, title: "打包下载（不含 .git）" }, icon(Download, 13), "下载 zip")),
      ...(b.error ? [h("p", { class: "test-result bad" }, icon(CircleAlert, 13), b.error)] : []),
      b.view === "changes" ? changesPage(b, canWriteBack) : filesPage(b),
    ];
  }

  function filesPage(b: Browse): HTMLElement {
    if (b.file) {
      return h("div", { class: "browse-body" }, crumbs(b),
        h("div", { class: "muted small" }, `${fmtSize(b.file.size)}${b.file.truncated ? " · 只显示前 200KB" : ""}`), codeView(b.file));
    }
    if (!b.entries) return h("p", { class: "muted drawer-empty" }, "正在读取…");
    return h("div", { class: "browse-body" }, crumbs(b),
      b.path && h("button", { class: "file-row", onclick: () => void loadDir(b.path.split("/").slice(0, -1).join("/")) },
        icon(Folder, 14), h("span", null, ".."), h("span", { class: "spacer" })),
      b.entries.length === 0 && h("p", { class: "muted drawer-empty" }, "这里是空的"),
      b.entries.map((e) => h("button", {
        class: "file-row",
        onclick: () => (e.type === "dir" ? void loadDir(joinPath(b.path, e.name)) : void loadFile(joinPath(b.path, e.name))),
      }, icon(e.type === "dir" ? Folder : FileIcon, 14), h("span", { class: "file-name" }, e.name),
      h("span", { class: "spacer" }), e.type === "file" && h("span", { class: "muted small" }, fmtSize(e.size)))));
  }

  function changesPage(b: Browse, canWriteBack: boolean): HTMLElement {
    const ch = b.changes?.changes ?? [];
    return h("div", { class: "browse-body" },
      h("p", { class: "muted small" }, b.changes?.base
        ? `相对导入 / 克隆时的快照（${b.changes.base}）。agent 提交过的改动也算在内。`
        : "这个目录还不是 git 仓库，没有可比较的基准。"),
      ch.length === 0 ? h("p", { class: "muted drawer-empty" }, "还没有改动") : h("div", { class: "change-list" }, ch.map((c) =>
        h("button", { class: "file-row", attrs: { disabled: c.status === "deleted" },
          onclick: () => { b.view = "files"; void loadFile(c.path); } },
        h("span", { class: `st ${c.status}` }, CHANGE_LABEL[c.status]), h("span", { class: "file-name" }, c.path)))),
      ch.length > 0 && h("div", { class: "form-actions" }, h("span", { class: "spacer" }),
        canWriteBack
          ? h("button", { class: "btn primary", attrs: { disabled: !!busy }, onclick: () => void writeBack(b) },
            spin(busy === "writeback", Undo2), "写回本地文件夹…")
          : h("span", { class: "muted small" }, b.item.source === "upload" ? "这个浏览器不能直接写回，请下载 zip 覆盖原文件夹" : "用「下载 zip」带走改动")),
      ch.length > 0 && canWriteBack && h("p", { class: "muted small note" },
        "会请你选择原来的那个文件夹（浏览器要求每次授权），只写入上面列出的文件，写之前会再确认一次。"));
  }

  async function dirAt(root: FileSystemDirectoryHandle, parts: string[], create: boolean) {
    let cur = root;
    for (const p of parts) cur = await cur.getDirectoryHandle(p, { create });
    return cur;
  }

  async function writeBack(b: Browse) {
    const pick = (window as unknown as { showDirectoryPicker: (o: object) => Promise<FileSystemDirectoryHandle> }).showDirectoryPicker;
    let root: FileSystemDirectoryHandle;
    try {
      root = await pick({ mode: "readwrite" });
    } catch { return; }  // 用户取消
    const ch = (await api.wsChanges(b.item.id)).changes;
    const put = ch.filter((c) => c.status !== "deleted");
    const del = ch.filter((c) => c.status === "deleted");
    const msg = `写入「${root.name}」：新增 / 修改 ${put.length} 个文件` + (del.length ? `，删除 ${del.length} 个文件` : "") +
      "。确认这是你导入时选的那个文件夹，继续？";
    if (!window.confirm(msg)) return;
    await run("writeback", async () => {
      for (const c of put) {
        const parts = c.path.split("/");
        const dir = await dirAt(root, parts.slice(0, -1), true);
        const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
        await w.write(await api.wsRaw(b.item.id, c.path));
        await w.close();
      }
      for (const c of del) {
        const parts = c.path.split("/");
        try {
          await (await dirAt(root, parts.slice(0, -1), false)).removeEntry(parts[parts.length - 1]);
        } catch { /* 本来就不在了 */ }
      }
      toast(`已写回 ${put.length} 个文件${del.length ? `，删除 ${del.length} 个` : ""}`);
    });
  }

  // ---------------- 页面 ----------------
  function listSection(kind: Kind): HTMLElement[] {
    const items = kind === "vault" ? listing!.vaults : listing!.workspaces;
    const activeId = kind === "vault" ? listing!.active_vault : listing!.active_workspace;
    return [
      h("div", { class: "ws-list" }, items.map((it) => itemRow(it, activeId))),
      addBox(kind),
    ];
  }

  function workspacePage(): HTMLElement[] {
    return [
      h("section", { class: "set-section" },
        h("div", { class: "set-title" }, "agent 操作的工作区"),
        h("p", { class: "muted small note" },
          "面板跑在 DGX Spark 上，看不到你电脑的磁盘，所以这里放的是节点上的一份副本：可以从 git 克隆、导入你电脑上的文件夹，或者新建空白项目。切换后新建的对话生效，进行中的对话不受影响。"),
        ...listSection("workspace")),
    ];
  }

  function vaultPage(): HTMLElement[] {
    return [
      h("section", { class: "set-section" },
        h("div", { class: "set-title" }, icon(BookOpen, 14), "笔记库（Obsidian，只读）"),
        h("p", { class: "muted small note" },
          "agent 用 list_notes / read_note 读节点上的笔记库副本，不会修改你的笔记。线上面板碰不到你本机的 Obsidian，有两种接法："),
        h("div", { class: "how" },
          h("div", null, h("b", null, "① git 同步（推荐）："), "在 Obsidian 里装「Obsidian Git」插件，把库推到一个私有仓库；在这里填仓库地址（私有仓库先在「集成」填令牌），之后点「同步」拉最新。"),
          h("div", null, h("b", null, "② 上传快照："), "直接选笔记库文件夹或 zip 上传，一次性的，笔记更新后要重新上传。")),
        ...listSection("vault")),
    ];
  }

  // ---- 集成 ----
  async function linDiscover() {
    lin.busy = true; render();
    try {
      const found = await api.discoverLinear(lin.key.trim());
      lin.found = found;
      if (!found.teams.some((t) => t.key === lin.team)) lin.team = found.teams[0]?.key ?? "";
      lin.project = "";
      toast(`已连上 Linear：${found.user}`);
    } catch (e) {
      toast(errText(e), "error");
    }
    lin.busy = false; render();
  }
  async function linSave() {
    await run("linear", async () => {
      integ = await api.saveLinear({ api_key: lin.key.trim() || undefined, team_key: lin.team, project_name: lin.project });
      lin.key = ""; lin.found = null;
      toast("Linear 已保存，新对话生效");
      void loadStatus();
    });
  }
  async function linClear() {
    if (!window.confirm("清除你填的 Linear Key，恢复到演示项目？")) return;
    await run("linear", async () => { integ = await api.clearLinear(); toast("已恢复演示 Linear"); void loadStatus(); });
  }

  function linearCard(): HTMLElement {
    const l = integ!.linear;
    const found = lin.found;
    const projects = found ? found.projects.filter((p) => p.teams.includes(lin.team)) : [];
    const select = (value: string, opts: [string, string][], onChange: (v: string) => void) => {
      const s = h("select", { class: "text-input" }, opts.map(([v, label]) => h("option", { attrs: { value: v, selected: v === value } }, label)));
      s.addEventListener("change", () => onChange(s.value));
      return s;
    };
    return h("section", { class: "set-section card" },
      h("div", { class: "set-title" }, icon(Plug, 14), "Linear",
        l.demo ? h("span", { class: "tag" }, "演示项目") : h("span", { class: "tag accent" }, `你的 · ${l.team_key}${l.project_name ? " / " + l.project_name : ""}`)),
      h("p", { class: "muted small note" }, l.demo
        ? `现在连的是演示用的 Linear 项目（团队 ${l.team_key}${l.project_name ? "，项目「" + l.project_name + "」" : ""}）。填你自己的 Personal API Key，agent 就读写你自己的 issue。`
        : "agent 现在读写的是你的 Linear。Key 存在节点上，页面不会再显示。"),
      field("Personal API Key", inp(() => lin.key, (v) => (lin.key = v), { type: "password", placeholder: l.demo ? "lin_api_…" : "已设置，留空保持不变" }),
        "Linear → Settings → Security & access → Personal API keys 里创建；只需要读写 issue 的权限。"),
      h("div", { class: "form-actions" },
        h("button", { class: "btn", attrs: { disabled: lin.busy || (!lin.key.trim() && l.demo) }, onclick: () => void linDiscover() },
          spin(lin.busy, KeyRound), "连接并读取团队 / 项目")),
      found && field("团队", select(lin.team, found.teams.map((t) => [t.key, `${t.name}（${t.key}）`]), (v) => { lin.team = v; lin.project = ""; render(); })),
      found && field("项目（可选）", select(lin.project, [["", "整个团队"], ...projects.map((p): [string, string] => [p.name, p.name])], (v) => (lin.project = v)),
        "选项目就只读写这个项目里的 issue；选「整个团队」范围更大。agent 访问范围外的 issue 会被拒绝。"),
      h("div", { class: "form-actions" },
        !l.demo && l.source === "panel" && h("button", { class: "btn ghost", attrs: { disabled: !!busy }, onclick: () => void linClear() }, "恢复演示"),
        h("span", { class: "spacer" }),
        found && h("button", { class: "btn primary", attrs: { disabled: !!busy || !lin.team }, onclick: () => void linSave() },
          busy === "linear" ? "保存中…" : "保存")));
  }

  function gitCard(): HTMLElement {
    const g = integ!.git;
    if (!git.name && !git.email) { git.name = g.user_name; git.email = g.user_email; }
    return h("section", { class: "set-section card" },
      h("div", { class: "set-title" }, icon(GitBranch, 14), "Git"),
      h("p", { class: "muted small note" },
        "提交身份决定 agent 帮你提交代码时署谁的名；访问令牌用来克隆 / 同步私有仓库。agent 自己不会 push，推送由你在本地做。"),
      h("div", { class: "two-col" },
        field("提交姓名", inp(() => git.name, (v) => (git.name = v), { placeholder: "dgx-agent", maxlength: "60" })),
        field("提交邮箱", inp(() => git.email, (v) => (git.email = v), { placeholder: "dgx-agent@localhost", maxlength: "80", inputmode: "email" }))),
      h("div", { class: "form-actions" }, h("span", { class: "spacer" }),
        h("button", { class: "btn", attrs: { disabled: !!busy }, onclick: () => void run("git", async () => {
          integ = await api.saveGit(git.name.trim(), git.email.trim());
          toast("提交身份已保存，新对话生效");
        }) }, "保存身份")),
      h("div", { class: "field-label token-title" }, "私有仓库访问令牌"),
      g.hosts.length > 0 && h("div", { class: "chips" }, g.hosts.map((host) => h("span", { class: "chip" }, icon(KeyRound, 11), host,
        h("button", { class: "chip-x", title: `删除 ${host} 的令牌`, onclick: () => void run("token", async () => {
          integ = await api.deleteToken(host);
        }) }, icon(X, 11))))),
      h("div", { class: "two-col" },
        field("主机", inp(() => git.host, (v) => (git.host = v), { placeholder: "github.com" })),
        field("令牌", inp(() => git.token, (v) => (git.token = v), { type: "password", placeholder: "ghp_… / glpat-…" }))),
      h("div", { class: "form-actions" },
        h("span", { class: "field-hint" }, "令牌明文存在节点 var/integrations.json（600 权限），页面不回显；只在克隆 / 同步时使用。"),
        h("span", { class: "spacer" }),
        h("button", { class: "btn", attrs: { disabled: !!busy || !git.token.trim() }, onclick: () => void run("token", async () => {
          integ = await api.saveToken(git.host.trim(), git.token.trim());
          git.token = "";
          toast(`已保存 ${git.host.trim()} 的令牌`);
        }) }, "保存令牌")));
  }

  function integrationsPage(): HTMLElement[] {
    return [
      h("p", { class: "muted small note" }, "这个面板是单实例，这里的设置对所有能登录的人生效。要回到演示环境，在对应卡片里点「恢复演示」。"),
      linearCard(), gitCard(),
    ];
  }

  // ---------------- 总渲染 ----------------
  function render() {
    progressEl = null;
    const tabDefs: [SetupTab, string][] = [["workspace", "工作区"], ["vault", "笔记库"], ["integrations", "集成"]];
    mount(tabs, h("div", { class: "seg" }, tabDefs.map(([t, label]) =>
      h("button", { class: ["seg-btn", tab === t && "on"], onclick: () => { tab = t; browse = null; addOpen = false; render(); } }, label))));
    title.textContent = wizard ? "开始之前：接上你的环境" : "工作区与集成";
    sub.textContent = wizard
      ? "都可以跳过，直接用演示环境；之后在左下角随时再改。"
      : "选 agent 改代码的地方、看里面的文件，接自己的 Linear、Git 和笔记库。";
    mount(banner, wizard && h("div", { class: "wizard-banner" },
      h("div", null, h("b", null, "三步接上你自己的东西："),
        " ① 工作区（克隆仓库 / 导入本地文件夹） ② 集成（Linear、Git） ③ 笔记库（Obsidian）。")));
    mount(foot, wizard && [
      h("span", { class: "muted small" }, "评审 / 试用的话，直接用演示环境就行。"),
      h("span", { class: "spacer" }),
      h("button", { class: "btn primary", onclick: () => close() }, icon(Check, 14), "使用演示环境，开始")]);
    foot.style.display = wizard ? "flex" : "none";
    if (loadError) return mount(body, h("p", { class: "muted drawer-empty" }, loadError));
    if (!listing || !integ) return mount(body, h("p", { class: "muted drawer-empty" }, "正在读取…"));
    if (browse && tab !== "integrations") return mount(body, ...browsePage());
    mount(body, ...(tab === "workspace" ? workspacePage() : tab === "vault" ? vaultPage() : integrationsPage()));
  }

  return {
    el,
    request(t, w = false) {
      pending = { tab: t, wizard: w };
      update((s) => (s.drawer = "setup"));
    },
    open() {
      ({ tab, wizard } = pending);
      pending = { tab: "workspace", wizard: false };
      browse = null; addOpen = false; busy = "";
      lin.key = lin.project = ""; lin.found = null; git.token = "";
      render();
      void refresh();
    },
    close() {
      // 无论点「开始」、关闭按钮还是 Esc：看过向导就不再自动弹出
      if (wizard) void api.setOnboarded(true).then(() => loadStatus()).catch(() => {});
      wizard = false;
      browse = null;
    },
  };
}

export const setup = createSetup();
