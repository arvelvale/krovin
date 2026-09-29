# 会话选项移至输入框左下角

- 目的：参考用户粘贴的 PromptBar 布局，把截图中的 JEV 与模型档位控件置于对话输入框底部左侧；不添加附件按钮，不更改语音和发送功能。
- 执行 Agent/任务：Codex / 当前对话，前端输入区布局与选项调整。
- 项目与分支：`D:\Develop\DGXHackthon\spark-devflow-agent`，`feat/liquid-glass-ui`。
- 修改文件：`web/src/ui/composer.ts`、`web/src/ui/rubber-segments.tsx`、`web/src/main.ts`、`web/src/glass.css`、`docs/前端视觉设计.md`。
- 改动：从顶部移走状态徽章与模型档位，输入框底部新增“下次 JEV”开关和既有 RubberSegment 模型档位；在线会话档位仍下一轮生效，其他状态预设新对话档位。用户确认 JEV 开关只影响下次新对话，悬停说明显示当前会话状态。语音和发送按钮保留原节点与事件。
- 验证：`npm.cmd run build` 通过；`git diff --check` 通过（仅既有 CRLF 提示）；本地 5173 首页与相关前端模块返回 HTTP 200。未自动操作浏览器，实际视觉待用户确认。
- 未完成事项：用户确认布局与窄屏效果。无提交或 PR。
