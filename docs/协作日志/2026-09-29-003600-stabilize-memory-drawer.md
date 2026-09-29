# 长期记忆抽屉点击后保持稳定

- 目的：消除长期记忆页点击“记住它”“忘掉”或切换标签后整页弹动、列表跳回顶部的现象。
- 执行 Agent/任务：Codex / 当前对话，前端抽屉交互修正。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改文件：`web/src/styles.css`、`web/src/motion.css`、`web/src/main.ts`、`docs/前端视觉设计.md`。
- 改动：取消 `.drawer` 的两处整体滑入动画；在长期记忆抽屉重绘前保存列表滚动位置，重绘后恢复。保留标签滑动与按钮局部反馈。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过（仅既有 CRLF 提示）；代码检索确认不再有 drawer 整体滑入关键帧。未自动操作浏览器，视觉待用户自行确认。
- 未完成事项：用户确认实际点击与滚动效果。无提交或 PR。
