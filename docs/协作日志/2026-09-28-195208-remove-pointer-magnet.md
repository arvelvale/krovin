# 移除工作台控件鼠标跟随

- 目的：修复上轮遗漏的侧栏长期记忆、模型设置、退出登录与新对话按钮随鼠标微移的问题。
- 执行 Agent/任务：Codex `/root`，当前对话。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改文件：`web/src/ui/interaction-motion.ts`（整体移除 Magnet 鼠标跟随弹簧，保留 Spotlight 和 ClickSpark）；`web/src/motion.css`（移除 Magnet 专用样式）；`docs/前端视觉设计.md`（记录当前交互状态）。
- 验证：TypeScript/Vite 构建通过；`git diff --check` 通过。选中框独立滑动仍保留，原有点击逻辑未改。
- 未完成事项：视觉手感由用户在本地预览确认；未提交、未创建 PR；本轮未做节点真实模型验收。
