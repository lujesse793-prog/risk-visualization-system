# 报告期与来源选择规则

先读 `source-policy.md` 和 `search-and-verification.md`。以下规则在文档已从三平台检索后适用。

## 主文件优先级

```
annual_report > semi_annual_report > quarterly_report > prospectus > rating_report
```

年度报告是主数据来源。不得用更新季报、募集说明书或评级报告替换已有的年度报告。

## 动态报告期门控

以 `run_date` 为基准。记 `run_date` 所在年份为 **Y**。

| 文件类型 | 新鲜度标准 |
|---|---|
| 财务报告（annual/semi/quarterly） | `report_period >= Y-1` 年 |
| 募集说明书、评级报告 | `publish_date >= Y-1-01-01` |

- 如果 `run_date` 在当年年报披露窗口期前（如 1-4 月），可允许 Y-2 年年报作为过渡性主文件，但必须在 `freshness_gate.transitional_fallback_used=true` 并记录 `data_limitation_note`
- `publish_date >= Y-1-01-01` 但 `report_period < Y-1` 年的财务报告 → `stale_or_prior_period_document`
- 三平台均无符合新鲜度标准的文档 → `pdf_handoff.no_latest_public_data=true`

**不得写死任何固定年份（如 2025）。**

## 选择规则

每平台：

1. 至少扫描前 30 条结果（如有）
2. 分类所有允许文件类型
3. 每类文件保留最新有效文件
4. 年报优先选为 `selected_main`
5. 更新季报选为 `selected_supplement`
6. 新鲜募集说明书和评级报告选为 `selected_supplement`
7. 记录所有跳过的文件及 `skipped_reason`
8. 如通用全名搜索前 30 条未找到年报，运行定向年报搜索（见 `search-and-verification.md`）

## 具体规则

1. 最新有效年报 → `selected_main`
2. 同时存在的更新季度报告 → `selected_supplement`
3. **不得因季度报告更新就停止搜索或跳过年报**
4. 无财务报告但有新鲜募集说明书/评级报告 → `selected_supplement`，不能伪装成完整财务报表来源
5. 三平台均无符合新鲜度标准的有效文件 → `no_latest_public_data=true`

## 报告期识别

本 skill 仅识别每个文件的 `report_period` 并记录在 `source_documents[]` 中。报告期展示和格式排列由后续 skill 决定。

## 季度报告

- 季度报告仅作为 `selected_supplement` 进入 `source_documents[]` 和 `pdf_handoff`
- 本 skill **不写入** `supplemental_financial_tables`（该字段必须为空）
- 是否解析季度财务数据、是否用于指标计算，由后续 PDF 解析 skill 和财务分析 skill 决定

## 募集说明书和评级报告

募集说明书和评级报告作为 `selected_supplement`，可提供以下补充信息：
- 企业概况、股东和实际控制人、主营业务
- 重大债务、对外担保
- 评级观点、风险提示
- 受限资产、有息债务结构

本 skill 不从中抽取财务字段——这些字段由后续 PDF 解析 skill 从文档中抽取。

## 过期文件处理

不符合动态新鲜度标准的历史文件（如 `report_period < Y-1` 年的财务报告）：
- 记录在 `source_documents[]`，`document_status=stale_or_prior_period_document`
- **不进入** `pdf_handoff.documents_needing_pdf_parse`
- 如三平台仅有过期文件，`no_latest_public_data=true`

## 回归测试示例

> 以下为回归测试示例（以 `run_date=2026-05-31` 为例，Y=2026），不作为通用报告期规则。

对「泰州医药城控股集团有限公司」，如检索结果含：
- 2025年年度报告（Y-1=2025，符合标准，2026-04-30 发布）
- 2026年一季度财务报表（Y-1=2025，符合标准，2026-04-30 发布）
- 「泰州东方中国医药城控股集团有限公司」2025年年度报告

必须：
1. 将「泰州医药城控股集团有限公司 2025年年度报告」选为 `selected_main`
2. 2026年一季度财报选为 `selected_supplement`
3. 「泰州东方中国医药城控股集团有限公司」文件必须验证历史名称关系后才能采用
4. 在 `search_log` 中记录所有信息

## 本 skill 不负责的事项

以下由后续 PDF 解析 skill 和财务分析 skill 负责，本 skill **不写入、不计算、不判断**：

- `financial_tables`：必须为空 `{}`
- `supplemental_financial_tables`：必须为空 `{}`
- `financial_indicators`：必须为空 `[]`
- `negative_findings`：必须为空 `[]`
- 财务指标计算、风险判断、负面事项识别