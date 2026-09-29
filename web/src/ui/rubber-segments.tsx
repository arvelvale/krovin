import { createRoot, type Root } from "react-dom/client";
import RubberSegment, { type RubberSegmentItem } from "../components/RubberSegment.jsx";
import { setMemoryTab, state, update } from "../store";
import { setup, type SetupTab } from "./setup";

type Segment = {
  host: HTMLElement;
  reactRoot: Root;
  value: string;
  pending: boolean;
  signature: string;
};

type Spec = {
  items: RubberSegmentItem[];
  value: string;
  label: string;
  size: "sm" | "md" | "lg";
  signature: string;
  change: (value: string, segment: Segment) => void;
};

function specFor(key: string, refresh: () => void): Spec | null {
  const pendingCount = state.current?.working?.todo.filter((item) => !item.done).length ?? 0;
  if (key === "setup-tabs") return {
    items: [
      { value: "workspace", label: "工作区" },
      { value: "vault", label: "笔记库" },
      { value: "integrations", label: "集成" },
    ],
    value: setup.currentTab(),
    label: "工作区与集成视图",
    size: "lg",
    signature: "",
    change: (value) => { setup.selectTab(value as SetupTab); refresh(); },
  };
  if (key === "right-tabs") return {
    items: [
      { value: "trace", label: "决策轨迹" },
      { value: "working", label: <>工作记忆{pendingCount > 0 && <span className="count">{pendingCount}</span>}</> },
    ],
    value: state.rightTab,
    label: "洞察视图",
    size: "md",
    signature: String(pendingCount),
    change: (value) => update((s) => { s.rightTab = value as "trace" | "working"; }),
  };
  if (key === "memory-tabs") return {
    items: [{ value: "active", label: "生效中" }, { value: "pending", label: "待确认" }],
    value: state.memoryTab,
    label: "长期记忆状态",
    size: "md",
    signature: "",
    change: (value) => void setMemoryTab(value as "active" | "pending"),
  };
  if (key === "new-session-tier") return {
    items: [{ value: "auto", label: "自动" }, { value: "local", label: "主力" }, { value: "cloud", label: "难题" }],
    value: state.newSession.tier,
    label: "新对话模型档位",
    size: "sm",
    signature: "",
    change: (value) => update((s) => { s.newSession.tier = value; }),
  };
  return null;
}

/** Keeps each React control mounted across the workbench's native DOM redraws. */
export function installRubberSegments(root: HTMLElement): { sync: () => void; dispose: () => void } {
  const segments = new Map<string, Segment>();

  function renderSegment(segment: Segment, spec: Spec): void {
    segment.reactRoot.render(
      <RubberSegment
        items={spec.items}
        defaultValue={spec.value}
        onChange={(value) => {
          segment.value = value;
          spec.change(value, segment);
        }}
        trackColor="#17171b"
        thumbColor="#e6e6e9"
        textColor="#f5f5f6"
        activeTextColor="#17171b"
        size={spec.size}
        radius={10}
        inset={3}
        equalSlots
        stretch={100}
        squash={3}
        speed={1}
        glide={75}
        draggable
        aria-label={spec.label}
      />,
    );
  }

  function sync(): void {
    const seen = new Set<string>();
    for (const slot of root.querySelectorAll<HTMLElement>("[data-rubber-segment]")) {
      const key = slot.dataset.rubberSegment!;
      const spec = specFor(key, sync);
      if (!spec) continue;
      seen.add(key);
      let segment = segments.get(key);
      if (!segment) {
        const host = document.createElement("div");
        host.className = "rubber-react-host";
        slot.append(host);
        segment = { host, reactRoot: createRoot(host), value: spec.value, pending: false, signature: spec.signature };
        segments.set(key, segment);
        renderSegment(segment, spec);
      } else {
        if (segment.host.parentElement !== slot) slot.append(segment.host);
        if (!segment.pending && segment.value !== spec.value) {
          // An external state change should jump to the authoritative selection.
          segment.reactRoot.unmount();
          segment.reactRoot = createRoot(segment.host);
          segment.value = spec.value;
          segment.signature = spec.signature;
          renderSegment(segment, spec);
        } else if (segment.signature !== spec.signature && !segment.pending) {
          segment.signature = spec.signature;
          renderSegment(segment, spec);
        }
      }
    }
    for (const [key, segment] of segments) {
      if (seen.has(key)) continue;
      segment.reactRoot.unmount();
      segment.host.remove();
      segments.delete(key);
    }
  }

  return { sync, dispose: () => {
    for (const segment of segments.values()) {
      segment.reactRoot.unmount();
      segment.host.remove();
    }
    segments.clear();
  } };
}
