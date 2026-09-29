/**
 * KROVIN 标志：一条从空心起点走到实心终点的路径——对应产品里「每一步决策都可追溯」。
 * 单色，颜色跟随 currentColor，和玻璃质感的界面搭配。public/favicon.svg 是同一个图形加了深色底。
 * （早先试过字母 K + 分叉的方案，太像别家产品的标志，已弃用；也不使用通用的「闪光星」图标。）
 */
const NS = "http://www.w3.org/2000/svg";

function el(tag: string, attrs: Record<string, string>): SVGElement {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

export function logoMark(size = 20, cls = ""): SVGElement {
  const svg = el("svg", { viewBox: "0 0 32 32", width: String(size), height: String(size), fill: "none", "aria-hidden": "true" });
  svg.classList.add("logo-mark");
  if (cls) svg.classList.add(...cls.split(" "));
  svg.append(
    el("path", { d: "M9 24.5c0-6 14-4.5 14-11.5", stroke: "currentColor", "stroke-width": "2.7", "stroke-linecap": "round" }),
    el("circle", { cx: "9", cy: "24.8", r: "3", stroke: "currentColor", "stroke-width": "2.1" }),   // 空心：起点
    el("circle", { cx: "23", cy: "8.2", r: "3.4", fill: "currentColor" }),                          // 实心：落点
  );
  return svg;
}
