"""
MiniMall 电商后端服务（被测系统 · 企业级版）
=========================================
相比早期"玩具版"，本次重构为真实可落库的关系型电商后端：
  - 持久化：SQLAlchemy + SQLite（用户/地址/商品/购物车/优惠券/订单/订单项/幂等键）
  - 鉴权：密码哈希 + 签名 Bearer Token（itsdangerous），支持登出吊销
  - 交易正确性：下单原子扣库存（防超卖）、支付幂等（同键重试不重复扣款）
  - 营销：满减/折扣/品类限定/可叠加/有效期（见 promotion.py）
  - 可观测/韧性：/metrics 指标、/api/chaos/* 故障注入（高可用测试）
  - 实时：下单/支付经 WebSocket(5001) 推送，供 mitmproxy 抓包实战

预埋缺陷（用于测试价值演示，已被对应用例固化）：
  BUG-001：购物车 quantity 下限未校验（0/负数可被加入）
  BUG-002：满减门槛用严格大于，金额恰等于门槛时优惠券不可用（应为可用）

WebSocket 订单状态推送（独立端口 5001）：与 Werkzeug 3.1.8 不兼容的 flask_sock 方案已弃用。
"""
import asyncio
import json
import threading
import time
import os
import uuid
import random
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, g
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import update as sa_update, delete as sa_delete

import websockets
from db import (
    Session, User, Address, Product, CartItem, Coupon, UserCoupon,
    Order, OrderItem, Idempotency, init_db,
)
from promotion import calc_amount, CATALOG, COUPONS

app = Flask(__name__)
init_db(seed=True)

# ---------------- 鉴权 ----------------
SECRET = os.environ.get("MINIMALL_SECRET", "dev-secret-change-me")
_signer = URLSafeTimedSerializer(SECRET)
REVOKED = set()  # 已吊销 jti


def make_token(username):
    jti = uuid.uuid4().hex
    return _signer.dumps({"u": username, "jti": jti})


def auth_username():
    """Bearer 鉴权：解析 Authorization: Bearer <token>，校验签名与吊销。"""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[7:].strip()
    if not token:
        return None
    try:
        data = _signer.loads(token, max_age=86400)
    except (BadSignature, SignatureExpired):
        return None
    if data.get("jti") in REVOKED:
        return None
    return data.get("u")


def auth_uid():
    """返回当前用户 DB id，未登录/已吊销返回 None。"""
    uname = auth_username()
    if not uname:
        return None
    s = Session()
    try:
        u = s.query(User).filter_by(username=uname).first()
        return u.id if u else None
    finally:
        s.close()


def auth_admin_uid():
    uname = auth_username()
    if not uname:
        return None
    s = Session()
    try:
        u = s.query(User).filter_by(username=uname).first()
        return u.id if (u and u.role == "admin") else None
    finally:
        s.close()


def resp(code, msg, data=None):
    return jsonify({"code": code, "msg": msg, "data": data})


# 登录失败限流（防暴力破解）：按用户名记失败时间戳，60s 内超过阈值拒绝
_LOGIN_FAIL = {}
_LOGIN_WINDOW = 60
_LOGIN_MAX_FAIL = 8


def _db_catalog(pid_list):
    """从 DB 构造促销计算用的目录 {pid: {price, category}}。"""
    s = Session()
    try:
        prods = s.query(Product).filter(Product.id.in_(pid_list)).all()
        return {p.id: {"price": p.price, "category": p.category} for p in prods}
    finally:
        s.close()


# ---------------- WebSocket 订单推送（独立端口 5001） ----------------
WS_PORT = 5001
WS_LOOP = None
WS_CLIENTS = set()
WS_LOCK = threading.Lock()


async def _ws_handler(ws):
    with WS_LOCK:
        WS_CLIENTS.add(ws)
    try:
        async for _msg in ws:
            pass
    except Exception:
        pass
    finally:
        with WS_LOCK:
            WS_CLIENTS.discard(ws)


async def _ws_broadcast(payload):
    text = json.dumps(payload, ensure_ascii=False)
    with WS_LOCK:
        clients = list(WS_CLIENTS)
    for ws in clients:
        try:
            await ws.send(text)
        except Exception:
            pass


