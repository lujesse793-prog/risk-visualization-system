# Period And Source Rules

Read `source-policy.md` and `search-and-verification.md` first. These rules apply after documents have been retrieved from 中国货币网, 上海证券交易所, or 深圳证券交易所.

## Main Source Priority

Use this source priority for main financial analysis:

```text
annual_report > semi_annual_report > quarterly_report > prospectus > rating_report
```

Annual reports are the main source for post-loan financial analysis. Do not replace an available annual report with a newer quarterly report, prospectus, or rating report.

For financial reports, the main-analysis source must pass the report-period gate: `report_period` must be 2025 or later. A file published in 2025 or later but covering 2024 or earlier is `stale_or_prior_period_document` and cannot be treated as latest financial data.

## Period Display

Prefer `三年一期`:

```text
最新半年度数据 | 最近一年年报 | 前一年年报 | 再前一年年报
```

If no semiannual report exists, use the latest annual reports:

```text
2025年 | 2024年 | 2023年
```

If fewer periods are available, display the actual available annual/semiannual periods and explain the limitation.

## Quarterly Reports

Quarterly reports are supplemental by default:

- Store parsed quarterly data in `supplemental_financial_tables`.
- Record quarterly reports in `sources.financial_report`.
- Set `used_for_main_analysis=false` and `used_as_supplement=true`.
- If `quarterly_report_used_for_analysis=false`, do not use quarterly reports as the core basis for `financial_indicators`, `negative_findings`, or `negative_summary_under_200_chars`.

If only quarterly reports are found, do not force a full financial analysis. Explain that only quarterly financial disclosure was found and keep quarterly data supplemental unless the user explicitly requests quarterly analysis.

## Prospectus And Rating Reports

Use prospectuses and rating reports mainly to supplement:

- Enterprise profile.
- Shareholders and actual controller.
- Main business.
- Material debt.
- External guarantees.
- Rating views.
- Risk warnings.
- Restricted assets.
- Interest-bearing debt structure.

If no annual, semiannual, or quarterly report exists but a fresh prospectus or rating report exists, extract only disclosed financial fields and clearly mark them as supplementary or limited-source data. Do not reconstruct full statements from incomplete metrics.

When only prospectus or rating-report data is available:

- `data_level` must be no higher than `partial_financial`.
- `data_period_type` must not claim a complete `三年一期`.
- `missing_data_note` must state `未取得正式财务报告，仅基于募集说明书/评级报告披露内容摘录`.
- Financial tables and indicators may include only fields directly disclosed and fully supported by those documents.

When only 2024-or-earlier financial reports are found:

- Record them in `search_log.selected_documents` or `search_log.skipped_documents` with `document_status=stale_or_prior_period_document` when applicable.
- Set `used_for_main_analysis=false`.
- Do not put them in `sources.financial_report` or financial tables.
- Set `data_level=no_data` and use `未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。`.

## Selection Rules

For each channel:

1. Scan at least the first 30 search results when available.
2. Classify all allowed file types.
3. Keep the latest valid document for each file type.
4. Prefer annual reports for main analysis.
5. Keep newer quarterly reports as supplemental information.
6. Keep fresh prospectuses and rating reports as supplemental sources.
7. Record skipped documents and `skipped_reason`.
8. If generic full-name search scans the first 30 results and finds no annual report, run the directed annual-report searches listed in `search-and-verification.md` before concluding that no annual report exists.

## Regression Requirement

For `泰州医药城控股集团有限公司`, if the retrieval results include:

- `泰州医药城控股集团有限公司关于更正2026年第一季度财务报表的公告及更正后的文件` published `2026-05-15`.
- `泰州医药城控股集团有限公司2026年第一季度财务报表` published `2026-04-30`.
- `泰州医药城控股集团有限公司2025年年度报告` published `2026-04-30`.
- `泰州东方中国医药城控股集团有限公司2025年年度报告` published `2026-04-30`.
- `泰州东方中国医药城控股集团有限公司2026年一季度合并及母公司财务报表` published `2026-04-30`.

The skill must:

1. Download and parse `泰州医药城控股集团有限公司2025年年度报告`.
2. Classify it as `annual_report`.
3. Use it as the main financial analysis source.
4. Use the 2026 first-quarter financial statements only as supplemental information.
5. Verify the historical-name or same-subject relationship before using any `泰州东方中国医药城控股集团有限公司` file.
6. Record total results, scanned count, selected documents, and skipped reasons in `search_log`.

## No Negative Findings

If valid financial data has been retrieved and parsed but no negative matter can be directly supported by the downloaded public disclosure files, keep `negative_findings` as an empty array and set:

```text
未识别到可由公开披露文件直接支持的重大负面事项。
```

Do not force a negative judgement merely to fill the summary.
