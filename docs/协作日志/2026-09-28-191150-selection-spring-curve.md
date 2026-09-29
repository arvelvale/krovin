# 选中方框运动曲线调整

- 目的：响应用户反馈，将选中框从快速弹跳改为较慢、平滑的滑行。
- 执行 Agent/任务：Codex `/root`，当前对话。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改文件：`web/src/ui/selection-motion.ts`（由按帧积分改为按真实时间计算的临界阻尼弹簧，频率 8/s，连续切换保留速度）；`docs/前端视觉设计.md`（参数及参考依据）。
- 参考资料：Motion 官方弹簧与 springValue 文档、Apple SwiftUI spring API。没有新增依赖。
- 验证：`npm.cmd --prefix web run build` 通过；`git diff --check` 通过；本地 5173 的新模块 HTTP 200。未自动检查浏览器视觉，依用户既有偏好由用户自行预览。
- 未完成事项：等待用户确认实际滑动速度和手感；未提交、未创建 PR；本轮未做节点模型验收。
