# Spark 镂空 ASCII 卡片

执行：Codex 当前对话主 Agent。项目 D:\Develop\DGXHackthon\spark-devflow-agent，分支 feat/liquid-glass-ui。

用户纠正效果层级为卡片层，并进一步明确「镂空出来的图形字样为 Spark」。最终：周围是流动 ASCII 字符，Spark 是不绘制字符的文字遮罩留空，不是 ASCII 字符拼字。

新增 web/src/ui/ascii-card.ts，自定义元素 + Canvas 2D；参照提供的 ShapeWaves 视觉行为实现低速波纹、鼠标涟漪、边缘渐隐。欢迎区替换原装饰图标，登录介绍区新增同款卡片。移除上一轮 dither-background.ts 与 main.ts 全局背景安装，glass.css 恢复实体黑色聊天底色并新增卡片样式。更新 docs/前端视觉设计.md。

性能/清理：约 24fps 绘制，DPR 最多 1.5；IntersectionObserver 和 visibilitychange 暂停离屏/后台动画；减少动态效果静态显示；断开 DOM 时取消 RAF、观察器和监听。无 React/vgpu/WebGPU 依赖，Canvas 不可用有文字回退。

验证：npm.cmd --prefix web run build 通过 TypeScript 与 Vite；git diff --check 通过，仅换行提示。浏览器视觉与实际鼠标效果未自动验收，仍按用户先前决定由用户自己预览。未同步节点、执行模型任务、提交、推送或创建 PR。本地构建不等于正式节点验收。

记录库按独立文件维护，本轮未读取其它 Agent 日志。后续以本次卡片方案为准，上一条全局 Bayer 背景记录已被取代。
