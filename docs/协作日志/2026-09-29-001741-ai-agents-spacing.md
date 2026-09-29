# AI agents 标题字距调整

- 目的：让标题中 AI 与 agents 之间的空格在斜体字体下清晰可见。
- 执行 Agent/任务标识：Codex / 当前对话“AI Agents中间加个空格”。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改：`web/src/ui/chat.ts` 和 `web/src/ui/login.ts` 将标题中的英文词拆成保留空格的内联结构；`web/src/glass.css` 给第二个词增加 0.1em 的可见间距。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过（仅既有换行提示）。
- 未完成：实际视觉由用户在 5173 自行查看；未部署节点或运行真实模型场景。
- 提交号/PR：本次未提交或创建 PR。
