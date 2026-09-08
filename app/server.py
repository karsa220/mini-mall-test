"""
MiniMall 电商后端服务（被测系统）
接口：登录 / 商品 / 购物车 / 下单 / 优惠券 / 支付
说明：本系统预埋了 3 个典型缺陷，用于测试演示（见 docs/07-缺陷报告.md）

WebSocket 订单状态推送：用独立的 websockets 库在 5001 端口起一个 WS server，
下单/支付成功后通过 ws_broadcast 广播订单事件，供 mitmproxy 抓包实战使用。
（早期用过 flask_sock 绑定 5000，但与 Werkzeug 3.1.8 不兼容，故改为独立端口方案。）
"""
import asyncio
import json
import threading
import time
import os
import uuid
from flask import Flask, request, jsonify
import websockets

app = Flask(__name__)

# ---------------- 模拟数据存储（内存版，重启即重置） ----------------
USERS = {
    "test01": "123456",
    "test02": "abc@2026",
    "alice": "password123",
    "bob":   "password123",
}

PRODUCTS = {
    1: {"id": 1, "name": "机械键盘", "price": 199.00, "stock": 10},
    2: {"id": 2, "name": "无线鼠标", "price": 59.90, "stock": 50},
    3: {"id": 3, "name": "显示器支架", "price": 30.00, "stock": 5},
}

# 优惠券：满 30 减 10
COUPONS = {
    "MAN30JIAN10": {"threshold": 30.00, "discount": 10.00, "desc": "满30减10"},
}

TOKENS = {}   # token -> username
CARTS = {}    # username -> {product_id: quantity}
ORDERS = {}   # order_id -> order dict


# ---------------- WebSocket 订单状态推送（独立端口 5001） ----------------
WS_PORT = 5001
WS_LOOP = None
WS_CLIENTS = set()      # 当前订阅连接集合（asyncio WebSocketServerProtocol）
WS_LOCK = threading.Lock()


async def _ws_handler(ws):
    with WS_LOCK:
        WS_CLIENTS.add(ws)
    try:
        # 保持连接；客户端可发订阅消息，本演示广播全部订单事件
        async for _msg in ws:
            pass
    except Exception:
        pass
    finally:
        with WS_LOCK:
            WS_CLIENTS.discard(ws)


async def _ws_broadcast(payload):
    text = json.dumps(payload, ensure_ascii=False)
    dead = []
    with WS_LOCK:
        clients = list(WS_CLIENTS)
    for ws in clients:
        try:
            await ws.send(text)
        except Exception:
            dead.append(ws)
    if dead:
        with WS_LOCK:
            for ws in dead:
                WS_CLIENTS.discard(ws)


def ws_broadcast(payload):
    """供同步的 Flask 路由跨线程调用，把订单事件推送给所有 WS 订阅者"""
    if WS_LOOP is None:
        return
    asyncio.run_coroutine_threadsafe(_ws_broadcast(payload), WS_LOOP)


def _run_ws_server():
    global WS_LOOP
    loop = asyncio.new_event_loop()
    WS_LOOP = loop
    asyncio.set_event_loop(loop)

    async def amain():
        # websockets 17.x 的 serve 必须在运行中的事件循环内创建，故用 async with
        async with websockets.serve(_ws_handler, "0.0.0.0", WS_PORT):
            stop = asyncio.Event()
            await stop.wait()

    try:
        loop.run_until_complete(amain())
    except Exception as e:
        print("WS server error:", e)


def make_token(username):
    token = "tk_" + uuid.uuid4().hex[:16]
    TOKENS[token] = username
    return token


def auth_username():
    """标准 Bearer 鉴权：解析 Authorization: Bearer <token>"""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[7:].strip()
    if not token:
        return None
    return TOKENS.get(token)


def resp(code, msg, data=None):
    return jsonify({"code": code, "msg": msg, "data": data})


# ---------------- 登录 ----------------
@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        return resp(1001, "用户名或密码不能为空")
    if USERS.get(username) is None:
        return resp(1002, "用户不存在")
    if USERS[username] != password:
        return resp(1003, "密码错误")
    return resp(0, "登录成功", {"token": make_token(username)})


# ---------------- 商品 ----------------
@app.route("/api/products", methods=["GET"])
def products():
    return resp(0, "success", list(PRODUCTS.values()))


# ---------------- 购物车 ----------------
@app.route("/api/cart/add", methods=["POST"])
def cart_add():
    username = auth_username()
    if not username:
        return resp(401, "未登录或token已过期")
    body = request.get_json(silent=True) or {}
    pid = body.get("product_id")
    qty = body.get("quantity")
    if pid not in PRODUCTS:
        return resp(2001, "商品不存在")
    # !!! BUG-001：未校验 quantity 下限，0 和负数也能加进购物车
    if not isinstance(qty, int):
        return resp(2002, "quantity 必须为整数")
    if qty > PRODUCTS[pid]["stock"]:
        return resp(2003, "库存不足")
    cart = CARTS.setdefault(username, {})
    cart[pid] = cart.get(pid, 0) + qty
    return resp(0, "加购成功", cart)


