"""
MiniMall 抓包自动化 —— pytest 集成测试

把上一轮已跑通的 mitmproxy 抓包，以及本轮新增的 WebSocket 抓包 / Mock改包 / HAR契约diff，
全部用 pytest 串起来，退出码即断言结果，可直接接 Jenkins CI。

每个子脚本都是自包含（自己起 server + 代理 + 业务流 + 断言），
本文件用 subprocess 调用它们，并复核产物 JSON，确保"抓包=可重复测试资产"。

运行：
  python -m pytest test_mitm_capture.py -v
"""
import os
import sys
import json
import subprocess
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# CI 可用 PY 环境变量覆盖解释器（默认用当前 pytest 运行的解释器）
PY = os.environ.get("PY", sys.executable)


def _run_script(name):
    """调用 automation/ 下的自包含抓包脚本，返回 CompletedProcess"""
    script = os.path.join(ROOT, "automation", name)
    p = subprocess.run([PY, script], cwd=ROOT,
                       capture_output=True, text=True, timeout=150)
    print("---- %s (rc=%d) ----\n%s" % (name, p.returncode, p.stdout))
    if p.stderr:
        print("STDERR:", p.stderr[-800:])
    return p


def test_mitm_capture_basic():
    """基础抓包断言：登录/下单/支付 字段断言全 PASS"""
    p = _run_script("run_mitm_capture.py")
    assert p.returncode == 0, "run_mitm_capture.py 退出码非 0"
    with open(os.path.join(ROOT, "automation", "mitm_assertions.json"), encoding="utf-8") as f:
        res = json.load(f)
    assert res["all_passed"], "mitmproxy 字段断言未全部通过"
    assert len(res["assertions"]) >= 5


def test_ws_capture():
    """WebSocket 抓包：能抓到 order_created / order_paid 推送并断言通过"""
    p = _run_script("run_ws_capture.py")
    assert p.returncode == 0, "run_ws_capture.py 退出码非 0"
    with open(os.path.join(ROOT, "automation", "ws_messages.json"), encoding="utf-8") as f:
        res = json.load(f)
    assert res["all_passed"], "WS 推送断言未全部通过"
    s2c = [m for m in res["messages"] if m["direction"] == "server->client"]
    assert len(s2c) >= 2, "服务端推送不足 2 条"


def test_mock_capture():
    """Mock/改包：支付接口被代理 mock 成 504 支付网关超时"""
    p = _run_script("run_mock_capture.py")
    assert p.returncode == 0, "run_mock_capture.py 退出码非 0"
    with open(os.path.join(ROOT, "automation", "mitm_mock_events.json"), encoding="utf-8") as f:
        res = json.load(f)
    assert any(e["stage"] == "response_mock" for e in res["events"]), "未记录到 mock 事件"


def test_har_contract_diff():
    """HAR 契约 diff：接口字段无 breaking change（首次自动生成基线）"""
    p = _run_script("har_contract_diff.py")
    assert p.returncode == 0, "契约出现 breaking change（字段删除/类型变化）"
