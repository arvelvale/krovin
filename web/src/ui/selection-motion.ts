type Frame = {
  node: HTMLElement;
  x: number; y: number; w: number; h: number;
  vx: number; vy: number; vw: number; vh: number;
  tx: number; ty: number; tw: number; th: number;
};

/** Keeps a single selection rectangle moving across the workspace's full DOM redraws. */
export function installSelectionMotion(root: HTMLElement): { sync: () => void; dispose: () => void } {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const frames = new Map<string, Frame>();
  let animation = 0;
  let lastTime = 0;

  // Critically damped spring: about 90% of the travel in 0.13s, without a visible bounce.
  // Position and velocity stay continuous when a second selection interrupts the first.
  const frequency = 30;

  function place(frame: Frame): void {
    frame.node.style.left = `${frame.x}px`;
    frame.node.style.top = `${frame.y}px`;
    frame.node.style.width = `${frame.w}px`;
    frame.node.style.height = `${frame.h}px`;
  }

  function settle(frame: Frame, dt: number): boolean {
    const spring = (value: number, velocity: number, target: number): [number, number, boolean] => {
      const displacement = value - target;
      const carry = velocity + frequency * displacement;
      const decay = Math.exp(-frequency * dt);
      const next = target + (displacement + carry * dt) * decay;
      const nextVelocity = (velocity - frequency * carry * dt) * decay;
      return [next, nextVelocity, Math.abs(next - target) > .4 || Math.abs(nextVelocity) > 3];
    };
    const [x, vx, mx] = spring(frame.x, frame.vx, frame.tx);
    const [y, vy, my] = spring(frame.y, frame.vy, frame.ty);
    const [w, vw, mw] = spring(frame.w, frame.vw, frame.tw);
    const [h, vh, mh] = spring(frame.h, frame.vh, frame.th);
    frame.x = x; frame.vx = vx;
    frame.y = y; frame.vy = vy;
    frame.w = w; frame.vw = vw;
    frame.h = h; frame.vh = vh;
    const moving = mx || my || mw || mh;
    if (!moving) {
      frame.x = frame.tx; frame.y = frame.ty;
      frame.w = frame.tw; frame.h = frame.th;
      frame.vx = frame.vy = frame.vw = frame.vh = 0;
    }
    place(frame);
    return moving;
  }

  function tick(now: number): void {
    animation = 0;
    const dt = Math.min((now - lastTime) / 1000, 1 / 30);
    lastTime = now;
    let moving = false;
    for (const frame of frames.values()) {
      if (!frame.node.isConnected) continue;
      moving = settle(frame, dt) || moving;
    }
    if (moving) animation = requestAnimationFrame(tick);
  }

  function wake(): void {
    if (!animation && !reduced.matches) {
      lastTime = performance.now();
      animation = requestAnimationFrame(tick);
    }
  }

  function sync(): void {
    const seen = new Set<string>();
    for (const container of root.querySelectorAll<HTMLElement>("[data-selection-group]")) {
      const group = container.dataset.selectionGroup!;
      seen.add(group);
      const selected = container.querySelector<HTMLElement>("[data-selection-key].active, [data-selection-key].on");
      if (!selected) {
        // A newly created session can become current before its list entry arrives.
        const previous = frames.get(group);
        if (previous && previous.node.parentElement !== container) {
          container.prepend(previous.node);
          place(previous);
        }
        continue;
      }
      const box = selected.getBoundingClientRect();
      const parent = container.getBoundingClientRect();
      const x = box.left - parent.left - container.clientLeft + container.scrollLeft;
      const y = box.top - parent.top - container.clientTop + container.scrollTop;
      const { width: w, height: h } = box;
      let frame = frames.get(group);
      if (!frame) {
        const node = document.createElement("div");
        node.className = "selection-frame";
        node.setAttribute("aria-hidden", "true");
        frame = { node, x, y, w, h,
          vx: 0, vy: 0, vw: 0, vh: 0, tx: x, ty: y, tw: w, th: h };
        frames.set(group, frame);
      }
      frame.tx = x; frame.ty = y; frame.tw = w; frame.th = h;
      if (frame.node.parentElement !== container) container.prepend(frame.node);
      if (reduced.matches) {
        frame.x = x; frame.y = y; frame.w = w; frame.h = h;
        frame.vx = frame.vy = frame.vw = frame.vh = 0;
      }
      place(frame);
      if (Math.abs(frame.x - x) + Math.abs(frame.y - y) + Math.abs(frame.w - w) + Math.abs(frame.h - h) > .1) wake();
    }
    for (const [group, frame] of frames) {
      if (seen.has(group)) continue;
      frame.node.remove();
      frames.delete(group);
    }
  }

  function preference(): void {
    if (reduced.matches) {
      cancelAnimationFrame(animation);
      animation = 0;
    }
    sync();
  }

  window.addEventListener("resize", sync);
  reduced.addEventListener("change", preference);
  return { sync, dispose: () => {
    window.removeEventListener("resize", sync);
    reduced.removeEventListener("change", preference);
    cancelAnimationFrame(animation);
    for (const frame of frames.values()) frame.node.remove();
    frames.clear();
  } };
}
