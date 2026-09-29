@echo off
chcp 65001 >nul
title KROVIN · 部署面板到节点（第一次或更新代码后运行一次）
cd /d "%~dp0"
echo.
echo ===== 同步代码到节点 =====
python scripts/node.py sync
echo.
echo ===== 重启节点上的常驻面板（tmux 会话 krovin，只听 127.0.0.1） =====
python scripts/node.py daemon stop
python scripts/node.py daemon start
echo.
echo 接下来双击 krovin-tunnel.bat，然后浏览器打开 http://127.0.0.1:9000
echo 面板常驻在节点上，不依赖本机；本机关机后面板还在，只是 JEV / Linear 暂时不可用。
pause
