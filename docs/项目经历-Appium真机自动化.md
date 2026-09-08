# 项目经历：MiniMall 电商测试项目（个人项目）

> 一句话版（贴简历）：独立负责 MiniMall 电商交易链路（登录→购物车→下单→支付）的完整测试交付，覆盖需求评审、用例设计、接口/移动端 UI 自动化、Charles 抓包复现缺陷、Jenkins CI，对标测开实习 JD 全流程能力。

- **角色**：测试开发（独立负责） **周期**：2026.09
- **技术栈**：Python · pytest · requests · YAML · allure · Appium 3.7 · UiAutomator2 · chromedriver · Charles · Flask · Jenkins · SonarQube · Docker · K8s · 真机（vivo / Android）

---

## 对标 JD 的核心交付（一个项目，全链路闭环）

**1. 需求评审与风险识别（JD：参与需求评审）**
- 评审提出 6 个问题，2 个提测后命中 P0 缺陷（优惠券门槛 BUG-002、下单幂等 BUG-003）。

**2. 测试用例设计（JD：负责功能测试）**
- 设计 36 条用例，等价类 / 边界值 / 场景法 / 判定表四类方法全覆盖，需求覆盖率 100%。

**3. 接口自动化（JD：Python + 自动化框架）**
- pytest + requests + YAML 数据驱动，17 通过 + 4 xfail（已知缺陷可重复覆盖，修复即转 pass），Allure 报告按业务模块分组并附请求/响应现场。

**4. 移动端 UI 自动化（JD：功能测试延伸）**
- Appium + UiAutomator2 驱动 vivo 真机 Chrome（WiFi 无线调试打通 PC 与真机），登录 3 + 订单 3 共 6 条用例真机全部通过，端到端验证交易链路。

**5. Charles 抓包（JD：熟练 Charles/Fiddler）**
- Throttle 弱网模拟、Breakpoints 改包验服务端校验、Repeat Advanced 并发重放下单请求；结合代码确认下单接口无幂等令牌，在并行后端（多线程 worker）+ 弱网延迟下竞态窗口打开，实测 8 并发复现 8 笔重复订单（单进程串行因清购物车兜底仅 1 笔，故该缺陷在弱网/客户端重试场景必现），BUG-003 待修复，留存 Charles Session + 截图证据链。并用 mitmproxy 脚本化落地断言与 HAR 导出（可进 CI、可写自动化断言），把抓包从手工 GUI 升级为可重复自动化资产。后续进一步扩展为：mitmproxy 改包/Mock（模拟支付通道故障、弱网超时）、WebSocket 抓包断言（订单状态推送含 order_id）、HAR 契约 diff（接口字段增删/类型变化自动报警），并接入 pytest + Jenkins 门禁，四模块自动化用例全绿。
- 移动端 Charles：模拟器 / 真机代理抓包，按请求参数 / 响应数据 / 页面展示三层定位前后端问题。

**6. Jenkins CI/CD（工程化交付）**
- 主 Jenkinsfile + 4 个场景变体，覆盖 6 大实战场景：定时夜间回归、并行执行（30→11min）、多环境并行回归（90→15min）、SonarQube 质量门禁、PR 拦截 + 失败自动建 Jira bug、CI→Docker→K8s 自动部署（30→5min）；凭据全走 credentials 注入。

**7. 企业级质量门禁（对标大厂测开体系）**
- **性能门禁**：Locust 压测交易主链路（登录→加购→下单→支付），CI 中卡 p95 时延与错误率阈值（k6 thresholds 等价），暴露容量拐点。
- **混沌/高可用测试**：server 的 `/api/chaos` 注入宕机/随机错误/延迟 + mitmproxy 网络级注入 504，验证系统优雅降级，并复现"支付超时重试→重复下单"的幂等缺口（与 BUG-003 同源）。
- **覆盖率门禁**：单元层（纯函数）+ 组件层（Flask test client 进程内）做分层测试底座，pytest-cov 行覆盖 ≥ 60% 卡门禁，失败不准合入。
- **测试数据工厂**：合成数据（合法/边界/异常）+ 每用例独立命名空间，解决面经高频的"用例间数据污染/造数局限"。
- **可观测性**：server 暴露 `/metrics`（QPS/错误率/时延分位），对接质量仪表盘；HAR 契约 diff 守护接口兼容性。

---

## 项目成果
- **一个项目**，9 份交付物闭环（需求→计划→用例→环境→抓包→缺陷→报告）+ 自动化 + CI + 企业级门禁，可一键复现。
- 接口 21 用例（17 passed + 4 xfailed）、移动端 6 用例真机全绿、单元+组件 9 用例全绿（覆盖 69%）；Charles 实证 3 个预埋缺陷；Jenkins 6 场景 + 企业级质量门禁（性能/混沌/覆盖率/契约）落地。
- 交付资产：Jenkinsfile + 4 变体 + `docs/10-Jenkins教学.md` + `docs/14-企业级测试体系.md` + `docs/15-字节测开-JD与面经.md` + 单命令启动脚本（`adb connect` → 起服务 → 起 Appium → pytest`）。
