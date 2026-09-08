@echo off
chcp 65001 >nul
setlocal

title Appium 真机测试 - MiniMall H5

set "PROJ=C:\Users\bfdym\WorkBuddy\2026-09-05-23-54-54\testdev-portfolio"
set "NODE_DIR=C:\Users\bfdym\.workbuddy\binaries\node\versions\22.22.2-2"
set "ADB=C:\Android\Sdk\platform-tools\adb.exe"
set "PY=C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\python.exe"

echo ============================================
echo   Appium 真机自动化测试
echo   项目: %PROJ%
echo ============================================
echo.

REM ---------- 环境变量 ----------
set "ANDROID_HOME=C:\Android\Sdk"
set "ANDROID_SDK_ROOT=C:\Android\Sdk"

echo [1/5] 检查 Android SDK...
if not exist "%ANDROID_HOME%" (
    echo   [X] 找不到 %ANDROID_HOME%
    goto :fail
)
echo   [OK] ANDROID_HOME=%ANDROID_HOME%

echo.
echo [2/5] 检查手机连接（最多重试 5 次）...
set "DEVICE="
for /l %%i in (1,1,5) do (
    if not defined DEVICE (
        "%ADB%" kill-server >nul 2>&1
        timeout /t 2 /nobreak >nul
        "%ADB%" start-server >nul 2>&1
        timeout /t 4 /nobreak >nul
        for /f "skip=1 tokens=1" %%d in ('"%ADB%" devices') do (
            if "%%d" NEQ "" set "DEVICE=%%d"
        )
        if not defined DEVICE echo   第 %%i 次未检测到，重试...
    )
)
"%ADB%" devices
if not defined DEVICE (
    echo.
    echo   [X] 没检测到手机。请检查：
    echo      1. USB 线插机箱背后主板口，不要用前面板/hub
    echo      2. 换一根数据线（很多充电线没有数据通道）
    echo      3. 屏幕解锁并保持亮着，锁屏会断 adb
    echo      4. 通知栏 USB 用途改成「传输文件」，不要停在「仅充电」
    echo      5. 开发者选项 -^> 撤销 USB 调试授权，重插后点「允许」
    echo      6. 开发者选项 -^> 打开「保持唤醒 / 充电时屏幕不休眠」
    goto :fail
)
echo   [OK] 设备: %DEVICE%

echo.
echo [3/5] 启动 MiniMall 服务...
curl -s -m 2 http://127.0.0.1:5000/ >nul 2>&1
if errorlevel 1 (
    echo   未检测到服务，正在启动...
    start "MiniMall" /MIN cmd /c "cd /d %PROJ% && "%PY%" app/server.py"
    timeout /t 4 /nobreak >nul
) else (
    echo   [OK] 服务已在运行
)

echo.
echo [4/5] 启动 Appium server...
start "AppiumServer" /MIN cmd /c ""%NODE_DIR%\appium.cmd" --address 127.0.0.1 --port 4723 --base-path / > "%TEMP%\appium.log" 2>&1"

echo   等待 Appium 就绪...
set /a TRY=0
:wait_appium
timeout /t 2 /nobreak >nul
curl -s -m 2 http://127.0.0.1:4723/status >nul 2>&1
if not errorlevel 1 goto :appium_up
set /a TRY+=1
if %TRY% GEQ 20 (
    echo   [X] Appium 启动超时，日志：
    type "%TEMP%\appium.log"
    goto :fail
)
goto :wait_appium
:appium_up
echo   [OK] Appium 已就绪

echo.
echo [5/5] 执行真机用例...
echo ============================================
cd /d "%PROJ%"
"%PY%" -m pytest automation/test_appium_login.py -v -s
set "RC=%ERRORLEVEL%"
echo ============================================

echo.
if "%RC%"=="0" (
    echo   结果: 全部通过
) else (
    echo   结果: 有失败，退出码 %RC%
)

echo.
echo 正在清理 Appium 进程...
taskkill /FI "WINDOWTITLE eq AppiumServer*" /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":4723" ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1

echo.
echo 完成。按任意键退出...
pause >nul
endlocal
exit /b %RC%

:fail
echo.
echo 执行失败，按任意键退出...
pause >nul
endlocal
exit /b 1
