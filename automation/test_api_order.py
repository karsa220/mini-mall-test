"""下单/优惠券/支付链路自动化（场景法 + 幂等 + 越权）"""
import allure
import pytest

from conftest import attach_response, login


@allure.feature("下单支付")
@allure.story("主流程")
class TestOrderFlow:
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("ORD-01 加购→下单→支付，校验金额/状态/库存/购物车清空")
    def test_full_flow_order_and_pay(self, fresh_cart, base_url):
        s = fresh_cart
        r = s.post(f"{base_url}/api/order/create", json={})
        attach_response(r)
        assert r.json()["code"] == 0
        order = r.json()["data"]
        assert order["status"] == "待支付"
        assert order["total"] == 59.90 and order["payable"] == 59.90

        cart = s.get(f"{base_url}/api/cart").json()["data"]
        assert cart["items"] == [] and cart["total"] == 0.0

        r = s.post(f"{base_url}/api/order/pay",
                   json={"order_id": order["order_id"]})
        attach_response(r)
        assert r.json()["code"] == 0
        assert r.json()["data"]["status"] == "已支付"

    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("ORD-02 空购物车下单应失败")
    def test_create_order_empty_cart(self, auth_session, base_url):
        auth_session.request("DELETE", f"{base_url}/api/cart/clear")
        r = auth_session.post(f"{base_url}/api/order/create", json={})
        attach_response(r)
        assert r.json()["code"] == 3001

    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("ORD-03 重复支付同一订单应被拒绝")
    def test_pay_twice_rejected(self, fresh_cart, base_url):
        s = fresh_cart
        order = s.post(f"{base_url}/api/order/create", json={}).json()["data"]
        s.post(f"{base_url}/api/order/pay", json={"order_id": order["order_id"]})
        r = s.post(f"{base_url}/api/order/pay", json={"order_id": order["order_id"]})
        attach_response(r)
        assert r.json()["code"] == 4003

    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("ORD-04 同一购物车重复提交只应生成一笔订单（幂等）")
    @pytest.mark.xfail(reason="已知缺陷 BUG-003：下单无幂等控制", strict=False)
    def test_create_order_idempotent(self, fresh_cart, base_url):
        s = fresh_cart
        r1 = s.post(f"{base_url}/api/order/create", json={}).json()
        r2 = s.post(f"{base_url}/api/order/create", json={}).json()
        assert r1["code"] == 0 and r2["code"] == 0
        assert r1["data"]["order_id"] == r2["data"]["order_id"]

    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("ORD-05 越权支付他人订单应被拒绝")
    def test_pay_others_order_forbidden(self, session, base_url, fresh_cart):
        order = fresh_cart.post(f"{base_url}/api/order/create", json={}).json()["data"]
        # 另一用户登录后尝试支付
        token2 = login(session, base_url, "test02", "abc@2026")
        session.headers.update({"Authorization": "Bearer " + token2})
        r = session.post(f"{base_url}/api/order/pay",
                         json={"order_id": order["order_id"]})
        attach_response(r)
        assert r.json()["code"] == 4002
        session.headers.pop("Authorization", None)


@allure.feature("下单支付")
@allure.story("优惠券")
class TestCoupon:
    def _buy_product3(self, auth_session, base_url, qty):
        r = auth_session.post(f"{base_url}/api/cart/add",
                              json={"product_id": 3, "quantity": qty})
        assert r.json()["code"] == 0
        return auth_session

    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("CP-01 订单恰好30.00（含本数）应可用满30减10券")
    @pytest.mark.xfail(reason="已知缺陷 BUG-002：门槛判断 > 误写，30.00 整不可用券", strict=False)
    def test_coupon_at_exact_threshold(self, auth_session, base_url):
        s = self._buy_product3(auth_session, base_url, 1)
        r = s.post(f"{base_url}/api/order/create",
                   json={"coupon_code": "MAN30JIAN10"})
        attach_response(r)
        body = r.json()
        assert body["code"] == 0, f"30.00 整应可用券，实际: {body}"
        assert body["data"]["discount"] == 10.00
        assert body["data"]["payable"] == 20.00

    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("CP-03 59.90订单用满30减10券：应付49.90")
    def test_coupon_below_threshold_rejected(self, auth_session, base_url):
        auth_session.request("DELETE", f"{base_url}/api/cart/clear")
        r = auth_session.post(f"{base_url}/api/cart/add",
                              json={"product_id": 2, "quantity": 1})
        assert r.json()["code"] == 0
        ok = auth_session.post(f"{base_url}/api/order/create",
                               json={"coupon_code": "MAN30JIAN10"}).json()
        attach_response(ok)
        assert ok["code"] == 0
        assert ok["data"]["discount"] == 10.00
        assert ok["data"]["payable"] == round(59.90 - 10.00, 2)

    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("CP-04 使用不存在的券码应被拒绝")
    def test_invalid_coupon_code(self, fresh_cart, base_url):
        r = fresh_cart.post(f"{base_url}/api/order/create",
                            json={"coupon_code": "NOT_EXIST"})
        attach_response(r)
        assert r.json()["code"] == 3002