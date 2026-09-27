// 宣传片场景：纸面手绘 + 真实面板录屏。录屏片段按"配音第几句 ↔ 录屏里的标记"分段对齐，中间自动变速。
import { arrow, bar, box, C, check, circle, clamp01, highlight, stamp, stroke, text, type Ctx } from "../engine/ink";
import type { Sc } from "../engine/timeline";
import { chip, type Scene } from "../scenes/common";
import { clipEnd, clipMeta, frameAt, markBox, markT, type Rect } from "./clips";

// 录屏在纸上的位置（1440×810 的"屏幕"，正好是录制时的 CSS 视口）
const FX = 240, FY = 132, FW = 1440, FH = 810;

/** 场景内第 i 句开始（加上句长的 frac 比例）的时刻，单位秒，相对场景开头 */
const lt = (s: Sc, i: number, frac = 0) => {
  const l = s.scene.lines[Math.min(i, s.scene.lines.length - 1)];
  return l.start - s.scene.start + frac * (l.end - l.start);
};

type Key = [number, number]; // [场景时间, 片段时间]

/** 批注的显示窗口：第 i 句说到 frac 处出现，第 until 句开始时淡出（录屏滚动后旧坐标就不准了） */
const win = (s: Sc, i: number, frac: number, until?: number, len = 0.6) =>
  s.at(i, frac, len) * (until === undefined ? 1 : 1 - s.p(until, 0, 0.45));

function clipTime(keys: Key[], t: number): { ct: number; rate: number } {
  if (t <= keys[0][0]) return { ct: keys[0][1], rate: 0 };
  for (let i = 1; i < keys.length; i++) {
    const [a, ca] = keys[i - 1], [b, cb] = keys[i];
    if (t <= b) {
      const u = b > a ? (t - a) / (b - a) : 1;
      return { ct: ca + (cb - ca) * u, rate: b > a ? (cb - ca) / (b - a) : 0 };
    }
  }
  return { ct: keys[keys.length - 1][1], rate: 0 };
}

/** 录屏里的 CSS 坐标 → 纸面坐标 */
function place(clip: string, r: Rect, pad = 8): Rect {
  const m = clipMeta(clip)!;
  const k = FW / m.css.w;
  return { x: FX + r.x * k - pad, y: FY + r.y * k - pad, w: r.w * k + pad * 2, h: r.h * k + pad * 2 };
}

/** 在某个标记记下的元素外面画一圈手绘框，旁边写一句批注 */
function callout(ctx: Ctx, clip: string, mark: string, key: string, p: number,
  o: { color?: string; note?: string; side?: "left" | "right" | "below" | "above"; pad?: number; maxH?: number } = {}): void {
  if (p <= 0) return;
  const raw = markBox(clip, mark, key);
  if (!raw) return;
  const r = place(clip, { ...raw, h: Math.min(raw.h, o.maxH ?? raw.h) }, o.pad ?? 8);
  const color = o.color ?? C.red;
  box(ctx, r.x, r.y, r.w, r.h, p, { color, width: 3.6, seed: Math.round(r.x + r.y) }, undefined, 14);
  if (!o.note) return;
  const tp = clamp01(p * 1.6 - 0.5);
  const side = o.side ?? "left";
  ctx.save();
  ctx.font = `400 34px "LXGW WenKai", serif`;
  const w = ctx.measureText(o.note).width;
  ctx.restore();
  let x = side === "left" ? r.x - w - 36 : side === "right" ? r.x + r.w + 30 : r.x;
  let y = side === "below" ? r.y + r.h + 52 : side === "above" ? r.y - 22 : r.y + 42;
  x = Math.max(24, Math.min(1896 - w, x));
  y = Math.max(150, Math.min(1000, y));
  highlight(ctx, x - 8, y - 32, w + 16, 44, tp, "rgba(255, 250, 235, 0.92)", Math.round(x));
  text(ctx, o.note, x, y, { size: 34, color, p: tp });
}

