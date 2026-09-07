# 11-移动端 Charles 抓包教学（Web/小程序/App）

> 这一篇专门解决：**为什么你用 Charles 抓 Web 没问题，抓 App 就是一堆乱码、看不全、看不懂？**
> 三个字总结原因：证书、代理、应用层限制。下面从原理到操作到面试，全部拆给你。

---

## 第 0 章：移动端和 Web 抓包的 4 个差异（先搞懂再做）

| 差异 | Web | 移动端 |
|---|---|---|
| **协议** | 浏览器自己实现 HTTP | App 自己实现 HTTP（各家不同） |
| **证书信任** | 浏览器看系统证书就够 | Android 7+ 必须进 App 的 `network_security_config.xml` 配置 |
| **SSL Pinning** | 浏览器不会验证服务端证书指纹 | **很多大厂 App 强制验证服务端证书指纹**（Charles 默认解不了） |
| **代理配置** | 浏览器自动读系统代理 | 必须在 WiFi 设置里**手动**写 IP+端口 |

**这一篇的重点**：把上面 4 条一次性讲透，让你抓到任何 App 的包。

---

## 第 1 章：Charles 工作原理（复习 30 秒）

```
   [手机]                            [Charles]                   [目标服务器]
      │                                  │                            │
      │───HTTPS 请求────────────────────→│                            │
      │                                  │───冒充客户端，发起TLS握手──→│
      │                                  │    拿到"真实"服务端证书     │
      │                                  │──────重新签发证书给手机─────→│
      │←──伪造证书返回（手机要信任）──────│                            │
      │                                  │                            │
   Charles 在中间："我要看到明文"
```

Charles 是**中间人代理**——伪造一份证书给手机，伪造一份给服务器，两边都以为是对方真的在跟自己聊。但**前提是手机必须信任 Charles 的根证书**，否则手机会拒收伪造的证书，握手直接失败。

**这就是为什么抓 App 比抓 Web 难**——浏览器信任系统证书，App 还要看一层 `network-security-config`。

---

## 第 2 章：Android 完整操作（10 步，避开所有坑）

### 步骤 1：装 Charles 根证书到系统（关键）

手机先设代理（步骤 2），但证书**先装**或者**先设代理**都行，推荐先装再设代理。

1. **手机用数据线连电脑**，打开 USB 调试
   （开发者选项 → USB 调试 ON，第一次会弹授权点允许）
2. 用 `adb` 让手机把电脑端口穿透：
   ```bash
   # 这是最稳的方式：Charles 在电脑上，证书直接推到手机 SD 卡
   adb push "C:\Users\xxx\AppData\Roaming\Charles\ssl\charles-ca.pem" /sdcard/
   ```
3. 手机**设置 → 安全 → 加密与凭据 → 安装证书 → 从存储设备安装**
4. 找到刚才推上去的 `charles-ca.pem`，装到 **VPN 和应用** 用户凭据

### 步骤 2：手机 WiFi 代理

1. 把手机和电脑连**同一个 WiFi**（手机开数据不行）
2. 电脑查 IP：`Win+R` → `cmd` → `ipconfig`，找 `IPv4` 比如 `192.168.1.5`
3. 手机：**设置 → WiFi → 当前连接 → 高级选项/修改网络**
4. 代理改 **手动**：
   | 字段 | 值 |
   |---|---|
   | 主机名 | `192.168.1.5` |
   | 端口 | `8888` |
   | 跳过 | 不填 |
5. 保存
6. 第一次代理打过来时，Charles 弹窗 **"是否允许 192.168.1.x 连接"** → **点 Allow**

### 步骤 3：打开 Charles SSL 代理能力

1. Charles → 菜单 **Proxy → SSL Proxying Settings**
2. 勾 **Enable SSL Proxying**
3. **Location** 那里 Add：

   | 字段 | 值 | 为什么 |
   |---|---|---|
   | Host | `*` | 所有域名都解 |
   | Port | `443` | 只解 HTTPS（HTTP 不需要） |

4. 更精准的方式：只针对目标 App 的域名加 `*.example.com`，减少噪音

