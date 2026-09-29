# 桌面端卡片取消鼠标跟随

- 目的：按用户反馈移除卡片随指针微移的不自然效果。
- 执行 Agent/任务：Codex `/root`，当前对话。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改文件：`web/src/ui/interaction-motion.ts`（建议卡、模型预设卡退出磁吸目标）；`web/src/glass.css`（取消建议卡悬停上浮）；`web/src/motion.css`（移除不再需要的卡片磁吸覆盖）；`docs/前端视觉设计.md`（设计记录）。
- 验证：TypeScript/Vite 构建通过；`git diff --check` 通过；本地 Vite 的 ogl 依赖返回 200。卡片聚光、掠光、点击反馈仍保留。
- 未完成事项：视觉手感由用户自行预览；未提交、未创建 PR；本轮未做节点真实模型验收。
