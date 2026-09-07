"""购物车接口自动化（YAML 数据驱动 + 边界值）"""
import allure
import pytest

from conftest import attach_response, load_yaml

cases = load_yaml("test_cart.yaml")


def case_mark(case):
    marks = []
    if case.get("xfail_bug"):
        marks.append(pytest.mark.xfail(
            reason=f'已知缺陷 {case["xfail_bug"]}，见缺陷报告', strict=False))
    return marks


@allure.feature("购物车")
@allure.story("加购")
class TestCart:
    @pytest.mark.parametrize(
        "case",
        [pytest.param(c, marks=case_mark(c), id=c["case_id"]) for c in cases],
    )
    @allure.severity(allure.severity_level.CRITICAL)
    def test_cart_add(self, auth_session, base_url, case):
        allure.dynamic.title(f"{case['case_id']} {case['title']}")
        # 测试前清空购物车，避免用例间状态串
        auth_session.request("DELETE", f"{base_url}/api/cart/clear")
        r = auth_session.post(f"{base_url}/api/cart/add",
                              json={"product_id": case["product_id"],
                                    "quantity": case["quantity"]})
        attach_response(r)
        body = r.json()
        assert body["code"] == case["expect_code"], \
            f'{case["case_id"]} {case["title"]}: 期望 {case["expect_code"]}, 实际 {body}'