// 全局状态 + SSE 同步。所有界面都从这里读，改完调用 update() 触发一次重绘。
import { api, ApiError } from "./api";
import type {
  ConfirmItem, MemoryItem, ReasoningItem, SessionDetail, SessionSummary, Status, TraceEvent, Turn, TurnDone, Working,
} from "./types";

export interface Current {
  id: string;
  live: boolean;
  busy: boolean;
  useJev: boolean | null;
  tier: string;
  bypass: boolean;
  yolo: boolean; // 全自动：原本要问你的确认改由 JEV 自动决定
  workspace: string | null; // 这个会话固定使用的工作区名字
  workspaceId: string | null; // 对应的工作区 id（产物卡片用它开预览）
  turns: Map<number, Turn>;
  working: Working | null;
  confirms: Map<string, ConfirmItem>;
  pendingInput: { text: string; source: "text" | "voice"; images: string[] } | null;
  stream: "none" | "open" | "reconnecting";
}

export interface AppState {
  authed: boolean | null; // null = 还在判断
  status: Status | null;
  sessions: SessionSummary[];
  current: Current | null;
  selectedTurn: number | null;
  followLatest: boolean;
  rightTab: "trace" | "working";
  memories: Map<string, MemoryItem>;
  memoryTab: "active" | "pending";
  memoryList: MemoryItem[];
  drawer: "memory" | "models" | "setup" | "preview" | null;
  newSessionOpen: boolean;
  newSession: { useJev: boolean; tier: string; yolo: boolean; bypass: boolean };
  mobileView: "chat" | "trace";
  sidebarOpen: boolean;
  landing: boolean;  // 登录后先落落地页（下载项目报告书），点「进入工作台」才进对话
  toast: { text: string; kind: "info" | "error" } | null;
}

export const state: AppState = {
  authed: null,
  status: null,
  sessions: [],
  current: null,
  selectedTurn: null,
  followLatest: true,
  rightTab: "trace",
  memories: new Map(),
  memoryTab: "active",
  memoryList: [],
  drawer: null,
  newSessionOpen: false,
  newSession: { useJev: true, tier: "auto", yolo: false, bypass: false },
  mobileView: "chat",
  sidebarOpen: false,
  landing: true,
  toast: null,
};

type Listener = () => void;
const listeners: Listener[] = [];
let scheduled = false;

export function subscribe(fn: Listener): void {
  listeners.push(fn);
}

export function update(mutate?: (s: AppState) => void): void {
  if (mutate) mutate(state);
  if (scheduled) return;
  scheduled = true;
  // 不用 requestAnimationFrame：页面在后台时 rAF 完全停掉，切回来之前界面会卡在旧状态；
  // 定时器在后台只是变慢，事件照样落到界面上
  window.setTimeout(() => {
    scheduled = false;
    for (const fn of listeners) fn();
  }, 16);
}

let toastTimer = 0;
export function toast(text: string, kind: "info" | "error" = "info"): void {
  window.clearTimeout(toastTimer);
  update((s) => (s.toast = { text, kind }));
  toastTimer = window.setTimeout(() => update((s) => (s.toast = null)), kind === "error" ? 6000 : 3000);
}

function fail(err: unknown): void {
  toast(err instanceof ApiError ? err.message : "出了点意外，稍后再试一次", "error");
}

// ---------------- 轮次拼装 ----------------

function turnOf(cur: Current, n: number): Turn {
  let t = cur.turns.get(n);
  if (!t) {
    t = { n, input: "", source: "text", events: [], reasoning: [] };
    cur.turns.set(n, t);
  }
  return t;
}

function applyEvent(cur: Current, ev: TraceEvent): void {
  if (ev.type === "mode.change") { cur.yolo = !!ev.data.yolo; cur.bypass = !!ev.data.bypass; }
  if (!ev.turn) return;
  const t = turnOf(cur, ev.turn);
  if (t.events.some((e) => e.seq === ev.seq)) return; // 重连后去重
  t.events.push(ev);
  if (ev.type === "turn.start") {
    t.input = String(ev.data.input ?? "");
    t.source = String(ev.data.source ?? "text");
    t.images = Array.isArray(ev.data.images) ? ev.data.images : [];
  } else if (ev.type === "turn.end" && !t.done) {
    t.done = {
      turn: ev.turn, stopped: ev.data.stopped, steps: ev.data.steps, tokens: ev.data.tokens,
      latency: ev.latency_ms !== undefined ? ev.latency_ms / 1000 : undefined,
    };
  }
}

