# 输入区下拉菜单高亮框滑动

- 目的：参考用户提供的录屏，让输入区菜单选项后的高亮框在行间平顺滑动。
- 执行 Agent／任务：Codex / 当前对话，菜单选项动画。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/ui/composer-pickers.ts、web/src/setup.css、docs/前端视觉设计.md。图片入口、模型、工作区和权限菜单共用独立高亮框；鼠标悬停与键盘聚焦时移动，离开或滚动时隐藏；减少动态效果偏好下取消过渡。未改选择行为或后端接口。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过。未进行本地页面视觉检查。
- 未完成事项：用户可在本地页面查看效果；改动尚未提交或推送。为分析录屏生成的 .video-frames/slide-*.png 临时文件清理命令被自动审批拒绝，暂时保留。
- 提交号或 PR：无。
