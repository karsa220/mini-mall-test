"""
Appium 移动端 UI 自动化 Demo（基于 MiniMall H5）
目标：用真机/模拟器 Chrome 浏览器访问 MiniMall H5 登录页，自动填账号点登录，断言响应有 token

启动顺序：
1. cmd 窗口 A：appium                          (启动 Appium server)
2. cmd 窗口 B：python app/server.py             (启动 MiniMall 服务)
3. usb 连接 vivo 真机（开了 USB 调试），或启动模拟器
4. pytest -v -s automation/test_appium_login.py  (跑测试)
"""
import time
import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from appium.webdriver.common.appiumby import AppiumBy


# ============ 配置 ============
# Appium server 地址
APPIUM_SERVER = "http://127.0.0.1:4723"
# MiniMall 服务在电脑上的 IP（手机/模拟器要能访问到）
# 本机默认 192.168.0.x；改成你电脑的实际 IP
MINI_MALL_URL = "http://192.168.0.103:5000/"

# ============ Capability ============
def make_options():
    """构造 Android 启动参数"""
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.device_name = "vivo-test"          # 任意起名，adb devices 看到的名字
    options.automation_name = "UiAutomator2"
    options.no_reset = True                    # 不重置 App 状态
    options.new_command_timeout = 300
    options.auto_grant_permissions = True
    return options


# ============ Fixture ============
@pytest.fixture(scope="function")
def driver():
    """每个用例起一个 driver（新手用 function scope 隔离最稳）"""
    options = make_options()
    # 不指定 app，会让用户手动选应用（适合演示）
    # 真要自动化打开 Chrome 请加上：
    # options.android_package = "com.android.chrome"
    # options.android_activity = "com.google.android.apps.chrome.Main"

    drv = webdriver.Remote(APPIUM_SERVER, options=options)
    yield drv
    drv.quit()


# ============ 测试用例 ============
def test_01_homepage_visible(driver):
    """测1：手机能打开 MiniMall H5，页面加载出登录按钮"""
    driver.get(MINI_MALL_URL)

    # 等登录按钮渲染
    btn = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((AppiumBy.ID, "btn_login"))
    )
    assert btn.is_displayed(), "登录按钮应该可见"
    print(f"✅ 测1 通过：手机看到登录按钮")


def test_02_login_with_correct_password(driver):
    """测2：填正确账号密码 → 点登录 → 看到 token"""
    driver.get(MINI_MALL_URL)

    # 1. 等页面加载
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((AppiumBy.ID, "btn_login"))
    )

    # 2. 清空 username 然后填入 alice（默认就是 alice，但测试要确保）
    username_input = driver.find_element(AppiumBy.ID, "username")
    username_input.clear()
    username_input.send_keys("alice")

    # 3. 同理密码
    password_input = driver.find_element(AppiumBy.ID, "password")
    password_input.clear()
    password_input.send_keys("password123")

    # 4. 点登录
    btn = driver.find_element(AppiumBy.ID, "btn_login")
    btn.click()

    # 5. 等响应渲染到 #result
    WebDriverWait(driver, 10).until(
        EC.text_to_be_present_in_element((AppiumBy.ID, "result"), "token")
    )

    # 6. 断言
    result_text = driver.find_element(AppiumBy.ID, "result").text
    assert '"code": 0' in result_text or '"code":0' in result_text, \
        f"登录响应应该有 code 0，实际：\n{result_text}"
    assert '"token"' in result_text, f"响应应包含 token 字段：\n{result_text}"

    print(f"✅ 测2 通过：登录成功，响应有 token")
    print(f"响应内容：\n{result_text}")


def test_03_login_with_wrong_password(driver):
    """测3：填错密码 → 应提示错误（不出现 token）"""
    driver.get(MINI_MALL_URL)
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((AppiumBy.ID, "btn_login"))
    )

    driver.find_element(AppiumBy.ID, "username").clear()
    driver.find_element(AppiumBy.ID, "username").send_keys("alice")
    driver.find_element(AppiumBy.ID, "password").clear()
    driver.find_element(AppiumBy.ID, "password").send_keys("WRONG_PASSWORD")
    driver.find_element(AppiumBy.ID, "btn_login").click()

    WebDriverWait(driver, 10).until(
        EC.text_to_be_present_in_element((AppiumBy.ID, "result"), "code")
    )

    result_text = driver.find_element(AppiumBy.ID, "result").text
    assert '"code"' in result_text
    assert "tk_" not in result_text, "错误密码不该有 token"
    print(f"✅ 测3 通过：错误密码被服务端拦截")
    print(f"响应：\n{result_text}")


# ============ 手动调试入口 ============
if __name__ == "__main__":
    """本地调试用：python automation/test_appium_login.py"""
    options = make_options()
    drv = webdriver.Remote(APPIUM_SERVER, options=options)
    print("🔗 已连 Appium server")
    print("👉 手机现在应该出现 Appium 设置界面 / 默认应用列表")
    print("👉 在手机上选 Chrome 浏览器，手动打开 http://192.168.0.103:5000/ 后继续")
    input("按 Enter 关闭 driver...")
    drv.quit()
