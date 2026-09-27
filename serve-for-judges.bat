@echo off
chcp 65001 >nul
title Spark 开发流 · 评审服务（这个窗口不要关）
cd /d "%~dp0"
echo.
echo ===== 1/3 自检：本机代理、JEV / Linear、SSH、口令、前端 =====
python scripts\node.py preflight
if errorlevel 1 (
  echo.
  echo 有未通过的项目，按上面的提示处理后再双击本文件。
  echo 仍要启动请按任意键（JEV / Linear 可能不可用，写操作会全部改为人工确认）。
  pause >nul
)
echo.
echo ===== 2/3 同步代码到节点，检查模型与服务 =====
python scripts\node.py sync
python scripts\node.py run "python3 -m agent doctor"
echo.
echo ===== 3/3 启动评审服务：断线自动重连，运行期间电脑不会睡眠 =====
echo 停止请按 Ctrl+C。
python scripts\node.py serve --public --keep-alive
pause
