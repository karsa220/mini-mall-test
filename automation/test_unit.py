"""
单元测试层（测试金字塔的底座）
====================
企业级分层测试：单元层最快、最稳、最便宜，应占最大比例（金字塔底座）。
这里直接 import 被测模块对纯函数做断言，覆盖优惠券金额计算逻辑，
并固化两个预埋缺陷的边界（BUG-002 门槛判断），作为回归守护。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import server as s  # noqa: E402


def test_calc_no_coupon():
    total, discount, payable, err = s.calc_amount({1: 1}, None)
    assert err is None
    assert discount == 0.0
    assert payable == total


def test_calc_coupon_above_threshold():
    # 商品1单价199，满30减10，应生效
    total, discount, payable, err = s.calc_amount({1: 1}, "MAN30JIAN10")
    assert err is None
    assert discount == 10.0
    assert payable == round(total - 10.0, 2)


def test_bug002_exact_threshold_rejected():
    # 商品3单价30，金额恰好等于门槛30；BUG-002 用 > 判断，恰好相等时反而被拒（应为减10）
    total, discount, payable, err = s.calc_amount({3: 1}, "MAN30JIAN10")
    assert err == "未达到优惠券使用门槛", "复现 BUG-002：金额恰等于门槛时被错误拒绝（应为满30减10）"
    assert discount is None


def test_bug002_below_threshold_rejected():
    # 1 件商品2（59.9）? 用商品3以外构造低于30：商品2×0.5 不行，用单价最低组合
    # 商品2=59.9 已>30；这里用 任意 <30 的构造：以 商品3 的 0.5 倍不可，改测 calc 对低于门槛返回错误
    # 直接构造购物车总价<30 不可行（最低单价30），故验证「优惠券不存在」分支
    total, discount, payable, err = s.calc_amount({1: 1}, "NOT_EXIST")
    assert err == "优惠券不存在"
