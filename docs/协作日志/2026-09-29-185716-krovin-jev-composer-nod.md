# 点击输入框时 JEV 小人点头

- 目的：参考用户视频中的橙色小球，在点击对话输入框时让右上角 JEV 小人点头。
- 执行 Agent／任务：Codex / 当前对话，输入框点头反馈。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/ui/jev-status.ts、web/src/glass.css。输入框按下或键盘聚焦时触发一次约 480ms 的低头、回弹动画；连续点击可重新触发，减少动态效果偏好下不播放。JEV 状态和输入行为未改动。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过。未进行本地页面视觉检查。
- 未完成事项：用户可在本地页面查看效果；改动尚未提交或推送。
- 提交号或 PR：无。
