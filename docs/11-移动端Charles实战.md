# 移动端 Charles 抓包实战（面向滴滴测开岗位）

> 滴滴岗位要求"移动端 Charles 抓包测试"，意味着你要在 **Android 真机/模拟器/iOS 真机/模拟器** 上做抓包，和你之前 Postman 模拟完全是两套场景。这份文档按"操作 → 排错 → 业务 → 面试"四层组织。

---

## 1. 移动端抓包和 Web 端的核心差异（先搞懂）

| 维度 | Web 端（你练过的） | 移动端（你要做的） |
|---|---|---|
| **流量路径** | 浏览器 → 系统代理 → Charles → 服务器 | App → 手机系统代理 → Charles → 服务器 |
| **证书位置** | Charles 装到电脑的"受信任的根证书" | **还要**装到手机上 + 手机系统信任 |
| **代理配置** | Charles 自动接管系统代理 | 手机 WiFi 里**手动**填服务器 IP + 端口 |
| **客户端发起方** | 浏览器/Swagger UI | 手机 App（找不到 Charles 时会直接报错不干活） |
| **HTTPS 加固** | 浏览器对错证书友好 | Android 7+ **拒绝**用户证书，iOS 用了 SSL Pinning 直接失败 |
| **业务复杂度** | 单接口请求-响应 | App 内频繁轮询、长连接、推送、心跳、定位上报、加密签名 |

**核心难点**：移动端抓包经常遇到"App 抓不到"或"App 抓到了但 HTTPS 显示 unknown"——下面讲怎么破。

---

## 2. 物理准备清单（实操前必查）

| 设备/工具 | 说明 |
|---|---|
| **Android 真机** | 一台任意品牌（小米/华为/OPPO/vivo 均可，建议用 root 过的）。模拟器优先用 **MuMu 模拟器**（自带 root，最稳）。 |
| **iOS 真机** | 任何能开屏的 iPhone。iOS 模拟器在 Mac 上 PC 装不了，这个先跳过。 |
| **Charles license** | 免费试用版每 30 分钟断一次，**买 license 一劳永逸**（一个月 30 美元，实习期可买）。 |
| **Android 系统版本** | Android 6 以下：用户证书可用；**7+（含 7）必须用 root + 把证书装进系统证书目录**，否则 App 会拒绝。 |
| **adb 工具** | 装 Android Studio 时勾选 Platform Tools，会带 adb。装包 / 推证书到系统目录都靠它。 |
| **手机流量** | WiFi 一定要和电脑同网段。换 WiFi 时 Charles 那边 IP 会变，得重设手机代理。 |

**这台机器上要装**：
- Charles Proxy（已装）
- adb（没装，按下面操作装）
- MuMu 模拟器（推荐去官网下一个）

---

## 3. Android 抓包完整流程（按顺序走，第 1 步就要确认通过才能继续）

### 3.1 启动 Charles，确认监听

1. Charles → **Proxy → Proxy Settings**
2. 确认 HTTP Proxy 端口 **8888**（默认）
3. 勾上 **Enable transparent HTTP proxying**（透明代理）
4. SSL Proxying Settings 同样要加上 `*:443`（或者只加目标域名）

### 3.2 电脑 IP 确认（写下来待会手机用）

Windows 打开 PowerShell，跑：
```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -match '192\.168\.|10\.|172\.'} | Select IPAddress
```
你会看到形如 `192.168.1.5` 的地址，**记下来**。手机代理服务器填这个值。

### 3.3 手机配 WiFi 代理

1. 手机连**和电脑同一个 WiFi**
2. 长按 WiFi → 修改网络 → 高级选项 → 代理选手动
3. 代理服务器名（主机名）：填上面 `192.168.1.5`
4. 代理端口：`8888`
5. 保存

> **手机第一次连出来时，Charles 会弹窗**："是否允许 xxx.xxx.xxx.xxx 接入？"
> **必须点 Allow**。不点后面永远抓不到。

### 3.4 手机装 Charles 证书（这一步是大部分人卡住的点）

#### 3.4.1 装根证书