def ws_broadcast(payload):
    if WS_LOOP is None:
        return
    asyncio.run_coroutine_threadsafe(_ws_broadcast(payload), WS_LOOP)


def _run_ws_server():
    global WS_LOOP
    loop = asyncio.new_event_loop()
    WS_LOOP = loop
    asyncio.set_event_loop(loop)

    async def amain():
        async with websockets.serve(_ws_handler, "0.0.0.0", WS_PORT):
            stop = asyncio.Event()
            await stop.wait()

    try:
        loop.run_until_complete(amain())
    except Exception as e:
        print("WS server error:", e)


# ---------------- 用户 / 鉴权 ----------------
@app.route("/api/register", methods=["POST"])
def register():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if len(username) < 3 or len(username) > 32:
        return resp(1004, "用户名长度需 3-32 位")
    if len(password) < 6:
        return resp(1005, "密码至少 6 位")
    s = Session()
    try:
        if s.query(User).filter_by(username=username).first():
            return resp(1006, "用户名已存在")
        u = User(username=username, pw_hash=generate_password_hash(password), role="normal")
        s.add(u)
        s.commit()
        return resp(0, "注册成功", {"username": username})
    finally:
        s.close()


@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        return resp(1001, "用户名或密码不能为空")
    now = time.time()
    fails = [t for t in _LOGIN_FAIL.get(username, []) if now - t < _LOGIN_WINDOW]
    if len(fails) >= _LOGIN_MAX_FAIL:
        return resp(429, "登录失败次数过多，请稍后再试")
    s = Session()
    try:
        u = s.query(User).filter_by(username=username).first()
        if not u:
            return resp(1002, "用户不存在")
        if not check_password_hash(u.pw_hash, password):
            fails.append(now)
            _LOGIN_FAIL[username] = fails
            return resp(1003, "密码错误")
        _LOGIN_FAIL.pop(username, None)
        return resp(0, "登录成功", {"token": make_token(username)})
    finally:
        s.close()


@app.route("/api/logout", methods=["POST"])
def logout():
    uname = auth_username()
    if not uname:
        return resp(401, "未登录或token已过期")
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.startswith("Bearer ") else ""
    try:
        data = _signer.loads(token, max_age=86400)
        REVOKED.add(data.get("jti"))
    except Exception:
        pass
    return resp(0, "已登出")


@app.route("/api/profile", methods=["GET"])
def profile():
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    s = Session()
    try:
        u = s.query(User).get(uid)
        return resp(0, "success", {"username": u.username, "role": u.role})
    finally:
        s.close()


# ---------------- 收货地址 ----------------
@app.route("/api/addresses", methods=["POST"])
def address_add():
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    phone = (body.get("phone") or "").strip()
    detail = (body.get("detail") or "").strip()
    if not (name and phone and detail):
        return resp(5001, "姓名/电话/详细地址均必填")
    s = Session()
    try:
        a = Address(user_id=uid, name=name, phone=phone, detail=detail)
        s.add(a)
        s.commit()
        return resp(0, "地址已添加", {"id": a.id})
    finally:
        s.close()


@app.route("/api/addresses", methods=["GET"])
def address_list():
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    s = Session()
    try:
        items = [{"id": a.id, "name": a.name, "phone": a.phone, "detail": a.detail}
                 for a in s.query(Address).filter_by(user_id=uid).all()]
        return resp(0, "success", items)
    finally:
        s.close()


@app.route("/api/addresses/<int:aid>", methods=["DELETE"])
def address_del(aid):
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    s = Session()
    try:
        a = s.query(Address).filter_by(id=aid, user_id=uid).first()
        if not a:
            return resp(5002, "地址不存在或无权限")
        s.delete(a)
        s.commit()
        return resp(0, "地址已删除")
    finally:
        s.close()


