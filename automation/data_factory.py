"""
测试数据工厂（Test Data Factory）
====================
企业级测试中「造数」是高频痛点：面经常问「用例间数据污染怎么解决」「造数工具的局限性」。
本模块提供：
  1. 合法 / 边界 / 异常 三类数据的程序化生成（不依赖生产数据，规避合规与脏数据风险）
  2. 唯一性保证（uuid 命名空间），天然支持用例间数据隔离（互不污染）
  3. 可序列化为接口请求体，直接喂给 MiniMall 接口自动化

设计要点（对标字节测开「测试数据管理」要求）：
  - 合成数据优先于脱敏生产数据：可重复、可版本化、合规
  - 每个用例拿到的数据是「独立命名空间」，避免 A 用例的订单影响了 B 用例断言
"""
import random
import string
import uuid


def _rand_str(n=8, charset=string.ascii_lowercase + string.digits):
    return "".join(random.choices(charset, k=n))


def _uid(prefix="u"):
    """全局唯一 id：用例级数据隔离的关键"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------- 合法数据 ----------------
def make_user(role: str = "normal") -> dict:
    """生成一个合法用户（可直接用于注册/登录造数）"""
    uname = _uid("user")
    return {
        "username": uname,
        "password": "Pwd_" + _rand_str(10) + "1!",   # 满足复杂度
        "role": role,
    }


def make_product(price: float = None, stock: int = None) -> dict:
    pid = random.randint(1000, 9999)
    return {
        "product_id": pid,
        "name": "商品_" + _rand_str(6),
        "price": round(price if price is not None else random.uniform(1.0, 999.0), 2),
        "stock": stock if stock is not None else random.randint(1, 100),
    }


def make_coupon(threshold: float = 30.0, discount: float = 10.0) -> dict:
    return {
        "code": "CPN_" + _rand_str(6).upper(),
        "threshold": threshold,
        "discount": discount,
    }


# ---------------- 边界 / 异常数据（负面用例原料） ----------------
def make_boundary_cases() -> dict:
    """覆盖等价类/边界值法的典型异常输入"""
    return {
        "empty_username": {"username": "", "password": "123456"},
        "none_password": {"username": "alice", "password": None},
        "zero_quantity": {"product_id": 1, "quantity": 0},          # 命中 BUG-001：应被拒但后端接受
        "negative_quantity": {"product_id": 1, "quantity": -1},     # 命 BUG-001
        "huge_quantity": {"product_id": 1, "quantity": 10 ** 9},
        "oversize_coupon": {"coupon_code": "NOT_EXIST"},
        "exact_threshold_coupon": {"coupon_code": "MAN30JIAN10"},   # 金额恰等于门槛 → 命中 BUG-002
    }


# ---------------- 隔离型造数（pytest fixture 友好） ----------------
class DataFactory:
    """有状态的工厂：一次测试会话内生成的所有数据带同一命名空间，互不污染。"""

    def __init__(self, namespace: str = None):
        self.namespace = namespace or _uid("ns")
        self._created = []   # 记录造出的数据，便于 teardown 清理

    def user(self, **kw) -> dict:
        u = make_user(**kw)
        u["username"] = f"{self.namespace}_{u['username']}"
        self._created.append(("user", u["username"]))
        return u

    def product(self, **kw) -> dict:
        p = make_product(**kw)
        self._created.append(("product", p["product_id"]))
        return p

    def summary(self) -> list:
        return list(self._created)


if __name__ == "__main__":
    # 演示：两个独立工厂造出的用户名天然不冲突
    f1, f2 = DataFactory(), DataFactory()
    u1, u2 = f1.user(), f2.user()
    print("factory1 user:", u1["username"])
    print("factory2 user:", u2["username"])
    print("不冲突:", u1["username"] != u2["username"])
    print("边界用例样本:", list(make_boundary_cases().keys()))
