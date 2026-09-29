import { ArrowUp, LoaderCircle, Mic, Square, X } from "lucide";
import { api, ApiError } from "../api";
import { createSession, sendTurn, setYolo, state, stopTurn, toast } from "../store";
import { MAX_SECONDS, Recorder, voiceSupported } from "../voice";
import { createComposerPickers } from "./composer-pickers";
import { h, icon, mount } from "./dom";

type VoiceState = "idle" | "recording" | "transcribing";
type DraftImage = { id: number; file: File; url: string };

/** 输入框只建一次（重绘会丢焦点和输入法状态），状态变化时调用 sync() */
export function createComposer(): { el: HTMLElement; sync: () => void } {
  let voice: VoiceState = "idle";
  let voiceDraft = false; // 当前文字来自语音识别（用户没清空之前都算语音输入）
  let recorder: Recorder | null = null;
  let timer = 0;
  let seconds = 0;
  let nextImageId = 0;
  let sending = false;
  const images: DraftImage[] = [];

  const imageInput = h("input", { class: "composer-image-input", attrs: {
    type: "file", accept: "image/png,image/jpeg,image/gif,image/webp", multiple: true, "aria-label": "选择图片",
  } });
  const imagePreviews = h("div", { class: "composer-attachments", attrs: { "aria-live": "polite" } });

  const textarea = h("textarea", {
    class: "composer-input",
    attrs: { rows: "1", placeholder: "有什么想推进的？", "aria-label": "输入任务" },
  });
  const micBtn = h("button", { class: "icon-btn mic", attrs: { type: "button" } });
  const sendBtn = h("button", { class: "send", attrs: { type: "button", "aria-label": "发送" } }, icon(ArrowUp, 18));
  const pickers = createComposerPickers(() => imageInput.click());
  const hint = h("div", { class: "composer-hint" });
  const level = h("span", { class: "level" });

  const autosize = () => {
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`;
  };

  const renderImages = () => {
    mount(imagePreviews, images.length > 0 && [
      h("div", { class: "composer-image-list" }, images.map(({ id, file, url }) =>
        h("div", { class: "composer-image" },
          h("img", { attrs: { src: url, alt: file.name } }),
          h("button", { class: "composer-image-remove", attrs: { type: "button", "aria-label": `移除图片 ${file.name}` },
            onclick: () => {
              const index = images.findIndex((image) => image.id === id);
              if (index < 0) return;
              URL.revokeObjectURL(images[index].url);
              images.splice(index, 1);
              renderImages();
              sync();
            } }, icon(X, 12))))),
      h("span", { class: "composer-image-note" }, "最多 6 张，每张不超过 8 MB"),
    ]);
  };

  function addImages(selected: File[]) {
    if (sending) return;
    const valid = selected.filter((file) => ["image/png", "image/jpeg", "image/gif", "image/webp"].includes(file.type) && file.size <= 8 * 1024 * 1024);
    const available = Math.max(0, 6 - images.length);
    for (const file of valid.slice(0, available)) images.push({ id: ++nextImageId, file, url: URL.createObjectURL(file) });
    if (valid.length < selected.length) toast("只支持 8 MB 以内的 PNG、JPEG、GIF 或 WebP 图片", "info");
    if (valid.length > available) toast("最多上传 6 张图片", "info");
    renderImages();
    sync();
  }

  imageInput.addEventListener("change", () => {
    addImages(Array.from(imageInput.files ?? []));
    imageInput.value = "";
  });
  textarea.addEventListener("paste", (event: ClipboardEvent) => {
    const files = Array.from(event.clipboardData?.items ?? [])
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item) => item.getAsFile()).filter((file): file is File => file !== null);
    if (!files.length) return; // 普通文本粘贴保持浏览器原有行为
    event.preventDefault();
    addImages(files);
  });

  // 欢迎页发送时新建；历史会话发送时恢复原会话。
  const busy = () => !!state.current?.busy;

  const currentLive = () => !!state.current?.live;

  async function submit() {
    const text = textarea.value.trim();
    if (text === "/yolo" && state.current?.live) {  // 斜杠命令：开关全自动，不当作任务发出去
      textarea.value = "";
      autosize();
      await setYolo(!state.current.yolo);
      sync();
      return;
    }
    if ((!text && !images.length) || busy() || sending || voice !== "idle") return;
    sending = true;
    sync();
    try {
      if (!state.current) {
        await createSession();
        if (!currentLive()) return;
      }
      const ok = await sendTurn(text, voiceDraft ? "voice" : "text", images.map((image) => image.file));
      if (ok) {
        textarea.value = "";
        voiceDraft = false;
        for (const image of images) URL.revokeObjectURL(image.url);
        images.length = 0;
        renderImages();
        autosize();
      }
    } finally {
      sending = false;
      sync();
    }
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
  sendBtn.addEventListener("click", () => {
    // 运行中这个键变成「停止」（Claude Desktop 的方形键）：点了就在步边界收尾
    if (busy()) void stopTurn();
    else void submit();
  });
  micBtn.addEventListener("click", () => void toggleVoice());
  window.addEventListener("spark:add-image", () => imageInput.click());
  window.addEventListener("spark:compose", (event) => {
    if (!state.current) return;
    textarea.value = (event as CustomEvent<string>).detail;
    voiceDraft = false;
    autosize();
    sync();
    textarea.focus();
  });

  function sync() {
    const cur = state.current;
    const running = busy();
    textarea.disabled = false;
    sendBtn.disabled = !running && (sending || (!textarea.value.trim() && !images.length) || voice !== "idle");
    // 运行中：发送键变方形停止键（图标和配色跟着换，位置不动，肌肉记忆不打断）
    sendBtn.classList.toggle("stop", running);
    mount(sendBtn, icon(running ? Square : ArrowUp, running ? 13 : 18));
    sendBtn.title = running ? "停止这一轮" : "发送";
    sendBtn.setAttribute("aria-label", sendBtn.title);
    micBtn.disabled = voice === "transcribing";
    micBtn.classList.toggle("recording", voice === "recording");
    micBtn.title = voice === "recording" ? "再点一下结束录音" : "语音输入";
    micBtn.setAttribute("aria-label", micBtn.title);
    pickers.sync();
    mount(micBtn, voice === "transcribing" ? icon(LoaderCircle, 16, "spin") : voice === "recording" ? icon(Square, 14) : icon(Mic, 16));
    if (!cur) hint.textContent = "直接输入就会新建对话 · Enter 发送";
    else if (!cur.live) hint.textContent = "输入即可接续这段会话，将恢复原工作区和上下文";
    else if (voice === "recording") mount(hint, level, `正在听 ${seconds}s · 再点一下结束（最长 ${MAX_SECONDS}s）`);
    else if (voice === "transcribing") hint.textContent = "正在把语音转成文字…";
    else if (cur.busy) hint.textContent = "正在进行中 · 点右边的方形键停止";
    else hint.textContent = "Enter 发送 · Shift + Enter 换行 · 每一步决策，都有迹可循";
  }

  const el = h("div", { class: "composer" },
    h("div", { class: "composer-box" }, imageInput, imagePreviews, textarea,
      h("div", { class: "composer-toolbar" },
        h("div", { class: "composer-controls" }, pickers.el),
        h("div", { class: "composer-actions" }, micBtn, sendBtn))),
    hint);
  sync();
  return { el, sync };
}
