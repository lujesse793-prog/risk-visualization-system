# Search And Verification Rules

Apply `source-policy.md` before searching. This skill may only search 中国货币网, 上海证券交易所, and 深圳证券交易所. Do not expand to other websites.

## Candidate Names

Do not search only by exact full name. Build candidate names first:

1. Input enterprise full legal name.
2. Enterprise short name.
3. Bond issuer name.
4. Historical names or former names.
5. Highly similar subject names found in PDF titles.

Prefer files whose title exactly matches the input name. If a title uses a historical name, former name, or highly similar name, verify the subject before using it through at least one of:

- PDF cover page issuer/disclosure subject.
- Issuer field in the prospectus or report.
- Unified social credit code.
- Bond issuer identity.
- Explicit historical-name relationship.

If the same-subject relationship cannot be confirmed, do not use the file and record `skipped_reason`.

Example: for `泰州医药城控股集团有限公司`, candidate names may include:

- 泰州医药城控股集团有限公司
- 泰州东方中国医药城控股集团有限公司

The second name must not be directly adopted or rejected without subject verification.

## File Classification

Classify titles and attachments as:

- `annual_report`: contains 年度报告, 年报, 年度财务报表, 年度审计报告, 经审计财务报告, 合并及母公司财务报表, 合并财务报表, 母公司财务报表, 审计报告, 财务报表及附注, 年度财务报表及附注.
- `semi_annual_report`: contains 半年度报告, 半年报, 半年度财务报表.
- `quarterly_report`: contains 第一季度, 第三季度, 一季度, 三季度, 季度报告, 季度财务报表.
- `prospectus`: contains 募集说明书.
- `rating_report`: contains 评级报告, 跟踪评级报告, 信用评级报告, 主体评级报告, 债项评级报告.

Do not classify `评级结果公告` as `rating_report` unless the detail page or attachment list contains a full rating-report PDF. If no full rating-report attachment exists, classify it as `unsupported_file_type` and record `skipped_reason`.

If a title contains generic `财务报表` and also contains `一季度`, `第一季度`, `三季度`, `第三季度`, `半年度`, or `半年报`, classify it as the corresponding quarterly or semiannual report, not as `annual_report`.

For wrapper pages titled 更正公告 or 说明公告, inspect attachment names before filtering. If an attachment name contains an allowed file type or `更正后文件`, download and parse the corrected formal PDF.

## ChinaMoney Retrieval

For 中国货币网, internal retrieval or equivalent ChinaMoney page/API retrieval is required. External search-engine `site:` queries may be used only as a supplement, never as the only retrieval method.

For each enterprise:

1. Search by candidate enterprise names.
2. Prefer title search.
3. Use all-time range or a range covering at least the latest two years.
4. Use all columns first, then identify financial reports, prospectuses, and rating reports.
5. Scan at least the first 30 search results when available.
6. Do not stop at the first or newest result.
7. Open the detail page or PDF link for matched results.
8. If a page has an attachment list, parse the attachment list and download the PDF. Do not conclude `no_data` merely because the HTML wrapper has no financial table.
9. Treat ChinaMoney `dealPath` pages as valid when the detail page title, publish date, and attachment list match the target enterprise.

## Directed Annual-Report Search

The default scan is the first 30 results per platform. However, if the first 30 generic full-name results do not include an `annual_report`, run additional directed searches on each platform:

1. `{企业全名} 年度报告`
2. `{企业全名} 年报`
3. `{企业全名} 审计报告`
4. `{企业全名} 年度财务报表`
5. `{企业全名} 合并及母公司财务报表`

For each directed search, scan at least the first 30 results when available. Do not conclude that no annual report exists merely because the generic first 30 results do not include one.

## SSE Retrieval

For 上海证券交易所, search only bond-related disclosure pages and project-platform pages:

- 上交所债券信息网.
- 公司债券项目信息平台.
- 债券公告 and 信息披露 pages.

Use candidate names including full name, short name, issuer name, and historical name if identifiable.