# ---------------- 商品 ----------------
@app.route("/api/products", methods=["GET"])
def products():
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    sort = (request.args.get("sort") or "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
        page_size = min(100, max(1, int(request.args.get("page_size", 20))))
    except ValueError:
        return resp(2005, "分页参数非法")
    s = Session()
    try:
        query = s.query(Product).filter(Product.status == 1)
        if q:
            query = query.filter(Product.name.like(f"%{q}%"))
        if category:
            query = query.filter(Product.category == category)
        total = query.count()
        if sort == "price_asc":
            query = query.order_by(Product.price.asc())
        elif sort == "price_desc":
            query = query.order_by(Product.price.desc())
        rows = query.limit(page_size).offset((page - 1) * page_size).all()
        items = [{"id": p.id, "name": p.name, "category": p.category,
                  "price": p.price, "stock": p.stock} for p in rows]
        return resp(0, "success", {"items": items, "total": total,
                                    "page": page, "page_size": page_size})
    finally:
        s.close()


@app.route("/api/products/<int:pid>", methods=["GET"])
def product_detail(pid):
    s = Session()
    try:
        p = s.query(Product).get(pid)
        if not p or p.status != 1:
            return resp(2004, "商品不存在")
        return resp(0, "success", {"id": p.id, "name": p.name, "category": p.category,
                                    "price": p.price, "stock": p.stock})
    finally:
        s.close()


@app.route("/api/admin/products", methods=["POST"])
def admin_product_create():
    uid = auth_admin_uid()
    if uid is None:
        return resp(403, "无权限（需管理员）")
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    try:
        price = float(body.get("price", 0))
        stock = int(body.get("stock", 0))
    except (TypeError, ValueError):
        return resp(2006, "价格/库存非法")
    if not name or price <= 0 or stock < 0:
        return resp(2007, "商品名称/价格/库存非法")
    s = Session()
    try:
        p = Product(name=name, category=body.get("category") or "general",
                    price=price, stock=stock)
        s.add(p)
        s.commit()
        return resp(0, "商品已创建", {"id": p.id})
    finally:
        s.close()


@app.route("/api/admin/products/<int:pid>/stock", methods=["PATCH"])
def admin_stock_adjust(pid):
    uid = auth_admin_uid()
    if uid is None:
        return resp(403, "无权限（需管理员）")
    body = request.get_json(silent=True) or {}
    try:
        delta = int(body.get("delta", 0))
    except (TypeError, ValueError):
        return resp(2008, "delta 必须为整数")
    s = Session()
    try:
        p = s.query(Product).with_for_update().filter_by(id=pid).first()
        if not p:
            return resp(2004, "商品不存在")
        new_stock = max(0, p.stock + delta)
        p.stock = new_stock
        s.commit()
        return resp(0, "库存已调整", {"id": p.id, "stock": new_stock})
    finally:
        s.close()


# ---------------- 优惠券 ----------------
@app.route("/api/coupons/claim", methods=["POST"])
def coupon_claim():
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    body = request.get_json(silent=True) or {}
    code = (body.get("code") or "").strip()
    s = Session()
    try:
        cp = s.query(Coupon).filter_by(code=code).first()
        if not cp:
            return resp(6001, "优惠券不存在")
        now = datetime.utcnow()
        if cp.end_at and now > cp.end_at:
            return resp(6002, "优惠券已过期")
        if cp.total_limit:
            issued = s.query(UserCoupon).filter_by(coupon_id=cp.id).count()
            if issued >= cp.total_limit:
                return resp(6003, "优惠券已被领完")
        held = s.query(UserCoupon).filter_by(user_id=uid, coupon_id=cp.id).count()
        if held >= cp.per_user_limit:
            return resp(6004, "已超过领取上限")
        uc = UserCoupon(user_id=uid, coupon_id=cp.id, used=False)
        s.add(uc)
        s.commit()
        return resp(0, "领取成功", {"code": cp.code})
    finally:
        s.close()


@app.route("/api/coupons", methods=["GET"])
def my_coupons():
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    s = Session()
    try:
        rows = (s.query(UserCoupon, Coupon)
                .join(Coupon, UserCoupon.coupon_id == Coupon.id)
                .filter(UserCoupon.user_id == uid).all())
        items = [{"code": c.code, "type": c.type, "used": uc.used,
                  "desc": c.desc} for uc, c in rows]
        return resp(0, "success", items)
    finally:
        s.close()


@app.route("/api/admin/coupons", methods=["POST"])
def admin_coupon_issue():
    uid = auth_admin_uid()
    if uid is None:
        return resp(403, "无权限（需管理员）")
    body = request.get_json(silent=True) or {}
    code = (body.get("code") or "").strip()
    if not code:
        return resp(6005, "优惠券 code 必填")
    s = Session()
    try:
        if s.query(Coupon).filter_by(code=code).first():
            return resp(6006, "优惠券 code 已存在")
        end = None
        if body.get("end_at"):
            end = datetime.fromisoformat(body["end_at"])
        cp = Coupon(
            code=code,
            type=body.get("type", "full_reduction"),
            threshold=float(body.get("threshold", 0) or 0),
            value=float(body.get("value", 0) or 0),
            rate=float(body.get("rate", 0) or 0),
            cap=float(body.get("cap", 0) or 0),
            category=body.get("category"),
            stackable=bool(body.get("stackable", False)),
            per_user_limit=int(body.get("per_user_limit", 1) or 1),
            total_limit=int(body.get("total_limit", 0) or 0),
            end_at=end,
            desc=body.get("desc", ""),
        )
        s.add(cp)
        s.commit()
        return resp(0, "优惠券已发放", {"code": cp.code})
    finally:
        s.close()


# ---------------- 购物车 ----------------
@app.route("/api/cart/add", methods=["POST"])
def cart_add():
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    body = request.get_json(silent=True) or {}
    pid = body.get("product_id")
    qty = body.get("quantity")
    s = Session()
    try:
        p = s.query(Product).get(pid) if isinstance(pid, int) else None
        if not isinstance(pid, int) or not p:
            return resp(2001, "商品不存在")
        # BUG-001 预埋：未校验 quantity 下限，0 与负数可被加入购物车
        if not isinstance(qty, int):
            return resp(2002, "quantity 必须为整数")
        if qty > p.stock:
            return resp(2003, "库存不足")
        item = s.query(CartItem).filter_by(user_id=uid, product_id=pid).first()
        if item:
            item.qty += qty
        else:
            s.add(CartItem(user_id=uid, product_id=pid, qty=qty))
        s.commit()
        return resp(0, "加购成功", _cart_view(s, uid))
    finally:
        s.close()


@app.route("/api/cart", methods=["GET"])
def cart_detail():
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    s = Session()
    try:
        return resp(0, "success", _cart_view(s, uid))
    finally:
        s.close()


@app.route("/api/cart/item", methods=["PATCH"])
def cart_item_update():
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    body = request.get_json(silent=True) or {}
    pid = body.get("product_id")
    qty = body.get("quantity")
    if not isinstance(pid, int) or not isinstance(qty, int):
        return resp(2009, "product_id/quantity 必须为整数")
    s = Session()
    try:
        p = s.query(Product).get(pid)
        if not p:
            return resp(2001, "商品不存在")
        if qty > p.stock:
            return resp(2003, "库存不足")
        item = s.query(CartItem).filter_by(user_id=uid, product_id=pid).first()
        if not item:
            return resp(2010, "购物车中无此商品")
        if qty <= 0:
            s.delete(item)            # 数量<=0 视为移除
        else:
            item.qty = qty
        s.commit()
        return resp(0, "更新成功", _cart_view(s, uid))
    finally:
        s.close()


@app.route("/api/cart/item/<int:pid>", methods=["DELETE"])
def cart_item_remove(pid):
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    s = Session()
    try:
        item = s.query(CartItem).filter_by(user_id=uid, product_id=pid).first()
        if item:
            s.delete(item)
            s.commit()
        return resp(0, "移除成功", _cart_view(s, uid))
    finally:
        s.close()


@app.route("/api/cart/clear", methods=["DELETE"])
def cart_clear():
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    s = Session()
    try:
        s.query(CartItem).filter_by(user_id=uid).delete()
        s.commit()
        return resp(0, "购物车已清空")
    finally:
        s.close()


def _cart_view(s, uid):
    items = s.query(CartItem).filter_by(user_id=uid).all()
    view = []
    total = 0.0
    for it in items:
        p = s.query(Product).get(it.product_id)
        if not p:
            continue
        subtotal = round(p.price * it.qty, 2)
        total += subtotal
        view.append({"product_id": p.id, "name": p.name, "price": p.price,
                     "quantity": it.qty, "subtotal": subtotal})
    return {"items": view, "total": round(total, 2)}


# ---------------- 订单 ----------------
def _gen_order_no():
    return "OD" + time.strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4]


