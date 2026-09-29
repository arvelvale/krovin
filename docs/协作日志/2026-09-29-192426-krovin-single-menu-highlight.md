# 下拉菜单只保留一块高亮框

- 目的：消除已选项固定底色与滑动高亮框重复的问题；打开菜单时高亮框默认停在已选项。
- 执行 Agent／任务：Codex / 当前对话，菜单高亮交互修正。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/ui/composer-pickers.ts、web/src/setup.css、docs/前端视觉设计.md。去掉已选项固定底色，保留勾选标记；模型、工作区、权限菜单打开时将唯一的滑动高亮定位到已选项，鼠标移到其他项时滑动，离开后回到已选项；列表滚动时只在已选项可见时显示。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过。未进行本地页面视觉检查。
- 未完成事项：用户可在本地页面查看效果；改动尚未提交或推送。
- 提交号或 PR：无。
