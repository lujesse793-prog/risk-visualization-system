# Output Schema

Always emit JSON:

```json
{
  "enterprise_name": "企业名称",
  "extraction_status": "success | partial | failed",
  "data_periods": ["2025", "2024"],
  "selected_main_document_id": "doc_001",
  "selected_supplement_document_ids": [],
  "structured_financial_data": {
    "financial_tables": {
      "balance_sheet": [],
      "income_statement": [],
      "cash_flow_statement": []
    }
  },
  "field_evidence": [],
  "missing_fields": [],
  "extraction_warnings": [],
  "document_usage": [],
  "validation_result": {
    "passed": true,
    "errors": [],
    "warnings": []
  }
}
```

Each extracted field must include `field_name`, `standard_field_name`, `statement_type`, `period`, `period_type`, `value`, `unit`, `source_document_id`, `source_document_type`, `source_pdf`, `page`, `table_id`, `table_title`, `raw_row`, `raw_column`, `evidence_text`, and `confidence`. `unit` must be one of `元`, `千元`, `万元`, `亿元`, or `unknown`; `unknown` requires a `unit_uncertain` warning.

Each `extraction_warnings[]` item must keep `warning_type` and include `severity` with one of `fatal`, `important`, or `debug`.
