# 工作区与集成弹层切换改为滑动分段控件

- 目的：让「工作区 / 笔记库 / 集成」使用项目现有 RubberSegment 滑动选中框，沿用此前工作台的惯性动效。
- 执行 Agent / 任务：Codex `/root`；当前任务「这个页面也用之前一样的滑动ui」。
- 项目与分支：`D:\Develop\DGXHackthon\krovin`；`feat/promo-followup`。
- 修改文件：`web/src/ui/setup.ts` 保留固定标签容器、暴露当前标签与切换方法，不再每次重绘按钮；`web/src/ui/rubber-segments.tsx` 接入 setup-tabs 配置；`web/src/setup.css` 调整新控件占宽和尺寸。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过。现有浏览器权限设置不允许 Agent 进入 5173 视觉检查，待用户刷新页面查看动画。
- 未完成：未提交或推送。本分支还包含前两轮登录玻璃内层与标题间距的未提交改动。
