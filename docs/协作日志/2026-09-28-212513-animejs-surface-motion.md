# Anime.js 控件状态动效扩展

- 目的：从 Anime.js 选择适合工作台的入场与开关动效，让控件状态变化更顺滑，避免鼠标跟随或重复动画。
- 执行 Agent/任务标识：Codex / 当前对话“你在里面找合适的动画效果 给控件加上”。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改：新增 `web/src/ui/surface-motion.ts`，以 Anime.js 驱动新对话弹层、记忆/模型抽屉、确认卡、提示条的短距离淡入与开关圆点弹簧切换；`web/src/main.ts` 接入同步和清理；`web/src/ui/chat.ts`、`sidebar.ts`、`models.ts` 增加稳定的动效标识；`web/src/motion.css`、`styles.css` 移除重复的 CSS 入场/开关位移动画；`docs/前端视觉设计.md` 记录当前方案。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过（仅既有换行提示）；5173 首页、surface-motion 模块、selection-motion 模块及动效 CSS 返回 HTTP 200。
- 未完成：按用户此前选择，未自动操作浏览器做视觉验收；未部署节点或运行真实模型场景。
- 提交号/PR：本次未提交或创建 PR。
