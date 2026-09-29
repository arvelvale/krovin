# JEV 小人改为两次等幅点头

- 目的：点击输入框时，小人做两次幅度大致相同的明显点头，不再呈现逐渐减弱的弹簧回摆。
- 执行 Agent／任务：Codex / 当前对话，点头节奏调整。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/glass.css；将点头关键帧改为两个相同的低头与回正循环，时长 660ms。输入触发和减少动态效果偏好不变。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过。未进行本地页面视觉检查。
- 未完成事项：用户可在本地页面查看效果；改动尚未提交或推送。
- 提交号或 PR：无。