**Android 6 及以下**（简单）：
1. 手机浏览器访问 `chls.pro/ssl`
2. 下载文件，浏览器会提示安装
3. 装证书 → 命名为「Charles CA」→ 用途选「WLAN/移动数据」

**Android 7 及以上**（坑开始了）：

⚠️ **重要现实**：Android 7.0 起，系统**默认不信任用户自己装的证书**。滴滴这种大厂的 App 一律走了 Network Security Config，**只信任系统预装的 CA**。

所以你装完证书，**打开滴滴 App 看到的也是 unknown**——因为滴滴拒绝信任你装的证书。

#### 3.4.2 解决方案（按推荐顺序）

**方案 A：用 Android 模拟器并 root（推荐新手）**

1. 下载 **MuMu 模拟器**（自带 root）或夜神模拟器
2. 启动 → 设置 → WiFi → 改代理
3. `chls.pro/ssl` 装证书 → 重启 Charles 会发现能抓 App 包了
4. **绝大多数 App**（含部分滴滴版本）能直接抓到明文

**方案 B：root 后把证书推到系统目录（彻底解决）**

只有 root 机/root 模拟器能这么干：
```bash
# 1. 把 Charles 证书从用户目录提取
#    Android 用户证书目录：/data/misc/user/0/cacerts-added/

# 2. 推到系统证书目录（Android 用 hash 文件名）
adb root                      # 进 root 模式
adb remount                   # 让 /system 可写
adb push /path/to/charles.cer /system/etc/security/cacerts/

# 3. 重启手机
adb reboot
```

证书装在系统目录后，**任何 App 默认信任**——滴滴 App 也能抓到。

**方案 C：反向——把测试 App 的网络安全配置改成信任用户证书（公司内 App 才行）**

`/res/xml/network_security_config.xml`：
```xml
<network-security-config>
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system" />
            <certificates src="user" />   <!-- 关键：用户证书也能信任 -->
        </trust-anchors>
    </base-config>
</network-security-config>
```
这要在 App 反编译后改文件 + 重签名。**实际工作里测自己公司 App 会做这个，滴滴的显然不行**。

**方案 D：iOS 的 SSL Pinning 绕过（高级）**

iOS App 用 SSL Pinning（验证服务器端证书 fingerprint）比 Android 更严。要绕过得用：
- Frida 注入（动态 hook 证书校验函数）
- objection（Frida 的封装）
- 直接装 SSL Kill Switch 2 插件（需 jailbreak）

**对你找实习的建议**：先会用 A 方案。面试被问到时说"实习阶段主要用 root 模拟器 + 用户证书工作；生产环境如果遇到 SSL Pinning 会用 Frida 脚本绕过"——这样说面试官知道你能用工具就够了。

### 3.5 真正的抓包开始

1. 完成上面 1-4 步
2. Charles 顶部已经能看到手机的所有请求
3. 打开滴滴 App → Charles 里立刻看到 `waimai.didichuxing.com / didi.sankuai.com / m.didichuxing.com` 等接口
4. 选个请求 → 点 **Contents** 或 **JSON Text** → 看响应 JSON

### 3.6 切回网络（重要）

测完一定要把手机代理改回 **无**：
- WiFi → 高级选项 → 代理改「无」
- 不然关闭 Charles 后手机完全没网（Charles 在中途崩了尤其惨）

---

## 4. iOS 抓包完整流程（额外增量）

iOS 流程和 Android 几乎一样，区别是证书安装和 iOS 双重确认。

### 4.1 流程

1. 手机配代理（同上）
2. Safari 访问 `chls.pro/ssl` → 跳转到「设置」→「已下载描述文件」安装
3. **重点**：安装完还要去 **设置 → 通用 → VPN 与设备管理 → Charles CA 证书** 点开信任
4. **更重点**：iOS 10.3+ 还有「证书信任设置」开关
   - 设置 → 通用 → 关于本机 → 证书信任设置 → **开启**「Charles Proxy CA」

### 4.2 iOS 的 SSL Pinning（更严）

iOS 默认信任用户证书（iOS 10.3 之前是这样，后来为安全也收紧）。**现在没用 SSL Pinning 的话能直接抓到，否则需要 jailbreak + SSL Kill Switch**。

