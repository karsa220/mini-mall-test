"""
促销/优惠引擎（纯函数，可单测）
==============================
支持能力（对标电商真实营销规则）：
  - 满减（full_reduction）：达到门槛减固定金额
  - 折扣（discount）：按比例打折，可设封顶 cap
  - 品类限定（category）：仅指定品类商品参与计算
  - 可叠加（stackable）：多券组合
  - 有效期（start_at / end_at）：过期不可用

设计要点：
  - 纯函数、无 IO、无全局状态，便于单测做等价类/边界值全覆盖
  - calc_amount 与旧单测兼容：coupon 可传 code 字符串（查静态表）或 dict（查 DB）
  - BUG-002 预埋：满减门槛用严格大于 `>`，金额恰等于门槛时无法使用（单测固化）
"""
from datetime import datetime

# 静态目录（与 DB 播种保持一致的镜像），保证 calc_amount 单测不依赖 DB
CATALOG = {
    1: {"price": 199.0, "category": "keyboard"},
    2: {"price": 59.9, "category": "mouse"},
    3: {"price": 30.0, "category": "stand"},
    4: {"price": 129.0, "category": "hub"},
}
COUPONS = {
    "MAN30JIAN10": {"type": "full_reduction", "threshold": 30.0, "value": 10.0,
                    "rate": 0.0, "cap": 0.0, "category": None, "stackable": False,
                    "desc": "满30减10"},
}


def catalog_total(items, catalog):
    """购物车总价（items: {pid: qty}）"""
    return round(sum(round(catalog[pid]["price"] * qty, 2) for pid, qty in items.items()), 2)


def category_subtotal(items, coupon, catalog):
    """品类限定券：仅统计命中品类的金额"""
    if not coupon.get("category"):
        return catalog_total(items, catalog)
    return round(sum(round(catalog[pid]["price"] * qty, 2)
                     for pid, qty in items.items()
                     if catalog.get(pid, {}).get("category") == coupon["category"]), 2)


def _discount_of(coupon, base, now=None):
    """单券优惠额计算，返回 (discount, err)。err 非 None 表示不可用。"""
    ctype = coupon.get("type", "full_reduction")
    if ctype == "full_reduction":
        th = float(coupon.get("threshold", 0.0) or 0.0)
        # BUG-002 预埋：严格大于，恰好等于门槛不可用（测试固化该缺陷边界）
        if base > th:
            discount = float(coupon.get("value", 0.0) or 0.0)
        else:
            return None, "未达到优惠券使用门槛"
    elif ctype == "discount":
        rate = float(coupon.get("rate", 0.0) or 0.0)
        discount = round(base * rate, 2)
        cap = float(coupon.get("cap", 0.0) or 0.0)
        if cap and discount > cap:
            discount = cap
    else:
        return None, "不支持的优惠券类型"

    # 有效期校验
    start = coupon.get("start_at")
    end = coupon.get("end_at")
    now = now or datetime.utcnow()
    if start and now < start:
        return None, "优惠券尚未生效"
    if end and now > end:
        return None, "优惠券已过期"
    if discount < 0:
        discount = 0.0
    return round(discount, 2), None


def evaluate(items, coupon, catalog=None, now=None):
    """单券评估，返回 (discount, err)。err 为 None 表示可用。"""
    catalog = catalog or CATALOG
    if not coupon:
        return 0.0, None
    base = category_subtotal(items, coupon, catalog)
    return _discount_of(coupon, base, now)


def apply_coupons(items, coupons, catalog=None, now=None):
    """多券叠加计算，返回 (total_discount, err)。非叠加券与叠加券混用时按规则累加。"""
    catalog = catalog or CATALOG
    if not coupons:
        return 0.0, None
    total = catalog_total(items, catalog)
    total_discount = 0.0
    for cp in coupons:
        disc, err = evaluate(items, cp, catalog, now)
        if err:
            return None, err
        total_discount += disc
    # 折扣不允许超过应付总额
    if total_discount > total:
        total_discount = total
    return round(total_discount, 2), None


def calc_amount(items, coupon, catalog=None):
    """兼容旧单测的对外纯函数。

    coupon 支持：
      - 空 / None          -> 无优惠
      - code 字符串        -> 查静态 COUPONS
      - dict（来自 DB）    -> 直接评估
    返回 (total, discount, payable, err)。
    """
    catalog = catalog or CATALOG
    if isinstance(coupon, str):
        if not coupon:
            coupon = None
        else:
            coupon = COUPONS.get(coupon)
            if coupon is None:
                return None, None, None, "优惠券不存在"
    total = catalog_total(items, catalog)
    if not coupon:
        return total, 0.0, total, None
    discount, err = evaluate(items, coupon, catalog)
    if err:
        return None, None, None, err
    payable = round(total - discount, 2)
    return total, discount, payable, None
