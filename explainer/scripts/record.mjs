// 录真实面板：无头 Edge + CDP 驱动 Web 面板跑真实任务，逐帧录屏，顺手记下关键元素坐标和高清截图。
//   node scripts/record.mjs [片段名…]        默认按顺序录全部片段
// 面板地址：PANEL（默认 http://127.0.0.1:9100，免登录回环实例）、LOGIN_URL（带口令的实例，只截登录页，不输入口令）
// 输出：public/rec/<片段>/f000123.jpg + clip.json（每帧时间、标记、元素坐标）；public/rec/shots/*.png（文档用截图）
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const PANEL = process.env.PANEL || "http://127.0.0.1:9100";
const LOGIN_URL = process.env.LOGIN_URL || "http://127.0.0.1:9101";
const EDGE = process.env.EDGE_PATH || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const OUT = path.resolve("public/rec");
const VW = 1440, VH = 810, DPR = 4 / 3; // 录出来是 1920×1080，界面相当于 1440 宽的笔记本屏幕
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (m) => console.error(`[record] ${m}`);

// ---------------- CDP ----------------
const port = 9700 + Math.floor(Math.random() * 60);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "rec-edge-"));
const edge = spawn(EDGE, ["--headless=new", `--remote-debugging-port=${port}`, "--remote-allow-origins=*", `--user-data-dir=${profile}`,
  `--window-size=${VW},${VH}`, "--hide-scrollbars", "--no-first-run", "--no-proxy-server", "--mute-audio",
  "--force-color-profile=srgb", "--lang=zh-CN", "about:blank"], { stdio: "ignore" });

let ws, id = 0;
const pending = new Map();
const handlers = new Map();
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    pending.set(++id, (m) => (m.error ? reject(new Error(`${method}: ${m.error.message}`)) : resolve(m.result)));
    ws.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(`页面报错：${r.exceptionDetails.exception?.description ?? r.exceptionDetails.text}`);
  return r.result?.value;
}
async function waitFor(expr, timeout = 15000, every = 250) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await evaluate(expr).catch(() => false)) return true;
    await sleep(every);
  }
  throw new Error(`等待超时：${expr.slice(0, 80)}`);
}

// ---------------- 假指针（无头浏览器没有鼠标，视频里点击会凭空发生） ----------------
const CURSOR = `(() => {
  if (window.__cur) return;
  const make = () => {
    const c = document.createElement("div");
    c.id = "__cursor";
    c.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l15 9-6.5 1.6L9.6 19z" fill="#1c211e" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: "fixed", left: "0", top: "0", zIndex: 2147483647, pointerEvents: "none",
      transform: "translate(720px, 460px)", transition: "transform 0ms", filter: "drop-shadow(0 2px 3px rgba(0,0,0,.25))" });
    const ring = document.createElement("div");
    ring.id = "__ring";
    Object.assign(ring.style, { position: "fixed", width: "34px", height: "34px", marginLeft: "-15px", marginTop: "-15px",
      borderRadius: "50%", border: "2.5px solid #3d7a4c", zIndex: 2147483646, pointerEvents: "none", opacity: "0" });
    document.body.append(c, ring);
    return { c, ring };
  };
  let el = null, x = 720, y = 460;
  window.__cur = {
    move(nx, ny, ms) { el = el || make(); el.c.style.transition = "transform " + ms + "ms cubic-bezier(.3,.7,.2,1)";
      el.c.style.transform = "translate(" + nx + "px," + ny + "px)"; x = nx; y = ny; },
    click() { el = el || make(); const r = el.ring; r.style.left = x + "px"; r.style.top = y + "px";
      r.animate([{ opacity: .9, transform: "scale(.4)" }, { opacity: 0, transform: "scale(1.4)" }], { duration: 520, easing: "ease-out" }); },
  };
})()`;

