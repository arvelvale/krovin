import { Component, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import GlassSurface from "../components/GlassSurface.jsx";

type Surface = { host: HTMLElement; reactRoot: Root };

class SurfaceBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  render(): ReactNode {
    return this.state.failed ? null : this.props.children;
  }
}

/** Mounts the registry component as a visual layer; native form controls stay native. */
export function installGlassSurfaces(root: HTMLElement): { sync: () => void; dispose: () => void } {
  const surfaces = new Map<HTMLElement, Surface>();
  const transparency = matchMedia("(prefers-reduced-transparency: reduce)");
  const contrast = matchMedia("(prefers-contrast: more)");
  const forcedColors = matchMedia("(forced-colors: active)");

  function remove(element: HTMLElement, surface: Surface): void {
    surface.reactRoot.unmount();
    surface.host.remove();
    element.classList.remove("has-glass-surface");
    surfaces.delete(element);
  }

  function sync(): void {
    const disabled = transparency.matches || contrast.matches || forcedColors.matches;
    for (const [element, surface] of surfaces) {
      if (!root.contains(element) || disabled) remove(element, surface);
    }
    if (disabled) return;
    for (const element of root.querySelectorAll<HTMLElement>(".composer-box")) {
      if (surfaces.has(element)) continue;
      const host = document.createElement("div");
      host.className = "glass-surface-host";
      host.setAttribute("aria-hidden", "true");
      element.prepend(host);
      element.classList.add("has-glass-surface");
      const reactRoot = createRoot(host);
      reactRoot.render(
        <SurfaceBoundary>
          <GlassSurface
            width="100%"
            height="100%"
            borderRadius={24}
            className="spark-glass-surface"
            displace={15}
            distortionScale={-150}
            redOffset={5}
            greenOffset={15}
            blueOffset={25}
            brightness={60}
            opacity={0.8}
            mixBlendMode="screen"
          />
        </SurfaceBoundary>,
      );
      surfaces.set(element, { host, reactRoot });
    }
  }

  for (const query of [transparency, contrast, forcedColors]) query.addEventListener("change", sync);
  return { sync, dispose: () => {
    for (const query of [transparency, contrast, forcedColors]) query.removeEventListener("change", sync);
    for (const [element, surface] of surfaces) remove(element, surface);
  } };
}
