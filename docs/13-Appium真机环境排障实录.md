# 13-Appium 真机环境排障实录（Windows + vivo 真机）

> 记录从零搭建 Appium 3.7.0 + UiAutomator2 真机自动化时踩的全部坑。
> 每一条都是真实报错 → 根因 → 解法，面试时可以直接讲。

---

## 环境基线

| 组件 | 版本 / 路径 |
|---|---|
| Appium | 3.7.0（`C:\Users\bfdym\.workbuddy\binaries\node\versions\22.22.2-2\appium.cmd`） |
| 驱动 | uiautomator2@8.6.1（装在 `C:\Users\bfdym\.appium`） |
| Node | 22.22.2 |
| Android SDK | `C:\Android\Sdk`（cmdline-tools 必须在 `cmdline-tools\latest\` 层） |
| JDK | 17（新版 sdkmanager 要求，JDK 8 报 `UnsupportedClassVersionError` class file version 61.0） |
| 真机 | vivo V2425A，序列号 `10CF1N1XSG0017C` |
| npm 镜像 | 腾讯云 `https://mirrors.cloud.tencent.com/npm/` |

---

## 坑 1：`'appium' 不是内部或外部命令`

**现象**：CMD 里敲 `appium driver list` 报命令不存在。

**根因**：appium 装在受管 Node 目录，没进系统 PATH。

**解法**：用全路径调用，或把目录加进 PATH。

```bat
"C:\Users\bfdym\.workbuddy\binaries\node\versions\22.22.2-2\appium.cmd" driver list --installed
```

同理 `adb` 也要用全路径 `C:\Android\Sdk\platform-tools\adb.exe`。

---

## 坑 2：npm 装驱动时装到一半中断，留下大量"半截包"

**现象**：appium 启动时连环报错，每次都换一个包：

```
Cannot find package '...\node_modules\asyncbox\index.js'
Cannot find module '...\node_modules\bluebird\js\release\bluebird.js'
Cannot find module './lib/truncate'
```

**根因**：第一次 `npm install` 被沙盒/网络中断，解压到一半就停了。
很多包目录里只剩 `LICENSE` + `build/`，**连 `package.json` 都没了**。Node 找不到入口就报上面这些错。

**教训**：只检查 `main` 入口文件是否存在是不够的——包内部文件（如 `./lib/truncate`）也会缺。必须做**全量文件比对**。

**解法**：按 `npm-shrinkwrap.json` 拿到完整依赖清单（含精确版本），逐个下载 tarball 补齐所有本地缺失文件。

```js
// 核心逻辑：只补文件，不删已有内容
function copyMissing(srcDir, dstDir) {
  for (const e of fs.readdirSync(srcDir, { withFileTypes: true })) {
    const s = path.join(srcDir, e.name), d = path.join(dstDir, e.name);
    if (e.isDirectory()) { if (!fs.existsSync(d)) fs.mkdirSync(d, {recursive:true}); copyMissing(s, d); }
    else if (!fs.existsSync(d)) fs.copyFileSync(s, d);
  }
}
```

---

## 坑 3：`npm error Missing script: "clean;"`

**现象**：装驱动时报

```
> appium-uiautomator2-driver@8.6.1 rebuild
> npm run clean; npm run build
npm error Missing script: "clean;"
```

**根因**：驱动 package.json 里

```json
"rebuild": "npm run clean; npm run build"
```

用 `;` 分隔命令——这是 **Linux bash 语法**。Windows 的 `cmd.exe` 不认 `;`，
把 `clean; npm run build` 整体当成一个脚本名去找，自然找不到。

**解法**：改成 `&&`（cmd 和 bash 都认）。

```json
"rebuild": "npm run clean && npm run build"
```

---

## 坑 4：`error TS5083: Cannot read file '.../tsconfig.json'`

**现象**：改完 `;` 之后又报

```
> tsc -b
error TS5083: Cannot read file '.../appium-uiautomator2-driver/tsconfig.json'
```

**根因**：npm 发布这个包时 **`files` 字段里没有 `tsconfig.json`**：

```json
"files": ["lib", "build/lib", "scripts", "CHANGELOG.md", "LICENSE", "npm-shrinkwrap.json"]
```

但 `prepare` 钩子会触发 `rebuild`，而 `build/lib/` 里**预编译产物本来就是完整的**。
`clean` 先把它们删掉，`tsc -b` 又没有 tsconfig 可依据 —— 于是把好端端的产物清空后构建失败。

**解法**：装的时候跳过 lifecycle 脚本，直接用预编译产物。

```powershell
npm install --omit=optional --no-audit --no-fund --ignore-scripts
```

`--ignore-scripts` 是**必须的**。或者更彻底，把 `prepare` 改成空操作：

```json
"prepare": "echo skip-rebuild-prebuilt-lib-exists"
```

---

## 坑 5：下载 tarball 一直是 0 字节