@app.route("/api/order/create", methods=["POST"])
def order_create():
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    body = request.get_json(silent=True) or {}
    coupon_code = (body.get("coupon_code") or "").strip()
    idem_key = request.headers.get("Idempotency-Key", "").strip()

    s = Session()
    try:
        # 幂等：同键直接返回已创建的订单，避免弱网重试重复下单
        if idem_key:
            rec = s.query(Idempotency).get(idem_key)
            if rec and rec.order_no:
                exist = s.query(Order).filter_by(order_no=rec.order_no).first()
                if exist:
                    return resp(0, "订单已存在（幂等）", _order_view(exist))

        cart_items = s.query(CartItem).filter_by(user_id=uid).all()
        if not cart_items:
            return resp(3001, "购物车为空")
        items = {it.product_id: it.qty for it in cart_items}
        pids = list(items.keys())
        catalog = _db_catalog(pids)
        total = round(sum(round(catalog[pid]["price"] * qty, 2)
                          for pid, qty in items.items()), 2)

        # 解析优惠券（必须是本人已领取且未使用）
        coupon = None
        if coupon_code:
            uc = (s.query(UserCoupon).join(Coupon, UserCoupon.coupon_id == Coupon.id)
                  .filter(UserCoupon.user_id == uid, Coupon.code == coupon_code,
                          UserCoupon.used == False).first())
            if not uc:
                return resp(3004, "未领取或已使用此优惠券")
            cp = s.query(Coupon).get(uc.coupon_id)
            coupon = {"type": cp.type, "threshold": cp.threshold, "value": cp.value,
                      "rate": cp.rate, "cap": cp.cap, "category": cp.category}
            # 原子核销：WHERE used==False 保证并发下只有一个请求能核销成功
            used_res = s.execute(
                sa_update(UserCoupon)
                .where(UserCoupon.id == uc.id, UserCoupon.used == False)
                .values(used=True)
            )
            if used_res.rowcount == 0:
                s.rollback()
                return resp(3004, "优惠券已被使用（并发冲突）")

        if coupon:
            total, discount, payable, err = calc_amount(items, coupon, catalog)
        else:
            discount = 0.0
            payable = total
            err = None
        if err:
            return resp(3002, err)

        # 库存校验
        for pid, qty in items.items():
            p = s.query(Product).get(pid)
            if not p or p.stock < qty:
                return resp(2003, "库存不足")

        # 模拟「读购物车→扣库存」之间的并发窗口（默认关闭），用于复现/验证防超卖
        _lat = float(os.getenv("ORDER_SIM_LATENCY", "0") or 0)
        if _lat > 0:
            time.sleep(_lat)

        # 原子扣库存：WHERE stock>=qty 保证不会超卖；任一失败整体回滚
        for pid, qty in items.items():
            res = s.execute(
                sa_update(Product)
                .where(Product.id == pid, Product.stock >= qty)
                .values(stock=Product.stock - qty)
            )
            if res.rowcount == 0:
                s.rollback()
                return resp(2003, "库存不足（并发扣减失败）")

        order_no = _gen_order_no()
        order = Order(order_no=order_no, user_id=uid, status="UNPAID",
                      total=total, discount=discount if coupon else 0.0,
                      payable=payable, coupon_id=(uc.coupon_id if coupon else None),
                      idem_key=idem_key or None)
        s.add(order)
        s.flush()
        for pid, qty in items.items():
            p = s.query(Product).get(pid)
            s.add(OrderItem(order_id=order.id, product_id=pid, name=p.name,
                            price=p.price, qty=qty))
        # 原子清空购物车（按影响行数判断）：并发下第二个请求读到 0 行 -> 回滚，
        # 避免同一购物车被并发提交出两笔订单
        del_res = s.execute(sa_delete(CartItem).where(CartItem.user_id == uid))
        if del_res.rowcount == 0:
            s.rollback()
            return resp(3001, "购物车为空（并发已被他人提交）")
        if idem_key:
            s.add(Idempotency(key=idem_key, order_no=order_no))
        s.commit()

        view = _order_view(order)
        ws_broadcast({"type": "order_created", "order_id": order_no,
                      "username": auth_username(), "status": "UNPAID",
                      "payable": payable})
        return resp(0, "下单成功", view)
    finally:
        s.close()


