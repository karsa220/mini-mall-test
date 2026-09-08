"""
组件/集成层测试（Flask test client，进程内）
============================
用 server.app.test_client() 在进程内驱动全部路由，既能做端到端接口校验，
又能被 pytest-cov 计入 app 模块覆盖率（HTTP 子进程模式测不到行覆盖）。
这是测试金字塔的「集成层」：比纯单元稍重，但比真机/UI 更快更稳。

同时固化三个预埋缺陷的边界，作为回归守护：
  BUG-001 数量下限未校验 / BUG-002 优惠券门槛 / BUG-003 幂等（见 chaos 模块）
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import server as s  # noqa: E402

client = s.app.test_client()
USER = {"username": "alice", "password": "password123"}


def _login():
    r = client.post("/api/login", json=USER)
    assert r.status_code == 200 and r.json["code"] == 0
    return r.json["data"]["token"]


def test_login_and_products():
    assert _login()
    assert client.get("/api/products").json["code"] == 0


def test_cart_order_pay_flow():
    token = _login()
    h = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h).json["code"] == 0
    ro = client.post("/api/order/create", json={}, headers=h)
    assert ro.json["code"] == 0
    oid = ro.json["data"]["order_id"]
    assert client.post("/api/order/pay", json={"order_id": oid}, headers=h).json["code"] == 0
    # 订单列表应含刚支付的订单
    mine = client.get("/api/orders", headers=h).json["data"]
    assert any(o["order_id"] == oid for o in mine)


def test_metrics_endpoint():
    assert client.get("/metrics").json["code"] == 0


def test_chaos_injection():
    token = _login()
    h = {"Authorization": f"Bearer {token}"}
    client.post("/api/chaos/set", json={"down": True}, headers=h)
    assert client.get("/api/products", headers=h).json["code"] == 503
    client.post("/api/chaos/reset", json={}, headers=h)
    assert client.get("/api/products", headers=h).json["code"] == 0


def test_bug001_zero_quantity_accepted():
    token = _login()
    h = {"Authorization": f"Bearer {token}"}
    # BUG-001：quantity=0 后端未拒（应返回错误码），这里固化该缺陷边界
    rc = client.post("/api/cart/add", json={"product_id": 1, "quantity": 0}, headers=h)
    assert rc.json["code"] == 0, "复现 BUG-001：0 数量被接受"
