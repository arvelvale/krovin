# 输入框内两个下拉菜单缩放

- 目的：让工作区和权限两个下拉菜单与输入框内的小型工具栏控件保持比例一致。
- 执行 Agent／任务：Codex / 当前对话，下拉菜单尺寸调整。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/setup.css；工作区菜单宽度由 300px 改为 250px，权限菜单由 340px 改为 280px，同时缩小搜索框、选项行、字号、图标和留白；维持视口宽度限制。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过。未进行本地页面视觉检查。
- 未完成事项：用户可在本地页面查看效果；改动尚未提交或推送。
- 提交号或 PR：无。
