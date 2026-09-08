"""
MiniMall 抓包 —— WebSocket 流量捕获 addon（mitmproxy 12）

mitmproxy 支持 WebSocket（握手后的 upgrade 流量），提供三个钩子：
  websocket_start   握手完成
  websocket_message 每收发一条 WS 消息（flow.websocket.messages[-1]）
  websocket_end     连接关闭

本 addon 在代理 MiniMall 的 /ws/notify 流量时：
  1. 记录每条消息的方向（client->server / server->client）+ 内容
  2. 对服务端推送的订单事件（order_created / order_paid）做断言：必须含 order_id
  3. 实时落盘 automation/ws_messages.json（含断言汇总）

驱动见 automation/run_ws_capture.py。同样必须用模块级 `addons = [...]` 注册。
"""
import os
import json
from mitmproxy import ctx


class MiniMallWSCapture:
    def __init__(self):
        root = os.environ.get("PROJECT_ROOT", "")
        out_dir = os.path.join(root, "automation") if root else "automation"
        self.ws_path = os.path.join(out_dir, "ws_messages.json")
        self.messages = []
        self.assertions = []

    @staticmethod
    def _is_mm_ws(flow):
        # WS 握手请求走 /ws/notify（独立 WS server 在 5001 端口）
        return flow.request.port in (5000, 5001) or flow.request.path.startswith("/ws/")

    def websocket_start(self, flow):
        if not self._is_mm_ws(flow):
            return
        ctx.log.info("[WS] handshake %s" % flow.request.path)

    def websocket_message(self, flow):
        if not self._is_mm_ws(flow):
            return
        try:
            ws = flow.websocket
            if ws is None:
                return
            msg = ws.messages[-1]
        except Exception as e:
            ctx.log.warn("ws msg get error: %s" % e)
            return

        direction = "client->server" if msg.from_client else "server->client"
        try:
            text = msg.content.decode("utf-8", "replace")
        except Exception:
            text = repr(msg.content)
        self.messages.append({"direction": direction, "content": text})
        ctx.log.info("[WS] %s %s" % (direction, text))

        # 服务端推送的订单事件必须携带 order_id（契约断言）
        if not msg.from_client:
            try:
                data = json.loads(msg.content)
                if data.get("type") in ("order_created", "order_paid"):
                    self.assertions.append({
                        "type": data.get("type"),
                        "has_order_id": bool(data.get("order_id")),
                        "passed": bool(data.get("order_id")),
                    })
            except Exception:
                pass
        self._dump()

    def websocket_end(self, flow):
        if not self._is_mm_ws(flow):
            return
        ctx.log.info("[WS] connection closed")
        self._dump()

    def _dump(self):
        with open(self.ws_path, "w", encoding="utf-8") as f:
            json.dump({"messages": self.messages,
                       "assertions": self.assertions,
                       "all_passed": all(a["passed"] for a in self.assertions)},
                      f, ensure_ascii=False, indent=2)


addons = [MiniMallWSCapture()]