@app.route("/api/order/pay", methods=["POST"])
def order_pay():
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    body = request.get_json(silent=True) or {}
    order_id = body.get("order_id") or body.get("order_no")
    s = Session()
    try:
        order = s.query(Order).filter_by(order_no=order_id).first()
        if not order:
            return resp(4001, "订单不存在")
        if order.user_id != uid:
            return resp(4002, "无权操作他人订单")
        # 幂等：已支付直接返回成功，避免重复扣款
        if order.status == "PAID":
            return resp(0, "订单已支付（幂等）", _order_view(order))
        if order.status != "UNPAID":
            return resp(4003, "订单状态不允许支付")
        order.status = "PAID"
        order.paid_at = datetime.utcnow()
        s.commit()
        view = _order_view(order)
        ws_broadcast({"type": "order_paid", "order_id": order.order_no,
                      "username": auth_username(), "status": "PAID"})
        return resp(0, "支付成功", view)
    finally:
        s.close()


@app.route("/api/order/<order_id>/cancel", methods=["POST"])
def order_cancel(order_id):
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    s = Session()
    try:
        order = s.query(Order).filter_by(order_no=order_id).first()
        if not order:
            return resp(4001, "订单不存在")
        if order.user_id != uid:
            return resp(4002, "无权操作他人订单")
        if order.status != "UNPAID":
            return resp(4004, "仅待支付订单可取消")
        order.status = "CANCELLED"
        s.commit()
        return resp(0, "订单已取消", _order_view(order))
    finally:
        s.close()


