import os

import allure
import pytest
import requests
import yaml


def pytest_collection_modifyitems(config, items):
    """按用例 ID（如 LOGIN-01）补 allure.title，便于报告展示"""
    for item in items:
        if hasattr(item, "callspec") and item.callspec.params.get("case_id"):
            cid = item.callspec.params["case_id"]
            item._nodeid = f"{cid} :: {item.name}"


@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("BASE_URL", "http://127.0.0.1:5000")


@pytest.fixture(scope="session")
def session(base_url):
    """带步骤重试的会话"""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    yield s
    s.close()


@pytest.fixture(scope="session")
def token(session, base_url):
    """登录拿到 token：默认 alice，CI 环境用 CI_USER/CI_PASS 覆盖"""
    username = os.environ.get("CI_USER", "alice")
    password = os.environ.get("CI_PASS", "password123")
    r = session.post(f"{base_url}/api/login",
                     json={"username": username, "password": password})
    assert r.json().get("code") == 0, f"登录失败：{r.text}"
    return r.json()["data"]["token"]


@pytest.fixture()
def auth_session(session, token):
    """已鉴权的 session：Authorization 头带 Bearer 前缀"""
    session.headers.update({"Authorization": "Bearer " + token})
    yield session
    session.headers.pop("Authorization", None)


@pytest.fixture()
def fresh_cart(auth_session, base_url):
    """构造非空购物车：先清空再加购，避免用例间状态串"""
    auth_session.request("DELETE", f"{base_url}/api/cart/clear")
    r = auth_session.post(f"{base_url}/api/cart/add",
                          json={"product_id": 2, "quantity": 1})
    assert r.json().get("code") == 0, f"加购失败：{r.text}"
    return auth_session


def login(s, base_url, username, password):
    """辅助：用一个不带认证的 session 登录拿 token"""
    r = s.post(f"{base_url}/api/login",
               json={"username": username, "password": password})
    assert r.json().get("code") == 0, f"登录 {username} 失败：{r.text}"
    return r.json()["data"]["token"]


def load_yaml(name):
    """加载 data 目录下的 YAML 用例数据"""
    path = os.path.join(os.path.dirname(__file__), "data", name)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def attach_response(resp):
    """把响应内容作为附件挂到 allure 报告：传 Response 对象或 dict 都可以"""
    if isinstance(resp, dict):
        body, method, url = resp, "(dict)", "(dict)"
    else:
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        method, url = resp.request.method, resp.url
    allure.attach(
        body=str(body)[:2000],
        name=f"Response {method} {url}",
        attachment_type=allure.attachment_type.JSON,
    )