function fromDetail(d: SessionDetail): Current {
  const cur: Current = {
    id: d.id, live: d.live, busy: d.busy, useJev: d.use_jev, tier: d.tier ?? "auto", yolo: !!d.yolo, bypass: !!d.bypass, workspace: d.workspace ?? null, workspaceId: d.workspace_id ?? null,
    turns: new Map(), working: d.working, confirms: new Map(), pendingInput: null, stream: "none",
  };
  for (const ev of d.events) applyEvent(cur, ev);
  for (const item of d.reasoning ?? []) {
    const t = turnOf(cur, item.turn);
    if (!t.reasoning.some((r) => r.step === item.step)) t.reasoning.push(item);
  }
  for (const m of d.messages) {
    const t = turnOf(cur, m.turn);
    if (m.role === "user") {
      if (!t.input) t.input = m.content;
      if (m.images?.length) t.images = m.images;
    }
    if (m.role === "assistant") t.reply = m.content;
  }
  for (const c of d.pending) cur.confirms.set(c.id, c);
  return cur;
}

export function sortedTurns(cur: Current | null): Turn[] {
  return cur ? [...cur.turns.values()].sort((a, b) => a.n - b.n) : [];
}

export function latestTurn(cur: Current | null): number | null {
  const ts = sortedTurns(cur);
  return ts.length ? ts[ts.length - 1].n : null;
}

// ---------------- SSE ----------------

let source: EventSource | null = null;

function closeStream(): void {
  source?.close();
  source = null;
}

function openStream(id: string): void {
  closeStream();
  const es = new EventSource(api.streamUrl(id));
  source = es;
  let wasDown = false;
  const mine = () => state.current?.id === id && source === es;
  es.onopen = () => {
    if (!mine()) return;
    update((s) => s.current && (s.current.stream = "open"));
    if (wasDown) void resync(id); // 断线期间可能漏事件，重新拉一次全量
    wasDown = false;
  };
  es.onerror = () => {
    if (!mine()) return;
    wasDown = true;
    update((s) => s.current && (s.current.stream = "reconnecting"));
    void resync(id); // 后端重启后旧 SSE 会返回 404，不能只等 onopen。
  };
  es.addEventListener("trace", (e) => {
    if (!mine()) return;
    const ev = JSON.parse((e as MessageEvent).data) as TraceEvent;
    update((s) => {
      const cur = s.current!;
      if (ev.type === "turn.start") cur.pendingInput = null;
      applyEvent(cur, ev);
      if (s.followLatest) s.selectedTurn = latestTurn(cur);
    });
    if (ev.type === "memory.recall" || ev.type === "memory.write") void refreshMemories();
  });
  es.addEventListener("reasoning", (e) => {
    if (!mine()) return;
    const item = JSON.parse((e as MessageEvent).data) as ReasoningItem;
    update((s) => {
      const t = turnOf(s.current!, item.turn);
      if (!t.reasoning.some((r) => r.step === item.step)) t.reasoning.push(item);
    });
  });
  es.addEventListener("confirm", (e) => {
    if (!mine()) return;
    const item = JSON.parse((e as MessageEvent).data) as ConfirmItem;
    update((s) => s.current!.confirms.set(item.id, item));
  });
  es.addEventListener("confirm_resolved", (e) => {
    if (!mine()) return;
    const r = JSON.parse((e as MessageEvent).data) as { id: string; approve: boolean; timeout: boolean };
    update((s) => {
      const c = s.current!.confirms.get(r.id);
      if (c) c.resolved = { approve: r.approve, timeout: r.timeout };
    });
  });
  es.addEventListener("working", (e) => {
    if (!mine()) return;
    const w = JSON.parse((e as MessageEvent).data) as Working;
    update((s) => (s.current!.working = w));
  });
  es.addEventListener("turn_done", (e) => {
    if (!mine()) return;
    const d = JSON.parse((e as MessageEvent).data) as TurnDone;
    update((s) => {
      const cur = s.current!;
      const t = turnOf(cur, d.turn);
      t.done = { ...t.done, ...d };
      t.reply = d.reply ?? (d.error ? `这一轮出错了：${d.error}` : t.reply);
      cur.busy = false;
      cur.pendingInput = null;
    });
    void loadSessions();
  });
}

