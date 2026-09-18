# 采购清单与盯价提醒（P0 升级版）

> 由单一 watchlist 升级为**采购清单**（items.json，多物品管理）。
> 兼容旧 watchlist.json（check_watchlist.py 自动识别两种格式）。
> 数据文件：`data/items.json`（脚本默认路径），示例见 `assets/items.example.json`。

## items.json 结构（数据契约）

```json
{
  "items": [
    {
      "id": "a1b2c3d4",
      "name": "可口可乐 330ml*24罐",
      "description": "给办公室囤的",
      "spec": "330ml*24罐",
      "budget": 60.0,
      "priority": "high",
      "platform": "jd",
      "item_id": "10100803635701",
      "url": "https://item.jd.com/10100803635701.html",
      "target_price": 52.0,
      "status": "active",
      "image_description": null,
      "created_at": "2026-09-17T10:00:00",
      "updated_at": "2026-09-17T10:00:00",
      "price_records": [
        {"date": "2026-09-17", "price": 55.9, "platform": "jd", "url": "https://...", "title": "可口可乐...24罐"}
      ],
      "price_alerts": [
        {"date": "2026-09-17", "type": "price_drop", "message": "降价提醒：..."}
      ]
    }
  ]
}
```

| 字段 | 说明 |
|---|---|
| id | 唯一标识（items_manager 自动生成 uuid8） |
| name / description | 名称与描述（图片录入时由 AI 识别自动填 name+spec） |
| spec | 规格文本（如 "330ml*24罐"），用于规格归一化与匹配 |
| budget | 预算（可选，超预算时报告提醒"超出预算"） |
| priority | high / mid / low |
| platform / item_id | 采集主键；url 便于回跳 |
| target_price | 目标价（命中即提醒"已达目标价"） |
| status | active / archived（下架归档） |
| price_records[] | 价格历史（自动裁剪最近 90 条） |
| price_alerts[] | 触发过的提醒记录（最近 3 条展示在清单列表） |

## 命令用法

```bash
# 添加物品（加入清单后立即执行一次比价，回填首条记录）
python scripts/items_manager.py add data/items.json \
  --name "可口可乐330ml*24罐" --spec "330ml*24罐" --budget 60 --priority high \
  --platform jd --item-id 10100803635701 --target-price 52

# 列出在追物品（含最近价格、趋势、近 3 条提醒）
python scripts/items_manager.py list data/items.json

# 追加价格记录（比价采集后调用）
python scripts/items_manager.py record data/items.json --id a1b2c3d4 --price 52.9 --platform jd --url https://...

# 下架 / 删除
python scripts/items_manager.py archive data/items.json --id a1b2c3d4
python scripts/items_manager.py rm data/items.json --id a1b2c3d4

# 查看某物品价格历史
python scripts/items_manager.py price data/items.json --id a1b2c3d4
```

## 盯价判定（check_watchlist.py，三级触发）

```bash
python scripts/check_watchlist.py check data/items.json \
  --prices '[{"platform":"jd","item_id":"10100803635701","price":49.9,"title":"可口可乐330ml*24罐","promo":"领券立减5元"}]'
```

| 触发 | 条件 | 提醒文案示例 |
|---|---|---|
| 已达目标价 | 当前价 ≤ target_price | "已达目标价：可口可乐 当前 49.9 元 ≤ 目标 52 元" |
| 降价提醒 | 较上次记录降价 ≥5%（可调 alert_threshold） | "降价提醒：从 55.9 降至 49.9（-10.7%）" |
| 大幅降价 | 降价 ≥10%（--big-drop-pct 可调） | "大幅降价：从 55.9 降至 49.9（-10.7%）" |
| 促销动态 | 采集数据带 promo 字段（页面可见券/促销） | "促销动态：现价 49.9 元（领券立减5元）" |

- check 顺带把本次价格写入 price_records、命中写入 price_alerts（数据契约闭环）。
- 未命中不打扰；未采到该条目时标记 no_data 跳过。

## 推送（notifier.py，多渠道）

```bash
# 查看已配置渠道
python scripts/notifier.py status --config data/config.json

# 推送到全部已配置渠道（Server酱/PushPlus/邮箱）
python scripts/notifier.py push --title "盯价提醒" --content-file report.txt --channel all --config data/config.json

# 单独指定渠道
python scripts/notifier.py push --title "比价报告" --content "..." --channel serverchan --sendkey xxx
```

config.json channels 结构见 SKILL.md 第四节与 assets/items.example.json 说明。

## 与定时任务（doubao-cron-scheduler）集成

1. 先 Read `doubao-cron-scheduler/SKILL.md`，按其规范创建 cron 任务。
2. 周期建议：日常 `0 9 * * *`（每天 9 点）；单日单商品采集不超过 8 次，避免风控。
3. cron 的 query 标准模板（{title} 为任务标题，必须原样替换）：

```
本次请求是由「{title}」定时任务到时触发的。请读取 data/items.json，对每个在追物品（status=active）用浏览器采集当前价，组装 --prices 调用 scripts/check_watchlist.py check 判定；命中条目（hits）整理成提醒文本，用 scripts/notifier.py push 按 data/config.json 配置推送（未配置渠道则直接发我）；生成当日比价小结发给我。未命中不打扰。
```

## 边界

- 只提醒不代下单；目标价与预算由用户设定。
- 平台登录态失效时：按 browser-use-automation 规则移交用户扫码后继续；用户不在场则本轮跳过并在下次提醒"有 N 条因登录未检查"。
- 不承诺"一定能抢到"：价格变化实时性以页面为准。
- 图片录入：用户传截图 → AI 识别名称+规格 → 用户确认后 add（识别结果不自信时让用户补文字）。