function uiFrame(ctx: Ctx, clip: string, ct: number, p: number): void {
  const img = frameAt(clip, ct);
  ctx.save();
  ctx.globalAlpha *= clamp01(p * 1.3);
  ctx.shadowColor = "rgba(60, 45, 20, 0.28)";
  ctx.shadowBlur = 38;
  ctx.shadowOffsetY = 14;
  ctx.fillStyle = "#fff";
  ctx.fillRect(FX, FY, FW, FH);
  ctx.shadowColor = "transparent";
  if (img) ctx.drawImage(img, FX, FY, FW, FH);
  ctx.restore();
  box(ctx, FX - 6, FY - 6, FW + 12, FH + 12, p, { color: C.ink, width: 2.4, seed: 7, amp: 1.2 }, undefined, 8);
}

function speedBadge(ctx: Ctx, rate: number): void {
  if (rate < 1.8) return;
  const n = rate >= 10 ? Math.round(rate / 5) * 5 : Math.round(rate);
  stamp(ctx, `快进 ×${n}`, FX + FW - 120, FY + 58, 1, C.blue, 0.06, 34);
}

interface UiDef {
  id: string;
  clip: string;
  keys: (s: Sc) => Key[];
  notes?: (ctx: Ctx, s: Sc) => void;
}

function uiScene(d: UiDef): Scene & { clip: string; clipTimeAt: (s: Sc) => number } {
  const at = (s: Sc) => clipTime(d.keys(s), s.t);
  return {
    id: d.id,
    clip: d.clip,
    clipTimeAt: (s) => at(s).ct,
    draw(ctx, s) {
      if (!clipMeta(d.clip)) {
        text(ctx, `（缺少录屏片段 ${d.clip}）`, 960, 540, { size: 36, align: "center", color: C.red });
        return;
      }
      const { ct, rate } = at(s);
      uiFrame(ctx, d.clip, ct, s.p(0, 0, 0.7));
      speedBadge(ctx, rate);
      d.notes?.(ctx, s);
    },
  };
}

// ---------------- 纸面场景 ----------------
const open: Scene = {
  id: "open",
  draw(ctx, s) {
    const tp = s.p(0, 0, 1.4);
    highlight(ctx, 590, 300, 740, 70, s.p(0, 1.2, 0.8), C.hlGreen, 4);
    text(ctx, "Spark 开发流", 960, 360, { size: 120, align: "center", p: tp, weight: 700 });
    text(ctx, "跑在 NVIDIA DGX Spark 上的开发流助手", 960, 450, { size: 44, align: "center", p: s.at(0, 0.45, 1), color: C.soft });
    stamp(ctx, "DGX Spark", 1540, 250, s.at(0, 0.7, 0.5), C.green, 0.1, 32);
    // 第二句：三个来源 → 五步流水线
    const src = ["Linear issue", "会议纪要", "你说的话"];
    src.forEach((t, i) => chip(ctx, 150, 590 + i * 92, t, s.at(1, 0.02 + i * 0.07, 0.6), C.blue, "rgba(255,255,255,0.6)", 28));
    arrow(ctx, [420, 690], [520, 690], s.at(1, 0.25, 0.5), { color: C.soft, width: 2.6, seed: 3 });
    const steps = ["拆解", "计划", "开发", "写日志", "同步状态"];
    steps.forEach((t, i) => {
      const x = 560 + i * 262, p = s.at(1, 0.3 + i * 0.1, 0.7);
      box(ctx, x, 640, 200, 100, p, { width: 2.8, seed: 20 + i, color: i === 2 ? C.green : C.ink }, "rgba(255,255,255,0.55)", 12);
      text(ctx, t, x + 100, 703, { size: 38, align: "center", p: clamp01(p * 1.6 - 0.4) });
      if (i < steps.length - 1) arrow(ctx, [x + 206, 690], [x + 256, 690], s.at(1, 0.36 + i * 0.1, 0.4), { color: C.soft, width: 2.4, seed: 40 + i });
    });
  },
};

