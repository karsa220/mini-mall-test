"""
MiniMall 抓包自动化驱动 —— 把 mitmproxy 脚本化抓包接进项目。

流程（单命令自包含）：
  1. 释放 5000(残留 server) / 8080(残留 mitm) 端口
  2. 启动 MiniMall server (127.0.0.1:5000)
  3. 启动 mitmdump 代理 (127.0.0.1:8080)，加载 mitmproxy_addon.py
  4. 用 requests 走代理跑 登录 -> 加购 -> 下单 -> 支付
  5. addon 自动拦截断言 + 导出 HAR / 断言 JSON
  6. 读取断言结果，打印汇总，退出码反映是否全通过

这是"抓包自动化"的落地：相比 Charles 手工 GUI，脚本可重复、可进 CI、可写断言。
运行：
  python automation/run_mitm_capture.py
输出：
  automation/capture.har          标准 HAR（可用 Charles/Fiddler 打开回看）
  automation/mitm_assertions.json 断言汇总
"""
import os
import sys
import time
import json
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.environ.get("PY", r"C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\python.exe")
MITMDUMP = os.environ.get("MITMDUMP", r"C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\mitmdump.exe")
SERVER_PORT = 5000
MITM_PORT = 8080
BASE = "http://127.0.0.1:%d" % SERVER_PORT
PROXY = "http://127.0.0.1:%d" % MITM_PORT
ADDON = os.path.join(ROOT, "automation", "mitmproxy_addon.py")
ASSERT_JSON = os.path.join(ROOT, "automation", "mitm_assertions.json")
HAR = os.path.join(ROOT, "automation", "capture.har")


def free_port(port):
    import subprocess as _sp
    try:
        res = _sp.run(["netstat", "-ano"], capture_output=True)
        text = res.stdout.decode("gbk", "replace") if res.stdout else ""
        for line in text.splitlines():
            if (":%d " % port) in line and "LISTENING" in line:
                pid = line.split()[-1]
                try:
                    _sp.run(["taskkill", "/F", "/PID", pid], capture_output=True)
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

    # 起 server（独立临时库，避免历史运行耗尽库存影响抓包断言）
    srv_env = os.environ.copy()
    srv_env["MINIMALL_DB"] = os.path.join(tempfile.gettempdir(), f"mm_cap_{os.getpid()}.db")
    server = subprocess.Popen([PY, "app/server.py"], cwd=ROOT, env=srv_env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_server():
        print("ERROR: MiniMall server 未就绪")
        server.terminate()
        return 2

    # 起 mitmdump（脚本化抓包）
    env = os.environ.copy()
    env["PROJECT_ROOT"] = ROOT
    # 清掉系统代理变量，避免 mitmdump 把上游请求甩给公司代理
    for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        env.pop(_k, None)
    mitm = subprocess.Popen([MITMDUMP, "-p", str(MITM_PORT), "-s", ADDON],
                            cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=open(os.path.join(ROOT, "automation", "mitm_run.log"), "w", encoding="utf-8"))
    if not wait_proxy():
        print("ERROR: mitmproxy 代理未就绪")
        mitm.terminate()
        server.terminate()
        return 2

    import requests
    proxies = {"http": PROXY}
    # ---- 业务流（走代理，被 addon 拦截断言）----
    r = requests.post(BASE + "/api/login",
                      json={"username": "alice", "password": "password123"},
                      proxies=proxies, timeout=10)
    print("登录:", r.status_code, "code=", r.json().get("code"))
    tok = r.json()["data"]["token"]
    h = {"Authorization": "Bearer %s" % tok}
    requests.post(BASE + "/api/cart/add", json={"product_id": 1, "quantity": 1}, headers=h, proxies=proxies)
    requests.post(BASE + "/api/cart/add", json={"product_id": 2, "quantity": 1}, headers=h, proxies=proxies)
    r = requests.post(BASE + "/api/order/create", json={}, headers=h, proxies=proxies)
    oid = r.json()["data"]["order_id"]
    print("下单:", "order_id=", oid)
    r = requests.post(BASE + "/api/order/pay", json={"order_id": oid}, headers=h, proxies=proxies)
    print("支付:", r.json().get("data", {}))

    time.sleep(1)  # 让 addon 把最后一个响应写进文件

    # 停止代理（addon 已实时写出 HAR / 断言，强杀不丢数据）
    mitm.terminate()
    try:
        mitm.wait(timeout=5)
    except Exception:
        mitm.kill()

    # ---- 读断言结果 ----
    rc = 0
    try:
        with open(ASSERT_JSON, encoding="utf-8") as f:
            res = json.load(f)
        print("\n===== mitmproxy 抓包断言汇总 =====")
        print("捕获响应数:", res.get("captured_responses"))
        for a in res.get("assertions", []):
            mark = "PASS" if a["passed"] else "FAIL"
            print("  [%s] %s/%s  %s" % (mark, a["api"], a["name"], a.get("detail")))
        print("HAR:", HAR)
        print("断言文件:", ASSERT_JSON)
        if not res.get("all_passed"):
            rc = 1
    except Exception as e:
        print("ERROR: 读取断言失败", e)
        rc = 2

    server.terminate()
    return rc


if __name__ == "__main__":
    sys.exit(main())
