---
name: build-webpage
description: >-
  做网页 / 小游戏 / 前端原型 / html / React / Vue / 页面 / 在线小工具：在工作区里从零写一个能在浏览器里直接运行的静态网页（可用 CDN 版 React、Vue），完成后让用户点「预览」看效果。
version: 0.1.0
argument-hint: "<想做的网页或小游戏>"
model: auto
allowed-tools:
  - write_file
  - edit_file
  - run_in_sandbox
  - linear_create_issue
  - linear_update_issue
  - fetch_webpage
  - git_commit
triggers:
  - 做一个在线的贪吃蛇游戏
  - 写一个 todo 网页，用 Vue
  - 帮我做个 React 计数器页面
  - 做一个个人主页，一个 html 就行
not-for:
  - 修工作区已有项目里的 bug、按 issue 改代码 → implement-change
  - 只是写一份实施计划文档 → plan-writer
tags: [dev-flow, frontend]
---
# 做网页 / 小游戏

## 什么时候用
用户要一个能在浏览器里跑起来的页面或小游戏，而不是改一个已有的后端项目。

## 前提：工作区
- 先 `list_dir` 看工作区。如果里面是别的项目（比如有 `AGENTS.md` 约束了技术栈、和网页无关），**不要往里面塞网页**。
  告诉用户：「请先在左栏『工作区与文件』新建一个空白工作区并设为当前，再开新对话」，然后停下。
- 空白工作区（只有一个 README）就直接做。

## 用户要求「创建 / 拆分 issue」或「同步进度」时
你有 `linear_create_issue` 和 `linear_update_issue`，**不要说自己没有 Linear 工具**。
1. 开工前先 `linear_list_issues` 看现有 issue：用户给了标题就找这个 issue；没有就 `linear_create_issue` 建一个父 issue（标题用项目名，描述写功能清单和验收标准）。
2. 把项目拆成 4–8 个可以独立验收的子任务，逐个 `linear_create_issue`，`parent` 填父 issue 的编号，描述里写验收标准。这些调用会请用户确认（全自动模式下由 JEV 自动决定）。
3. 每做完一个子任务，`linear_update_issue` 把它改为 Done，`comment` 写一句做了什么；全部完成后在父 issue 上留一条汇总评论。
4. 报「找不到团队 / 项目」说明还没接入用户自己的 Linear：如实告诉用户去左栏「集成设置」填自己的 Linear Key，**不要改成只写文档就算完成**。

## 步骤
1. 简单页面可直接用 `index.html`、`style.css`、`app.js`。需要 React、Vue、TypeScript 或打包时，可以在沙箱里运行 `npm install` 和构建命令；不要因为旧说明就认定云端模型不能用 npm/pip。软件源已配置，但安装失败时要根据真实报错处理或说明。
2. 不需要打包时，React / Vue 也可以走浏览器直接加载：
   - Vue：`<script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>`，用 `Vue.createApp({...}).mount('#app')`。
   - React：`import React from "https://esm.sh/react@18"; import { createRoot } from "https://esm.sh/react-dom@18/client";`，不写 JSX，用 `React.createElement`（或 `https://esm.sh/htm` 的 `html\`...\``）。
   - 只允许这些 CDN：esm.sh、unpkg.com、cdn.jsdelivr.net、cdnjs.cloudflare.com。图片用 data URI 或 emoji，不要引外链图片。
3. 游戏要点：`requestAnimationFrame` 或固定间隔循环；键盘用 `keydown`（方向键 / WASD），同时给触屏提供按钮；显示分数与「重新开始」；`canvas` 要按 `devicePixelRatio` 处理清晰度。
4. 写完先自检语法：原生脚本用 `run_in_sandbox` 跑 `node --check app.js`；使用打包工具的项目要运行构建命令。逻辑部分（碰撞、计分）可以抽成纯函数用 `node test.js` 验证。需要读公开网页资料时调用 `fetch_webpage`，不要在沙箱里直接 curl 未放行的站点。
5. 用户看效果：**不要说「已经运行」**，你没有浏览器。告诉用户：左栏「工作区与文件」→ 找到当前工作区「查看文件」→ 点顶部的「预览」，也可以「新窗口打开」。

## 输出契约
回复包含：文件清单（一行一个，说明用途）、怎么操作（键位）、怎么预览（上面第 5 点）、已验证与未验证的部分（语法检查过；真实画面和手感没在浏览器里试过）。

## 不要做
- 不要把软件源放行等同于任意网站可访问；安装命令若失败，回报实际退出码和错误。
- 不引入需要后端的东西（登录、数据库）；要存档用 `localStorage`。
- 不改工作区里与这个页面无关的文件。
