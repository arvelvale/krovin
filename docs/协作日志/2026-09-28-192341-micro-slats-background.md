# 背景替换为 React Bits MicroSlats

- 目的：按用户给出的 React Bits MicroSlats JS-CSS registry 与参数替换现有全屏背景。
- 执行 Agent/任务：Codex `/root`，当前对话。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改文件与操作：新增 `web/src/components/MicroSlats.jsx`、`MicroSlats.css`（registry 原样源码）、`MicroSlats.d.ts`、`web/src/ui/micro-background.tsx`；修改 `web/src/main.ts`、`web/src/glass.css`、`web/package.json`、`web/package-lock.json`、`docs/前端视觉设计.md`。移除旧 `ShapeWaves.jsx`/`.css`、`shape-background.tsx`、`shape-fallback.tsx`，卸载 vgpu，安装 ogl 1.0.11。
- 配置：swell、#A855F7、白色 glint、黑色底、10×25 slat、gap 3、roundness 0.75、interactive、cursorStrength 1、cursorSize 40、swirl 0、trail 1.4、lean 0、intro。
- 验证：组件两份源文件与 registry JSON 内容逐字一致；TypeScript/Vite 构建通过；`npm ls` 确认 ogl 1.0.11 且无 vgpu；`git diff --check` 通过；本地 5173 新组件与挂载模块返回 HTTP 200。用户此前选择自行检查浏览器效果，未自动视觉验收。
- 未完成事项：等待用户确认实际 WebGL 视觉；未提交、未创建 PR；本轮未做节点真实模型验收。
