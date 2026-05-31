const fs = require("fs");
const path = require("path");
const root = "C:/Users/luyng/.codex/skills/post-loan-analysis-report";

// ==================== SKILL.md ====================
let skill = fs.readFileSync(path.join(root, "SKILL.md"), "utf8");

// Add query_runs reference after search_modes line
skill = skill.replace(
  "   - Use `search_modes` as an array, for example `[\"内部检索\", \"页面检索\", \"附件检索\", \"PDF下载解析\"]`.\n   - For each adopted file, record `title`, `file_type`, `report_period`, `publish_date`, `source_url`, `pdf_url`, `entity_match_result`, `used_for_main_analysis`, and `used_as_supplement`.",
  "   - Use `search_modes` as an array, for example `[\"内部检索\", \"页面检索\", \"附件检索\", \"PDF下载解析\"]`.\n   - Each `search_log` entry must include `query_runs`, a list recording every specific search performed on that platform.\n   - For each adopted file, record `title`, `attachment_title`, `file_type`, `report_period`, `publish_date`, `source_url`, `pdf_url`, `entity_match_result`, `used_for_main_analysis`, and `used_as_supplement`."
);

// Add URL whitelist, analysis_basis, attachment_title rules
skill = skill.replace(
  "## Data Rules\n\n- All data must have a source.\n- Financial data sources must come only from 中国货币网, 上海证券交易所, or 深圳证券交易所.\n- Set `source_policy.allowed_announcement_sources_only=true` and `source_policy.external_financial_sources_used=false`.\n- Do not retrieve public opinion, news, business-registration pages, third-party aggregators, issuer websites, or unofficial reposts.\n- Every source item must include `entity_verification`; discard sources that cannot verify the target subject.\n- Support non-bond issuers and unrated entities; absence of bonds, ratings, or prospectuses is a data limitation, not a reason to fabricate.\n- If no financial report with `report_period` 2025 or later and no 2025-or-later prospectus/rating report is found, stop financial analysis and use the fixed no-data summary.\n- If only quarterly data is found, keep it supplemental unless the user explicitly asks for quarterly analysis.\n- Exclude unsupported announcement types unless their attachment list contains a corrected formal allowed file.\n- Prefer latest publish date within each file type, but never let publish date override file-type priority.",
  "## Data Rules\n\n- All data must have a source.\n- Financial data sources must come only from 中国货币网, 上海证券交易所, or 深圳证券交易所.\n- Set `source_policy.allowed_announcement_sources_only=true` and `source_policy.external_financial_sources_used=false`.\n- Do not retrieve public opinion, news, business-registration pages, third-party aggregators, issuer websites, or unofficial reposts.\n- Every source item must include `entity_verification`; discard sources that cannot verify the target subject.\n- Every source item must include `attachment_title`. For `rating_report`, if the wrapper page title is `评级结果公告` and the attachment title does not contain `评级报告`/`跟踪评级报告`/`信用评级报告`/`主体评级报告`/`债项评级报告`, classify as `unsupported_file_type`.\n- All URLs in source files must belong to `chinamoney.com.cn`, `sse.com.cn`, `bond.sse.com.cn`, or `szse.cn`. `source_platform` must match the URL domain.\n- Support non-bond issuers and unrated entities; absence of bonds, ratings, or prospectuses is a data limitation, not a reason to fabricate.\n- If no financial report with `report_period` 2025 or later and no 2025-or-later prospectus/rating report is found, stop financial analysis and use the fixed no-data summary.\n- If only quarterly data is found, keep it supplemental unless the user explicitly asks for quarterly analysis.\n- Exclude unsupported announcement types unless their attachment list contains a corrected formal allowed file.\n- Prefer latest publish date within each file type, but never let publish date override file-type priority.\n- `analysis_basis` must be one of: `年度报告`, `半年度报告`, `季度报告补充`, `募集说明书补充`, `评级报告补充`, `无有效公开资料`. When `data_level=no_data`, use `无有效公开资料`."
);

fs.writeFileSync(path.join(root, "SKILL.md"), skill, "utf8");
console.log("SKILL.md OK");

// ==================== source-policy.md ====================
let sp = fs.readFileSync(path.join(root, "references", "source-policy.md"), "utf8");
// Add URL whitelist section at the end
sp += "\n\n## URL Domain Whitelist\n\nOnly these domains are allowed for financial source URLs:\n\n- 中国货币网: `chinamoney.com.cn`\n- 上海证券交易所: `sse.com.cn`, `bond.sse.com.cn`\n- 深圳证券交易所: `szse.cn`\n\nEvery `source_url` and `pdf_url` must match one of these domains. A file's `source_platform` must match the domain (e.g., a `chinamoney.com.cn` URL requires `source_platform` = `中国货币网`).\n";
fs.writeFileSync(path.join(root, "references", "source-policy.md"), sp, "utf8");
console.log("source-policy.md OK");

// ==================== search-and-verification.md ====================
let sv = fs.readFileSync(path.join(root, "references", "search-and-verification.md"), "utf8");

// Add query_runs documentation after the "Do Not Skip Annual Reports" section
sv = sv.replace(
  "## PDF Parsing Requirements",
  "## Query Runs Recording\n\nEvery search on each platform must be recorded in `search_log.query_runs`. Each `query_run` records one specific keyword search with its scope and results.\n\nRequired fields per `query_run`:\n\n- `keyword`: exact search keyword used.\n- `search_scope`: `按标题`, `按正文`, or `全部`.\n- `search_column`: the column or section searched (e.g., `债券信息披露`, `财务报告`).\n- `total_results`: total results returned by the platform for this query.\n- `scanned_result_count`: number of results actually scanned; must be >= 30 when `total_results >= 30`.\n- `matched_documents`: number of documents matching the allowed file types.\n- `annual_report_found`: whether any matched document is an `annual_report`.\n- `matched_titles`: list of titles that matched allowed file types.\n- `selected_titles`: list of titles selected for download and parsing.\n- `skipped_titles`: list of titles skipped, with brief skip reasons.\n- `note`: free-text note about this query.\n\n### Annual Report Directed Search Recording\n\nIf the main full-name search (first `query_run`) does not find an `annual_report`, five directed `query_run` entries must follow:\n\n1. `{企业全名} 年度报告`\n2. `{企业全名} 年报`\n3. `{企业全名} 审计报告`\n4. `{企业全名} 年度财务报表`\n5. `{企业全名} 合并及母公司财务报表`\n\nEach directed search must be recorded as a separate `query_run`. Do not merely list the keywords in `keywords_used`.\n\n## PDF Parsing Requirements"
);

fs.writeFileSync(path.join(root, "references", "search-and-verification.md"), sv, "utf8");
console.log("search-and-verification.md OK");

console.log("All reference files updated");
