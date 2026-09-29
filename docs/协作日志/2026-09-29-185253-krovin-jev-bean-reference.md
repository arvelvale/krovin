# JEV 豆豆眼参考录屏调整

- 目的：参考用户录屏中黄色小球的倾身和脸部视线运动，优化右上角 JEV 状态的两个绿色豆豆。
- 执行 Agent／任务：Codex / 当前对话，JEV 状态动画细化。
- 项目与分支：D:\Develop\DGXHackthon\krovin；feat/promo-followup。
- 修改文件或操作：web/src/ui/jev-status.ts、web/src/glass.css；将眼睛改成两个有眼点和短线的绿色豆豆，并随指针轻微平移、倾斜；关闭状态仍为灰色，减少动态效果偏好下保持静止。为查看用户提供的 4 秒录屏，在工作区根目录生成 .video-tools 和 .video-frames 临时目录。
- 验证结果：web 目录 npm.cmd run build 通过；git diff --check 通过。未进行本地页面视觉检查。
- 未完成事项：改动尚未提交或推送；用户可在本地页面查看效果。临时视频检查目录清理命令被自动审批策略拒绝，目录暂时保留。
- 提交号或 PR：无。
