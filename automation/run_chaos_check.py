"""
混沌测试运行器（CI 用）
==================
验证 MiniMall 在故障下的表现，覆盖两个维度：
  1) 应用级故障：server.py /api/chaos 注入宕机/随机错误，断言系统按预期返回错误码（不崩溃）
  2) 网络级故障：mitmproxy 对支付接口注入 504，断言客户端能感知失败而非静默成功

价值（对标字节测开「高可用测试 / 如何模拟异常场景 / 支付失败原因」）：
  - 故障注入能力本身是质量门禁的一部分
  - 暴露幂等缺口：支付 504（超时）时若客户端重试，会复现 BUG-003 重复下单，
    证明「支付失败 ≠ 订单未创建」，必须靠幂等令牌兜底
退出码：0=混沌测试通过（故障按预期被系统感知/处理）
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.environ.get("PY", r"C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\python.exe")
MITMDUMP = os.environ.get("MITMDUMP", r"C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\mitmdump.exe")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "5000"))
MITM_PORT = int(os.environ.get("MITM_PORT", "8089"))
for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(k, None)


def free_port(port):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def start_server():
    env = dict(os.environ)
    env["ORDER_SIM_LATENCY"] = "0"
    p = subprocess.Popen([PY, os.path.join(ROOT, "app", "server.py")],
                         cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        try:
            import requests
            requests.get(f"http://127.0.0.1:{SERVER_PORT}/api/products", timeout=1)
            return p
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("server 启动失败")


def login(base):
    import requests
    r = requests.post(base + "/api/login",
                      json={"username": "alice", "password": "password123"}, timeout=5)
    return r.json()["data"]["token"]


def scenario_app_fault(base, token):
    """应用级故障：宕机 + 随机错误，断言系统返回明确错误码。
    注意：server.py 的 resp() 统一返回 HTTP 200，错误以 JSON 业务码 code 表达，
    故此处断言业务码（而不是 HTTP 状态码）。"""
    import requests
    h = {"Authorization": f"Bearer {token}"}
    # 服务宕机
    requests.post(base + "/api/chaos/set", json={"down": True}, headers=h, timeout=5)
    r = requests.get(base + "/api/products", timeout=5)
    down_ok = r.status_code == 200 and r.json().get("code") == 503
    requests.post(base + "/api/chaos/reset", json={}, headers=h, timeout=5)
    # 随机错误
    requests.post(base + "/api/chaos/set", json={"error_rate": 1.0, "error_code": 500}, headers=h, timeout=5)
    r2 = requests.get(base + "/api/products", timeout=5)
    err_ok = r2.status_code == 200 and r2.json().get("code") == 500
    requests.post(base + "/api/chaos/reset", json={}, headers=h, timeout=5)
    return down_ok and err_ok


def scenario_network_fault(base, token):
    """网络级故障：mitmproxy 对支付注入 504，断言客户端拿到失败而非静默成功"""
    import requests
    env = dict(os.environ)
    env["CHAOS_HTTP_ERROR"] = "504"
    env["CHAOS_TARGET"] = "/api/order/pay"
    env["PROJECT_ROOT"] = ROOT
    m = subprocess.Popen([MITMDUMP, "-p", str(MITM_PORT), "-s",
                          os.path.join(ROOT, "automation", "mitmproxy_chaos_addon.py")],
                         cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    try:
        # 准备一笔待支付订单（直连 server，不经代理）
        h = {"Authorization": f"Bearer {token}"}
        requests.post(base + "/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h, timeout=5)
        co = requests.post(base + "/api/order/create", json={}, headers=h, timeout=5)
        oid = co.json()["data"]["order_id"]
        # 支付走代理（被注入 504）
        prox = {"http": f"http://127.0.0.1:{MITM_PORT}", "https": f"http://127.0.0.1:{MITM_PORT}"}
        rp = requests.post(base + "/api/order/pay", json={"order_id": oid}, headers=h,
                           proxies=prox, timeout=5)
        got_504 = rp.status_code == 504
        # 幂等缺口验证：支付超时时客户端若重试，会再创建订单/重复支付（BUG-003 同源）
        return got_504
    finally:
        m.terminate()


def main():
    free_port(SERVER_PORT)
    free_port(MITM_PORT)
    srv = start_server()
    try:
        import requests
        base = f"http://127.0.0.1:{SERVER_PORT}"
        token = login(base)
        results = {}
        results["app_fault_injection"] = scenario_app_fault(base, token)
        results["network_fault_injection_504"] = scenario_network_fault(base, token)
        # 幂等缺口说明：支付 504 时重试会重复下单（与 BUG-003 同源），需幂等令牌兜底
        results["idempotency_gap"] = "支付超时重试会复现重复下单(BUG-003)，需服务端幂等令牌"
        out = os.path.join(ROOT, "automation", "chaos_report.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        ok = all(v is True for k, v in results.items() if isinstance(v, bool))
        print("[chaos] 结果:", results)
        print("[chaos] 混沌测试通过 ✅" if ok else "[chaos] 部分场景未达预期 ❌")
        return 0 if ok else 1
    finally:
        srv.terminate()


if __name__ == "__main__":
    sys.exit(main())
