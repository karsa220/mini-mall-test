"""
Locust 性能压测脚本（MiniMall 交易链路）
============================
对标字节测开 JD 明确点名的 Locust / JMeter，以及面经高频追问：
  「性能测试关注哪些参数？」「怎么分析瓶颈？」「容量规划怎么做？」

覆盖交易主链路：登录 -> 加购 -> 下单 -> 支付，模拟多用户并发。
通过 run_perf_check.py 以「无头模式」运行并解析统计，做 CI 性能门禁
（p95 时延、错误率不达标则构建失败，等价于行业实践中的 k6 thresholds）。

运行（直接看波形，本地调试用）：
  locust -f automation/perf_test.py -H http://127.0.0.1:5000 --web-host 127.0.0.1
"""
import random
from locust import HttpUser, task, between


# 压测使用的固定测试账号（server.py 内存用户表内置）
TEST_USER = {"username": "alice", "password": "password123"}


class MiniMallUser(HttpUser):
    """模拟一个用户完成一次交易闭环"""
    wait_time = between(0.2, 1.0)

    def on_start(self):
        # 每个虚拟用户登录拿到 token
        r = self.client.post("/api/login",
                              json=TEST_USER,
                              name="login")
        if r.status_code == 200:
            self.token = r.json().get("data", {}).get("token", "")
        else:
            self.token = ""
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(5)
    def view_products(self):
        self.client.get("/api/products", name="view_products")

    @task(3)
    def add_cart(self):
        pid = random.choice([1, 2, 3])
        self.client.post("/api/cart/add",
                         json={"product_id": pid, "quantity": 1},
                         headers=self.headers, name="add_cart")

    @task(2)
    def create_and_pay_order(self):
        # 先加购保证购物车非空，再下单、支付、清购物车（避免跨用户购物车冲突）
        self.client.post("/api/cart/add",
                         json={"product_id": 1, "quantity": 1},
                         headers=self.headers, name="pre_add")
        c = self.client.post("/api/order/create",
                            json={}, headers=self.headers, name="create_order")
        if c.status_code == 200:
            oid = c.json().get("data", {}).get("order_id")
            if oid:
                self.client.post("/api/order/pay",
                                json={"order_id": oid},
                                headers=self.headers, name="pay_order")
        self.client.delete("/api/cart/clear", headers=self.headers, name="clear_cart")
