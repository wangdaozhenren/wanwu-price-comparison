# 历史价格存储（P0-1）

## 存储位置

技能运行目录下的 `data/price_history.jsonl`（JSONL：每行一条观测记录，追加写）。
多用户/多项目场景可换用 `data/<商品指纹前缀>/price_history.jsonl` 分目录。

## 记录字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| platform | str | 是 | jd / taobao / pdd / 1688 / dangdang 等 |
| item_id | str | 是 | 该平台商品 ID（京东 SKU、1688 offer id、拼多多 goods_id） |
| title | str | 是 | 采集时的商品标题 |
| spec_norm | str | 是 | 归一化规格，如 `330mlx24罐`（用 normalize.py spec 生成） |
| price | float | 是 | 数值价格（优先到手价） |
| price_type | str | 否 | 价格口径：页面价/到手价/券后价/会员价/批发价 |
| unit_price | float | 否 | 每单位价（元/升、元/罐），用 normalize.py per-price 计算 |
| region | str | 否 | 采集地区口径，如 深圳 |
| fetched_at | str | 是 | ISO8601（Asia/Shanghai），如 2026-09-16T20:15:00+08:00 |
| url | str | 否 | 商品链接（可点开核对） |
| shop | str | 否 | 店铺名 |
| fingerprint | str | 否 | 跨平台同款指纹（normalize.py fingerprint 生成） |

## 主键与裁剪

- 主键：`platform + item_id`，同一商品同一平台每次采集追加一条，不覆盖。
- 裁剪：每主键保留最近 **90 条**（`MAX_RECORDS_PER_ITEM`），超出丢弃最老记录，防止文件无限膨胀。
- 同一指纹（跨平台同款）在 `summary/export` 时按平台分别给出，报告层再聚合。

## 常用命令

```bash
# 追加一条（采集完成后立即调用）
python scripts/price_history.py add data/price_history.jsonl \
  --platform jd --item-id 10100803635701 --title "可口可乐330ml*24罐整箱" \
  --spec-norm "330mlx24罐" --price 42.89 --price-type 到手价 \
  --unit-price 1.79 --region 深圳 --url "https://item.jd.com/10100803635701.html" \
  --shop "中粮良品会" --fingerprint "可口可乐330mlx24罐"

# 汇总（当前价/历史最低/中位/均值）
python scripts/price_history.py summary data/price_history.jsonl \
  --platform jd --item-id 10100803635701

# 导出走势 JSON（供 ECharts 折线：dates/prices/history_low/current）
python scripts/price_history.py export data/price_history.jsonl \
  --platform jd --item-id 10100803635701 --days 90
```

## 报告接入

- 报告中"价格走势"区块渲染 export 的 JSON：折线 = dates×prices，另标注历史最低价横线与当前价点。
- 记录数 < 2 时显示"基线已建立（fetched_at），持续采集后出走势"，不渲染空折线、不编造历史。
- 首日即回填基线：技能第一次采集某商品时也执行一次 add，保证后续有对比起点。

## 口径规范

- 同一商品必须记录 price_type；跨价格口径比较时在报告备注注明（批发价 vs 到手价）。
- 价格变化可能因促销/券变化，不代表平台真实涨价——判断"先涨后降"至少需要同口径 3 个时间点。
- 采集频率建议：日常 1 次/日（由 cron 驱动）；大促期可临时提高到 1 次/小时并写备注。
