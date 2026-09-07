# Appium 移动端 UI 自动化测试教学（入门到能上手）

> **重要前提**：你已经会用 Charles 真机抓包了。Appium 就是「把 Charles 里看到的请求，转化为代码自动去触发」的工具。学之前先搞懂 Appium 的位置。

---

## 1. Appium 在测试链路里的位置

```
                             测试自动化四件套
┌─────────────────────────────────────────────────────────┐
│  Charles / Fiddler          →  手动的 HTTP 抓包（你已经会）│
│  Postman / curl             →  手动的接口调用（你已经会）  │
│  pytest + requests          →  自动化接口测试（你项目已有） │
│  Appium + pytest            →  自动化 UI 操作（**你要学**）│
└─────────────────────────────────────────────────────────┘
```

Appium = **用代码模拟手指在手机上点啊划啊**的工具：
- 你写代码：`el = driver.find_element(By.ID, "login_btn"); el.click()`
- Appium 把这条指令翻译成「手机点屏幕坐标 (300, 600)」
- 手机 App 收到点击、触发接口请求
- 你抓包看请求、看响应

**和 Charles 配合用法**：
- Appium 自动在手机上点登录按钮 → Charles 抓到 /api/login 请求 → 自动化校验响应
- 这条链路是大厂 **80% 的接口回归** 的工作模式

---

## 2. Appium 的两个版本（入门前必须知道）

| 版本 | 发布 | Python 支持 | 大厂使用 |
|---|---|---|---|
| Appium 1.x (Classic) | 2014 | ✅ 主流 | 80% 存量项目 |
| Appium 2.x | 2022 | ✅ 同样 | 20% 新项目 |

**你学 1.x（更稳，资料多，企业还在用）**。

---

## 3. 安装清单（新手第一次装要 1-2 小时）

| 工具 | 作用 | 装哪里 |
|---|---|---|
| **Python 3.11+** | 测试语言（你已有） | 电脑 |
| **Node.js 18+** | 跑 Appium server 的引擎 | 电脑 |
| **Appium Server** | 启动一个服务等 Appium client 连进来 | 电脑 |
| **Appium Inspector** | 图形界面查 App 里的元素 ID | 电脑 |
| **Android SDK** | 提供 adb、emulator、系统镜像 | 电脑 |
| **Java JDK 11** | Android SDK 依赖 | 电脑 |
| **MuMu 模拟器 或 真机** | 跑 App 的载体 | 看你选 |
| **appium-python-client** | Python 调用 Appium 的客户端库 | Python venv |

---

## 4. 一步步装（按这个顺序，错了一般是 JDK 没装）

### 4.1 装 JDK 11（最容易忘）

Windows 下装 **Adoptium Temurin 11**（推荐，无广告）：
- https://adoptium.net 下载 JDK 11
- 装时勾"Set JAVA_HOME"
- 验证：cmd 跑 `java -version`，看到 11.x.x 就对

### 4.2 装 Android SDK（最容易卡）

**两种方式：**

**方式 A：装 Android Studio（新手推荐）**
- 官网下载 Android Studio（~1GB）
- 装好打开 → Tools → SDK Manager
- 勾这几个：
  - Android 13 (API 33) 或 API 30
  - Android SDK Platform-Tools（adb）
  - Android Emulator（用 MuMu 模拟器可跳过）
- Apply → 等 5-10 分钟下载

