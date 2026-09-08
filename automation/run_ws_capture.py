"""
MiniMall WebSocket 抓包驱动 —— 把 WS 流量经 mitmproxy 代理抓下来并断言。

流程（单命令自包含）：
  1. 释放 5000 / 8080 端口
  2. 启动 MiniMall server（已带 /ws/notify 端点）
  3. 启动 mitmdump 加载 mitmproxy_ws_addon.py（拦截 WS 流量）
  4. 起一个 WS 客户端走代理订阅 /ws/notify
  5. 用 requests 走代理跑 登录 -> 加购 -> 下单 -> 支付（触发 server 广播 WS 推送）
  6. WS 客户端收到 order_created / order_paid 推送，addon 写入 ws_messages.json
  7. 读取断言，退出码反映是否抓到并断言通过

运行：
  python automation/run_ws_capture.py
输出：
  automation/ws_messages.json   WS 消息记录 + 断言汇总
"""
import os
import sys
import time
import json
import threading
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.environ.get("PY", r"C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\python.exe")
MITMDUMP = os.environ.get("MITMDUMP", r"C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\mitmdump.exe")
SERVER_PORT = 5000
MITM_PORT = 8080
BASE = "http://127.0.0.1:%d" % SERVER_PORT
PROXY = "http://127.0.0.1:%d" % MITM_PORT
WS_PORT = 5001
WS_URL = "ws://127.0.0.1:%d/ws/notify" % WS_PORT
WS_ADDON = os.path.join(ROOT, "automation", "mitmproxy_ws_addon.py")
WS_JSON = os.path.join(ROOT, "automation", "ws_messages.json")


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


def ws_listener(received, stop):
    """后台线程：走代理订阅 WS，把收到的消息累积到 received"""
    import websocket
    try:
        ws = websocket.create_connection(
            WS_URL,
            http_proxy_host="127.0.0.1",
            http_proxy_port=MITM_PORT,
        )
        ws.send(json.dumps({"type": "subscribe"}))
        while not stop.is_set():
            try:
                ws.settimeout(1)
                msg = ws.recv()
                received.append(msg)
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                break
        ws.close()
    except Exception as e:
        print("WS 客户端异常:", e)


def main():
    free_port(SERVER_PORT)
    free_port(MITM_PORT)
    free_port(WS_PORT)

    server = subprocess.Popen([PY, "app/server.py"], cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_server():
        print("ERROR: MiniMall server 未就绪")
        server.terminate()
        return 2

    env = os.environ.copy()
    env["PROJECT_ROOT"] = ROOT
    # 清掉系统代理变量，避免 mitmdump 把 WS 的 CONNECT 目标甩给上游代理导致 502
    for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        env.pop(_k, None)
    mitm = subprocess.Popen([MITMDUMP, "-p", str(MITM_PORT), "-s", WS_ADDON],
                            cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=open(os.path.join(ROOT, "automation", "ws_run.log"), "w", encoding="utf-8"))
    if not wait_proxy():
        print("ERROR: mitmproxy 代理未就绪")
        mitm.terminate()
        server.terminate()
        return 2

    received = []
    stop = threading.Event()
    t = threading.Thread(target=ws_listener, args=(received, stop), daemon=True)
    t.start()
    time.sleep(1)  # 等 WS 握手完成

    import requests
    proxies = {"http": PROXY}
    r = requests.post(BASE + "/api/login",
                      json={"username": "alice", "password": "password123"},
                      proxies=proxies, timeout=10)
    tok = r.json()["data"]["token"]
    h = {"Authorization": "Bearer %s" % tok}
    requests.post(BASE + "/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h, proxies=proxies)
    requests.post(BASE + "/api/cart/add", json={"product_id": 2, "quantity": 1}, headers=h, proxies=proxies)
    r = requests.post(BASE + "/api/order/create", json={}, headers=h, proxies=proxies)
    oid = r.json()["data"]["order_id"]
    print("下单:", "order_id=", oid)
    requests.post(BASE + "/api/order/pay", json={"order_id": oid}, headers=h, proxies=proxies)

    time.sleep(2)  # 等 WS 推送经代理到达客户端 + addon 写盘
    stop.set()
    t.join(timeout=3)

    mitm.terminate()
    try:
        mitm.wait(timeout=5)
    except Exception:
        mitm.kill()

    rc = 0
    try:
        with open(WS_JSON, encoding="utf-8") as f:
            res = json.load(f)
        print("\n===== WebSocket 抓包断言汇总 =====")
        print("捕获 WS 消息数:", len(res.get("messages", [])))
        for m in res.get("messages", []):
            print("  [%s] %s" % (m["direction"], m["content"]))
        print("断言:")
        for a in res.get("assertions", []):
            mark = "PASS" if a["passed"] else "FAIL"
            print("  [%s] %s has_order_id=%s" % (mark, a["type"], a["has_order_id"]))
        if not res.get("all_passed"):
            rc = 1
        # 至少应抓到 2 条服务端推送（order_created + order_paid）
        s2c = [m for m in res.get("messages", []) if m["direction"] == "server->client"]
        if len(s2c) < 2:
            print("⚠️  服务端推送不足 2 条，WS 抓包可能不完整")
            rc = 1
    except Exception as e:
        print("ERROR: 读取 WS 断言失败", e)
        rc = 2

    server.terminate()
    return rc


if __name__ == "__main__":
    sys.exit(main())
