---
name: post-loan-analysis-report
description: Generate concise post-loan financial disclosure analysis for a named enterprise using only 中国货币网, 上海证券交易所, and 深圳证券交易所. Use this skill for 贷后分析, 贷后分析报告, 债券公开资料提取, 财务数据结构化, 年报/半年报/季报/募集说明书/评级报告解析, and latest public financial disclosure checks. It must prioritize annual reports over newer quarterly reports, download and parse PDFs instead of relying on snippets, verify historical or similar subject names, and return frontend-ready JSON with detailed search_log. Do not use for public-opinion monitoring, news analysis, business-registration lookup, automatic rating, credit approval advice, investment advice, full Word reports, or default probability prediction.
---

# Post-Loan Analysis Report

## Purpose

Produce a sourced, frontend-ready JSON object for one enterprise. The skill only does four things:

1. Retrieve latest public financial disclosure only from 中国货币网, 上海证券交易所, and 深圳证券交易所.
2. Download and parse only annual reports, semiannual reports, quarterly reports, prospectuses, and rating reports.
3. Use annual reports as the main financial analysis source, with semiannual and quarterly reports as supplements.
4. Generate a negative-information disclosure summary under 200 Chinese characters.

Never generate ratings, risk levels, credit approval advice, investment advice, default probability forecasts, public-opinion summaries, or a full post-loan Word report.

If the 3 allowed channels do not provide valid latest public financial disclosure, stop and output:

```text
未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。
```

## Inputs

Accept an enterprise full name and optional controls:

```json
{
  "enterprise_name": "企业全名",
  "report_period_preference": "latest",
  "max_results_per_channel": 30
}
```

Treat `enterprise_name` as required. Default `report_period_preference` to `latest` and `max_results_per_channel` to `30`.

## Workflow

1. Confirm the enterprise subject.
   - Use the full legal name as the primary identifier.
   - Read `references/search-and-verification.md` before searching.
   - Generate candidate names: full name, short name, bond issuer name, historical names, and highly similar names found in PDF titles.
   - Prefer exact-name files. Use historical or similar-name files only after same-subject verification through PDF cover page, issuer field, unified social credit code, bond issuer identity, or explicit historical-name relationship.
   - Record filtered files and `skipped_reason`.

2. Retrieve public materials only from the 3 allowed channels.
   - Read `references/source-policy.md` before retrieval.
   - Search only 中国货币网, 上海证券交易所, and 深圳证券交易所.
   - Do not search or use other websites, news, public opinion, business-registration pages, third-party aggregators, issuer websites, or unofficial reposts.
   - On 中国货币网, perform internal retrieval or equivalent ChinaMoney page/API retrieval; do not rely only on external `site:` search.
   - On each channel, scan at least the first 30 results when available.
   - Do not stop at the first result or the newest result.

3. Classify only the allowed file types.
   - `annual_report`: 年度报告, 年报, 年度财务报表, 年度审计报告, 经审计财务报告, 合并及母公司财务报表, 合并财务报表, 母公司财务报表, 审计报告, 财务报表及附注, 年度财务报表及附注.
   - `semi_annual_report`: 半年度报告, 半年报, 半年度财务报表.
   - `quarterly_report`: 第一季度报告, 一季度报告, 第一季度财务报表, 一季度财务报表, 第三季度报告, 三季度报告, 季度财务报表.
   - `prospectus`: 募集说明书, 更新募集说明书, 债券募集说明书, 中期票据募集说明书, 超短期融资券募集说明书.
   - `rating_report`: 主体评级报告, 债项评级报告, 跟踪评级报告, 信用评级报告, 评级报告.
   - Do not classify a standalone `评级结果公告` as `rating_report` unless a full rating-report PDF attachment exists; otherwise record it as `unsupported_file_type`.
   - Exclude付息公告、兑付公告、发行结果公告、持有人会议公告、法律意见书、受托管理事务报告、临时公告、发行方案、承诺函、普通说明公告、工商信息、新闻报道、舆情信息.
   - Exception: if a correction wrapper or attachment contains an allowed file type or `更正后文件`, open the attachment list and use the corrected formal PDF first.
   - If a generic `财务报表` title also contains 一季度、三季度、半年度, classify it as quarterly or semiannual, not annual.
   - If the first 30 generic full-name results contain no annual report, run directed annual-report searches for `{企业全名} 年度报告`, `{企业全名} 年报`, `{企业全名} 审计报告`, `{企业全名} 年度财务报表`, and `{企业全名} 合并及母公司财务报表`.