const idea: Scene = {
  id: "idea",
  draw(ctx, s) {
    text(ctx, "每一个「选哪个」", 960, 250, { size: 60, align: "center", p: s.p(0, 0, 0.9) });
    const cards = [
      ["用哪个技能", "standup-brief", 0.96],
      ["交给哪个模型", "难题：step-5", 0.68],
      ["这步要不要问你", "合理 0.46", 0.46],
      ["哪段上下文可以丢", "保留结果", 0.31],
    ] as const;
    cards.forEach(([title, sub, v], i) => {
      const x = 170 + i * 405, p = s.at(0, 0.18 + i * 0.13, 0.8);
      box(ctx, x, 330, 370, 290, p, { width: 2.8, seed: 50 + i }, "rgba(255,255,255,0.55)", 14);
      text(ctx, title, x + 185, 400, { size: 36, align: "center", p: clamp01(p * 1.5 - 0.3) });
      text(ctx, sub, x + 185, 460, { size: 26, align: "center", p: clamp01(p * 1.5 - 0.5), color: C.soft, font: "mono" });
      bar(ctx, x + 40, 510, 290, 34, v, clamp01(p * 1.4 - 0.4), v >= 0.5 ? C.green : C.amber, 60 + i);
      stroke(ctx, [[x + 40 + 290 * 0.5, 498], [x + 40 + 290 * 0.5, 556]], clamp01(p * 1.4 - 0.5), { color: C.red, width: 2.6, seed: 70 + i, double: false });
      text(ctx, v.toFixed(2), x + 185, 596, { size: 30, align: "center", p: clamp01(p * 1.5 - 0.6), font: "mono" });
    });
    stamp(ctx, "JEV", 1700, 250, s.p(0, 0.6, 0.5), C.green, -0.1, 44);
    // 第二句：阈值写在代码里 + 轨迹
    const q = s.p(1, 0, 1);
    text(ctx, "阈值（红线）写在代码里", 170, 710, { size: 38, p: q, color: C.red });
    box(ctx, 820, 670, 930, 250, s.p(1, 0.4, 0.9), { color: C.soft, width: 2.2, seed: 81 }, "rgba(255,255,255,0.5)", 8);
    const rows = ['skill.select   standup-brief 0.96', 'route.model    cloud  P(hard)=0.26 code=0.96', 'tool.gate      confirm in_scope=0.46', 'context.compress  t4 keep_result=0.31 → 截短'];
    rows.forEach((r, i) => text(ctx, r, 850, 725 + i * 50, { size: 26, font: "mono", p: s.at(1, 0.25 + i * 0.12, 0.8), color: C.ink }));
    text(ctx, "trace.jsonl", 1600, 900, { size: 24, font: "mono", color: C.soft, p: s.p(1, 0.6, 0.6) });
  },
};

// ---------------- 真实界面场景 ----------------
const panel = uiScene({
  id: "panel",
  clip: "overview",
  keys: (s) => [[0, 0], [s.dur - 0.4, clipEnd("overview")]],
  notes(ctx, s) {
    callout(ctx, "overview", "overview", "services", win(s, 0, 0.55, 1), { note: "五个服务的状态灯", side: "right", color: C.red });
    callout(ctx, "overview", "overview", "empty", win(s, 1, 0.55), { note: "中间对话 · 右边决策轨迹", side: "above", color: C.blue, pad: -60 });
  },
});

const standup = uiScene({
  id: "standup",
  clip: "standup",
  keys: (s) => {
    const c = "standup";
    return [
      [0, Math.max(0, markT(c, "session-ready") - 0.3)],
      [lt(s, 0, 0.95), markT(c, "sent")],
      [lt(s, 1, 1), markT(c, "done") - 3],
      [lt(s, 2, 0.4), markT(c, "done") + 0.6],
      [lt(s, 3, 0), markT(c, "standup-trace-top")],
      [s.dur - 0.3, clipEnd(c)],
    ];
  },
  notes(ctx, s) {
    callout(ctx, "standup", "standup-trace-top", "skill", win(s, 1, 0.35, 3), { note: "JEV 两级选技能", side: "left", maxH: 540 });
    callout(ctx, "standup", "standup-trace-top", "route", win(s, 1, 0.7, 3), { note: "日常任务 → 本地 Nemotron", side: "left", color: C.green });
  },
});

