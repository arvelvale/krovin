# JEV 小人不规律眨眼

- 目的：让启用 JEV 时的小人在平常随机眨眼，避免固定节拍。
- 执行 Agent／任务：Codex / 当前对话，JEV 眨眼动画。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/ui/jev-status.ts、web/src/glass.css；加入约 1.8 至 6 秒的随机眨眼间隔与短暂眼睛压扁动画。关闭或状态未知时仍闭眼；页面隐藏或启用减少动态效果时停止定时器，重新可见后恢复。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过。未进行本地页面视觉检查。
- 未完成事项：用户可在本地页面查看效果；改动尚未提交或推送。
- 提交号或 PR：无。