Process results:

1. Scan at least the first 30 results when available.
2. Classify by allowed file type.
3. Prefer annual reports even if a quarterly report is newer.
4. Open detail pages or PDF attachments.
5. Download PDFs before parsing.
6. Do not rely on list snippets.

## SZSE Retrieval

For 深圳证券交易所, search only fixed-income and bond disclosure areas:

- 固定收益信息平台.
- 债券公告.
- 信息披露 pages.

Use the same processing rules as ChinaMoney and SSE:

1. Scan at least the first 30 results when available.
2. Classify by allowed file type.
3. Prefer annual reports.
4. Open detail pages or PDF attachments.
5. Download PDFs before parsing.
6. Do not rely on search-result snippets.

## Do Not Skip Annual Reports Because A Quarterly Report Is Newer

If results include both:

- 2026年一季度财务报表.
- 2025年年度报告.

Download and parse both. Use the 2025 annual report as the main analysis source and the 2026 first-quarter financial statements as supplemental information.

Never:

- Stop after the newest quarterly report.
- Take only the first result.
- Select only by publish date.
- Stop searching annual reports because a quarterly report exists.
- Miss annual reports because they appear lower in the result list.

## Query Runs Recording

Every search on each platform must be recorded in `search_log.query_runs`. Each `query_run` records one specific keyword search with its scope and results.

Required fields per `query_run`:

- `keyword`: exact search keyword used.
- `search_scope`: `按标题`, `按正文`, or `全部`.
- `search_column`: the column or section searched (e.g., `债券信息披露`, `财务报告`).
- `total_results`: total results returned by the platform for this query.
- `scanned_result_count`: number of results actually scanned; must be >= 30 when `total_results >= 30`.
- `matched_documents`: number of documents matching the allowed file types.
- `annual_report_found`: whether any matched document is an `annual_report`.
- `matched_titles`: list of titles that matched allowed file types.
- `selected_titles`: list of titles selected for download and parsing.
- `skipped_titles`: list of titles skipped, with brief skip reasons.
- `matched_items`: item-level trace objects with `title`, `publish_date`, `source_url`, `pdf_url`, `file_type`, `decision` (`selected` or `skipped`), and `reason`.
- `note`: free-text note about this query.

### Annual Report Directed Search Recording

If the main full-name search (first `query_run`) does not find an `annual_report`, five directed `query_run` entries must follow:

1. `{企业全名} 年度报告`
2. `{企业全名} 年报`
3. `{企业全名} 审计报告`
4. `{企业全名} 年度财务报表`
5. `{企业全名} 合并及母公司财务报表`

Each directed search must be recorded as a separate `query_run`. All five exact keywords are mandatory when the first `query_run.annual_report_found=false`; do not merely list the keywords in `keywords_used`.

## PDF Parsing Requirements

For every selected PDF:

1. Download the PDF.
2. Read the cover page and verify the subject name.
3. Identify report period.
4. Identify file type.
5. Extract key balance sheet, income statement, and cash flow statement fields.
6. If table extraction fails, extract key financial fields from PDF text.
7. If the PDF downloads but parsing fails, record `parse_failed_reason` in `search_log`; do not pretend the file was not found.

For financial reports, record the recognized `report_period`. A financial report published in 2025 or later but covering 2024 or earlier must be recorded as `stale_or_prior_period_document` and cannot be used as latest financial data.

For prospectuses and rating reports, record `disclosed_financial_data_cutoff` to show the actual cutoff period of financial data disclosed in that document.

## Entity Verification Object

Every adopted source must include:

```json
{
  "entity_verification": {
    "input_name": "",
    "matched_name_in_document": "",
    "matched_role": "发行人 / 披露主体 / 受评主体 / 母公司 / 子公司 / 关联方 / 历史名称 / 不确定",
    "is_same_subject": true,
    "relationship_to_target": "",
    "verification_evidence": "",
    "confidence": "high / medium / low"
  }
}
```

Use only high- or medium-confidence same-subject files for financial extraction.
