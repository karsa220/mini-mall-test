"""
组件/接口测试层（测试金字塔中间层 · 全端点正负边界）
====================================================
用进程内 test_client 驱动每个端点，覆盖：
  成功路径 / 参数校验 / 鉴权 / 库存 / 优惠券 / 权限 / 状态机
约 30 例，与单元层、集成层共同构成多层防护。
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


@pytest.fixture()
def admin(client):
    tok = login(client, "admin", "admin123")
    return client, tok


# ---------------- 注册 / 登录 / 鉴权 ----------------
def test_register_success(client):
    u = {"username": "u_" + uuid.uuid4().hex[:10], "password": "Pwd_123456a"}
    assert client.post("/api/register", json=u).json["code"] == 0


def test_register_short_username(client):
    assert client.post("/api/register", json={"username": "ab", "password": "123456"}).json["code"] == 1004


def test_register_short_password(client):
    assert client.post("/api/register", json={"username": "abcde", "password": "123"}).json["code"] == 1005


def test_register_duplicate(client):
    u = {"username": "u_" + uuid.uuid4().hex[:10], "password": "Pwd_123456a"}
    assert client.post("/api/register", json=u).json["code"] == 0
    assert client.post("/api/register", json=u).json["code"] == 1006


def test_login_wrong_password(client):
    assert client.post("/api/login", json={"username": "alice", "password": "wrong"}).json["code"] == 1003


def test_login_empty(client):
    assert client.post("/api/login", json={"username": "", "password": ""}).json["code"] == 1001


def test_profile_requires_auth(client):
    assert client.get("/api/profile").json["code"] == 401


def test_logout_revokes_token(client):
    tok = login(client, "alice", "password123")
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/api/logout", headers=h).json["code"] == 0
    assert client.get("/api/profile", headers=h).json["code"] == 401


# ---------------- 地址 ----------------
def test_address_crud(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    r = c.post("/api/addresses", json={"name": "张三", "phone": "13800000000", "detail": "北京"}, headers=h)
    assert r.json["code"] == 0
    aid = r.json["data"]["id"]
    assert c.get("/api/addresses", headers=h).json["code"] == 0
    assert c.delete(f"/api/addresses/{aid}", headers=h).json["code"] == 0


def test_address_missing_fields(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/addresses", json={"name": "张三"}, headers=h).json["code"] == 5001


def test_address_delete_others_forbidden(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    # 用另一个用户建地址，再尝试删除（无权限）
    u2 = {"username": "u_" + uuid.uuid4().hex[:10], "password": "Pwd_123456a"}
    c.post("/api/register", json=u2)
    t2 = login(c, u2["username"], u2["password"])
    aid = c.post("/api/addresses", json={"name": "x", "phone": "1", "detail": "y"},
                 headers={"Authorization": f"Bearer {t2}"}).json["data"]["id"]
    assert c.delete(f"/api/addresses/{aid}", headers=h).json["code"] == 5002


# ---------------- 商品 ----------------
def test_products_list_and_search(client):
    assert client.get("/api/products").json["code"] == 0
    assert client.get("/api/products?q=键盘").json["code"] == 0
    assert client.get("/api/products?category=keyboard").json["code"] == 0
    assert client.get("/api/products?sort=price_asc").json["code"] == 0
    assert client.get("/api/products?page=1&page_size=2").json["code"] == 0


def test_products_pagination_bad_param(client):
    assert client.get("/api/products?page_size=abc").json["code"] == 2005


def test_product_detail_and_missing(client):
    assert client.get("/api/products/1").json["code"] == 0
    assert client.get("/api/products/999999").json["code"] == 2004


# ---------------- 管理端：商品 ----------------
def test_admin_create_product(admin):
    c, tok = admin
    h = {"Authorization": f"Bearer {tok}"}
    r = c.post("/api/admin/products", json={"name": "测试商品", "price": 9.9, "stock": 3}, headers=h)
    assert r.json["code"] == 0 and r.json["data"]["id"]


def test_admin_create_product_forbidden(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/admin/products", json={"name": "x", "price": 1, "stock": 1}, headers=h).json["code"] == 403


def test_admin_create_product_invalid(admin):
    c, tok = admin
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/admin/products", json={"name": "", "price": -1, "stock": 1}, headers=h).json["code"] == 2007


def test_admin_stock_adjust_and_clamp(admin):
    c, tok = admin
    h = {"Authorization": f"Bearer {tok}"}
    pid = c.post("/api/admin/products", json={"name": "库存商品", "price": 1, "stock": 2}, headers=h).json["data"]["id"]
    r = c.patch(f"/api/admin/products/{pid}/stock", json={"delta": -10}, headers=h)
    assert r.json["code"] == 0 and r.json["data"]["stock"] == 0  # 不允许负库存


# ---------------- 优惠券 ----------------
def test_coupon_claim_and_list(admin, user):
    c, atok = admin
    ah = {"Authorization": f"Bearer {atok}"}
    code = "CPN_" + uuid.uuid4().hex[:6].upper()
    assert c.post("/api/admin/coupons", json={"code": code, "type": "full_reduction",
                                              "threshold": 10, "value": 2}, headers=ah).json["code"] == 0
    uc, utok, _ = user
    uh = {"Authorization": f"Bearer {utok}"}
    assert uc.post("/api/coupons/claim", json={"code": code}, headers=uh).json["code"] == 0
    assert any(x["code"] == code for x in uc.get("/api/coupons", headers=uh).json["data"])


def test_coupon_claim_unknown(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/coupons/claim", json={"code": "NOPE"}, headers=h).json["code"] == 6001


def test_coupon_claim_limit(admin, user):
    c, atok = admin
    ah = {"Authorization": f"Bearer {atok}"}
    code = "CPN_" + uuid.uuid4().hex[:6].upper()
    c.post("/api/admin/coupons", json={"code": code, "per_user_limit": 1, "type": "full_reduction",
                                        "threshold": 1, "value": 1}, headers=ah)
    uc, utok, _ = user
    uh = {"Authorization": f"Bearer {utok}"}
    assert uc.post("/api/coupons/claim", json={"code": code}, headers=uh).json["code"] == 0
    assert uc.post("/api/coupons/claim", json={"code": code}, headers=uh).json["code"] == 6004


def test_admin_coupon_issue_forbidden(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/admin/coupons", json={"code": "X1", "type": "full_reduction",
                                              "threshold": 1, "value": 1}, headers=h).json["code"] == 403


# ---------------- 购物车 ----------------
def test_cart_add_and_view(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/cart/add", json={"product_id": 1, "quantity": 2}, headers=h).json["code"] == 0
    assert c.get("/api/cart", headers=h).json["data"]["total"] > 0


def test_cart_add_nonexist_product(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/cart/add", json={"product_id": 999999, "quantity": 1}, headers=h).json["code"] == 2001


def test_cart_add_nonint_qty(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/cart/add", json={"product_id": 1, "quantity": 1.5}, headers=h).json["code"] == 2002


def test_cart_add_over_stock(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/cart/add", json={"product_id": 3, "quantity": 9999}, headers=h).json["code"] == 2003


def test_cart_add_requires_auth(client):
    assert client.post("/api/cart/add", json={"product_id": 1, "quantity": 1}).json["code"] == 401


def test_bug001_zero_quantity_accepted(user):
    # BUG-001 固化：0/负数被后端接受（应拒）
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/cart/add", json={"product_id": 1, "quantity": 0}, headers=h).json["code"] == 0


def test_cart_update_and_remove(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/cart/add", json={"product_id": 1, "quantity": 2}, headers=h)
    assert c.patch("/api/cart/item", json={"product_id": 1, "quantity": 5}, headers=h).json["code"] == 0
    assert c.delete("/api/cart/item/1", headers=h).json["code"] == 0
    assert c.delete("/api/cart/clear", headers=h).json["code"] == 0


# ---------------- 订单：创建 ----------------
def test_order_create_empty_cart(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/order/create", json={}, headers=h).json["code"] == 3001


def test_order_create_deducts_stock(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/cart/add", json={"product_id": 2, "quantity": 3}, headers=h)
    before = c.get("/api/products/2").json["data"]["stock"]
    oid = c.post("/api/order/create", json={}, headers=h).json["data"]["order_id"]
    after = c.get("/api/products/2").json["data"]["stock"]
    assert before - after == 3
    # 支付
    assert c.post("/api/order/pay", json={"order_id": oid}, headers=h).json["code"] == 0


def test_order_create_with_unheld_coupon(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h)
    # 未领取 MAN30JIAN10 却尝试使用 → 应拒
    assert c.post("/api/order/create", json={"coupon_code": "MAN30JIAN10"}, headers=h).json["code"] == 3004


def test_order_create_bug002_exact_threshold(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    # 领取并使用满30减10，购物车恰好 30（商品3）
    assert c.post("/api/coupons/claim", json={"code": "MAN30JIAN10"}, headers=h).json["code"] == 0
    c.post("/api/cart/add", json={"product_id": 3, "quantity": 1}, headers=h)
    r = c.post("/api/order/create", json={"coupon_code": "MAN30JIAN10"}, headers=h)
    assert r.json["code"] == 3002 and r.json["msg"] == "未达到优惠券使用门槛"


# ---------------- 订单：支付 / 状态机 ----------------
def test_order_pay_not_found(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/order/pay", json={"order_id": "OD_NONE"}, headers=h).json["code"] == 4001


def test_order_pay_others_forbidden(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h)
    oid = c.post("/api/order/create", json={}, headers=h).json["data"]["order_id"]
    # 另一个用户尝试支付
    u2 = {"username": "u_" + uuid.uuid4().hex[:10], "password": "Pwd_123456a"}
    c.post("/api/register", json=u2)
    t2 = login(c, u2["username"], u2["password"])
    assert c.post("/api/order/pay", json={"order_id": oid}, headers={"Authorization": f"Bearer {t2}"}).json["code"] == 4002


def test_order_cancel_and_refund_state_machine(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h)
    oid = c.post("/api/order/create", json={}, headers=h).json["data"]["order_id"]
    assert c.post(f"/api/order/{oid}/cancel", headers=h).json["code"] == 0
    # 已取消订单不可支付
    assert c.post("/api/order/pay", json={"order_id": oid}, headers=h).json["code"] == 4003
    # 重新走支付->退款
    c.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h)
    oid2 = c.post("/api/order/create", json={}, headers=h).json["data"]["order_id"]
    assert c.post("/api/order/pay", json={"order_id": oid2}, headers=h).json["code"] == 0
    assert c.post(f"/api/order/{oid2}/refund", headers=h).json["code"] == 0
    assert c.post(f"/api/order/{oid2}/refund", headers=h).json["code"] == 4005  # 重复退款


def test_order_detail_others_forbidden(user):
    c, tok, _ = user
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h)
    oid = c.post("/api/order/create", json={}, headers=h).json["data"]["order_id"]
    u2 = {"username": "u_" + uuid.uuid4().hex[:10], "password": "Pwd_123456a"}
    c.post("/api/register", json=u2)
    t2 = login(c, u2["username"], u2["password"])
    assert c.get(f"/api/orders/{oid}", headers={"Authorization": f"Bearer {t2}"}).json["code"] == 4002


# ---------------- 混沌 / 可观测 ----------------
def test_chaos_down_returns_503(client):
    tok = login(client, "alice", "password123")
    h = {"Authorization": f"Bearer {tok}"}
    client.post("/api/chaos/set", json={"down": True}, headers=h)
    assert client.get("/api/products", headers=h).json["code"] == 503
    client.post("/api/chaos/reset", json={}, headers=h)
    assert client.get("/api/products", headers=h).json["code"] == 0


def test_metrics_endpoint(client):
    assert client.get("/metrics").json["code"] == 0
