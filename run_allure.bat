@echo off
REM 一键启动被测服务 + 跑 pytest + 生成 Allure 原始结果（Windows 本地用）
REM 注意：本地无 Java 环境，无法用 allure CLI 直接生成 HTML 报告。
REM 想看 HTML 报告有两条路：
REM   a) 推 GitHub，CI 自动生成 HTML（推荐，见 .github/workflows/test.yml）
REM   b) 本地安装 Java + allure-commandline 后手动 allure generate

setlocal
set PY=C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\python.exe

REM 杀掉旧服务
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr LISTENING') do (
  taskkill /F /PID %%a >nul 2>&1
)

echo === 启动被测服务 ===
start "MiniMall" /B "%PY%" "%~dp0app\server.py"
timeout /t 2 /nobreak >nul

echo === 跑 pytest + 生成 Allure 原始结果 ===
cd /d "%~dp0automation"
"%PY%" -m pytest --alluredir=reports/allure-results --clean-alluredir

echo.
echo === 完成 ===
echo Allure 原始结果: automation\reports\allure-results\
echo.
echo 想看 HTML 报告？从 CI 下载 allure-html-report.zip 解压后，在该目录运行：
echo     python -m http.server 8080
echo 然后浏览器打开 http://localhost:8080  （不要双击 index.html，会报 500）
echo.
endlocal