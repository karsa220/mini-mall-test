# MiniMall 电商测试项目（简历项目）

> 一个可独立运行的"测试开发日常实习"级别完整交付物：被测系统 + 测试文档 + 接口自动化 + Allure 报告 + Jenkins CI + 抓包实践，专为简历和面试准备设计。

![API Test](https://img.shields.io/badge/API%20Test-pytest%20%2B%20allure-blue)
![Coverage](https://img.shields.io/badge/Cases-76%20(73%20passed%20%2B%203%20gates)-brightgreen)
![Coverage](https://img.shields.io/badge/Coverage-89%25-green)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![CI](https://img.shields.io/badge/CI-Jenkins-D24939)
![Container](https://img.shields.io/badge/Container-Docker-2496ED)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

## 这个项目对应 JD 的哪条要求

| JD 条款 | 项目中如何体现 | 对应交付物 |
|---|---|---|
| **1. 参与产品需求评审** | 提了 6 个问题，其中 2 个在提测后实锤为缺陷（BUG-002、BUG-003） | `docs/02-需求评审记录.md` |
| **2. 负责产品功能测试** | 设计 36 条用例，等价类/边界值/场景法/判定表全覆盖；执行并发现 3 个缺陷 | `docs/04-测试用例设计.md`、`docs/07-缺陷报告.md` |
| **3. 独立负责一个业务方向** | 独立负责 MiniMall 交易链路（登录→购物车→下单→支付），从评审到上线全流程 | `docs/03-测试计划.md` |
| **4. 制定完整的测试计划** | 含范围/策略/进度/资源/风险/准入准出 6 要素 | `docs/03-测试计划.md` |
| **5. 参与测试环境搭建与评估** | venv 隔离依赖；3 个环境局限项写明评估结论 | `docs/05-测试环境搭建与评估.md` |
| **熟练使用 Charles/Fiddler** | Throttle / Breakpoints / Repeat Advanced / Map Local 全用上，证据可复现 | `docs/06-抓包测试实践.md`、`docs/08-Charles实战手册-以MiniMall为例.md` |
| **熟练使用一门语言（Python）** | Flask 后端 + pytest 自动化 + YAML 数据驱动 | `app/server.py`、`automation/*.py` |

## 企业级测试能力矩阵（对标大厂测开 JD）

> 被测系统已重构为**真实关系型电商后端**（SQLAlchemy + SQLite，22 个端点），测试升级为**四层测试金字塔**（单元/组件/集成/安全，73 例 + 3 项企业级门禁），覆盖率 89%。详见 `docs/14-企业级测试体系.md` 与 `docs/15-字节测开-JD与面经.md`。

| 能力 | 实现 | 门禁/产出 | 文件 |
|---|---|---|---|
| 真实被测系统 | SQLAlchemy+SQLite，用户/地址/商品/购物车/优惠券/订单/幂等键 7 领域 22 端点 | 可并发、可落库 | `app/db.py` `app/promotion.py` `app/server.py` |
| 分层测试金字塔 | 单元(促销引擎15)+组件(全端点38)+集成(6)+安全(7)+冒烟(5) | 73 例全绿，覆盖 89% | `test_unit/component/integration/security.py` |
| **交易一致性** | 原子扣库存防超卖 + 优惠券原子核销 + Idempotency-Key 幂等 | 并发竞态测试断言不超卖/不重复扣款 | `test_integration.py` |
| **性能压测** | Locust 交易主链路（注册/浏览/加购/下单/支付），解析 P95/错误率 | p95≤800ms、错误率≤1% 卡 CI | `perf_test.py` `run_perf_check.py` |
| **混沌/高可用** | `/api/chaos` 应用级 + mitmproxy 网络级 504 | 故障被感知/降级 + 幂等重试验证 | `server.py` `run_chaos_check.py` |
| **安全专项** | 越权/伪造token/SQL注入/弱口令/暴力破解限流/敏感字段 | 全部拒绝或限流 | `test_security.py` |
| **覆盖率门禁** | pytest-cov 行覆盖（server+db+promotion） | `--cov-fail-under=80` | `Jenkinsfile` |
| **测试数据工厂** | 合成数据 + 每用例独立命名空间 | 解决数据污染 | `data_factory.py` |
| **契约守护** | HAR 契约 diff（消费者驱动契约等价） | 破坏性变更退出码非0 | `har_contract_diff.py` |
| **可观测性** | `/metrics`：QPS/错误率/时延 | 质量仪表盘输入 | `server.py` |
| CI 质量门禁 | Jenkins 四层并行 + 性能/混沌/覆盖率门禁 | fail fast | `Jenkinsfile` |

## 项目结构

```
testdev-portfolio/
├── README.md                         # 本文件（项目总览 + JD 映射）
├── app/
│   ├── server.py                     # MiniMall 后端（被测系统，22 端点，含 2 个预埋 bug）
│   ├── db.py                         # SQLAlchemy 模型 + SQLite 持久化 + 播种
│   ├── promotion.py                  # 促销引擎（满减/折扣/品类/叠加/有效期，纯函数）
│   └── requirements.txt              # flask + sqlalchemy + websockets
├── automation/                       # 接口自动化（四层金字塔 + 企业级门禁）
│   ├── conftest.py                   # 共享 fixture（HTTP/session 层）
│   ├── _tutil.py                     # 进程内 test_client + 用例级隔离
│   ├── data_factory.py               # 测试数据工厂（合成/边界/隔离）
│   ├── test_unit.py                  # 单元层：促销引擎（15 例）
│   ├── test_component.py             # 组件层：全端点正负边界（38 例）
│   ├── test_integration.py           # 集成层：幂等/并发防超卖/防重复核销（6 例）
│   ├── test_security.py              # 安全层：越权/注入/限流（7 例）
│   ├── test_api_server.py            # 冒烟（5 例）
│   ├── test_enterprise.py            # 企业级门禁统一入口（性能/混沌/契约）
│   ├── perf_test.py + run_perf_check.py    # Locust 性能门禁
│   ├── run_chaos_check.py + mitmproxy_*_addon.py  # 混沌/抓包/Mock
│   ├── har_contract_diff.py          # HAR 契约 diff
│   ├── pytest.ini
│   └── requirements.txt              # pytest+requests+allure+locust+mitmproxy+sqlalchemy
├── reports/                          # ⭐ Allure 结果（自动生成）
│   ├── allure-results/               # 原始 JSON
│   └── allure-report/                # HTML 报告（CI 生成）
├── Jenkinsfile                       # ⭐ Jenkins 流水线（实战升级版：定时+并行+Jira）
├── Jenkinsfile.multienv             # ⭐ 多环境并行回归 demo（linux/mac/windows agent）
├── Jenkinsfile.sonar                # ⭐ 质量门禁 demo（SonarQube 卡口 + 覆盖率）
├── Jenkinsfile.pr-hook              # ⭐ PR 拦截 demo（GitHub webhook + Jira 自动建 bug + 端到端配置步骤）
├── Jenkinsfile.auto-deploy          # ⭐ 自动部署 demo（Jenkins→Docker→K8s 闭合链路）
├── docs/
│   ├── ...
│   └── 10-Jenkins教学.md             # ⭐ Jenkins 入门到能跑（按 7 步走）
│   └── 11-移动端Charles实战.md        # ⭐ Android/iOS 抓包 + 滴滴业务场景 + SSL Pinning 绕过思路
└── run_allure.bat                    # ⭐ Windows 一键：启服务+跑测试+生成报告
└── docs/                             # 测试交付物
    ├── 01-需求规格说明书.md
    ├── 02-需求评审记录.md            # ⭐ 体现"参与需求评审"
    ├── 03-测试计划.md                # ⭐ 体现"制定完整测试计划"
    ├── 04-测试用例设计.md            # ⭐ 体现"功能测试"
    ├── 05-测试环境搭建与评估.md      # ⭐ 体现"测试环境搭建"
    ├── 06-抓包测试实践.md            # ⭐ 体现"Charles 熟练"
    ├── 07-缺陷报告.md                # ⭐ 体现"独立负责业务方向"
    ├── 08-Charles实战手册-以MiniMall为例.md   # ⭐ 手把手教你用 Charles 测本系统
    └── 09-测试报告.md                # ⭐ 体现"保障交付质量"
```

## 一键运行

```bash
# 1. 启动被测系统
python -m venv .venv && .venv\Scripts\activate
pip install flask sqlalchemy pytest requests pyyaml
python app/server.py          # 启动后访问 http://127.0.0.1:5000

# 2. 另开终端，跑四层接口自动化（进程内，无需起服务）
cd automation && pytest test_unit.py test_component.py test_integration.py test_security.py
# 期望 "73 passed"（含 3 项企业级门禁则 76 passed）

# 3. 跑 + 生成 Allure HTML 报告（推荐）
cd automation
pytest --alluredir=reports/allure-results --clean-alluredir
# HTML 报告生成有两种方式：
#   a) CI 上自动生成（GitHub Actions 页直接看）
#   b) 本地：在 automation/reports/ 下手动跑 `allure serve allure-results`（需安装 Allure CLI）
```

### 自动化能力速览

| 能力 | 实现方式 | 价值点 |
|---|---|---|
| **数据驱动** | `data/*.yaml` + `@pytest.mark.parametrize` | 加用例不加代码，HR 看代码就知道你懂解耦 |
| **依赖管理** | `conftest.py` 的 session/token/auth_session 三个 fixture | 面试必问"自动化稳定性怎么做"的答案 |
| **Allure 报告** | `@allure.feature/story/title/severity` + `--alluredir` | 截图贴进简历，颜值即正义 |
| **响应证据** | `attach_response()` 把每次请求/响应附到报告 | 失败用例带现场，定位 bug 一秒就找到 |
| **CI 流水线** | `Jenkinsfile`（declarative pipeline + post 钩子） | 测开岗位 100% 会问的硬技能，比 GitHub Actions 更有"工程感" |

### Jenkins CI（企业主流方案）

项目自带 **4 个 Jenkinsfile**，覆盖 6 个大厂实战场景：

| 文件 | 覆盖的实战场景 | 简历亮点 |
|---|---|---|
| **Jenkinsfile**（主文件） | ✅ 定时夜间跑（cron）<br>✅ 并行执行（parallel：登录/购物车/订单三组并行）<br>✅ 失败自动建 Jira bug | "主导 X 项目夜间定时回归 + 失败 30 秒内建缺陷到 Jira" |
| **Jenkinsfile.multienv** | ✅ 多环境并行回归（agent label 分组） | "搭建 5 环境 ×3 客户端自动化回归体系，回归耗时 90min→15min" |
| **Jenkinsfile.sonar** | ✅ 质量门禁（SonarQube 覆盖率/漏洞卡口） | "集成 SonarQube 质量门禁，PR 卡口覆盖率≥80%/漏洞=0" |
| **Jenkinsfile.pr-hook** | ✅ PR 拦截（GitHub webhook 自动跑测试）<br>✅ CI 失败自动建缺陷（已在主文件里）<br>✅ 端到端配置步骤（PAT + 仓库 + 凭据 + 插件 + Branch Protection） | "搭建 PR 自动测试+卡口+建缺陷全链路，PR 平均合并时间从 4h 降至 30min" |
| **Jenkinsfile.auto-deploy** | ✅ Docker 镜像构建+推送<br>✅ K8s 滚动更新（kubectl set image）<br>✅ 部署后冒烟测试+回滚预案<br>✅ Slack 通知成功/失败 | "搭建 Jenkins→Docker→K8s 自动部署链路，PR 合入到测试环境可用从 30min 缩至 5min" |

**本地 5 分钟跑起来：**

```bash
docker run -d --name jenkins -p 8080:8080 -p 50000:50000 ^
  -v jenkins_home:/var/jenkins_home jenkins/jenkins:lts
```

浏览器访问 `http://localhost:8080`，详细操作见 [`docs/10-Jenkins教学.md`](docs/10-Jenkins教学.md)。

> **关于工具选型**：GitHub Actions 适合开源/初创项目；Jenkins 适合企业内网（1800+ 插件、可控性更强）；大厂基本都自研（字节 ByteCycle、美团自研引擎、阿里云效）。**测开面试的核心不是"你用过哪个工具"，而是"你懂 CI/CD 流水线分层、并行调度、质量门禁这些工程化思维"。**

## 快速产出面试话术

**讲项目**（90 秒版）：
> 这个项目是 MiniMall 电商后端，我把它从"内存字典的玩具 demo"升级成了真实可落库的企业级被测系统（SQLAlchemy + SQLite，22 个接口，覆盖用户/地址/商品/购物车/优惠券/订单/幂等键七大领域）。测试按金字塔分层：单元层覆盖促销引擎（满减/折扣/品类/叠加/有效期的等价类边界），组件层打满全部端点的正反用例，集成层用并发线程验证"防超卖、幂等下单、防优惠券重复核销"这些交易一致性，安全层做越权/注入/限流。再加上 Locust 性能门禁（p95≤800ms）、混沌故障注入、HAR 契约 diff、覆盖率 89% 卡 CI。总共 76 个用例全绿。这套东西直接对齐大厂测开 JD 里"功能/自动化/性能/安全/稳定性监控/流程改进"的完整闭环。

**被追问"测试设计方法论"**：
> 等价类 + 边界值用于输入域（登录、加购数量），场景法用于流程（下单支付全链路），判定表用于规则（优惠券），再叠加接口维度的异常（弱网、并发、越权）。每个用例的设计意图在 `04-测试用例设计.md` 里都写了。

**被追问"前后端 bug 怎么定位"**：
> Charles 抓包看三点：请求参数错就是前端问题、响应数据错就是后端问题、响应数据对但页面错就是前端渲染问题。这是我项目里 ORD 系列用例的设计基础。

## 你下一步该做什么

1. **打开 `docs/08-Charles实战手册-以MiniMall为例.md`**，按 6 步真的用 Charles 测一次
2. 把 Charles Session 保存为 `evidence_BUG003.chls`，把截图贴进 `docs/06-抓包测试实践.md`
3. 把项目 push 到 GitHub（README 就是项目门面，CI 徽章自动亮）
4. **项目进 CI 后**：进 Actions 页下载 Allure 报告 HTML，把图截下来贴简历项目栏
5. 简历项目栏写：「MiniMall 电商测试项目 | GitHub: 链接 | 21 用例+Allure+CI+Charles 全流程交付物」