async function box(selector, text) {
  return evaluate(`(() => {
    const els = [...document.querySelectorAll(${JSON.stringify(selector)})];
    const el = ${text ? `els.find((e) => e.textContent.includes(${JSON.stringify(text)}))` : "els[0]"};
    if (!el) return null;
    el.scrollIntoView({ block: "nearest" });
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height };
  })()`);
}
async function pointAt(selector, text, ms = 650) {
  const b = await box(selector, text);
  if (!b) throw new Error(`找不到元素 ${selector} ${text ?? ""}`);
  const x = Math.round(b.x + Math.min(b.w / 2, 60)), y = Math.round(b.y + b.h / 2);
  await evaluate(`window.__cur.move(${x}, ${y}, ${ms})`);
  await sleep(ms + 120);
  return { x, y, b };
}
async function click(selector, text, ms) {
  const { x, y } = await pointAt(selector, text, ms);
  await evaluate("window.__cur.click()");
  for (const type of ["mousePressed", "mouseReleased"]) {
    await send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 });
  }
  await sleep(300);
}
async function type(selector, text) {
  await click(selector);
  for (const ch of text) {
    await send("Input.insertText", { text: ch });
    await sleep(45 + Math.random() * 55);
  }
  await sleep(400);
}
async function scrollIn(selector, dy, steps = 12, gap = 90) {
  for (let i = 0; i < steps; i++) {
    await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (el) el.scrollBy({ top: ${dy / steps} }); })()`);
    await sleep(gap);
  }
}

// ---------------- 录制 ----------------
let clip = null;
function startClip(name) {
  const dir = path.join(OUT, name);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  clip = { name, dir, frames: [], marks: [], t0: null, n: 0 };
  return send("Page.startScreencast", { format: "jpeg", quality: 82, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
}
handlers.set("Page.screencastFrame", (p) => {
  send("Page.screencastFrameAck", { sessionId: p.sessionId }).catch(() => {});
  if (!clip) return;
  const ts = p.metadata.timestamp;
  if (clip.t0 === null) clip.t0 = ts;
  const f = `f${String(clip.n++).padStart(6, "0")}.jpg`;
  fs.writeFileSync(path.join(clip.dir, f), Buffer.from(p.data, "base64"));
  clip.frames.push({ f, t: +(ts - clip.t0).toFixed(3) });
});
function now() {
  return clip && clip.frames.length ? clip.frames[clip.frames.length - 1].t + 0.001 : 0;
}
async function mark(name, boxes = {}) {
  const resolved = {};
  for (const [k, [sel, text]] of Object.entries(boxes)) resolved[k] = await box(sel, text).catch(() => null);
  clip.marks.push({ name, t: now(), wall: Date.now(), boxes: resolved });
  log(`  标记 ${name}`);
}
async function stopClip() {
  await sleep(600);
  await send("Page.stopScreencast");
  await sleep(300);
  const meta = { name: clip.name, width: VW * DPR, height: VH * DPR, css: { w: VW, h: VH, dpr: DPR }, frames: clip.frames, marks: clip.marks };
  fs.writeFileSync(path.join(clip.dir, "clip.json"), JSON.stringify(meta));
  log(`片段 ${clip.name}：${clip.frames.length} 帧，${clip.frames.at(-1)?.t.toFixed(1)}s`);
  clip = null;
}
async function shot(name) {
  const dir = path.join(OUT, "shots");
  fs.mkdirSync(dir, { recursive: true });
  const r = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(dir, `${name}.png`), Buffer.from(r.data, "base64"));
  log(`  截图 ${name}.png`);
}

// ---------------- 面板状态 ----------------
const currentId = () => evaluate("decodeURIComponent(location.hash.slice(1))");
async function turnBusy() {
  return evaluate(`fetch("/api/sessions/" + location.hash.slice(1)).then((r) => r.json()).then((d) => d.busy)`);
}
/** 画面外重置演示仓库：站会、子助手片段都要从"DAY-298 还没修"的起点讲 */
async function silentReset() {
  const r = await evaluate(`fetch("/api/demo/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then((r) => r.status)`);
  if (r !== 200) throw new Error(`重置演示仓库失败：HTTP ${r}`);
  log("  已在画面外重置演示仓库");
}
async function newSession() {
  await click(".btn.primary.block", "新对话");
  await sleep(500);
  await click(".popover .btn.primary", "开始对话");
  await waitFor(`location.hash.length > 3`);
  await sleep(700);
}
async function ask(text) {
  await type(".composer-input", text);
  await click(".send");
  await waitFor(`(async () => (await fetch("/api/sessions/" + location.hash.slice(1)).then((r) => r.json())).busy)()`, 10000);
}
/** 等这一轮跑完；途中出现写操作确认卡就停一下让观众看清，再点"同意执行" */
async function waitTurn({ timeout = 15 * 60e3, approve = true } = {}) {
  const end = Date.now() + timeout;
  let confirms = 0;
  while (Date.now() < end) {
    const card = await box(".confirm .btn.primary", "同意执行").catch(() => null);
    if (card && approve) {
      confirms++;
      await mark(`confirm-${confirms}`, { card: [".confirm"] });
      if (confirms === 1) await shot("confirm-card");
      await sleep(2200);
      await click(".confirm .btn.primary", "同意执行", 500);
      continue;
    }
    if (!(await turnBusy())) return confirms;
    await sleep(700);
  }
  throw new Error("这一轮超时没跑完");
}
async function showTrace(label) {
  await click(".tab", "决策轨迹");
  await sleep(300);
  await evaluate(`document.querySelector(".panel-scroll")?.scrollTo({ top: 0 })`);
  await sleep(800);
  await mark(`${label}-trace-top`, {
    skill: [".panel-scroll .tcard", "技能"], route: [".panel-scroll .tcard", "模型路由"], panel: [".panel"],
  });
  await shot(`${label}-trace`);
  await sleep(1500);
  await scrollIn(".panel-scroll", 700, 18, 110);
  await mark(`${label}-trace-mid`, { steps: [".panel-scroll .tcard", "执行过程"], panel: [".panel"] });
  await sleep(1500);
  await scrollIn(".panel-scroll", 900, 18, 110);
  await sleep(1400);
}

