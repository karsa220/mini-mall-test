"""
MiniMall 数据层（SQLAlchemy + SQLite）
=====================================
企业级被测系统的持久化底座：
  - 真实关系模型（用户/地址/商品/购物车/优惠券/订单/订单项/幂等键）
  - 相比原内存字典版，支持并发下的库存一致性、订单幂等、用户隔离
  - SQLite 文件库，零外部依赖，CI 与本机均可直接跑

测试隔离：通过环境变量 MINIMALL_DB 指定独立库文件；conftest 在每用例前
reset_db() 重建并重新播种基础数据，保证用例互不影响（实测数据工厂命名空间
与之配合，双重防污染）。
"""
import os
from datetime import datetime, timedelta

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Text, update as sa_update,
)
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = os.environ.get(
    "MINIMALL_DB",
    os.path.join(os.path.dirname(__file__), "minimall.db"),
)
# check_same_thread=False 允许 Flask 多线程 + 测试并发访问；sqlite 文件锁保证写原子
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
Session = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


# ---------------- 模型 ----------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, index=True)
    pw_hash = Column(String(128), default="")
    role = Column(String(16), default="normal")        # normal | admin
    created_at = Column(DateTime, default=datetime.utcnow)


class Address(Base):
    __tablename__ = "addresses"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String(64))
    phone = Column(String(32))
    detail = Column(String(256))


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(128))
    category = Column(String(32), default="general")
    price = Column(Float)
    stock = Column(Integer, default=0)
    status = Column(Integer, default=1)               # 1 在售 | 0 下架


class CartItem(Base):
    __tablename__ = "cart_items"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    qty = Column(Integer, default=1)


class Coupon(Base):
    __tablename__ = "coupons"
    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, index=True)
    type = Column(String(16), default="full_reduction")   # full_reduction | discount
    threshold = Column(Float, default=0.0)                # 满减门槛
    value = Column(Float, default=0.0)                    # 满减金额
    rate = Column(Float, default=0.0)                     # 折扣率（discount 型）
    cap = Column(Float, default=0.0)                      # 折扣上限，0=不限
    category = Column(String(32), default=None)           # 限定品类，None=全品类
    stackable = Column(Boolean, default=False)            # 是否可叠加
    per_user_limit = Column(Integer, default=1)           # 每人限领
    total_limit = Column(Integer, default=0)              # 总发行量，0=不限
    start_at = Column(DateTime, default=datetime.utcnow)
    end_at = Column(DateTime, default=None)               # 有效期止，None=长期
    desc = Column(String(128), default="")


class UserCoupon(Base):
    __tablename__ = "user_coupons"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    coupon_id = Column(Integer, ForeignKey("coupons.id"))
    used = Column(Boolean, default=False)
    claimed_at = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    order_no = Column(String(40), unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    status = Column(String(16), default="UNPAID")         # UNPAID PAID CANCELLED REFUNDED
    total = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)
    payable = Column(Float, default=0.0)
    coupon_id = Column(Integer, ForeignKey("coupons.id"), nullable=True)
    address_id = Column(Integer, ForeignKey("addresses.id"), nullable=True)
    idem_key = Column(String(64), index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, default=None)


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)
    product_id = Column(Integer)
    name = Column(String(128))
    price = Column(Float)
    qty = Column(Integer)


class Idempotency(Base):
    __tablename__ = "idempotency"
    key = Column(String(64), primary_key=True)
    order_no = Column(String(40), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------- 初始化与播种 ----------------
def _seed():
    """仅当库为空时播种基础数据，保证 alice / 商品 1/2/3 / MAN30JIAN10 等契约稳定。"""
    from werkzeug.security import generate_password_hash
    s = Session()
    try:
        if s.query(User).count() > 0:
            return
        users = {
            "admin": ("admin123", "admin"),
            "alice": ("password123", "normal"),
            "test01": ("123456", "normal"),
            "test02": ("abc@2026", "normal"),
            "bob": ("password123", "normal"),
        }
        uid = {}
        for name, (pw, role) in users.items():
            u = User(username=name, pw_hash=generate_password_hash(pw), role=role)
            s.add(u)
            s.flush()
            uid[name] = u.id

        products = [
            Product(id=1, name="机械键盘", category="keyboard", price=199.00, stock=10),
            Product(id=2, name="无线鼠标", category="mouse", price=59.90, stock=50),
            Product(id=3, name="显示器支架", category="stand", price=30.00, stock=5),
            Product(id=4, name="USB-C 扩展坞", category="hub", price=129.00, stock=8),
        ]
        for p in products:
            s.add(p)

        # 满30减10（与旧单测和 perf/chaos 契约一致）
        s.add(Coupon(code="MAN30JIAN10", type="full_reduction",
                     threshold=30.0, value=10.0, desc="满30减10"))
        # 折扣券：键盘品类 8 折，封顶 50
        s.add(Coupon(code="KB80", type="discount", rate=0.20, cap=50.0,
                     category="keyboard", desc="键盘8折封顶50"))
        # 可叠加的满100减15
        s.add(Coupon(code="STACK100", type="full_reduction", threshold=100.0,
                     value=15.0, stackable=True, desc="满100减15(可叠加)"))
        s.commit()
    finally:
        s.close()


def init_db(seed=True):
    Base.metadata.create_all(engine)
    if seed:
        _seed()


def reset_db():
    """测试隔离用：清空全部表并重新播种，保证用例间零污染。"""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    _seed()
