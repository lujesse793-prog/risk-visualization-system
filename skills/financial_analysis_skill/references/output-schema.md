# 输出 JSON Schema

```json
{
  "task_id": "",
  "enterprise_name": "",
  "analysis_status": "success | partial | failed",
  "data_status": "sufficient | partial | insufficient",
  "main_period": "",
  "periods_analyzed": [],
  "source_documents": [
    {
      "document_id": "",
      "source_platform": "",
      "file_type": "",
      "report_period": "",
      "publish_date": "",
      "source_url": "",
      "pdf_url": "",
      "local_pdf_path": "",
      "document_status": "",
      "entity_verification": {},
      "file_name": "",
      "source_pdf": "",
      "report_type": "",
      "selected_type": ""
    }
  ],
  "financial_indicators": [
    {
      "indicator_name": "",
      "indicator_category": "debt_capacity | liquidity | profitability | cash_flow | debt_structure | capital_structure | growth | data_quality",
      "period": "",
      "value": null,
      "unit": "",
      "formula": "",
      "input_fields": [
        {
          "field_name": "",
          "standard_field_name": "",
          "period": "",
          "value": null,
          "unit": "亿元",
          "source_document_id": "",
          "source_pdf": "",
          "page": null,
          "table_id": "",
          "table_title": "",
          "raw_row": "",
          "raw_column": "",
          "evidence_text": "",
          "confidence": "high | medium | low"
        }
      ],
      "source_refs": [
        {
          "source_document_id": "",
          "source_pdf": "",
          "page": null,
          "table_id": "",
          "table_title": "",
          "raw_row": "",
          "raw_column": "",
          "evidence_text": "",
          "confidence": "high | medium | low"
        }
      ],
      "status": "available | unavailable",
      "unavailable_reason": "",
      "confidence": "high | medium | low",
      "formula_warning": ""
    }
  ],
  "negative_findings": [
    {
      "finding_id": "",
      "finding_type": "confirmed_risk | warning_signal | data_limitation",
      "risk_level": "low | medium | high",
      "indicator_name": "",
      "period": "",
      "value": null,
      "threshold": "",
      "judgement": "",
      "evidence_text": "",
      "source_document_id": "",
      "source_pdf": "",
      "page": null,
      "table_id": "",
      "table_title": "",
      "source_refs": [
        {
          "source_document_id": "",
          "source_pdf": "",
          "page": null,
          "table_id": "",
          "table_title": "",
          "raw_row": "",
          "raw_column": "",
          "evidence_text": "",
          "confidence": "high | medium | low"
        }
      ],
      "confidence": "high | medium | low"
    }
  ],
  "unavailable_indicators": [
    {
      "indicator_name": "",
      "period": "",
      "unavailable_reason": "",
      "is_core_indicator": true
    }
  ],
  "analysis_summary": {
    "overall_view": "",
    "debt_pressure": "",
    "profitability": "",
    "cash_flow": "",
    "refinancing_pressure": "",
    "capital_structure": "",
    "data_limitation_note": ""
  },
  "frontend_financial_summary": {
    "total_assets": null,
    "total_liabilities": null,
    "asset_liability_ratio": null,
    "cash_and_cash_equivalents": null,
    "short_term_interest_bearing_debt": null,
    "cash_short_debt_ratio": null,
    "operating_revenue": null,
    "net_profit": null,
    "net_cash_flow_from_operating_activities": null,
    "total_owner_equity": null,
    "interest_bearing_debt": null,
    "current_ratio": null,
    "quick_ratio": null
  },
  "risk_level_summary": {
    "confirmed_risk_count": 0,
    "warning_signal_count": 0,
    "data_limitation_count": 0,
    "highest_risk_level": "none | low | medium | high"
  },
  "validation_result": {
    "passed": true,
    "errors": [],
    "warnings": []
  }
}
```

说明：`page` 使用 1 起始的正整数页码；上游未提供真实页码时输出 `null`，不使用 `0` 表示未知。
