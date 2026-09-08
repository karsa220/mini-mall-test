"""
性能门禁运行器（CI 用）
==================
自包含：起 server -> 无头跑 Locust -> 解析统计 -> 阈值门禁 -> 退出码。
阈值（可环境变量覆盖，便于按环境分级）：
  PERF_P95_MS   默认 800   （p95 时延上限，毫秒）
  PERF_ERR_RATE 默认 0.01  （错误率上限）
  PERF_USERS    默认 20     （并发用户数）
  PERF_RUNTIME  默认 20s    （压测时长）

退出码：0=达标，非0=性能回归（与 Jenkins quality gate 联动）
"""
import csv
import os
import subprocess
import sys
import time
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.environ.get("PY", r"C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\python.exe")
LOCUST = os.environ.get("LOCUST", r"C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\locust.exe")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "5000"))
# 清掉系统代理，避免 Locust/requests 把流量甩给公司代理
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
    # 独立临时库：每次压测从播种状态开始，避免历史运行耗尽库存
    env["MINIMALL_DB"] = os.path.join(tempfile.gettempdir(), f"mm_perf_{os.getpid()}.db")
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


def parse_stats(csv_path):
    """读取 Locust 聚合统计，返回 (p95_ms, err_rate, total_req)"""
    agg = None
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Name") == "Aggregated":
                agg = row
                break
    if not agg:
        raise RuntimeError("未找到 Aggregated 统计行")
    p95 = float(agg.get("95%", "0") or 0)
    reqs = int(agg.get("Request Count", agg.get("Requests", "0")) or 0)
    fails = int(agg.get("Failure Count", agg.get("Fails", "0")) or 0)
    err_rate = (fails / reqs) if reqs else 1.0
    return p95, err_rate, reqs


def main():
    p95_th = float(os.environ.get("PERF_P95_MS", "800"))
    err_th = float(os.environ.get("PERF_ERR_RATE", "0.01"))
    users = int(os.environ.get("PERF_USERS", "20"))
    runtime = os.environ.get("PERF_RUNTIME", "20s")

    if not free_port(SERVER_PORT):
        print(f"[perf] 端口 {SERVER_PORT} 被占用，先尝试释放")
    srv = start_server()
    csv_prefix = os.path.join(ROOT, "automation", "perf_stats")
    try:
        cmd = [LOCUST, "-f", os.path.join(ROOT, "automation", "perf_test.py"),
               "--headless", "-u", str(users), "-r", str(min(users, 10)),
               "-t", runtime, f"--csv={csv_prefix}", "-H", f"http://127.0.0.1:{SERVER_PORT}"]
        print("[perf] 运行 Locust:", " ".join(cmd))
        rc = subprocess.run(cmd, cwd=ROOT, env=os.environ).returncode
        # Locust 无头模式默认以非零退出表示有色情失败，但我们自己按阈值判定
        stats_csv = csv_prefix + "_stats.csv"
        if not os.path.exists(stats_csv):
            print("[perf] 未生成统计文件，Locust 可能启动失败")
            return 2
        p95, err_rate, total = parse_stats(stats_csv)
        report = {
            "p95_ms": round(p95, 2),
            "err_rate": round(err_rate, 4),
            "total_requests": total,
            "threshold_p95_ms": p95_th,
            "threshold_err_rate": err_th,
            "pass": (p95 <= p95_th and err_rate <= err_th),
        }
        out = os.path.join(ROOT, "automation", "perf_report.json")
        with open(out, "w", encoding="utf-8") as f:
            import json
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("[perf] 报告:", report)
        if report["pass"]:
            print(f"[perf] 门禁通过 ✅ p95={p95}ms<= {p95_th}ms, err={err_rate}<= {err_th}")
            return 0
        print(f"[perf] 门禁失败 ❌ p95={p95}ms(阈值{p95_th}) err={err_rate}(阈值{err_th})")
        return 1
    finally:
        srv.terminate()


if __name__ == "__main__":
    sys.exit(main())
