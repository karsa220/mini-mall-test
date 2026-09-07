# MiniMall 电商测试项目（简历项目）

> 一个可独立运行的"测试开发日常实习"级别完整交付物：被测系统 + 测试文档 + 接口自动化 + Allure 报告 + GitHub Actions CI + 抓包实践，专为简历和面试准备设计。

![API Test](https://img.shields.io/badge/API%20Test-pytest%20%2B%20allure-blue)
![Coverage](https://img.shields.io/badge/Cases-21%20(17%20passed%20%2B%204%20xfail)-brightgreen)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF)
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

## 项目结构

```
testdev-portfolio/
├── README.md                         # 本文件（项目总览 + JD 映射）
├── app/
│   ├── server.py                     # MiniMall 后端（被测系统，含 3 个预埋 bug）
│   └── requirements.txt
├── automation/                       # 接口自动化
│   ├── conftest.py                   # 共享 fixture（登录、清空购物车）
│   ├── data/test_login.yaml          # 登录用例数据驱动
│   ├── data/test_cart.yaml           # 购物车边界值数据驱动
│   ├── test_api_login.py             # 登录接口用例
│   ├── test_api_cart.py              # 购物车接口用例（含 xfail）
│   ├── test_api_order.py             # 下单/支付/优惠券用例（含 xfail）
│   ├── pytest.ini
│   └── requirements.txt              # pytest+requests+allure-pytest
├── reports/                          # ⭐ Allure 结果（自动生成）
│   ├── allure-results/               # 原始 JSON
│   └── allure-report/                # HTML 报告（CI 生成）
├── .github/
│   └── workflows/test.yml            # ⭐ GitHub Actions CI（提交即跑）
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
pip install flask pytest requests pyyaml
python app/server.py          # 启动后访问 http://127.0.0.1:5000

# 2. 另开终端，跑接口自动化
cd automation && pytest        # 看到 "17 passed, 4 xfailed" 即正常

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
| **CI 流水线** | `.github/workflows/test.yml` | 提交即跑、PR 拦截；大厂看这个就知道你懂工程化 |

### GitHub Actions CI

项目自带 CI：每次 push / PR 自动跑一遍测试，并把 Allure HTML 报告上传为 artifact。

启用方式：
1. 把项目 push 到 GitHub
2. 进 Actions 页 → 选 `接口自动化测试` workflow
3. 跑完后在 Artifacts 下载 `allure-html-report.zip`，解压打开 `index.html`

## 快速产出面试话术

**讲项目**（90 秒版）：
> 这个项目是 MiniMall 电商 V1.0，我从需求评审介入，提了 6 个问题，其中"优惠券门槛边界"和"下单幂等"两个疑问在提测后命中为 P0 缺陷（BUG-002、003）。独立负责交易链路方向，设计了 36 条用例，跑出 17 个自动化全通过 + 4 个预期 xfail。3 个缺陷都用 Charles 复现过证据，其中 BUG-003 是用 Repeat Advanced 5 并发直接看到的。整套用 Python + pytest + requests + YAML 数据驱动搭建，可重复运行。

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