"""
测试公共助手（进程内 / 用例隔离）
================================
供新增的组件/集成/安全/并发测试复用：
  - 进程内 test_client 驱动 Flask 应用，pytest-cov 可计入行覆盖
  - 每用例 reset_db() 重建并重新播种，保证数据零污染（与数据工厂命名空间双保险）
  - 登录助手返回 token
不依赖既有 conftest 的 HTTP/session 风格，互不干扰。
"""
import os
import sys
import tempfile

_appdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app")
if _appdir not in sys.path:
    sys.path.insert(0, _appdir)


def _ensure_env():
    if "MINIMALL_DB" not in os.environ:
        os.environ["MINIMALL_DB"] = tempfile.mktemp(suffix=".db", prefix="mm_test_")


_ensure_env()

import server as s  # noqa: E402
from db import reset_db  # noqa: E402


def reset_server():
    reset_db()
    s.REVOKED.clear()
    s._LOGIN_FAIL.clear()
    s.CHAOS.update({"latency": 0.0, "error_rate": 0.0, "down": False, "error_code": 500})


def make_client():
    reset_server()
    return s.app.test_client()


def login(c, username, password):
    r = c.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200 and r.json["code"] == 0, r.json
    return r.json["data"]["token"]
