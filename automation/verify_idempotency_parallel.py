"""
BUG-003 幂等缺陷 —— 并行后端复现实测
====================================
说明：
  Flask 开发服务器(app.run 默认 threaded=False 的旧版本 / 或单进程串行)在 GIL 下把
  「读购物车 → 建单 → 清购物车」基本串行化，第一个请求清完购物车后其余请求读到空 cart
  被拦，所以只生成 1 笔 —— 这是单进程串行后端的假象。
  真实后端是并行处理请求的(多线/多进程 worker)，且「读购物车→建单→清购物车」之间隔着
  DB/下游延迟，竞态窗口会打开。本脚本用 threaded=True 的并行服务器 + 受控延迟模拟该窗口，
  复现重复下单。等价于 Charles Throttle 弱网下客户端重试并发触发的场景。

用法：
  ORDER_SIM_LATENCY=0.3 python automation/verify_idempotency_parallel.py
"""
import os
import sys
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ["ORDER_SIM_LATENCY"] = os.getenv("ORDER_SIM_LATENCY", "0.3")

from app.server import app  # 必须在设置 env 之后导入（处理时读取 env）

BASE = "http://127.0.0.1:5099"
THREAD = threading.Thread(
    target=lambda: app.run(host="127.0.0.1", port=5099, threaded=True, use_reloader=False),
    daemon=True,
)
THREAD.start()
for _ in range(30):
    try:
        requests.get(BASE + "/", timeout=1)
        break
    except Exception:
        time.sleep(0.3)


def login():
    r = requests.post(BASE + "/api/login", json={"username": "alice", "password": "password123"}, timeout=5)
    return r.json()["data"]["token"]


def add_to_cart(token):
    h = {"Authorization": f"Bearer {token}"}
    requests.post(BASE + "/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h, timeout=5)
    requests.post(BASE + "/api/cart/add", json={"product_id": 2, "quantity": 1}, headers=h, timeout=5)


def place_once(_):
    h = {"Authorization": f"Bearer {TOKEN}"}
    return requests.post(BASE + "/api/order/create", json={}, headers=h, timeout=10).json()


TOKEN = login()
add_to_cart(TOKEN)

N = int(os.getenv("CONCURRENCY", "8"))
print(f"=== 并行后端(threaded=True) + 延迟 {os.environ['ORDER_SIM_LATENCY']}s，并发 {N} 次重放下单 ===")
t0 = time.time()
with ThreadPoolExecutor(max_workers=N) as ex:
    results = list(ex.map(place_once, range(N)))
print(f"耗时 {time.time()-t0:.2f}s\n")

for i, res in enumerate(results, 1):
    d = res.get("data") or {}
    oid = d.get("order_id") if isinstance(d, dict) else None
    print(f"  并发{i}: code={res.get('code')} order_id={oid} msg={res.get('msg')}")

oids = [r.get("data", {}).get("order_id") for r in results
        if isinstance(r.get("data"), dict) and r.get("data", {}).get("order_id")]
print(f"\n下单成功返回的 order_id：去重 {len(set(oids))} 个 / 共 {len(oids)} 次成功响应")
print("结论：去重数 > 1 即证明 BUG-003 在并行后端下可复现重复下单")
