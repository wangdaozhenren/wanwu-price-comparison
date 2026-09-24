#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""link_helper.py — 优惠链接生成

把「商品关键词 / 活动 / 原始链接」转成「可直接打开的优惠链接」，供推荐时使用。

工作方式：
- 京东 / 拼多多 / 淘宝（选品转链）、美团（活动会场）：调用统一优惠链接服务的
  公开接口完成；本脚本不持有、也不需要任何密钥或 token。
- 携程：本地附加公开优惠参数（allianceid / sid），无需调用转链服务。
- 美团具体单店/单品、淘宝具体单品：以服务端当前实际能力为准，不支持时如实返回，
  绝不伪造链接。

安全模型：技能包内不含任何 appSecret / token；平台签名密钥只存在于服务端。

命令：
  ping                                              检查优惠链接服务是否可达
  status                                            查看本地配置与服务状态
  search  --platform jd|pdd|taobao --keyword 词     按关键词查询候选商品
  acts    [--page N] [--page-size N]                查询美团/饿了么活动会场
  convert --platform jd|pdd|taobao|meituan|ctrip
          [--keyword 词] [--goods-id ID] [--act-id ID] [--url 链接]
                                                   生成单个优惠链接
  enrich  --results results.json                    批量：读结果集，逐条生成优惠链接
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error

TIMEOUT = 25
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def load_config(path):
    if not os.path.exists(path):
        return {"worker": {}}
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _base(cfg):
    return (cfg.get("worker") or {}).get("url", "").rstrip("/")


def _slug(cfg):
    """技能标识，用于转链服务的调用统计；仅传技能标识，不含用户个人信息。"""
    return cfg.get("slug") or cfg.get("src") or ""


def _request(method, url, obj=None, params=None, timeout=TIMEOUT):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    data = json.dumps(obj).encode("utf-8") if obj is not None else None
    hdr = {"User-Agent": _UA}
    if obj is not None:
        hdr["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return {"ok": False, "http_error": e.code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------- 携程：本地拼公开参数 ----------
def _ctrip_url(cfg, url):
    c = cfg.get("ctrip") or {}
    aid, sid = c.get("alliance_id"), c.get("sid")
    if not aid or not sid or not url:
        return ""
    sep = "&" if "?" in url else "?"
    return url + sep + "allianceid=" + str(aid) + "&sid=" + str(sid)


# ---------- 命令 ----------
def cmd_ping(args):
    cfg = load_config(args.config)
    base = _base(cfg)
    if not base:
        print(json.dumps({"ok": False, "error": "worker_url_missing"}, ensure_ascii=False))
        return
    print(json.dumps(_request("GET", base + "/p/ping"), ensure_ascii=False))


def cmd_status(args):
    cfg = load_config(args.config)
    base = _base(cfg)
    out = {"worker_url_set": bool(base), "slug": _slug(cfg),
           "ctrip_local": bool((cfg.get("ctrip") or {}).get("alliance_id"))}
    if base:
        p = _request("GET", base + "/p/ping", timeout=10)
        out["service_reachable"] = bool(p.get("ok"))
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_search(args):
    cfg = load_config(args.config)
    base = _base(cfg)
    if not base:
        print(json.dumps({"ok": False, "error": "worker_url_missing"}, ensure_ascii=False))
        return
    o = {"platform": args.platform, "keyword": args.keyword, "slug": _slug(cfg),
         "page_no": args.page, "page_size": args.page_size}
    print(json.dumps(_request("POST", base + "/p/search", obj=o),
                     ensure_ascii=False, indent=1))


def cmd_acts(args):
    cfg = load_config(args.config)
    base = _base(cfg)
    if not base:
        print(json.dumps({"ok": False, "error": "worker_url_missing"}, ensure_ascii=False))
        return
    o = {"page_no": args.page, "page_size": args.page_size, "slug": _slug(cfg)}
    print(json.dumps(_request("POST", base + "/p/acts", obj=o),
                     ensure_ascii=False, indent=1))


def cmd_convert(args):
    cfg = load_config(args.config)
    # 携程：本地拼参数，不调用服务
    if args.platform == "ctrip":
        link = _ctrip_url(cfg, args.url)
        print(json.dumps({"ok": bool(link), "platform": "ctrip", "link": link,
                          "via": "local_param" if link else None,
                          "error": None if link else "ctrip_need_url"},
                         ensure_ascii=False, indent=1))
        return
    base = _base(cfg)
    if not base:
        print(json.dumps({"ok": False, "error": "worker_url_missing"}, ensure_ascii=False))
        return
    o = {"platform": args.platform, "slug": _slug(cfg)}
    if args.keyword:
        o["keyword"] = args.keyword
    if args.goods_id:
        o["goods_id"] = args.goods_id
    if args.act_id:
        o["act_id"] = str(args.act_id)
    if args.url:
        o["url"] = args.url
    print(json.dumps(_request("POST", base + "/p/convert", obj=o),
                     ensure_ascii=False, indent=1))


def cmd_enrich(args):
    cfg = load_config(args.config)
    base = _base(cfg)
    with open(args.results, "r", encoding="utf-8-sig") as f:
        rows = json.load(f)
    out = []
    for r in rows:
        platform = r.get("platform")
        row = dict(r)
        if platform == "ctrip":
            link = _ctrip_url(cfg, r.get("url", ""))
            row["link"] = link
            row["ok"] = bool(link)
        else:
            o = {"platform": platform, "slug": _slug(cfg)}
            for k_src, k_dst in (("keyword", "keyword"), ("goods_id", "goods_id"),
                                 ("act_id", "act_id"), ("url", "url")):
                if r.get(k_src):
                    o[k_dst] = r[k_src]
            res = _request("POST", base + "/p/convert", obj=o) if base else {"ok": False}
            row["link"] = res.get("link")
            row["via"] = res.get("via")
            row["ok"] = bool(res.get("ok"))
            if not row["ok"]:
                row["error"] = res.get("error")
        out.append(row)
    print(json.dumps(out, ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser(description="优惠链接生成")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p0 = sub.add_parser("ping")
    p0.add_argument("--config", default="data/union_config.json")
    p0.set_defaults(func=cmd_ping)

    p1 = sub.add_parser("status")
    p1.add_argument("--config", default="data/union_config.json")
    p1.set_defaults(func=cmd_status)

    p2 = sub.add_parser("search")
    p2.add_argument("--config", default="data/union_config.json")
    p2.add_argument("--platform", required=True, choices=["jd", "pdd", "taobao"])
    p2.add_argument("--keyword", required=True)
    p2.add_argument("--page", type=int, default=1)
    p2.add_argument("--page-size", type=int, default=20)
    p2.set_defaults(func=cmd_search)

    p3 = sub.add_parser("acts")
    p3.add_argument("--config", default="data/union_config.json")
    p3.add_argument("--page", type=int, default=1)
    p3.add_argument("--page-size", type=int, default=20)
    p3.set_defaults(func=cmd_acts)

    p4 = sub.add_parser("convert")
    p4.add_argument("--config", default="data/union_config.json")
    p4.add_argument("--platform", required=True,
                    choices=["jd", "pdd", "taobao", "meituan", "ctrip"])
    p4.add_argument("--keyword")
    p4.add_argument("--goods-id")
    p4.add_argument("--act-id")
    p4.add_argument("--url")
    p4.set_defaults(func=cmd_convert)

    p5 = sub.add_parser("enrich")
    p5.add_argument("--config", default="data/union_config.json")
    p5.add_argument("--results", required=True)
    p5.set_defaults(func=cmd_enrich)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
