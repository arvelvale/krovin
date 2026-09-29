import { ArrowRight, Eye, EyeOff, KeyRound, ShieldCheck, Sparkles } from "lucide";
import { login } from "../store";
import { h, icon } from "./dom";

export function renderLogin(): HTMLElement {
  const input = h("input", {
    class: "input", attrs: { id: "access-token", type: "password", placeholder: "输入团队访问口令", "aria-label": "访问口令", "aria-describedby": "login-error", autocomplete: "current-password", autofocus: true },
  });
  const err = h("div", { class: "login-error", attrs: { id: "login-error", role: "alert" } });
  const btn = h("button", { class: "btn primary block", attrs: { type: "submit" } }, "进入工作空间", icon(ArrowRight, 16));
  const reveal = h("button", { class: "icon-btn", title: "显示口令", attrs: { type: "button", "aria-pressed": "false" }, onclick: () => {
    const showing = input.type === "password";
    input.type = showing ? "text" : "password";
    reveal.title = showing ? "隐藏口令" : "显示口令";
    reveal.setAttribute("aria-label", reveal.title);
    reveal.setAttribute("aria-pressed", String(showing));
    reveal.replaceChildren(icon(showing ? EyeOff : Eye, 17));
  } }, icon(Eye, 17));
  const form = h("form", {
    class: "login-card",
    onsubmit: async (e: Event) => {
      e.preventDefault();
      err.textContent = "";
      input.removeAttribute("aria-invalid");
      if (!input.value.trim()) {
        err.textContent = "先填一下口令";
        return;
      }
      btn.setAttribute("disabled", "");
      btn.textContent = "正在验证…";
      const msg = await login(input.value);
      btn.removeAttribute("disabled");
      btn.replaceChildren("进入工作空间", icon(ArrowRight, 16));
      if (msg) {
        err.textContent = msg === "访问口令不对" ? "口令不匹配，请核对团队手册或启动终端中的口令。" : msg;
        input.setAttribute("aria-invalid", "true");
      }
    },
  },
  h("div", { class: "brand-mark lg" }, icon(Sparkles, 26)),
  h("div", { class: "login-eyebrow" }, "你的工作空间，已就绪"),
  h("h1", null, "欢迎回来。"),
  h("p", { class: "login-sub" }, "用一个对话，开启下一段开发。"),
  h("label", { class: "login-label", attrs: { for: "access-token" } }, "访问口令"),
  h("div", { class: "input-wrap" }, icon(KeyRound, 16), input, reveal),
  err,
  btn,
  h("p", { class: "login-help" }, icon(ShieldCheck, 14), "口令可在团队手册或启动终端中找到"));
  setTimeout(() => input.focus(), 0);
  return h("div", { class: "login" },
    h("div", { class: "login-brand" }, icon(Sparkles, 22), "KROVIN", h("span", null, "开发流助手")),
    h("div", { class: "login-layout" },
      h("section", { class: "login-story" },
        h("span", { class: "welcome-kicker" }, "AGENTIC DEVELOPMENT INFRASTRUCTURE"),
        h("h2", null, "让 ", h("em", null, "AI", h("span", { class: "ai-agents-word" }, " agents")), h("br"), h("span", null, "融入你的开发流。")),
        h("p", null, "从第一行想法，到最后一次提交。", h("br"), "KROVIN 陪你把开发的每一步，连在一起。"),
        h("div", { class: "login-flow" }, "理解需求", h("span", null, "→"), "执行计划", h("span", null, "→"), "交付进展")),
      form),
    h("footer", { class: "login-footer" }, h("span", null, "KROVIN"), h("span", null, "本地模型 · 智能调度 · 清晰可控")));
}