@app.route("/api/order/<order_id>/refund", methods=["POST"])
def order_refund(order_id):
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    s = Session()
    try:
        order = s.query(Order).filter_by(order_no=order_id).first()
        if not order:
            return resp(4001, "订单不存在")
        if order.user_id != uid:
            return resp(4002, "无权操作他人订单")
        if order.status != "PAID":
            return resp(4005, "仅已支付订单可退款")
        order.status = "REFUNDED"
        s.commit()
        return resp(0, "退款成功", _order_view(order))
    finally:
        s.close()


@app.route("/api/orders", methods=["GET"])
def order_list():
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    s = Session()
    try:
        rows = s.query(Order).filter_by(user_id=uid).order_by(Order.id.desc()).all()
        return resp(0, "success", [_order_view(o) for o in rows])
    finally:
        s.close()


@app.route("/api/orders/<order_id>", methods=["GET"])
def order_detail(order_id):
    uid = auth_uid()
    if uid is None:
        return resp(401, "未登录或token已过期")
    s = Session()
    try:
        order = s.query(Order).filter_by(order_no=order_id).first()
        if not order:
            return resp(4001, "订单不存在")
        if order.user_id != uid:
            return resp(4002, "无权操作他人订单")
        return resp(0, "success", _order_view(order))
    finally:
        s.close()


def _order_view(order):
    s = Session()
    try:
        items = [{"product_id": it.product_id, "name": it.name,
                  "price": it.price, "quantity": it.qty}
                 for it in s.query(OrderItem).filter_by(order_id=order.id).all()]
    finally:
        s.close()
    return {
        "order_id": order.order_no,
        "order_no": order.order_no,
        "status": order.status,
        "total": order.total,
        "discount": order.discount,
        "payable": order.payable,
        "items": items,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
    }


