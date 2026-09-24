#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notifier.py — 多渠道推送（万物比价 P0）

把报告/提醒文本推送到用户配置的渠道：
- serverchan（Server酱 → 微信）：https://sctapi.ftqq.com/<SENDKEY>.send
- pushplus（PushPlus → 微信）：https://www.pushplus.plus/send
- email（SMTP 邮箱）：smtplib

配置来源：--config data/config.json（channels 字段），或直接命令行传参。
config.json 结构见 assets/items.example.json 旁附的说明，channels 示例：
{
  "channels": {
    "serverchan": {"enabled": false, "sendkey": ""},
    "pushplus": {"enabled": false, "token": ""},
    "email": {"enabled": false, "smtp_host": "", "smtp_port": 465,
              "sender": "", "password": "", "receivers": []}
  },
  "alert_threshold": 5
}

用法示例：
  python notifier.py push --title "比价报告" --content "..." --channel all --config data/config.json
  python notifier.py push --title "盯价提醒" --content-file report.txt --channel serverchan --sendkey xxx
  python notifier.py status --config data/config.json
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.parse

DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "config.json")


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _http_post(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode("utf-8"),
                                 headers={"User-Agent": "Mozilla/5.0 wanwu-price-comparison"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", "ignore")[:500]
    except Exception as e:
        return "ERR:" + str(e)


def push_serverchan(sendkey, title, content):
    url = "https://sctapi.ftqq.com/{}.send".format(sendkey)
    return _http_post(url, {"title": title[:32], "desp": content})


def push_pushplus(token, title, content):
    return _http_post("https://www.pushplus.plus/send",
                      {"token": token, "title": title, "content": content, "template": "markdown"})


def push_email(cfg, title, content):
    import smtplib
    from email.mime.text import MIMEText
    from email.header import Header
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = Header(title, "utf-8")
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(cfg["receivers"])
    port = int(cfg.get("smtp_port", 465))
    if port == 465:
        s = smtplib.SMTP_SSL(cfg["smtp_host"], port, timeout=20)
    else:
        s = smtplib.SMTP(cfg["smtp_host"], port, timeout=20)
        s.starttls()
    s.login(cfg["sender"], cfg["password"])
    s.sendmail(cfg["sender"], cfg["receivers"], msg.as_string())
    s.quit()
    return "sent"


def cmd_status(args):
    cfg = _load_json(args.config, {})
    ch = cfg.get("channels", {})
    out = {"ok": True, "configured": []}
    for name in ("serverchan", "pushplus", "email"):
        c = ch.get(name) or {}
        enabled = bool(c.get("enabled"))
        out["configured"].append({"channel": name, "enabled": enabled})
    print(json.dumps(out, ensure_ascii=False))


def cmd_push(args):
    cfg = _load_json(args.config, {})
    ch = cfg.get("channels", {})
    content = args.content
    if args.content_file:
        with open(args.content_file, "r", encoding="utf-8") as f:
            content = f.read()
    if content is None:
        print(json.dumps({"ok": False, "error": "缺少内容（--content 或 --content-file）"}, ensure_ascii=False))
        sys.exit(1)

    results = {}
    channels = (args.channel or "").split(",")
    for name in channels:
        name = name.strip()
        if name == "all":
            names = ["serverchan", "pushplus", "email"]
        else:
            names = [name]
        for n in names:
            c = ch.get(n) or {}
            if n == "serverchan":
                sk = args.sendkey or c.get("sendkey")
                if not sk:
                    results[n] = "not_configured"
                    continue
                results[n] = push_serverchan(sk, args.title, content)
            elif n == "pushplus":
                tk = args.token or c.get("token")
                if not tk:
                    results[n] = "not_configured"
                    continue
                results[n] = push_pushplus(tk, args.title, content)
            elif n == "email":
                c2 = c
                if not c2.get("enabled") or not c2.get("smtp_host"):
                    results[n] = "not_configured"
                    continue
                try:
                    results[n] = push_email(c2, args.title, content)
                except Exception as e:
                    results[n] = "ERR:" + str(e)
            else:
                results[n] = "unknown_channel"
    print(json.dumps({"ok": True, "title": args.title, "results": results}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="多渠道推送（Server酱 / PushPlus / SMTP）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("status")
    p1.add_argument("--config", default=DEFAULT_CONFIG)
    p1.set_defaults(func=cmd_status)
    p2 = sub.add_parser("push")
    p2.add_argument("--title", required=True)
    p2.add_argument("--content", default=None)
    p2.add_argument("--content-file", default=None)
    p2.add_argument("--channel", default="all", help="serverchan,pushplus,email 或 all")
    p2.add_argument("--sendkey", default=None)
    p2.add_argument("--token", default=None)
    p2.add_argument("--config", default=DEFAULT_CONFIG)
    p2.set_defaults(func=cmd_push)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
