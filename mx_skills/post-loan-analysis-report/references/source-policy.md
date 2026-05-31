# Source Policy And Freshness Gate

## Allowed Retrieval Channels

For post-loan analysis, financial reports, prospectuses, rating reports, and all files used for financial tables or indicators may only be retrieved from these 3 public channels:

1. 中国货币网
   - `https://www.chinamoney.com.cn`
   - Use the internal site search or equivalent ChinaMoney page/API retrieval for 债券信息披露, 财务报告, 募集说明书, and 评级报告.
   - Do not rely only on external search-engine `site:` queries.
2. 上海证券交易所
   - `https://www.sse.com.cn`
   - `https://bond.sse.com.cn`
   - Use 上交所债券信息网, 公司债券项目信息平台, 债券公告, and 信息披露 pages.
3. 深圳证券交易所
   - `https://www.szse.cn`
   - Use 深交所固定收益信息平台, 债券公告, and 信息披露 pages.

Do not search or use any other website for this skill run. If these 3 channels do not provide valid latest public financial disclosure, stop and output:

```text
未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。
```

Do not supplement with news, public opinion, business-registration pages, recruitment pages, bidding pages, third-party aggregators, unofficial reposts, or issuer websites.

## Allowed File Types

Only retrieve, download, and parse these 5 file types:

1. `annual_report`: 年度报告, 年报, 年度财务报表, 年度审计报告, 经审计财务报告, 合并及母公司财务报表, 合并财务报表, 母公司财务报表, 审计报告, 财务报表及附注, 年度财务报表及附注.
2. `semi_annual_report`: 半年度报告, 半年报, 半年度财务报表.
3. `quarterly_report`: 第一季度报告, 一季度报告, 第一季度财务报表, 一季度财务报表, 第三季度报告, 三季度报告, 季度财务报表.
4. `prospectus`: 募集说明书, 更新募集说明书, 债券募集说明书, 中期票据募集说明书, 超短期融资券募集说明书.
5. `rating_report`: 主体评级报告, 债项评级报告, 跟踪评级报告, 信用评级报告, 评级报告.

`评级结果公告` must not be classified as `rating_report` by itself. If a rating-result announcement has a full rating-report attachment whose title contains `评级报告`, `跟踪评级报告`, `信用评级报告`, `主体评级报告`, or `债项评级报告`, classify and use the attachment. If there is no full rating-report attachment, classify the wrapper as `unsupported_file_type` and record `skipped_reason`.

Exclude these by default:

- 付息公告
- 兑付公告
- 发行结果公告
- 持有人会议公告
- 法律意见书
- 受托管理事务报告
- 临时公告
- 发行方案
- 承诺函
- 说明公告
- 一般更正公告
- 工商信息
- 新闻报道
- 舆情信息

Exception: if the title or attachment contains `年度报告`, `半年度报告`, `季度报告`, `财务报表`, `审计报告`, `募集说明书`, `评级报告`, or `更正后文件`, do not filter it merely because the wrapper title includes `更正公告`. Open the detail page and attachment list, download the corrected formal PDF, and use the corrected file first.

## Report Type Priority

Do not select documents only by latest publish date. Select by `report type priority + publish date`:

```text
annual_report > semi_annual_report > quarterly_report > prospectus > rating_report
```

Rules:

1. Annual reports are the main data source. If the latest annual report is available, it must be downloaded, parsed, and used for core financial indicators.
2. Semiannual reports supplement annual reports and show the latest interim change.
3. Quarterly reports are supplemental. They may enter `supplemental_financial_tables` and `sources`, but if `quarterly_report_used_for_analysis=false`, do not use them as the main basis for negative judgements.
4. Prospectuses and rating reports supplement enterprise profile, shareholders, actual controllers, main business, material debt, guarantees, rating views, risk warnings, restricted assets, and interest-bearing debt structure.
5. Never use a prospectus or rating report to replace an available annual report.
6. If annual report, quarterly report, prospectus, and rating report are all found, record all sources. Use the annual report for main financial analysis and the other documents only as supplements.

## Freshness Gate

The skill is for latest public post-loan analysis. After searching the 3 allowed channels, apply a dual `report_period + publish_date` gate.

For financial reports (`annual_report`, `semi_annual_report`, `quarterly_report`):

1. Identify `report_period` before using the file.
2. Only financial reports whose `report_period` is 2025 or later may be treated as latest financial data.
3. If `publish_date >= 2025-01-01` but `report_period` is 2024 or earlier, record the file as `stale_or_prior_period_document`; do not use it as the latest post-loan analysis main basis.

For prospectuses and rating reports:

1. Use `publish_date >= 2025-01-01` as the newness test.
2. Also record the actual cutoff date or period of financial data disclosed inside the document as `disclosed_financial_data_cutoff`.

Trigger the gate when:

1. No financial report with `report_period` 2025 or later is found.
2. No prospectus or rating report published in 2025 or later is found.
3. All matched documents are either published before 2025 or are `stale_or_prior_period_document`.

When triggered:

- Stop analysis.
- Do not search any other website.
- Do not extract financial tables.
- Do not calculate indicators.
- Do not generate current financial negative judgements from older data.
- Use exactly:

```text
未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。
```

Do not use 2024 or earlier old report periods to generate a latest post-loan analysis, even if the file itself was published in 2025 or later.


## URL Domain Whitelist

Only these domains and their subdomains are allowed for financial source URLs:

- 中国货币网: `chinamoney.com.cn` and subdomains
- 上海证券交易所: `sse.com.cn` and subdomains
- 深圳证券交易所: `szse.cn` and subdomains

Every `source_url` and `pdf_url` must match one of these domains or subdomains. A file's `source_platform` must match the domain (e.g., a `chinamoney.com.cn` URL requires `source_platform` = `中国货币网`).
