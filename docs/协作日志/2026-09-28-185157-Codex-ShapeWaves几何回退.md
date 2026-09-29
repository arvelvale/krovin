# ShapeWaves 几何回退

执行者：Codex 当前主 Agent。项目 D:\Develop\DGXHackthon\spark-devflow-agent；分支 feat/liquid-glass-ui。

用户登录后反馈未见流动几何图形。检查发现前版在 WebGPU 初始化或渲染失败时只显示静态 Spark；不能从本地 HTTP 与构建结果断言用户浏览器 GPU 失败的确切原因。新增 web/src/ui/shape-fallback.tsx：Canvas 2D 绘制流动的方块、圆点、三角形，保留 Spark 镂空、鼠标涟漪及 #120f17 底色。web/src/ui/shape-background.tsx 在无 navigator.gpu、组件 onError 或 10 秒内未进入 data-ready=true 时使用此回退。原版 ShapeWaves 仍用于 WebGPU 可用且初始化成功的浏览器。glass.css 补全背景容器尺寸。更新 docs/前端视觉设计.md。

Canvas 后备逻辑画布最多960×600，约24fps，离屏或后台暂停，减少动态效果静态绘制，卸载清理 RAF/观察器/监听。npm run build 通过 TypeScript 与 Vite；git diff --check 通过，仅换行提示；5173 首页、背景入口与后备模块 HTTP200。未自动浏览器视觉验收，用户自行刷新查看。未部署节点、执行模型任务、提交、推送或创建PR。未读取其它Agent日志。
