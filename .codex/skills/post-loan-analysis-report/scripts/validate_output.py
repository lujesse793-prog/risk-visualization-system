#!/usr/bin/env python3
"""Validate announcement-source-discovery JSON output.

Validates the output of the "公告搜索与PDF来源发现" skill:
- task_type must be "announcement_source_discovery"
- source_documents[] structure and completeness
- source_platform and URL domain matching
- entity_verification + handoff_to_pdf_parser for selected documents
- search_log and query_runs completeness
- annual_report priority and directed search rules
- pdf_handoff must exist with valid documents_needing_pdf_parse
- dynamic freshness gate
- financial_tables/indicators/negative_findings must be empty
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

# ---- Constants ----

ALLOWED_SOURCES = ["中国货币网", "上海证券交易所", "深圳证券交易所"]

ALLOWED_DOMAINS = {
    "中国货币网": ["chinamoney.com.cn"],
    "上海证券交易所": ["sse.com.cn", "bond.sse.com.cn"],
    "深圳证券交易所": ["szse.cn"],
}

FILE_TYPES = {
    "annual_report", "semi_annual_report", "quarterly_report",
    "prospectus", "rating_report", "unsupported_file_type",
}

HANGOFF_ELIGIBLE_FILE_TYPES = {
    "annual_report", "semi_annual_report", "quarterly_report",
    "prospectus", "rating_report",
}

DOCUMENT_STATUS_VALUES = {
    "selected_main", "selected_supplement", "skipped",
    "stale_or_prior_period_document", "subject_mismatch",
    "unsupported_file_type", "download_failed",
}

DOWNLOAD_STATUS_VALUES = {"success", "failed", "skipped"}
LIGHT_PARSE_STATUS_VALUES = {"success", "partial", "failed", "not_attempted"}
ENTITY_CONFIDENCE_VALUES = {"high", "medium", "low"}
ENTITY_ROLE_VALUES = {
    "发行人", "披露主体", "受评主体", "母公司", "子公司",
    "关联方", "历史名称", "不确定",
}
SEARCH_STATUS_VALUES = {"matched", "not_found", "stale_only", "subject_mismatch", "error"}
SEARCH_SCOPE_VALUES = {"按标题", "按正文", "全部"}
MATCHED_ITEM_DECISIONS = {"selected", "skipped"}
SEARCH_MODES = {"内部检索", "页面检索", "附件检索", "PDF下载/链接提取"}
PLATFORM_STATUS_VALUES = {"success", "partial", "failed", "not_applicable"}

SOURCE_DOCUMENT_KEYS = {
    "document_id", "enterprise_input_name", "source_platform", "source_channel",
    "title", "attachment_title", "file_type", "report_period", "publish_date",
    "source_url", "pdf_url", "local_pdf_path", "pdf_download_status",
    "pdf_file_size", "pdf_sha256", "light_parse_status",
    "light_parse_failed_reason", "needs_deep_pdf_parse", "document_status",
    "selection_reason", "skipped_reason", "entity_verification", "handoff_to_pdf_parser",
}

ENTITY_VERIFICATION_KEYS = {
    "input_name", "matched_name_in_document", "matched_role",
    "is_same_subject", "relationship_to_target", "verification_evidence", "confidence",
}

HANDOFF_KEYS = {"enabled", "parser_hint", "priority", "reason"}

QUERY_RUN_KEYS = {
    "keyword", "search_scope", "search_column", "total_results",
    "scanned_result_count", "matched_documents", "annual_report_found",
    "matched_titles", "selected_titles", "skipped_titles", "matched_items", "note",
}

MATCHED_ITEM_KEYS = {
    "title", "attachment_title", "publish_date", "source_url",
    "pdf_url", "file_type", "decision", "reason",
}

PDF_HANDOFF_KEYS = {
    "enterprise_name", "task_id", "generated_at",
    "selected_main_documents", "selected_supplement_documents",
    "documents_needing_pdf_parse", "no_latest_public_data", "message",
}

FULL_RATING_REPORT_TERMS = {
    "评级报告", "跟踪评级报告", "信用评级报告", "主体评级报告", "债项评级报告",
}

DIRECTED_ANNUAL_KEYWORDS = [
    "年度报告", "年报", "审计报告", "年度财务报表", "合并及母公司财务报表",
]

PLATFORM_NAMES = {"中国货币网", "上海证券交易所", "深圳证券交易所"}

NO_DATA_MESSAGE = "未有最新公开财务数据披露，无法基于公开资料生成有效分析。"

# ---- Helpers ----

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def extract_domain(url: str) -> str:
    if not url:
        return ""
    m = re.search(r"https?://([^/:\s]+)", url)
    if not m:
        return ""
    host = m.group(1).lower()
    for domain_list in ALLOWED_DOMAINS.values():
        for d in domain_list:
            if host == d or host.endswith("." + d):
                return d
    return host


def get_platform_for_domain(domain: str) -> str | None:
    for platform, domains in ALLOWED_DOMAINS.items():
        for d in domains:
            if domain == d or domain.endswith("." + d):
                return platform
    return None


def validate_url_domain(url: str, expected_platform: str, path: str) -> None:
    if not url:
        return
    domain = extract_domain(url)
    if not domain:
        return
    platform = get_platform_for_domain(domain)
    if platform is None:
        fail(f"{path}: domain '{domain}' not in allowed domains")
    elif expected_platform and platform != expected_platform:
        fail(f"{path}: domain maps to '{platform}', expected '{expected_platform}'")


def parse_date(s: str) -> date | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


# ---- Per-document validation ----

def validate_source_document(doc: dict, idx: int, enterprise_name: str) -> None:
    prefix = f"source_documents[{idx}]"

    missing = [k for k in SOURCE_DOCUMENT_KEYS if k not in doc]
    if missing:
        fail(f"{prefix}: missing keys: {', '.join(sorted(missing))}")

    platform = doc.get("source_platform", "")
    if platform and platform not in ALLOWED_SOURCES:
        fail(f"{prefix}.source_platform '{platform}' not in allowed sources")

    file_type = doc.get("file_type", "")
    if file_type and file_type not in FILE_TYPES:
        fail(f"{prefix}.file_type '{file_type}' not valid")

    doc_status = doc.get("document_status", "")
    if doc_status and doc_status not in DOCUMENT_STATUS_VALUES:
        fail(f"{prefix}.document_status '{doc_status}' not valid")

    dl_status = doc.get("pdf_download_status", "")
    if dl_status and dl_status not in DOWNLOAD_STATUS_VALUES:
        fail(f"{prefix}.pdf_download_status '{dl_status}' not valid")

    lp_status = doc.get("light_parse_status", "")
    if lp_status and lp_status not in LIGHT_PARSE_STATUS_VALUES:
        fail(f"{prefix}.light_parse_status '{lp_status}' not valid")

    source_url = doc.get("source_url", "")
    pdf_url = doc.get("pdf_url", "")
    if source_url:
        validate_url_domain(source_url, platform, f"{prefix}.source_url")
    if pdf_url:
        validate_url_domain(pdf_url, platform, f"{prefix}.pdf_url")

    doc_ent = doc.get("enterprise_input_name", "")
    if doc_ent and enterprise_name and doc_ent != enterprise_name:
        fail(f"{prefix}.enterprise_input_name does not match top-level")

    # entity_verification for selected documents
    if doc_status in {"selected_main", "selected_supplement"}:
        ev = doc.get("entity_verification")
        if not isinstance(ev, dict):
            fail(f"{prefix}: selected document must have entity_verification")
        else:
            validate_entity_verification(ev, prefix)

        ho = doc.get("handoff_to_pdf_parser")
        if not isinstance(ho, dict):
            fail(f"{prefix}: selected document must have handoff_to_pdf_parser")
        else:
            validate_handoff(ho, prefix)

    # rating_report classification check
    if file_type == "rating_report":
        combined = doc.get("title", "") + doc.get("attachment_title", "")
        has_rating_term = any(term in combined for term in FULL_RATING_REPORT_TERMS)
        if not has_rating_term:
            fail(f"{prefix}: classified rating_report but no rating-report term found")


def validate_entity_verification(ev: dict, prefix: str) -> None:
    missing = [k for k in ENTITY_VERIFICATION_KEYS if k not in ev]
    if missing:
        fail(f"{prefix}.entity_verification: missing: {', '.join(sorted(missing))}")

    role = ev.get("matched_role", "")
    if role and role not in ENTITY_ROLE_VALUES:
        fail(f"{prefix}.entity_verification.matched_role '{role}' not valid")

    confidence = ev.get("confidence", "")
    if confidence and confidence not in ENTITY_CONFIDENCE_VALUES:
        fail(f"{prefix}.entity_verification.confidence '{confidence}' not valid")

    if not isinstance(ev.get("is_same_subject"), bool):
        fail(f"{prefix}.entity_verification.is_same_subject must be boolean")


def validate_handoff(ho: dict, prefix: str) -> None:
    missing = [k for k in HANDOFF_KEYS if k not in ho]
    if missing:
        fail(f"{prefix}.handoff_to_pdf_parser: missing: {', '.join(sorted(missing))}")
    if not isinstance(ho.get("enabled"), bool):
        fail(f"{prefix}.handoff_to_pdf_parser.enabled must be boolean")


# ---- search_log validation ----

def validate_search_log_item(item: dict, idx: int) -> None:
    prefix = f"search_log[{idx}]"

    source_name = item.get("source_name", "")
    if source_name not in PLATFORM_NAMES:
        fail(f"{prefix}.source_name '{source_name}' not valid")

    if item.get("searched") is not True:
        fail(f"{prefix}.searched must be true")

    modes = item.get("search_modes", [])
    if not isinstance(modes, list) or len(modes) == 0:
        fail(f"{prefix}.search_modes must be non-empty")
    for m in modes:
        if m not in SEARCH_MODES:
            fail(f"{prefix}.search_modes: invalid '{m}'")

    dl_status = item.get("download_status", "")
    if dl_status not in PLATFORM_STATUS_VALUES:
        fail(f"{prefix}.download_status '{dl_status}' not valid")

    lp_status = item.get("light_parse_status", "")
    if lp_status not in PLATFORM_STATUS_VALUES:
        fail(f"{prefix}.light_parse_status '{lp_status}' not valid")

    status = item.get("status", "")
    if status not in SEARCH_STATUS_VALUES:
        fail(f"{prefix}.status '{status}' not valid")

    for sdoc in item.get("selected_documents", []):
        if isinstance(sdoc, dict):
            sp = sdoc.get("source_platform", "")
            if sp and sp != source_name:
                fail(f"{prefix}.selected: platform '{sp}' != source '{source_name}'")

    query_runs = item.get("query_runs", [])
    if not isinstance(query_runs, list):
        fail(f"{prefix}.query_runs must be a list")
    for qidx, qr in enumerate(query_runs):
        validate_query_run(qr, qidx, prefix)


def validate_query_run(qr: dict, idx: int, parent: str) -> None:
    prefix = f"{parent}.query_runs[{idx}]"
    missing = [k for k in QUERY_RUN_KEYS if k not in qr]
    if missing:
        fail(f"{prefix}: missing: {', '.join(sorted(missing))}")

    scope = qr.get("search_scope", "")
    if scope and scope not in SEARCH_SCOPE_VALUES:
        fail(f"{prefix}.search_scope '{scope}' not valid")

    total = qr.get("total_results", 0)
    scanned = qr.get("scanned_result_count", 0)
    if isinstance(total, int) and isinstance(scanned, int):
        if total >= 30 and scanned < 30:
            fail(f"{prefix}: total={total} but scanned={scanned} < 30")
        if total < 30 and scanned != total:
            fail(f"{prefix}: total={total} but scanned={scanned} (mismatch)")

    for midx, mi in enumerate(qr.get("matched_items", [])):
        validate_matched_item(mi, midx, prefix)


def validate_matched_item(mi: dict, idx: int, parent: str) -> None:
    prefix = f"{parent}.matched_items[{idx}]"
    missing = [k for k in MATCHED_ITEM_KEYS if k not in mi]
    if missing:
        fail(f"{prefix}: missing: {', '.join(sorted(missing))}")
    decision = mi.get("decision", "")
    if decision not in MATCHED_ITEM_DECISIONS:
        fail(f"{prefix}.decision '{decision}' not valid")
    ft = mi.get("file_type", "")
    if ft and ft not in FILE_TYPES:
        fail(f"{prefix}.file_type '{ft}' not valid")


def validate_source_documents_array(docs: list, enterprise_name: str) -> None:
    if not isinstance(docs, list):
        fail("source_documents must be a list")
        return
    if len(docs) == 0:
        fail("source_documents must not be empty")
    for idx, doc in enumerate(docs):
        if not isinstance(doc, dict):
            fail(f"source_documents[{idx}] must be an object")
            continue
        validate_source_document(doc, idx, enterprise_name)


def validate_search_log(data: dict) -> None:
    search_log = data.get("search_log", [])
    if not isinstance(search_log, list):
        fail("search_log must be a list")
        return

    found_platforms = {item.get("source_name", "") for item in search_log
                       if isinstance(item, dict)}
    missing_platforms = PLATFORM_NAMES - found_platforms
    if missing_platforms:
        fail(f"search_log missing: {', '.join(sorted(missing_platforms))}")

    for idx, item in enumerate(search_log):
        if not isinstance(item, dict):
            fail(f"search_log[{idx}] must be an object")
            continue
        validate_search_log_item(item, idx)

    # Directed annual report search rule
    for pidx, item in enumerate(search_log):
        if not isinstance(item, dict):
            continue
        query_runs = item.get("query_runs", [])
        if not query_runs:
            continue
        first_run = query_runs[0]
        if not isinstance(first_run, dict):
            continue
        if first_run.get("total_results", 0) == 0:
            continue
        if not first_run.get("annual_report_found"):
            directed_found = set()
            for qr in query_runs[1:]:
                kw = qr.get("keyword", "") if isinstance(qr, dict) else ""
                for dkw in DIRECTED_ANNUAL_KEYWORDS:
                    if dkw in kw:
                        directed_found.add(dkw)
            missing_directed = set(DIRECTED_ANNUAL_KEYWORDS) - directed_found
            if missing_directed:
                fail(
                    f"search_log[{pidx}]: no annual_report in first query, "
                    f"missing directed: {', '.join(sorted(missing_directed))}"
                )


# ---- pdf_handoff validation ----

def validate_pdf_handoff(data: dict) -> None:
    """Validate pdf_handoff structure and content rules."""
    handoff = data.get("pdf_handoff")
    if handoff is None:
        fail("pdf_handoff is missing from top-level output")
        return

    if not isinstance(handoff, dict):
        fail("pdf_handoff must be an object")
        return

    # Required keys
    missing = [k for k in PDF_HANDOFF_KEYS if k not in handoff]
    if missing:
        fail(f"pdf_handoff missing keys: {', '.join(sorted(missing))}")

    # Validate basic structure
    for key in ("selected_main_documents", "selected_supplement_documents",
                "documents_needing_pdf_parse"):
        val = handoff.get(key)
        if not isinstance(val, list):
            fail(f"pdf_handoff.{key} must be a list")

    no_data = handoff.get("no_latest_public_data", False)
    needing = handoff.get("documents_needing_pdf_parse", [])

    # Rule: if no_latest_public_data=true, documents_needing_pdf_parse must be empty
    if no_data:
        if len(needing) > 0:
            fail("pdf_handoff: no_latest_public_data=true but documents_needing_pdf_parse is not empty")
        message = handoff.get("message", "")
        if not message:
            fail("pdf_handoff: no_latest_public_data=true but message is empty")
        return  # skip further checks when no data

    # Rule: documents_needing_pdf_parse must reference valid source_documents
    source_docs = data.get("source_documents", [])
    doc_ids = {d.get("document_id", "") for d in source_docs if isinstance(d, dict)}
    doc_by_id = {d.get("document_id", ""): d for d in source_docs if isinstance(d, dict)}

    for idx, ref in enumerate(needing):
        if not isinstance(ref, dict):
            fail(f"pdf_handoff.documents_needing_pdf_parse[{idx}] must be an object")
            continue

        doc_id = ref.get("document_id", "")
        prefix = f"pdf_handoff.documents_needing_pdf_parse[{idx}]"

        # Must exist in source_documents
        if doc_id and doc_id not in doc_ids:
            fail(f"{prefix}: document_id '{doc_id}' not found in source_documents[]")

        # Validate against source document
        if doc_id in doc_by_id:
            sdoc = doc_by_id[doc_id]
            _validate_handoff_document(sdoc, doc_id, prefix)


def _validate_handoff_document(sdoc: dict, doc_id: str, prefix: str) -> None:
    """Validate a document in documents_needing_pdf_parse against its source."""
    ds = sdoc.get("document_status", "")
    ft = sdoc.get("file_type", "")

    # Must be selected_main or selected_supplement
    if ds not in {"selected_main", "selected_supplement"}:
        fail(f"{prefix}: document_status='{ds}' not selected_main/supplement")

    # file_type must be eligible
    if ft not in HANGOFF_ELIGIBLE_FILE_TYPES:
        if ft == "unsupported_file_type":
            fail(f"{prefix}: unsupported_file_type must not enter handoff")
        else:
            fail(f"{prefix}: file_type='{ft}' not eligible for handoff")

    # document_status restrictions
    FORBIDDEN_STATUSES = {
        "subject_mismatch", "stale_or_prior_period_document",
        "download_failed", "unsupported_file_type",
    }
    if ds in FORBIDDEN_STATUSES:
        fail(f"{prefix}: document_status='{ds}' forbidden in handoff")

    # Needs PDF URL or local path
    if not sdoc.get("pdf_url") and not sdoc.get("local_pdf_path"):
        fail(f"{prefix}: no pdf_url or local_pdf_path")

    # needs_deep_pdf_parse must be true
    if not sdoc.get("needs_deep_pdf_parse"):
        fail(f"{prefix}: needs_deep_pdf_parse is not true")

    # Entity verification
    ev = sdoc.get("entity_verification", {})
    if not isinstance(ev, dict):
        fail(f"{prefix}: missing entity_verification")
        return
    if not ev.get("is_same_subject"):
        fail(f"{prefix}: entity_verification.is_same_subject is false")
    confidence = ev.get("confidence", "")
    if confidence not in {"high", "medium"}:
        fail(f"{prefix}: entity_verification.confidence='{confidence}' not high/medium")


# ---- Selection & freshness rules ----

def validate_selection_rules(data: dict) -> None:
    source_docs = data.get("source_documents", [])
    if not isinstance(source_docs, list):
        return

    selected_main = [d for d in source_docs
                     if isinstance(d, dict) and d.get("document_status") == "selected_main"]

    if selected_main:
        main_types = {d.get("file_type") for d in selected_main}
        if "annual_report" not in main_types:
            fail("selected_main does not include an annual_report")

    for doc in source_docs:
        if not isinstance(doc, dict):
            continue
        ft = doc.get("file_type", "")
        ds = doc.get("document_status", "")
        if ft == "unsupported_file_type" and ds in {"selected_main", "selected_supplement"}:
            fail(f"unsupported_file_type cannot have document_status={ds}")


def validate_financial_emptiness(data: dict) -> None:
    """Financial fields must be empty since this skill doesn't do financial analysis."""
    for field in ("financial_tables", "supplemental_financial_tables"):
        val = data.get(field)
        if not isinstance(val, dict):
            fail(f"{field} must be a dict (must be empty)")
        elif val:
            fail(f"{field} must be empty; this skill does not parse financial tables")

    for field in ("financial_indicators", "negative_findings"):
        val = data.get(field)
        if not isinstance(val, list):
            fail(f"{field} must be a list (must be empty)")
        elif len(val) > 0:
            fail(f"{field} must be empty; this skill does not compute indicators")


