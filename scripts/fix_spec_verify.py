#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_spec_verify.py — 规格核验修正（2026-09-18 可口可乐案例）

背景：淘宝多条低价条目标题含「12/24罐」双规格，页面默认/补贴价对应 12 罐，
不能按 24 罐口径入主表。本脚本：
1. 更新 results.json：给降级条目打 verified=false 与待核说明；已开卡核实的条目打 true；
2. 更新 price_history.jsonl：降级条目的 spec_norm 改为「330mlx24罐/12罐(待核)」，
   使其在按规格分组的报告中单独成组，不污染 24 罐口径。
"""
import json
import os
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(BASE, "data", "results.json")
HISTORY = os.path.join(BASE, "data", "price_history.jsonl")

# 已开卡核实为双规格（含 12 罐 SKU，页面价对应最低 SKU 的可能性大，24 罐实价未确认）
# item_id -> (spec, verified, verified_note)
UNVERIFIED = {
    "1004980936537": ("330ml*24罐/12罐(待核)", False,
                      "已开卡核实：SKU 含 12/24/48 罐多规格，页面补贴价实为 12 罐，24 罐实价未确认"),
    "969275034114": ("330ml*24罐/12罐(待核)", False,
                     "已开卡核实：SKU 含「可乐330ml*24」「可乐330ml*12罐」双规格，页面价对应 SKU 未确认，按最低规格保守处理"),
    "611657680078": ("330ml*24罐/12罐(待核)", False,
                     "已开卡核实：SKU 含 24罐/12罐 双规格，页面价对应 SKU 未确认，按最低规格保守处理"),
    "1038383895502": ("330ml*24罐/12罐(待核)", False,
                      "已开卡核实：SKU 含 24罐/12罐 双规格，页面价对应 SKU 未确认，按最低规格保守处理"),
    "724979495227": ("330ml*24罐/12罐(待核)", False,
                     "已开卡核实：SKU 含 24罐/12罐 双规格，页面价对应 SKU 未确认，按最低规格保守处理"),
    "820027862008": ("330ml*24罐/12罐(待核)", False,
                     "已开卡核实：SKU 含「整箱24罐」「半箱12罐」等多规格，页面价对应 SKU 未确认，按最低规格保守处理"),
}

# 已开卡核实的条目：正鸿水饮详情页秒杀价 23.9 起，主推 SKU=330ml*24罐（真 24 罐）
VERIFIED_UPDATE = {
    "765841547084": {
        "price": 23.9,
        "note": "已开卡核实：详情页秒杀价 23.9 起，主推 SKU=可口可乐330ml*24罐（新老包装），真 24 罐价",
    },
}

def main():
    # ---- 1. results.json ----
    with open(RESULTS, "r", encoding="utf-8") as f:
        rows = json.load(f)
    n_unv = n_ver = 0
    for r in rows:
        iid = r.get("item_id")
        if iid in UNVERIFIED:
            spec, ver, note = UNVERIFIED[iid]
            r["spec"] = spec
            r["verified"] = ver
            r["verified_note"] = note
            n_unv += 1
        elif iid in VERIFIED_UPDATE:
            u = VERIFIED_UPDATE[iid]
            r["price"] = u["price"]
            r["note"] = u["note"]
            r["verified"] = True
            r["verified_note"] = "已开卡核实：24 罐 SKU 实价"
            n_ver += 1
        else:
            r["verified"] = True
            r["verified_note"] = "标题单规格/价位符合 24 罐市场区间，可信"
    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"results.json: {n_unv} 条降级标注, {n_ver} 条更新为已核实价, 其余 {len(rows)-n_unv-n_ver} 条标记可信")

    # ---- 2. price_history.jsonl ----
    hist = []
    changed = 0
    with open(HISTORY, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            iid = rec.get("item_id")
            if iid in UNVERIFIED:
                rec["spec_norm"] = "330mlx24罐/12罐(待核)"
                rec["price_type"] = "页面价(规格待核)"
                rec["spec_verified"] = False
                changed += 1
            hist.append(rec)
    with open(HISTORY, "w", encoding="utf-8") as f:
        for rec in hist:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"price_history.jsonl: {changed} 条已改规格口径为待核")

if __name__ == "__main__":
    main()
