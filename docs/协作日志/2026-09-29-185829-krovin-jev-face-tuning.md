# JEV 小人眼睛与笑口微调

- 目的：按用户反馈把睁眼改成略竖长的豆豆眼，并减弱笑口的纵向弧度。
- 执行 Agent／任务：Codex / 当前对话，JEV 小人表情微调。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/glass.css；睁眼尺寸由 3×3 调为 3×5，笑口高度由 5 调为 4 并下移 1px。闭眼和点头逻辑未变。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过。未进行本地页面视觉检查。
- 未完成事项：用户可在本地页面查看效果；改动尚未提交或推送。
- 提交号或 PR：无。