@app.route("/api/cart", methods=["GET"])
def cart_detail():
    username = auth_username()
    if not username:
        return resp(401, "未登录或token已过期")
    cart = CARTS.get(username, {})
    items = []
    total = 0.0
    for pid, qty in cart.items():
        p = PRODUCTS[pid]
        subtotal = round(p["price"] * qty, 2)
        total += subtotal
        items.append({"product_id": pid, "name": p["name"],
                      "price": p["price"], "quantity": qty, "subtotal": subtotal})
    return resp(0, "success", {"items": items, "total": round(total, 2)})


@app.route("/api/cart/clear", methods=["DELETE"])
def cart_clear():
    username = auth_username()
    if not username:
        return resp(401, "未登录或token已过期")
    CARTS[username] = {}
    return resp(0, "购物车已清空")


# ---------------- 下单 / 支付 ----------------
def calc_amount(cart, coupon_code):
    """返回 (total, discount, payable, err_msg)"""
    total = round(sum(PRODUCTS[pid]["price"] * qty for pid, qty in cart.items()), 2)
    discount = 0.0
    if coupon_code:
        coupon = COUPONS.get(coupon_code)
        if not coupon:
            return None, None, None, "优惠券不存在"
        # !!! BUG-002：门槛判断用了 > 而非 >=，金额恰好等于门槛时无法使用优惠券
        if total > coupon["threshold"]:
            discount = coupon["discount"]
        else:
            return None, None, None, "未达到优惠券使用门槛"
    payable = round(total - discount, 2)
    return total, discount, payable, None


