# Data Availability Fallback

Support non-bond issuers, unrated entities, and entities without public financial data. The rule is: use whatever can be reliably sourced from the 3 allowed channels; never fabricate data; if no latest public financial disclosure is found on those channels, stop and output the fixed no-data message.

This skill no longer searches ordinary public opinion, news, business-registration pages, issuer websites, or third-party aggregators as fallback sources.

## Retrieval Priority

Within 中国货币网, 上海证券交易所, and 深圳证券交易所, retrieve allowed file types in this priority:

1. Latest annual report / annual financial statements / annual audit report whose `report_period` is 2025 or later.
2. Latest semiannual report whose `report_period` is 2025 or later.
3. Latest quarterly report whose `report_period` is 2025 or later.
4. Latest prospectus.
5. Latest rating report.

Record all matched allowed files, but use annual reports first for main analysis.

## Fallback Rules

### Annual Report Available

Use the latest annual report as the main financial source. Extract and display:

- Balance sheet.
- Income statement.
- Cash flow statement.
- Business segments when disclosed.
- Core financial indicators.
- Negative findings supported by annual-report data.

If semiannual data is also available, use it as the latest-period supplement. If quarterly data is also available, store it in `supplemental_financial_tables`.

### Semiannual Report Available But No Annual Report

Use semiannual data as available, but clearly explain the missing annual report. Calculate only indicators that are meaningful for the available period and source fields.

### Only Quarterly Report Available

Quarterly data is supplemental by default. Do not use it as the main negative-analysis basis unless the user explicitly requests quarterly analysis. If `quarterly_report_used_for_analysis=false`, keep `financial_indicators` and financial negative summaries based on annual/semiannual/prospectus/rating data only.

### No Financial Report, Prospectus Available

Extract only disclosed recent and historical financial data from the prospectus. Mark all source fields as prospectus-derived.

Set `data_limitation_note` to:

```text
未检索到公开年报或半年报，当前财务数据来源于募集说明书披露内容。
```

### No Financial Report Or Prospectus, Rating Report Available

Extract only financial data and rating concerns disclosed in the rating report. Do not fill missing complete statements when the rating report provides only selected metrics.

Set `data_limitation_note` to:

```text
未检索到公开年报、半年报或募集说明书，当前财务数据来源于评级报告披露内容。
```

### No Latest Public Financial Disclosure

If the 3 channels do not provide any valid latest document from the allowed file types, stop analysis. For financial reports, latest means `report_period` is 2025 or later; for prospectuses and rating reports, latest means `publish_date` is 2025 or later, with the disclosed financial-data cutoff recorded.

Use this fixed summary and no-data output:

```text
未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。
```

## Frontend Display Levels

- `full`: annual and, when available, semiannual data are present; display enterprise information, source files, main financial tables, supplemental tables, indicators, and negative summary.
- `partial_financial`: only partial annual/semiannual data, only quarterly supplemental data, prospectus data, or rating-report data are available; display only reliable modules and explain limitations.
- `no_data`: display only `未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。`

## Prohibited Behavior

Do not:

1. Fabricate financial data to fill tables.
2. Use business-registration information as financial data.
3. Use registered capital, paid-in capital, number of insured employees, or other business-registration fields to make financial judgements.
4. Derive financial indicators from news or public-opinion summaries.
5. Apply parent, subsidiary, affiliate, same-name, or historical-name documents directly to the target enterprise without subject verification.
6. Convert `未查询到负面事项` into positive commentary such as `企业经营稳健`.
7. Output unsourced risk judgements.
8. Display blank financial tables when no financial data is available.
9. Use 2024 or earlier old files to generate a latest post-loan analysis when no fresh document is found.

## No Negative Findings

If valid financial data exists but no directly supported negative finding is identified, do not invent one. Use:

```text
未识别到可由公开披露文件直接支持的重大负面事项。
```

In that case `negative_findings` may be an empty array.