// ---------------- 片段 ----------------
const CLIPS = {
  async login() {
    await nav(LOGIN_URL);
    await waitFor(`!!document.querySelector(".login")`);
    await startClip("login");
    await sleep(800);
    await pointAt(".login input");
    await mark("login", { form: [".login"] });
    await shot("login");
    await sleep(2000);
    await stopClip();
  },
  async overview() {
    await nav(PANEL);
    await waitFor(`document.querySelectorAll(".service").length >= 5`);
    await sleep(1500);
    await startClip("overview");
    await sleep(1000);
    await mark("overview", { services: [".services"], workspace: [".workspace"], sidebar: [".sidebar"], empty: [".messages"] });
    await shot("overview");
    await pointAt(".services", undefined, 900);
    await sleep(1600);
    await pointAt(".workspace", undefined, 700);
    await sleep(1400);
    await pointAt(".btn.primary.block", "新对话", 700);
    await sleep(800);
    await stopClip();
  },
  async standup() {
    await nav(PANEL);
    await waitFor(`document.querySelectorAll(".service").length >= 5`);
    await silentReset();
    await nav(PANEL);
    await waitFor(`document.querySelectorAll(".service").length >= 5`);
    await startClip("standup");
    await newSession();
    await mark("session-ready", { composer: [".composer"] });
    await ask("待会开站会，帮我理一下昨天干了啥今天干啥");
    await mark("sent");
    await waitTurn();
    await mark("done", { reply: [".messages"] });
    await sleep(1800);
    await shot("standup-reply");
    await showTrace("standup");
    await stopClip();
  },
  async fix() {
    await nav(PANEL);
    await waitFor(`document.querySelectorAll(".service").length >= 5`);
    await startClip("fix");
    await click(".workspace .link.reset", "重置");   // 弹出的 confirm 对话框由下面的处理器自动确认
    await waitFor(`!!document.querySelector(".toast")`, 60000);
    await mark("reset", { workspace: [".workspace"] });
    await sleep(1500);
    await newSession();
    await ask("把 DAY-298 金额累加精度的 bug 修掉，记得补测试");
    await mark("sent");
    const n = await waitTurn({ timeout: 20 * 60e3 });
    log(`  确认了 ${n} 次写操作`);
    await mark("done", { reply: [".messages"] });
    await sleep(1800);
    await shot("fix-reply");
    await showTrace("fix");
    await click(".tab", "工作记忆");
    await sleep(1200);
    await mark("working", { panel: [".panel"] });
    await shot("fix-working");
    await sleep(2200);
    await stopClip();
  },
  async delegate() {
    await nav(PANEL);
    await waitFor(`document.querySelectorAll(".service").length >= 5`);
    await silentReset();
    await nav(PANEL);
    await waitFor(`document.querySelectorAll(".service").length >= 5`);
    await startClip("delegate");
    await newSession();
    await ask("用 delegate 同时派两个子助手：一个查清金额从命令行输入到写进文件经过哪些函数（给行号），另一个查 AGENTS.md 里有哪些约定还没在代码里落实。最后汇总成一段话。");
    await mark("sent");
    await waitTurn();
    await mark("done", { reply: [".messages"] });
    await sleep(1500);
    await click(".tab", "决策轨迹");
    await sleep(600);
    await evaluate(`document.querySelector(".panel-scroll")?.scrollTo({ top: 0 })`);
    await scrollIn(".panel-scroll", 500, 10, 110);
    await mark("subagents", { sub: [".step.sub"], panel: [".panel"] });
    await shot("delegate-trace");
    await sleep(1500);
    await evaluate(`document.querySelector(".sub-answer")?.setAttribute("open", "")`);
    await sleep(2500);
    await stopClip();
  },
  async models() {
    await nav(PANEL);
    await waitFor(`document.querySelectorAll(".service").length >= 5`);
    await startClip("models");
    await click(".side-link", "模型设置");
    await waitFor(`!!document.querySelector(".slot-row")`);
    await sleep(1200);
    await mark("models", { slots: [".slot-list"], providers: [".prov-list"], drawer: [".drawer"] });
    await shot("models");
    await pointAt(".slot-row", "难题", 700);
    await sleep(1500);
    await click(".set-title .btn", "添加");
    await sleep(1500);
    await mark("presets", { presets: [".preset-box"] });
    await shot("models-presets");
    await sleep(1500);
    await click(".preset-head .btn", "取消");
    await click(".prov-card", "阶跃");
    await sleep(1200);
    await mark("provider", { form: [".form"] });
    await shot("models-provider");
    await sleep(2000);
    await click(".back", "返回");
    await sleep(800);
    await stopClip();
  },
  async memory() {
    await nav(PANEL);
    await waitFor(`document.querySelectorAll(".service").length >= 5`);
    await startClip("memory");
    await click(".side-link", "长期记忆");
    await sleep(1400);
    await mark("memory", { drawer: [".drawer"] });
    await shot("memory");
    await sleep(1200);
    await click(".tab", "待确认");
    await sleep(1800);
    await stopClip();
  },
};

