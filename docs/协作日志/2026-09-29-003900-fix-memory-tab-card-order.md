# 修正长期记忆标签切换时的卡片顺序

- 目的：切换“生效中／待确认”时，不再先在新标签下显示旧标签卡片，再等待接口响应替换。
- 执行 Agent/任务：Codex / 当前对话，前端记忆列表状态修正。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改文件：`web/src/store.ts`、`web/src/main.ts`、`docs/前端视觉设计.md`。
- 改动：标签与对应缓存卡片在同一次状态更新中切换；记忆接口异步刷新只接收最新请求结果；同一标签刷新保留滚动位置，切换标签从新列表顶部开始。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过（仅既有 CRLF 提示）。未自动操作浏览器，实际视觉待用户确认。
- 未完成事项：用户确认快速切换和滚动后的效果。无提交或 PR。
