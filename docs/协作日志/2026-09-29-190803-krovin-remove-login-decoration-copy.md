# 删除登录页两处装饰文案

- 目的：删除用户截图指出的页脚品牌与技术标签，以及流程文字。
- 执行 Agent／任务：Codex / 当前对话，登录页文案精简。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/ui/login.ts、web/src/glass.css；删除页脚 KROVIN / 本地模型 · 智能调度 · 清晰可控，以及理解需求 → 执行计划 → 交付进展；清理对应样式并让主要登录布局继续居中。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过；源代码搜索确认上述文案与对应选择器已移除。未进行本地页面视觉检查。
- 未完成事项：用户可在本地页面查看效果；改动尚未提交或推送。
- 提交号或 PR：无。
