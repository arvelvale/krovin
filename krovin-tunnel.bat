@echo off
chcp 65001 >nul
title KROVIN · 本机隧道（个人使用，这个窗口保持打开）
cd /d "%~dp0"
echo.
echo 个人使用：只维持两样东西
echo   1. 节点到本机代理的反向隧道（JEV / Linear 靠它；需要本机代理 mihomo 在运行）
echo   2. 本机 http://127.0.0.1:9000 到节点上面板的转发
echo 不同步代码、不启动面板。面板第一次使用（或更新代码后）请先运行 krovin-panel.bat。
echo 断线会自动重连；关掉这个窗口后 JEV / Linear 暂时不可用，聊天和改代码照常。
echo.
python scripts
ode.py tunnel
pause