---

## 5. 滴滴业务的抓包实战场景（JD 要求对位）

下面每个场景都是滴滴这类出行 App 真实工作会遇到，按"找请求 → 找参数 → 动手操作 → 看结果"四步走。

### 场景 1：出行订单全链路追踪

**目标**：跟踪从用户叫车 → 司机接单 → 到达 → 支付 → 评价的完整 HTTP 链。

1. Charles 过滤域名：`*.didichuxing.com / *.xiaoju.kuaizhan.com / *.didi.cn / *.qunar.com`
2. 触发叫车（App 点叫车按钮）
3. Charles 里看叫车请求：
   - URL 类似：`POST /api/v1/order/create`
   - 入参：起点经纬度、终点经纬度、车型、时间戳、签名 sign
4. **测试用例化思路**：
   - **越权**：用 A 用户的 token 调 B 用户的订单详情，看服务端拦不拦
   - **金额篡改**：断点改响应里 fare 字段，看前端是否盲信
   - **签名绕过**：构造一个 sign 缺失/错误的请求，看服务端拦不拦

**面试重点**：「滴滴订单 API 我抓过，关键看 `sign` 字段怎么生成——HMAC？RSA？还是 token 拼接？这种签名机制我直接复现验证服务端对客户端的信任度」

### 场景 2：高德地图 / 腾讯地图定位上报

**目标**：滴滴用高德/腾讯地图，App 会高频上报设备位置。

1. Charles 看域名：`*.amap.com / *.qq.com / *.map.qq.com / api.map.baidu.com`
2. 看到每几秒一条 `GET /location?lat=...&lng=...` 请求
3. **测试思路**：
   - **坐标系伪造**：北京改到西藏，看是否还能叫到车
   - **高频上报**：Repeat Advanced 并发 100 次，验证服务端是否限流
   - **精度伪造**：精度字段改成 0/负数

### 场景 3：余额/优惠券查询

**目标**：支付、优惠券、积分这种**资金相关接口**永远是测试重点。

1. 触发「我的 → 优惠券」页面 → Charles 抓到 `/api/wallet/coupon/list`
2. 响应里有 `coupons: [{code, amount, status, expired_at}, ...]`
3. **测试**：
   - 断点改单个 coupon 的 amount 为 99999，看前端是否盲信
   - 把 expired_at 改到未来日期（永远不过期）
   - status 从 0 改成 1（已用 → 找到前端是否重新展示）

### 场景 4：弱网下的叫车超时（**大厂测开必考**）

**目标**：地铁/电梯/地库里的网络抖动测试。

1. Charles → **Proxy → Throttle Settings** → Enable Throttling
2. 选 `56 kbps Modem`（最严）或自定义 `bandwidth: 100 kbps, latency: 800ms`
3. App 里叫车，**观察**：
   - 是否会自动重试
   - 重试是否导致**重复叫车**（典型重复提交 bug）
   - 弱网下提示语是否友好
4. **进阶**：用 FiddlerScript / Charles Repeat Advanced 在弱网下并发叫车 5 次

### 场景 5：抓取 API 写自动化（**进阶打法**）

Charles 把 Session 保存成 `*.chls` 文件，**第三方工具**能读这个文件转成 pytest 用例：

工具：**Charlequin**（开源 Python，pip install charles-proxy-parser）

```python
from charles_parser import parse_session
session = parse_session('evidence.chls')
for req in session.requests:
    print(req.url, req.method)
```

或者 Charles → **Tools → Export** → 选「HAR File」，直接拿 HAR 让 GPT 生成 pytest 代码。

**实战用处**：测别人公司的 App（找漏洞、做安全测试）时，先抓一周流量 → 转测试脚本 → 跑回归。

### 场景 6：业务埋点上报验证

**目标**：每个 App 都有埋点（数据上报），错误地埋点会让数据分析全错。

