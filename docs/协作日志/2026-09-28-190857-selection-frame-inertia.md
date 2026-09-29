# 选中方框惯性滑动

- 目的：按用户截图，使最近对话和右侧标签切换时，选中方框从旧卡片带惯性滑向新卡片，并覆盖相似的分段控件。
- 执行 Agent/任务：Codex `/root`，当前对话。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改文件：`web/src/ui/selection-motion.ts`（新增跨 DOM 重绘持续的弹簧选中框）；`web/src/ui/sidebar.ts`、`web/src/ui/trace.ts`、`web/src/ui/drawer.ts`、`web/src/main.ts`（标记会话和标签组、挂载同步、保留会话列表滚动位置）；`web/src/motion.css`（选中框材质及高对比度样式）；`web/src/ui/interaction-motion.ts`（避免选中项磁吸与方框错位）；`docs/前端视觉设计.md`（设计说明）。
- 验证：`npm.cmd --prefix web run build` 通过（TypeScript 与 Vite）；`git diff --check` 通过；本地 5173 的新动效模块及 CSS 均返回 HTTP 200。用户此前选择自行查看浏览器效果，未自动视觉验收。
- 未完成事项：等待用户对实际切换手感的反馈。本轮未执行节点真实模型验收，未提交、未创建 PR。
- 补充：新建会话先成为 current、稍后进入会话列表的短暂间隔保留原选中框，列表到达后仍可连续滑动；补充后构建与 diff 检查通过。
