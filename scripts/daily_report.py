#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""commission_daily.py — 每日佣金聚合日报（内部脚本，对使用者透明）"""
import argparse, json, os, sys, urllib.request, urllib.parse
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

def load_config():
    if not os.path.exists(CONFIG_PATH): return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f: return json.load(f)

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def fetch_jutuike_orders(apikey, start, end):
    params = urllib.parse.urlencode({"apikey": apikey, "start_time": start, "end_time": end, "page": 1, "pageSize": 100})
    url = "http://api.jutuike.com/union/orders?" + params
    try:
        r = http_get(url)
    except Exception as e:
        return {"error": str(e)}
    if r.get("code") not in (0, 1):
        return {"error": r.get("msg", "unknown")}
    data = r.get("data") or []
    if isinstance(data, dict): data = data.get("data") or []
    total = len(data); commission = 0.0; valid = 0; details = []
    for o in data:
        fee = float(o.get("jtk_share_fee") or o.get("share_fee") or 0)
        commission += fee
        vc = o.get("validCode") or o.get("valid_code")
        if str(vc) in ("16","17"): valid += 1
        name = o.get("skuName") or o.get("short_title") or o.get("goodsName") or "未知商品"
        price = o.get("price") or o.get("pay_price") or ""
        details.append({"name": str(name)[:40], "price": price, "fee": fee, "time": o.get("orderTime") or ""})
    return {"total": total, "valid": valid, "commission": round(commission, 2), "details": details}

def send_serverchan(sendkey, title, desp):
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    body = json.dumps({"title": title, "desp": desp}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["report"])
    ap.add_argument("--days", type=int, default=1)
    args = ap.parse_args()
    cfg = load_config()
    sendkey = cfg.get("serverchan_sendkey")
    jtk_apikey = cfg.get("jutuike_apikey")
    if not sendkey: print("缺 serverchan_sendkey"); sys.exit(1)
    now = datetime.now()
    end_str = now.strftime("%Y-%m-%d %H:%M:%S")
    yest_start = (now - timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    yest_end = now.strftime("%Y-%m-%d 00:00:00")
    yest_label = (now - timedelta(days=1)).strftime("%m月%d日")
    week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
    month_start = now.replace(day=1, hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"## 万物比价 · 佣金日报（{yest_label}）\n"]
    total_orders = 0; total_commission = 0.0

    lines.append("### 昨日明细")
    j_orders = 0; j_fee = 0.0
    if jtk_apikey:
        j = fetch_jutuike_orders(jtk_apikey, yest_start, yest_end)
        if "error" in j:
            lines.append(f"- 聚推客查询失败：{j['error']}")
        else:
            j_orders = j["total"]; j_fee = j["commission"]
            if j_orders == 0:
                lines.append("- 昨日暂无订单")
            else:
                for i, d in enumerate(j["details"][:20], 1):
                    p = f" ¥{d['price']}" if d["price"] else ""
                    lines.append(f"{i}. {d['name']}{p} · 佣金 ¥{d['fee']:.2f}")
            total_orders += j_orders; total_commission += j_fee
    else:
        lines.append("- 未配置聚推客 apikey")

    lines.append("\n### 累计")
    if jtk_apikey:
        jw = fetch_jutuike_orders(jtk_apikey, week_start, end_str)
        jm = fetch_jutuike_orders(jtk_apikey, month_start, end_str)
        lines.append(f"- 本周（7天）：{jw.get('total',0)} 单 · ¥{jw.get('commission',0):.2f}" if "error" not in jw else "- 本周查询失败")
        lines.append(f"- 本月：{jm.get('total',0)} 单 · ¥{jm.get('commission',0):.2f}" if "error" not in jm else "- 本月查询失败")
    else:
        lines.append("- 未配置")

    lines.append("\n### 分渠道")
    lines.append(f"- 聚推客：{j_orders} 单 · ¥{j_fee:.2f}" if jtk_apikey else "- 聚推客：未配置")
    lines.append("- 携程：待接入")
    lines.append("- 拼多多：待接入")
    lines.append(f"\n---\n**昨日合计：{total_orders} 单 · 预估佣金 ¥{total_commission:.2f}**")
    lines.append("\n> 实际结算以各渠道后台为准；未入住/退款订单不计")
    desp = "\n".join(lines)
    title = f"佣金日报 {yest_label} · {total_orders}单 ¥{total_commission:.2f}"
    res = send_serverchan(sendkey, title, desp)
    print(json.dumps({"title": title, "push": res}, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()