@echo off
chcp 65001 >nul
title 策略看板 (本地服务器)
cd /d "%~dp0"
echo 启动看板服务器,浏览器将自动打开 http://127.0.0.1:8766
echo 页面右上角「刷新数据」按钮 = 拉最新数据并重算(A股需 akshare 可达)。
echo 关闭本窗口即停止。
echo.
python serve.py
pause
