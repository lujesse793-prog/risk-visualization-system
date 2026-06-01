# Extraction Rules

## Source Priority

Use documents in this order:

1. Latest annual report.
2. Latest semiannual report.
3. Latest quarterly report.
4. Latest prospectus.
5. Latest rating report.

Formal annual, semiannual, and quarterly financial statements outrank prospectus or rating-report summaries. Prospectus and rating-report data are supplemental only and must not overwrite newer formal statement data.

## Table Recognition

Prefer consolidated primary statements:

- Balance sheet: `合并资产负债表`, then `资产负债表`.
- Income statement: `合并利润表`, then `利润表`.
- Cash flow statement: `合并现金流量表`, then `现金流量表`.

If both consolidated and parent-company statements exist, extract consolidated statements only. If only parent-company statements exist, warn in `extraction_warnings`.

Do not treat titles containing `附注`, `明细`, `构成`, `账龄`, `分类`, or `补充资料` as primary statements.

## Extraction Priority

1. Structured `tables_raw`.
2. `page_texts` statement text.
3. Prospectus/rating-report financial summary tables.

`page_texts` is a fallback only. Use it when `tables_raw` is empty or when a parsed document lacks a recognized primary balance sheet, income statement, or cash flow statement. Text fallback must not overwrite primary structured statement data, must use lower confidence, and must emit `text_fallback_used` when it contributes fields.

Normalize table rows before extraction:

- Skip title rows, unit rows, blank rows, and classification rows such as `流动资产：` or `所有者权益：`.
- Detect the header row instead of assuming `rows[0]`.
- Detect the `项目`/financial-line-item column.
- Skip `附注` columns.
- Extract amount columns only, including headers such as `2025年末`, `2025年12月31日`, `期末余额`, `期初余额`, `本期金额`, `上期金额`, `本期发生额`, and `上期发生额`.
- Merge simple OCR split rows where a financial subject line is followed by a numeric-only row.

## Conflict Handling

For duplicate field-period pairs, select by primary statement, consolidated statement, newer formal source, and structured table quality. If non-selected values differ, emit `source_conflict`. Do not average or merge values.

## Warning Types

Use locatable warnings with `source_document_id`, `page`, `statement_type`, and `message` where applicable:

Each warning must keep `warning_type` and include `severity`:

| warning_type | severity |
|---|---|
| stale_financial_data | fatal |
| financial_statement_not_found | important |
| balance_sheet_not_found | important |
| income_statement_not_found | important |
| cash_flow_statement_not_found | important |
| unit_uncertain | important |
| period_uncertain | important |
| source_conflict | important |
| parent_company_only | important |
| no_tables_raw | debug |
| text_fallback_used | debug |
