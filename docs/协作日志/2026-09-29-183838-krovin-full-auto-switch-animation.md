# 全自动开关滑动动画

- 目的：给新对话弹窗中的“全自动”开关加入与 JEV 开关一致的滑动动画，保留原有开关行为。
- 执行 Agent／任务：Codex / 当前对话，全自动开关动画。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/ui/sidebar.ts；记录全自动开关的开／关动画方向，在重绘时应用既有 switch-motion-on/off 样式，并在弹窗关闭时清除状态。未改动接口和持久化逻辑。
- 验证结果：npm.cmd run build 通过；git diff --check 通过。
- 未完成事项：改动尚未提交或推送；本地视觉效果由用户在 http://127.0.0.1:5173/ 查看。
- 提交号或 PR：无。
