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

## 步骤
1. 一个目录就够：`index.html` 为入口，样式和脚本可以拆成 `style.css`、`app.js`（用 `<script type="module" src="./app.js">`）。**不要用打包工具**——这里没有 npm 网络，也不需要。
2. 要 React / Vue 就走浏览器直接加载：
   - Vue：`<script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>`，用 `Vue.createApp({...}).mount('#app')`。
   - React：`import React from "https://esm.sh/react@18"; import { createRoot } from "https://esm.sh/react-dom@18/client";`，不写 JSX，用 `React.createElement`（或 `https://esm.sh/htm` 的 `html\`...\``）。
   - 只允许这些 CDN：esm.sh、unpkg.com、cdn.jsdelivr.net、cdnjs.cloudflare.com。图片用 data URI 或 emoji，不要引外链图片。
3. 游戏要点：`requestAnimationFrame` 或固定间隔循环；键盘用 `keydown`（方向键 / WASD），同时给触屏提供按钮；显示分数与「重新开始」；`canvas` 要按 `devicePixelRatio` 处理清晰度。
4. 写完先自检语法：`run_in_sandbox` 跑 `node --check app.js`（模块脚本用 `node --input-type=module --check < app.js` 不可行时，至少检查括号与 import 路径）。逻辑部分（碰撞、计分）可以抽成纯函数写在 `logic.js`，用 `run_in_sandbox` 跑一个 `node test.js` 验证。
5. 用户看效果：**不要说「已经运行」**，你没有浏览器。告诉用户：左栏「工作区与文件」→ 找到当前工作区「查看文件」→ 点顶部的「预览」，也可以「新窗口打开」。

## 输出契约
回复包含：文件清单（一行一个，说明用途）、怎么操作（键位）、怎么预览（上面第 5 点）、已验证与未验证的部分（语法检查过；真实画面和手感没在浏览器里试过）。

## 不要做
- 不用 `npm install` / `pip install`（沙箱没网络，会失败）。
- 不引入需要后端的东西（登录、数据库）；要存档用 `localStorage`。
- 不改工作区里与这个页面无关的文件。
