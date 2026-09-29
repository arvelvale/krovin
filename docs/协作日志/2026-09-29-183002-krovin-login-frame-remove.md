# 去除 KROVIN 登录表单玻璃外框

- 目的：移除用户截图中表单上沿的半透明长框，保留登录内容和背景。
- 执行 Agent / 任务：Codex `/root`；当前任务「删除这个框」。
- 项目与分支：`D:\Develop\DGXHackthon\krovin`；`feat/promo-followup`。
- 修改文件：`web/src/glass.css` 去掉登录卡片的背景、边框、阴影与模糊；`web/src/ui/glass-surfaces.tsx` 不再给登录卡片挂载 React Bits GlassSurface。工作台输入框的 GlassSurface 保留。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过。浏览器保存的权限设置禁止 Agent 检查 5173 页面，实际视觉结果待用户刷新确认。
- 未完成：未提交或推送；若截图所指并非登录卡片外框，需要用户指出所在页面位置再调整。
