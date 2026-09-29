# KROVIN

KROVIN 是跑在 NVIDIA DGX Spark 上的开发流 agent：读 Linear issue、Obsidian 纪要和用户口述，完成"拆解 → 计划 → 开发 → 写日志 → 同步状态"。
所有"选哪个"的结构化判断（技能选择、模型路由、工具门控、记忆精选、上下文压缩）交给 JEV 决策层，并且每个决策都写进可度量的决策轨迹。

> 这是团队内部 README。参赛提交用的对外版本（500 字说明、部署三问、技术栈清单）在截止前另写。

## 架构一览

```
输入 → 技能选择（JEV 两级）→ 模型路由（本地 Nemotron / 云端 step-5）→ 记忆精选
     → 规划循环：[压缩检查 → 主模型 → 工具门控 → 执行 → 回填] × N → 回复
     → 记忆写回 → 决策轨迹
```

| 层 | 组件 |
|---|---|
| 本地推理 | vLLM 0.28 + Nemotron-3.5 30B-A3B NVFP4（约 80 tok/s，主力）；Ollama + Qwen3.8 27B（备用） |
| 云端推理 | StepFun `step-5-preview`（写代码、复杂规划） |
| 决策层 | JEV（TypeSafe `jev-latest`） |
| 工具 | 文件、git、白名单命令、Obsidian、Linear |

设计正本：[docs/agent架构设计.md](docs/agent架构设计.md)；场景与排期：[docs/主场景方案-开发流skills.md](docs/主场景方案-开发流skills.md)。

## 目录

```
agent/            内核（每个模块文件头都写了职责和设计依据）
  tools/          工具实现；新增工具就在对应模块的 TOOLS 里加一项
skills/*/SKILL.md 技能（格式见 docs/接口/01-技能文件格式.md）
eval/             任务集、技能选择 A/B、门控标定
demo/             演示种子：tinyledger 仓库生成、Linear 演示 issue、Obsidian 纪要
docs/接口/        三个接口契约：技能文件 / 任务集 / 决策轨迹
scripts/node.py   同步到节点、带隧道执行
tests/            单元测试（不访问网络）
```

## 快速开始

```bash
pip install pyyaml pytest            # 唯一的运行依赖是 pyyaml
python -m pytest                     # 单元测试
python demo/seed/make_workspace.py   # 生成演示仓库到 var/workspace/tinyledger
python -m agent doctor               # 检查模型、JEV、Linear、工作区
python -m agent chat                 # 交互对话；写操作会逐条请你确认
python -m agent run "待会开站会，帮我理一下昨天干了啥今天干啥"
```

密钥放在根目录 `.env`（已 gitignore）：`STEPFUN_API_KEY`、`TYPESAFE_API_KEY`、`LINEAR_API_KEY`。
本机运行时本地模型要走 SSH 隧道（`-L 8000:127.0.0.1:8000 -L 11434:127.0.0.1:11434`）。

在节点上跑（推荐，本地模型直连）：

```bash
python scripts/node.py sync
python scripts/node.py run "python3 -m agent doctor"
```

节点直连不了境外，JEV 和 Linear 经 SSH 反向隧道走操作机代理，所以**操作机要在线**。详见 [docs/节点连接与模型运维.md](docs/节点连接与模型运维.md)。

## 分工入口

| 角色 | 主要改哪里 | 怎么验证 |
|---|---|---|
| 架构 / skills 基础设计 | `agent/`、`docs/接口/` | `python -m pytest` |
| agent 优化 | `agent/router.py`、`agent/context.py`、`agent/memory.py`、`agent/config.py` 里的阈值 | `python -m eval.run_selection`，节点上跑真实场景看 `var/runs/*/trace.jsonl` |
| 提示词优化 | `agent/prompts.py`、各模块里的 JEV 问题措辞（`gate_questions()` 等） | `python -m eval.run_gate`、`python -m eval.run_selection` |
| skills 优化 | `skills/*/SKILL.md`、`eval/tasks/*.json` | `python -m agent skills`、`python -m eval.run_selection` |

改阈值前先读 `agent/config.py` 里每个阈值的方向注释（值越大意味着什么），改完跑一遍对应的评估。

## Web 面板

```bash
python scripts/node.py sync      # 先在 web/ 里 npm install && npm run build，sync 会把 web/dist 一起带上
python scripts/node.py serve     # 节点上起面板 + 本机 127.0.0.1:9000 转发；Ctrl+C 结束，节点进程随之退出
```

浏览器打开 http://127.0.0.1:9000，口令是 `.env` 里的 `AGENT_WEB_TOKEN`（没设就每次随机生成并打印在终端）。

