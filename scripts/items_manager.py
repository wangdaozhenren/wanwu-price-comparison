#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""items_manager.py — 采购清单管理（万物比价 P0）

管理在追物品清单 data/items.json：
- add    添加物品（名称/预算/优先级/规格/平台/商品ID/目标价/图片说明）
- list   列出在追物品（含最近价格与趋势）
- archive 下架（归档）物品
- rm     彻底删除物品
- record 为某物品追加一条价格记录（check_watchlist 也调用）
- price  查询某物品最近价格记录

数据文件由 items.json 参数指定（默认 data/items.json，可在技能运行目录调用）。

items.json 结构（与采购比价跟踪技能的数据契约同构）：
{
  "items": [
    {
      "id": "uuid8",
      "name": "物品名称",
      "description": "描述",
      "spec": "330ml*24罐",
      "budget": 1000.0,
      "priority": "high",
      "platform": "jd",
      "item_id": "10100803635701",
      "url": "",
      "target_price": 500.0,
      "status": "active",
      "image_description": null,
      "created_at": "2026-09-17T10:00:00",
      "updated_at": "2026-09-17T10:00:00",
      "price_records": [{"date":"2026-09-17","price":899.0,"platform":"jd","url":"...","title":"..."}],
      "price_alerts": [{"date":"2026-09-17","type":"price_drop","message":"..."}]
    }
  ]
}

用法示例：
  python items_manager.py add data/items.json --name "可口可乐330ml*24罐" --budget 60 --priority high --spec "330ml*24罐" --platform jd
  python items_manager.py list data/items.json
  python items_manager.py record data/items.json --id <id> --price 52.9 --platform jd --url https://... --title "..."
  python items_manager.py archive data/items.json --id <id>
  python items_manager.py rm data/items.json --id <id>
  python items_manager.py price data/items.json --id <id>
