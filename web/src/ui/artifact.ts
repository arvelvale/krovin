import { Code2, ExternalLink, FileCode2, Play, RefreshCw, X } from "lucide";
import "../setup.css";
import { api, ApiError } from "../api";
import { toast, update, type Current } from "../store";
import type { Turn, WsFile } from "../types";
import { h, icon, mount } from "./dom";

/**
 * 对话里的「产物卡片」：agent 这一轮写出了网页（html），回复下面就出现一张卡片，点开在大窗口里预览 / 看代码。
 * 预览窗口是常驻的一个元素（和「工作区与集成」一样只挂载一次）——对话区每次重绘都会重建，
 * iframe 一旦被重建游戏就重新开始，所以不能放在对话区里。
 */
const HTML = /\.html?$/i;
const ASSET = /\.(js|mjs|jsx|ts|tsx|css|vue|svg)$/i;

export interface Artifact { path: string; others: string[] }

function writtenPaths(t: Turn): string[] {
  const out: string[] = [];
  for (const e of t.events) {
    if (e.type !== "tool.call" || !e.data.ok || (e.data.tool !== "write_file" && e.data.tool !== "edit_file")) continue;
    const p = String(e.data.args?.path ?? "");
    if (p && !out.includes(p)) out.push(p);
  }
  return out;
}

/** 这一轮产出的网页：写了 html 就是它；只改了 js / css，就取本次会话里最近写过的 html */
export function turnArtifacts(cur: Current, t: Turn): Artifact[] {
  if (!cur.workspaceId) return [];
  const written = writtenPaths(t);
  if (t.events.some(e => e.type === "preview.ready") || written.some(p => /(?:package\.json|\.[jt]sx)$/.test(p)))
    return [{path:"index.html", others:written}];
  const htmls = written.filter((p) => HTML.test(p));
  if (htmls.length) return htmls.map((path) => ({ path, others: written.filter((p) => p !== path) }));
  if (!written.some((p) => ASSET.test(p))) return [];
  const earlier = [...cur.turns.values()].filter((x) => x.n < t.n).sort((a, b) => b.n - a.n);
  for (const prev of earlier) {
    const h2 = writtenPaths(prev).filter((p) => HTML.test(p));
    if (h2.length) return [{ path: h2[h2.length - 1], others: written }];
  }
  return [];
}

export function artifactCard(cur: Current, a: Artifact): HTMLElement {
  const open = (mode: "preview" | "code") => artifactView.request(cur.workspaceId!, a.path, mode);
  const name = a.path.split("/").pop() ?? a.path;
  return h("div", { class: "artifact", attrs: { role: "group", "aria-label": `产物 ${name}` } },
    h("div", { class: "artifact-icon" }, icon(FileCode2, 20)),
    h("button", { class: "artifact-text", title: "预览", onclick: () => open("preview") },
      h("span", { class: "artifact-name" }, name),
      h("span", { class: "artifact-sub" }, "网页 · 在线预览" + (a.others.length ? ` · 同时改动 ${a.others.slice(0, 3).join("、")}${a.others.length > 3 ? "…" : ""}` : ""))),
    h("div", { class: "artifact-actions" },
      h("button", { class: "icon-btn", title: "看代码", onclick: () => open("code") }, icon(Code2, 16)),
      h("button", { class: "icon-btn primary", title: "预览", onclick: () => open("preview") }, icon(Play, 16))));
}

