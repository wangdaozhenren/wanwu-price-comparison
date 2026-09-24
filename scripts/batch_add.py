#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""batch_add.py — 将 results.json 批量写入 price_history.jsonl"""
import json, os, sys, argparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 技能根目录（相对定位，不写死本机路径）
sys.path.insert(0, os.path.join(BASE, "scripts"))
import price_history as ph
from normalize import per_unit_price as _pup

def per_unit(price, spec_norm):
    up, _u = _pup(price, spec_norm)
    return up

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("history")
    ap.add_argument("--region", default="深圳")
    args = ap.parse_args()

    with open(args.results, "r", encoding="utf-8") as f:
        rows = json.load(f)
    ok = 0
    for r in rows:
        spec = r.get("spec") or ""
        up = per_unit(r["price"], spec)
        rec = ph.cmd_add(
            argparse.Namespace(
                file=args.history,
                platform=r["platform"],
                item_id=r["item_id"],
                title=r["title"],
                spec_norm=spec,
                price=r["price"],
                price_type="补贴后/页面价" if "补贴" in (r.get("note") or "") or "新人价" in (r.get("note") or "") else "页面价",
                unit_price=up,
                region=args.region,
                fetched_at=None,
                url=r.get("url", ""),
                shop=r.get("shop", ""),
                fingerprint="coke-330ml-24cans",
            )
        )
        ok += 1
        print(r["platform"], r["item_id"], r["price"], up)
    print("TOTAL ADDED:", ok)

if __name__ == "__main__":
    main()