const fix = uiScene({
  id: "fix",
  clip: "fix",
  keys: (s) => {
    const c = "fix";
    const sent = markT(c, "sent"), conf = markT(c, "confirm-1"), done = markT(c, "done");
    return [
      [0, 0],
      [lt(s, 0, 0.95), sent],
      [lt(s, 1, 1), sent + 18],
      [lt(s, 3, 0.25), conf - 0.3],
      [lt(s, 3, 0.75), conf + 2.2],
      [lt(s, 4, 0), done - 1],
      [lt(s, 4, 0.45), markT(c, "fix-trace-top")],
      [s.dur - 0.3, markT(c, "fix-trace-mid") + 1.5],
    ];
  },
  notes(ctx, s) {
    callout(ctx, "fix", "fix-trace-top", "route", win(s, 1, 0.3, 2), { note: "要写代码且不简单 → step-5", side: "left", color: C.blue });
    callout(ctx, "fix", "confirm-1", "card", win(s, 3, 0.3, 4), { note: "合理 0.46 < 0.50：停下来问你", side: "below", color: C.red, pad: 4 });
    const q = s.at(4, 0.1, 0.8);
    if (q > 0) {
      const lines = ["17 步 · 2 分 46 秒", "测试 3 → 8 个，全部通过", "分支 agent/day-298-cents"];
      box(ctx, 40, 700, 610, 190, q, { color: C.green, width: 3, seed: 91 }, "rgba(255, 252, 240, 0.96)", 12);
      lines.forEach((l, i) => {
        check(ctx, 68, 736 + i * 52, 26, clamp01(q * 1.5 - 0.3 - i * 0.15));
        text(ctx, l, 110, 758 + i * 52, { size: 32, p: clamp01(q * 1.5 - 0.35 - i * 0.15), font: i === 2 ? "mono" : "hand" });
      });
    }
  },
});

const sub = uiScene({
  id: "sub",
  clip: "delegate",
  keys: (s) => {
    const c = "delegate";
    return [
      [0, 1.5],
      [lt(s, 0, 0.5), markT(c, "sent")],
      [lt(s, 0, 1), markT(c, "done") + 0.5],
      [lt(s, 1, 0.1), markT(c, "subagents") - 0.2],
      [s.dur - 0.3, clipEnd(c)],
    ];
  },
  notes(ctx, s) {
    callout(ctx, "delegate", "subagents", "sub", win(s, 1, 0.2), { note: "两个只读子助手，本地并行", side: "left", color: C.blue });
  },
});

const models = uiScene({
  id: "models",
  clip: "models",
  keys: (s) => {
    const c = "models";
    return [
      [0, 0],
      [lt(s, 0, 0.45), markT(c, "models") + 0.5],
      [lt(s, 0, 1), markT(c, "presets") + 1],
      [lt(s, 1, 0), markT(c, "provider") - 1.4],
      [s.dur - 0.3, clipEnd(c)],
    ];
  },
  notes(ctx, s) {
    callout(ctx, "models", "models", "slots", win(s, 0, 0.3, 1), { note: "主力 · 备用 · 难题", side: "left", color: C.green });
    callout(ctx, "models", "provider", "form", win(s, 1, 0.15), { note: "私有部署 = 能看到隐私记忆", side: "left", color: C.red, maxH: 430 });
  },
});

