"""
安全测试层（企业级专项 · 鉴权 / 越权 / 注入 / 限流）
================================================
覆盖面经高频安全考点：
  - 未鉴权 / 伪造 token 一律 401
  - 越权访问他人资源（订单 / 地址）一律拒绝
  - 管理端接口普通用户不可达（403）
  - SQL 注入：搜索参数化查询，注入串不应导致 500 或数据泄露
  - 弱口令注册被拒
  - 登录暴力破解限流（连续失败达阈值返回 429）
  - 敏感字段（密码哈希）不出现在响应
"""
import os
import sys
import uuid

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


def test_protected_requires_token(client):
    for path in ["/api/profile", "/api/cart", "/api/orders",
                 "/api/products/1" if False else "/api/order/create"]:
        pass
    assert client.get("/api/profile").json["code"] == 401
    assert client.post("/api/order/create", json={}).json["code"] == 401
    assert client.get("/api/cart").json["code"] == 401


def test_tampered_token_rejected(client):
    h = {"Authorization": "Bearer tk_tampered.invalid.signature"}
    assert client.get("/api/profile", headers=h).json["code"] == 401


def test_access_others_order_forbidden(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h)
    oid = c.post("/api/order/create", json={}, headers=h).json["data"]["order_id"]
    # 受害者看不到攻击者的订单
    victim = {"username": "u_" + uuid.uuid4().hex[:10], "password": "Pwd_123456a"}
    c.post("/api/register", json=victim)
    vt = login(c, victim["username"], victim["password"])
    assert c.get(f"/api/orders/{oid}", headers={"Authorization": f"Bearer {vt}"}).json["code"] == 4002
    assert c.post("/api/order/pay", json={"order_id": oid}, headers={"Authorization": f"Bearer {vt}"}).json["code"] == 4002


def test_admin_endpoint_forbidden_for_normal(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/admin/products", json={"name": "x", "price": 1, "stock": 1}, headers=h).json["code"] == 403
    assert c.post("/api/admin/coupons", json={"code": "X", "type": "full_reduction",
                                              "threshold": 1, "value": 1}, headers=h).json["code"] == 403


def test_sql_injection_in_search_is_safe(client):
    # 注入串不应导致 500，也不应泄露额外数据（参数化查询）
    inj = "'; DROP TABLE products; --"
    r = client.get("/api/products", query_string={"q": inj})
    assert r.status_code == 200 and r.json["code"] == 0
    # 表依然存在，可正常查询
    assert client.get("/api/products/1").json["code"] == 0


def test_weak_password_rejected(client):
    assert client.post("/api/register", json={"username": "weak1", "password": "123"}).json["code"] == 1005


def test_login_bruteforce_rate_limited(client):
    s._LOGIN_FAIL.clear()
    user = "alice"  # 已播种账号
    # 连续 8 次错误密码
    codes = []
    for _ in range(8):
        codes.append(client.post("/api/login", json={"username": user, "password": "wrong"}).json["code"])
    # 第 9 次应被限流（即使密码正确也被拒，直到窗口过期）
    ninth = client.post("/api/login", json={"username": user, "password": "password123"}).json["code"]
    assert set(codes) == {1003}
    assert ninth == 429


def test_sensitive_fields_not_leaked(client):
    r = client.post("/api/login", json={"username": "alice", "password": "password123"})
    body = r.json
    assert "pw_hash" not in body.get("data", {})
    assert "pw_hash" not in body
    prof = client.get("/api/profile", headers={"Authorization": f"Bearer {body['data']['token']}"})
    assert "pw_hash" not in prof.json.get("data", {})