4. Download and parse PDFs.
   - Open detail pages or PDF links for matched results.
   - If a page has attachment PDFs, download the relevant PDF; do not judge by HTML snippets only.
   - Read the first page to confirm subject name.
   - Identify file type and report period.
   - For financial reports, use the file as latest financial data only when `report_period` is 2025 or later.
   - If `publish_date >= 2025-01-01` but the financial-report `report_period` is 2024 or earlier, record it as `stale_or_prior_period_document` and do not use it as the latest post-loan analysis main basis.
   - For prospectuses and rating reports, record the disclosed financial-data cutoff period.
   - Extract key balance sheet, income statement, and cash flow statement fields.
   - If table extraction fails, extract key financial fields from text.
   - If download succeeds but parsing fails, record `parse_failed_reason` in `search_log`.

5. Select analysis sources by priority.
   - Use `references/period-and-source-rules.md`.
   - Priority is: annual report > semiannual report > quarterly report > prospectus > rating report.
   - If a latest annual report exists, it must be used for main financial analysis.
   - Do not skip an annual report because a quarterly report was published later.
   - If both a 2026 first-quarter financial statement and a 2025 annual report exist, download and parse both; use the 2025 annual report as main analysis and the quarter as supplemental data.
   - Prospectuses and rating reports supplement enterprise profile, debt, guarantees, restricted assets, rating views, and risk warnings. They must not replace an available annual report.

6. Validate freshness.
   - Always output `source_policy`, `freshness_gate`, and enhanced `search_log`.
   - Trigger the freshness gate if the 3 channels do not produce any financial report with `report_period` 2025 or later and do not produce any prospectus or rating report published in 2025 or later.
   - When the freshness gate triggers, set `data_level=no_data`, leave all financial tables and indicators empty, and use the fixed no-data summary from `references/source-policy.md`.
   - Do not use 2024 or earlier files to generate latest post-loan analysis when no fresh document exists.

7. Extract and calculate.
   - Read `references/financial-fields.md` for required statement fields and indicator formulas.
   - Preserve cell-level source metadata for each financial data point whenever possible.
   - Normalize monetary amounts to `亿元`; keep percentages to two decimals.
   - Use `—` for unavailable values and never invent data.
   - Calculate only when numerator and denominator are available and denominator is nonzero.
   - Apply default negative indicator thresholds in `references/negative-thresholds.md`.

8. Identify negative facts only.
   - Read `references/negative-signals.md`.
   - Include only findings traceable to annual/semiannual financial data, prospectus, rating report, or a downloaded disclosure file on the 3 allowed channels.
   - Do not output public-opinion findings, positive commentary, or unsupported judgement.
   - Do not use quarterly reports as the main negative-analysis basis when `quarterly_report_used_for_analysis=false`.

9. Return strict JSON.
   - Read `references/output-schema.md` before producing the final object.
   - Always include `supplemental_financial_tables`.
   - Always include 3-entry `search_log` for 中国货币网, 上海证券交易所, and 深圳证券交易所.
   - Use `search_modes` as an array, for example `["内部检索", "页面检索", "附件检索", "PDF下载解析"]`.
   - Each `search_log` entry must include `query_runs`, a list recording every specific search performed on that platform; each run must include `matched_items` with item-level URLs and selected/skipped decisions.
   - If the first query run does not find an annual report, record all five directed annual-report queries from `references/search-and-verification.md`.
   - For each adopted file, record `title`, `attachment_title`, `file_type`, `report_period`, `publish_date`, `source_url`, `pdf_url`, `source_platform`, `entity_match_result`, `used_for_main_analysis`, and `used_as_supplement`.
   - Keep `negative_summary_under_200_chars` under 200 Chinese characters.
   - If valid financial data exists but no directly supported negative matter is identified, set `negative_findings=[]` and summary to `未识别到可由公开披露文件直接支持的重大负面事项。`
   - Run `python scripts/validate_output.py <output.json>` when a JSON file is produced locally.