def validate_freshness_gate(data: dict) -> None:
    """Validate dynamic freshness gate."""
    fg = data.get("freshness_gate", {})
    if not isinstance(fg, dict):
        return

    run_date_str = data.get("run_date", "")
    run_date = parse_date(run_date_str)

    if run_date and isinstance(fg.get("run_year"), int):
        expected_year = run_date.year
        if fg["run_year"] != expected_year:
            fail(f"freshness_gate.run_year={fg['run_year']} != run_date year={expected_year}")

    if run_date and isinstance(fg.get("min_financial_report_year"), int):
        expected_min = run_date.year - 1
        if fg.get("transitional_fallback_used"):
            expected_min = run_date.year - 2
        # Only warn if significantly off
        if fg["min_financial_report_year"] < run_date.year - 3:
            fail(f"freshness_gate.min_financial_report_year={fg['min_financial_report_year']} too old for run_date={run_date_str}")

    if not fg.get("is_fresh_enough", True):
        dl = data.get("data_availability", {}).get("data_level", "")
        if dl != "no_data":
            fail("stale freshness gate requires data_level=no_data")


# ---- Main ----

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python validate_output.py <output.json>", file=sys.stderr)
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"File not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Rule: task_type
    if data.get("task_type") != "announcement_source_discovery":
        fail("task_type must be 'announcement_source_discovery'")

    # Rule: run_date
    run_date = data.get("run_date", "")
    if not run_date or not parse_date(run_date):
        fail("run_date is missing or invalid")

    enterprise_name = data.get("enterprise_name", "")

    # Validate source_documents
    source_docs = data.get("source_documents")
    if source_docs is None:
        fail("source_documents is missing")
    else:
        validate_source_documents_array(source_docs, enterprise_name)

    # Validate search_log
    validate_search_log(data)

    # Validate selection rules
    validate_selection_rules(data)

    # Validate financial emptiness
    validate_financial_emptiness(data)

    # Validate pdf_handoff (mandatory)
    validate_pdf_handoff(data)

    # Validate freshness gate
    validate_freshness_gate(data)

    if errors:
        print(f"\n[FAIL] {len(errors)} validation error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("[OK] announcement-source-discovery output passed validation")


if __name__ == "__main__":
    main()