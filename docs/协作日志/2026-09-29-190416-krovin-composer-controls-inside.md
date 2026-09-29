# 输入框内统一放置三个控件

- 目的：把模型档位、工作区和权限三个控件统一放到对话输入框内部。
- 执行 Agent／任务：Codex / 当前对话，输入框工具栏布局。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/ui/composer.ts、web/src/ui/composer-pickers.ts、web/src/glass.css、web/src/setup.css。将工作区与权限选择器移入输入框工具栏，调整间距与窄屏换行；向上展开的菜单限制在视口内并适应窗口尺寸。选择器原有功能未改动。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过。未进行本地页面视觉检查。
- 未完成事项：用户可在本地页面查看效果；改动尚未提交或推送。
- 提交号或 PR：无。
