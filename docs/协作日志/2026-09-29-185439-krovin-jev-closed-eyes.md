# JEV 关闭或未知时闭眼

- 目的：JEV 状态关闭或未知时，让右上角的小人闭眼并停止跟随鼠标。
- 执行 Agent／任务：Codex / 当前对话，JEV 状态表情。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/ui/jev-status.ts、web/src/glass.css。未启用状态显示两道闭合眼线并清除视线偏移；启用时恢复绿色、睁眼和鼠标跟随。状态文字与判定逻辑保持不变。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过。未进行本地页面视觉检查。
- 未完成事项：用户可在本地页面查看效果；改动尚未提交或推送。
- 提交号或 PR：无。