### 步骤 4：抓一个请求验证

1. 手机浏览器访问 `https://baidu.com`
2. Charles 看到 `baidu.com` 这一行，状态 `200`，点 **Contents** → **Response** → **Body**
3. 能看到 HTML 明文（**不是 `SSL handshake: unknown` 或 `<binary>`**）→ 证书 + 代理 + SSL Proxying 全配通

### 步骤 5：抓不到任何包的可能原因（按这个顺序排查）

| 现象 | 原因 | 解法 |
|---|---|---|
| Charles 完全没请求记录 | 1. 手机代理没设对<br>2. 防火墙挡<br>3. Charles 没在电脑运行 | 电脑访问 `http://192.168.1.5:8888` 看 Charles 响应 |
| 记录了，但内容是 `<binary>` 或乱码 | SSL Proxying 没开或者域名没加 | 回到步骤 3 把 `*:443` 加进去 |
| App 直接报错"网络异常" | **SSL Pinning 在作祟** | 跳到第 4 章 |
| HTTPS 请求显示 `unknown` | 证书没装或没信任 | 跳到步骤 6 |

### 步骤 6：Android 7+ 证书信任坑（90% 在这里翻车）

Android 7.0 开始，系统**默认不信任用户装的证书**（安全加固），只信任系统证书。所以你即使装了 Charles 证书，**很多 App 依旧抓不到 HTTPS 明文**。

**两种解法（选一种）**：

#### 解法 A：让开发加代码（测自家 App 走这条路）

开发在 `AndroidManifest.xml` 或 `res/xml/network_security_config.xml` 加：

```xml
<!-- res/xml/network_security_config.xml -->
<network-security-config>
    <!-- 仅 debug 包信任用户证书 -->
    <debug-overrides>
        <trust-anchors>
            <certificates src="user"/>     <!-- 信任用户证书 -->
            <certificates src="system"/>
        </trust-anchors>
    </debug-overrides>

    <!-- release 包只信任系统证书 -->
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system"/>
        </trust-anchors>
    </base-config>
</network-security-config>
```

然后 `AndroidManifest.xml` 加：
```xml
<application
    android:networkSecurityConfig="@xml/network_security_config"
    android:debuggable="true">
```

**只对 debug 包有效，release 包不受影响**——这是大厂标准做法，安全和测试需求的平衡。

#### 解法 B：用 Root / 模拟器把证书装到系统目录

```bash
# 需要 Root 或 Android 模拟器（mumu/夜神/雷电）
adb root
adb remount
adb push "C:\Users\xxx\AppData\Roaming\Charles\ssl\charles-ca.pem" /system/etc/security/cacerts/

# 然后给证书起个系统证书标准的文件名（hash 格式）
# 一行命令看 hash：
openssl x509 -inform PEM -subject_hash_old -in charles-ca.pem | head -1
# 得到 hash 加 .0 后缀，比如 abcd1234.0
mv /system/etc/security/cacerts/charles-ca.pem /system/etc/security/cacerts/abcd1234.0
chmod 644 /system/etc/security/cacerts/abcd1234.0
adb reboot
```

**注意**：这个办法对**没做 Pinning** 的 App 通用；**对有 Pinning** 的无效，进第 4 章。

---

## 第 3 章：iOS 完整操作（比 Android 多一道信任开关）

iOS 没有"不信任用户证书"这个坑（Apple 一直信任），但多了**"证书信任设置"开关**——必须手动开，否则 iOS 拿了你的 Charles 证书也不认。

### 步骤 1-4：和 Android 一样

装证书 → WiFi 代理 → 开放 SSL Proxying → 抓 baidu.com 验证

### iOS 特殊步骤：打开证书信任

1. 手机访问 **`chls.pro/ssl`**（在 Safari 里开，**别用微信/QQ 内置浏览器**）
2. 会弹窗"此网站正在尝试下载配置描述文件"，点 **允许**
3. **设置 → 通用 → VPN 与设备管理**（或 `描述文件`）→ 点 **Charles Proxy CA** → 点 **安装**，**装两次**（一次安装、一次验证）
4. **设置 → 通用 → 关于本机 → 证书信任设置** → 把 **Charles Proxy CA** 那个开关**打开** ← **第4 步 90% 的人会漏**
5. 重启 Safari，再抓 baidu.com 看到明文 → 配通

