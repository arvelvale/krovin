import { ArrowRight, Download, ExternalLink, FileText, PenLine } from "lucide";
import { enterWorkspace } from "../store";
import { h, icon } from "./dom";
import { logoMark } from "./logo";

/** 登录后的落地页：先给评委/使用者项目报告书，再进工作台。
 *  报告 PDF 由 scripts/make_report.py 生成，随面板静态部署在 /report/ 下（免登录）。 */
export function renderLanding(): HTMLElement {
  const reportName = "KROVIN-项目报告书.pdf";
  const reportHref = `/report/${encodeURIComponent(reportName)}`;
  return h("div", { class: "landing" },
    h("header", { class: "landing-top" },
      h("div", { class: "landing-brand" }, logoMark(22), "KROVIN", h("span", null, "开发流 Agent")),
      h("a", { class: "landing-link", attrs: { href: "https://github.com/arvelvale/krovin", target: "_blank", rel: "noreferrer" } },
        icon(ExternalLink, 15), "GitHub")),
    h("main", { class: "landing-body" },
      h("span", { class: "landing-kicker" }, "DGX SPARK HACKATHON · 项目交付"),
      h("h1", null, "让每一次「AI 替人动手」，", h("br"), "都先给人", h("em", null, "看明白"), "。"),
      h("p", { class: "landing-sub" },
        "KROVIN 跑在 NVIDIA DGX Spark 上：读 Linear issue、Obsidian 纪要和人口述，",
        h("br"), "完成拆解、计划、开发、日志与状态同步。每一步「选哪个」，都有迹可循。"),
      h("div", { class: "landing-facts" },
        fact("JEV", "结构化决策层"),
        fact("12", "项 Skills"),
        fact("3", "档模型路由"),
        fact("本地", "推理为主力")),

      h("section", { class: "landing-card" },
        h("div", { class: "landing-card-head" },
          h("span", { class: "landing-card-icon" }, icon(FileText, 18)),
          h("div", null,
            h("h2", null, "项目报告书"),
            h("p", { class: "landing-card-sub" }, "PDF · 提交表单同款内容"))),
        h("ul", { class: "landing-toc" },
          h("li", null, "GitHub 开源仓库地址"),
          h("li", null, "项目说明：作品特点、核心亮点、技术实现方案与架构设计思路、优化方案"),
          h("li", null, "部署说明：本地算力如何部署智能体、如何优化大模型、如何设计 Agent Skills"),
          h("li", null, "技术栈说明：NVIDIA SDK、NVIDIA 与 StepFun 相关模型")),
        h("div", { class: "landing-actions" },
          h("a", { class: "btn primary", attrs: { href: reportHref, download: reportName, target: "_blank", rel: "noreferrer" } },
            icon(Download, 16), "下载项目报告书（PDF）"),
          h("button", { class: "btn", attrs: { type: "button" }, onclick: () => enterWorkspace() },
            "进入工作台", icon(ArrowRight, 16)))),

      h("p", { class: "landing-note" },
        icon(PenLine, 13), "参赛历程记录「黑客松十日谈」征文：",
        h("a", { class: "landing-link", attrs: { href: "/essay/index.html", target: "_blank", rel: "noreferrer" } }, "前往阅读 →"))),
    h("footer", { class: "landing-foot" },
      h("span", null, "KROVIN · 本地模型 · 智能调度 · 清晰可控"),
      h("span", null, "github.com/arvelvale/krovin")));
}

function fact(n: string, label: string): HTMLElement {
  return h("div", { class: "landing-fact" }, h("b", null, n), h("span", null, label));
}
