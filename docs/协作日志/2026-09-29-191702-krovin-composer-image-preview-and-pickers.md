# 输入框图片预览与下拉菜单统一

- 目的：参考用户提供的 PromptBar 加号和模型菜单，为工作台输入框加入图片选择入口，并统一模型、工作区、权限三个下拉控件的视觉样式。
- 执行 Agent／任务：Codex / 当前对话，输入框控件与图片预览。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/ui/composer.ts、web/src/ui/composer-pickers.ts、web/src/ui/rubber-segments.tsx、web/src/setup.css、web/src/glass.css、docs/前端视觉设计.md。加号菜单可选择最多 6 张图片并显示缩略图、移除图片；模型档位由输入框内的分段控件改为同系列下拉菜单，保留现有档位切换逻辑。工作区与权限菜单共享按钮、菜单和选项样式。
- 功能边界：图片仅保留在浏览器草稿中，不上传后端；附有图片时禁用发送并显示提示。未改后端接口、依赖或模型配置。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过。未进行本地页面视觉检查。
- 未完成事项：图片发送后端仍未实现；用户可在本地页面查看前端效果；改动尚未提交或推送。
- 提交号或 PR：无。