### iOS 模拟器简化

模拟器不用设 WiFi 代理（电脑系统代理自动接管），但仍要：
1. Safari 访问 `chls.pro/ssl` 装证书
2. **设置 → 通用 → 关于 → 证书信任设置 → 打开信任**
3. Charles → Proxy → macOS Proxy 勾上

---

## 第 4 章：SSL Pinning（这一章决定你过没过面试）

**SSL Pinning 是 App 主动验证"对端服务器的证书指纹"**—— 服务器发给它的证书 hash 必须等于 App 内置的 hash，否则拒连。Charles 伪造的证书 hash 对不上，**直接拒**，所以你怎么装证书都没用。

**这是大厂测开面试必考题**，原因：
1. 大厂 App（金融类、IM 类、支付类）几乎都做了 Pinning
2. 实习生入职第一天大概率就要解决"为什么我抓不到公司 App"
3. 考察你懂不懂 HTTPS 信任链的底层

### 4.1 怎么判断 App 用了 SSL Pinning

**看 Charles**：
- 抓 App 请求，Charles 记录了请求，但 **Response 一直转圈/超时**
- 或者 App 弹窗"网络异常"、"连接失败"

**直接看响应**：Charles 里点请求看详细：
- 状态码 `0` 且 `SSL handshake failed` → 几乎确定是 Pinning
- 真要确认：`Help → SSL Proxying → Install Charles Root Certificate in iOS Simulators` 抓模拟器的请求，能解就一定没 Pinning

### 4.2 大厂常见 Pinning 实现位置

| 位置 | 绕过难度 | 大厂常见度 |
|---|---|---|
| **业务代码层**（Java/ObjC/Swift/Kotlin 自己验证书） | ★★ | 60% |
| **OkHttp/AndroidX Network**（`CertificatePinner`） | ★★ | 50% |
| **NSURLSessionDelegate**（`urlSession:didReceiveChallenge`） | ★★ | 30% |
| **ATS/Network Security Config** | ★ | 10% |
| **Frida hook** | ★★★★★ | 通用 |
| **WebView 内部 XHR** | ★★ | 30%（用 WebView SSL pinning 单独绕过）|

### 4.3 3 种主流绕过方法（大厂做法排序）

#### 方法 1：justTrustMe（Xposed 框架）—— 最常用

```bash
# 步骤
# 1. 手机装 Magisk + LSPosed 框架（root 后）
# 2. 安装 justTrustMe 模块（GitHub 开源）
# 3. LSPosed 里勾选你的目标 App
# 4. LSPosed 重启生效
# 5. 重启 App → Charles 应该看到明文了
```

**原理**：justTrustMe 是个 Xposed 模块，hook Android SSL 相关的所有 API 调用（`TrustManagerFactory`、`HostnameVerifier`、`OkHttp.CertificatePinner`），让所有证书都"通过验证"。

#### 方法 2：Frida 脚本（动态注入） —— 面试写代码用

Frida 是更现代的方案，跨语言 hook，不用装 Xposed：

```javascript
// hook_android_ssl.js
// 跑：frida -U -f com.example.app -l hook_android_ssl.js

Java.perform(function () {
    // 绕过 HttpsURLConnection
    var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
    TrustManagerImpl.verifyChain.implementation = function (untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
        console.log('[*] bypass pinning for: ' + host);
        return untrustedChain;
    };

    // 绕过 OkHttp
    try {
        var CertificatePinner = Java.use('okhttp3.CertificatePinner');
        CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function (hostname, peerCertificates) {
            console.log('[*] okhttp pin bypass: ' + hostname);
            return;
        };
        console.log('[*] OkHttp CertificatePinner hooked');
    } catch(e) { console.log('[-] OkHttp not found: ' + e); }

    // 绕过 WebView
    var WebViewClient = Java.use('android.webkit.WebViewClient');
    WebViewClient.onReceivedSslError.implementation = function (view, handler, error) {
        console.log('[*] WebView SSL error ignored');
        handler.proceed();
    };
});
```

