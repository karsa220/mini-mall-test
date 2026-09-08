"""
单元测试层（测试金字塔底座 · 促销/优惠引擎）
==========================================
纯函数、无 IO、无全局状态，做等价类/边界值全覆盖：
  - 满减门槛（含 BUG-002 恰好等于门槛的缺陷边界，已固化）
  - 折扣率与封顶
  - 品类限定
  - 多券叠加
  - 有效期（未生效/已过期）
  - 优惠不超过应付总额
同时保留与旧单测兼容的 calc_amount 字符串 code 路径。
"""
import os
import sys
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from promotion import calc_amount, apply_coupons, evaluate  # noqa: E402


# ---------------- 兼容旧单测（calc_amount 字符串 code） ----------------
def test_calc_no_coupon():
    total, discount, payable, err = calc_amount({1: 1}, None)
    assert err is None
    assert discount == 0.0
    assert payable == total


def test_calc_coupon_above_threshold():
    total, discount, payable, err = calc_amount({1: 1}, "MAN30JIAN10")
    assert err is None
    assert discount == 10.0
    assert payable == round(total - 10.0, 2)


def test_bug002_exact_threshold_rejected():
    # 商品3单价30，金额恰好等于门槛30；BUG-002 用严格大于，恰好相等时反而被拒
    total, discount, payable, err = calc_amount({3: 1}, "MAN30JIAN10")
    assert err == "未达到优惠券使用门槛"
    assert discount is None


def test_calc_unknown_coupon():
    total, discount, payable, err = calc_amount({1: 1}, "NOT_EXIST")
    assert err == "优惠券不存在"


# ---------------- 满减 ----------------
def test_full_reduction_above():
    cp = {"type": "full_reduction", "threshold": 30.0, "value": 10.0}
    d, err = evaluate({1: 1}, cp)
    assert err is None and d == 10.0


def test_full_reduction_exact_is_bug002():
    cp = {"type": "full_reduction", "threshold": 30.0, "value": 10.0}
    d, err = evaluate({3: 1}, cp)  # 单价恰好 30
    assert err == "未达到优惠券使用门槛"


def test_full_reduction_below():
    cp = {"type": "full_reduction", "threshold": 31.0, "value": 10.0}
    d, err = evaluate({3: 1}, cp)  # 30 < 31
    assert err == "未达到优惠券使用门槛"


# ---------------- 折扣 + 封顶 ----------------
def test_discount_rate():
    cp = {"type": "discount", "rate": 0.2, "cap": 0.0}
    d, err = evaluate({1: 1}, cp)  # 199 * 0.2
    assert err is None and d == round(199 * 0.2, 2)


def test_discount_cap():
    cp = {"type": "discount", "rate": 0.5, "cap": 50.0}
    d, err = evaluate({1: 1}, cp)  # 199*0.5=99.5 -> 封顶 50
    assert err is None and d == 50.0


# ---------------- 品类限定 ----------------
def test_category_restriction_counts_only_matched():
    cp = {"type": "discount", "rate": 0.2, "cap": 0.0, "category": "keyboard"}
    d, err = evaluate({1: 1, 2: 1}, cp)  # 仅键盘 199 计入
    assert err is None and d == round(199 * 0.2, 2)


def test_category_full_reduction_no_match():
    cp = {"type": "full_reduction", "threshold": 30.0, "value": 10.0, "category": "keyboard"}
    d, err = evaluate({2: 1}, cp)  # 仅鼠标，无命中品类
    assert err == "未达到优惠券使用门槛"


# ---------------- 有效期 ----------------
def test_expired_coupon():
    cp = {"type": "full_reduction", "threshold": 10.0, "value": 5.0,
          "end_at": datetime.datetime(2000, 1, 1)}
    d, err = evaluate({1: 1}, cp)
    assert err == "优惠券已过期"


def test_not_yet_effective():
    future = datetime.datetime.utcnow() + datetime.timedelta(days=1)
    cp = {"type": "full_reduction", "threshold": 10.0, "value": 5.0, "start_at": future}
    d, err = evaluate({1: 1}, cp)
    assert err == "优惠券尚未生效"


# ---------------- 叠加 / 总额保护 ----------------
def test_stackable_combine():
    items = {1: 2}  # 398
    c1 = {"type": "full_reduction", "threshold": 30.0, "value": 10.0, "stackable": True}
    c2 = {"type": "full_reduction", "threshold": 100.0, "value": 15.0, "stackable": True}
    d, err = apply_coupons(items, [c1, c2])
    assert err is None and d == 25.0


def test_discount_capped_by_total():
    c1 = {"type": "full_reduction", "threshold": 1.0, "value": 100.0}
    d, err = apply_coupons({3: 1}, [c1])  # 应付仅 30
    assert err is None and d == 30.0
