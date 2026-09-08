"""
Locust 性能压测脚本（MiniMall 交易链路）
============================
对标字节测开 JD 点名的 Locust / JMeter，以及面经常问：
  「性能测试关注哪些参数？」「怎么分析瓶颈？」「容量规划怎么做？」

覆盖交易主链路：注册 -> 登录 -> 浏览/搜索 -> 加购 -> 下单 -> 支付 -> 查订单。
每个虚拟用户注册独立账号（互不污染购物车），更接近真实多用户并发。

通过 run_perf_check.py 以「无头模式」运行并解析统计，做 CI 性能门禁
（p95 时延、错误率不达标则构建失败，等价于行业实践中的 k6 thresholds）。
"""
import uuid
from locust import HttpUser, task, between


class MiniMallUser(HttpUser):
    """模拟一个真实用户完成一次交易闭环"""
    wait_time = between(0.2, 1.0)

    def on_start(self):
        # 每个虚拟用户注册独立账号，避免共享购物车导致的并发干扰
        uname = "perf_" + uuid.uuid4().hex[:12]
        pw = "Pwd_" + uuid.uuid4().hex[:8] + "1!"
        self.client.post("/api/register", json={"username": uname, "password": pw}, name="register")
        r = self.client.post("/api/login", json={"username": uname, "password": pw}, name="login")
        self.token = r.json().get("data", {}).get("token", "") if r.status_code == 200 else ""
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(6)
    def view_products(self):
        self.client.get("/api/products", name="view_products")

    @task(3)
    def search_products(self):
        self.client.get("/api/products?q=键盘&sort=price_asc", name="search_products")

    @task(4)
    def add_cart(self):
        pid = uuid.choice([1, 2, 3, 4])
        self.client.post("/api/cart/add", json={"product_id": pid, "quantity": 1},
                         headers=self.headers, name="add_cart")

    @task(3)
    def create_and_pay_order(self):
        # 先加购保证购物车非空，再下单、支付、清购物车
        self.client.post("/api/cart/add", json={"product_id": 1, "quantity": 1},
                         headers=self.headers, name="pre_add")
        c = self.client.post("/api/order/create", json={}, headers=self.headers, name="create_order")
        if c.status_code == 200:
            oid = c.json().get("data", {}).get("order_id")
            if oid:
                self.client.post("/api/order/pay", json={"order_id": oid},
                                 headers=self.headers, name="pay_order")
        self.client.get("/api/orders", headers=self.headers, name="list_orders")
        self.client.delete("/api/cart/clear", headers=self.headers, name="clear_cart")