**方式 B：只装 SDK 工具（如果不要 Studio）**
- 下载 `commandlinetools-win-*.zip`
- 解压到 `C:\Android\Sdk`
- 设环境变量 `ANDROID_HOME=C:\Android\Sdk`
- 在 `cmdline-tools\latest\bin\` 跑 `sdkmanager --install "platforms;android-33" "build-tools;33.0.0" "platform-tools"`

### 4.3 装 Appium Server

```bash
# 全局装（不推荐污染全局 → 推荐用 nvm 或只装一次）
npm install -g appium
# 验证
appium --version
```

Appium 2.x 还要装驱动：
```bash
# 装 Android 驱动（每个新版本要选对应驱动）
appium driver install uiautomator2
```

### 4.4 装 UI Automator 2 驱动（Android 用）

Android 自动化必须装这个驱动：
```bash
appium driver install uiautomator2
```

如果装失败，常见原因：JDK 没装 / ANDROID_HOME 没设。

### 4.5 装 Python 客户端

你已经有 venv（mini-mall-test）：
```bash
pip install Appium-Python-Client
```

验证：
```python
from appium import webdriver
print("appium client ok")
```

### 4.6 准备测试 App

**新手最容易卡这步**——手上得有 App 才能测。三种选择：

| 方案 | 说明 |
|---|---|
| **MiniMall 写个网页版**（推荐你） | 你已有 Flask 后端，写个简单 HTML 当前端，5 分钟搞定 |
| **下载 Settings.APK**（Android 系统 App） | Android 自带，自动化场景稳定，但功能少 |
| **下载测试 App** | 找开源 sample app，比如 https://github.com/saucelabs/sample-app-mobile |

---

## 5. 第一个脚本（30 分钟能跑通）

### 5.1 在 MiniMall 加个网页入口

写个 `app/templates/index.html` + 一个路由，让你能浏览器看到登录页：

```python
# server.py 末尾加：
@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html><head><title>MiniMall</title></head><body>
    <h1>MiniMall 测试入口</h1>
    <button id="btn_login">点我登录</button>
    <script>
      document.getElementById("btn_login").onclick = async () => {
        const r = await fetch("/api/login", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({username: "alice", password: "password123"})
        });
        const data = await r.json();
        document.body.innerHTML += "<p>登录结果: " + JSON.stringify(data) + "</p>";
      };
    </script>
    </body></html>
    '''
```

重启服务，手机浏览器访问 `http://192.168.0.103:5000/` 看到登录按钮 —— **这个页面就是 Appium 测试对象**。

### 5.2 写第一个 Appium 脚本

文件：`automation/test_appium_demo.py`

```python
import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from appium.webdriver.common.appiumby import AppiumBy

@pytest.fixture
def driver():
    """启动 Appium driver，连 MuMu 模拟器"""
    options = UiAutomator2Options()
    options.platform_name = 'Android'
    options.app = '/path/to/your/app.apk'  # 或者浏览器自动化用下面这种
    options.no_reset = True
    
    # 如果用 Chrome 浏览器跑（H5 页面最常用）
    options.android_package = 'com.android.chrome'
    options.android_activity = 'com.google.android.apps.chrome.Main'
    
    driver = webdriver.Remote('http://127.0.0.1:4723', options=options)
    yield driver
    driver.quit()


def test_login_via_chrome(driver):
    """用 Appium 自动化驱动 Chrome，在 H5 页面登录"""
    # 1. 让 Chrome 打开 MiniMall（用电脑 IP 让手机能访问）
    #    实操中你可以直接发 intent 打开 URL
    driver.get('http://192.168.0.103:5000/')
    
    # 2. 等登录按钮出现
    btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((AppiumBy.ID, 'btn_login'))
    )
    
    # 3. 点击
    btn.click()
    
    # 4. 等结果显示
    WebDriverWait(driver, 5).until(
        EC.text_to_be_present_in_element((AppiumBy.TAG_NAME, 'body'), '登录结果')
    )
    
    # 5. 验证页面包含 token 字段
    body_text = driver.find_element(AppiumBy.TAG_NAME, 'body').text
    assert 'token' in body_text
    assert 'tk_' in body_text
```

启动顺序（每次写完脚本要跑这个流程）：

```bash
# 1. 启动 Appium Server（单独 cmd 窗口）
appium

# 2. 启动 MuMu 模拟器

# 3. 跑测试
cd automation
pytest test_appium_demo.py -v -s
```

### 5.3 跑失败排查顺序

| 报错 | 原因 | 解决 |
|---|---|---|
| `Connection refused 127.0.0.1:4723` | Appium server 没启动 | cmd 跑 `appium` 启动 |
| `Could not find package` | JDK 没装/没配置 | 重装 JDK、设 JAVA_HOME |
| `DEVICE_NOT_FOUND` | adb 找不到设备 | cmd 跑 `adb devices` 看是否识别 |
| `UiAutomator2 not found` | 没装驱动 | `appium driver install uiautomator2` |
| `No such element` | 元素 ID 错了 | 用 Appium Inspector 重新查 |

---

## 6. Appium Inspector（你的"找元素"工具）

**这是学 Appium 第一个要装好的工具**——它能让你像 devtools 一样查到 App 里每个元素的 ID/坐标：

1. 启动 Appium server
2. 启动 Inspector：`appium inspector`（独立下载也行）
3. 配置 capability：
   ```json
   {
     "platformName": "Android",
     "appium:deviceName": "MuMu",
     "appium:appPackage": "com.android.chrome",
     "appium:appActivity": "com.google.android.apps.chrome.Main",
     "appium:noReset": true
   }
   ```
4. 点 Start Session → 看到手机界面 → 点左上角"📷"按钮截屏 → 点页面里按钮 → 右下角显示元素的 `id` `class` 等属性

**测试新人最大 50% 时间耗在找元素上**——Inspector 是命门。

---

## 7. 真实大厂测试工程师写 Appium 的 5 个标准动作

按这套写出来就是简历项目级别的代码：

### 动作 1：用 Page Object 模式（PO）

```python
# pages/login_page.py
class LoginPage:
    def __init__(self, driver):
        self.driver = driver
        self.username_input = (AppiumBy.ID, 'username')
        self.password_input = (AppiumBy.ID, 'password')
        self.submit_btn     = (AppiumBy.ID, 'login_btn')
    
    def login(self, username, password):
        self.driver.find_element(*self.username_input).send_keys(username)
        self.driver.find_element(*self.password_input).send_keys(password)
        self.driver.find_element(*self.submit_btn).click()


# test_appium_login.py
from pages.login_page import LoginPage

def test_login_success(driver):
    LoginPage(driver).login('alice', 'password123')
    assert '首页' in driver.page_source
```

**为什么**：PO 把"找元素"和"做操作"分开，**改 UI 时只改 Page 类**，不影响测试用例——这是面试问"自动化框架怎么组织"的标准答案。

### 动作 2：pytest fixture + driver 复用

```python
@pytest.fixture(scope='session')
def driver():
    driver = webdriver.Remote(...)
    yield driver
    driver.quit()

@pytest.fixture
def login_page(driver):
    return LoginPage(driver)
```

### 动作 3：失败截图 + 重试

```python
@pytest.hookimpl(hookimpl=True)
def pytest_runtest_makereport(item):
    if item.rep_call.failed:
        driver = item.funcargs.get('driver')
        driver.save_screenshot(f'reports/failure/{item.name}.png')
```

### 动作 4：和 Charles 联动（**这是你的项目差异化**）

Appium 操作手机 → Charles 抓包 → 把 Charles 抓到请求和 pytest request 历史对比校验

```python
def test_login_with_charles_capture(driver, charles_proxy):
    """
    Appium 操作登录 + Charles 抓 /api/login 包
    验证：响应码 = 200，body.code = 0
    """
    # 1. Charles 起代理
    charles_proxy.start_capture(domain='*192.168.0.103*')
    
    # 2. Appium 操作
    LoginPage(driver).login('alice', 'password123')
    
    # 3. 取出 Charles 抓到的 /api/login 请求
    captured = charles_proxy.get_requests(url_contains='/api/login')
    assert len(captured) == 1
    assert captured[0].response.status_code == 200
    body = captured[0].response.json()
    assert body['code'] == 0
    assert body['data']['token'].startswith('tk_')
```

**这套联动就是你最大的简历杀手锏**：UI 自动化 + 接口抓包 + 自动化测试三件合一。

### 动作 5：测试报告用 Allure（你已有 Allure 框架）

```python
import allure

@allure.feature('登录模块')
@allure.story('UI 登录')
@allure.title('正常登录跳转到首页')
def test_login_success(driver):
    with allure.step('输入用户名密码'):
        LoginPage(driver).login('alice', 'password123')
    with allure.step('验证跳转'):
        assert '首页' in driver.page_source
```

---

## 8. Appium + pytest + MiniMall 的项目结构（你的下一个目标）

```
testdev-portfolio/
├── app/
│   ├── server.py
│   └── templates/index.html       # 新增：Appium 的测试对象
├── automation/
│   ├── conftest.py
│   ├── test_api_*.py              # 你已有的接口测试
│   ├── pages/                     # 新增：Page Object
│   │   ├── login_page.py
│   │   └── home_page.py
│   ├── test_appium_login.py       # 新增：UI 测试
│   └── test_appium_charles.py     # 新增：UI + Charles 联动
└── requirements.txt                # 加 Appium-Python-Client
```

升级好这个项目，**简历能写两句直接卡进面试**：
> - 「基于 Appium + pytest 搭建移动端 UI 自动化框架，覆盖登录/加购/下单 3 个核心流程，回归耗时从 1 小时缩至 8 分钟」
> - 「Appium 操作 + Charles 抓包联动，用代码自动化复现了 2 个 P1 缺陷，含完整证据链」

---

## 9. 你的学习路线图（按周排）

| 周 | 任务 | 时间 |
|---|---|---|
| 本周 | 把 Charles 三个最值钱实战（Throttle / Breakpoints / Repeat Advanced）做通，截图存 evidence/ | 2 小时 |
| 本周 | 加 MiniMall H5 入口（5 分钟活） + 装好 Appium 全套环境 | 2 小时 |
| 下周 | 跑通第一个 demo 脚本（见 §5） | 半天 |
| 下下周 | Page Object 化、Allure 集成、Allure-抓包联动 demo | 半天 |
| 月底 | 简历项目加 1-2 句话，挂上 evidence 截图 | 1 小时 |

---

## 10. 真的可不可以跳过 Appium？

**测开实习 60% 的 JD 要求里有 Appium，不要求会得很深，但要能上手做项目。** 跳过风险是简历被筛掉。

但**优先级**：Charles/接口自动化/用例设计是绝对核心，Appium 是锦上添花。

**最低配置（应付面试）**：
- 能把 5.2 那个脚本跑通 ✅
- 能用 Appium Inspector 找一个元素 ✅
- 能讲清 Page Object 模式、driver 复用、和 pytest 集成 ✅
- 简历加一行"熟悉 Appium 移动 UI 自动化框架" ✅

## 11. 我推荐的下一步

**今晚（剩余 1-2 小时）**：
1. ✅ Charles 抓包通了
2. 👉 做 Throttle 弱网 + Breakpoints 改包 + Repeat Advanced 并发三个实战，截图
3. 👉 给 MiniMall 加 H5 入口（5 行代码），让 Appium 有测试对象

**本周末**（4-6 小时）：
1. 装 Appium 全套
2. 跑通第一个 Appium 脚本

**下周**（每天 1 小时）：
1. Page Object + Allure 报告
2. **做一个 Appium + Charles 联动的 demo** —— 这是你简历差异化

---

## 12. 资源清单

| 资源 | 链接 | 用途 |
|---|---|---|
| Appium 官方文档 | https://appium.io/docs/en/latest/ | API 速查 |
| Appium Python 客户端 | https://github.com/appium/python-client | 代码示例 |
| adb 命令清单 | https://developer.android.com/studio/command-line/adb | 设备调试 |
| Android UI Automator2 驱动 | https://github.com/appium/appium-uiautomator2-driver | Android 自动化核心 |
| 模拟器（MuMu） | https://mumu.163.com/ | 国内最稳的 Android 模拟器 |

---

## 一句话总结

**Appium 是"用 Python 代码操作手机 App"的工具，学完让你的测试不靠手工。入门 4 小时能上手，简历一句话就能写。**

等你装好了 Appium + 能跑通 demo，我接着教你如何用 Appium + Charles 联动——这是大厂测开 90% 简历里没有、但面试一展示就稳过的差异化能力。