"""
import argparse
import json
import os
import sys
import time
import uuid

DEFAULT_ITEMS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "items.json")


def _load(path):
    if not os.path.exists(path):
        return {"items": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _find(data, item_id):
    for it in data["items"]:
        if it["id"] == item_id:
            return it
    return None


def cmd_add(args):
    data = _load(args.file)
    it = {
        "id": uuid.uuid4().hex[:8],
        "name": args.name,
        "description": args.description or "",
        "spec": args.spec or "",
        "budget": args.budget,
        "priority": args.priority or "mid",
        "platform": args.platform or "",
        "item_id": args.item_id or "",
        "url": args.url or "",
        "target_price": args.target_price,
        "status": "active",
        "image_description": args.image_description or None,
        "created_at": _now(),
        "updated_at": _now(),
        "price_records": [],
        "price_alerts": [],
    }
    data["items"].append(it)
    _save(args.file, data)
    print(json.dumps({"ok": True, "id": it["id"], "name": it["name"],
                      "active_count": len([i for i in data["items"] if i["status"] == "active"])},
                     ensure_ascii=False))


def cmd_list(args):
    data = _load(args.file)
    items = data["items"]
    if args.status:
        items = [i for i in items if i["status"] == args.status]
    out = []
    for it in items:
        recs = it.get("price_records", [])
        latest = recs[-1] if recs else None
        prev = recs[-2] if len(recs) >= 2 else None
        trend = None
        if latest and prev:
            diff = float(latest["price"]) - float(prev["price"])
            trend = "up" if diff > 0.001 else ("down" if diff < -0.001 else "flat")
        out.append({
            "id": it["id"], "name": it["name"], "spec": it.get("spec", ""),
            "budget": it.get("budget"), "priority": it.get("priority"),
            "status": it["status"], "platform": it.get("platform", ""),
            "item_id": it.get("item_id", ""), "target_price": it.get("target_price"),
            "latest_price": latest["price"] if latest else None,
            "latest_date": latest["date"] if latest else None,
            "latest_platform": latest["platform"] if latest else None,
            "latest_url": latest["url"] if latest else None,
            "trend": trend, "records": len(recs),
            "alerts": it.get("price_alerts", [])[-3:],
        })
    print(json.dumps({"ok": True, "count": len(out), "items": out}, ensure_ascii=False))


def cmd_record(args):
    data = _load(args.file)
    it = _find(data, args.id)
    if not it:
        print(json.dumps({"ok": False, "error": "item not found: " + args.id}, ensure_ascii=False))
        sys.exit(1)
    rec = {"date": args.date or time.strftime("%Y-%m-%d"), "price": args.price,
           "platform": args.platform or it.get("platform", ""), "url": args.url or "",
           "title": args.title or it["name"]}
    it.setdefault("price_records", []).append(rec)
    # 裁剪保留最近 90 条
    it["price_records"] = it["price_records"][-90:]
    it["updated_at"] = _now()
    _save(args.file, data)
    print(json.dumps({"ok": True, "id": it["id"], "records": len(it["price_records"]),
                      "latest": rec}, ensure_ascii=False))


def cmd_archive(args):
    data = _load(args.file)
    it = _find(data, args.id)
    if not it:
        print(json.dumps({"ok": False, "error": "item not found: " + args.id}, ensure_ascii=False))
        sys.exit(1)
    it["status"] = "archived"
    it["updated_at"] = _now()
    _save(args.file, data)
    print(json.dumps({"ok": True, "id": it["id"], "status": "archived"}, ensure_ascii=False))


def cmd_rm(args):
    data = _load(args.file)
    before = len(data["items"])
    data["items"] = [i for i in data["items"] if i["id"] != args.id]
    _save(args.file, data)
    print(json.dumps({"ok": True, "removed": before - len(data["items"])}, ensure_ascii=False))


def cmd_price(args):
    data = _load(args.file)
    it = _find(data, args.id)
    if not it:
        print(json.dumps({"ok": False, "error": "item not found: " + args.id}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps({"ok": True, "id": it["id"], "name": it["name"],
                      "price_records": it.get("price_records", [])[-90:]},
                     ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="采购清单管理（万物比价）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_common(p):
        p.add_argument("file", nargs="?", default=DEFAULT_ITEMS, help="items.json 路径")

    p1 = sub.add_parser("add")
    add_common(p1)
    p1.add_argument("--name", required=True)
    p1.add_argument("--description", default="")
    p1.add_argument("--spec", default="")
    p1.add_argument("--budget", type=float, default=None)
    p1.add_argument("--priority", choices=["high", "mid", "low"], default="mid")
    p1.add_argument("--platform", default="")
    p1.add_argument("--item-id", default="")
    p1.add_argument("--url", default="")
    p1.add_argument("--target-price", type=float, default=None)
    p1.add_argument("--image-description", default=None, help="图片识别出的物品描述")
    p1.set_defaults(func=cmd_add)

    p2 = sub.add_parser("list")
    add_common(p2)
    p2.add_argument("--status", choices=["active", "archived"], default="active")
    p2.set_defaults(func=cmd_list)

    p3 = sub.add_parser("record")
    add_common(p3)
    p3.add_argument("--id", required=True)
    p3.add_argument("--price", type=float, required=True)
    p3.add_argument("--platform", default="")
    p3.add_argument("--url", default="")
    p3.add_argument("--title", default="")
    p3.add_argument("--date", default="")
    p3.set_defaults(func=cmd_record)

    p4 = sub.add_parser("archive")
    add_common(p4)
    p4.add_argument("--id", required=True)
    p4.set_defaults(func=cmd_archive)

    p5 = sub.add_parser("rm")
    add_common(p5)
    p5.add_argument("--id", required=True)
    p5.set_defaults(func=cmd_rm)

    p6 = sub.add_parser("price")
    add_common(p6)
    p6.add_argument("--id", required=True)
    p6.set_defaults(func=cmd_price)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
