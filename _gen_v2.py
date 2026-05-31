import re
from pathlib import Path

p = Path(r"C:\Users\luyng\.codex\skills\post-loan-analysis-report\scripts\validate_output.py")
txt = p.read_text("utf-8")

# Insert helper functions before def main()
helpers = r"""
def extract_domain(url: object) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    match = re.search(r"https?://([^/:\s]+)", url)
    return match.group(1).lower().removeprefix("www.") if match else None


def platform_for_domain(domain: str) -> str | None:
    for platform, domains in ALLOWED_DOMAINS.items():
        if domain in domains:
            return platform
    return None


def validate_url_domain(url: str, source_platform: str, path: str) -> None:
    domain = extract_domain(url)
    if domain is None:
        return
    expected = platform_for_domain(domain)
    if expected is None:
        fail(f"{path} URL domain '{domain}' not in allowed whitelist")
    if source_platform and expected != source_platform:
        fail(f"{path} URL domain '{domain}' -> '{expected}' but source_platform is '{source_platform}'")


def has_full_rating_report_term(item: dict) -> bool:
    text = " ".join(str(v) for k, v in item.items() if k in {"title", "attachment_title", "pdf_url"})
    return any(term in text for term in FULL_RATING_REPORT_TERMS)


def collect_table_urls(tables: dict, prefix: str) -> list:
    urls = []
    if not isinstance(tables, dict):
        return urls
    for tkey in FINANCIAL_TABLE_KEYS:
        rows = tables.get(tkey)
        if not isinstance(rows, list):
            continue
        for ridx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            for k, v in row.items():
                if isinstance(v, dict) and v.get("source_url"):
                    urls.append((v["source_url"], f"{prefix}.{tkey}[{ridx}].{k}.source_url"))
    return urls


def validate_query_run(run: object, path: str) -> None:
    if not isinstance(run, dict):
        fail(f"{path} must be an object")
    missing = QUERY_RUN_REQUIRED_KEYS - run.keys()
    if missing:
        fail(f"{path} missing keys: {', '.join(sorted(missing))}")
    if not isinstance(run.get("keyword"), str) or not run.get("keyword"):
        fail(f"{path}.keyword must be non-empty string")
    if run.get("search_scope") not in SEARCH_SCOPE_VALUES:
        fail(f"{path}.search_scope invalid")
    if not isinstance(run.get("search_column"), str):
        fail(f"{path}.search_column must be string")
    for ik in ("total_results", "scanned_result_count", "matched_documents"):
        require_non_negative_int(run, ik, path)
    require_bool(run, "annual_report_found", path)
    for lk in ("matched_titles", "selected_titles", "skipped_titles"):
        if not isinstance(run.get(lk), list):
            fail(f"{path}.{lk} must be list")
    if not isinstance(run.get("note"), str):
        fail(f"{path}.note must be string")
    if run.get("total_results") >= 30 and run.get("scanned_result_count") < 30:
        fail(f"{path}.scanned_result_count must be >= 30 when total_results >= 30")
    if run.get("total_results") < 30 and run.get("scanned_result_count") != run.get("total_results"):
        fail(f"{path}.scanned_result_count must equal total_results when < 30")
"""

txt = txt.replace("\n\ndef main() -> None:", helpers + "\n\ndef main() -> None:")

# After analysis_basis check (which should be after summary check), add basis validation
# Find the summary check and add basis check after it
txt = txt.replace(
    '    if len(summary) > 200:\n        fail(f"negative summary exceeds 200 characters: {len(summary)}")\n\n    # ---- data_availability ----',
    '    if len(summary) > 200:\n        fail(f"negative summary exceeds 200 characters: {len(summary)}")\n\n    # ---- analysis_basis ----\n    basis = data.get("analysis_basis", "")\n    if basis not in ANALYSIS_BASIS_VALUES:\n        fail(f"analysis_basis must be one of: {chr(44).join(sorted(ANALYSIS_BASIS_VALUES))}")\n\n    # ---- data_availability ----'
)

# After data_level check (after the has_public_opinion check), add no_data + basis check
txt = txt.replace(
    '    if not isinstance(availability.get("data_limitation_note"), str):\n        fail("data_availability.data_limitation_note must be a string")\n\n    # ---- source_policy ----',
    '    if not isinstance(availability.get("data_limitation_note"), str):\n        fail("data_availability.data_limitation_note must be a string")\n    if data_level == "no_data" and basis != "\u65e0\u6709\u6548\u516c\u5f00\u8d44\u6599":\n        fail(\'analysis_basis must be "\u65e0\u6709\u6548\u516c\u5f00\u8d44\u6599" when data_level=no_data\')\n\n    # ---- source_policy ----'
)

# Add url domain validation for source items - insert before validate_entity_verification call
txt = txt.replace(
    '    validate_entity_verification(item.get("entity_verification"), path_str)\n    if item.get("file_type") in FINANCIAL_REPORT_TYPES:',
    '    validate_entity_verification(item.get("entity_verification"), path_str)\n    # URL domain validation\n    for uf in ("source_url", "pdf_url"):\n        u = item.get(uf, "")\n        if u:\n            validate_url_domain(u, platform, f"{path_str}.{uf}")\n    if item.get("file_type") in FINANCIAL_REPORT_TYPES:'
)

