import re
from pathlib import Path

p = Path(r"C:\Users\luyng\.codex\skills\post-loan-analysis-report\scripts\validate_output.py")
txt = p.read_text("utf-8")

# 1. Remove opinion_only from DATA_LEVELS
txt = txt.replace(
    'DATA_LEVELS = {"full", "partial_financial", "opinion_only", "no_data"}',
    'DATA_LEVELS = {"full", "partial_financial", "no_data"}'
)

# 2. Remove opinion_only block
txt = re.sub(
    r'\n    if data_level == "opinion_only":\n        fail.*?\n    if availability.*?is not retrieved"\)\n',
    '\n',
    txt,
    flags=re.DOTALL
)

# 3. Add ALLOWED_DOMAINS and other new constants after ALLOWED_SOURCES
new_constants = '''
ALLOWED_DOMAINS = {
    "\u4e2d\u56fd\u8d27\u5e01\u7f51": ["chinamoney.com.cn"],
    "\u4e0a\u6d77\u8bc1\u5238\u4ea4\u6613\u6240": ["sse.com.cn", "bond.sse.com.cn"],
    "\u6df1\u5733\u8bc1\u5238\u4ea4\u6613\u6240": ["szse.cn"],
}
ANALYSIS_BASIS_VALUES = {
    "\u5e74\u5ea6\u62a5\u544a",
    "\u534a\u5e74\u5ea6\u62a5\u544a",
    "\u5b63\u5ea6\u62a5\u544a\u8865\u5145",
    "\u52df\u96c6\u8bf4\u660e\u4e66\u8865\u5145",
    "\u8bc4\u7ea7\u62a5\u544a\u8865\u5145",
    "\u65e0\u6709\u6548\u516c\u5f00\u8d44\u6599",
}
SEARCH_SCOPE_VALUES = {"\u6309\u6807\u9898", "\u6309\u6b63\u6587", "\u5168\u90e8"}
SKIPPED_REASON_VALUES = {
    "unsupported_file_type",
    "stale_only",
    "stale_or_prior_period_document",
    "subject_mismatch",
    "duplicate",
    "parse_failed",
    "lower_priority",
}
QUERY_RUN_REQUIRED_KEYS = {
    "keyword",
    "search_scope",
    "search_column",
    "total_results",
    "scanned_result_count",
    "matched_documents",
    "annual_report_found",
    "matched_titles",
    "selected_titles",
    "skipped_titles",
    "note",
}
'''

txt = txt.replace(
    'SEARCH_STATUS_VALUES = {',
    new_constants + 'SEARCH_STATUS_VALUES = {'
)

# 4. Add FULL_RATING_REPORT_TERMS after DOCUMENT_STATUS_VALUES
txt = txt.replace(
    'DOCUMENT_STATUS_VALUES = {\n    "latest_financial_data",\n    "stale_or_prior_period_document",\n    "supplemental_document",\n}',
    'DOCUMENT_STATUS_VALUES = {\n    "latest_financial_data",\n    "stale_or_prior_period_document",\n    "supplemental_document",\n}\nFULL_RATING_REPORT_TERMS = {\n    "\u8bc4\u7ea7\u62a5\u544a",\n    "\u8ddf\u8e2a\u8bc4\u7ea7\u62a5\u544a",\n    "\u4fe1\u7528\u8bc4\u7ea7\u62a5\u544a",\n    "\u4e3b\u4f53\u8bc4\u7ea7\u62a5\u544a",\n    "\u503a\u9879\u8bc4\u7ea7\u62a5\u544a",\n}'
)

# 5. Add attachment_title to ADOPTED_SOURCE_KEYS and SELECTED_DOCUMENT_KEYS
txt = txt.replace(
    '    "title",\n    "file_type",\n    "report_period",\n    "publish_date",\n    "source_url",\n    "pdf_url",\n    "source_platform",\n    "entity_match_result",\n    "used_for_main_analysis",\n    "used_as_supplement",\n    "document_status",\n    "entity_verification",',
    '    "title",\n    "attachment_title",\n    "file_type",\n    "report_period",\n    "publish_date",\n    "source_url",\n    "pdf_url",\n    "source_platform",\n    "entity_match_result",\n    "used_for_main_analysis",\n    "used_as_supplement",\n    "document_status",\n    "entity_verification",'
)
txt = txt.replace(
    'SELECTED_DOCUMENT_KEYS = {\n    "title",\n    "file_type",',
    'SELECTED_DOCUMENT_KEYS = {\n    "title",\n    "attachment_title",\n    "file_type",'
)

print("patches applied, lines:", len(txt.splitlines()))
p.write_text(txt, "utf-8")
print("written, checking syntax...")
import ast
ast.parse(txt)
print("syntax OK")
