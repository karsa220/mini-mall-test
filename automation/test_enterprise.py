"""
企业级质量门禁统一入口（pytest 用例）
============================
把「性能门禁 / 混沌测试 / 契约 diff」三个企业级能力编排为一个 pytest 套件，
每个能力作为独立用例（自包含起 server + 工具），退出码即该能力是否达标。
CI 中一条 `pytest automation/test_enterprise.py` 即可跑全部门禁。

另见：automation/test_unit.py（单元层）、automation/test_mitm_capture.py（抓包层）
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.environ.get("PY", r"C:\Users\bfdym\.workbuddy\binaries\python\envs\mini-mall-test\Scripts\python.exe")


def _run(script, env_extra=None):
    env = dict(os.environ)
    env["PY"] = PY
    if env_extra:
        env.update(env_extra)
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        env.pop(k, None)
    return subprocess.run([PY, os.path.join(ROOT, "automation", script)],
                          cwd=ROOT, env=env).returncode


def test_perf_gate():
    """性能门禁：p95 时延、错误率达标"""
    rc = _run("run_perf_check.py")
    assert rc == 0, f"性能门禁未通过 (rc={rc})"


def test_chaos_resilience():
    """混沌测试：故障被系统感知/处理"""
    rc = _run("run_chaos_check.py")
    assert rc == 0, f"混沌测试未通过 (rc={rc})"


def test_contract_diff():
    """契约 diff：接口字段无破坏性变更"""
    # 复用 mitmproxy 抓包生成 HAR，再跑 diff 对比 baseline
    rc = _run("run_mitm_capture.py")
    assert rc == 0, f"抓包断言未通过 (rc={rc})"
    rc2 = _run("har_contract_diff.py")
    assert rc2 == 0, f"契约 diff 发现破坏性变更 (rc={rc2})"


if __name__ == "__main__":
    sys.exit(pytest_main := 0)
