# 删除新对话面板的基线说明文字

- 目的：移除用户截图中 JEV 关闭时显示的“基线：主模型自己选（A/B 对照用）”。
- 执行 Agent/任务：Codex / 当前对话，前端文案删减。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改文件：`web/src/ui/sidebar.ts`。
- 改动：JEV 关闭时不渲染该说明；启用时原有说明和开关行为保留。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过（仅既有 CRLF 提示）；检索确认原文案已从前端源码移除。
- 未完成事项：无。无提交或 PR。