**个人使用**：面板常驻节点（`krovin-panel.bat` 部署一次），日常只双击 `krovin-tunnel.bat` 维持反向隧道，浏览器开 http://127.0.0.1:9000；不同步、不上公网，详见 [docs/个人使用.md](docs/个人使用.md)。

**评审期间**：双击 `serve-for-judges.bat`（自检 → 同步 → 节点自检 → 公网常驻，断线自动重连、运行期间电脑不睡眠）。
为什么必须有一台团队电脑开着、出问题怎么办，见 [docs/评审期间运维.md](docs/评审期间运维.md)；
评委使用指南用 `python scripts/make_guide.py` 生成到 `deliverables/`（含口令，不入库）。

- 左栏：会话、长期记忆、服务状态灯（绿 运行 / 蓝 备用 / 琥珀 异常 / 灰 离线）。Web 历史会话可以直接输入接续，恢复原工作区、对话和任务计划；原工作区已删除或旧记录缺少工作区归属时明确报错，不切换到其它目录。
  - 每步保存压缩后的上下文检查点；中断的工具调用补齐“结果未知”记录，恢复不会重放写操作。恢复使用当前集成与模型配置，旧记录未保存的全自动开关默认关闭。
  - 2026-09-29 节点真实模型验证：`s-20260929-080402-9e09` 在服务重启后接续第 2 轮，正确复述前轮验证内容并读取原工作区。断开 SSH 前后 tmux 面板进程保持不变。证据：`var/resume_e2e_evidence.json`、节点对应会话轨迹。
  - 删除会话前显示关联清理范围：专属 OpenShell 目录一并删除；非演示工作区仅在没有其它会话引用时删除，共用工作区保留。清理失败保留会话以便重试，正在执行的会话不能删除。不会删除 Linear issue 或用户电脑上的原始文件。2026-09-29 节点真实模型在临时会话 `s-20260929-071334-8d08` 创建网页并成功调用沙箱后，删除接口与独立目录检查均确认会话、工作区、专属沙箱目录消失，既有用户沙箱仍存在；测试轨迹删除前保存在本机 `var/cleanup_e2e_evidence.json`。此前已删除会话留下的孤立目录不自动追溯删除。
- 中间：对话；每轮下面一条决策摘要（技能 · 本地/云端 · 步数 · 耗时），写操作在这里弹确认卡
  - 用户消息悬停出现复制按钮（走 http 隧道时用老式剪贴板兜底，评委环境也能复制）
  - 运行中输入框右侧的圆形发送键变成**方形停止键**（Claude Desktop 的做法）：点了就在当前步边界停止，未完成事项留在工作记忆里；停止时等待中的确认卡按拒绝处理。工具批次执行中不打断，保证 tool_calls 与结果配对完整
- 右栏：所选轮次的决策轨迹（技能两级概率与阈值、路由难度、记忆精选、每步工具与门控、用量）和工作记忆
- 语音：点麦克风说话 → 转成文字进输入框，可以先改再发。**浏览器只在 localhost 或 https 下开放麦克风**
- 模型设置（左栏）：像 OpenCode 那样登记任意 OpenAI 兼容的供应商（预设 OpenAI / Anthropic / DeepSeek / Kimi / 智谱 / 百炼 / 硅基流动 / OpenRouter 等），填 Key、拉模型列表、测连通，再给**主力 / 备用 / 难题**三个分工位各选一个模型，新建对话生效。
  - Key 明文存在节点的 `var/models.json`（600 权限），接口永不回传原文；改了接口地址不重填 Key 时旧 Key 作废。
  - 「私有部署」开关决定隐私边界：只有私有模型能看到隐私记忆、跑摘要和记忆抽取；主力换成外部 API 时隐私记忆自动过滤。
  - 境外服务要打开「经操作机代理出境」（节点直连不了境外）。没有 `models.json` 时一切沿用 `config.py` 默认值和环境变量。

