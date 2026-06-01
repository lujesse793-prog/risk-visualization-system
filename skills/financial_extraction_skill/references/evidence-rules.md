# Evidence Rules

Every extracted field must have traceable evidence:

```json
{
  "evidence_id": "ev_001",
  "standard_field_name": "total_assets",
  "field_name": "资产总计",
  "period": "2025",
  "value": 123456.78,
  "unit": "万元",
  "source_document_id": "doc_001",
  "source_document_type": "annual_report",
  "page": 88,
  "table_id": "tbl_001",
  "table_title": "合并资产负债表",
  "raw_row": "资产总计",
  "raw_column": "2025年末",
  "evidence_text": "合并资产负债表第88页，资产总计，2025年末金额为123456.78万元",
  "confidence": "high"
}
```

Evidence may be one-to-one with extracted fields or otherwise directly traceable by `source_document_id`, `page`, `table_id`, `raw_row`, and `raw_column`.

