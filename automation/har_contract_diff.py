"""
MiniMall 接口契约回归 —— HAR 契约 diff（测开抓包进阶）

把抓包产物 capture.har 当成"接口契约快照"：
  - 首次运行：抽取每个 /api 路由的响应字段结构（字段名 + 类型），生成基线
    contract_baseline.json
  - 后续运行：与基线对比，报告 新增字段 / 删除字段 / 类型变化
      * 删除字段、类型变化 = breaking change（退出码 1）
      * 新增字段 = 警告（非 breaking，退出码 0）

价值：后端偷偷改接口字段（如 order_id 改名、price 由 number 变 string），
抓包 diff 立刻报警，比人工比对 HAR 高效得多。可直接接 pytest / CI。

用法：
  python automation/har_contract_diff.py                # 用默认 capture.har
  python automation/har_contract_diff.py --har x.har --baseline y.json
"""
import os
import sys
import json
import argparse


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAR = os.path.join(ROOT, "automation", "capture.har")
BASELINE = os.path.join(ROOT, "automation", "contract_baseline.json")


def _type_of(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "dict"
    return "unknown"


def _schema_of(obj):
    """从响应 JSON 抽取字段 -> 类型 的契约"""
    if not isinstance(obj, dict):
        return {}
    schema = {}
    for k, v in obj.items():
        if k == "data" and isinstance(v, dict):
            # data 内再展开一层（Order/User 对象），其余按类型记
            schema[k] = {"__type__": "dict", "fields": _schema_of(v)}
        else:
            schema[k] = _type_of(v)
    return schema


def _extract_routes(har_path):
    """返回 {method+path: schema}"""
    with open(har_path, encoding="utf-8") as f:
        har = json.load(f)
    routes = {}
    for e in har.get("log", {}).get("entries", []):
        req = e.get("request", {})
        resp = e.get("response", {})
        url = req.get("url", "")
        # 只关心 /api 路由
        if "/api/" not in url:
            continue
        # 去掉 query 用 path 归一
        path = url.split("?")[0]
        if path.startswith("http"):
            path = "/" + path.split("/", 3)[-1] if path.count("/") >= 3 else path
        method = req.get("method", "GET")
        key = "%s %s" % (method, path)
        try:
            body = json.loads(resp.get("content", {}).get("text", "") or "{}")
        except Exception:
            continue
        # 实际业务数据在 data 字段内
        data = body.get("data") if isinstance(body, dict) else None
        routes[key] = _schema_of(data if data is not None else body)
    return routes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--har", default=HAR)
    ap.add_argument("--baseline", default=BASELINE)
    args = ap.parse_args()

    if not os.path.exists(args.har):
        print("ERROR: 未找到 HAR: %s（请先跑 run_mitm_capture.py 生成）" % args.har)
        return 2

    current = _extract_routes(args.har)

    if not os.path.exists(args.baseline):
        with open(args.baseline, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        print("✅ 首次运行：已生成契约基线 -> %s" % args.baseline)
        print("   覆盖路由数: %d" % len(current))
        for k in current:
            print("   - %s" % k)
        return 0

    with open(args.baseline, encoding="utf-8") as f:
        base = json.load(f)

    breaking = []
    warnings = []
    for key in set(base) | set(current):
        if key not in current:
            breaking.append("删除路由: %s" % key)
            continue
        if key not in base:
            warnings.append("新增路由: %s" % key)
            continue
        b_fields = base[key]
        c_fields = current[key]
        # 顶层字段对比
        for fld in set(b_fields) | set(c_fields):
            if fld not in c_fields:
                breaking.append("%s 删除字段: %s" % (key, fld))
            elif fld not in b_fields:
                warnings.append("%s 新增字段: %s" % (key, fld))
            else:
                bt, ct = b_fields[fld], c_fields[fld]
                if isinstance(bt, dict) and isinstance(ct, dict):
                    # data 内逐字段对比
                    bf = bt.get("fields", {})
                    cf = ct.get("fields", {})
                    for sub in set(bf) | set(cf):
                        if sub not in cf:
                            breaking.append("%s.data 删除字段: %s" % (key, sub))
                        elif sub not in bf:
                            warnings.append("%s.data 新增字段: %s" % (key, sub))
                        elif bf[sub] != cf[sub]:
                            breaking.append("%s.data 字段 %s 类型变化: %s -> %s"
                                            % (key, sub, bf[sub], cf[sub]))
                elif bt != ct:
                    breaking.append("%s 字段 %s 类型变化: %s -> %s" % (key, fld, bt, ct))

    print("\n===== HAR 契约 diff =====")
    print("当前路由数: %d | 基线路由数: %d" % (len(current), len(base)))
    if breaking:
        print("❌ Breaking changes (%d):" % len(breaking))
        for b in breaking:
            print("   - %s" % b)
    if warnings:
        print("⚠️  非破坏性变更 (%d):" % len(warnings))
        for w in warnings:
            print("   - %s" % w)
    if not breaking and not warnings:
        print("✅ 契约完全一致，无字段增删/类型变化")

    return 1 if breaking else 0


if __name__ == "__main__":
    sys.exit(main())