async function resync(id: string): Promise<void> {
  try {
    const d = await api.session(id);
    update((s) => {
      if (s.current?.id !== id) return;
      const fresh = fromDetail(d);
      fresh.stream = s.current.stream;
      fresh.pendingInput = s.current.pendingInput;
      s.current = fresh;
    });
    if (!d.live && state.current?.id === id) closeStream();
  } catch (err) {
    fail(err);
  }
}

// ---------------- 动作 ----------------

export async function checkAuth(): Promise<void> {
  try {
    const status = await api.status();
    update((s) => {
      s.authed = true;
      s.status = status;
    });
    await Promise.all([loadSessions(), refreshMemories()]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) update((s) => (s.authed = false));
    else {
      update((s) => (s.authed = false));
      fail(err);
    }
  }
}

export async function login(token: string): Promise<string | null> {
  try {
    await api.login(token.trim());
    await checkAuth();
    return null;
  } catch (err) {
    return err instanceof ApiError ? err.message : "登录失败";
  }
}

export async function logout(): Promise<void> {
  closeStream();
  try {
    await api.logout();
  } finally {
    update((s) => {
      s.authed = false;
      s.current = null;
      s.landing = true;  // 下次登录还是先回落地页
    });
  }
}

/** 落地页 → 工作台 */
export function enterWorkspace(): void {
  update((s) => (s.landing = false));
}

export async function loadStatus(): Promise<void> {
  try {
    const status = await api.status();
    update((s) => (s.status = status));
  } catch (err) {
    fail(err);
  }
}

export async function loadSessions(): Promise<void> {
  try {
    const list = await api.sessions();
    update((s) => (s.sessions = list));
  } catch (err) {
    fail(err);
  }
}

let memoryRefreshGeneration = 0;

export async function refreshMemories(): Promise<void> {
  const generation = ++memoryRefreshGeneration;
  try {
    const [active, pending] = await Promise.all([api.memory("active"), api.memory("pending")]);
    if (generation !== memoryRefreshGeneration) return;
    update((s) => {
      s.memories = new Map([...active, ...pending].map((m) => [m.id, m]));
      s.memoryList = s.memoryTab === "active" ? active : pending;
    });
  } catch {
    /* 记忆列表只是辅助信息，拉不到不打扰用户 */
  }
}

export async function openSession(id: string): Promise<void> {
  try {
    const d = await api.session(id);
    const cur = fromDetail(d);
    update((s) => {
      s.current = cur;
      s.followLatest = true;
      s.selectedTurn = latestTurn(cur);
      s.sidebarOpen = false;
      s.mobileView = "chat";
    });
    history.replaceState(null, "", `#${id}`);
    if (d.live) openStream(id);
    else closeStream();
  } catch (err) {
    fail(err);
  }
}

export async function createSession(): Promise<void> {
  try {
    const { id } = await api.createSession(state.newSession.useJev, state.newSession.tier, state.newSession.yolo, state.newSession.bypass);
    update((s) => (s.newSessionOpen = false));
    await openSession(id);
    await loadSessions();
  } catch (err) {
    fail(err);
  }
}

export async function sendTurn(text: string, source: "text" | "voice", files: File[] = []): Promise<boolean> {
  const cur = state.current;
  if (!cur) {
    toast("请先选择一个对话", "info");
    return false;
  }
  if (!cur.live) {
    try {
      await api.resumeSession(cur.id);
      await openSession(cur.id);
    } catch (err) {
      fail(err);
      return false;
    }
  }
  const images: string[] = [];
  try {
    for (const file of files) images.push((await api.uploadImage(cur.id, file)).id);
  } catch (err) {
    fail(err);
    return false;
  }
  update((s) => {
    s.current!.busy = true;
    s.current!.pendingInput = { text: text || "请查看我发送的图片。", source,
      images: images.map((imageId) => api.imageUrl(cur.id, imageId)) };
    s.followLatest = true;
  });
  try {
    await api.turn(cur.id, text, source, images);
    return true;
  } catch (err) {
    update((s) => {
      if (s.current) {
        s.current.busy = false;
        s.current.pendingInput = null;
      }
    });
    fail(err);
    return false;
  }
}

