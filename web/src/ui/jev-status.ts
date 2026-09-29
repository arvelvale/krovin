import { state } from "../store";
import { h } from "./dom";

/** 工作台顶部的 JEV 状态：小人只跟随指针，不改变会话配置。 */
export function createJevStatus(): { el: HTMLElement; sync: () => void; dispose: () => void } {
  const label = h("span", { class: "jev-status-label" });
  const mascot = h("span", { class: "jev-mascot", attrs: { "aria-hidden": "true" } },
    h("span", { class: "jev-bean" },
      h("span", { class: "jev-bean-eye" }),
      h("span", { class: "jev-bean-eye" }),
      h("span", { class: "jev-bean-mouth" })));
  const el = h("span", { class: "jev-status", attrs: { role: "status", "aria-live": "polite" } }, mascot, label);
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let frame = 0;
  let pointerX = 0;
  let pointerY = 0;
  let lastPointerNod = -Infinity;
  let blinkTimer = 0;
  let blinkEndTimer = 0;

  const stopBlink = () => {
    window.clearTimeout(blinkTimer);
    window.clearTimeout(blinkEndTimer);
    blinkTimer = 0;
    blinkEndTimer = 0;
    el.classList.remove("blink");
  };
  const scheduleBlink = () => {
    if (blinkTimer || blinkEndTimer || !el.isConnected || !el.classList.contains("on") ||
        document.hidden || reducedMotion.matches) return;
    blinkTimer = window.setTimeout(() => {
      blinkTimer = 0;
      if (!el.isConnected || !el.classList.contains("on") || document.hidden || reducedMotion.matches) return;
      el.classList.add("blink");
      blinkEndTimer = window.setTimeout(() => {
        blinkEndTimer = 0;
        el.classList.remove("blink");
        scheduleBlink();
      }, 190);
    }, 1800 + Math.random() * 4200);
  };

  const nod = () => {
    if (!el.isConnected || reducedMotion.matches) return;
    el.classList.remove("nod");
    void mascot.offsetWidth;
    el.classList.add("nod");
  };
  const isComposerInput = (target: EventTarget | null) =>
    target instanceof HTMLTextAreaElement && target.matches(".composer-input");
  const onComposerPointerDown = (event: PointerEvent) => {
    if (event.button !== 0 || !isComposerInput(event.target)) return;
    lastPointerNod = performance.now();
    nod();
  };
  const onComposerFocus = (event: FocusEvent) => {
    if (isComposerInput(event.target) && performance.now() - lastPointerNod > 200) nod();
  };
  const onNodEnd = (event: AnimationEvent) => {
    if (event.target === mascot) el.classList.remove("nod");
  };

  const aim = () => {
    frame = 0;
    if (!el.isConnected || reducedMotion.matches || !el.classList.contains("on")) return;
    const rect = mascot.getBoundingClientRect();
    const dx = pointerX - (rect.left + rect.width / 2);
    const dy = pointerY - (rect.top + rect.height / 2);
    const distance = Math.hypot(dx, dy);
    const gazeX = distance ? dx / distance : 0;
    const gazeY = distance ? dy / distance : 0;
    const reach = Math.min(3, distance * 0.015);
    el.style.setProperty("--bean-x", `${gazeX * reach}px`);
    el.style.setProperty("--bean-y", `${gazeY * reach * 0.6}px`);
    el.style.setProperty("--bean-lean", `${gazeX * Math.min(13, distance * 0.065)}deg`);
    el.style.setProperty("--face-x", `${gazeX * Math.min(2, distance * 0.01)}px`);
    el.style.setProperty("--face-y", `${gazeY * Math.min(1.5, distance * 0.008)}px`);
  };
  const onPointerMove = (event: PointerEvent) => {
    if (!el.isConnected || reducedMotion.matches || !el.classList.contains("on")) return;
    pointerX = event.clientX;
    pointerY = event.clientY;
    if (!frame) frame = requestAnimationFrame(aim);
  };
  const reset = () => {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    for (const property of ["--bean-x", "--bean-y", "--bean-lean", "--face-x", "--face-y"]) {
      el.style.removeProperty(property);
    }
  };
  const onReducedMotionChange = () => {
    reset();
    el.classList.remove("nod");
    if (reducedMotion.matches) stopBlink();
    else scheduleBlink();
  };
  const onVisibilityChange = () => {
    if (document.hidden) stopBlink();
    else scheduleBlink();
  };
  window.addEventListener("pointermove", onPointerMove, { passive: true });
  document.addEventListener("pointerleave", reset);
  document.addEventListener("pointerdown", onComposerPointerDown);
  document.addEventListener("focusin", onComposerFocus);
  mascot.addEventListener("animationend", onNodEnd);
  reducedMotion.addEventListener("change", onReducedMotionChange);
  document.addEventListener("visibilitychange", onVisibilityChange);

  const sync = () => {
    const cur = state.current;
    const text = !cur ? (state.newSession.useJev ? "JEV 决策层" : "基线 · 无 JEV")
      : cur.useJev === true ? "JEV 决策层" : cur.useJev === false ? "基线 · 无 JEV" : "JEV 状态未知";
    label.textContent = text;
    el.title = text;
    const enabled = cur ? cur.useJev === true : state.newSession.useJev;
    el.classList.toggle("on", enabled);
    if (enabled) scheduleBlink();
    else {
      reset();
      stopBlink();
    }
  };

  return {
    el, sync,
    dispose: () => {
      window.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerleave", reset);
      document.removeEventListener("pointerdown", onComposerPointerDown);
      document.removeEventListener("focusin", onComposerFocus);
      mascot.removeEventListener("animationend", onNodEnd);
      reducedMotion.removeEventListener("change", onReducedMotionChange);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      stopBlink();
      reset();
    },
  };
}
