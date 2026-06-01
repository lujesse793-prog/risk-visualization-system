# 财务指标计算公式

## 标准字段名

统一使用标准字段名；兼容旧别名：

- `current_assets` -> `total_current_assets`
- `current_liabilities` -> `total_current_liabilities`
- `owner_equity` -> `total_owner_equity`
- `net_operating_cash_flow` -> `net_cash_flow_from_operating_activities`
- `net_investing_cash_flow` -> `net_cash_flow_from_investing_activities`
- `net_financing_cash_flow` -> `net_cash_flow_from_financing_activities`

## 核心指标

| 指标 | 公式 | 单位 |
| --- | --- | --- |
| `asset_liability_ratio` | `total_liabilities / total_assets * 100` | `%` |
| `cash_short_debt_ratio` | `cash_and_cash_equivalents / short_term_interest_bearing_debt` | `倍` |
| `current_ratio` | `total_current_assets / total_current_liabilities` | `倍` |
| `quick_ratio` | `(total_current_assets - inventory) / total_current_liabilities` | `倍` |
| `interest_bearing_debt` | `short_term_borrowings + non_current_liabilities_due_within_one_year + long_term_borrowings + bonds_payable + long_term_payables` | `亿元` |
| `short_term_debt_ratio` | `short_term_interest_bearing_debt / interest_bearing_debt * 100` | `%` |
| `operating_cash_flow_to_short_debt` | `net_cash_flow_from_operating_activities / short_term_interest_bearing_debt` | `倍` |
| `revenue_yoy` | `本期 operating_revenue / 上期 operating_revenue - 1` | `%` |
| `net_profit_yoy` | `本期 net_profit / 上期 net_profit - 1` | `%` |
| `net_cash_flow_from_operating_activities_yoy` | `本期经营现金流净额 / 上期经营现金流净额 - 1` | `%` |

计算限制：

- `cash_short_debt_ratio` 不得乘以 100，不得输出 `%`。
- `quick_ratio` 必须有 `inventory`；缺失时不得计算。
- 同比指标上期值为 0 或缺失时不得计算；上期值为负数时必须写入 `formula_warning`。
- `interest_bearing_debt` 纳入 `long_term_payables` 时，`formula_warning` 写明：`长期应付款可能包含非债务性质款项，有息债务口径需结合附注确认。`

## 城投关键指标

| 指标 | 公式 | 单位 |
| --- | --- | --- |
| `other_receivables_to_total_assets` | `other_receivables / total_assets * 100` | `%` |
| `inventory_to_total_assets` | `inventory / total_assets * 100` | `%` |
| `capital_reserve_to_owner_equity` | `capital_reserve / total_owner_equity * 100` | `%` |
| `other_equity_instruments_to_owner_equity` | `other_equity_instruments / total_owner_equity * 100` | `%` |
| `net_cash_flow_to_net_profit` | `net_cash_flow_from_operating_activities / net_profit` | `倍` |
| `net_profit_margin` | `net_profit / operating_revenue * 100` | `%` |
| `gross_profit_margin` | `(operating_revenue - operating_cost) / operating_revenue * 100` | `%` |

## 证据链要求

每个 `indicator.input_fields[]` 至少包含：

```json
{
  "field_name": "",
  "standard_field_name": "",
  "period": "",
  "value": null,
  "unit": "亿元",
  "source_document_id": "",
  "source_pdf": "",
  "page": null,
  "table_id": "",
  "table_title": "",
  "raw_row": "",
  "raw_column": "",
  "evidence_text": "",
  "confidence": "high"
}
```

`source_refs` 必须是来自 `input_fields` 的证据引用对象，不能保存字段名字符串。