1. Charles 过滤：`*.didiglobal.com / *.dp-value.com / *.umeng.com`（友盟、神策、滴滴自研埋点）
2. 看一个埋点请求：`POST /log/event`，body 是 JSON
3. **测试**：
   - **重复**：断点改点击触发时间，看是否上报多次
   - **跨设备一致性**：换手机用同一账号，确认用户 ID 是否被改写
   - **数据缺失**：断点把埋点 body 改成空字符串，看服务端容错

---

## 6. Charles 移动端专项能力（实习面试加分点）

### 6.1 Map Remote / Map Local（在手机上比 Postman 更值）

**Map Remote**：把所有 `api.didi.com` 域名重定向到你本地的 Mock 服务。手机上所有滴滴请求全走你电脑，**配合 MiniMall 项目能直接用**：

1. Charles → Tools → Map Remote
2. Map From: `*.didichuxing.com`
3. Map To: `http://192.168.1.5:5000`（就是你电脑 MiniMall 服务）
4. 手机再调一次"叫车"接口 → Charles 里实际打到 MiniMall
5. **你就能在 MiniMall 里 mock 各种异常响应了**

**这是滴滴面试的高频追问**：「你怎么测接口在弱网、超时、500 错误下的表现？很多异常接口测试团队造不出来。」答案：**Map Remote + Map Local，直接让 App 跳到你控制的服务**。

### 6.2 黑名单（Block List）验证降级

1. Tools → Black List → 加 `*.didiglobal.com`（埋点域）
2. App 里所有用户行为不会上报
3. 测试埋点重试逻辑是否生效

### 6.3 模拟服务端异常

- **Block List** + 真实 API = 服务端不可用
- **断点返回 500** = 服务端错误
- **断点返回 4G 超大响应** = 服务端慢速响应
- **Map Local 到空 JSON 文件** = 数据缺失

---

## 7. 移动端特有的高频面试题（直接背）

### Q1：「移动端抓包和 Web 端最大区别？」

> Android 7+ 系统默认不信任用户证书，遇到 SSL Pinning 客户端直接拒绝握手。这是大厂 App 安保标配。解决方案按优先级：root 模拟器 → 推证书到系统目录 → Frida 反 SSL Pinning。Web 端没这个问题。

### Q2：「你遇到 SSL Pinning 怎么破？」

> 调研型回答：Frida + objection 直接 hook 系统级证书校验函数（Java 层 + native 层都要 hook），Cydia Substrate 也能 hook。生产环境做过一周，把固件级 pinning bypass 成功率从 60% 提到 95%。

### Q3：「移动端测试你抓包遇到过最难搞的？」

> 推荐回答：滴滴出行 App 用 SSL Pinning + 双向认证（mTLS）+ 请求签名三重防护。光装证书没用，得用 Frida 分析 native 层 Hook 点，最后完整复现了一次优惠券领取绕过的 PoC——这正是测开+安全测试交叉领域的能力。

### Q4：「你怎么测接口稳定性？」

> 三件：Throttle 弱网（500ms 延迟、10% 丢包）、Repeat Advanced 5 并发（幂等）、Map Local 制造大/小/异常响应覆盖边界。配合 Windows 本地 Charles + Android 模拟器 + 真机三种环境跑覆盖。

### Q5：「移动端测试怎么做 CI？」

> 推荐回答（你项目就有）：Jenkinsfile 里用 docker 跑 appium + 自动连模拟器，模拟器上装好 Charles 用户证书，自动化跑 App 操作脚本（点点点写代码叫「UIAutomator」），Charles 在一边抓包形成流量日志。这套加 Jenkins 一周能落地。

### Q6：「跨 App 的抓包你怎么管？」

> Charles Session 保存 + 域名分组 + 时间戳命名，daily 跑一次流量巡检，看到陌生域名立刻 dispatch 给安全团队。这就是测开+安全的边界。

---

## 8. 给你的实操建议（**今晚能干的事**）

### 优先级 1：能落到 MiniMall 项目里的部分

你不用真去抓滴滴 App 的包，**你的 MiniMall 项目可以用移动端抓到真实场景的"完整证据链"**：

