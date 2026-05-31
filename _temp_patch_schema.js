const fs = require("fs");
const p = "C:/Users/luyng/.codex/skills/post-loan-analysis-report/references/output-schema.md";
let md = fs.readFileSync(p, "utf8");
md = md.replace(String.raw`"analysis_basis": "年度报告"`, String.raw`"analysis_basis": "年度报告 / 半年度报告 / 季度报告补充 / 募集说明书补充 / 评级报告补充 / 无有效公开资料"`);
md = md.replace(String.raw`"data_level": "full / partial_financial / opinion_only / no_data"`, String.raw`"data_level": "full / partial_financial / no_data"`);
const lines = md.split("\n");
const out = [];
let inFin = false, inPros = false, inRat = false;
for (let i = 0; i < lines.length; i++) {
  const line = lines[i];
  out.push(line);
  if (line.includes('"financial_report": [')) inFin = true;
  if (line.includes('"prospectus": [')) { inFin = false; inPros = true; }
  if (line.includes('"rating_report": [')) { inPros = false; inRat = true; }
  if (line.includes('"public_opinion": []')) inRat = false;
  const trimmed = line.trim();
  if (trimmed.startsWith('"title": ""') && !trimmed.includes("file_type") && (inFin || inPros || inRat)) {
    const indent = line.match(/^(\s*)/)[1];
    out.push(indent + '"attachment_title": "",');
  }
}
md = out.join("\n");
md = md.replace(
  '      "note": ""\n    }\n  ],\n  "financial_tables"',
  '      "note": ""\n    },\n    "query_runs": [\n      {\n        "keyword": "",\n        "search_scope": "按标题 / 按正文 / 全部",\n        "search_column": "",\n        "total_results": 0,\n        "scanned_result_count": 0,\n        "matched_documents": 0,\n        "annual_report_found": false,\n        "matched_titles": [],\n        "selected_titles": [],\n        "skipped_titles": [],\n        "note": ""\n      }\n    ]\n  ],\n  "financial_tables"'
);
md = md.replace(
  'Each adopted file inside `selected_documents` should include:\n\n```json\n{\n  "title": ""',
  'Each adopted file inside `selected_documents` should include:\n\n```json\n{\n  "title": "",\n  "attachment_title": ""'
);
md = md.replace(
  "4. Each `search_log` item must include `search_modes`, `total_results`",
  "4. Each `search_log` item must include `search_modes`, `query_runs`, `total_results`"
);
md = md.replace(
  "5. Scan at least 30 results when `total_results >= 30`; otherwise scan all results.",
  "5. `query_runs` records every specific search performed on each platform. Each `query_run` must include `keyword`, `search_scope`, `search_column`, `total_results`, `scanned_result_count`, `matched_documents`, `annual_report_found`, `matched_titles`, `selected_titles`, `skipped_titles`, and `note`.\n6. If a `query_run.total_results >= 30`, `query_run.scanned_result_count` must be `>= 30`. If `total_results < 30`, `scanned_result_count` must equal `total_results`.\n7. If the main full-name search does not find an `annual_report`, subsequent directed annual-report query runs must exist.\n8. If a final `annual_report` is adopted, its title must appear in `query_runs.matched_titles` or `selected_titles`.\n9. `search_log` platform-level `total_results` and `scanned_result_count` are summaries; per-query scan completeness is verified from `query_runs`."
);
const oldRules = "6. Every adopted source must include `file_type`, `report_period`, `source_url`, `pdf_url`, `entity_match_result`, `used_for_main_analysis`, `used_as_supplement`, `document_status`, and `entity_verification`.\n-7. Every adopted financial source must have `source_platform` equal to one of the 3 allowed channels.\n-8. If an `annual_report` is available, at least one annual report must have `used_for_main_analysis=true`.\n-9. Quarterly reports must not be the main basis when `quarterly_report_used_for_analysis=false`.\n-10. Financial report sources must have `report_period` in 2025 or later to be used as latest financial data.\n-11. Financial reports with `publish_date >= 2025-01-01` but `report_period` before 2025 must be recorded as `stale_or_prior_period_document` and must not make `data_level=full`.\n-12. `rating_report` must not be based solely on a `评级结果公告`; use it only when the title or attachment name contains a full rating-report phrase.\n-13. If `freshness_gate.is_fresh_enough_for_analysis=false`, use `data_level=no_data`, leave financial tables and indicators empty, and use the fixed no-data summary.\n-14. If valid financial data exists but no direct negative finding is identified, `negative_findings` may be empty and `negative_summary_under_200_chars` should be `未识别到可由公开披露文件直接支持的重大负面事项。`\n-15. If `data_level=full` or `partial_financial`, at least one financial source must exist and `has_financial_data=true`.\n-16. Every `negative_findings` item must include `type`, `finding`, `evidence`, and `source_url`.\n-17. Every `financial_indicators` item must include `indicator_name`, `current_value`, `judgement`, and `source`.";
const newRules = "6. Every adopted source must include `file_type`, `report_period`, `source_url`, `pdf_url`, `entity_match_result`, `used_for_main_analysis`, `used_as_supplement`, `document_status`, and `entity_verification`.\n7. Every adopted source must include `attachment_title`. `rating_report` with `attachment_title` containing only `评级结果公告` without `评级报告`/`跟踪评级报告`/`信用评级报告`/`主体评级报告`/`债项评级报告` must be rejected.\n8. All `source_url`, `pdf_url`, and `negative_findings.*.source_url` domains must match: `chinamoney.com.cn`, `sse.com.cn`, `bond.sse.com.cn`, `szse.cn`. `source_platform` must match the URL domain.\n9. Every adopted source in `sources` must have a matching entry in `search_log.selected_documents` on the same platform with the same `title` and `pdf_url`. Every `search_log.selected_documents` entry with `used_for_main_analysis=true` must appear in `sources`.\n10. Every adopted financial source must have `source_platform` equal to one of the 3 allowed channels.\n11. If an `annual_report` is available, at least one annual report must have `used_for_main_analysis=true`.\n12. Quarterly reports must not be the main basis when `quarterly_report_used_for_analysis=false`.\n13. Financial report sources must have `report_period` in 2025 or later to be used as latest financial data.\n14. Financial reports with `publish_date >= 2025-01-01` but `report_period` before 2025 must be recorded as `stale_or_prior_period_document`.\n15. `rating_report` must not be based solely on a `评级结果公告`; use it only when the title or attachment name contains a full rating-report phrase.\n16. If `freshness_gate.is_fresh_enough_for_analysis=false`, use `data_level=no_data`.\n17. If valid financial data exists but no direct negative finding is identified, `negative_findings` may be empty and `negative_summary_under_200_chars` should be `未识别到可由公开披露文件直接支持的重大负面事项。`\n18. Every `negative_findings` item must include `type`, `finding`, `evidence`, and `source_url`.\n19. Every `financial_indicators` item must include `indicator_name`, `current_value`, `judgement`, and `source`.\n20. `analysis_basis` must be one of: `年度报告`, `半年度报告`, `季度报告补充`, `募集说明书补充`, `评级报告补充`, `无有效公开资料`. When `data_level=no_data`, `analysis_basis` must be `无有效公开资料`.";
md = md.replace(oldRules, newRules);
fs.writeFileSync(p, md, "utf8");
console.log("output-schema.md updated OK");
