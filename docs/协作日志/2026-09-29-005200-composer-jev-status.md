# 输入框 JEV 控件改为当前状态展示

- 目的：根据用户反馈，输入框左下角的 JEV 元素只展示当前会话状态，不作为下次新对话的开关。
- 执行 Agent/任务：Codex / 当前对话，前端状态展示修正。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改文件：`web/src/ui/composer.ts`、`web/src/glass.css`、`docs/前端视觉设计.md`。
- 改动：移除“下次 JEV”点击处理及开关轨道，改为只读状态标签；当前会话按 useJev 显示“JEV 决策层”或“基线 · 无 JEV”，无会话和状态未知时显示明确占位。新对话的 JEV 设置仍在原“新对话”面板。模型档位、语音和发送逻辑不变。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过（仅既有 CRLF 提示）。未自动操作浏览器，实际视觉待用户确认。
- 未完成事项：用户确认标签观感。无提交或 PR。
