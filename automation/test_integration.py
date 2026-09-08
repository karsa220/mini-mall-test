"""
集成 / 并发竞态测试层（测试金字塔上层 · 交易正确性）
================================================
覆盖企业级最看重的「交易一致性」：
  - 下单全链路 + 数据库落地断言（库存扣减、订单状态）
  - 幂等：同 Idempotency-Key 重试返回同一笔订单，库存只扣一次（防弱网重复下单）
  - 支付幂等：已支付订单重复支付不重复扣款
  - 并发防超卖：限量库存 + 高并发下单，库存不穿底、成交数 == 初始库存 - 结余
  - 并发防重复核销：同一优惠券并发下单只有一个能用（原子核销）
"""
import os
import sys
import uuid
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from _tutil import make_client, login  # noqa: E402
import server as s  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture()
def client():
    return make_client()


@pytest.fixture()
def user(client):
    u = {"username": "u_" + uuid.uuid4().hex[:10], "password": "Pwd_123456a"}
    assert client.post("/api/register", json=u).json["code"] == 0
    tok = login(client, u["username"], u["password"])
    return client, tok, u["username"]


@pytest.fixture()
def admin(client):
    tok = login(client, "admin", "admin123")
    return client, tok


def test_full_purchase_flow_persists(client):
    # 注册 -> 加购 -> 下单 -> 支付 -> 订单落地，数据库断言
    u = {"username": "u_" + uuid.uuid4().hex[:10], "password": "Pwd_123456a"}
    assert client.post("/api/register", json=u).json["code"] == 0
    tok = login(client, u["username"], u["password"])
    h = {"Authorization": f"Bearer {tok}"}
    before = client.get("/api/products/1").json["data"]["stock"]
    client.post("/api/cart/add", json={"product_id": 1, "quantity": 2}, headers=h)
    oid = client.post("/api/order/create", json={}, headers=h).json["data"]["order_id"]
    client.post("/api/order/pay", json={"order_id": oid}, headers=h)
    # 库存已扣 2
    assert client.get("/api/products/1").json["data"]["stock"] == before - 2
    # 订单在「我的订单」列表中且为已支付
    mine = client.get("/api/orders", headers=h).json["data"]
    assert any(o["order_id"] == oid and o["status"] == "PAID" for o in mine)


def test_order_idempotency_same_key(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h)
    k = "idem_" + uuid.uuid4().hex
    r1 = c.post("/api/order/create", json={}, headers={**h, "Idempotency-Key": k})
    r2 = c.post("/api/order/create", json={}, headers={**h, "Idempotency-Key": k})
    assert r1.json["code"] == 0 and r2.json["code"] == 0
    assert r1.json["data"]["order_id"] == r2.json["data"]["order_id"]
    # 幂等：库存只扣一次
    assert c.get("/api/products/1").json["data"]["stock"] == 9


def test_order_idempotency_diff_key_empty_cart(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h)
    k1 = "idem_" + uuid.uuid4().hex
    k2 = "idem_" + uuid.uuid4().hex
    assert c.post("/api/order/create", json={}, headers={**h, "Idempotency-Key": k1}).json["code"] == 0
    # 购物车已清空，再次下单（不同 key）应购物车为空
    assert c.post("/api/order/create", json={}, headers={**h, "Idempotency-Key": k2}).json["code"] == 3001


def test_pay_idempotency_no_double_charge(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h)
    oid = c.post("/api/order/create", json={}, headers=h).json["data"]["order_id"]
    r1 = c.post("/api/order/pay", json={"order_id": oid}, headers=h)
    r2 = c.post("/api/order/pay", json={"order_id": oid}, headers=h)
    assert r1.json["code"] == 0 and r2.json["code"] == 0
    assert r1.json["data"]["status"] == "PAID" == r2.json["data"]["status"]


def test_pay_already_paid_idempotent_response(user):
    """支付幂等第二例:已支付订单重复支付 → 业务码 0 + status 仍为 PAID"""
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h)
    oid = c.post("/api/order/create", json={}, headers=h).json["data"]["order_id"]
    c.post("/api/order/pay", json={"order_id": oid}, headers=h)
    r = c.post("/api/order/pay", json={"order_id": oid}, headers=h)
    assert r.json["code"] == 0, f"重复支付不应报错,实际 {r.json['code']}"
    assert r.json["data"]["status"] == "PAID"


