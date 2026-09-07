@echo off
REM 一键启动被测服务 + 跑 pytest + 生成 Allure 报告（Windows 本地用）
REM 前提：已 pip install -r automation/requirements.txt
REM 看完 allure 报告后浏览器会打开

setlocal
set PY=C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\python.exe

REM 杀掉旧服务
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr LISTENING') do (
  taskkill /F /PID %%a >nul 2>&1
)

echo === 启动被测服务 ===
start "MiniMall" /B "%PY%" "%~dp0app\server.py"
timeout /t 2 /nobreak >nul

echo === 跑 pytest + Allure ===
cd /d "%~dp0automation"
"%PY%" -m pytest --alluredir=reports/allure-results --clean-alluredir
if errorlevel 1 (
  echo pytest 失败，仍尝试生成报告...
)

echo === 生成 Allure HTML 报告 ===
"%PY%" -m allure_combine.cli combine reports/allure-results -o reports/allure-report || (
  echo allure CLI 未安装，跳过 HTML 生成。
  echo 如需查看，请: pip install allure-pytest allure-combine, 或在 GitHub Actions 页面下载 artifact。
)

echo === 完成。报告位置: automation\reports\allure-report\index.html ===
endlocal