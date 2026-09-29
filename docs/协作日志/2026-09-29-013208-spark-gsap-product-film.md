# Spark 三分钟 GSAP 产品影片

- 目的：按 DGX Spark 黑客松项目能力与赛事演示要求，新增 3 分钟可播放、可定位的概念产品演示动画。
- 执行 Agent / 任务：Codex `/root`；当前任务「三分钟产品演示代码动画」。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`；`feat/liquid-glass-ui`。
- 修改文件：新增 `web/promo.html`、`web/src/promo.ts`、`web/src/promo.css`、`docs/产品演示分镜.md`；修改 `web/vite.config.ts`、`web/package.json`、`web/package-lock.json`、`README.md`。安装 `gsap` 并新增独立 Vite 多页面入口；未修改现有工作台业务交互。
- 内容：六幕 00:00–03:00 时间轴，展示问题碎片化、DGX Spark/JEV 架构、DAY-298 任务拆解、代码修复示意、工具门控与决策轨迹、品牌收束。支持播放/暂停、时间轴拖动、章节跳转、键盘控制及 `capture` 模式。代码画面明确标识为示意，不代替真实运行证据。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过；本地 Vite 服务 `http://127.0.0.1:5173/promo.html` 与脚本请求均返回 HTTP 200。实际视觉效果由用户自行在浏览器查看。
- 未完成：未制作最终 MP4、旁白与真实后端录屏；赛事提交版需将实际运行、测试和决策轨迹素材剪入成片。未执行新的 Git 提交或 PR。此前工作台 UI 的本地提交为 `01881f9`，推送 fork 时遇 TLS EOF，PR 仍未创建。