function createArtifactView() {
  let pending: { wid: string; path: string; mode: "preview" | "code" } | null = null;
  let cur: { wid: string; path: string } | null = null;
  let mode: "preview" | "code" = "preview";
  let url = "";
  let file: WsFile | null = null;
  let error = "";
  let loading = false;

  const title = h("span", { class: "av-title mono" });
  const tabPreview = h("button", { class: "seg-btn", onclick: () => switchTo("preview") }, "预览");
  const tabCode = h("button", { class: "seg-btn", onclick: () => switchTo("code") }, "代码");
  const frameHost = h("div", { class: "av-frame-host" });
  const codeHost = h("div", { class: "av-code" });
  const errBox = h("p", { class: "muted av-error" });
  let frame: HTMLIFrameElement | null = null;
  const close = () => update((s) => (s.drawer = null));
  const refreshBtn = h("button", { class: "btn ghost sm", title: "agent 改完文件后点这里重新载入", onclick: () => { url = ""; void load(); } },
    icon(RefreshCw, 13), "重新启动");
  const newTab = h("a", { class: "btn ghost sm", attrs: { target: "_blank", rel: "noopener noreferrer" } }, icon(ExternalLink, 13), "新窗口打开");
  const el = h("div", { class: "av-mask", onclick: (e: MouseEvent) => e.target === e.currentTarget && close() },
    h("div", { class: "av-panel", attrs: { role: "dialog", "aria-label": "产物预览" } },
      h("header", { class: "av-head" }, icon(FileCode2, 16), title, h("div", { class: "seg small" }, tabPreview, tabCode),
        h("span", { class: "spacer" }), refreshBtn,
        h("button", {class:"btn ghost sm", onclick:async () => { if(cur) { await api.stopPreview(cur.wid); url=""; error="预览已停止，点击重新启动即可恢复"; mount(frameHost); render(); } }}, "停止预览"), newTab,
        h("button", { class: "icon-btn", title: "关闭", onclick: close }, icon(X, 16))),
      errBox, frameHost, codeHost, h("p", {class:"muted small"}, "预览保留 2 小时；修改代码后点重新启动。预览中的本地存储为临时数据，刷新会清空。")));

  function render() {
    tabPreview.classList.toggle("on", mode === "preview");
    tabCode.classList.toggle("on", mode === "code");
    frameHost.style.display = mode === "preview" && !error ? "block" : "none";
    codeHost.style.display = mode === "code" && !error ? "block" : "none";
    refreshBtn.style.display = mode === "preview" ? "" : "none";
    errBox.textContent = error;
    refreshBtn.disabled = loading;
    if (url) newTab.setAttribute("href", url); else newTab.removeAttribute("href");
    if (mode === "code") {
      if (!file) return mount(codeHost, h("p", { class: "muted drawer-empty" }, "正在读取…"));
      if (file.binary) return mount(codeHost, h("p", { class: "muted drawer-empty" }, "二进制文件，不预览"));
      const lines = file.text.split("\n");
      if (lines[lines.length - 1] === "") lines.pop();
      mount(codeHost, h("div", { class: "code" }, h("pre", { class: "gutter" }, lines.map((_, i) => i + 1).join("\n")),
        h("pre", { class: "src" }, file.text)));
    }
  }

  window.addEventListener("message", (event) => {
    if (!frame || event.source !== frame.contentWindow || event.data?.type !== "krovin-preview-error") return;
    error = "预览运行失败：" + String(event.data.message ?? "未知错误").slice(0, 1200);
    render();
  });

  async function load() {
    if (!cur || loading) return;
    loading = true;
    error = "";
    try {
      if (!url && mode === "preview") {
        error = "正在启动预览，首次安装依赖可能需要一两分钟…";
        render();
        const r = await api.startPreview(cur.wid, cur.path);
        error = "";
        url = r.url;
        frame = h("iframe", { class: "av-frame", title: `预览 ${cur.path}`,
          attrs: { src: url, sandbox: "allow-scripts allow-modals allow-forms allow-pointer-lock", referrerpolicy: "no-referrer" } }) as HTMLIFrameElement;
        mount(frameHost, frame);
      }
      if (mode === "code" && !file) file = await api.wsFile(cur.wid, cur.path);
    } catch (e) {
      error = e instanceof ApiError ? e.message : "读取失败，稍后再试";
      toast(error, "error");
    } finally { loading = false; }
    render();
  }

  async function switchTo(m: "preview" | "code") {
    mode = m;
    render();
    await load();
  }

  return {
    el,
    request(wid: string, path: string, m: "preview" | "code") {
      pending = { wid, path, mode: m };
      update((s) => (s.drawer = "preview"));
    },
    open() {
      if (!pending) return;
      cur = { wid: pending.wid, path: pending.path };
      mode = pending.mode;
      pending = null;
      url = ""; file = null; error = ""; frame = null;
      mount(frameHost);
      title.textContent = cur.path;
      render();
      void load();
    },
    close() {
      // 关掉就销毁 iframe：游戏 / 页面里的定时器和声音也随之停止
      mount(frameHost);
      frame = null;
    },
  };
}

export const artifactView = createArtifactView();