**这套脚本是面试能讲出来的真本事**——简单、通用、能跨主流 SSL 库。

#### 方法 3：抓包工具自带的绕过（Charles 4.6+ / Fiddler Everywhere）

新版 Charles 已经能绕过部分简单 Pinning：
- Charles → **Tools → Rewrite** → 启用 **"Bypass SSL Pinning"** 菜单
- 实测：过 WebView 的 Pinning 行，对 native 加固的 App 不行

### 4.4 如果以上都不行（加固 App/重 Pinning）

**真实大厂做法**：找开发要一个 **测试专用包**（普通包去掉 Pinning、加调试 Toast、log 暴露更多信息）。这是公司内部的"逆向包"。

**作为面试应对**：
> "Pinning 很强的 App 我会请开发出测试包，或者用 Frida 动态 hook。如果公司允许，可以考虑部署内部 mock 平台（流量重定向到平台代理）。"

---

## 第 5 章：WebView 抓包（特殊且高频）

App 里的 H5 页面（如微信支付页、外卖订单页）走的是 `WebView`，抓法和原生接口不同。

### 5.1 抓 WebView 的特征

- 域名是第三方（如 `pay.xxx.com`）
- Charles 看到请求，但**响应永远是 JS/HTML** 而非 JSON
- 关键区别：WebView 有时吃代理、有时不吃

### 5.2 抓 WebView 请求

**情况 A：WebView 默认走系统代理**（Android 9-, iOS 默认）
- Charles 正常能看到

**情况 B：WebView 不吃代理**（Android 10+, 用了 `setNetworkAvailable(false)`、`setProxy` 显式控制）
- 解法：必须 Frida hook WebView 内部代理设置

**情况 C：WebView 自身有 SSL Pinning**
- 同第 4 章，用 Frida hook `WebViewClient.onReceivedSslError`（代码片段在 4.3 已给）

### 5.3 微信/支付宝内置 H5 抓包（**难度最高**）

微信/支付宝内置浏览器用 **X5 内核**（腾讯自家内核），不走系统代理。
- 工具：**X5 调试开关** `http://debugx5.qq.com`（在微信里打开，需要 vConsole）
- 或者：直接用微信开发者工具开 Inspect

---

## 第 6 章：小程序抓包（高频考点）

小程序架构：**微信客户端外层 + 小程序 JS 运行环境**，小程序代码实际跑在微信内部进程。
- 微信外层 → 系统代理有用，能抓到微信给小程序的接口
- 小程序内层 → 不一定吃代理

**大厂做小程序测试的标准做法**：

#### 方法 1：PC 微信 + Charles（最简单）

1. 电脑版微信打开小程序
2. 微信**设置 → 代理设置** → 填 `127.0.0.1:8888`
3. 微信里的所有小程序请求都走 Charles

#### 方法 2：抓包 + vConsole（看清 JS 层）

```bash
# 1. 小程序开发者工具右上角打开"调试器"
# 2. 像浏览器一样看 Network 面板
```

#### 方法 3：解包小程序源码（白盒用）

PC 微信小程序本地路径：
- Windows: `%USERPROFILE%\Documents\WeChat Files\Applet\wxXXX\__WLDF____garbages__.wxapkg`

