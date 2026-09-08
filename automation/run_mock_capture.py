"""
MiniMall Mock/改包 抓包驱动 —— 用 mitmproxy 伪造支付网关超时，验证客户端容错。

流程（单命令自包含）：
  1. 释放 5000 / 8080 端口
  2. 启动 MiniMall server
  3. 启动 mitmdump 加载 mitmproxy_mock_addon.py，并设环境变量 MOCK_PAY_TIMEOUT=1
     （对 /api/order/pay 的响应改成 504 支付网关超时，等价 Charles Map Local 伪造响应）
  4. 用 requests 走代理跑 登录 -> 加购 -> 下单 -> 支付
  5. 支付请求应被代理拦截并返回 504（mock 生效），addon 写入 mitm_mock_events.json
  6. 读取事件，退出码反映 mock 是否生效

运行：
  python automation/run_mock_capture.py
输出：
  automation/mitm_mock_events.json   改包/mock 事件记录
"""
import os
import sys
import time
import json
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.environ.get("PY", r"C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\python.exe")
MITMDUMP = os.environ.get("MITMDUMP", r"C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\mitmdump.exe")
SERVER_PORT = 5000
MITM_PORT = 8080
BASE = "http://127.0.0.1:%d" % SERVER_PORT
PROXY = "http://127.0.0.1:%d" % MITM_PORT
MOCK_ADDON = os.path.join(ROOT, "automation", "mitmproxy_mock_addon.py")
MOCK_JSON = os.path.join(ROOT, "automation", "mitm_mock_events.json")


def free_port(port):
    try:
        res = subprocess.run(["netstat", "-ano"], capture_output=True)
        text = res.stdout.decode("gbk", "replace") if res.stdout else ""
        for line in text.splitlines():
            if (":%d " % port) in line and "LISTENING" in line:
                pid = line.split()[-1]
                try:
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                    print("释放端口 %d 的残留进程 %s" % (port, pid))
                    time.sleep(1)
                except Exception:
                    pass
    except Exception:
        pass


def wait_server(timeout=30):
    import requests
    for _ in range(timeout):
        try:
            if requests.get(BASE + "/", timeout=2).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def wait_proxy(timeout=30):
    import requests
    for _ in range(timeout):
        try:
            if requests.get(BASE + "/", proxies={"http": PROXY}, timeout=3).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main():
    free_port(SERVER_PORT)
    free_port(MITM_PORT)
    free_port(5001)  # 独立 WS server 端口，避免残留

    server = subprocess.Popen([PY, "app/server.py"], cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_server():
        print("ERROR: MiniMall server 未就绪")
        server.terminate()
        return 2

    env = os.environ.copy()
    env["PROJECT_ROOT"] = ROOT
    # 清掉系统代理变量，避免 mitmdump 把上游请求甩给公司代理
    for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        env.pop(_k, None)
    env["MOCK_PAY_TIMEOUT"] = "1"   # 让 mock addon 对 /api/order/pay 伪造 504
    mitm = subprocess.Popen([MITMDUMP, "-p", str(MITM_PORT), "-s", MOCK_ADDON],
                            cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=open(os.path.join(ROOT, "automation", "mock_run.log"), "w", encoding="utf-8"))
    if not wait_proxy():
        print("ERROR: mitmproxy 代理未就绪")
        mitm.terminate()
        server.terminate()
        return 2

    import requests
    proxies = {"http": PROXY}
    r = requests.post(BASE + "/api/login",
                      json={"username": "alice", "password": "password123"},
                      proxies=proxies, timeout=10)
    tok = r.json()["data"]["token"]
    h = {"Authorization": "Bearer %s" % tok}
    requests.post(BASE + "/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h, proxies=proxies)
    requests.post(BASE + "/api/cart/add", json={"product_id": 2, "quantity": 1}, headers=h, proxies=proxies)
    requests.post(BASE + "/api/order/create", json={}, headers=h, proxies=proxies)
    # 支付：应被代理 mock 成 504 支付网关超时
    r = requests.post(BASE + "/api/order/pay", json={"order_id": "OD_MOCK_TEST"}, headers=h, proxies=proxies)
    mock_ok = (r.status_code == 504) or (r.json().get("code") == 5040)
    print("支付响应(被mock):", r.status_code, r.text[:120])

    time.sleep(1)
    mitm.terminate()
    try:
        mitm.wait(timeout=5)
    except Exception:
        mitm.kill()

    rc = 0
    try:
        with open(MOCK_JSON, encoding="utf-8") as f:
            res = json.load(f)
        print("\n===== Mock/改包 事件汇总 =====")
        for e in res.get("events", []):
            print("  [%s] %s %s" % (e["stage"], e["api"], e.get("mocked_body") or e.get("modified") or ""))
        if not mock_ok:
            print("❌ 支付未被 mock 成 504")
            rc = 1
        if not any(e["stage"] == "response_mock" for e in res.get("events", [])):
            print("❌ 未记录到 response_mock 事件")
            rc = 1
    except Exception as e:
        print("ERROR: 读取 mock 事件失败", e)
        rc = 2

    server.terminate()
    return rc


if __name__ == "__main__":
    sys.exit(main())
