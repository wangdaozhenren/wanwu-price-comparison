#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_report.py — 万物比价·日报（内部运维推送脚本）

内容：各应用使用量 / 成交与佣金 / 用药助手付费 / 合计
数据源（任一失败自动降级标注，不编造数字）：
  1. 转链服务 /stats          各技能 src 使用量（union_config.json worker.api_token）
  2. 聚推客 /union/orders     成交数量 + 预估佣金（昨日/周末/本周/本月）
  3. drug-helper /api/stats   用药助手付费笔数/金额/买断数
推送：Server酱（data/config.json serverchan_sendkey）

用法：
  python daily_report.py report [--dry-run]   --dry-run 只打印不推送
周一自动覆盖周末（周五~周日），其余日期统计昨日。
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
UNION_CONFIG_PATH = os.path.join(DATA_DIR, "union_config.json")

UNION_STATS_URL = "https://union-convert-tbxkbskpjy.cn-hangzhou.fcapp.run/stats"
DRUG_STATS_URL = "https://drug-helper-tciuozgdun.cn-hangzhou.fcapp.run/api/stats"

# src slug -> 显示名（与各技能 union_config.json 的 src 一致）
SRC_NAMES = {
    "waimai": "外卖助手", "jiudian": "酒店助手", "meishi": "美食券助手",
    "dianying": "电影助手", "dache": "打车助手", "kuaidi": "快递助手",
    "quanwang": "全网购物助手", "tushu": "图书助手", "yaopin": "药品健康助手",
    "jiazheng": "家政助手", "jianshen": "健身助手", "zufang": "租房助手",
    "jiaoyu": "教育助手", "chongzhi": "充值助手", "jipiao": "机票助手",
    "yanchu": "演出票务助手", "yongyao": "用药助手", "chongwu": "宠物助手",
    "shuma": "3C数码家电助手", "meizhuang": "美妆个护助手", "xianzhi": "二手闲置助手",
    "juyu": "剧愈", "wanwu": "万物比价", "shuyu": "书愈", "yingyu": "影愈",
}


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def http_get_json(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0 (daily-report)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_union_stats(api_token, date_str):
    """转链服务按日使用量：{src: count}"""
    try:
        r = http_get_json(f"{UNION_STATS_URL}?date={date_str}",
                          headers={"X-API-Token": api_token})
        if not r.get("ok"):
            return {"error": r.get("error", "unknown")}
        return {a["app"]: a["count"] for a in r.get("apps", [])}
    except Exception as e:
        return {"error": str(e)}


def fetch_drug_stats(date_str):
    """用药助手后端按日付费统计，返回 dict 或 {'error': ...}"""
    try:
        r = http_get_json(f"{DRUG_STATS_URL}?date={date_str}")
        if r.get("status") != "ok":
            return {"error": r.get("error", "unknown")}
        return r
    except Exception as e:
        return {"error": str(e)}


def fetch_jutuike_orders(apikey, start, end):
    params = urllib.parse.urlencode({"apikey": apikey, "start_time": start, "end_time": end, "page": 1, "pageSize": 100})
    url = "http://api.jutuike.com/union/orders?" + params
    try:
        r = http_get_json(url)
    except Exception as e:
        return {"error": str(e)}
    if r.get("code") not in (0, 1):
        return {"error": r.get("msg", "unknown")}
    data = r.get("data") or []
    if isinstance(data, dict):
        data = data.get("data") or []
    total = len(data)
    commission = 0.0
    valid = 0
    details = []
    for o in data:
        fee = float(o.get("jtk_share_fee") or o.get("share_fee") or 0)
        commission += fee
        vc = o.get("validCode") or o.get("valid_code")
        if str(vc) in ("16", "17"):
            valid += 1
        name = o.get("skuName") or o.get("short_title") or o.get("goodsName") or "未知商品"
        price = o.get("price") or o.get("pay_price") or ""
        details.append({"name": str(name)[:40], "price": price, "fee": fee, "time": o.get("orderTime") or ""})
    return {"total": total, "valid": valid, "commission": round(commission, 2), "details": details}


def send_serverchan(sendkey, title, desp):
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    body = json.dumps({"title": title, "desp": desp}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def period_dates(now):
    """返回统计周期日期列表（datetime，升序）。周一覆盖周五~周日，其余为昨日。"""
    if now.weekday() == 0:
        days = [now - timedelta(days=d) for d in (3, 2, 1)]
    else:
        days = [now - timedelta(days=1)]
    return days


def period_label(days):
    if len(days) == 1:
        return days[0].strftime("%m月%d日")
    return f"{days[0].strftime('%m月%d')}-{days[-1].strftime('%d日')}·周末"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["report"])
    ap.add_argument("--dry-run", action="store_true", default=False)
    args = ap.parse_args()

    cfg = load_json(CONFIG_PATH)
    union_cfg = load_json(UNION_CONFIG_PATH)
    sendkey = cfg.get("serverchan_sendkey")
    jtk_apikey = cfg.get("jutuike_apikey")
    api_token = (union_cfg.get("worker") or {}).get("api_token", "")
    if not sendkey:
        print("缺 serverchan_sendkey")
        sys.exit(1)

    now = datetime.now()
    days = period_dates(now)
    label = period_label(days)
    day_strs = [d.strftime("%Y-%m-%d") for d in days]
    start_dt = days[0].strftime("%Y-%m-%d 00:00:00")
    end_dt = now.strftime("%Y-%m-%d 00:00:00")
    yest_label = days[-1].strftime("%m月%d日")

    lines = [f"## 万物比价 · 日报（{label}）"]

    # ---------- 1. 各应用使用量 ----------
    lines.append("\n### 各应用使用量")
    usage_total = 0
    usage_map = {}
    usage_errors = []
    if api_token:
        for ds in day_strs:
            r = fetch_union_stats(api_token, ds)
            if "error" in r:
                usage_errors.append(f"{ds}: {r['error']}")
                continue
            for src, cnt in r.items():
                usage_map[src] = usage_map.get(src, 0) + cnt
                usage_total += cnt
    else:
        usage_errors.append("union_config.json 未配置 worker.api_token")
    if usage_map:
        ordered = sorted(usage_map.items(), key=lambda x: -x[1])
        for src, cnt in ordered:
            name = SRC_NAMES.get(src, f"未知({src})")
            lines.append(f"- {name}：{cnt} 次")
        zero = [n for s, n in SRC_NAMES.items() if s not in usage_map]
        if zero:
            lines.append(f"- 其余 {len(zero)} 个技能：0 次")
        lines.append(f"- **合计：{usage_total} 次**")
    elif usage_errors:
        lines.append(f"- 转链服务使用量查询失败：{'；'.join(usage_errors[:2])}")

    # ---------- 2. 成交与佣金 ----------
    lines.append("\n### 成交与佣金")
    total_orders = 0
    total_commission = 0.0
    j_orders = 0
    j_fee = 0.0
    if jtk_apikey:
        j = fetch_jutuike_orders(jtk_apikey, start_dt, end_dt)
        if "error" in j:
            lines.append(f"- 聚推客查询失败：{j['error']}")
        else:
            j_orders = j["total"]
            j_fee = j["commission"]
            lines.append(f"- 周期内：{j_orders} 单 · 预估佣金 ¥{j_fee:.2f}（有效 {j['valid']} 单）")
            if j_orders == 0:
                lines.append("- 暂无订单")
            else:
                for i, d in enumerate(j["details"][:20], 1):
                    p = f" ¥{d['price']}" if d["price"] else ""
                    lines.append(f"{i}. {d['name']}{p} · 佣金 ¥{d['fee']:.2f}")
                if len(j["details"]) > 20:
                    lines.append(f"……等共 {len(j['details'])} 单")
            total_orders += j_orders
            total_commission += j_fee

            week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
            month_start = now.replace(day=1, hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
            jw = fetch_jutuike_orders(jtk_apikey, week_start, end_dt)
            jm = fetch_jutuike_orders(jtk_apikey, month_start, end_dt)
            lines.append(f"- 本周（7天）：{jw.get('total', 0)} 单 · ¥{jw.get('commission', 0):.2f}" if "error" not in jw else "- 本周查询失败")
            lines.append(f"- 本月：{jm.get('total', 0)} 单 · ¥{jm.get('commission', 0):.2f}" if "error" not in jm else "- 本月查询失败")
    else:
        lines.append("- 未配置聚推客 apikey")

    lines.append("\n### 分渠道")
    lines.append(f"- 聚推客：{j_orders} 单 · ¥{j_fee:.2f}" if jtk_apikey else "- 聚推客：未配置")
    lines.append("- 多多：待接入")
    lines.append("- 淘宝：待接入")
    lines.append("- 美团：待接入")
    lines.append("- 携程：待接入")

    # ---------- 3. 用药助手付费 ----------
    lines.append("\n### 用药助手付费")
    pay = {"count": 0, "amount": 0.0, "per_query_count": 0, "per_query_amount": 0.0,
           "buyout_count": 0, "buyout_amount": 0.0, "buyout_total": 0}
    pay_errors = []
    for ds in day_strs:
        r = fetch_drug_stats(ds)
        if "error" in r:
            pay_errors.append(f"{ds}: {r['error']}")
            continue
        for k in ("count", "per_query_count", "buyout_count"):
            pay[k] += int(r.get(k) or 0)
        for k in ("amount", "per_query_amount", "buyout_amount"):
            pay[k] += float(r.get(k) or 0)
        if r.get("buyout_total") is not None:
            pay["buyout_total"] = int(r["buyout_total"])
    if pay["count"] > 0 or not pay_errors:
        lines.append(f"- 付费笔数：{pay['count']} 笔（按次 {pay['per_query_count']} · 买断 {pay['buyout_count']}）")
        lines.append(f"- 付费金额：¥{pay['amount']:.2f}（按次 ¥{pay['per_query_amount']:.2f} · 买断 ¥{pay['buyout_amount']:.2f}）")
        lines.append(f"- 累计买断：{pay['buyout_total']} 笔")
    if pay_errors:
        lines.append(f"- 统计接口查询失败：{'；'.join(pay_errors[:2])}")

    # ---------- 4. 合计 ----------
    pay_amount = pay["amount"]
    lines.append("\n---")
    lines.append(f"**周期合计：成交 {total_orders} 单 · 佣金 ¥{total_commission:.2f} · 付费 {pay['count']} 笔 ¥{pay_amount:.2f}**")
    lines.append("> 实际结算以各渠道后台为准；未入住/退款订单不计；使用量为转链调用次数（冷启动可能低估）。")

    desp = "\n".join(lines)
    title = f"万物比价 · 日报（{label}）· {total_orders}单 ¥{total_commission:.2f} {pay['count']}笔"
    if len(title) > 32:
        title = f"万物比价 · 日报（{label}）"

    print(f"[dry-run] 标题({len(title)}字): {title}" if args.dry_run else f"标题({len(title)}字): {title}")
    print(f"[dry-run] 正文 {len(desp.encode('utf-8'))} 字节 / {len(lines)} 行" if args.dry_run else f"正文 {len(desp.encode('utf-8'))} 字节 / {len(lines)} 行")

    if args.dry_run:
        print("---- 正文预览 ----")
        print(desp)
        return

    res = send_serverchan(sendkey, title, desp)
    print(json.dumps({"title": title, "push": res}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
