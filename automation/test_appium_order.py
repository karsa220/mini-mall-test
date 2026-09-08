"""
Appium 移动端 UI 自动化 Demo（二）：MiniMall 订单流程 E2E
前置：test_appium_login.py 已验证登录链路；本文件在登录成功后继续驱动订单流程。

流程：登录(alice) -> 加购两件 -> 创建订单 -> 支付订单
驱动：UiAutomator2 + chromedriver（Chrome 150 对应 chromedriver 150）
定位：全部用 CSS 选择器（chromedriver W3C 模式不认 "id" 策略）

启动顺序（单条命令完成）：
  adb connect 192.168.0.101:37475
  python app/server.py
  appium --address 127.0.0.1 --port 4723
  pytest -v -s automation/test_appium_order.py
"""
import time
import os
import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from appium.webdriver.common.appiumby import AppiumBy

CSS = AppiumBy.CSS_SELECTOR

# ============ 配置 ============
APPIUM_SERVER = "http://127.0.0.1:4723"
MINI_MALL_URL = "http://192.168.0.103:5000/"

# WiFi 无线调试地址
DEVICE_UDID = "192.168.0.101:37475"
CHROMEDRIVER_PATH = "C:/Android/chromedriver-win64/chromedriver.exe"

# 留给用户点 Google FRE 的时间（秒）。已登录 Google 后可设 0：MANUAL_TAP_WAIT=0 pytest ...
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
    options.set_capability("goog:chromeOptions", {
        "args": ["--no-first-run", "--disable-fre", "--disable-features=WelcomeTrial",
                 "--no-default-browser-check"]
    })
    return options


# ============ Fixture：登录并展开订单面板 ============
@pytest.fixture(scope="session")
def driver():
    """整个会话共用一个 Chrome；先 UI 登录拿到 token，订单用例在此之上驱动"""
    drv = webdriver.Remote(APPIUM_SERVER, options=make_options())
    time.sleep(2)  # 等 Chrome 起来

    # Google FRE 兜底等待（已登录 Google 后基本不会弹）
    for i in range(MANUAL_TAP_WAIT, 0, -1):
        time.sleep(1)

    # 缓存击穿：带时间戳避免 Chrome 复用上一轮缓存的旧 H5
    drv.get(MINI_MALL_URL + "?ts=" + str(int(time.time() * 1000)))

    # —— UI 登录 ——
    WebDriverWait(drv, 20).until(EC.element_to_be_clickable((CSS, "#btn_login")))
    drv.find_element(CSS, "#username").clear()
    drv.find_element(CSS, "#username").send_keys("alice")
    drv.find_element(CSS, "#password").clear()
    drv.find_element(CSS, "#password").send_keys("password123")
    drv.find_element(CSS, "#btn_login").click()

    WebDriverWait(drv, 15).until(EC.text_to_be_present_in_element((CSS, "#result"), "token"))

    # 强制展开订单面板（绕开 H5 显隐逻辑；若页面不含该元素会直接抛错，便于定位）
    drv.execute_script("document.getElementById('order_panel').style.display='block'")
    try:
        WebDriverWait(drv, 10).until(
            lambda d: d.find_element(CSS, "#order_panel").is_displayed()
        )
    except Exception:
        with open("/tmp/order_page.html", "w", encoding="utf-8") as f:
            f.write(drv.page_source)
        print("!!! order_panel 未显示，页面源码已 dump 到 /tmp/order_page.html")
        raise
    yield drv
    drv.quit()


# ============ 订单流程用例 ============
def test_01_add_to_cart(driver):
    """加购两件：面板应回显「加购成功」且 code=0"""
    drv = driver
    drv.find_element(CSS, "#btn_add_cart_1").click()
    WebDriverWait(drv, 10).until(EC.text_to_be_present_in_element((CSS, "#order_result"), "加购成功"))

    drv.find_element(CSS, "#btn_add_cart_2").click()
    WebDriverWait(drv, 10).until(EC.text_to_be_present_in_element((CSS, "#order_result"), "加购成功"))

    text = drv.find_element(CSS, "#order_result").text
    assert '"code": 0' in text or '"code":0' in text, f"加购应成功：\n{text}"
    print("✅ 测1 通过：两件商品加购成功")
    print(text)


def test_02_create_order(driver):
    """创建订单：返回 order_id 且状态为「待支付」"""
    drv = driver
    drv.find_element(CSS, "#btn_create_order").click()

    WebDriverWait(drv, 10).until(EC.text_to_be_present_in_element((CSS, "#order_result"), "下单成功"))
    # order_id 写入 #order_id 元素，便于断言
    WebDriverWait(drv, 10).until(lambda d: d.find_element(CSS, "#order_id").text.strip() != "")

    text = drv.find_element(CSS, "#order_result").text
    order_id = drv.find_element(CSS, "#order_id").text.strip()
    assert order_id.startswith("OD"), f"order_id 应以 OD 开头，实际：{order_id}"
    assert "待支付" in text, f"新订单状态应为待支付：\n{text}"
    print("✅ 测2 通过：订单创建成功，order_id=" + order_id)
    print(text)


def test_03_pay_order(driver):
    """支付订单：状态应变为「已支付」"""
    drv = driver
    drv.find_element(CSS, "#btn_pay").click()

    WebDriverWait(drv, 10).until(EC.text_to_be_present_in_element((CSS, "#order_result"), "支付成功"))

    text = drv.find_element(CSS, "#order_result").text
    assert "已支付" in text, f"支付后状态应为已支付：\n{text}"
    print("✅ 测3 通过：订单支付成功")
    print(text)


if __name__ == "__main__":
    drv = webdriver.Remote(APPIUM_SERVER, options=make_options())
    print("🔗 已连 Appium server")
    input("按 Enter 关闭 driver...")
    drv.quit()
