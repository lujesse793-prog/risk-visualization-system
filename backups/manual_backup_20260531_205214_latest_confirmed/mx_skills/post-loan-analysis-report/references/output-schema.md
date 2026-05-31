# Output Schema

Return strict JSON for frontend rendering:

```json
{
  "enterprise_name": "",
  "report_date": "",
  "data_updated_at": "",
  "data_period_type": "三年一期 / 两年一期 / 三年 / 两年 / 可获取数据不足",
  "analysis_basis": "年度报告 / 半年度报告 / 季度报告补充 / 募集说明书补充 / 评级报告补充 / 无有效公开资料",
  "quarterly_report_used_for_analysis": false,
  "source_policy": {
    "allowed_announcement_sources_only": true,
    "allowed_sources": [
      "中国货币网",
      "上海证券交易所",
      "深圳证券交易所"
    ],
    "external_financial_sources_used": false
  },
  "freshness_gate": {
    "enabled": true,
    "cutoff_publish_date": "2025-01-01",
    "minimum_report_period": "2025年及之后公开披露",
    "latest_document_publish_date": "",
    "latest_report_period": "",
    "is_fresh_enough_for_analysis": false,
    "stop_reason": ""
  },
  "data_availability": {
    "has_financial_report": false,
    "has_prospectus": false,
    "has_rating_report": false,
    "has_financial_data": false,
    "has_public_opinion": false,
    "data_level": "full / partial_financial / no_data",
    "data_limitation_note": ""
  },
  "sources": {
    "financial_report": [
      {
        "title": "",
        "attachment_title": "",
        "file_type": "annual_report / semi_annual_report / quarterly_report",
        "report_period": "",
        "period": "",
        "report_type": "annual / semiannual / quarterly",
        "publish_date": "",
        "url": "",
        "source_url": "",
        "pdf_url": "",
        "source_platform": "中国货币网 / 上海证券交易所 / 深圳证券交易所",
        "entity_match_result": "",
        "used_for_main_analysis": true,
        "used_as_supplement": false,
        "document_status": "latest_financial_data / stale_or_prior_period_document / supplemental_document",
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
    ],
    "prospectus": [
      {
        "title": "",
        "attachment_title": "",
        "file_type": "prospectus",
        "report_period": "",
        "publish_date": "",
        "url": "",
        "source_url": "",
        "pdf_url": "",
        "source_platform": "中国货币网 / 上海证券交易所 / 深圳证券交易所",
        "entity_match_result": "",
        "used_for_main_analysis": false,
        "used_as_supplement": true,
        "document_status": "supplemental_document",
        "disclosed_financial_data_cutoff": "",
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
    ],
    "rating_report": [
      {
        "title": "",
        "attachment_title": "",
        "file_type": "rating_report",
        "report_period": "",
        "publish_date": "",
        "url": "",
        "source_url": "",
        "pdf_url": "",
        "source_platform": "中国货币网 / 上海证券交易所 / 深圳证券交易所",
        "entity_match_result": "",
        "used_for_main_analysis": false,
        "used_as_supplement": true,
        "document_status": "supplemental_document",
        "disclosed_financial_data_cutoff": "",
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
    ],
    "public_opinion": []
  },
  "search_log": [
    {
      "source_name": "中国货币网",
      "searched": true,
      "search_modes": ["内部检索", "页面检索", "附件检索", "PDF下载解析"],
      "keywords_used": [],
      "total_results": 0,
      "scanned_result_count": 0,
      "matched_documents": 0,
      "selected_documents": [],
      "skipped_documents": [],
      "skipped_reason": [],
      "download_status": "success / partial / failed / not_applicable",
      "parse_status": "success / partial / failed / not_applicable",
      "parse_failed_reason": "",
      "latest_document_publish_date": "",
      "latest_report_period": "",
      "status": "matched / not_found / stale_only / subject_mismatch / error",
      "note": "",
      "query_runs": [
        {
          "keyword": "",
          "search_scope": "按标题 / 按正文 / 全部",
          "search_column": "",
          "total_results": 0,
          "scanned_result_count": 0,
          "matched_documents": 0,
          "annual_report_found": false,
          "matched_titles": [],
          "selected_titles": [],
          "skipped_titles": [],
          "matched_items": [
            {
              "title": "",
              "publish_date": "",
              "source_url": "",
              "pdf_url": "",
              "file_type": "",
              "decision": "selected / skipped",
              "reason": ""
            }
          ],
          "note": ""
        }
      ]
    }
  ],
  "financial_tables": {
    "periods": [],
    "balance_sheet": [],
    "income_statement": [],
    "cash_flow_statement": [],
    "business_segments": []
  },
  "supplemental_financial_tables": {
    "periods": [],
    "balance_sheet": [],
    "income_statement": [],
    "cash_flow_statement": [],
    "business_segments": []
  },
  "financial_indicators": [
    {
      "indicator_name": "",
      "current_value": "",
      "previous_value": "",
      "change_direction": "",
      "judgement": "",
      "source": ""
    }
  ],
  "negative_findings": [
    {
      "type": "财务指标 / 评级报告 / 募集说明书",
      "finding": "",
      "evidence": "",
      "source_url": ""
    }
  ],
  "negative_summary_under_200_chars": "",
  "missing_data_note": ""
}
```