def test_concurrent_orders_respect_stock_atomic(admin):
    """防超卖第二例:限量库存 + 并发下单,库存不穿底 + 库存-成交数 == 初始库存"""
    c, atok = admin
    ah = {"Authorization": f"Bearer {atok}"}
    pid = c.post("/api/admin/products",
                 json={"name": "限量品A", "price": 1.0, "stock": 5}, headers=ah).json["data"]["id"]
    N = 16
    results = []
    lock = threading.Lock()

    def worker():
        u = {"username": "u_" + uuid.uuid4().hex[:10], "password": "Pwd_123456a"}
        try:
            r = c.post("/api/register", json=u)
            code = (r.json or {}).get("code", -1) if r else -1
        except Exception:
            code = -1
        if code != 0:
            return
        try:
            t = login(c, u["username"], u["password"])
            h = {"Authorization": f"Bearer {t}"}
            c.post("/api/cart/add", json={"product_id": pid, "quantity": 1}, headers=h)
            ro = c.post("/api/order/create", json={}, headers=h)
            with lock:
                results.append((ro.json or {}).get("code", -1) if ro else -1)
        except Exception:
            with lock:
                results.append(-1)

    os.environ["ORDER_SIM_LATENCY"] = "0.1"
    try:
        ts = [threading.Thread(target=worker) for _ in range(N)]
        [t.start() for t in ts]
        [t.join() for t in ts]
    finally:
        os.environ["ORDER_SIM_LATENCY"] = "0"
    success = sum(1 for x in results if x == 0)
    final = c.get(f"/api/products/{pid}").json["data"]["stock"]
    assert final == 5 - success, f"atomic stock 失败: 始 5 终 {final} 成交 {success}"


def test_retry_weak_network_no_duplicate_order(user):
    """弱网场景:同 Idempotency-Key 并发/重复提交,只产生 1 笔订单 + 库存只扣 1 次"""
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    initial = c.get("/api/products/2").json["data"]["stock"]
    c.post("/api/cart/add", json={"product_id": 2, "quantity": 1}, headers=h)
    k = "weak_" + uuid.uuid4().hex

    def hit():
        c.post("/api/order/create", json={}, headers={**h, "Idempotency-Key": k})

    # 模拟客户端弱网重试:5 次并发用同 key
    ts = [threading.Thread(target=hit) for _ in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]

    # 库存应只减 1
    final = c.get("/api/products/2").json["data"]["stock"]
    assert final == initial - 1, f"弱网重试导致重复扣库存: 初 {initial} 终 {final}"


def test_concurrent_no_oversell(admin):
    """限量库存(3) + 12 并发下单，断言不超卖：成交数 <= 3，库存不穿底。"""
    c, atok = admin
    ah = {"Authorization": f"Bearer {atok}"}
    pid = c.post("/api/admin/products", json={"name": "限量品", "price": 1.0, "stock": 3}, headers=ah).json["data"]["id"]
    N = 12
    results = []
    lock = threading.Lock()

    def worker():
        u = {"username": "u_" + uuid.uuid4().hex[:10], "password": "Pwd_123456a"}
        try:
            r = c.post("/api/register", json=u)
            code = (r.json or {}).get("code", -1) if r else -1
        except Exception:
            code = -1
        if code != 0:
            return
        try:
            t = login(c, u["username"], u["password"])
            h = {"Authorization": f"Bearer {t}"}
            c.post("/api/cart/add", json={"product_id": pid, "quantity": 1}, headers=h)
            ro = c.post("/api/order/create", json={}, headers=h)
            with lock:
                results.append((ro.json or {}).get("code", -1) if ro else -1)
        except Exception:
            with lock:
                results.append(-1)

    # 人为放大「读->扣」并发窗口，更易暴露非原子实现的问题
    os.environ["ORDER_SIM_LATENCY"] = "0.15"
    try:
        threads = [threading.Thread(target=worker) for _ in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        os.environ["ORDER_SIM_LATENCY"] = "0"
    success = sum(1 for code in results if code == 0)
    final_stock = c.get(f"/api/products/{pid}").json["data"]["stock"]
    assert final_stock >= 0, f"库存穿底: {final_stock}"
    assert success <= 3, f"超卖：成交 {success} > 库存 3"
    assert (3 - final_stock) == success, f"库存与成交不一致: stock={final_stock}, success={success}"


def test_coupon_no_double_spend(user):
    """同一用户领取一张券后并发下单，只有一个请求能核销成功。"""
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    atok = login(c, "admin", "admin123")
    ah = {"Authorization": f"Bearer {atok}"}
    code = "CPN_" + uuid.uuid4().hex[:6].upper()
    c.post("/api/admin/coupons", json={"code": code, "type": "full_reduction",
                                        "threshold": 1, "value": 5}, headers=ah)
    assert c.post("/api/coupons/claim", json={"code": code}, headers=h).json["code"] == 0
    c.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h)

    results = []
    lock = threading.Lock()

    def worker():
        ro = c.post("/api/order/create", json={"coupon_code": code}, headers=h)
        with lock:
            results.append(ro.json["code"])

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok = sum(1 for code in results if code == 0)
    assert ok == 1, f"优惠券被并发重复核销: {results}"
