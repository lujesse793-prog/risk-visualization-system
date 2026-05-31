# Financial Fields

Extract sourced data from annual reports, semiannual reports, quarterly reports, prospectuses, and rating reports. Quarterly report data may only enter `supplemental_financial_tables` unless `quarterly_report_used_for_analysis=true`. Normalize all monetary fields to `亿元`; keep percentages to two decimals; use `—` when unavailable.

## Cell-Level Source Metadata

Preserve source metadata for each data point whenever possible:

```json
{
  "value": "",
  "unit": "亿元",
  "source_title": "",
  "source_url": "",
  "page": "",
  "table_name": "",
  "raw_text": ""
}
```

Use at least `source_title` and `source_url` when page number is unavailable.

## Balance Sheet

Required fields:

```json
[
  "货币资金",
  "交易性金融资产",
  "应收账款",
  "其他应收款",
  "存货",
  "一年内到期的非流动资产",
  "流动资产合计",
  "长期股权投资",
  "固定资产",
  "在建工程",
  "无形资产",
  "非流动资产合计",
  "资产总计",
  "短期借款",
  "应付账款",
  "其他应付款",
  "一年内到期的非流动负债",
  "流动负债合计",
  "长期借款",
  "应付债券",
  "长期应付款",
  "非流动负债合计",
  "负债合计",
  "所有者权益合计"
]
```

## Income Statement

Required fields:

```json
[
  "营业收入",
  "营业成本",
  "税金及附加",
  "销售费用",
  "管理费用",
  "研发费用",
  "财务费用",
  "其他收益",
  "投资收益",
  "公允价值变动收益",
  "资产减值损失",
  "信用减值损失",
  "营业利润",
  "利润总额",
  "净利润",
  "归属于母公司所有者的净利润"
]
```

## Cash Flow Statement

Required fields:

```json
[
  "经营活动现金流入小计",
  "经营活动现金流出小计",
  "经营活动产生的现金流量净额",
  "投资活动现金流入小计",
  "投资活动现金流出小计",
  "投资活动产生的现金流量净额",
  "筹资活动现金流入小计",
  "筹资活动现金流出小计",
  "筹资活动产生的现金流量净额",
  "现金及现金等价物净增加额"
]
```

## Business Segments

Extract from annual reports, prospectuses, or rating reports when available:

```json
{
  "业务板块": "",
  "收入金额": "",
  "收入占比": "",
  "毛利率": "",
  "同比变化": "",
  "数据来源": ""
}
```

Leave `毛利率` or `同比变化` blank when unavailable.

## Indicator Formulas

Calculate from annual and semiannual data only:

```json
{
  "资产负债率": "负债合计 / 资产总计",
  "流动比率": "流动资产合计 / 流动负债合计",
  "现金短债比": "货币资金 / (短期借款 + 一年内到期的非流动负债)",
  "短期有息债务占比": "(短期借款 + 一年内到期的非流动负债) / (短期借款 + 一年内到期的非流动负债 + 长期借款 + 应付债券)",
  "营业收入同比变动": "本期营业收入 / 上期营业收入 - 1",
  "净利润同比变动": "本期净利润 / 上期净利润 - 1",
  "经营性净现金流/营业收入": "经营活动产生的现金流量净额 / 营业收入",
  "财务费用率": "财务费用 / 营业收入"
}
```

Rules:

1. If a denominator is missing or zero, output `无法计算`.
2. Do not estimate missing indicators.
3. Do not use quarterly data for formal indicator conclusions.
4. Compare semiannual reports with the previous year's same semiannual period.
5. Compare annual reports with the previous full year.
6. Do not directly compare semiannual data with full-year data for year-on-year analysis.