Each adopted file inside `selected_documents` should include:

```json
{
  "title": "",
  "attachment_title": "",
  "file_type": "annual_report / semi_annual_report / quarterly_report / prospectus / rating_report",
  "report_period": "",
  "publish_date": "",
  "source_url": "",
  "pdf_url": "",
  "source_platform": "中国货币网 / 上海证券交易所 / 深圳证券交易所",
  "entity_match_result": "",
  "used_for_main_analysis": true,
  "used_as_supplement": false,
  "document_status": "latest_financial_data / stale_or_prior_period_document / supplemental_document",
  "disclosed_financial_data_cutoff": ""
}
```

Each skipped file inside `skipped_documents` should include:

```json
{
  "title": "",
  "file_type": "",
  "source_url": "",
  "pdf_url": "",
  "skipped_reason": "unsupported_file_type / stale_only / stale_or_prior_period_document / subject_mismatch / duplicate / parse_failed / lower_priority"
}
```

Each financial data point inside `financial_tables` and `supplemental_financial_tables` should use this cell shape whenever possible:

```json
{
  "value": "",
  "unit": "亿元",
  "source_title": "",
  "source_url": "",
  "page": "",
  "table_name": "",
  "raw_text": ""
}
```

Validation rules:

1. `negative_summary_under_200_chars` must not exceed 200 Chinese characters.
2. Use only 中国货币网, 上海证券交易所, and 深圳证券交易所 for source files.
3. `search_log` must contain exactly one entry for each of the 3 allowed channels.
4. Each `search_log` item must include `search_modes`, `query_runs`, `total_results`, `scanned_result_count`, `matched_documents`, `selected_documents`, `skipped_documents`, `skipped_reason`, `download_status`, and `parse_status`.
5. `query_runs` records every specific search performed on each platform. Each `query_run` must include `keyword`, `search_scope`, `search_column`, `total_results`, `scanned_result_count`, `matched_documents`, `annual_report_found`, `matched_titles`, `selected_titles`, `skipped_titles`, `matched_items`, and `note`.
6. If a `query_run.total_results >= 30`, `query_run.scanned_result_count` must be `>= 30`. If `total_results < 30`, `scanned_result_count` must equal `total_results`.
7. If the main full-name search does not find an `annual_report`, subsequent directed annual-report query runs must include all five exact keywords: `{企业全名} 年度报告`, `{企业全名} 年报`, `{企业全名} 审计报告`, `{企业全名} 年度财务报表`, `{企业全名} 合并及母公司财务报表`.
8. If a final `annual_report` is adopted, its title must appear in `query_runs.matched_titles` or `selected_titles`.
9. `search_log` platform-level `total_results` and `scanned_result_count` are summaries; per-query scan completeness is verified from `query_runs`.
10. Every adopted source must include `file_type`, `report_period`, `source_url`, `pdf_url`, `source_platform`, `entity_match_result`, `used_for_main_analysis`, `used_as_supplement`, `document_status`, and `entity_verification`.
11. Every `search_log.selected_documents` item must have `source_platform` equal to the outer `search_log.source_name`.
12. `search_log.skipped_reason` is a platform-level summary; each `skipped_documents[]` item must include its own `title`, `file_type`, `source_url`, and `skipped_reason`.
13. If an `annual_report` is available, at least one annual report must have `used_for_main_analysis=true`.
14. Quarterly reports must not be the main basis when `quarterly_report_used_for_analysis=false`.
15. Financial report sources must have `report_period` in 2025 or later to be used as latest financial data.
16. Financial reports with `publish_date >= 2025-01-01` but `report_period` before 2025 must be recorded as `stale_or_prior_period_document` and must not enter `sources.financial_report` or financial tables.
17. `rating_report` must not be based solely on a `评级结果公告`; use it only when the title, attachment name, source URL, or PDF URL contains a full rating-report phrase.
18. If `freshness_gate.is_fresh_enough_for_analysis=false`, use `data_level=no_data`, leave financial tables and indicators empty, and use the fixed no-data summary.
19. If only prospectus/rating report data is available, `data_level` must not be `full`, `data_period_type` must not claim `三年一期`, and `missing_data_note` must explain `未取得正式财务报告，仅基于募集说明书/评级报告披露内容摘录`.
20. If valid financial data exists but no direct negative finding is identified, `negative_findings` may be empty and `negative_summary_under_200_chars` should be `未识别到可由公开披露文件直接支持的重大负面事项。`
21. If `data_level=full` or `partial_financial`, at least one financial source must exist and `has_financial_data=true`.
22. Every `negative_findings` item must include `type`, `finding`, `evidence`, and `source_url`.
23. Every `financial_indicators` item must include `indicator_name`, `current_value`, `judgement`, and `source`.
