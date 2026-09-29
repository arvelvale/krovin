# 移除点击后整块缩放回弹

- 目的：欢迎建议卡与新对话弹层在点击后不再从小到大弹出。
- 执行 Agent/任务：Codex / 当前对话，前端交互修正。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改文件：`web/src/glass.css`、`web/src/motion.css`、`docs/前端视觉设计.md`。
- 改动：移除欢迎区因重绘反复触发的入场动画；移除弹层的重复入场动画；取消建议卡和普通按钮的按压缩放；登录与提示的入场关键帧不再改变缩放。分段控件的选中滑动保留。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过（仅既有 CRLF 提示）。未自动操作浏览器，实际视觉由用户查看。
- 未完成事项：用户确认点击后视觉效果。无提交或 PR。