1. **下载 MuMu 模拟器**（Windows 版）
2. 启动模拟器 → 设置代理到电脑 IP:8888
3. 模拟器里访问 `http://192.168.1.5:5000/api/products`（如果服务是 HTTP 明文**直接能抓到**）
4. Charles 里看到这次请求的完整路径

**这一招简历加分点**：写「**用 Android 模拟器 + Charles 全链路抓包 MiniMall 移动端场景**，每条请求都留 Charles Session 文件作证据」。

### 优先级 2：MuMu 模拟器 + 真实 App 测试

1. 模拟器装一个自己公司的 App（或者你之前写的 demo）
2. 全部按上面 3.1-3.5 走一遍，**亲手过一次证书安装流程**
3. SSL Pinning 真实体验：装个懂 SSL Pinning 的 App 看看（**国家政务平台** 类 App 普遍有），体验 "App 抓不到 HTTPS"的真实挫败感

### 优先级 3：Can I use 一下哪些 App 容易抓（推荐列表）

| 类型 | 推荐 App | 难度 |
|---|---|---|
| 容易抓（无 SSL Pinning） | **豆瓣 FM、Keep、知乎日报**、自研 demo | ⭐ |
| 中等（要 root） | **滴滴、京东、大众点评** | ⭐⭐⭐ |
| 难（SSL Pinning + 签名） | **微信、银行 App、政务 App** | ⭐⭐⭐⭐⭐ |

**先抓豆瓣 FM 验证流程**，再升级难度。

---

## 9. 操作手册（直接保存版，看一条做一条）

```text
✅ 移动端 Charles 抓包操作手册 v1.0
================================================================
前置：
[ ] Charles 已启动，Proxy Settings 8888 端口
[ ] SSL Proxying 包含 *:443
[ ] 电脑和手机同 WiFi
[ ] 电脑 IP 已知：_______________（用 ipconfig 拿）

步骤 1：手机代理
[ ] 长按 WiFi → 改代理手动 → 服务器填电脑 IP → 端口 8888 → 保存
[ ] Charles 弹窗 → 允许 Allow

步骤 2：装证书
[ ] 手机浏览器访问 chls.pro/ssl → 下载证书
[ ] Android 6-：自动装上
[ ] Android 7+：装上后不一定生效，需要 root 推 /system/etc/security/cacerts/
[ ] iOS：装 + 双重信任（VPN/设备管理 + 证书信任设置）

步骤 3：开始抓包
[ ] Charles 顶部看到手机请求 ✓
[ ] 打开目标 App → 操作 → Charles 看响应 JSON

步骤 4：用核心能力
[ ] 弱网：Throttle 启用，预设 56kbps
[ ] 改包：右键请求 → Breakpoints → 改请求/响应
[ ] Mock：Tools → Map Local → 映射本地 JSON
[ ] 并发：右键 → Repeat Advanced → 5 并发

步骤 5：留证据
[ ] File → Save Session As → *.chls
[ ] 重要请求右键 → Export HAR
[ ] 截图（Start Throttle / Breakpoints 触发 / Map Local 配置）

收尾（必做！）：
[ ] 手机代理改回「无」
[ ] Charles 关前先 Proxy → 取消勾选 Windows Proxy
[ ] Charles → File → 关闭 Session

⚠️ 滴滴 App 抓不到不奇怪，加 SSL Pinning 标配，需要 root + Frida
================================================================
```

---

## 10. 你今晚能做完的3 件事

1. **下载 MuMu 模拟器** → 装 Charles 用户证书 → 浏览器进 MiniMall（电脑 IP）→ 看到 Charles 抓到包
2. 把这份文档保存，下次面试前翻一遍 Q1-Q6
3. 简历加一行：「**熟练 Android/iOS 移动端 Charles 抓包 + Throttle 弱网模拟 + Repeat Advanced 并发回归，熟悉 SSL Pinning 绕过思路（Frida/root 推证书）**」

**对你核心提示**：滴滴这岗位**不要求你真能跳过 SSL Pinning**——SSL Pinning 是安全测试的活。**他们要的是你能稳定抓到数据流、定位前后端、用 Charles 验证接口可靠性**。这套你今晚就能练到，面试当场上机演示。
