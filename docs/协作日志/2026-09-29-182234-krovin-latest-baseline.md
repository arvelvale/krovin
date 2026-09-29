# 切换到 KROVIN 最新合并基线

- 目的：后续开发改从 GitHub `arvelvale/krovin` 的最新已合并 `main` 出发，避免在旧仓库和旧历史上继续修改。
- 执行 Agent / 任务：Codex `/root`；当前任务「使用最新合并版本继续后续开发」。
- 项目与分支：新副本 `D:\Develop\DGXHackthon\krovin`，`feat/promo-followup`，基于 `main` 提交 `0ede06ba1835d2a42cd5877a53f9ee7e1ade7077`；远端 `https://github.com/arvelvale/krovin.git`。
- 修改文件或操作：克隆最新仓库，建立本地开发分支；`web/` 与 `explainer/` 运行 `npm ci`，未改动受 Git 跟踪的文件。旧 `spark-devflow-agent` 目录及其中未提交的 GSAP 演示和其他文档改动完整保留；旧目录的 `origin` URL 更新为新仓库名。
- 决策：最新仓库已有 `explainer/` 宣传片实现及音频/录屏入口，不把旧副本的概念宣传页直接复制进去，避免重复及覆盖团队新成果。
- 验证：新仓库工作区干净；`web`、`explainer` 的 `npm run build` 均通过；本地工作台 `http://127.0.0.1:5173/` 和宣传片 `http://127.0.0.1:5174/promo.html` 均返回 HTTP 200。
- 未完成：本地分支尚未推送；没有新增提交或 PR。后续具体功能改动应在新目录进行。
