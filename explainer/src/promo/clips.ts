// 真实面板录屏（scripts/record.mjs 录的 public/rec/<片段>/）：按片段时间取帧，按需加载。
export interface Rect { x: number; y: number; w: number; h: number }
export interface Mark { name: string; t: number; boxes: Record<string, Rect | null> }
export interface ClipMeta {
  name: string;
  width: number;
  height: number;
  css: { w: number; h: number; dpr: number };
  frames: { f: string; t: number }[];
  marks: Mark[];
}

const meta = new Map<string, ClipMeta>();
const images = new Map<string, HTMLImageElement>();
const loading = new Map<string, Promise<void>>();
const order: string[] = []; // 简单 LRU：导出 4 分钟视频会碰到上万帧，不能全留在内存里
const MAX_IMAGES = 400;

export async function loadClips(names: string[]): Promise<void> {
  await Promise.all(names.map(async (n) => {
    if (meta.has(n)) return;
    const r = await fetch(`rec/${n}/clip.json`);
    if (!r.ok) throw new Error(`缺少录屏片段 ${n}（先跑 node scripts/record.mjs ${n}）`);
    meta.set(n, await r.json());
  }));
}

export const clipMeta = (name: string): ClipMeta | undefined => meta.get(name);
export const clipEnd = (name: string): number => meta.get(name)?.frames.at(-1)?.t ?? 0;

/** 片段里某个标记的时间；找不到就报错（比悄悄对错位好查） */
export function markT(name: string, mark: string, nth = 0): number {
  const m = meta.get(name)?.marks.filter((x) => x.name === mark)[nth];
  if (!m) throw new Error(`片段 ${name} 里没有标记 ${mark}`);
  return m.t;
}
export function markBox(name: string, mark: string, key: string): Rect | null {
  return meta.get(name)?.marks.find((x) => x.name === mark)?.boxes[key] ?? null;
}

function frameIndex(m: ClipMeta, t: number): number {
  const fr = m.frames;
  let lo = 0, hi = fr.length - 1;
  if (t <= fr[0].t) return 0;
  if (t >= fr[hi].t) return hi;
  while (lo < hi) { // 最后一个 t <= 目标时间的帧
    const mid = (lo + hi + 1) >> 1;
    if (fr[mid].t <= t) lo = mid; else hi = mid - 1;
  }
  return lo;
}

function key(name: string, i: number): string {
  return `${name}/${meta.get(name)!.frames[i].f}`;
}

function load(name: string, i: number): Promise<void> {
  const k = key(name, i);
  if (images.has(k)) return Promise.resolve();
  const inflight = loading.get(k);
  if (inflight) return inflight;
  const p = new Promise<void>((resolve) => {
    const img = new Image();
    img.onload = () => {
      images.set(k, img);
      order.push(k);
      while (order.length > MAX_IMAGES) images.delete(order.shift()!);
      loading.delete(k);
      resolve();
    };
    img.onerror = () => { loading.delete(k); resolve(); };
    img.src = `rec/${k}`;
  });
  loading.set(k, p);
  return p;
}

/** 确保片段在时间 t 的那一帧已解码（导出时 await，播放时只预取） */
export function ensure(name: string, t: number): Promise<void> {
  const m = meta.get(name);
  if (!m) return Promise.resolve();
  return load(name, frameIndex(m, t));
}

/** 取时间 t 的帧；还没加载好就往前找最近一张已加载的，避免闪空白 */
export function frameAt(name: string, t: number): HTMLImageElement | null {
  const m = meta.get(name);
  if (!m) return null;
  for (let i = frameIndex(m, t); i >= 0; i--) {
    const img = images.get(key(name, i));
    if (img) return img;
  }
  return null;
}
