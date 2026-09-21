#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""normalize.py — 规格归一化 / 单价换算 / 同款指纹聚合（P0-3）

能力：
- spec "330ml*24罐" -> {"capacity_ml":330,"unit":"罐","count":24,"spec_key":"330mlx24罐"}
- 支持单位别名：毫升/ML/ml、瓶/罐/听/支/盒/包/袋/箱/片/卷、克/g/kg、升/L
- per-price 计算每单位价（元/罐、元/升、元/100g）
- fingerprint 生成跨平台同款指纹：品牌关键词 + 品名 + 规格键
- dedupe 对采集结果按指纹聚合：同款合并，标注最低价行与去重后行数

用法示例：
  python normalize.py spec "可口可乐330ml*24罐"
  python normalize.py per-price 22.42 "330ml*24罐"
  python normalize.py dedupe results.json
"""
import argparse
import json
import re
import sys

# 单位归一化表
VOLUME_ML = {"ml": 1.0, "毫升": 1.0, "l": 1000.0, "升": 1000.0}
WEIGHT_G = {"g": 1.0, "克": 1.0, "kg": 1000.0, "千克": 1000.0, "公斤": 1000.0}
COUNT_UNIT = {"瓶", "罐", "听", "支", "盒", "包", "袋", "箱", "片", "卷", "杯", "条", "个", "件", "桶", "板", "扎"}

STOP_WORDS = ["官方旗舰店", "旗舰店", "专卖店", "专营店", "自营", "官方", "正品", "包邮", "批发",
              "整箱", "促销", "特价", "新品", "爆款", "秒杀", "直营", "企业店", "工厂店", "现货",
              "领券", "到手", "优惠", "礼盒", "组合装", "迷你", "mini", "小瓶", "大瓶",
              "新人价", "新客价", "首单减", "免运费", "补贴", "立减", "减", "券", "险",
              "经典", "矮罐", "听装", "罐装", "瓶装", "囤货", "便携", "多口味", "原味",
              "整提", "超级", "即将恢复", "授权", "源头", "整箱装", "装", "件", "包", "箱",
              "元", "本周", "上新", "好评", "超", "价", "口径", "满", "广东", "易拉罐", "主题",
              "混合", "礼金", "京东", "淘宝", "拼多多", "天天特卖", "工厂", "家庭", "每",
              "旗舰", "自营", "小店", "供应", "好食", "第", "工厂店", "企业", "期"]


def norm_spec(spec_text):
    """把规格文本转成结构化 + 规范化键。返回 dict。"""
    t = (spec_text or "").lower().strip()
    t = re.sub(r"[x×*＊]", "x", t)  # 统一乘号
    t = re.sub(r"\s+", "", t)
    capacity_ml, weight_g, count, unit = None, None, None, ""

    m = re.search(r"(\d+(?:\.\d+)?)(ml|毫升|l|升)", t)
    if m:
        capacity_ml = float(m.group(1)) * VOLUME_ML[m.group(2)]
        t = t.replace(m.group(0), "", 1)
    m = re.search(r"(\d+(?:\.\d+)?)(g|克|kg|千克|公斤)", t)
    if m:
        weight_g = float(m.group(1)) * WEIGHT_G[m.group(2)]
        t = t.replace(m.group(0), "", 1)
    m = re.search(r"(\d+)\s*(瓶|罐|听|支|盒|包|袋|箱|片|卷|杯|条|个|件|桶|板|扎)", t)
    if m:
        count = int(m.group(1))
        unit = m.group(2)
        t = t.replace(m.group(0), "", 1)

    # 组合成规范键：容量优先（ml），否则重量（g），否则仅件数
    if capacity_ml:
        amount = "{}ml".format(int(capacity_ml) if capacity_ml == int(capacity_ml) else capacity_ml)
    elif weight_g:
        amount = "{}g".format(int(weight_g) if weight_g == int(weight_g) else weight_g)
    else:
        amount = ""
    spec_key = (amount + ("x" + str(count) + unit if count else "")).strip("x")
    return {"capacity_ml": capacity_ml, "weight_g": weight_g,
            "count": count, "unit": unit, "spec_key": spec_key or (spec_text or "").strip()[:30]}


def per_unit_price(price, spec_text):
    """算每单位价：优先 元/容量(升 或 100g)，其次 元/件。"""
    s = norm_spec(spec_text)
    if price is None:
        return None, "无法计算"
    p = float(price)
    if s["capacity_ml"]:
        return round(p / (s["capacity_ml"] * (s["count"] or 1) / 1000.0), 3), "元/升"
    if s["weight_g"]:
        return round(p / (s["weight_g"] * (s["count"] or 1) / 100.0), 3), "元/100g"
    if s["count"]:
        return round(p / s["count"], 3), "元/" + (s["unit"] or "件")
    return None, "无法计算"


def normalize_title(title):
    """规范化标题：转小写、去促销/店铺词、去规格片段，得到同款指纹核心。"""
    t = (title or "").lower().strip()
    t = re.sub(r"[\s\-—_]+", "", t)
    # 去掉规格片段
    t = re.sub(r"\d+(?:\.\d+)?(ml|毫升|l|升|g|克|kg|千克|公斤)", "", t)
    t = re.sub(r"\d+(瓶|罐|听|支|盒|包|袋|箱|片|卷|杯|条|个|件|桶|板|扎)", "", t)
    t = re.sub(r"\d+(?:\.\d+)?%?", "", t)          # 清掉剩余数字与百分比
    t = re.sub(r"[x×*＊/]+", "", t)  # 清掉规格片段残留的乘号/斜杠
    for w in STOP_WORDS:
        t = t.replace(w, "")
    # 清掉孤立单字残留（如 后/且/每/价）
    parts = [p for p in re.split(r"([\u4e00-\u9fff]+)", t) if p]
    t = "".join(p if not re.fullmatch(r"[\u4e00-\u9fff]", p) else "" for p in parts)
    t = re.sub(r"[【】\[\]()（）·,，。.!！]", "", t)
    return t.strip()[:60]


def fingerprint(title, spec_text, platform=None, item_id=None):
    """生成商品指纹。平台+item_id 为唯一主键；跨平台同款指纹 = 规范化标题 + 规格键。"""
    core = normalize_title(title) + "|" + norm_spec(spec_text)["spec_key"]
    return core


def cmd_spec(args):
    print(json.dumps(norm_spec(args.text), ensure_ascii=False))


def cmd_per_price(args):
    price, unit = per_unit_price(args.price, args.spec)
    print(json.dumps({"price": args.price, "spec": args.spec, "unit_price": price, "unit": unit},
                     ensure_ascii=False))


def cmd_fingerprint(args):
    print(json.dumps({"fingerprint": fingerprint(args.title, args.spec)}, ensure_ascii=False))


def confidence_score(title_a, title_b, spec_key_a="", spec_key_b=""):
    """同款匹配置信度 0-100。

    规则（参考 Taobao Price Compare 的匹配评分思路）：
    - 规格键一致（且非空）：基础分 80，同款候选；
    - 规范化标题（去规格/促销词后的核心）字符级相似度 s ∈ [0,1]：
      核心词完全一致 +15；高度重叠（≥0.6）+10；部分重叠（≥0.3）0；弱重叠 -10；
    - 规格键存在但不一致：-15（规格不同不算同款）；
    - 标题核心词完全无重叠且规格不一致：≤ 40，判定"仅参考"。
    返回 (score, grade, reason)。grade: 同款(≥80) / 近似款(60-79) / 仅参考(<60)
    """
    ca = normalize_title(title_a)
    cb = normalize_title(title_b)
    if not ca or not cb:
        return 45, "仅参考", "标题过短，无法判断"

    same_spec = bool(spec_key_a and spec_key_b and spec_key_a == spec_key_b)
    has_spec = bool(spec_key_a or spec_key_b)

    # 字符级 Jaccard 相似度
    sa, sb = set(ca), set(cb)
    inter = len(sa & sb)
    union = len(sa | sb) or 1
    sim = inter / union

    score = 50
    if same_spec:
        score = 80
    if sim >= 0.99 and len(ca) >= 2:
        score += 15
    elif sim >= 0.6:
        score += 10
    elif sim >= 0.3:
        score += 0
    else:
        score -= 10
    if has_spec and not same_spec:
        score -= 15
    if not has_spec and sim < 0.4:
        score -= 10

    score = max(0, min(100, score))
    grade = "同款" if score >= 80 else ("近似款" if score >= 60 else "仅参考")
    reason = []
    if same_spec:
        reason.append("规格键一致")
    elif has_spec:
        reason.append("规格键不一致")
    if sim >= 0.99:
        reason.append("标题核心一致")
    elif sim >= 0.6:
        reason.append("标题高度相似")
    elif sim >= 0.3:
        reason.append("标题部分相似")
    else:
        reason.append("标题差异较大")
    return score, grade, "；".join(reason)


def cmd_confidence(args):
    score, grade, reason = confidence_score(args.title_a, args.title_b,
                                            args.spec_key_a or "", args.spec_key_b or "")
    print(json.dumps({"confidence": score, "grade": grade, "reason": reason,
                      "title_a_norm": normalize_title(args.title_a),
                      "title_b_norm": normalize_title(args.title_b)}, ensure_ascii=False))


def cmd_dedupe(args):
    with open(args.file, "r", encoding="utf-8") as f:
        results = json.load(f)
    # 输入行字段：title, price, spec(可选), platform, item_id, shop, url, 其他
    by_fp = {}
    for r in results:
        spec_text = r.get("spec") or r.get("spec_norm") or ""
        fp = fingerprint(r.get("title", ""), spec_text, r.get("platform"), r.get("item_id"))
        key = fp
        if key not in by_fp:
            by_fp[key] = {"fingerprint": key, "title": r.get("title", ""), "spec_key": norm_spec(spec_text)["spec_key"],
                          "offers": []}
        by_fp[key]["offers"].append(r)
    groups = []
    for fp, g in by_fp.items():
        g["offers"].sort(key=lambda o: float(o.get("price") or 9e18))
        for i, o in enumerate(g["offers"]):
            o["_rank_in_group"] = i + 1
            o["_is_lowest"] = (i == 0)
        low = g["offers"][0]
        g["lowest"] = {"price": low.get("price"), "platform": low.get("platform"),
                       "shop": low.get("shop"), "url": low.get("url")}
        g["offer_count"] = len(g["offers"])
        groups.append(g)
    groups.sort(key=lambda g: g["lowest"]["price"] if isinstance(g["lowest"]["price"], (int, float)) else 9e18)
    out = {"groups": len(groups), "offers_total": len(results), "deduped": len(results) - len(groups), "groups_data": groups}
    print(json.dumps(out, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="规格归一化 / 单价换算 / 指纹去重")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("spec")
    p1.add_argument("text")
    p1.set_defaults(func=cmd_spec)

    p2 = sub.add_parser("per-price")
    p2.add_argument("price", type=float)
    p2.add_argument("spec")
    p2.set_defaults(func=cmd_per_price)

    p3 = sub.add_parser("fingerprint")
    p3.add_argument("--title", required=True)
    p3.add_argument("--spec", required=True)
    p3.set_defaults(func=cmd_fingerprint)

    p4 = sub.add_parser("dedupe")
    p4.add_argument("file")
    p4.set_defaults(func=cmd_dedupe)

    p5 = sub.add_parser("confidence")
    p5.add_argument("--title-a", required=True)
    p5.add_argument("--title-b", required=True)
    p5.add_argument("--spec-key-a", default="")
    p5.add_argument("--spec-key-b", default="")
    p5.set_defaults(func=cmd_confidence)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
