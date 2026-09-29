# JEV 状态移至顶部并加入跟随视线

- 目的：把工作台输入框中的 JEV 状态移到右上角，用两个随鼠标轻微转动的豆豆眼显示启用状态。
- 执行 Agent／任务：Codex / 当前对话，JEV 状态显示。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/main.ts、web/src/ui/composer.ts、web/src/ui/jev-status.ts、web/src/glass.css。状态文字和启用、关闭、未知判断保持一致；启用时眼睛为绿色，关闭时为灰色；尊重减少动态效果偏好。
- 验证结果：web 目录 npm.cmd run build 通过，npm.cmd run typecheck 通过，git diff --check 通过。未进行浏览器视觉检查。
- 未完成事项：由用户在本地页面检查视觉效果；改动尚未提交或推送。
- 提交号或 PR：无。