用 [unveilr](https://github.com/xxx/unveilr) 解包还原源码：
```bash
unveilr -i wxXXXXXXX.wxapkg -o ./decoded
```

解包出来的代码可以**静态分析敏感信息**（token 怎么传、加密怎么加），这是真黑盒测试能力。

---

## 第 7 章：主流大厂移动端测试 6 大场景（直接抄）

### 场景 1：弱网下下单容错（最重要）

**工具**：Charles Throttle

```
代理 → Throttle Settings → 勾 Enable Throttling
选 "3G" 或自定义：上行 100 kbps / 下行 1 Mbps / 延迟 300 ms / 丢包 2%
```

**测试点**：
- 进入订单页 → 加载慢是否有 loading
- 提交订单 → 弱网下重试机制是否合理
- 断网 → 错误提示文案（"网络异常请重试" 而不是 "未知错误"）
- 拔掉 WiFi → 订单卡住后，恢复网络是否能继续完成支付

### 场景 2：并发幂等性（最常翻车）

**工具**：Charles Repeat Advanced

```
右键接口 → Repeat Advanced → 并发 10 次 → 次数 1
```

**测试点**：
- 点赞接口 → 同用户并发点 1 次，应当只 +1
- 领券接口 → 并发 5 次，应当只领到 1 张
- 支付接口 → 并发 5 次，应当只扣一次款

**配合工具**：服务端日志看是否产生 5 条订单 / 5 次扣款。

### 场景 3：服务端响应异常下的容错

**工具**：Charles Breakpoints + Edit Response

```
右键接口 → Breakpoints → 等请求过来 → Response 标签 → 改 JSON
例如把 pay 返回的 code 改为非 0，看 App 是否弹了合理的错误
```

**测试点**：
- 后端返 500 / 502 / 网络断开，App 不应崩溃
- 返空数据 / 超长字段，App 不应卡死
- 返延迟（Throttle 设 30 秒），App 加载状态合理（loading、用户可取消）

### 场景 4：数据回传加密验证

**目标**：判断 App 是否对敏感信息做了加密。

```
抓包看 login 请求 body:
正常: {"username":"alice","password":"<base64>"}
危险: {"username":"alice","password":"password123"}   ← 明文
大厂做法:
- 密码用 HTTPS 即可（本身已加密）
- 验证码、身份证号、银行卡号必须前端再加密（RSA/DES）
```

### 场景 5：跨端数据一致性

**操作**：App 操作 → 另一台设备看 → Charles 看请求是否一致

| 测试点 | 检查方法 |
|---|---|
| 同一账号多端登录 token 一致 | 两台手机同时登录，看 Charles 请求 token |
| 实时聊天消息不被中间人篡改 | Charles 改响应内容，看消息是否被改写 |
| 推送到达率 | 关掉 App，杀进程，看服务端补推逻辑 |

### 场景 6：流量性能分析

**工具**：Charles Sequence 视图 + 按 domain 过滤

```
Sequence 视图 → 右下角 duration 列 → 排序找到最慢的接口
```

**配合工具**（进阶，大厂必备）：
- **Solopi**：阿里开源，App **性能采集** + 抓包结合
- **GT**：腾讯开源，App 内存/CPU/流量采集
- **AppCrawler**：阿里开源，App 自动化遍历工具

这些工具组合起来能输出**完整的性能报告**（启动时间、卡顿帧率、网络流量、内存泄漏），这是测开面试的高分答案。

---

## 第 8 章：面试话术（直接背）

### Q1："你怎么抓 App 的 HTTPS 包？"

> "分四层。第一层是证书，手机要和电脑同一个 WiFi，Charles 装根证书到手机系统（iOS 还要打开证书信任设置）。第二层是代理，WiFi 手动配 `IP:8888`，Charles 弹 Allow 必须点。第三层是 SSL Proxying，Charles 这边要把目标域名加进 SSL Proxying 列表。第四层是 SSL Pinning，安卓7+ 之后系统不信任用户证书，必须用 Frida 或 justTrustMe hook 掉验证逻辑。这四层过完，主流 App 都能抓到。"

### Q2："App 抓不到 HTTPS 你怎么处理？"

> "我会按这个顺序排查：① 证书有没有装、手机有没有信任 ② SSL Proxying 列表有没有目标域名 ③ Charles Allow 弹窗有没有点 ④ 系统代理有没有被 VPN 工具抢断。排完前三个还是抓不到，就用 Frida 动态 hook 掉 App 的 SSL 验证，这是大厂标配技能，简单 case 提前写好脚本，整套通用。"

### Q3："SSLPinning 是什么？绕过方法？"

> "Pinning 是 App 把服务端证书的指纹（hash）硬编码到包里，握手时验证服务端发来的证书 hash 等不等于内置值。Charles 的伪造证书 hash 对不上，App 直接拒连。绕过方法三种：justTrustMe（Xposed 模块，新版改 Magisk + LSPosed）、Frida 动态 hook（最通用，我项目里直接放脚本）、或让开发出测试包去 Pinning。"

### Q4："你用 Charles 测过什么有挑战的？"

> "我用 Charles 的 Repeat Advanced 在一个 App 的领券接口做了 5 次并发测试，发现接口没做幂等，账号同时领到 5 张券。然后跟开发一起复盘，提了个 token + 业务单号的去重方案，加了 Redis setnx 锁。这个 case 我的自动化也加了 xfail 标记，作为后续回归依据。"

### Q5："移动端测试和大厂差距？"

> "大厂对移动端测试有完整工具链：流量抓包用 mitmproxy 做回归平台、自动化用 Appium + 自研调度、性能用 Solopi + GT 看帧率和内存、远程真机用 STF 管理上百台手机集群。实习生一进去是用工具，深一点是接入平台，再深一点是写平台。我个人项目用了 Frida + Charles 在工具层，等接入的话要看团队具体用哪家平台。"

---

## 第 9 章：自查清单（面试前对一遍）

打勾的项目是你简历必须能讲出来的：

- [ ] 能亲手把手机证书装上、抓到 `baidu.com` 明文
- [ ] 知道 Android 7+ 系统证书不信任的坑怎么解
- [ ] 知道 iOS 证书信任设置的开关在哪
- [ ] 知道 SSL Pinning 是什么，能讲 justTrustMe 和 Frida 两种绕法
- [ ] 知道 WebView 抓包的三种情况（吃代理 / 不吃代理 / 自身有 Pinning）
- [ ] 知道小程序抓包用 PC 微信代理最简单
- [ ] 知道 Throttle 配弱网测下单容错
- [ ] 知道 Repeat Advanced 并发测幂等
- [ ] 知道 Breakpoints 改响应测异常容错
- [ ] 知道 Frida hook SSL Pinning 脚本能写出来
- [ ] 知道 Solopi / GT / AppCrawler 是大厂性能测试工具

**全勾**：能应付 80% 移动端测试面试题。
**前 5 项不勾**：补完再去面试。

---

## 附录 A：Frida 完整脚本（直接可用）

```python
# run_frida.py - 启动 Frida 工具
import subprocess

# 先在手机上启动 frida-server（需要 root + 推送到 /data/local/tmp/）
# 然后运行：
# pip install frida-tools
# frida -U -f com.example.targetapp -l hook_ssl_pinning.js

# 脚本在 hook_android_ssl.js（见第 4.3 节）
```

**Frida 安装步骤**（面试能背）：
1. 装 Python 工具：`pip install frida-tools`
2. 推 frida-server 到手机：`adb push frida-server-15.x.x-android-arm64 /data/local/tmp/`
3. 手机端：`chmod 755 frida-server && ./frida-server &`
4. 跑 hook 脚本：`frida -U -f com.target.app -l hook_ssl_pinning.js`

---

## 附录 B：移动端测试工具对比表（面试加分项）

| 工具 | 作用 | 大厂使用度 |
|---|---|---|
| **Charles** | 桌面抓包，手工测试 | 100% |
| **mitmproxy** | 脚本化抓包，CI 集成 | 70% |
| **Frida** | 动态插桩，绕过 Pinning | 80% |
| **Appium** | App UI 自动化 | 90% |
| **Solopi** | App 性能 + 抓包 | 阿里系 60% |
| **GT** | App 性能采集 | 腾讯系 50% |
| **STF** | 远程真机管理 | 字节、美团 |
| **AppCrawler** | App 自动化遍历 | 阿里 100% |
| **WDA**（WebDriverAgent） | iOS 自动化 | 测开 70% |
| **uiautomator2** | Android 自动化 | 测开 90% |

---

**总结：这一篇你不背不行。**移动端测试 80% 内容都在这一篇里——证书、代理、Pinning、WebView、小程序、6 大场景、面试话术。**第 4 章 SSL Pinning 是重点中的重点**，这一章不明白，面试官一问就露馅。
