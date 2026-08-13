@echo off
chcp 65001 >nul
title HelloAents Setup
echo ==========================================
echo   HelloAents Setup (Windows)
echo   vLLM 需要 WSL2 + NVIDIA GPU
echo ==========================================
echo 正在进入 WSL 执行安装脚本...
for /f "delims=" %%i in ('wsl -e bash -lc "wslpath -a \"%CD%\""') do set "WS=%%i"
wsl -e bash -lc "cd '%WS%' && bash setup.sh"
echo.
pause