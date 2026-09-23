#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_watchlist.py — 盯价判定（万物比价 P0 升级）

兼容两种数据文件：
- items.json（推荐，采购清单格式，schema 见 assets/items.example.json）
- watchlist.json（旧格式 {"watch_items":[...]}，自动兼容）

判定规则（三级）：
1. 目标价命中：当前价 <= target_price → "已达目标价"；
2. 降幅阈值：较上一条价格记录，降价 >= alert_threshold% （默认5%）→ "降价提醒"；
   降价 >= 10% → "大幅降价"（10% 为内置硬阈值，可用 --big-drop-pct 覆盖）；
3. 促销动态：采集数据带 promo 标记（页面可见优惠券/限时促销/补贴）→ "促销动态"。

check 会顺带把本次价格写入 items.json 的 price_records（保留最近 90 条），
命中条目写入 price_alerts，实现数据契约闭环。

用法示例：
  python check_watchlist.py check data/items.json --prices '[{"platform":"jd","item_id":"10100803635701","price":39.9,"title":"可口可乐330ml*24罐","promo":"领券立减5元"}]'
  python check_watchlist.py init data/items.json
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
DEFAULT_ITEMS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "items.json")


def now_iso():
    return datetime.now(CST).isoformat(timespec="seconds")


def now_date():
    return datetime.now(CST).strftime("%Y-%m-%d")


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path, data):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _iter_targets(data):
    """把 items.json 或 watchlist.json 都归一成可迭代的目标条目。"""
    if "items" in data:  # 采购清单格式
        for it in data["items"]:
            if it.get("status") != "active":
                continue
            yield it, it
    elif "watch_items" in data:  # 旧 watchlist 格式
        for w in data["watch_items"]:
            yield w, w
    else:
        return


def cmd_check(args):
    data = _load_json(args.file, {"items": []})
    is_items = "items" in data
    if args.prices_file:
        prices = _load_json(args.prices_file, [])
    else:
        try:
            prices = json.loads(args.prices)
        except json.JSONDecodeError:
            print(json.dumps({"ok": False, "error": "prices 不是合法 JSON"}, ensure_ascii=False))
            sys.exit(1)

    idx = {}
    for p in prices:
        idx[(p.get("platform"), p.get("item_id"))] = p

    threshold = args.threshold  # 降幅阈值 %，默认 5
    big_drop = args.big_drop_pct  # 大幅降价阈值 %，默认 10

    hits, misses = [], []
    for item, w in _iter_targets(data):
        rec = {"id": item.get("id"), "name": item.get("name", w.get("name", "")),
               "platform": item.get("platform", w.get("platform")),
               "item_id": item.get("item_id", w.get("item_id")),
               "target_price": item.get("target_price", w.get("target_price"))}
        cur = idx.get((rec["platform"], rec["item_id"]))
        if cur is None:
            rec["status"] = "no_data"
            rec["alert"] = "本次未采到该条目价格，跳过。"
            misses.append(rec)
            continue
        price = cur.get("price")
        if price is None:
            rec["status"] = "no_data"
            misses.append(rec)
            continue
        price = float(price)
        rec["current_price"] = price
        rec["current_title"] = cur.get("title", "")

        records = item.get("price_records", [])
        last_rec = records[-1] if records else None
        last_price = float(last_rec["price"]) if last_rec and last_rec.get("price") is not None else None

        # 触发类型收集
        triggers = []
        target = rec["target_price"]
        if target is not None:
            if price <= float(target):
                triggers.append(("hit_target",
                                 "已达目标价：{name} 当前 {price} 元 ≤ 目标 {target} 元".format(
                                     name=rec["name"], price=price, target=target)))
            else:
                rec["gap"] = round(price - float(target), 2)
        if last_price is not None and last_price > 0:
            drop_pct = (last_price - price) / last_price * 100.0
            rec["last_price"] = last_price
            rec["drop_pct"] = round(drop_pct, 2)
            if drop_pct >= big_drop:
                triggers.append(("big_drop",
                                 "大幅降价：{name} 从 {last} 元降至 {price} 元（-{pct}%）".format(
                                     name=rec["name"], last=last_price, price=price, pct=round(drop_pct, 1))))
            elif drop_pct >= threshold:
                triggers.append(("price_drop",
                                 "降价提醒：{name} 从 {last} 元降至 {price} 元（-{pct}%）".format(
                                     name=rec["name"], last=last_price, price=price, pct=round(drop_pct, 1))))
        if cur.get("promo"):
            triggers.append(("promo", "促销动态：{name} 现价 {price} 元（{promo}）".format(
                name=rec["name"], price=price, promo=cur["promo"])))

        if triggers:
            rec["status"] = "hit"
            rec["trigger_types"] = [t[0] for t in triggers]
            rec["alert"] = "；".join(t[1] for t in triggers)
            hits.append(rec)
        else:
            rec["status"] = "miss"
            rec["alert"] = "未命中：{name} 当前 {price} 元，暂无降价触发。".format(name=rec["name"], price=price)
            misses.append(rec)

        # 数据契约闭环：写入价格记录与提醒（仅 items 格式）
        if is_items:
            new_rec = {"date": now_date(), "price": price, "platform": cur.get("platform"),
                       "url": cur.get("url", ""), "title": cur.get("title", rec["name"])}
            item.setdefault("price_records", []).append(new_rec)
            item["price_records"] = item["price_records"][-90:]
            item["updated_at"] = now_iso()
            for ttype, msg in triggers:
                item.setdefault("price_alerts", []).append(
                    {"date": now_date(), "type": ttype, "message": msg})

    if is_items:
        _save_json(args.file, data)

    out = {"ok": True, "checked_at": now_iso(), "target_total": len(list(_iter_targets(data))),
           "hits": hits, "misses": misses}
    print(json.dumps(out, ensure_ascii=False))


def cmd_init(args):
    """生成 items.json 骨架（空清单），不会覆盖已有文件。"""
    if os.path.exists(args.file):
        print(json.dumps({"ok": False, "error": "file already exists: " + args.file}, ensure_ascii=False))
        sys.exit(1)
    _save_json(args.file, {"items": []})
    print(json.dumps({"ok": True, "created": args.file}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="盯价判定（目标价 / 降幅阈值 / 促销动态）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("check")
    p1.add_argument("file", nargs="?", default=DEFAULT_ITEMS, help="items.json 或 watchlist.json")
    p1.add_argument("--prices", default="[]")
    p1.add_argument("--prices-file", default=None, help="当前价 JSON 数组文件路径（推荐）")
    p1.add_argument("--threshold", type=float, default=5.0, help="降幅提醒阈值，百分比数值，默认 5")
    p1.add_argument("--big-drop-pct", type=float, default=10.0, help="大幅降价阈值，百分比数值，默认 10")
    p1.set_defaults(func=cmd_check)
    p2 = sub.add_parser("init")
    p2.add_argument("file", nargs="?", default=DEFAULT_ITEMS)
    p2.set_defaults(func=cmd_init)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
