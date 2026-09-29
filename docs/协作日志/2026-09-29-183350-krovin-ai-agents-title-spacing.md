# 统一 AI agents 标题颜色与间距

- 目的：按用户截图，让标题中 agents 与 AI 同色，并拉开英文词组与两侧中文的距离。
- 执行 Agent / 任务：Codex `/root`；当前任务「agents和AI颜色保持一致 并且前后间距拉开一些」。
- 项目与分支：`D:\Develop\DGXHackthon\krovin`；`feat/promo-followup`。
- 修改文件：`web/src/glass.css` 让 agents 继承 AI 的灰色、增加词间和两侧间距、保持词组不拆行；`web/src/ui/login.ts`、`web/src/ui/chat.ts` 去掉文字节点中额外的前导空格，统一由 CSS 控制距离。前一轮 `web/src/ui/glass-surfaces.tsx` 的登录内部空白玻璃层删除仍在工作区，非本轮新增。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过。实际视觉效果待用户刷新本地页面确认。
- 未完成：未提交或推送。
