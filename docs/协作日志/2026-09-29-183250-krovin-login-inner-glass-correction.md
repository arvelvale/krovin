# 更正登录表单玻璃层

- 目的：按用户澄清，保留登录表单外层玻璃卡片，只删除内部多余的空白玻璃框。
- 执行 Agent / 任务：Codex `/root`；当前任务「登录表单玻璃外框需保留」。
- 项目与分支：`D:\Develop\DGXHackthon\krovin`；`feat/promo-followup`。
- 修改文件：撤销上一轮对 `web/src/glass.css` 的无框覆盖；保留 `web/src/ui/glass-surfaces.tsx` 中登录卡片不挂载额外 GlassSurface 的改动。最终只有该 TSX 文件相对 Git 基线修改，工作台输入框仍使用 GlassSurface。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过；最终 diff 仅一处选择器改动。实际视觉效果待用户刷新本地 5173 页面确认。
- 未完成：未提交或推送。
