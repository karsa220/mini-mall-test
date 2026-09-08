@echo off
chcp 65001 >nul
setlocal

REM ============================================================
REM  MiniMall 移动端 UI 自动化一键运行（WiFi 无线调试版）
REM  所有步骤在同一进程内完成，避免 adb 连接跨窗口丢失
REM ============================================================

set ADB=C:\Android\Sdk\platform-tools\adb.exe
set PYTHON=C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\python.exe
set APPIUM=C:\Users\bfdym\.workbuddy\binaries\node\versions\22.22.2-2\appium.cmd
set PROJ=C:\Users\bfdym\WorkBuddy\2026-09-05-23-54-54\testdev-portfolio

set ANDROID_HOME=C:\Android\Sdk
set ANDROID_SDK_ROOT=C:\Android\Sdk

REM 手机无线调试地址（开发者选项 -> 无线调试 -> IP 地址和端口）
set DEVICE=192.168.0.101:37475

cd /d "%PROJ%"

echo.
echo [1/5] 连接手机（WiFi 无线调试）...
"%ADB%" start-server >nul 2>&1
"%ADB%" connect %DEVICE%
timeout /t 3 /nobreak >nul
"%ADB%" devices | findstr /r "%DEVICE%.*device" >nul
if errorlevel 1 (
    echo   [X] 连不上手机 %DEVICE%
    echo       请确认：屏幕亮着、无线调试已开、端口号没变
    goto :fail
)
echo   [OK] 设备在线: %DEVICE%

echo.
echo [2/5] 启动 MiniMall 服务...
start "MiniMall" /min "%PYTHON%" app\server.py
timeout /t 4 /nobreak >nul
curl -s -m 3 http://192.168.0.103:5000/ >nul 2>&1
if errorlevel 1 (
    echo   [!] 服务未响应，继续尝试...
) else (
    echo   [OK] MiniMall 已启动 http://192.168.0.103:5000/
)

echo.
echo [3/5] 启动 Appium server...
start "Appium" /min "%APPIUM%" --address 127.0.0.1 --port 4723 --base-path /
timeout /t 14 /nobreak >nul
curl -s -m 5 http://127.0.0.1:4723/status >nul 2>&1
if errorlevel 1 (
    echo   [X] Appium 没起来
    goto :fail
)
echo   [OK] Appium 在线 127.0.0.1:4723

echo.
echo [4/5] 执行真机用例...
"%PYTHON%" -m pytest automation\test_appium_login.py -v -s
set TEST_RC=%ERRORLEVEL%

echo.
echo [5/5] 清理进程...
taskkill /FI "WINDOWTITLE eq Appium*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq MiniMall*" /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":4723.*LISTENING"') do taskkill /F /PID %%p >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5000.*LISTENING"') do taskkill /F /PID %%p >nul 2>&1

echo.
if "%TEST_RC%"=="0" (
    echo ========== 全部通过 ==========
) else (
    echo ========== 有失败，退出码 %TEST_RC% ==========
)
endlocal
exit /b %TEST_RC%

:fail
endlocal
exit /b 1
