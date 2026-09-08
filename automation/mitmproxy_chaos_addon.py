"""
mitmproxy 混沌注入 addon（网络级故障）
==============================
在代理层注入故障，模拟「弱网/网关超时/依赖不可用」等网络侧异常，
与 server.py 的 /api/chaos（应用级故障）互补，覆盖完整混沌测试维度。

环境变量（run_chaos_check.py 注入）：
  CHAOS_DELAY_MS   请求延迟毫秒（模拟弱网/高 RT）
  CHAOS_HTTP_ERROR 对目标路径返回的伪造状态码（如 504 网关超时），0=不注入
  CHAOS_TARGET     命中路径关键字（默认 /api/order/pay）
"""
import os
import time

from mitmproxy import http

DELAY = float(os.environ.get("CHAOS_DELAY_MS", "0")) / 1000.0
ERROR = int(os.environ.get("CHAOS_HTTP_ERROR", "0") or 0)
TARGET = os.environ.get("CHAOS_TARGET", "/api/order/pay")


class ChaosProxy:
    def request(self, flow):
        if TARGET and TARGET in flow.request.path and DELAY > 0:
            time.sleep(DELAY)

    def response(self, flow):
        if ERROR and TARGET and TARGET in flow.request.path:
            flow.response.status_code = ERROR
            flow.response.reason = "Chaos Injected"
            flow.response.content = (
                b'{"code":%d,"msg":"chaos injected network error"}' % ERROR
            )
            flow.response.headers["content-type"] = "application/json"


addons = [ChaosProxy()]
