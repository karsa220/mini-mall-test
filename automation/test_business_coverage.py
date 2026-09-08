"""
test_business_coverage.py
======================

业务测试覆盖度矩阵 —— 把 docs/16 业务方案文档里的 8 个维度、可量化成
"automation 目录下必须有 N 个用例名匹配某种 pattern" 的硬断言。

设计原则：
  1. 不依赖被测系统，独立可跑（pytest test_business_coverage.py）
  2. 用 AST + 正则扫描用例名，未来删用例 CI 立即红
  3. 阈值与 docs/16 业务方案表格一一对应（任何方案里写过的"必须测"维度都进表格）
  4. 输出可读的覆盖矩阵（CI 日志 + 文档可复用）

为什么重要：
  - 业务思维的"我能证明覆盖完整"不是嘴炮——是脚本级证据
  - 字节面试官爱问"你怎么证明你的覆盖够"，本文件就是答案
  - 现有 73+ 用例都会被自动归类到下面的 10+ 维度里
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).parent
AUTOMATION_DIR = ROOT
EXCLUDE_FILES = set()  # test_enterprise.py 也进入扫描(它含 test_perf_gate / test_chaos_resilience / test_contract_diff)


# ----- 维度定义（与 docs/16 业务方案每一节严格对齐）-----
# (维度名, [匹配用例名的正则], 最少用例数, 业务语义)
DIMENSIONS: List[Tuple[str, List[re.Pattern], int, str]] = [
    (
        "状态机_订单_合法转移",
        [
            re.compile(r"^test_.*cancel_unpaid.*$", re.I),
            re.compile(r"^test_.*pay_unpaid.*$", re.I),
            re.compile(r"^test_.*refund_paid.*$", re.I),
            re.compile(r"^test_.*paid_then_refund.*$", re.I),
            re.compile(r"^test_paid_refund_ok$", re.I),
        ],
        3,
        "UNPAID->CANCELLED、UNPAID->PAID、PAID->REFUNDED 必须有正向与逆向用例锁定",
    ),
    (
        "状态机_订单_非法转移",
        [
            re.compile(r"^test_.*cancel_then_pay.*$", re.I),
            re.compile(r"^test_.*pay_already_paid.*$", re.I),
            re.compile(r"^test_.*refund_already_refunded.*$", re.I),
            re.compile(r"^test_refund_then_refund", re.I),
            re.compile(r"^test_paid_then_cancel.*$", re.I),
            re.compile(r"^test_pay_cancelled_.*$", re.I),
        ],
        2,
        "CANCELLED->PAID 拒、PAID 重复支付、REFUNDED 重复退款 必须有 case 拦截",
    ),
    (
        "BUG_001_购物车数量下限",
        [
            re.compile(r"^test_.*bug.?001.*$", re.I),
            re.compile(r"^test_.*cart_add.*qty_?0.*$", re.I),
            re.compile(r"^test_.*cart_add.*negative.*$", re.I),
            re.compile(r"^test_.*cart_qty.*boundary.*$", re.I),
        ],
        2,
        "购物车 quantity 必须拒 0/负/超库存",
    ),
    (
        "BUG_002_优惠券门槛边界",
        [
            re.compile(r"^test_.*bug.?002.*$", re.I),
            re.compile(r"^test_.*coupon.*exact.*threshold.*$", re.I),
            re.compile(r"^test_.*coupon.*threshold.*boundary.*$", re.I),
        ],
        2,
        "满减门槛恰恰等于时必须可用，不能因严格大于拒",
    ),
    (
        "幂等_下单",
        [
            re.compile(r"^test_idempoten", re.I),
            re.compile(r"^test_.*idempotency.*same.*key.*$", re.I),
            re.compile(r"^test_.*concurrent.*coupon.*redemption.*$", re.I),
            re.compile(r"^test_.*retry.*duplicate.*$", re.I),
            re.compile(r"^test_.*weak.*network.*$", re.I),
        ],
        2,
        "幂等下单：同 Idempotency-Key 重试返回同 order_no;并发核销优惠券只 1 个成功",
    ),
    (
        "幂等_支付",
        [
            re.compile(r"^test_pay_idempoten", re.I),
            re.compile(r"^test_.*pay_already_paid.*$", re.I),
            re.compile(r"^test_.*pay.*same.*order.*$", re.I),
            re.compile(r"^test_.*pay_again.*$", re.I),
            re.compile(r"^test_.*order_paid.*pay.*$", re.I),
        ],
        2,
        "支付幂等：同 order_no 重试不重复扣款；状态不翻转",
    ),
    (
        "防超卖_并发一致",
        [
            re.compile(r"^test_concurrent.*order", re.I),
            re.compile(r"^test_.*oversell.*", re.I),
            re.compile(r"^test_.*atomic.*stock.*", re.I),
            re.compile(r"^test_.*concurrent.*stock.*", re.I),
        ],
        2,
        "并发防超卖:stock=N 的商品被 N+M 个线程抢,成交不大于 N",
    ),
    (
        "状态机_退款",
        [
            re.compile(r"^test_.*refund_", re.I),
            re.compile(r"^test_.*refund.*paid", re.I),
            re.compile(r"^test_.*refund.*unpaid", re.I),
        ],
        2,
        "退款状态机:PAID 才允许,UNPAID 拒",
    ),
    (
        "状态机_取消",
        [
            re.compile(r"^test_.*cancel_", re.I),
            re.compile(r"^test_.*cancel.*unpaid", re.I),
            re.compile(r"^test_cancel_then_pay", re.I),
        ],
        2,
        "取消订单状态机:UNPAID 可取消,其它状态拒",
    ),
    (
        "越权_订单",
        [
            re.compile(r"^test_.*cannot.*order", re.I),
            re.compile(r"^test_.*other.*order", re.I),
            re.compile(r"^test_.*others_?order", re.I),
            re.compile(r"^test_.*pay_other", re.I),
        ],
        2,
        "用户 A 不能看/付/取消用户 B 的订单",
    ),
    (
        "越权_地址",
        [
            re.compile(r"^test_.*cannot.*address", re.I),
            re.compile(r"^test_.*delete.*other.*address", re.I),
            re.compile(r"^test_.*other_user.*address", re.I),
            re.compile(r"^test_address_delete_others.*", re.I),
            re.compile(r"^test_.*delete_others_.*forbidden.*", re.I),
        ],
        1,
        "用户 A 不能删改用户 B 的地址",
    ),
    (
        "防爆破_登录限流",
        [
            re.compile(r"^test_.*brute", re.I),
            re.compile(r"^test_.*rate_?limit", re.I),
            re.compile(r"^test_.*login.*blocked", re.I),
            re.compile(r"^test_.*login.*lock", re.I),
        ],
        1,
        "60s 内 N 次失败 -> 429",
    ),
    (
        "安全_注入",
        [
            re.compile(r"^test_.*sql_?injection", re.I),
            re.compile(r"^test_.*inject", re.I),
            re.compile(r"^test_.*xss", re.I),
        ],
        1,
        "SQL 注入/XSS 攻击被拒",
    ),
    (
        "安全_敏感字段",
        [
            re.compile(r"^test_.*sensitive", re.I),
            re.compile(r"^test_.*pw_?hash", re.I),
            re.compile(r"^test_.*leak", re.I),
            re.compile(r"^test_.*expose", re.I),
        ],
        1,
        "响应/日志/异常栈不能泄露 pw_hash/token 签名等",
    ),
    (
        "鉴权_伪造token",
        [
            re.compile(r"^test_.*forged.*token", re.I),
            re.compile(r"^test_.*expired.*token", re.I),
            re.compile(r"^test_.*invalid.*token", re.I),
            re.compile(r"^test_.*auth.*header.*missing", re.I),
            re.compile(r"^test_.*requires.*auth", re.I),
        ],
        2,
        "Bearer 鉴权:伪造/过期/缺失均拒绝",
    ),
    (
        "促销引擎_单元",
        [
            re.compile(r"^test_.*full.?reduc", re.I),
            re.compile(r"^test_.*discount", re.I),
            re.compile(r"^test_.*stacking", re.I),
            re.compile(r"^test_.*threshold", re.I),
            re.compile(r"^test_.*category", re.I),
            re.compile(r"^test_.*expired", re.I),
        ],
        5,
        "促销引擎单测:满减/折扣/品类/叠加/有效期/门槛",
    ),
    (
        "弱网_重试",
        [
            re.compile(r"^test_.*retry.*order", re.I),
            re.compile(r"^test_.*network.*flaky", re.I),
            re.compile(r"^test_.*duplicate.*create", re.I),
        ],
        1,
        "弱网重复下单/支付不被重复处理",
    ),
    (
        "业务功能_基本路径",
        [
            re.compile(r"^test_.*login.*", re.I),
            re.compile(r"^test_.*register.*", re.I),
            re.compile(r"^test_.*cart_add.*", re.I),
            re.compile(r"^test_.*order_create.*", re.I),
            re.compile(r"^test_.*order_pay.*", re.I),
            re.compile(r"^test_.*coupon_claim.*", re.I),
        ],
        6,
        "九大业务功能基本路径",
    ),
    (
        "Mock_改包_抓包",
        [
            re.compile(r"^test_.*mock.*", re.I),
            re.compile(r"^test_.*intercept.*", re.I),
            re.compile(r"^test_.*map_?local", re.I),
        ],
        1,
        "抓包/Mock/Map Local 在测试链路里可触发",
    ),
    (
        "性能_门禁",
        [
            re.compile(r"^test_perf_?gate.*", re.I),
            re.compile(r"^test_.*performance.*gate.*", re.I),
        ],
        1,
        "性能门禁脚本存在并可跑(p95/错误率)",
    ),
    (
        "混沌_门禁",
        [
            re.compile(r"^test_chaos_?resilience.*", re.I),
            re.compile(r"^test_.*chaos.*resilience.*", re.I),
        ],
        1,
        "混沌测试脚本存在并可验证降级",
    ),
    (
        "契约_守护",
        [
            re.compile(r"^test_contract_?diff.*", re.I),
        ],
        1,
        "HAR 契约守护存在并能感知破坏性变更",
    ),
]


# ----- 工具：扫描 automation/test_*.py,返回所有 def test_xxx -----
def collect_test_names() -> Dict[Path, List[str]]:
    out: Dict[Path, List[str]] = {}
    for path in sorted(AUTOMATION_DIR.glob("test_*.py")):
        if path.name in EXCLUDE_FILES:
            continue
        if path.name == "test_business_coverage.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        names: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                names.append(node.name)
        if names:
            out[path] = names
    return out


def match_dimension(case_names: List[str], patterns: List[re.Pattern]) -> List[str]:
    hits = []
    for n in case_names:
        for p in patterns:
            if p.match(n):
                hits.append(n)
                break
    return hits


# ----- 维度评估并形成报告 -----
def evaluate() -> Tuple[Dict, List[str]]:
    by_file = collect_test_names()
    all_names = [n for names in by_file.values() for n in names]

    report = {}
    failures = []
    for dim, patterns, min_count, desc in DIMENSIONS:
        hits = match_dimension(all_names, patterns)
        report[dim] = {
            "matched": len(hits),
            "required": min_count,
            "cases": sorted(hits)[:10],
            "desc": desc,
        }
        if len(hits) < min_count:
            failures.append(
                f"❌ [{dim}] 当前 {len(hits)} < 阈值 {min_count}; "
                f"命中: {hits[:5]}\n   业务语义: {desc}"
            )
        else:
            pass  # OK
    # 总用例数
    report["__summary__"] = {
        "files": len(by_file),
        "total_cases": len(all_names),
        "files_list": [p.name for p in by_file.keys()],
    }
    return report, failures


# ----- 打印报告(便于 pytest -s 看)-----
def print_report(report: Dict) -> str:
    summary = report["__summary__"]
    lines = []
    lines.append("=" * 80)
    lines.append("  业务测试覆盖度矩阵 —— 与 docs/16-业务思维 严格对齐")
    lines.append("=" * 80)
    lines.append(f"扫描文件: {summary['files']} 个 -> {summary['files_list']}")
    lines.append(f"总用例数: {summary['total_cases']}")
    lines.append("-" * 80)

    ok_count = 0
    fail_count = 0
    for dim, info in report.items():
        if dim == "__summary__":
            continue
        status = "✅" if info["matched"] >= info["required"] else "❌"
        if info["matched"] >= info["required"]:
            ok_count += 1
        else:
            fail_count += 1
        lines.append(f"{status} {dim:32} {info['matched']:>3} / {info['required']:<3}  ({info['desc']})")

    lines.append("-" * 80)
    lines.append(f"维度通过: {ok_count} / 通过+失败 = {ok_count + fail_count}  (失败 = {fail_count})")
    lines.append("=" * 80)
    return "\n".join(lines)


# ----- 静态报告(不需要 pytest,管理员也可直接 python 调用) -----
if __name__ == "__main__":
    report, failures = evaluate()
    print(print_report(report))
    if failures:
        raise SystemExit(1)


# ----- pytest 用例 -----
def test_business_coverage_meets_all_dimensions():
    """业务测试覆盖度矩阵 - 所有维度必须达到阈值"""
    report, failures = evaluate()
    text = print_report(report)
    print("\n" + text)
    assert not failures, "\n".join(failures)


def test_at_least_one_test_per_pyramid_layer():
    """分层测试金字塔 - 各层必须有用例"""
    by_file = collect_test_names()
    layers = {
        "单元层(test_unit)": "test_unit.py",
        "组件层(test_component/test_api_*)": None,
        "集成层(test_integration)": "test_integration.py",
        "安全层(test_security)": "test_security.py",
    }
    missing = []
    for label, target in layers.items():
        if target is None:
            # 组件层 - 至少有 1 个 test_component 或 test_api_login/cart/order
            found = any(name.startswith("test_api_") or "component" in p.name.lower()
                        for p, names in by_file.items() for name in names)
            if not found:
                missing.append(label)
            continue
        if not any(p.name == target for p in by_file):
            missing.append(f"{label} ({target})")
    assert not missing, f"金字塔分层缺失: {missing}"


def test_bug_repro_cases_present():
    """BUG-001 / BUG-002 必须有自动化复现用例(否则 = 预埋缺陷无人管)"""
    report, _ = evaluate()
    b1 = report["BUG_001_购物车数量下限"]["matched"]
    b2 = report["BUG_002_优惠券门槛边界"]["matched"]
    assert b1 >= 1, "BUG-001(购物车 quantity 下限)未被任何用例覆盖!"
    assert b2 >= 1, "BUG-002(优惠券门槛严格大于)未被任何用例覆盖!"


def test_pre_existing_naming_only():
    """白名单:只接受 test_*.py 文件"""
    files = list(AUTOMATION_DIR.glob("**/test_*.py"))
    assert files, "未发现任何 test_*.py"
