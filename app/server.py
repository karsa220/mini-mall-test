"""
MiniMall 电商后端服务（被测系统）
接口：登录 / 商品 / 购物车 / 下单 / 优惠券 / 支付
说明：本系统预埋了 3 个典型缺陷，用于测试演示（见 docs/07-缺陷报告.md）
"""
from flask import Flask, request, jsonify
import time
import uuid

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
    return resp(0, "支付成功", order)


@app.route("/api/orders", methods=["GET"])
def order_list():
    username = auth_username()
    if not username:
        return resp(401, "未登录或token已过期")
    mine = [o for o in ORDERS.values() if o["username"] == username]
    return resp(0, "success", mine)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
