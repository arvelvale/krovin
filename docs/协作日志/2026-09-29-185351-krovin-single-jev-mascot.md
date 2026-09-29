# JEV 状态改为单个双眼小人

- 目的：根据用户截图纠正右上角 JEV 状态图形，只保留一个小人，并给它两只眼睛。
- 执行 Agent／任务：Codex / 当前对话，JEV 状态小人修正。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/ui/jev-status.ts、web/src/glass.css。删除第二个独立小人，放大单个绿色小人并加入两只眼睛；保持原有鼠标跟随、JEV 状态颜色和文字。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过。未进行本地页面视觉检查。
- 未完成事项：用户可在本地页面查看效果；改动尚未提交或推送。
- 提交号或 PR：无。