export async function answerConfirm(confirmId: string, approve: boolean): Promise<void> {
  const cur = state.current;
  if (!cur) return;
  try {
    await api.confirm(cur.id, confirmId, approve);
  } catch (err) {
    fail(err);
  }
}

/** 点「停止」：告诉内核在这一步边界收尾。busy 等 turn_done 事件自然清掉，不本地抢拍 */
export async function stopTurn(): Promise<void> {
  const cur = state.current;
  if (!cur?.busy) return;
  try {
    const r = await api.stop(cur.id);
    if (r.stopped) toast("收到，正在停下来");
  } catch (err) {
    fail(err);
  }
}

/** 输入框下面的工作空间选择器：设为当前；已经有对话时顺手新开一个（当前对话固定在原来的工作区里，不动它） */
export async function useWorkspace(id: string, name: string): Promise<void> {
  try {
    await api.activateWorkspace(id);
    await loadStatus();
    if (state.current) await createSession();
    toast(`已切换到「${name}」`);
  } catch (err) {
    fail(err);
  }
}

export async function renameSession(id: string, title: string): Promise<void> {
  try {
    await api.renameSession(id, title);
    await loadSessions();
  } catch (err) {
    fail(err);
  }
}

export async function deleteSession(id: string, deleteWorkspace?: boolean): Promise<void> {
  try {
    const result = await api.deleteSession(id, deleteWorkspace);
    if (state.current?.id === id) {
      closeStream();
      history.replaceState(null, "", location.pathname);
      update((s) => { s.current = null; s.selectedTurn = null; });
    }
    await loadSessions();
    await loadStatus();
    toast(result.workspace_deleted ? "会话、专属沙箱和工作区已清理" : "会话及专属沙箱已清理，工作区保留");
  } catch (err) {
    fail(err);
  }
}

export async function setYolo(on: boolean, bypass = false): Promise<void> {
  const cur = state.current;
  if (!cur?.live) return;
  try {
    const r = await api.setYolo(cur.id, on, bypass);
    update((s) => { if (s.current) { s.current.yolo = r.yolo; s.current.bypass = r.bypass; } });
    toast(r.bypass ? "Bypass 已开启：执行门控与逐次确认已跳过" : r.yolo ? "全自动已开启：由 JEV 自动决定，不再打扰你" : "全自动已关闭：需要时会问你", "info");
  } catch (err) {
    fail(err);
  }
}

export async function setTier(tier: string): Promise<void> {
  const cur = state.current;
  if (!cur?.live) return;
  try {
    const r = await api.setTier(cur.id, tier);
    update((s) => s.current && (s.current.tier = r.tier));
  } catch (err) {
    fail(err);
  }
}

export async function setMemoryTab(tab: "active" | "pending"): Promise<void> {
  update((s) => {
    s.memoryTab = tab;
    // Switch the visible list in the same render as the tab, before the refresh returns.
    s.memoryList = [...s.memories.values()].filter((m) => m.status === tab);
  });
  await refreshMemories();
}

export async function approveMemory(id: string): Promise<void> {
  try {
    await api.approveMemory(id);
    toast("记下了，之后的对话会用上它");
    await refreshMemories();
  } catch (err) {
    fail(err);
  }
}

export async function forgetMemory(id: string): Promise<void> {
  try {
    await api.forgetMemory(id);
    toast("已经忘掉这条了");
    await refreshMemories();
  } catch (err) {
    fail(err);
  }
}

export function selectTurn(n: number): void {
  update((s) => {
    s.selectedTurn = n;
    s.followLatest = n === latestTurn(s.current);
    s.rightTab = "trace";
    s.mobileView = window.innerWidth < 1100 ? "trace" : s.mobileView;
  });
}

window.addEventListener("dgx:unauthorized", () => {
  closeStream();
  update((s) => (s.authed = false));
});

export async function resetDemo(): Promise<void> {
  if (!window.confirm("把演示仓库恢复到初始状态？之前的改动和提交都会清掉（只影响演示沙盒）。")) return;
  try {
    const r = await api.resetDemo();
    toast(`演示仓库 ${r.workspace} 已恢复到初始状态`);
    void loadStatus();
  } catch (err) {
    toast(err instanceof ApiError ? err.message : "重置失败，稍后再试一次", "error");
  }
}
