/**
 * Native DOM adaptations of React Bits Spotlight Card and Click Spark.
 * The workspace redraws its DOM frequently; one delegated controller keeps the
 * existing buttons, focus behavior and confirmation callbacks intact.
 */
type Burst = { x: number; y: number; started: number };

const ACTION = "button:not(:disabled), a[href], summary";
const SPOTLIGHT = ".suggest-item, .tcard, .confirm, .services, .login-card, .mem-card, .prov-card";

export function installInteractionMotion(root: HTMLElement): () => void {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const finePointer = matchMedia("(pointer: fine)");
  const bursts: Burst[] = [];
  const canvas = document.createElement("canvas");
  canvas.className = "motion-sparks";
  canvas.setAttribute("aria-hidden", "true");
  document.body.append(canvas);
  const context = canvas.getContext("2d");
  let sparkFrame = 0;

  // Clear inline transforms left by older hot-reloaded Magnet controls.
  for (const element of root.querySelectorAll<HTMLElement>("[data-motion]")) {
    element.style.translate = "";
    element.style.scale = "";
    delete element.dataset.motion;
  }

  function resizeCanvas(): void {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(innerWidth * dpr);
    canvas.height = Math.round(innerHeight * dpr);
    context?.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resizeCanvas();

  function find(target: EventTarget | null, selector: string): HTMLElement | null {
    if (!(target instanceof Element)) return null;
    const element = target.closest<HTMLElement>(selector);
    return element && root.contains(element) ? element : null;
  }

  function pointerMove(event: PointerEvent): void {
    if (reduced.matches || !finePointer.matches) return;
    const spot = find(event.target, SPOTLIGHT);
    if (spot) {
      const box = spot.getBoundingClientRect();
      spot.style.setProperty("--spot-x", `${event.clientX - box.left}px`);
      spot.style.setProperty("--spot-y", `${event.clientY - box.top}px`);
    }
  }

  function drawSparks(now: number): void {
    sparkFrame = 0;
    if (!context || reduced.matches) return;
    context.clearRect(0, 0, innerWidth, innerHeight);
    for (let index = bursts.length - 1; index >= 0; index--) {
      const burst = bursts[index];
      const progress = (now - burst.started) / 420;
      if (progress >= 1) { bursts.splice(index, 1); continue; }
      const eased = 1 - Math.pow(1 - Math.max(0, progress), 3);
      context.strokeStyle = `rgba(238,243,255,${(.56 * (1 - eased)).toFixed(3)})`;
      context.lineWidth = 1.5;
      for (let ray = 0; ray < 6; ray++) {
        const angle = ray * Math.PI / 3;
        const inner = 7 + eased * 15;
        const outer = inner + 8 * (1 - eased);
        context.beginPath();
        context.moveTo(burst.x + Math.cos(angle) * inner, burst.y + Math.sin(angle) * inner);
        context.lineTo(burst.x + Math.cos(angle) * outer, burst.y + Math.sin(angle) * outer);
        context.stroke();
      }
    }
    if (bursts.length) sparkFrame = requestAnimationFrame(drawSparks);
    else context.clearRect(0, 0, innerWidth, innerHeight);
  }

  function click(event: MouseEvent): void {
    const element = find(event.target, ACTION);
    if (!element || element.matches(":disabled") || reduced.matches) return;
    const box = element.getBoundingClientRect();
    const x = event.detail ? event.clientX : box.left + box.width / 2;
    const y = event.detail ? event.clientY : box.top + box.height / 2;
    bursts.push({ x, y, started: performance.now() });
    if (!sparkFrame) sparkFrame = requestAnimationFrame(drawSparks);
  }

  function motionPreference(): void {
    if (!reduced.matches) return;
    cancelAnimationFrame(sparkFrame);
    sparkFrame = 0;
    bursts.length = 0;
    context?.clearRect(0, 0, innerWidth, innerHeight);
  }

  root.addEventListener("pointermove", pointerMove, { passive: true });
  // Capture before a control's handler redraws (and detaches) its DOM node.
  root.addEventListener("click", click, true);
  window.addEventListener("resize", resizeCanvas);
  reduced.addEventListener("change", motionPreference);
  return () => {
    root.removeEventListener("pointermove", pointerMove);
    root.removeEventListener("click", click, true);
    window.removeEventListener("resize", resizeCanvas);
    reduced.removeEventListener("change", motionPreference);
    cancelAnimationFrame(sparkFrame);
    canvas.remove();
  };
}
