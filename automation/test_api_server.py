"""
组件/集成层冒烟（Flask test client，进程内）
==========================================
早期 5 例冒烟，现改用 _tutil 做用例级隔离（每例重建 DB + 清鉴权/限流状态），
与 test_component/test_integration/test_security 同跑也不会串数据。
同时固化预埋缺陷边界：BUG-001（数量下限未校验）、BUG-002（优惠券门槛）。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from _tutil import reset_server, login as _login_helper  # noqa: E402
import server as s  # noqa: E402

USER = {"username": "alice", "password": "password123"}


@pytest.fixture(scope="function", autouse=True)
def _iso():
    reset_server()
    yield


@pytest.fixture()
def client():
    return s.app.test_client()


def _login(client):
    r = client.post("/api/login", json=USER)
    assert r.status_code == 200 and r.json["code"] == 0
    return r.json["data"]["token"]


def test_login_and_products(client):
    assert _login(client)
    assert client.get("/api/products").json["code"] == 0


def test_cart_order_pay_flow(client):
    token = _login(client)
    h = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h).json["code"] == 0
    ro = client.post("/api/order/create", json={}, headers=h)
    assert ro.json["code"] == 0
    oid = ro.json["data"]["order_id"]
    assert client.post("/api/order/pay", json={"order_id": oid}, headers=h).json["code"] == 0
    mine = client.get("/api/orders", headers=h).json["data"]
    assert any(o["order_id"] == oid for o in mine)


def test_metrics_endpoint(client):
    assert client.get("/metrics").json["code"] == 0


def test_chaos_injection(client):
    token = _login(client)
    h = {"Authorization": f"Bearer {token}"}
    client.post("/api/chaos/set", json={"down": True}, headers=h)
    assert client.get("/api/products", headers=h).json["code"] == 503
    client.post("/api/chaos/reset", json={}, headers=h)
    assert client.get("/api/products", headers=h).json["code"] == 0


def test_bug001_zero_quantity_accepted(client):
    token = _login(client)
    h = {"Authorization": f"Bearer {token}"}
    rc = client.post("/api/cart/add", json={"product_id": 1, "quantity": 0}, headers=h)
    assert rc.json["code"] == 0, "复现 BUG-001：0 数量被接受"
