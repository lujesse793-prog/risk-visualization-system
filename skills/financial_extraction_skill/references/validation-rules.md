# Validation Rules

Before returning:

1. Ensure `balance_sheet`, `income_statement`, and `cash_flow_statement` are arrays.
2. Ensure every extracted field has `standard_field_name`, `period`, `source_document_id`, `page`, `evidence_text`, and `confidence`.
3. Ensure every extracted field has `value`, unless the field appears in `missing_fields`.
4. Ensure `field_evidence` can trace each field to `source_document_id` and `page`.
5. Do not mark `success` when too many key fields are missing.
6. Allow units only from `元`, `千元`, `万元`, `亿元`, and `unknown`.
7. If `unit = "unknown"`, require a `unit_uncertain` warning.
8. Do not mark `success` when any key field has `unit = "unknown"`.
9. If no fields are extracted, `extraction_status` must be `failed`.

Status:

- `success`: latest period has the main statements and key fields including `total_assets`, `total_liabilities`, `total_owner_equity`, `cash_and_cash_equivalents`, `short_term_borrowings`, `non_current_liabilities_due_within_one_year`, `long_term_borrowings`, `bonds_payable`, `operating_revenue`, `net_profit`, and `net_cash_flow_from_operating_activities`.
- `partial`: some fields extracted, but key fields or full statements are missing, or only supplemental sources are available.
- `failed`: no effective statements, no usable fields, all parses failed, or data is too old to support latest post-loan analysis.