# Add url domain for selected_documents in search_log
txt = txt.replace(
    '        for doc_idx, doc in enumerate(item.get("selected_documents")):\n            dp = f"{slp}.selected_documents[{doc_idx}]"\n            validate_selected_document(doc, dp)',
    '        for doc_idx, doc in enumerate(item.get("selected_documents")):\n            dp = f"{slp}.selected_documents[{doc_idx}]"\n            validate_selected_document(doc, dp)\n            for uf in ("source_url", "pdf_url"):\n                ud = doc.get(uf, "")\n                if ud:\n                    validate_url_domain(ud, source_name, f"{dp}.{uf}")'
)

# Add query_runs validation and consistency check after search_log section
txt = txt.replace(
    '    if set(seen_sources) != set(ALLOWED_SOURCES):\n        fail("search_log must include \u4e2d\u56fd\u8d27\u5e01\u7f51, \u4e0a\u6d77\u8bc1\u5238\u4ea4\u6613\u6240, and \u6df1\u5733\u8bc1\u5238\u4ea4\u6613\u6240 exactly once")\n\n    if data_level in {"full", "partial_financial"}',
    '    if set(seen_sources) != set(ALLOWED_SOURCES):\n        fail("search_log must include 3 platforms exactly once")\n\n    # ---- sources <-> search_log consistency ----\n    all_sl_titles = {(d.get("title",""), d.get("pdf_url",""), sn) for si in search_log for sn in [si.get("source_name","")] for d in si.get("selected_documents",[])}\n    all_sl_main = {(d.get("title",""), d.get("pdf_url",""), sn) for si in search_log for sn in [si.get("source_name","")] for d in si.get("selected_documents",[]) if d.get("used_for_main_analysis") is True}\n    for group in SOURCE_KEYS:\n        if group == "public_opinion":\n            continue\n        for idx, item in enumerate(sources.get(group, [])):\n            t = (item.get("title",""), item.get("pdf_url",""), item.get("source_platform",""))\n            if t not in all_sl_titles:\n                fail(f"sources.{group}[{idx}] not found in search_log.selected_documents")\n    for mt in all_sl_main:\n        found_m = any(mt[0] == it.get("title","") and mt[1] == it.get("pdf_url","") and mt[2] == it.get("source_platform","") for group in SOURCE_KEYS if group != "public_opinion" for it in sources.get(group,[]))\n        if not found_m:\n            fail(f"selected_document with used_for_main_analysis=true not found in sources: {mt[0]}")\n\n    # ---- query_runs validation ----\n    for si in search_log:\n        runs = si.get("query_runs")\n        if not isinstance(runs, list) or not runs:\n            fail(f"search_log.query_runs must be non-empty list")\n        main_annual = False\n        for ri, run in enumerate(runs):\n            validate_query_run(run, f"search_log.query_runs[{ri}]")\n            if ri == 0 and run.get("annual_report_found") is True:\n                main_annual = True\n        if not main_annual and len(runs) > 1:\n            has_directed = any(any(kw in run.get("keyword","") for kw in ["\u5e74\u5ea6\u62a5\u544a","\u5e74\u62a5","\u5ba1\u8ba1\u62a5\u544a","\u5e74\u5ea6\u8d22\u52a1\u62a5\u8868","\u5408\u5e76\u53ca\u6bcd\u516c\u53f8\u8d22\u52a1\u62a5\u8868"]) for run in runs[1:])\n            if not has_directed:\n                warn("main search found no annual_report but no directed annual-report query_runs")\n\n    if data_level in {"full", "partial_financial"}'
)

# Add URL domain for findings and indicators
txt = txt.replace(
    '        if "舆情" in str(item.get("type", "")):\n            fail("negative_findings must not include public-opinion findings")',
    '        if "舆情" in str(item.get("type", "")):\n            fail("negative_findings must not include public-opinion findings")\n        surl = item.get("source_url", "")\n        if surl:\n            validate_url_domain(surl, "", f"negative_findings[{idx}].source_url")'
)

# Add URL domain check for financial_indicators source field
txt = txt.replace(
    '        if missing_indicator_keys:\n            fail(f"financial_indicators[{idx}] missing required keys: {chr(44).join(missing_indicator_keys)}")\n\n    if data_level == "no_data":',
    '        if missing_indicator_keys:\n            fail(f"financial_indicators[{idx}] missing required keys: {chr(44).join(missing_indicator_keys)}")\n        src = str(item.get("source", ""))\n        if "http" in src:\n            url_match = re.search(r"https?://[^\s)\]]+", src)\n            if url_match:\n                validate_url_domain(url_match.group(0), "", f"financial_indicators[{idx}].source")\n\n    # table url domains\n    for tname, tdata in [("financial_tables", tables), ("supplemental_financial_tables", supplemental_tables)]:\n        for u, upath in collect_table_urls(tdata, tname):\n            validate_url_domain(u, "", upath)\n\n    if data_level == "no_data":'
)

# remove has_full_rating_report_term duplicate if exists
txt = txt.replace('def has_full_rating_report_term(item: dict) -> bool:\n    text = " ".join(\n        str(v) for k, v in item.items() if k in {"title", "attachment_title"}\n    )\n    return any(term in text for term in FULL_RATING_REPORT_TERMS)\n\n', '')

print("generator applied, lines:", len(txt.splitlines()))
p.write_text(txt, "utf-8")
import ast
ast.parse(txt)
print("syntax OK")
