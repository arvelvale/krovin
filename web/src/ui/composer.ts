import { ArrowUp, LoaderCircle, Mic, Square, Zap } from "lucide";
import { api, ApiError } from "../api";
import { sendTurn, setYolo, state, toast } from "../store";
import { MAX_SECONDS, Recorder, voiceSupported } from "../voice";
import { h, icon, mount } from "./dom";

type VoiceState = "idle" | "recording" | "transcribing";

/** 输入框只建一次（重绘会丢焦点和输入法状态），状态变化时调用 sync() */
export function createComposer(): { el: HTMLElement; sync: () => void } {
  let voice: VoiceState = "idle";
  let voiceDraft = false; // 当前文字来自语音识别（用户没清空之前都算语音输入）
  let recorder: Recorder | null = null;
  let timer = 0;
  let seconds = 0;

  const textarea = h("textarea", {
    class: "composer-input",
    attrs: { rows: "1", placeholder: "有什么想推进的？", "aria-label": "输入任务" },
  });
  const micBtn = h("button", { class: "icon-btn mic", attrs: { type: "button" } });
  const sendBtn = h("button", { class: "send", attrs: { type: "button", "aria-label": "发送" } }, icon(ArrowUp, 18));
  const jevLabel = h("span", { class: "composer-jev-label" });
  const jevStatus = h("span", { class: "composer-jev-status", attrs: { role: "status", "aria-live": "polite" } },
    h("span", { class: "composer-jev-dot", attrs: { "aria-hidden": "true" } }), jevLabel);
  const yoloBtn = h("button", {
    class: "composer-yolo", attrs: { type: "button", "aria-pressed": "false" },
    title: "全自动：写文件、提交、改 Linear 都不再等你确认（技能白名单、路径与沙箱限制、JEV 对外部写的拦截照旧）。也可以在输入框里发 /yolo 开关",
  }, icon(Zap, 12), h("span", null, "全自动"));
  yoloBtn.addEventListener("click", () => void setYolo(!state.current?.yolo));
  const tierSlot = h("div", { class: "rubber-slot rubber-slot--composer", attrs: { "data-rubber-segment": "composer-tier" } });
  const hint = h("div", { class: "composer-hint" });
  const level = h("span", { class: "level" });

  const autosize = () => {
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`;
  };

  const busy = () => !state.current?.live || !!state.current?.busy;

  async function submit() {
    const text = textarea.value.trim();
    if (text === "/yolo" && state.current?.live) {  // 斜杠命令：开关全自动，不当作任务发出去
      textarea.value = "";
      autosize();
      await setYolo(!state.current.yolo);
      sync();
      return;
    }
    if (!text || busy() || voice !== "idle") return;
    const ok = await sendTurn(text, voiceDraft ? "voice" : "text");
    if (ok) {
      textarea.value = "";
      voiceDraft = false;
      autosize();
    }
    sync();
  }

  async function toggleVoice() {
    const support = voiceSupported();
    if (!support.ok) {
      toast(support.reason!, "info");
      return;
    }
    if (voice === "idle") {
      recorder = new Recorder();
      try {
        await recorder.start((v) => level.style.setProperty("--lv", String(v)));
      } catch {
        recorder = null;
        toast("没拿到麦克风权限，可以在地址栏左边的网站设置里打开", "error");
        return;
      }
      voice = "recording";
      seconds = 0;
      timer = window.setInterval(() => {
        seconds += 1;
        if (seconds >= MAX_SECONDS) void toggleVoice();
        sync();
      }, 1000);
    } else if (voice === "recording" && recorder) {
      window.clearInterval(timer);
      voice = "transcribing";
      sync();
      try {
        const wav = await recorder.stop();
        const { text } = await api.asr(wav);
        if (text) {
          textarea.value = textarea.value ? `${textarea.value.trimEnd()} ${text}` : text;
          voiceDraft = true;
          autosize();
          textarea.focus();
        } else {
          toast("没听清，再说一次试试", "info");
        }
      } catch (err) {
        toast(err instanceof ApiError ? err.message : "识别失败，再试一次", "error");
      } finally {
        recorder = null;
        voice = "idle";
      }
    }
    sync();
  }

  textarea.addEventListener("input", () => {
    autosize();
    if (!textarea.value.trim()) voiceDraft = false;
    sync();
  });
  textarea.addEventListener("keydown", (e) => {
    // 输入法选词时的回车不能当发送
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      void submit();
    }
  });
  sendBtn.addEventListener("click", () => void submit());
  micBtn.addEventListener("click", () => void toggleVoice());
  window.addEventListener("spark:compose", (event) => {
    if (!state.current?.live) return;
    textarea.value = (event as CustomEvent<string>).detail;
    voiceDraft = false;
    autosize();
    sync();
    textarea.focus();
  });

  function sync() {
    const cur = state.current;
    const disabled = busy();
    textarea.disabled = !cur?.live;
    sendBtn.disabled = disabled || !textarea.value.trim() || voice !== "idle";
    micBtn.disabled = !cur?.live || voice === "transcribing";
    micBtn.classList.toggle("recording", voice === "recording");
    micBtn.title = voice === "recording" ? "再点一下结束录音" : "语音输入";
    micBtn.setAttribute("aria-label", micBtn.title);
    const jevText = !cur ? "JEV 未开始" : cur.useJev === true ? "JEV 决策层" : cur.useJev === false ? "基线 · 无 JEV" : "JEV 状态未知";
    jevLabel.textContent = jevText;
    jevStatus.title = jevText;
    jevStatus.classList.toggle("on", cur?.useJev === true);
    yoloBtn.disabled = !cur?.live;
    yoloBtn.classList.toggle("on", !!cur?.yolo);
    yoloBtn.setAttribute("aria-pressed", String(!!cur?.yolo));
    mount(micBtn, voice === "transcribing" ? icon(LoaderCircle, 16, "spin") : voice === "recording" ? icon(Square, 14) : icon(Mic, 16));
    if (!cur) hint.textContent = "先在左边新建一个对话";
    else if (!cur.live) hint.textContent = "这是历史会话，只能查看；新建对话才能继续";
    else if (voice === "recording") mount(hint, level, `正在听 ${seconds}s · 再点一下结束（最长 ${MAX_SECONDS}s）`);
    else if (voice === "transcribing") hint.textContent = "正在把语音转成文字…";
    else if (cur.busy) hint.textContent = "上一轮还在进行，稍等一下";
    else hint.textContent = "Enter 发送 · Shift + Enter 换行 · 每一步决策，都有迹可循";
  }

  const el = h("div", { class: "composer" },
    h("div", { class: "composer-box" }, textarea,
      h("div", { class: "composer-toolbar" },
        h("div", { class: "composer-controls" }, jevStatus, yoloBtn, tierSlot),
        h("div", { class: "composer-actions" }, micBtn, sendBtn))),
    hint);
  sync();
  return { el, sync };
}