**现象**：`curl` 返回 `HTTP 200` 但 `size_download: 0`。

**根因**：环境里有代理 `https_proxy=http://127.0.0.1:7037`（VPN 残留），
代理放行请求头但把响应体吞了。

**解法**：
1. 关掉 VPN / 代理
2. 换国内镜像（腾讯云实测可用，且不需要跟随 302）

```powershell
npm config set registry https://mirrors.cloud.tencent.com/npm/
```

**注意**：npmmirror 的 tarball 地址会返回 302，自己写脚本下载时必须处理重定向。

---

## 坑 6：Windows 路径风格导致 tar 解压失败

**现象**：

```
tar (child): Cannot connect to C: resolve failed
```

**根因**：Git Bash 的 `tar` 对 `/c/Users/...` 这种路径做转换时炸了。

**解法**：用 Windows 原生 `tar.exe` + `C:/` 风格路径。

```bash
C:\\Windows\\System32\\tar.exe -xzf "C:/Users/.../pkg.tgz" -C "C:/Users/.../ext"
```

---

## 坑 7：驱动 tarball 根目录不一定叫 `package/`

**现象**：脚本报 `no package/ in tarball`。

**根因**：不同源的 tarball 根目录名不一样，可能是 `package/`、`bare-name/` 或 `@scope/name/`。

**解法**：依次尝试，都找不到就取第一个含 `package.json` 的子目录。

```js
const tryList = ['package', bareName, fullName];
// 都失败 → 遍历子目录找 package.json
```

---

## 坑 8：`appium driver uninstall` 删不干净，把包目录掏空

**现象**：uninstall 之后目录还在，但只剩 `build/`，`package.json` 全没了；
再 `driver install` 又报 "already installed"，进退两难。

**解法**：别在 CLI 层打转，直接在 `.appium` 目录用 npm 重装，让 npm 重建依赖树：

```powershell
cd C:\Users\bfdym\.appium
npm install appium@3.7.0 appium-uiautomator2-driver@8.6.1 --omit=optional --no-audit --no-fund --ignore-scripts
```

关键：`--ignore-scripts`（见坑 4）。

成功的标志是日志里出现 `removed N packages, and changed M packages` 且**没有 error**。

**验证**：

```bash
appium driver list --installed
# uiautomator2@8.6.1 [installed (npm)]
```

启动后看到这行才算驱动真正加载成功：

```
[Appium] AndroidUiautomator2Driver has been successfully loaded in 1.082s
```

---

## 坑 9：`Neither ANDROID_HOME nor ANDROID_SDK_ROOT environment variable was exported`

**现象**：driver 加载成功，但创建 session 时报这个。

**根因**：appium-adb 找不到 Android SDK。

**解法**：永久写进用户环境变量（当前 shell 里 export 只对本次有效）。

```powershell
[Environment]::SetEnvironmentVariable("ANDROID_HOME", "C:\Android\Sdk", "User")
[Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", "C:\Android\Sdk", "User")
```

写完**重开终端**才生效；当前会话要跑测试就临时 export：

```bash
export ANDROID_HOME="C:\\Android\\Sdk"
export ANDROID_SDK_ROOT="C:\\Android\\Sdk"
```

---

## 坑 10：测试没指定浏览器，UiAutomator2 不知道用什么打开 H5

**现象**：`driver.get(url)` 无响应或 session 创建异常。

**根因**：只给 platformName 不给浏览器，驱动不知道启动哪个 App。

**解法**：测 H5 要明确指定 Chrome，让 Appium 自动匹配 chromedriver。

```python
options.browser_name = "Chrome"
options.set_capability("chromedriverAutodownload", True)
```

---

## 坑 11：真机 adb 连接不稳定（vivo 特有）

**现象**：`adb devices` 时有时无；测试跑到一半报

```
adb.exe: device '10CF1N1XSG0017C' not found
Could not find a connected Android device in 20000ms
```

**根因**：vivo 的 USB 策略比较激进，锁屏/仅充电模式会主动断 adb。

**排查清单**：

1. 换机箱背后的主板 USB 口，不要用前面板 / hub
2. 换一根**数据线**（很多充电线没有数据通道）
3. 屏幕解锁并**保持亮着**
4. 通知栏 → USB 用途改成**「传输文件」**，不要停在「仅充电」
5. 开发者选项 → **撤销 USB 调试授权** → 重新插线 → 手机上点「允许」
6. 开发者选项 → 打开**「保持唤醒 / 充电时屏幕不休眠」**

**自检**（要连续 5 次都稳定出现 device 才算好）：

```powershell
1..5 | % { C:\Android\Sdk\platform-tools\adb.exe devices; Start-Sleep 3 }
```

---

## 坑 12：Appium server 随 shell 退出被杀

**现象**：后台启动 appium，bash 一退出进程就没了，`curl /status` 立刻 connection refused。

