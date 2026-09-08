"""
MiniMall 抓包 —— 改包 / Mock 响应 addon（mitmproxy 12）

对应 Charles 的「Breakpoints 改包」「Map Local / Rewrite 伪造响应」，
但做成脚本化、可进 CI、可断言：

  - request  钩子：演示「改包」——把 /api/order/create 的优惠券改成无效码，
                     验证服务端是否真的校验券合法性（等价 Charles Breakpoints 拦截请求）
  - response 钩子：演示「Mock 异常返回」——把 /api/order/pay 改成 504 支付网关超时，
                     构造弱网/支付通道故障场景（等价 Charles Map Local 伪造响应）

注意：这才是测开抓包的核心价值——用代理伪造后端难以造出的脏数据 / 异常，
验证客户端与下游的容错。mitmproxy 12 必须用模块级 `addons = [...]` 注册。

关于「HTTPS Pinning 绕过」：本 addon 解决的是"可控后端下的改包/mock"。
真正生产 App 的证书锁定（SSL Pinning）绕过是移动端逆向专项，需要 Frida /
Objection hook 客户端的 checkServerTrusted / SSLContext（见下文文档与示例脚本），
不属于 mitmproxy 能力范围，但思路一致：都是"让代理证书被客户端信任"。
"""
import os
import json
from mitmproxy import http, ctx


class MiniMallMock:
    def __init__(self):
        root = os.environ.get("PROJECT_ROOT", "")
        out_dir = os.path.join(root, "automation") if root else "automation"
        self.events_path = os.path.join(out_dir, "mitm_mock_events.json")
        self.events = []
        # 环境变量开关：是否启用对应改包/mock 行为
        self.mock_pay_timeout = os.environ.get("MOCK_PAY_TIMEOUT", "0") == "1"
        self.tamper_create = os.environ.get("TAMPER_ORDER_CREATE", "0") == "1"

    @staticmethod
    def _is_mm(flow):
        return flow.request.port == 5000 or flow.request.path.startswith("/api/")

    # ---------- 请求改包（等价 Charles Breakpoints 改请求体） ----------
    def request(self, flow):
        if not self._is_mm(flow) or not self.tamper_create:
            return
        if not flow.request.path.startswith("/api/order/create"):
            return
        try:
            body = json.loads(flow.request.content or b"{}")
            original = dict(body)
            # 把客户端真实优惠券改成不存在的码，验证服务端是否拦截（脏数据注入）
            if body.get("coupon_code"):
                body["coupon_code"] = "TAMPERED_INVALID"
            flow.request.content = json.dumps(body, ensure_ascii=False).encode("utf-8")
            flow.request.headers["Content-Length"] = str(len(flow.request.content))
            self.events.append({"stage": "request_tamper", "api": "/api/order/create",
                                "original": original, "modified": body})
            ctx.log.info("[MiniMallMock] 改包 /api/order/create coupon -> TAMPERED_INVALID")
            self._dump()
        except Exception as e:
            ctx.log.warn("tamper error: %s" % e)

    # ---------- 响应 Mock（等价 Charles Map Local / Rewrite 伪造响应） ----------
    def response(self, flow):
        if not self._is_mm(flow):
            return
        path = flow.request.path
        if self.mock_pay_timeout and path.startswith("/api/order/pay"):
            mock_body = json.dumps({"code": 5040, "msg": "支付网关超时（mock）", "data": None},
                                   ensure_ascii=False)
            flow.response.status_code = 504
            flow.response.set_text(mock_body)
            self.events.append({"stage": "response_mock", "api": "/api/order/pay",
                                "mocked_status": 504, "mocked_body": json.loads(mock_body)})
            ctx.log.info("[MiniMallMock] mock /api/order/pay -> 504 支付网关超时")
            self._dump()

    def _dump(self):
        with open(self.events_path, "w", encoding="utf-8") as f:
            json.dump({"events": self.events,
                       "mock_pay_timeout": self.mock_pay_timeout,
                       "tamper_create": self.tamper_create},
                      f, ensure_ascii=False, indent=2)


addons = [MiniMallMock()]
