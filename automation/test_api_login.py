"""登录接口自动化（YAML 数据驱动）"""
import allure
import pytest

from conftest import attach_response, load_yaml

cases = load_yaml("test_login.yaml")


@allure.feature("登录鉴权")
@allure.story("用户登录")
class TestLogin:
    @pytest.mark.parametrize("case", cases, ids=[c["case_id"] for c in cases])
    @allure.severity(allure.severity_level.CRITICAL)
    def test_login(self, session, base_url, case):
        allure.dynamic.title(f"{case['case_id']} {case['title']}")
        r = session.post(f"{base_url}/api/login",
                         json={"username": case["username"],
                               "password": case["password"]})
        attach_response(r)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == case["expect_code"], \
            f'{case["case_id"]} {case["title"]}: 期望 {case["expect_code"]}, 实际 {body}'
        if case["expect_code"] == 0:
            assert body["data"]["token"], "登录成功必须返回 token"

    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("ORD-06 无token访问交易接口应返回401")
    def test_no_token_access_trade_api(self, session, base_url):
        r = session.post(f"{base_url}/api/cart/add",
                         json={"product_id": 1, "quantity": 1})
        attach_response(r)
        assert r.json()["code"] == 401