- **全自动（yolo）**：输入框里的「全自动」按钮（或发 `/yolo`、新建对话时的开关；命令行 `--yolo` / 聊天里 `/yolo`）打开后，原本要弹给你的确认改由 JEV 自动决定（判断可能误伤无关内容 → 自动拦截，其余自动放行），全程不打扰你，轨迹里标 `auto`。确认卡（没开全自动时）先用一句人话说清「要做什么」和「JEV 怎么看」，原始参数折叠在下面。不变的硬边界：技能白名单、外部写被 JEV 判为不相关照样拦截、路径沙箱、命令只在白名单或 OpenShell 沙箱里跑、Linear 范围、agent 不 push。开启时已经弹出来等着的确认卡会一并同意。
- **代码执行沙箱（NVIDIA OpenShell）**：`run_in_sandbox` 工具把工作区副本放进节点上的 OpenShell 容器沙箱运行任意命令——网络只放行策略列出的 npm / pip 软件源，系统目录只读、非 root，只有沙箱内的目录可写，Python 3.14 / Node 22 / git 可用；策略在 `sandbox/policy.yaml`。运行后新增 / 修改的文件同步回工作区（不同步删除）。公开网页可用只读的 `fetch_webpage` 工具通过 curl 读取（拒绝内网地址，不自动跟随跳转）。实现与取舍见 `agent/sandbox.py` 头部；节点上的网关是 `~/openshell/bin/openshell-gateway`（不是 systemd 服务，节点重启后要手动拉起，见 docs/评审期间运维.md）。
- **网页预览**：`build-webpage` 技能让 agent 从零写静态网页 / 小游戏（可用 CDN 版 React、Vue，不需要打包）；agent 写出网页后，回复下面会出现一张产物卡片（同 ChatGPT），点「预览」在大窗口里运行、点「代码」看源码；也可以在「工作区与文件 → 查看文件」里点「预览」，页面在隔离的 sandbox iframe 里运行：能执行脚本、加载 CDN，但带不上面板的登录 cookie、也访问不了面板接口（真实 Edge 里验证过 `fetch('/api/status')` 被拦）。预览地址凭 2 小时有效的令牌访问。
- 工作区与集成（左栏「工作区与文件」「集成设置」，首次进入以向导打开，可跳过用演示环境）：
  - **工作区**：面板跑在节点上看不到你电脑的磁盘，所以工作区是节点上的一份副本（`var/workspaces/<id>/`）——克隆 git 仓库（https，私有仓库用「集成」里的令牌）、导入本地文件夹（浏览器逐文件上传，或传 zip）、新建空白项目。能在面板里逐级看目录、看文件内容、看**相对导入快照的改动清单**；改完可在 Chrome / Edge 里一键写回原文件夹（File System Access API，每次授权），或下载 zip。选中的工作区在**新建对话时**固定，进行中的对话不受影响。
  - **Linear**：填自己的 Personal API Key → 拉团队 / 项目 → 保存前真连一次。项目可留空（范围放宽到整个团队，团队外的 issue 仍被拒绝）；「恢复演示」回到环境变量里的演示项目。
    - 设置在新对话生效。指定项目的请求先查询项目名称，再按 `project_name` 筛选；列表和详情显示所属项目，查不到时不会回退到整个团队。2026-09-29 节点 Nemotron 实测：`s-20260929-064412-6ad3` 按 Pomodoro 筛选并读取 DAY-301，仅生成拆分提案，没有写入 Linear（轨迹：`var/runs/s-20260929-064412-6ad3/trace.jsonl`）。
  - **Git**：提交身份（agent 帮你提交时署你的名）和按主机保存的访问令牌（只用于克隆 / 同步私有仓库，走 `GIT_CONFIG_*` 环境变量、不进命令行、报错里抹掉）。agent 自己仍不 push。
  - **笔记库（Obsidian）**：同一套机制，agent 只读。线上面板碰不到你本机的 Obsidian，接法有两种：Obsidian Git 插件推到私有仓库 + 面板里「同步」（推荐），或上传 zip / 文件夹快照。
  - 设置存节点 `var/integrations.json`（600 权限，Key 与令牌只进不出）；面板是单实例，设置对所有登录者生效。导入的 `.git`、`node_modules` 等会被丢弃（上传自带的 `.git` 里的 hooks / config 会在节点上被 git 执行，所以重新 init）。

前端开发：`cd web && npm run dev`（5173 端口，/api 代理到 127.0.0.1:9000）。自测截图：`node web/scripts/shot.mjs <URL> out.png [--dark] [--w 390 --h 844]`。
`python -m agent serve --dev-no-auth` 可免登录，但只允许配合回环地址；挂公网（`serve --public`，监听 0.0.0.0:9000 → 节点公网地址的 9006，以登录表为准）一律要口令。

## 常用参数

- `--no-jev`：关掉 JEV 决策层（A/B 的基线臂）
- `--tier local|cloud`：强制模型档位
- `--yes`：写操作自动确认，**只在演示沙盒里用**
- 环境变量：`AGENT_CONTEXT_BUDGET`（压缩预算）、`AGENT_LOCAL_THINKING=0`（本地主循环关思考）、`AGENT_MEMORY_EXTRACT=0`（关记忆抽取）
- 主循环默认不限步数，每次模型调用前仍检查上下文压缩；不会在第 30 步截停。2026-09-29 节点 Nemotron 实测会话 `s-20260929-070507-f676` 连续执行 35 次工具调用，第 36 步正常收尾（`var/runs/s-20260929-070507-f676/trace.jsonl`）。单轮越过 30 步且触发压缩的组合场景另有回归测试；尚未做数小时连续运行实测。
