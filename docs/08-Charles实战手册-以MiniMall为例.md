# Charles 实战手册 —— 以 MiniMall 为例

> 你的环境：MiniMall 后端跑在 `http://127.0.0.1:5000`（纯 HTTP，本地回环，不需要装证书）
> 工具：Charles 4.x/5.x（试用版够用，每 30 分钟重启一次）
> 客户端建议：Postman（设代理）或 curl（加 `--proxy`）

## 第 0 步：环境就绪

1. 启动 MiniMall（已为你启动好了；如果关了重启）：
   ```bash
   python -m venv .venv && .venv\Scripts\activate
   pip install -r app/requirements.txt
   python app/server.py
   ```
   看到 `Running on http://127.0.0.1:5000` 即就绪。

2. 启动 Charles，弹出"是否设为系统代理"选 **Grant Privileges**（Windows 会弹权限框，允许）。

3. 验证抓到包：浏览器打开 `http://127.0.0.1:5000/api/products`，Charles 主界面应出现一条 `GET /api/products 200` 记录。
   - 如果没看到：检查 Proxy → Proxy Settings 里端口是不是 **8888**；检查系统代理/浏览器代理是否指向 `127.0.0.1:8888`。
   - 顺带设个 Include 只录本机：`Proxy → Recording Settings → Include → Add → 127.0.0.1`，避免噪音。

## 第 1 步：抓登录请求，看报文

目的：看清 HTTP 报文结构，验证"密码是否明文传输"。

1. 用 Postman 发：
   ```
   POST http://127.0.0.1:5000/api/login
   Content-Type: application/json
   Body: {"username":"test01","password":"123456"}
   ```
2. Charles 主界面点这条请求，下方两个标签：
   - **Contents 标签**：可看到 Request 区的 Method/URL/Headers/Body（密码明文 `123456`）、Response 的状态码/Body
3. 在请求上 **右键 → Copy cURL Request**，可以一行命令复现

**测试结论**：本地 HTTP 是明文 → 生产必须 HTTPS。落到测试报告里作为遗留风险。

## 第 2 步：模拟弱网（Throttle）

目的：验证弱网下下单是否有明确提示、有无脏数据（对应 NET-01/NET-02）。

1. `Proxy → Throttle Settings → Enable Throttling`
2. 选预设 `3G`（或自定义：带宽 400 kbps，延迟 300 ms）
3. 再用 Postman 下单：登录 → 加购 → `POST /api/order/create`
4. Charles 里能看到响应时间从 50ms 飙到 800ms+；Sequence 视图能看到 Throttling 图标 ⚠️ 标记
5. 取消 Throttle 验证恢复后功能正常

**测试结论**：弱网响应慢但仍成功 → 记录响应耗时；如果客户端有超时重试（很多 App 默认会），配合任务 4 会暴露幂等缺陷。

## 第 3 步：断点改包 —— 验证服务端校验

目的：用 Breakpoints 把请求参数改了放行，验证服务端是否真的校验。

### 3a. 改 coupon_code 试错误处理
1. 准备：登录 + 加购（product_id=2, qty=1，总额 59.90）
2. 在 Charles 里找到 `POST /api/order/create` 那条记录，**右键 → Breakpoints**
3. 再发一次下单请求，这次 body 带 `{"coupon_code":"FAKE_CODE"}`
4. Charles 自动弹拦截窗口 → 切到 Edit 标签 → 改 `coupon_code` 为 `FAKE_CODE` → 点 **Execute**
5. 看响应是否正确返回 `code=3002, msg="优惠券不存在"`

### 3b. 改响应 —— 验证客户端是否盲信服务端返回
1. 同样设置 Breakpoints，但这次拦的是 **Response** 那一栏（断点窗口切换到 Response 标签）
2. 把 `payable` 改成 `0.01`，放行
3. 如果是真实的前端页面，看是否真的按 0.01 显示并提交支付（**应该不**——前端应以后端返回为准做二次校验，但很多前端会信任后端而中招）

**测试结论**：服务端校验通过；客户端盲信响应是高风险点，写入测试报告。

## 第 4 步：Repeat Advanced —— 复现幂等缺陷（**最重要的演示**）

目的：用 Charles 内置的并发重放，**亲眼看到 BUG-003**——同一购物车重复 5 次请求，会生成 5 笔订单。

1. 准备：登录 + 加购（product_id=2, qty=1）→ **不要点下单**
2. 在 Charles 里选中准备好的 `POST /api/order/create` 请求（可以先正常发一次让 Charles 记录到，然后右键它重复发）
3. **右键 → Repeat Advanced**：
   - Iterations: 5
   - Concurrency: 5（5 个并发线程同时打）
4. 点 OK，Charles 会并发重放 5 次
5. 关键证据：再调 `GET /api/orders`（登录态 Authorization header），Charles 里搜 `GET /api/orders`，看响应里的 `data` 数组长度——**预期 1 笔，实际 5 笔**
6. 截图 + 保存 Charles 会话：`File → Save Session`，命名 `evidence_BUG003.chls`

**测试结论**：5 笔订单同时生成 → 实锤 BUG-003（幂等缺失）。这条放到缺陷报告里证据链最完整。

## 第 5 步：Map Local —— Mock 难构造场景

目的：后端接口没开发完 / 难造某种数据时，前端或接口测试怎么继续跑。

1. 准备本地 JSON 文件 `mock_empty_cart.json`：
   ```json
   {"code":0,"msg":"success","data":{"items":[],"total":0.0}}
   ```
2. `Tools → Map Local → Enable Map Local` → Add：
   - Map From: Protocol `http`, Host `127.0.0.1`, Port `5000`, Path `/api/cart`
   - Map To: 选本地那个 json 文件
3. 调一次 `GET /api/cart`，Charles 不会去问后端，直接返回你 mock 的内容
4. 验证前端按空购物车展示

**测试结论**：可以快速模拟"购物车为空""金额为负""列表超长"等后端难以快速造的场景；验证前端容错。

## 第 6 步：前端/后端责任定位（**抓包最值钱的能力**）

任何场景发现 bug，按这个流程定位：

1. Charles 抓到相关接口
3. 看**请求**：参数对吗？
   - 参数发错 → **前端 bug**
   - 参数没发出去 → **前端逻辑 bug**
3. 看**响应**：状态码 + 数据对吗？
   - 4xx → **客户端调用问题**
   - 5xx 或响应数据错 → **后端 bug**
4. 看**页面渲染**：响应数据对但显示错 → **前端渲染 bug**
5. 拿这个流程做过的真实 bug 写到简历项目里："通过抓包在 X 场景定位到 Y 性质 bug"

## 完成以上 6 步你就掌握 Charles 了

测试完把 Charles 会话保存、关键截图粘到 `docs/06-抓包测试实践.md`（我已经写好了对应章节，你把真实证据补进去），整个项目的抓包材料就齐了。

## 常见问题速查

| 问题 | 解决 |
|---|---|
| Charles 启动后电脑无法上网 | Proxy → 取消勾选 Windows Proxy，或完全退出 Charles |
| 抓不到任何包 | 系统/浏览器代理是否指向 127.0.0.1:8888；Charles 是否 Allow 了本机 |
| HTTPS 显示 unknown | 本项目是 HTTP 不需要证书；其他 App 需 chls.pro/ssl 装证书 |
| 重复发请求报错 | Repeat Advanced 的并发数不要超过后端能承受的范围；本项目是单机内存版并发 5 完全 OK |
| Breakpoints 弹窗不出现 | Edit 标签里也要点 Breakpoints 那个图标启用；可设 Proxy → Breakpoints Settings 加 URL 精确匹配 |