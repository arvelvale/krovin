# 回退 Anime.js 控件动画

- 目的：按用户要求，回到引入 Anime.js 之前的控件动效方案。
- 执行 Agent/任务标识：Codex / 当前对话“不用这个库了 回退到用这个之前的”。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改：从 `web/package.json`、`web/package-lock.json` 移除 Anime.js；`web/src/ui/selection-motion.ts` 恢复原生临界阻尼弹簧；`web/src/ui/interaction-motion.ts` 移除 Anime.js 按压控制；删除 `web/src/ui/surface-motion.ts` 并从 `web/src/main.ts` 移除接入；撤销 `chat.ts`、`sidebar.ts`、`models.ts` 的专用动效标识；`styles.css`、`glass.css`、`motion.css` 恢复原有按压、开关与浮层 CSS 动效；`docs/前端视觉设计.md` 更新当前状态。
- 运行操作：重启本地 5173 Vite 并用 `--force` 刷新依赖预构建。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过（仅既有换行提示）；源码及依赖清单无 Anime.js 引用；`npm.cmd ls animejs --depth=0` 为空；5173 首页和相关模块均返回 HTTP 200。
- 未完成：按用户此前选择，未自动操作浏览器进行视觉验收；未部署节点或运行真实模型场景。
- 提交号/PR：本次未提交或创建 PR。