# ---------------- H5 测试入口（Appium 跑这个页面） ----------------
@app.route('/')
def index():
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
        var TOKEN = ""; var ORDER_ID = "";
        function authHeaders(){ return {"Content-Type":"application/json","Authorization":"Bearer "+TOKEN}; }
        document.getElementById("btn_login").onclick = async () => {
          const u=document.getElementById("username").value, p=document.getElementById("password").value;
          const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:u,password:p})});
          const data=await r.json(); document.getElementById("result").innerText=JSON.stringify(data,null,2);
          if(data.code===0&&data.data&&data.data.token){TOKEN=data.data.token;document.getElementById("token_text").innerText=TOKEN;document.getElementById("order_panel").style.display="block";}
        };
        document.getElementById("btn_add_cart_1").onclick=async()=>await addCart(1,1);
        document.getElementById("btn_add_cart_2").onclick=async()=>await addCart(2,1);
        document.getElementById("btn_clear_cart").onclick=async()=>{const r=await fetch("/api/cart/clear",{method:"DELETE",headers:authHeaders()});show(await r.json());};
        async function addCart(pid,qty){const r=await fetch("/api/cart/add",{method:"POST",headers:authHeaders(),body:JSON.stringify({product_id:pid,quantity:qty})});show(await r.json());}
        function show(d){document.getElementById("order_result").innerText=JSON.stringify(d,null,2);}
        document.getElementById("btn_create_order").onclick=async()=>{const r=await fetch("/api/order/create",{method:"POST",headers:authHeaders(),body:JSON.stringify({coupon_code:""})});const d=await r.json();show(d);if(d.code===0&&d.data&&d.data.order_id){ORDER_ID=d.data.order_id;document.getElementById("order_id").innerText=ORDER_ID;}};
        document.getElementById("btn_pay").onclick=async()=>{if(!ORDER_ID){show("请先创建订单");return;}const r=await fetch("/api/order/pay",{method:"POST",headers:authHeaders(),body:JSON.stringify({order_id:ORDER_ID})});show(await r.json());};
      </script>
    </body></html>
    '''


# ---------------- 混沌工程 / 故障注入 ----------------
CHAOS = {"latency": 0.0, "error_rate": 0.0, "down": False, "error_code": 500}
_CHAOS_LOCK = threading.Lock()


@app.before_request
def _chaos_inject():
    p = request.path
    if p.startswith("/api/chaos") or p in ("/metrics", "/"):
        return
    with _CHAOS_LOCK:
        down = CHAOS["down"]
        lat = CHAOS["latency"]
        err_rate = CHAOS["error_rate"]
        err_code = CHAOS["error_code"]
    if down:
        return resp(503, "服务不可用（混沌注入：服务宕机）")
    if lat > 0:
        time.sleep(lat)
    if err_rate > 0 and random.random() < err_rate:
        return resp(err_code, "混沌注入：随机服务端错误")


@app.route("/api/chaos/set", methods=["POST"])
def chaos_set():
    body = request.get_json(silent=True) or {}
    with _CHAOS_LOCK:
        for k in ("latency", "error_rate", "error_code"):
            if k in body and body[k] is not None:
                CHAOS[k] = body[k]
        if "down" in body:
            CHAOS["down"] = bool(body["down"])
    return resp(0, "chaos set", dict(CHAOS))


@app.route("/api/chaos/reset", methods=["POST"])
def chaos_reset():
    with _CHAOS_LOCK:
        CHAOS.update({"latency": 0.0, "error_rate": 0.0, "down": False, "error_code": 500})
    return resp(0, "chaos reset", dict(CHAOS))


@app.route("/api/chaos/status", methods=["GET"])
def chaos_status():
    with _CHAOS_LOCK:
        return resp(0, "chaos status", dict(CHAOS))


# ---------------- 可观测性 /metrics ----------------
METRICS = {"req_total": 0, "req_err": 0, "lat_sum": 0.0, "lat_max": 0.0}
_METRICS_LOCK = threading.Lock()


@app.before_request
def _start_timer():
    g._t0 = time.perf_counter()


@app.after_request
def _metrics_collect(response):
    dt = time.perf_counter() - getattr(g, "_t0", time.perf_counter())
    with _METRICS_LOCK:
        METRICS["req_total"] += 1
        METRICS["lat_sum"] += dt
        if dt > METRICS["lat_max"]:
            METRICS["lat_max"] = dt
        if response.status_code >= 500:
            METRICS["req_err"] += 1
    return response


@app.route("/metrics")
def metrics():
    with _METRICS_LOCK:
        avg = (METRICS["lat_sum"] / METRICS["req_total"]) if METRICS["req_total"] else 0.0
        data = dict(METRICS)
        data["lat_avg_ms"] = round(avg * 1000, 2)
        data["lat_max_ms"] = round(METRICS["lat_max"] * 1000, 2)
        data["err_rate"] = round(METRICS["req_err"] / METRICS["req_total"], 4) if METRICS["req_total"] else 0.0
    return resp(0, "metrics", data)


if __name__ == "__main__":
    threading.Thread(target=_run_ws_server, daemon=True).start()
    time.sleep(0.5)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
