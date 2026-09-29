# 模型设置下拉列表接入 GlideSelect

- 目的：将模型设置中的三处模型下拉改为用户提供的 React Bits GlideSelect，并保留现有模型分配行为。
- 执行 Agent/任务：Codex / 当前对话，前端下拉控件替换。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改文件：`web/src/components/GlideSelect.jsx`、`GlideSelect.css`、`GlideSelect.d.ts`、`web/src/ui/models.ts`、`web/src/main.ts`、`web/src/styles.css`、`web/package.json`、`web/package-lock.json`、`docs/前端视觉设计.md`。
- 改动：添加用户粘贴的组件源与依赖；替换主力、备用、难题三处原生 select；保留当前值、供应商标签、setSlots API 和失败提示；重绘及关闭抽屉时卸载 React 根节点。按用户此前反馈取消组件按钮与菜单的缩放，仅保留菜单淡入和选项滑动。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过（仅既有 CRLF 提示）；依赖树包含两个 Hugeicons 包；本地 5173 首页、组件模块、CSS、两个依赖模块均返回 HTTP 200。未自动操作浏览器，视觉与点击交互由用户自行查看。
- 未完成事项：用户确认实际视觉与交互。无提交或 PR。