**根因**：Windows 上子进程随父 shell 退出而被终止。`run_in_background`、`nohup` 都挡不住。

**解法（推荐）**：同一条命令里启动 appium + 跑测试，保证服务在测试期间存活。

```bash
cd /c/.../testdev-portfolio
export ANDROID_HOME="C:\\Android\\Sdk"
appium.cmd --address 127.0.0.1 --port 4723 --base-path / > appium.log 2>&1 &
sleep 15
python -m pytest automation/test_appium_login.py -v -s
```

**注意**：`cd ... && appium ... &` 这种写法，末尾的 `&` 会把**整条 `cd && appium`** 丢进后台，
主 shell 的工作目录没变，后面 pytest 就找不到文件。**`cd` 必须单独一行。**

---

## 坑 13：后台 server / Appium 子进程不随 shell 退出，占端口吐旧页面

**现象**：订单用例 fixture 里 `document.getElementById('order_panel')` 直接报 `null`；
或 `find_element(CSS, "#btn_add_cart_1")` 找不到元素；或某次改完 `server.py` 后 Chrome 看到的还是旧页面。

**根因**：测试命令里 `app/server.py &` 和 `appium.cmd &` 是后台子进程。
**当前 bash 任务结束后这些子进程不会跟着死**，会一直霸占 5000 / 4723 端口。
下一轮测试再 `&` 起一个 server 时，因为端口已被占，**新 server 绑定失败、根本没起来**，
Chrome / curl 实际访问的还是上一轮那个残留旧进程吐的旧页面——自然没有新加的 `order_panel`、旧接口。

**排查**：看服务端返回的页面字节数 / 关键节点是否齐全即可一眼识破：

```bash
curl -s http://127.0.0.1:5000/ | wc -c            # 旧页 ~1816 字节，新页 ~5750 字节
curl -s http://127.0.0.1:5000/ | grep -c order_panel   # 旧页 0，新页 2
```

**解法（必做）**：每条测试命令开头，先按端口强杀残留进程再起服务：

```bash
free_port() {
  local port=$1 pid
  pid=$(netstat -ano 2>/dev/null | grep ":$port " | grep LISTENING | awk '{print $5}' | head -1)
  [ -n "$pid" ] && taskkill /F /PID "$pid" 2>/dev/null && sleep 1
}
free_port 5000   # MiniMall
free_port 4723   # Appium
```

> 实测 `pkill -f server.py` 在 Git Bash 下经常杀不掉 Windows 宿主进程，必须拿到 PID 用 `taskkill /F /PID` 才行。

---

## 坑 14：chromedriver（W3C 模式）不认 `id` 定位策略

**现象**：`find_element(AppiumBy.ID, "btn_login")` 直接抛

```
selenium.common.exceptions.InvalidArgumentException: invalid argument: invalid locator
```

**根因**：Appium 3.x 走 W3C WebDriver 协议，chromedriver 只认 `css selector` / `xpath` 等标准策略，
**不认 `id` 这个 strategy**（原生的 UiAutomator2 才认 `resource-id`）。所以 `By.ID` 在 Chrome 会话里一律报 `invalid locator`。

**解法**：H5 元素统一用 CSS 选择器：`#id`、`input#username`、`button#btn_login` 等。

```python
from selenium.webdriver.common.by import By
CSS = By.CSS_SELECTOR
drv.find_element(CSS, "#btn_login").click()
drv.find_element(CSS, "#username").send_keys("alice")
```

> 同理 `AppiumBy` 在 chromedriver 会话里也别用；直接用 selenium 的 `By.CSS_SELECTOR` / `By.XPATH`。

---

## 最终可用的完整流程

```bash
# 0. 前置：手机 USB 连好 + 解锁 + 传输文件模式
C:\Android\Sdk\platform-tools\adb.exe devices

# 1. 启动 Appium（同一条命令里跑测试，避免服务被杀）
cd C:\Users\bfdym\WorkBuddy\2026-09-05-23-54-54\testdev-portfolio
set ANDROID_HOME=C:\Android\Sdk
start "" appium  # 或保持一个窗口常开

# 2. 跑真机用例
python -m pytest automation/test_appium_login.py -v -s
```

---

## 面试怎么讲

> "配 Appium 真机环境时，npm 装驱动中断留下大量半截包，我写脚本按 shrinkwrap 清单
> 做了全量文件比对修复。过程中定位了两个上游问题：驱动 package.json 用 `;` 分隔命令
> 在 Windows cmd 下不兼容；以及 npm 发布包不含 tsconfig.json 却让 prepare 钩子跑
> tsc 构建，等于把预编译产物删了再构建失败——用 `--ignore-scripts` 绕开。
> 最后是 vivo 真机的 adb 掉线问题，属于厂商 USB 策略，靠传输文件模式 + 保持唤醒解决。"

这段话能同时体现：**问题定位能力、读上游源码/配置的能力、自动化修复的工程能力、真机适配经验**。
