---
name: financial_analysis_skill
description: 中国城投/发债企业贷后财务数据分析。接收已结构化抽取的财务数据（structured_financial_data、field_evidence），计算偿债能力、盈利能力、现金流、债务结构、资本结构等指标，根据阈值生成可追溯的风险提示和审慎分析文字。仅分析上游已结构化的数据，不搜索公告、不下载/解析PDF、不OCR、不抽取PDF表格。触发词：贷后分析、财务数据分析、城投财务分析、发债企业财务分析、偿债能力分析、财务指标计算、风险发现。
---

# 城投/发债企业贷后财务数据分析

## 定位

`financial_analysis_skill` 是贷后分析流程中的第4个环节，负责**基于已结构化的财务数据**计算指标、发现风险、生成分析摘要。

### 输入

| 字段 | 说明 |
|------|------|
| `task_id` | 任务ID |
| `enterprise_name` | 企业名称 |
| `analysis_context` | 分析上下文（企业类型、期间、分析日期等） |
| `structured_financial_data` | 已标准化的财务报表数据 |
| `field_evidence` | 字段溯源证据 |
| `extraction_warnings` | 上游提取警告 |
| `source_documents` | 来源文档列表 |
| `thresholds_config` | 可选，自定义阈值配置 |

### 输出

| 字段 | 说明 |
|------|------|
| `financial_indicators` | 计算后的财务指标列表 |
| `negative_findings` | 风险发现列表 |
| `analysis_summary` | 分析摘要（含数据限制说明） |
| `frontend_financial_summary` | 前端展示用关键财务数据 |
| `unavailable_indicators` | 不可计算指标列表；非核心指标缺失只进入此字段和 validation warnings |
| `risk_level_summary` | 风险等级统计 |
| `validation_result` | 输出校验结果 |

## 职责边界（重要）

本 skill **只能**分析和计算，**不得**：

- 自行访问互联网
- 重新搜索公告
- 读取PDF文件
- 执行OCR
- 调用 Marker / Surya
- 从 PDF 抽取表格
- 猜测缺失数据
- 使用无来源证据的数据生成风险判断
- 使用行业均值替代缺失数据
- 在缺少必要字段时自行补数或推测

## 数据来源优先级

仅使用以下来源的数据：

1. `structured_financial_data` 中已标准化的数据
2. `field_evidence` 中有来源证据的数据
3. `source_documents` 中的文档 ID、PDF 名称、页码和表格引用

多来源冲突时的优先级：
1. `annual_report` > `semi_annual_report` > `quarterly_report` > `prospectus` > `rating_report`
2. `selected_main` 文档优先
3. `confidence=high` 优先
4. 正式财务报表优先
5. 冲突无法解决时，不计算相关指标，加入 `data_limitation`

## 使用方法

```bash
python scripts/run_analysis.py --input sample_input.json --output analysis_output.json
```

## 指标分类

- `debt_capacity` — 偿债能力
- `liquidity` — 流动性
- `profitability` — 盈利能力
- `cash_flow` — 现金流
- `debt_structure` — 债务结构
- `capital_structure` — 资本结构
- `growth` — 增长率
- `data_quality` — 数据质量

## 风险发现类型

- `confirmed_risk` — 确认风险（必须有 evidence_text、threshold、真实 source_document_id，且 page 或 table_id 至少一个非空）
- `warning_signal` — 预警信号
- `data_limitation` — 数据限制

## 字段 confidence 规则

- `confidence=low`：不得用于 `confirmed_risk`，只能用于 `warning_signal` 或 `data_limitation`
- 没有 `source_document_id`、`evidence_text`、`page/table_id`：不允许生成 `confirmed_risk`
- `source_refs` 必须是证据引用对象，不能是字段名字符串

## 数据缺失处理

1. 不报错中断
2. 不编造数据
3. 输出 `unavailable` 指标并注明原因
4. 仅核心指标缺失生成 `data_limitation` finding；非核心指标缺失进入 `unavailable_indicators`、`analysis_summary.data_limitation_note` 和 `validation_result.warnings`

## 计算精度要求

- 百分比指标：保留两位小数
- 倍数指标：保留两位小数
- 金额指标：统一为亿元，保留两位小数
- 同比指标：上期值为0或缺失时不得计算；上期值负数时标记 `formula_warning`
- 现金短债比：单位为“倍”，不得乘以100或输出为百分比
- 值不得为 NaN 或 Infinity

## 参考文档

| 文档 | 内容 |
|------|------|
| `references/indicator-formulas.md` | 所有指标的计算公式和所需字段 |
| `references/default-thresholds.md` | 城投/产业企业默认风险阈值 |
| `references/analysis-writing-rules.md` | 分析摘要撰写规范 |
| `references/output-schema.md` | 完整输出JSON Schema |

## 校验规则

见 `scripts/validate_analysis_output.py`，包括证据链、字段名、单位、核心指标缺失噪音和摘要措辞等增强校验规则。
