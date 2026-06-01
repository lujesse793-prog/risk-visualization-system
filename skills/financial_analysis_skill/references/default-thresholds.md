# 默认风险阈值配置

默认阈值分为三档：`watch`（关注）、`warning`（预警）、`serious`（严重）。

风险映射：

- `watch` -> `risk_level=low`, `finding_type=warning_signal`
- `warning` -> `risk_level=medium`, `finding_type=warning_signal`
- `serious` -> 证据完整时 `risk_level=high`, `finding_type=confirmed_risk`
- `serious` 但缺少真实 `source_document_id`、`evidence_text`、`page/table_id` 时，降级为 `warning_signal` 或 `data_limitation`

## 默认阈值

| 指标 | watch | warning | serious | 方向 |
| --- | ---: | ---: | ---: | --- |
| `asset_liability_ratio` | >=70 | >=75 | >=85 | high |
| `cash_short_debt_ratio` | <1.0 | <0.5 | <0.3 | low |
| `current_ratio` | <1.2 | <1.0 | <0.7 | low |
| `quick_ratio` | <1.0 | <0.8 | <0.5 | low |
| `revenue_yoy` | <=-10 | <=-20 | <=-40 | low |
| `net_profit_yoy` | <=-20 | <=-40 | <=-60 | low |
| `net_cash_flow_from_operating_activities_yoy` | <=-20 | <=-40 | <=-60 | low |
| `short_term_debt_ratio` | >=40 | >=60 | >=75 | high |
| `operating_cash_flow_to_short_debt` | <0.5 | <0.3 | <0 | low |
| `other_receivables_to_total_assets` | >=15 | >=25 | >=35 | high |
| `inventory_to_total_assets` | >=25 | >=40 | >=50 | high |

## 连续为负规则

| 指标 | watch | warning | serious |
| --- | --- | --- | --- |
| `net_cash_flow_from_operating_activities` | 当期为负 | 连续两期为负 | 连续三期为负 |
| `net_profit` | 当期为负 | 连续两期为负 | 连续三期为负 |

## 自定义阈值

可通过 `thresholds_config` 覆盖默认阈值：

```json
{
  "thresholds_config": {
    "asset_liability_ratio": {
      "watch": 70,
      "warning": 75,
      "serious": 85,
      "direction": "high"
    }
  }
}
```
