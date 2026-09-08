"""验证 BUG-003：下单无幂等。
模拟 Charles Repeat Advanced 5 并发重放：对同一购物车同时发 5 次 /api/order/create，
看是否生成多笔订单（服务端无幂等令牌/去重，应复现多笔订单）。
"""
import requests
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:5000"

s = requests.Session()
r = s.post(f"{BASE}/api/login", json={"username": "alice", "password": "password123"})
tok = r.json()["data"]["token"]
h = {"Authorization": f"Bearer {tok}"}

# 清空并加购 1 件，制造一个非空购物车
s.delete(f"{BASE}/api/cart", headers=h)
s.post(f"{BASE}/api/cart/add", headers=h, json={"product_id": 1, "quantity": 1})

results = []
def place_once(_):
    rr = s.post(f"{BASE}/api/order/create", headers=h, json={})
    results.append(rr.json())

# —— 并发重放（提高并发数，碰清空购物车的竞态窗口）——
N = 15
with ThreadPoolExecutor(max_workers=N) as ex:
    list(ex.map(place_once, range(N)))

print(f"=== {N} 次并发下单响应 ===")
for i, res in enumerate(results, 1):
    d = res.get("data") or {}
    oid = d.get("order_id") if isinstance(d, dict) else None
    print(f"  并发{i}: code={res.get('code')} order_id={oid} msg={res.get('msg')}")

oids = [r.get("data", {}).get("order_id") for r in results
        if isinstance(r.get("data"), dict) and r.get("data", {}).get("order_id")]
uniq = set(oids)
print(f"\n下单成功返回的 order_id：去重 {len(uniq)} 个 / 共 {len(oids)} 次成功响应")

# 服务端订单总数
ol = s.get(f"{BASE}/api/orders", headers=h).json()
print(f"服务端 ORDERS 总订单数：{len(ol.get('data') or [])}")

if len(uniq) > 1:
    print("\n[结论] BUG-003 实锤：无幂等控制，同一请求并发重放生成了多笔订单。")
else:
    print("\n[结论] 未复现多笔（可能竞态下部分请求读到空购物车），需调整加购/并发时机。")
