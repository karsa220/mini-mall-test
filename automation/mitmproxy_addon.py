"""
MiniMall 抓包自动化 addon —— 用 mitmproxy 脚本化替代 Charles GUI。

职责（在代理流量时自动完成，无需手工点）：
  1. 拦截 MiniMall(5000 端口)的 HTTP 流量
  2. 对登录 / 下单 / 支付请求与响应做字段断言（送进接口/契约回归）
  3. 实时导出标准 HAR（capture.har）与断言汇总（mitm_assertions.json）

用法（由 run_mitm_capture.py 驱动）：
  mitmdump -p 8080 -s automation/mitmproxy_addon.py
环境变量 PROJECT_ROOT 指定输出文件根目录。

注意：mitmproxy 12 的脚本加载机制只递归遍历模块级 `addons` 列表，
因此本模块必须在末尾定义 `addons = [...]`（复数），实例才会被注册。
"""
import json
import os
import time
from mitmproxy import http, ctx


class MiniMallCapture:
    def __init__(self):
        root = os.environ.get("PROJECT_ROOT", "")
        out_dir = os.path.join(root, "automation") if root else "automation"
        self.har_path = os.path.join(out_dir, "capture.har")
        self.assert_path = os.path.join(out_dir, "mitm_assertions.json")
        self.entries = []      # HAR entries
        self.assertions = []   # 断言结果
        self.count = 0

    # ---------- 工具 ----------
    @staticmethod
    def _is_mm(flow):
        # 只关心 MiniMall 服务（5000 端口 或 /api/ 路径兜底）
        return flow.request.port == 5000 or flow.request.path.startswith("/api/")

    def _har_entry(self, flow):
        req, resp = flow.request, flow.response
        try:
            req_text = req.content.decode("utf-8", "replace")
        except Exception:
            req_text = ""
        try:
            resp_text = resp.content.decode("utf-8", "replace")
        except Exception:
            resp_text = ""
        start = getattr(req, "timestamp_start", time.time())
        end = getattr(resp, "timestamp_end", time.time())
        return {
            "startedDateTime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(start)),
            "time": max(0, int((end - start) * 1000)),
            "request": {
                "method": req.method,
                "url": req.url,
                "httpVersion": "HTTP/1.1",
                "headers": [{"name": k, "value": v} for k, v in req.headers.items()],
                "queryString": [{"name": k, "value": v} for k, v in req.query.items()],
                "cookies": [],
                "postData": {"mimeType": req.headers.get("Content-Type", ""), "text": req_text} if req_text else {},
                "bodySize": len(req.content or b""),
                "headerSize": -1,
            },
            "response": {
                "status": resp.status_code,
                "statusText": "",
                "httpVersion": "HTTP/1.1",
                "headers": [{"name": k, "value": v} for k, v in resp.headers.items()],
                "cookies": [],
                "content": {
                    "size": len(resp.content or b""),
                    "mimeType": resp.headers.get("Content-Type", ""),
                    "text": resp_text,
                },
                "bodySize": len(resp.content or b""),
                "headerSize": -1,
            },
            "cache": {},
            "timings": {"send": 0, "wait": max(0, int((end - start) * 1000)), "receive": 0},
            "serverIPAddress": "127.0.0.1",
        }

    def _assert(self, api, name, passed, detail):
        self.assertions.append({"api": api, "name": name, "passed": bool(passed), "detail": detail})

    def _dump_har(self):
        har = {"log": {"version": "1.2",
                       "creator": {"name": "MiniMallCapture(mitmproxy)", "version": "1.0"},
                       "entries": self.entries}}
        with open(self.har_path, "w", encoding="utf-8") as f:
            json.dump(har, f, ensure_ascii=False, indent=2)

    def _dump_assert(self):
        summary = {"captured_responses": self.count,
                   "assertions": self.assertions,
                   "all_passed": all(a["passed"] for a in self.assertions)}
        with open(self.assert_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    # ---------- 事件钩子 ----------
    def response(self, flow):
        if not self._is_mm(flow):
            return
        self.count += 1
        path = flow.request.path
        try:
            self.entries.append(self._har_entry(flow))
            self._dump_har()
        except Exception as e:
            ctx.log.warn("HAR dump error: %s" % e)

        try:
            body = json.loads(flow.request.content) if flow.request.content else {}
        except Exception:
            body = None
        try:
            resp = json.loads(flow.response.content) if flow.response.content else {}
        except Exception:
            resp = None

        if path.startswith("/api/login"):
            self._assert("login", "登录请求含 username/password",
                         isinstance(body, dict) and bool(body.get("username")) and bool(body.get("password")),
                         {"username": (body or {}).get("username")})
            self._assert("login", "登录响应返回 token(code=0)",
                         isinstance(resp, dict) and resp.get("code") == 0
                         and bool((resp.get("data") or {}).get("token")),
                         {"code": (resp or {}).get("code")})
        elif path.startswith("/api/order/create"):
            self._assert("order_create", "下单请求已发送", True, {"body": body})
            self._assert("order_create", "下单响应返回 order_id",
                         isinstance(resp, dict) and bool((resp.get("data") or {}).get("order_id")),
                         {"order_id": (resp or {}).get("data", {}).get("order_id")})
        elif path.startswith("/api/order/pay"):
            self._assert("pay", "支付响应 status=已支付",
                         isinstance(resp, dict) and (resp.get("data") or {}).get("status") == "已支付",
                         {"status": (resp or {}).get("data", {}).get("status")})

        self._dump_assert()
        ctx.log.info("[MiniMallCapture] 已捕获 %d 个响应，断言 %d 条" % (self.count, len(self.assertions)))


addons = [MiniMallCapture()]
