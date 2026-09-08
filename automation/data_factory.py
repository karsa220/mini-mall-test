"""
测试数据工厂（Test Data Factory · DB/接口友好版）
==============================================
企业级测试中「造数」是高频痛点（面经常问：用例间数据污染怎么解决？造数工具
的局限性？）。本工厂提供：
  1. 合法 / 边界 / 异常 三类数据的程序化生成，不依赖生产数据（合规、可版本化）
  2. 唯一性保证（uuid 命名空间），天然支持用例间数据隔离、互不污染
  3. 字段对齐新后端校验（用户名 3-32、密码 ≥6、商品价/库存非负等）

用法：
  - make_user()/make_product()/make_coupon() 生成可直接 POST 的合法请求体
  - make_boundary_cases() 输出负面用例原料（等价类/边界值法）
  - DataFactory 有状态工厂：同一会话内所有数据带同一命名空间，便于 teardown
"""
import random
import string
import uuid


def _rand_str(n=8, charset=string.ascii_lowercase + string.digits):
    return "".join(random.choices(charset, k=n))


def _uid(prefix="u"):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------- 合法数据 ----------------
def make_user(role: str = "normal") -> dict:
    """合法用户（可直接用于 /api/register）"""
    return {
        "username": _uid("user"),
        "password": "Pwd_" + _rand_str(10) + "1!",   # ≥6 位，含字母数字
        "role": role,
    }


def make_product(price: float = None, stock: int = None, category: str = "general") -> dict:
    return {
        "name": "商品_" + _rand_str(6),
        "category": category,
        "price": round(price if price is not None else random.uniform(1.0, 999.0), 2),
        "stock": stock if stock is not None else random.randint(1, 100),
    }


def make_coupon(code: str = None, ctype: str = "full_reduction",
                threshold: float = 30.0, value: float = 10.0,
                rate: float = 0.0, cap: float = 0.0, category=None,
                stackable: bool = False, per_user_limit: int = 1,
                total_limit: int = 0) -> dict:
    """合法优惠券（可直接用于 /api/admin/coupons 发放）"""
    return {
        "code": code or "CPN_" + _rand_str(6).upper(),
        "type": ctype,
        "threshold": threshold,
        "value": value,
        "rate": rate,
        "cap": cap,
        "category": category,
        "stackable": stackable,
        "per_user_limit": per_user_limit,
        "total_limit": total_limit,
        "desc": "factory_coupon",
    }


# ---------------- 边界 / 异常数据（负面用例原料） ----------------
def make_boundary_cases() -> dict:
    """覆盖等价类/边界值法的典型异常输入"""
    return {
        # 注册
        "empty_username": {"username": "", "password": "123456"},
        "short_username": {"username": "ab", "password": "123456"},
        "short_password": {"username": "alice2", "password": "123"},
        # 购物车 BUG-001：0 与负数量应被拒却后端接受
        "zero_quantity": {"product_id": 1, "quantity": 0},
        "negative_quantity": {"product_id": 1, "quantity": -1},
        "huge_quantity": {"product_id": 1, "quantity": 10 ** 9},
        "nonint_quantity": {"product_id": 1, "quantity": 1.5},
        "nonexist_product": {"product_id": 999999, "quantity": 1},
        # 优惠券
        "unknown_coupon": {"coupon_code": "NOT_EXIST"},
        # BUG-002：金额恰等于门槛 → 优惠券不可用（应为可用）
        "exact_threshold_coupon": {"coupon_code": "MAN30JIAN10"},
        # 订单幂等
        "idempotency_key": "idem_" + _uid(),
    }


# ---------------- 隔离型造数（pytest fixture 友好） ----------------
class DataFactory:
    """有状态工厂：一次测试会话内生成的所有数据带同一命名空间，互不污染。"""

    def __init__(self, namespace: str = None):
        self.namespace = namespace or _uid("ns")
        self._created = []

    def user(self, **kw) -> dict:
        u = make_user(**kw)
        u["username"] = f"{self.namespace}_{u['username']}"
        self._created.append(("user", u["username"]))
        return u

    def product(self, **kw) -> dict:
        p = make_product(**kw)
        self._created.append(("product", p["name"]))
        return p

    def coupon(self, **kw) -> dict:
        c = make_coupon(**kw)
        c["code"] = f"{self.namespace}_{c['code']}"
        self._created.append(("coupon", c["code"]))
        return c

    def summary(self) -> list:
        return list(self._created)


if __name__ == "__main__":
    f1, f2 = DataFactory(), DataFactory()
    u1, u2 = f1.user(), f2.user()
    print("factory1 user:", u1["username"])
    print("factory2 user:", u2["username"])
    print("不冲突:", u1["username"] != u2["username"])
    print("边界用例:", list(make_boundary_cases().keys()))
