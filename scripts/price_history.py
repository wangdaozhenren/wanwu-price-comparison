#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""price_history.py — 比价历史存储模块（P0-1）

JSONL 追加写（每条一行为一次观测），主键 platform + item_id。
- add      追加一条观测；同一商品裁剪保留最近 90 条
- summary  汇总某商品：当前价 / 历史最低 / 中位 / 均值 / 记录数 / 首次与末次时间
- export   导出某商品走势 JSON（供 ECharts 折线图直接使用）

字段规范（与 references/price-history.md 一致）：
  platform, item_id, title, spec_norm, price, price_type, unit_price,
  region, fetched_at(ISO8601), url, shop, fingerprint

用法示例：
  python price_history.py add history.jsonl --platform jd --item-id 10100803635701 \
    --title "可口可乐330ml*24罐整箱" --spec-norm "330ml*24罐" --price 42.89 \
    --price-type 到手价 --unit-price 1.79 --region 深圳 \
    --url "https://item.jd.com/10100803635701.html" --shop "中粮良品会" \
    --fingerprint "coke-330ml-24cans"
  python price_history.py summary history.jsonl --platform jd --item-id 10100803635701
  python price_history.py export history.jsonl --platform jd --item-id 10100803635701 --days 90
"""
import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timezone, timedelta

MAX_RECORDS_PER_ITEM = 90  # 每商品保留最近 90 条，防膨胀
CST = timezone(timedelta(hours=8))


def now_iso():
    return datetime.now(CST).isoformat(timespec="seconds")


def _read_all(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # 容忍坏行，不中断
    return rows


def _write_all(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def cmd_add(args):
    rows = _read_all(args.file)
    key = (args.platform, args.item_id)
    record = {
        "platform": args.platform,
        "item_id": args.item_id,
        "title": args.title,
        "spec_norm": args.spec_norm or "",
        "price": float(args.price),
        "price_type": args.price_type or "页面价",
        "unit_price": float(args.unit_price) if args.unit_price else None,
        "region": args.region or "",
        "fetched_at": args.fetched_at or now_iso(),
        "url": args.url or "",
        "shop": args.shop or "",
        "fingerprint": args.fingerprint or "",
    }
    rows.append(record)
    # 只保留该主键最近 MAX_RECORDS_PER_ITEM 条（其他商品不受影响）
    same_key = [r for r in rows if r.get("platform") == key[0] and r.get("item_id") == key[1]]
    if len(same_key) > MAX_RECORDS_PER_ITEM:
        drop = same_key[:len(same_key) - MAX_RECORDS_PER_ITEM]
        drop_ids = {id(r) for r in drop}
        rows = [r for r in rows if id(r) not in drop_ids]
    _write_all(args.file, rows)
    n = len([r for r in rows if r.get("platform") == key[0] and r.get("item_id") == key[1]])
    print(json.dumps({"ok": True, "written": record["fetched_at"], "records_for_item": n}, ensure_ascii=False))


def cmd_summary(args):
    rows = [r for r in _read_all(args.file)
            if r.get("platform") == args.platform and r.get("item_id") == args.item_id]
    if not rows:
        print(json.dumps({"ok": False, "error": "no history for this item"}, ensure_ascii=False))
        sys.exit(1)
    rows.sort(key=lambda r: r["fetched_at"])
    prices = [r["price"] for r in rows]
    first, last = rows[0], rows[-1]
    out = {
        "ok": True,
        "platform": args.platform,
        "item_id": args.item_id,
        "title": last.get("title", ""),
        "spec_norm": last.get("spec_norm", ""),
        "records": len(rows),
        "first_fetched_at": first["fetched_at"],
        "last_fetched_at": last["fetched_at"],
        "current_price": last["price"],
        "current_price_type": last.get("price_type", ""),
        "history_low": min(prices),
        "history_median": round(statistics.median(prices), 2),
        "history_mean": round(statistics.mean(prices), 2),
        "history_high": max(prices),
        "price_types_seen": sorted({r.get("price_type", "") for r in rows}),
    }
    print(json.dumps(out, ensure_ascii=False))


def cmd_export(args):
    rows = [r for r in _read_all(args.file)
            if r.get("platform") == args.platform and r.get("item_id") == args.item_id]
    if not rows:
        print(json.dumps({"ok": False, "error": "no history for this item"}, ensure_ascii=False))
        sys.exit(1)
    rows.sort(key=lambda r: r["fetched_at"])
    if args.days:
        cutoff = datetime.now(CST) - timedelta(days=args.days)
        rows = [r for r in rows if datetime.fromisoformat(r["fetched_at"]) >= cutoff]
    if not rows:
        print(json.dumps({"ok": False, "error": "no records in window"}, ensure_ascii=False))
        sys.exit(1)
    prices = [r["price"] for r in rows]
    out = {
        "ok": True,
        "platform": args.platform,
        "item_id": args.item_id,
        "title": rows[-1].get("title", ""),
        "spec_norm": rows[-1].get("spec_norm", ""),
        "unit": "元",
        "dates": [r["fetched_at"][:10] for r in rows],
        "prices": prices,
        "history_low": min(prices),
        "history_median": round(statistics.median(prices), 2),
        "history_mean": round(statistics.mean(prices), 2),
        "current": prices[-1],
        "lowest_at": rows[prices.index(min(prices))]["fetched_at"][:10],
    }
    print(json.dumps(out, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="比价历史存储（JSONL）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("file")
    for name, req in [("--platform", True), ("--item-id", True), ("--title", True),
                      ("--price", True), ("--spec-norm", False), ("--price-type", False),
                      ("--unit-price", False), ("--region", False), ("--fetched-at", False),
                      ("--url", False), ("--shop", False), ("--fingerprint", False)]:
        p_add.add_argument(name, required=req)
    p_add.set_defaults(func=cmd_add)

    p_sum = sub.add_parser("summary")
    p_sum.add_argument("file")
    p_sum.add_argument("--platform", required=True)
    p_sum.add_argument("--item-id", required=True)
    p_sum.set_defaults(func=cmd_summary)

    p_exp = sub.add_parser("export")
    p_exp.add_argument("file")
    p_exp.add_argument("--platform", required=True)
    p_exp.add_argument("--item-id", required=True)
    p_exp.add_argument("--days", type=int, default=90)
    p_exp.set_defaults(func=cmd_export)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
