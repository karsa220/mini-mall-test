@echo off
chcp 65001 >nul
title Appium Server - 保持本窗口开启
echo.
echo ============================================
echo   Appium Server
echo   地址: http://127.0.0.1:4723
echo   驱动: uiautomator2 (Android)
echo.
echo   跑测试期间请保持本窗口开启
echo   停止服务: 按 Ctrl+C 或直接关闭窗口
echo ============================================
echo.

set "NODE_DIR=C:\Users\bfdym\.workbuddy\binaries\node\versions\22.22.2-2"

echo [1/2] 检查手机连接...
"%NODE_DIR%\..\..\..\Android\Sdk\platform-tools\adb.exe" devices 2>nul
if not exist "C:\Android\Sdk\platform-tools\adb.exe" (
    echo   未找到 adb，跳过设备检查
) else (
    "C:\Android\Sdk\platform-tools\adb.exe" devices
)

echo.
echo [2/2] 启动 Appium...
echo.

call "%NODE_DIR%\appium.cmd" --address 127.0.0.1 --port 4723 --base-path /

echo.
echo Appium 已退出。
pause