@app.route("/api/order/create", methods=["POST"])
def order_create():
    username = auth_username()
    if not username:
        return resp(401, "未登录或token已过期")
    body = request.get_json(silent=True) or {}
    coupon_code = body.get("coupon_code")
    cart = CARTS.get(username, {})
    if not cart:
        return resp(3001, "购物车为空")
    # 模拟真实后端下单时的 DB/下游调用延迟，放大「读购物车→清购物车」之间的并发竞态窗口
    # 默认关闭（lat=0），仅压测/复现幂等缺陷时使用；等价于 Charles Throttle 弱网下客户端重试的并发场景
    _lat = float(os.getenv("ORDER_SIM_LATENCY", "0") or 0)
    if _lat > 0:
        time.sleep(_lat)
    total, discount, payable, err = calc_amount(cart, coupon_code)
    if err:
        return resp(3002, err)
    # !!! BUG-003：无幂等控制，同一购物车重复请求会创建多笔订单
    order_id = "OD" + time.strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4]
    ORDERS[order_id] = {
        "order_id": order_id, "username": username, "items": dict(cart),
        "total": total, "discount": discount, "payable": payable,
        "status": "待支付", "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    for pid, qty in cart.items():
        PRODUCTS[pid]["stock"] -= qty
    CARTS[username] = {}
    # 通过 WebSocket 实时推送「订单已创建」（供 mitmproxy 抓包实战）
    ws_broadcast({"type": "order_created", "order_id": order_id,
                  "username": username, "status": "待支付", "payable": payable})
    return resp(0, "下单成功", ORDERS[order_id])


@app.route("/api/order/pay", methods=["POST"])
def order_pay():
    username = auth_username()
    if not username:
        return resp(401, "未登录或token已过期")
    body = request.get_json(silent=True) or {}
    order = ORDERS.get(body.get("order_id"))
    if not order:
        return resp(4001, "订单不存在")
    if order["username"] != username:
        return resp(4002, "无权操作他人订单")
    if order["status"] != "待支付":
        return resp(4003, "订单状态不允许支付")
    order["status"] = "已支付"
    # 通过 WebSocket 实时推送「订单已支付」（供 mitmproxy 抓包实战）
    ws_broadcast({"type": "order_paid", "order_id": order["order_id"],
                  "username": username, "status": "已支付"})
    return resp(0, "支付成功", order)


@app.route("/api/orders", methods=["GET"])
def order_list():
    username = auth_username()
    if not username:
        return resp(401, "未登录或token已过期")
    mine = [o for o in ORDERS.values() if o["username"] == username]
    return resp(0, "success", mine)


# ---------------- H5 测试入口（Appium 跑这个页面） ----------------
@app.route('/')
def index():
    """迷你 H5 登录页：Appium 操作这个页面就能验证接口 + 表单自动化"""
    return '''
    <!DOCTYPE html>
    <html lang="zh">
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>MiniMall H5</title>
    </head>
    <body style="font-family:system-ui;padding:24px;max-width:480px;margin:auto">
      <h1 style="color:#333">MiniMall 测试入口</h1>
      <p style="color:#666;font-size:14px">Appium 移动端 UI 自动化测试对象</p>
      <label>用户名</label><br>
      <input id="username" value="alice" style="width:100%;padding:10px;margin:6px 0;box-sizing:border-box"><br>
      <label>密码</label><br>
      <input id="password" type="password" value="password123" style="width:100%;padding:10px;margin:6px 0;box-sizing:border-box"><br>
      <button id="btn_login" style="padding:12px 24px;margin-top:8px;background:#1677ff;color:#fff;border:0;border-radius:6px">登录</button>
      <pre id="result" style="background:#f5f5f5;padding:12px;margin-top:16px;white-space:pre-wrap;word-break:break-all"></pre>

      <div id="order_panel" style="display:none;margin-top:24px;border-top:1px solid #eee;padding-top:16px">
        <h2 style="color:#333;font-size:18px">订单流程</h2>
        <p style="color:#666;font-size:13px">token: <span id="token_text"></span></p>
        <div>
          <button id="btn_add_cart_1" style="padding:10px 16px;margin:4px;background:#1677ff;color:#fff;border:0;border-radius:6px">加购 机械键盘</button>
          <button id="btn_add_cart_2" style="padding:10px 16px;margin:4px;background:#1677ff;color:#fff;border:0;border-radius:6px">加购 无线鼠标</button>
          <button id="btn_clear_cart" style="padding:10px 16px;margin:4px;background:#999;color:#fff;border:0;border-radius:6px">清空购物车</button>
        </div>
        <div style="margin-top:10px">
          <button id="btn_create_order" style="padding:10px 16px;margin:4px;background:#52c41a;color:#fff;border:0;border-radius:6px">创建订单</button>
          <button id="btn_pay" style="padding:10px 16px;margin:4px;background:#fa8c16;color:#fff;border:0;border-radius:6px">支付订单</button>
        </div>
        <p style="color:#666;font-size:13px">order_id: <span id="order_id"></span></p>
        <pre id="order_result" style="background:#f5f5f5;padding:12px;margin-top:12px;white-space:pre-wrap;word-break:break-all"></pre>
      </div>

      <script>
        document.getElementById("btn_login").onclick = async () => {
          const u = document.getElementById("username").value;
          const p = document.getElementById("password").value;
          document.getElementById("result").innerText = "登录中...";
          try {
            const r = await fetch("/api/login", {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({username: u, password: p})
            });
            const data = await r.json();
            document.getElementById("result").innerText = JSON.stringify(data, null, 2);
            if (data.code === 0 && data.data && data.data.token) {
              TOKEN = data.data.token;
              document.getElementById("token_text").innerText = TOKEN;
              document.getElementById("order_panel").style.display = "block";
            }
          } catch (e) {
            document.getElementById("result").innerText = "请求失败: " + e;
          }
        };

        var TOKEN = "";
        var ORDER_ID = "";
        function authHeaders() {
          return {"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN};
        }
        function showOrder(data) {
          document.getElementById("order_result").innerText = JSON.stringify(data, null, 2);
        }
        document.getElementById("btn_add_cart_1").onclick = async function(){ await addCart(1, 1); };
        document.getElementById("btn_add_cart_2").onclick = async function(){ await addCart(2, 1); };
        document.getElementById("btn_clear_cart").onclick = async function(){
          try {
            var r = await fetch("/api/cart/clear", {method:"DELETE", headers: authHeaders()});
            showOrder(await r.json());
          } catch(e){ document.getElementById("order_result").innerText = "请求失败: " + e; }
        };
        async function addCart(pid, qty) {
          try {
            var r = await fetch("/api/cart/add", {method:"POST", headers: authHeaders(), body: JSON.stringify({product_id:pid, quantity:qty})});
            showOrder(await r.json());
          } catch(e){ document.getElementById("order_result").innerText = "请求失败: " + e; }
        }
        document.getElementById("btn_create_order").onclick = async function(){
          try {
            var r = await fetch("/api/order/create", {method:"POST", headers: authHeaders(), body: JSON.stringify({coupon_code:""})});
            var data = await r.json();
            showOrder(data);
            if (data.code === 0 && data.data && data.data.order_id) {
              ORDER_ID = data.data.order_id;
              document.getElementById("order_id").innerText = ORDER_ID;
            }
          } catch(e){ document.getElementById("order_result").innerText = "请求失败: " + e; }
        };
        document.getElementById("btn_pay").onclick = async function(){
          if (!ORDER_ID) { document.getElementById("order_result").innerText = "请先创建订单"; return; }
          try {
            var r = await fetch("/api/order/pay", {method:"POST", headers: authHeaders(), body: JSON.stringify({order_id: ORDER_ID})});
            showOrder(await r.json());
          } catch(e){ document.getElementById("order_result").innerText = "请求失败: " + e; }
        };
      </script>
    </body></html>
    '''


if __name__ == "__main__":
    # 先起独立 WS server（5001），再起 Flask REST（5000，多线程以支持 WS 长连接与 REST 并发）
    threading.Thread(target=_run_ws_server, daemon=True).start()
    time.sleep(0.5)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
