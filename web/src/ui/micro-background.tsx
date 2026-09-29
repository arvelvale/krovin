import { Component, useEffect, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import MicroSlats from "../components/MicroSlats.jsx";

class BackgroundBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  render(): ReactNode {
    return this.state.failed ? null : this.props.children;
  }
}

function Background(): ReactNode {
  const [disabled, setDisabled] = useState(false);
  useEffect(() => {
    const queries = [
      matchMedia("(prefers-reduced-transparency: reduce)"),
      matchMedia("(prefers-contrast: more)"),
      matchMedia("(forced-colors: active)"),
    ];
    const update = () => setDisabled(queries.some((query) => query.matches));
    update();
    queries.forEach((query) => query.addEventListener("change", update));
    return () => queries.forEach((query) => query.removeEventListener("change", update));
  }, []);

  if (disabled) return null;
  return <div className="micro-background-stage"><MicroSlats
    preset="swell"
    color="#A855F7"
    glintColor="#ffffff"
    backgroundColor="#000000"
    slatWidth={10}
    slatHeight={25}
    gap={3}
    roundness={0.75}
    interactive
    cursorStrength={1}
    cursorSize={40}
    swirl={0}
    trail={1.4}
    lean={0}
    intro
  /></div>;
}

export function installMicroBackground(): () => void {
  const host = document.createElement("div");
  host.className = "micro-background";
  host.setAttribute("aria-hidden", "true");
  document.body.prepend(host);
  const root = createRoot(host);
  root.render(<BackgroundBoundary><Background /></BackgroundBoundary>);
  return () => { root.unmount(); host.remove(); };
}
