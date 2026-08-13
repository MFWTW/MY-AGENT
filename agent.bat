@echo off
chcp 65001 >nul
title HelloAents - Coding Agent Launcher

echo ==========================================
echo   HelloAents 一键启动
echo ==========================================
echo   [0/3] 进入 WSL 环境...
echo.

REM 转换当前目录为 WSL 路径并运行（不再写死 /mnt/e/agent）
for /f "delims=" %%i in ('wsl -e bash -lc "wslpath -a \"%CD%\""') do set "WS=%%i"
if not defined WS set "WS=/mnt/e/agent"

wsl -e bash -lc "cd '%WS%' && AGENT_WORKSPACE='%WS%' bash start.sh"

echo.
echo ==========================================
echo   Agent 已退出，vLLM 已自动停止。
echo ==========================================
pause