// ---------------- 纸面：数据与结尾 ----------------
const data: Scene = {
  id: "data",
  draw(ctx, s) {
    text(ctx, "技能选择 · 60 条任务", 180, 250, { size: 40, p: s.p(0, 0, 0.8) });
    const groups = [
      ["完全正确率", [0.817, 0.75], ["81.7%", "75.0%"], "越高越好", 0.1],
      ["硬凑一个技能", [0.333, 0.5], ["33.3%", "50.0%"], "越低越好", 0],
    ] as const;
    groups.forEach(([name, vals, labels, dir], g) => {
      const y = 320 + g * 250;
      const line = g === 0 ? 0 : 1;
      const p = s.at(line, g === 0 ? 0.3 : 0.05, 1);
      text(ctx, name, 180, y + 30, { size: 34, p });
      text(ctx, dir, 180 + 250, y + 30, { size: 24, p, color: C.soft });
      ["JEV", "主模型自己选"].forEach((arm, k) => {
        text(ctx, arm, 200, y + 92 + k * 66, { size: 26, p, color: C.soft });
        bar(ctx, 400, y + 64 + k * 66, 560, 42, vals[k], p, k ? C.faint : C.green, 100 + g * 2 + k);
        text(ctx, labels[k], 985, y + 94 + k * 66, { size: 28, p, font: "mono" });
      });
    });
    // 门控
    const q = s.at(1, 0.55, 1);
    box(ctx, 1260, 330, 480, 420, q, { width: 2.8, seed: 120, color: C.green }, "rgba(255,255,255,0.55)", 14);
    text(ctx, "写操作门控", 1500, 400, { size: 36, align: "center", p: q });
    text(ctx, "27 / 33", 1500, 560, { size: 110, align: "center", p: clamp01(q * 1.3 - 0.2), weight: 700, color: C.green });
    text(ctx, "条标定用例判对", 1500, 640, { size: 30, align: "center", p: clamp01(q * 1.3 - 0.4), color: C.soft });
    text(ctx, "* 节点上用真实 JEV 跑出，eval/ 可复现", 180, 900, { size: 28, p: s.p(1, 1.5, 0.8), color: C.soft });
  },
};

const outro: Scene = {
  id: "outro",
  draw(ctx, s) {
    // 左：登录页快照（拍立得）
    const img = frameAt("login", 1.2);
    const p = s.p(0, 0, 0.8);
    if (img && p > 0) {
      ctx.save();
      ctx.globalAlpha *= p;
      ctx.translate(520, 470);
      ctx.rotate(-0.035);
      ctx.shadowColor = "rgba(60,45,20,0.3)";
      ctx.shadowBlur = 30;
      ctx.fillStyle = "#fff";
      ctx.fillRect(-380, -240, 760, 500);
      ctx.shadowColor = "transparent";
      ctx.drawImage(img, -360, -222, 720, 405);
      ctx.restore();
      text(ctx, "浏览器打开 · 输入访问口令", 520, 690, { size: 30, align: "center", p: s.p(0, 0.5, 0.8), color: C.soft });
    }
    const tips = ["站会简报", "修 DAY-298", "派子助手", "拆一个 issue", "看最近提交"];
    text(ctx, "使用指南里的五句话", 1020, 250, { size: 40, p: s.p(0, 0.3, 0.8) });
    tips.forEach((t, i) => {
      const q = s.at(0, 0.35 + i * 0.1, 0.6);
      circle(ctx, 1045, 318 + i * 70, 20, q, { color: C.green, width: 2.4, seed: 130 + i });
      text(ctx, String(i + 1), 1045, 328 + i * 70, { size: 26, align: "center", p: q, font: "mono", color: C.green });
      text(ctx, t, 1085, 330 + i * 70, { size: 34, p: q });
    });
    const f = s.p(1, 0, 1.2);
    if (f > 0) {
      ctx.fillStyle = `rgba(243, 236, 221, ${0.97 * clamp01(f * 2)})`;
      ctx.fillRect(0, 0, 1920, 1080);
      highlight(ctx, 640, 430, 640, 64, s.p(1, 0.8, 0.8), C.hlGreen);
      text(ctx, "Spark 开发流", 960, 480, { size: 110, align: "center", p: f, weight: 700 });
      text(ctx, "每一个「选哪个」，都可以被看见、被度量", 960, 590, { size: 42, align: "center", p: s.p(1, 0.6, 1), color: C.soft });
      chip(ctx, 640, 660, "github.com/arvelvale/spark-devflow-agent", s.p(1, 1.2, 1), C.soft, "rgba(255,255,255,0.5)", 28);
    }
  },
};

export const promoScenes = [open, idea, panel, standup, fix, sub, models, data, outro];
export const uiScenes = [panel, standup, fix, sub, models];
