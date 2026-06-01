# Input Schema

Skill3 receives Skill2 output:

```json
{
  "enterprise_name": "企业名称",
  "source_documents": [
    {
      "document_id": "doc_001",
      "document_type": "annual_report | semi_annual_report | quarterly_report | prospectus | rating_report",
      "report_period": "2025",
      "publication_date": "2026-04-30",
      "source_url": "",
      "pdf_url": "",
      "pdf_sha256": "",
      "is_selected_main": true,
      "is_selected_supplement": false
    }
  ],
  "parsed_documents": [
    {
      "document_id": "doc_001",
      "document_type": "annual_report | semi_annual_report | quarterly_report | prospectus | rating_report",
      "report_period": "2025",
      "parser_used": "marker | surya | marker+surya",
      "ocr_used": false,
      "page_count": 120,
      "page_texts": {"88": "页面文本"},
      "tables_raw": [
        {
          "table_id": "tbl_001",
          "page": 88,
          "table_title": "合并资产负债表",
          "rows": [
            ["项目", "2025年末", "2024年末"],
            ["货币资金", "123456.78", "100000.00"]
          ]
        }
      ],
      "parse_status": "success | partial | failed",
      "parse_confidence": "high | medium | low",
      "parse_warnings": []
    }
  ]
}
```

Do not require raw PDF paths. Do not fetch or parse PDFs in this skill.

