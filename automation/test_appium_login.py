"""
Appium 移动端 UI 自动化 Demo（基于 MiniMall H5 + 真机 WiFi 无线调试）
目标：用 vivo 真机 Chrome 访问 MiniMall H5 登录页，自动填账号点登录，断言响应有 token

驱动方案：UiAutomator2 + chromedriver（Chrome 150 用 chromedriver 150）
说明：
  - 纯 UiAutomator2 看不到 Chrome 里的 H5 DOM，driver.get() 和按 id 找
    <input id="username"> 都会 proxy 失败（socket hang up），必须用 chromedriver。
  - chromedriver 路径见 CHROMEDRIVER_PATH，需与手机 Chrome 大版本一致。

启动顺序（单条命令完成）：
  1. adb connect 192.168.0.101:37475
  2. python app/server.py                  (MiniMall)
  3. appium --address 127.0.0.1 --port 4723
  4. pytest -v -s automation/test_appium_login.py
"""
import time
import os
import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from appium.webdriver.common.appiumby import AppiumBy


# ============ 配置 ============
APPIUM_SERVER = "http://127.0.0.1:4723"
MINI_MALL_URL = "http://192.168.0.103:5000/"

# WiFi 无线调试地址（开发者选项 -> 无线调试 -> IP 地址和端口）
DEVICE_UDID = "192.168.0.101:37475"

# chromedriver 路径（需与手机 Chrome 大版本一致；v150 对 v150.0.7871.0）
CHROMEDRIVER_PATH = "C:/Android/chromedriver-win64/chromedriver.exe"

# 留给用户在手机上点「保持未登录状态」的时间（秒）。改小=快但容易来不及点。
# 若运行前已经点掉，可设环境变量跳过：MANUAL_TAP_WAIT=0 pytest ...
MANUAL_TAP_WAIT = int(os.environ.get("MANUAL_TAP_WAIT", "8"))


# ============ Capability ============
def make_options():
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.automation_name = "UiAutomator2"
    options.browser_name = "Chrome"
    options.udid = DEVICE_UDID
    options.chromedriver_executable = CHROMEDRIVER_PATH
    options.no_reset = True
    options.new_command_timeout = 300
    options.auto_grant_permissions = True
    # 抑制 Chrome 首次运行欢迎页（FRE），避免卡在 Google 登录页
    options.set_capability("goog:chromeOptions", {
        "args": [
            "--no-first-run",
            "--disable-fre",
            "--disable-features=WelcomeTrial",
            "--no-default-browser-check",
        ]
    })
    return options


# ============ Fixture ============
@pytest.fixture(scope="session")
def driver():
    """整个测试会话共用一个 Chrome 会话（只拉起一次、只点一次按钮）"""
    options = make_options()
    drv = webdriver.Remote(APPIUM_SERVER, options=options)
    # UiAutomator2 不支持 current_window_handle 探测，用短 sleep 等 Chrome 起来
    time.sleep(2)

    # 提示：让用户手动点掉 Google 登录欢迎页
    # vivo 系统的按钮是「保持未登录状态」
    # 此函数不自动点击（用 XPath/UiSelector 调 UiAutomator2 协议转换有 bug）
    print()
    print("=" * 60)
    print("  请在手机上手动点击 Google 登录页的「保持未登录状态」按钮")
    print(f"  {MANUAL_TAP_WAIT} 秒倒计时开始...")
    print("=" * 60)
    for i in range(MANUAL_TAP_WAIT, 0, -1):
        if i <= 3:
            print(f"  剩余 {i} 秒")
        time.sleep(1)
    print("  继续执行测试")

    drv.get(MINI_MALL_URL)
    yield drv
    drv.quit()


# ============ 测试用例 ============
def test_01_homepage_visible(driver):
    """测1：手机能打开 MiniMall H5，页面加载出登录按钮"""
    btn = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((AppiumBy.CSS_SELECTOR, "#btn_login"))
    )
    assert btn.is_displayed(), "登录按钮应该可见"
    print("✅ 测1 通过：手机看到登录按钮")


def test_02_login_with_correct_password(driver):
    """测2：填正确账号密码 → 点登录 → 看到 token"""
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((AppiumBy.CSS_SELECTOR, "#btn_login"))
    )

    username_input = driver.find_element(AppiumBy.CSS_SELECTOR, "#username")
    username_input.clear()
    username_input.send_keys("alice")

    password_input = driver.find_element(AppiumBy.CSS_SELECTOR, "#password")
    password_input.clear()
    password_input.send_keys("password123")

    driver.find_element(AppiumBy.CSS_SELECTOR, "#btn_login").click()

    WebDriverWait(driver, 10).until(
        EC.text_to_be_present_in_element((AppiumBy.CSS_SELECTOR, "#result"), "token")
    )

    result_text = driver.find_element(AppiumBy.CSS_SELECTOR, "#result").text
    assert '"code": 0' in result_text or '"code":0' in result_text, \
        f"登录响应应该有 code 0，实际：\n{result_text}"
    assert '"token"' in result_text, f"响应应包含 token 字段：\n{result_text}"

    print("✅ 测2 通过：登录成功，响应有 token")
    print(f"响应内容：\n{result_text}")


def test_03_login_with_wrong_password(driver):
    """测3：填错密码 → 应提示错误（不出现 token）"""
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((AppiumBy.CSS_SELECTOR, "#btn_login"))
    )

    driver.find_element(AppiumBy.CSS_SELECTOR, "#username").clear()
    driver.find_element(AppiumBy.CSS_SELECTOR, "#username").send_keys("alice")
    driver.find_element(AppiumBy.CSS_SELECTOR, "#password").clear()
    driver.find_element(AppiumBy.CSS_SELECTOR, "#password").send_keys("WRONG_PASSWORD")
    driver.find_element(AppiumBy.CSS_SELECTOR, "#btn_login").click()

    WebDriverWait(driver, 10).until(
        EC.text_to_be_present_in_element((AppiumBy.CSS_SELECTOR, "#result"), "code")
    )

    result_text = driver.find_element(AppiumBy.CSS_SELECTOR, "#result").text
    assert '"code"' in result_text
    assert "tk_" not in result_text, "错误密码不该有 token"
    print("✅ 测3 通过：错误密码被服务端拦截")
    print(f"响应：\n{result_text}")


if __name__ == "__main__":
    options = make_options()
    drv = webdriver.Remote(APPIUM_SERVER, options=options)
    print("🔗 已连 Appium server")
    input("按 Enter 关闭 driver...")
    drv.quit()