## Data Rules

- All data must have a source.
- Financial data sources must come only from 中国货币网, 上海证券交易所, or 深圳证券交易所.
- Set `source_policy.allowed_announcement_sources_only=true` and `source_policy.external_financial_sources_used=false`.
- Do not retrieve public opinion, news, business-registration pages, third-party aggregators, issuer websites, or unofficial reposts.
- Every source item must include `entity_verification`; discard sources that cannot verify the target subject.
- Every source item must include `attachment_title`. For `rating_report`, if the wrapper page title is `评级结果公告` and none of `title`, `attachment_title`, `source_url`, or `pdf_url` contains `评级报告`/`跟踪评级报告`/`信用评级报告`/`主体评级报告`/`债项评级报告`, classify as `unsupported_file_type`.
- All URLs in source files must belong to `chinamoney.com.cn`, `sse.com.cn`, `szse.cn`, or their subdomains. `source_platform` must match the URL domain.
- Support non-bond issuers and unrated entities; absence of bonds, ratings, or prospectuses is a data limitation, not a reason to fabricate.
- If no financial report with `report_period` 2025 or later and no 2025-or-later prospectus/rating report is found, stop financial analysis and use the fixed no-data summary.
- If only 2024-or-earlier financial reports are found, keep them out of `sources.financial_report` and financial tables, set `data_level=no_data`, and use the fixed no-data summary.
- If no annual/semiannual/quarterly report exists and only prospectus/rating data is available, `data_level` must be at most `partial_financial`; do not claim complete `三年一期`, and set `missing_data_note` to explain `未取得正式财务报告，仅基于募集说明书/评级报告披露内容摘录`.
- If only quarterly data is found, keep it supplemental unless the user explicitly asks for quarterly analysis.
- Exclude unsupported announcement types unless their attachment list contains a corrected formal allowed file.
- Prefer latest publish date within each file type, but never let publish date override file-type priority.
- `analysis_basis` must be one of: `年度报告`, `半年度报告`, `季度报告补充`, `募集说明书补充`, `评级报告补充`, `无有效公开资料`. When `data_level=no_data`, use `无有效公开资料`.

## Frontend Expectations

Return modules suitable for frontend rendering:

- Enterprise basic information and clickable source files.
- Enhanced search log for the 3 allowed channels.
- Main financial tables from annual/semiannual sources when available.
- `supplemental_financial_tables` for quarterly, prospectus, or rating-report supplementary fields.
- Indicator analysis with current value, previous value, change direction, objective judgement, and source.
- Negative findings with type, evidence, and source URL.
- A fixed short negative disclosure summary for top or side placement.
- Missing-data notes in the affected module instead of blank display.
- Hide financial tables and indicator cards when `data_availability.data_level` is `no_data`.

## References

- `references/financial-fields.md`: extraction fields, unit normalization, and indicator formulas.
- `references/source-policy.md`: 3-channel source whitelist, allowed file types, and latest-data freshness gate.
- `references/search-and-verification.md`: ChinaMoney/SSE/SZSE retrieval logic, candidate names, file classification, PDF parsing, and entity verification.
- `references/period-and-source-rules.md`: annual-report priority, quarterly-report limits, document filtering, and regression case.
- `references/data-availability.md`: fallback rules and no-data behavior under the 3-channel policy.
- `references/negative-signals.md`: allowed negative signal taxonomy and writing constraints.
- `references/negative-thresholds.md`: default negative indicator thresholds.
- `references/output-schema.md`: final JSON structure.