async function nav(url) {
  await send("Page.navigate", { url });
  await sleep(1200);
  await waitFor(`document.readyState === "complete"`);
}

try {
  let target;
  for (let i = 0; i < 40 && !target; i++) {
    await sleep(250);
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === "page"); } catch { /* 未就绪 */ }
  }
  if (!target) throw new Error("Edge 调试端口没起来");
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    else if (m.method && handlers.has(m.method)) handlers.get(m.method)(m.params);
  };
  handlers.set("Page.javascriptDialogOpening", () => send("Page.handleJavaScriptDialog", { accept: true }).catch(() => {}));
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: VW, height: VH, deviceScaleFactor: DPR, mobile: false });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] });
  await send("Page.addScriptToEvaluateOnNewDocument", { source: `addEventListener("DOMContentLoaded", () => ${CURSOR})` });
  const want = process.argv.slice(2);
  for (const name of want.length ? want : Object.keys(CLIPS)) {
    log(`开始录 ${name}`);
    const t = Date.now();
    await CLIPS[name]();
    log(`${name} 用时 ${((Date.now() - t) / 1000).toFixed(0)}s`);
  }
  ws.close();
} catch (err) {
  console.error(`[record] 失败：${err.message}`);
  if (clip) await stopClip().catch(() => {});
  process.exitCode = 1;
} finally {
  edge.kill();
}
