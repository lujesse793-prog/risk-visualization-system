#!/usr/bin/env python3
"""Validate post-loan analysis JSON output."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REQUIRED_TOP_LEVEL = {
    "enterprise_name",
    "report_date",
    "data_updated_at",
    "data_period_type",
    "analysis_basis",
    "quarterly_report_used_for_analysis",
    "source_policy",
    "freshness_gate",
    "data_availability",
    "search_log",
    "sources",
    "financial_tables",
    "supplemental_financial_tables",
    "financial_indicators",
    "negative_findings",
    "negative_summary_under_200_chars",
    "missing_data_note",
}

SOURCE_KEYS = {"financial_report", "prospectus", "rating_report", "public_opinion"}
FINANCIAL_SOURCE_KEYS = {"financial_report", "prospectus", "rating_report"}
DATA_LEVELS = {"full", "partial_financial", "no_data"}
ALLOWED_SOURCES = ["中国货币网", "上海证券交易所", "深圳证券交易所"]

ALLOWED_DOMAINS = {
    "中国货币网": ["chinamoney.com.cn"],
    "上海证券交易所": ["sse.com.cn", "bond.sse.com.cn"],
    "深圳证券交易所": ["szse.cn"],
}
ANALYSIS_BASIS_VALUES = {
    "年度报告",
    "半年度报告",
    "季度报告补充",
    "募集说明书补充",
    "评级报告补充",
    "无有效公开资料",
}
SEARCH_SCOPE_VALUES = {"按标题", "按正文", "全部"}
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
    "matched_items",
    "note",
}
MATCHED_ITEM_REQUIRED_KEYS = {
    "title",
    "publish_date",
    "source_url",
    "pdf_url",
    "file_type",
    "decision",
    "reason",
}
MATCHED_ITEM_DECISIONS = {"selected", "skipped"}
SEARCH_STATUS_VALUES = {"matched", "not_found", "stale_only", "subject_mismatch", "error"}
DOWNLOAD_STATUS_VALUES = {"success", "partial", "failed", "not_applicable"}
PARSE_STATUS_VALUES = {"success", "partial", "failed", "not_applicable"}
SEARCH_MODES = {"内部检索", "页面检索", "附件检索", "PDF下载解析"}
LEGACY_SEARCH_MODE_COMBOS = {
    "内部检索+附件检索",
    "页面检索+附件检索",
    "内部检索+页面检索+附件检索",
    "内部检索+页面检索+附件检索+PDF下载解析",
}
FILE_TYPES = {
    "annual_report",
    "semi_annual_report",
    "quarterly_report",
    "prospectus",
    "rating_report",
}
FINANCIAL_REPORT_TYPES = {"annual_report", "semi_annual_report", "quarterly_report"}
DOCUMENT_STATUS_VALUES = {
    "latest_financial_data",
    "stale_or_prior_period_document",
    "supplemental_document",
}
FULL_RATING_REPORT_TERMS = {
    "评级报告",
    "跟踪评级报告",
    "信用评级报告",
    "主体评级报告",
    "债项评级报告",
}
FINANCIAL_TABLE_KEYS = {
    "periods",
    "balance_sheet",
    "income_statement",
    "cash_flow_statement",
    "business_segments",
}
ENTITY_VERIFICATION_KEYS = {
    "input_name",
    "matched_name_in_document",
    "matched_role",
    "is_same_subject",
    "relationship_to_target",
    "verification_evidence",
    "confidence",
}
ENTITY_CONFIDENCE_VALUES = {"high", "medium", "low"}
ADOPTED_SOURCE_KEYS = {
    "title",
    "attachment_title",
    "file_type",
    "report_period",
    "publish_date",
    "source_url",
    "pdf_url",
    "source_platform",
    "entity_match_result",
    "used_for_main_analysis",
    "used_as_supplement",
    "document_status",
    "entity_verification",
}
SELECTED_DOCUMENT_KEYS = {
    "title",
    "attachment_title",
    "file_type",
    "report_period",
    "publish_date",
    "source_url",
    "pdf_url",
    "source_platform",
    "entity_match_result",
    "used_for_main_analysis",
    "used_as_supplement",
    "document_status",
}
FINDING_REQUIRED_KEYS = {"type", "finding", "evidence", "source_url"}
INDICATOR_REQUIRED_KEYS = {"indicator_name", "current_value", "judgement", "source"}
FINANCIAL_TERMS = {
    "资产负债率",
    "现金短债比",
    "营业收入",
    "净利润",
    "经营性现金流",
    "经营活动现金流",
    "流动比率",
    "速动比率",
    "财务费用",
    "有息债务",
}
QUARTERLY_TERMS = {"一季报", "三季报", "季度报告", "季报", "一季度", "三季度", "第一季度", "第三季度"}
NO_LATEST_DATA_SUMMARY = "未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。"
NO_NEGATIVE_FINDINGS_SUMMARY = "未识别到可由公开披露文件直接支持的重大负面事项。"


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def warn(message: str) -> None:
    print(f"[WARN] {message}")


def contains_any(text: object, terms: set[str]) -> set[str]:
    if not isinstance(text, str):
        return set()
    return {term for term in terms if term in text}


def require_bool(obj: dict, key: str, path: str) -> None:
    if not isinstance(obj.get(key), bool):
        fail(f"{path}.{key} must be boolean")


def require_non_negative_int(obj: dict, key: str, path: str) -> None:
    if not isinstance(obj.get(key), int) or obj.get(key) < 0:
        fail(f"{path}.{key} must be a non-negative integer")


def extract_year(text: object) -> int | None:
    if not isinstance(text, str):
        return None
    match = re.search(r"(20\d{2})", text)
    if not match:
        return None
    return int(match.group(1))


def is_2025_or_later(text: object) -> bool:
    year = extract_year(text)
    return year is not None and year >= 2025


def is_prior_to_2025(text: object) -> bool:
    year = extract_year(text)
    return year is not None and year < 2025


def has_full_rating_report_term(item: dict) -> bool:
    text = " ".join(
        str(item.get(key, ""))
        for key in ("title", "attachment_title", "source_url", "pdf_url")
    )
    return any(term in text for term in FULL_RATING_REPORT_TERMS)


def validate_tables(tables: object, path: str) -> None:
    if not isinstance(tables, dict):
        fail(f"{path} must be an object")
    missing_tables = FINANCIAL_TABLE_KEYS - tables.keys()
    if missing_tables:
        fail(f"Missing {path} keys: {', '.join(sorted(missing_tables))}")
    for key in FINANCIAL_TABLE_KEYS:
        if not isinstance(tables.get(key), list):
            fail(f"{path}.{key} must be a list")


def validate_entity_verification(verification: object, path: str) -> None:
    if not isinstance(verification, dict):
        fail(f"{path} missing entity_verification")
    missing = ENTITY_VERIFICATION_KEYS - verification.keys()
    if missing:
        fail(f"{path}.entity_verification missing keys: {', '.join(sorted(missing))}")
    if not isinstance(verification.get("is_same_subject"), bool):
        fail(f"{path}.entity_verification.is_same_subject must be boolean")
    if verification.get("confidence") not in ENTITY_CONFIDENCE_VALUES:
        fail(f"{path}.entity_verification.confidence must be high, medium, or low")


def validate_selected_document(item: object, path: str) -> None:
    if not isinstance(item, dict):
        fail(f"{path} must be an object")
    missing = SELECTED_DOCUMENT_KEYS - item.keys()
    if missing:
        fail(f"{path} missing keys: {', '.join(sorted(missing))}")
    if item.get("file_type") not in FILE_TYPES:
        fail(f"{path}.file_type invalid")
    if item.get("document_status") not in DOCUMENT_STATUS_VALUES:
        fail(f"{path}.document_status invalid")
    for key in {"used_for_main_analysis", "used_as_supplement"}:
        require_bool(item, key, path)
    for key in {
        "title",
        "attachment_title",
        "report_period",
        "publish_date",
        "source_url",
        "pdf_url",
        "source_platform",
        "entity_match_result",
    }:
        if not isinstance(item.get(key), str):
            fail(f"{path}.{key} must be a string")
    if item.get("source_platform") not in ALLOWED_SOURCES:
        fail(f"{path}.source_platform must be one of the 3 allowed channels")
    if item.get("file_type") in FINANCIAL_REPORT_TYPES:
        if extract_year(item.get("report_period")) is None:
            fail(f"{path}.report_period must identify a year for financial reports")
        if is_prior_to_2025(item.get("report_period")) and item.get("document_status") != "stale_or_prior_period_document":
            fail(f"{path} prior-period financial report must be stale_or_prior_period_document")
        if is_prior_to_2025(item.get("report_period")) and item.get("used_for_main_analysis"):
            fail(f"{path} prior-period financial report cannot be used_for_main_analysis")
    if item.get("file_type") == "rating_report":
        if "评级结果公告" in str(item.get("title", "")) and not has_full_rating_report_term(item):
            fail(f"{path} rating_report cannot be based only on 评级结果公告")
        if not has_full_rating_report_term(item):
            fail(f"{path} rating_report title or attachment must contain a full rating-report term")
    if item.get("file_type") in {"prospectus", "rating_report"}:
        if "disclosed_financial_data_cutoff" not in item:
            fail(f"{path}.disclosed_financial_data_cutoff is required for prospectus and rating_report")
        if not isinstance(item.get("disclosed_financial_data_cutoff"), str):
            fail(f"{path}.disclosed_financial_data_cutoff must be a string")


def validate_source_item(item: object, group: str, idx: int) -> None:
    path = f"sources.{group}[{idx}]"
    if not isinstance(item, dict):
        fail(f"{path} must be an object")
    missing = ADOPTED_SOURCE_KEYS - item.keys()
    if missing:
        fail(f"{path} missing keys: {', '.join(sorted(missing))}")
    if item.get("file_type") not in FILE_TYPES:
        fail(f"{path}.file_type invalid")
    if item.get("document_status") not in DOCUMENT_STATUS_VALUES:
        fail(f"{path}.document_status invalid")
    if group == "financial_report" and item.get("file_type") not in {
        "annual_report",
        "semi_annual_report",
        "quarterly_report",
    }:
        fail(f"{path}.file_type does not match financial_report")
    if group == "prospectus" and item.get("file_type") != "prospectus":
        fail(f"{path}.file_type must be prospectus")
    if group == "rating_report" and item.get("file_type") != "rating_report":
        fail(f"{path}.file_type must be rating_report")
    if group == "rating_report":
        if "评级结果公告" in str(item.get("title", "")) and not has_full_rating_report_term(item):
            fail(f"{path} cannot classify a standalone 评级结果公告 as rating_report")
        if not has_full_rating_report_term(item):
            fail(f"{path} rating_report title or attachment must contain a full rating-report term")
    if item.get("source_platform") not in ALLOWED_SOURCES:
        fail(f"{path}.source_platform must be one of the 3 allowed channels")
    for url_key in ("source_url", "pdf_url"):
        if item.get(url_key):
            validate_url_domain(item[url_key], item.get("source_platform", ""), f"{path}.{url_key}")
    for key in {"used_for_main_analysis", "used_as_supplement"}:
        require_bool(item, key, path)
    for key in {
        "title",
        "report_period",
        "publish_date",
        "source_url",
        "pdf_url",
        "entity_match_result",
    }:
        if not isinstance(item.get(key), str):
            fail(f"{path}.{key} must be a string")
    validate_entity_verification(item.get("entity_verification"), path)
    if item.get("file_type") in FINANCIAL_REPORT_TYPES:
        if group == "financial_report" and is_prior_to_2025(item.get("report_period")):
            fail(f"{path} stale_or_prior_period_document must not enter sources.financial_report")
        if extract_year(item.get("report_period")) is None:
            fail(f"{path}.report_period must identify a year for financial reports")
        if is_prior_to_2025(item.get("report_period")) and item.get("document_status") != "stale_or_prior_period_document":
            fail(f"{path} prior-period financial report must be stale_or_prior_period_document")
        if is_prior_to_2025(item.get("report_period")) and item.get("used_for_main_analysis"):
            fail(f"{path} prior-period financial report cannot be used_for_main_analysis")
        if item.get("document_status") == "latest_financial_data" and not is_2025_or_later(item.get("report_period")):
            fail(f"{path} latest financial data requires report_period in 2025 or later")
    if item.get("file_type") in {"prospectus", "rating_report"} and not isinstance(
        item.get("disclosed_financial_data_cutoff", ""), str
    ):
        fail(f"{path}.disclosed_financial_data_cutoff must be a string")
    if item.get("file_type") in {"prospectus", "rating_report"} and "disclosed_financial_data_cutoff" not in item:
        fail(f"{path}.disclosed_financial_data_cutoff is required for prospectus and rating_report")

def extract_domain(url: object) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    match = re.search(r"https?://([^/:\s]+)", url)
    return match.group(1).lower().removeprefix("www.") if match else None


def platform_for_domain(domain: str) -> str | None:
    for platform, domains in ALLOWED_DOMAINS.items():
        for allowed in domains:
            if domain == allowed or domain.endswith("." + allowed):
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


def validate_query_run(run: object, path: str, source_platform: str = "") -> None:
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
    if not isinstance(run.get("matched_items"), list):
        fail(f"{path}.matched_items must be list")
    for idx, item in enumerate(run.get("matched_items")):
        ipath = f"{path}.matched_items[{idx}]"
        if not isinstance(item, dict):
            fail(f"{ipath} must be an object")
        missing = MATCHED_ITEM_REQUIRED_KEYS - item.keys()
        if missing:
            fail(f"{ipath} missing keys: {', '.join(sorted(missing))}")
        for sk in MATCHED_ITEM_REQUIRED_KEYS - {"decision"}:
            if not isinstance(item.get(sk), str):
                fail(f"{ipath}.{sk} must be string")
        if item.get("decision") not in MATCHED_ITEM_DECISIONS:
            fail(f"{ipath}.decision must be selected or skipped")
        for url_key in ("source_url", "pdf_url"):
            url = item.get(url_key, "")
            if url:
                validate_url_domain(url, source_platform, f"{ipath}.{url_key}")
    if not isinstance(run.get("note"), str):
        fail(f"{path}.note must be string")
    if run.get("total_results") >= 30 and run.get("scanned_result_count") < 30:
        fail(f"{path}.scanned_result_count must be >= 30 when total_results >= 30")
    if run.get("total_results") < 30 and run.get("scanned_result_count") != run.get("total_results"):
        fail(f"{path}.scanned_result_count must equal total_results when < 30")


def main() -> None:
    if len(sys.argv) != 2:
        fail("Usage: validate_output.py <output.json>")

    path = Path(sys.argv[1])
    if not path.exists():
        fail(f"File not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON: {exc}")

    missing = REQUIRED_TOP_LEVEL - data.keys()
    if missing:
        fail(f"Missing top-level keys: {', '.join(sorted(missing))}")

    summary = data.get("negative_summary_under_200_chars", "")
    if not isinstance(summary, str):
        fail("negative_summary_under_200_chars must be a string")
    if len(summary) > 200:
        fail(f"negative summary exceeds 200 characters: {len(summary)}")
    enterprise_name = data.get("enterprise_name", "")
    if not isinstance(enterprise_name, str) or not enterprise_name.strip():
        fail("enterprise_name must be a non-empty string")
    missing_data_note = data.get("missing_data_note", "")
    if not isinstance(missing_data_note, str):
        fail("missing_data_note must be a string")

    # ---- analysis_basis ----
    basis = data.get("analysis_basis", "")
    if basis not in ANALYSIS_BASIS_VALUES:
        fail(f"analysis_basis must be one of: {chr(44).join(sorted(ANALYSIS_BASIS_VALUES))}")

    availability = data.get("data_availability")
    if not isinstance(availability, dict):
        fail("data_availability must be an object")
    required_availability = {
        "has_financial_report",
        "has_prospectus",
        "has_rating_report",
        "has_financial_data",
        "has_public_opinion",
        "data_level",
        "data_limitation_note",
    }
    missing_availability = required_availability - availability.keys()
    if missing_availability:
        fail("Missing data_availability keys: " + ", ".join(sorted(missing_availability)))
    for key in required_availability - {"data_level", "data_limitation_note"}:
        require_bool(availability, key, "data_availability")
    data_level = availability.get("data_level")
    if data_level not in DATA_LEVELS:
        fail("data_availability.data_level must be one of: " + ", ".join(sorted(DATA_LEVELS)))
    if not isinstance(availability.get("data_limitation_note"), str):
        fail("data_availability.data_limitation_note must be a string")
    if data_level == "no_data" and basis != "无有效公开资料":
        fail("analysis_basis must be \"无有效公开资料\" when data_level=no_data")

    source_policy = data.get("source_policy")
    if not isinstance(source_policy, dict):
        fail("source_policy must be an object")
    required_source_policy = {
        "allowed_announcement_sources_only",
        "allowed_sources",
        "external_financial_sources_used",
    }
    missing_source_policy = required_source_policy - source_policy.keys()
    if missing_source_policy:
        fail("Missing source_policy keys: " + ", ".join(sorted(missing_source_policy)))
    if source_policy.get("allowed_announcement_sources_only") is not True:
        fail("source_policy.allowed_announcement_sources_only must be true")
    if source_policy.get("external_financial_sources_used") is not False:
        fail("source_policy.external_financial_sources_used must be false")
    if source_policy.get("allowed_sources") != ALLOWED_SOURCES:
        fail("source_policy.allowed_sources must match the 3 allowed channels exactly")

    freshness = data.get("freshness_gate")
    if not isinstance(freshness, dict):
        fail("freshness_gate must be an object")
    required_freshness = {
        "enabled",
        "cutoff_publish_date",
        "minimum_report_period",
        "latest_document_publish_date",
        "latest_report_period",
        "is_fresh_enough_for_analysis",
        "stop_reason",
    }
    missing_freshness = required_freshness - freshness.keys()
    if missing_freshness:
        fail("Missing freshness_gate keys: " + ", ".join(sorted(missing_freshness)))
    if freshness.get("enabled") is not True:
        fail("freshness_gate.enabled must be true")
    if freshness.get("cutoff_publish_date") != "2025-01-01":
        fail("freshness_gate.cutoff_publish_date must be 2025-01-01")
    if freshness.get("minimum_report_period") != "2025年及之后公开披露":
        fail("freshness_gate.minimum_report_period must be 2025年及之后公开披露")
    if not isinstance(freshness.get("latest_document_publish_date"), str):
        fail("freshness_gate.latest_document_publish_date must be a string")
    if not isinstance(freshness.get("latest_report_period"), str):
        fail("freshness_gate.latest_report_period must be a string")
    if not isinstance(freshness.get("is_fresh_enough_for_analysis"), bool):
        fail("freshness_gate.is_fresh_enough_for_analysis must be boolean")
    if not isinstance(freshness.get("stop_reason"), str):
        fail("freshness_gate.stop_reason must be a string")

    sources = data.get("sources")
    if not isinstance(sources, dict):
        fail("sources must be an object")
    missing_sources = SOURCE_KEYS - sources.keys()
    if missing_sources:
        fail(f"Missing source groups: {', '.join(sorted(missing_sources))}")
    if sources.get("public_opinion"):
        fail("sources.public_opinion must be empty under the current 3-channel policy")

    has_latest_annual_report = False
    has_main_annual_report = False
    has_latest_financial_report = False
    has_fresh_prospectus_or_rating = False
    has_prior_period_financial_report = False
    for group in SOURCE_KEYS:
        items = sources.get(group)
        if not isinstance(items, list):
            fail(f"sources.{group} must be a list")
        if group == "public_opinion":
            continue
        for idx, item in enumerate(items):
            validate_source_item(item, group, idx)
            if item.get("file_type") == "annual_report" and is_2025_or_later(item.get("report_period")):
                has_latest_annual_report = True
                if item.get("used_for_main_analysis") is True:
                    has_main_annual_report = True
            if item.get("file_type") in FINANCIAL_REPORT_TYPES:
                if is_2025_or_later(item.get("report_period")):
                    has_latest_financial_report = True
                if is_prior_to_2025(item.get("report_period")):
                    has_prior_period_financial_report = True
            if item.get("file_type") in {"prospectus", "rating_report"} and is_2025_or_later(
                item.get("publish_date")
            ):
                has_fresh_prospectus_or_rating = True
            if item.get("file_type") == "quarterly_report" and item.get("used_for_main_analysis"):
                if data.get("quarterly_report_used_for_analysis") is not True:
                    fail(
                        f"sources.{group}[{idx}] quarterly_report cannot be used_for_main_analysis "
                        "when quarterly_report_used_for_analysis=false"
                    )

    search_log = data.get("search_log")
    if not isinstance(search_log, list):
        fail("search_log must be a list")
    if len(search_log) != len(ALLOWED_SOURCES):
        fail("search_log must contain exactly 3 entries")
    seen_sources = []
    has_prior_period_selected_financial_report = False
    for idx, item in enumerate(search_log):
        path = f"search_log[{idx}]"
        if not isinstance(item, dict):
            fail(f"{path} must be an object")
        required_search_keys = {
            "source_name",
            "searched",
            "keywords_used",
            "total_results",
            "scanned_result_count",
            "matched_documents",
            "selected_documents",
            "skipped_documents",
            "skipped_reason",
            "download_status",
            "parse_status",
            "latest_document_publish_date",
            "latest_report_period",
            "status",
            "note",
        }
        if "search_modes" not in item and "search_mode" not in item:
            required_search_keys.add("search_modes")
        missing_search_keys = required_search_keys - item.keys()
        if missing_search_keys:
            fail(f"{path} missing keys: " + ", ".join(sorted(missing_search_keys)))
        source_name = item.get("source_name")
        seen_sources.append(source_name)
        if source_name not in ALLOWED_SOURCES:
            fail(f"{path}.source_name must be one of the 3 allowed channels")
        if item.get("searched") is not True:
            fail(f"{path}.searched must be true")
        if "search_modes" in item:
            if not isinstance(item.get("search_modes"), list) or not item.get("search_modes"):
                fail(f"{path}.search_modes must be a non-empty list")
            invalid_modes = [mode for mode in item.get("search_modes") if mode not in SEARCH_MODES]
            if invalid_modes:
                fail(f"{path}.search_modes invalid: {', '.join(invalid_modes)}")
        else:
            if item.get("search_mode") not in SEARCH_MODES | LEGACY_SEARCH_MODE_COMBOS:
                fail(f"{path}.search_mode invalid")
        if not isinstance(item.get("keywords_used"), list) or not item.get("keywords_used"):
            fail(f"{path}.keywords_used must be a non-empty list")
        for key in {"total_results", "scanned_result_count", "matched_documents"}:
            require_non_negative_int(item, key, path)
        if item.get("total_results") >= 30 and item.get("scanned_result_count") < 30:
            fail(f"{path}.scanned_result_count must be at least 30 when total_results >= 30")
        if item.get("total_results") < 30 and item.get("scanned_result_count") != item.get("total_results"):
            fail(f"{path}.scanned_result_count must equal total_results when fewer than 30 results exist")
        if not isinstance(item.get("selected_documents"), list):
            fail(f"{path}.selected_documents must be a list")
        if not isinstance(item.get("skipped_documents"), list):
            fail(f"{path}.skipped_documents must be a list")
        if not isinstance(item.get("skipped_reason"), list):
            fail(f"{path}.skipped_reason must be a list")
        if len(item.get("selected_documents")) > item.get("matched_documents"):
            fail(f"{path}.selected_documents cannot exceed matched_documents")
        for doc_idx, doc in enumerate(item.get("selected_documents")):
            dp = f"{path}.selected_documents[{doc_idx}]"
            validate_selected_document(doc, dp)
            if doc.get("source_platform") != source_name:
                fail(f"{dp}.source_platform must equal outer search_log.source_name")
            for uf in ("source_url", "pdf_url"):
                ud = doc.get(uf, "")
                if ud:
                    validate_url_domain(ud, source_name, f"{dp}.{uf}")
            if doc.get("file_type") in FINANCIAL_REPORT_TYPES and is_prior_to_2025(doc.get("report_period")):
                if doc.get("document_status") != "stale_or_prior_period_document":
                    fail(
                        f"{path}.selected_documents[{doc_idx}] prior-period financial report "
                        "must be stale_or_prior_period_document"
                    )
                has_prior_period_selected_financial_report = True
                if doc.get("used_for_main_analysis"):
                    fail(
                        f"{path}.selected_documents[{doc_idx}] prior-period financial report "
                        "cannot be used_for_main_analysis"
                    )
            if doc.get("file_type") == "rating_report":
                if "评级结果公告" in str(doc.get("title", "")) and not has_full_rating_report_term(doc):
                    fail(
                        f"{path}.selected_documents[{doc_idx}] cannot classify standalone "
                        "评级结果公告 as rating_report"
                    )
        for doc_idx, doc in enumerate(item.get("skipped_documents")):
            sp = f"{path}.skipped_documents[{doc_idx}]"
            if not isinstance(doc, dict):
                fail(f"{sp} must be an object")
            missing_skipped_keys = {"title", "file_type", "source_url", "skipped_reason"} - doc.keys()
            if missing_skipped_keys:
                fail(f"{sp} missing keys: {', '.join(sorted(missing_skipped_keys))}")
            for sk in ("title", "file_type", "source_url", "skipped_reason"):
                if not isinstance(doc.get(sk), str) or not doc.get(sk):
                    fail(f"{sp}.{sk} must be a non-empty string")
            if doc.get("skipped_reason") not in SKIPPED_REASON_VALUES:
                fail(f"{sp}.skipped_reason invalid")
            validate_url_domain(doc.get("source_url", ""), source_name, f"{sp}.source_url")
            if "评级结果公告" in str(doc.get("title", "")) and doc.get("skipped_reason") != "unsupported_file_type":
                warn(
                    f"{path}.skipped_documents[{doc_idx}] 评级结果公告 should normally use "
                    "unsupported_file_type when no full report attachment exists"
                )
        if item.get("download_status") not in DOWNLOAD_STATUS_VALUES:
            fail(f"{path}.download_status invalid")
        if item.get("parse_status") not in PARSE_STATUS_VALUES:
            fail(f"{path}.parse_status invalid")
        if item.get("parse_status") == "failed" and not item.get("parse_failed_reason"):
            fail(f"{path}.parse_failed_reason required when parse_status=failed")
        if not isinstance(item.get("latest_document_publish_date"), str):
            fail(f"{path}.latest_document_publish_date must be a string")
        if not isinstance(item.get("latest_report_period"), str):
            fail(f"{path}.latest_report_period must be a string")
        if item.get("status") not in SEARCH_STATUS_VALUES:
            fail(f"{path}.status invalid")
        if item.get("status") == "matched" and not item.get("selected_documents"):
            fail(f"{path} matched status requires selected_documents")
        if not isinstance(item.get("note"), str):
            fail(f"{path}.note must be a string")
    if set(seen_sources) != set(ALLOWED_SOURCES):
        fail("search_log must include 3 platforms exactly once")

    # ---- sources <-> search_log consistency ----
    all_sl_titles = set()
    all_sl_main = set()
    for si in search_log:
        for d in si.get("selected_documents", []):
            sp = d.get("source_platform", "")
            all_sl_titles.add((d.get("title", ""), d.get("pdf_url", ""), sp))
            if d.get("used_for_main_analysis") is True:
                all_sl_main.add((d.get("title", ""), d.get("pdf_url", ""), sp))
    for group in SOURCE_KEYS:
        if group == "public_opinion":
            continue
        for idx, item in enumerate(sources.get(group, [])):
            t = (item.get("title", ""), item.get("pdf_url", ""), item.get("source_platform", ""))
            if t not in all_sl_titles:
                fail(f"sources.{group}[{idx}] not found in search_log.selected_documents")
    for mt in all_sl_main:
        found_m = False
        for group in SOURCE_KEYS:
            if group == "public_opinion":
                continue
            for it in sources.get(group, []):
                if mt[0] == it.get("title", "") and mt[1] == it.get("pdf_url", "") and mt[2] == it.get("source_platform", ""):
                    found_m = True
                    break
            if found_m:
                break
        if not found_m:
            fail(f"selected_document with used_for_main_analysis=true not found in sources: {mt[0]}")

    # ---- query_runs validation ----
    query_titles_by_platform = {}
    for si in search_log:
        runs = si.get("query_runs")
        if not isinstance(runs, list) or not runs:
            fail(f"search_log.query_runs must be non-empty list for {si.get('source_name', '?')}")
        source_name = si.get("source_name", "")
        main_annual = False
        query_titles = set()
        for ri, run in enumerate(runs):
            validate_query_run(run, f"search_log.query_runs[{ri}]", source_name)
            query_titles.update(str(title) for title in run.get("matched_titles", []))
            query_titles.update(str(title) for title in run.get("selected_titles", []))
            if ri == 0 and run.get("annual_report_found") is True:
                main_annual = True
        query_titles_by_platform[source_name] = query_titles
        if not main_annual:
            required_directed = [
                f"{enterprise_name} 年度报告",
                f"{enterprise_name} 年报",
                f"{enterprise_name} 审计报告",
                f"{enterprise_name} 年度财务报表",
                f"{enterprise_name} 合并及母公司财务报表",
            ]
            run_keywords = {run.get("keyword", "") for run in runs[1:]}
            missing_directed = [kw for kw in required_directed if kw not in run_keywords]
            if missing_directed:
                fail(
                    "main search found no annual_report; missing directed annual-report query_runs: "
                    + ", ".join(missing_directed)
                )

    for idx, item in enumerate(sources.get("financial_report", [])):
        if item.get("file_type") == "annual_report":
            platform_titles = query_titles_by_platform.get(item.get("source_platform", ""), set())
            if item.get("title", "") not in platform_titles:
                fail(
                    f"sources.financial_report[{idx}] annual_report title must appear in "
                    "query_runs.matched_titles or selected_titles"
                )

    if has_latest_annual_report and not has_main_annual_report:
        fail("At least one latest annual_report must be used_for_main_analysis=true")
    if freshness.get("is_fresh_enough_for_analysis") is True and not (
        has_latest_financial_report or has_fresh_prospectus_or_rating
    ):
        fail(
            "freshness_gate.is_fresh_enough_for_analysis=true requires a financial report "
            "with report_period in 2025 or later or a prospectus/rating report published in 2025 or later"
        )

    if data_level in {"full", "partial_financial"}:
        has_financial_source = any(sources.get(key) for key in FINANCIAL_SOURCE_KEYS)
        if not has_financial_source:
            fail(f"{data_level} requires at least one financial source")
        if not availability.get("has_financial_data"):
            fail(f"{data_level} requires has_financial_data=true")
        if freshness.get("is_fresh_enough_for_analysis") is not True:
            fail(f"{data_level} requires freshness_gate.is_fresh_enough_for_analysis=true")
        if not (has_latest_financial_report or has_fresh_prospectus_or_rating):
            fail(
                f"{data_level} requires a financial report with report_period in 2025 or later "
                "or a prospectus/rating report published in 2025 or later"
            )
    if data_level == "full" and not has_latest_financial_report:
        fail("full requires at least one financial report with report_period in 2025 or later")
    if data_level == "full" and has_prior_period_financial_report and not has_latest_financial_report:
        fail("prior-period financial reports cannot make data_level=full")
    has_supplemental_financial_source = bool(sources.get("prospectus") or sources.get("rating_report"))
    if not sources.get("financial_report") and has_supplemental_financial_source:
        if data_level == "full":
            fail("prospectus/rating-only data cannot make data_level=full")
        if data.get("data_period_type") == "三年一期":
            fail("prospectus/rating-only data must not claim a complete 三年一期 financial table")
        required_note = "未取得正式财务报告，仅基于募集说明书/评级报告披露内容摘录"
        if required_note not in missing_data_note:
            fail("missing_data_note must explain prospectus/rating-only limitations")
    if has_prior_period_selected_financial_report and not (
        has_latest_financial_report or has_fresh_prospectus_or_rating
    ):
        if data_level != "no_data":
            fail("stale-only financial reports require data_level=no_data")
        if summary != NO_LATEST_DATA_SUMMARY:
            fail("stale-only financial reports require the fixed no-data summary")

    findings = data.get("negative_findings")
    if not isinstance(findings, list):
        fail("negative_findings must be a list")
    for idx, item in enumerate(findings):
        if not isinstance(item, dict):
            fail(f"negative_findings[{idx}] must be an object")
        missing_finding_keys = [key for key in FINDING_REQUIRED_KEYS if not item.get(key)]
        if missing_finding_keys:
            fail(f"negative_findings[{idx}] missing required keys: " + ", ".join(missing_finding_keys))
        if "舆情" in str(item.get("type", "")):
            fail("negative_findings must not include public-opinion findings")
        surl = item.get("source_url", "")
        if surl:
            validate_url_domain(surl, "", f"negative_findings[{idx}].source_url")
    if not findings and data_level in {"full", "partial_financial"}:
        if summary != NO_NEGATIVE_FINDINGS_SUMMARY:
            fail(
                "When valid financial data exists but negative_findings is empty, "
                "summary must be the fixed no-negative-findings sentence"
            )

    validate_tables(data.get("financial_tables"), "financial_tables")
    validate_tables(data.get("supplemental_financial_tables"), "supplemental_financial_tables")
    tables = data.get("financial_tables")
    supplemental_tables = data.get("supplemental_financial_tables")

    indicators = data.get("financial_indicators")
    if not isinstance(indicators, list):
        fail("financial_indicators must be a list")
    for idx, item in enumerate(indicators):
        if not isinstance(item, dict):
            fail(f"financial_indicators[{idx}] must be an object")
        missing_indicator_keys = [key for key in INDICATOR_REQUIRED_KEYS if not item.get(key)]
        if missing_indicator_keys:
            fail(f"financial_indicators[{idx}] missing required keys: " + ", ".join(missing_indicator_keys))
        src = str(item.get("source", ""))
        if "http" in src:
            url_match = re.search(r"https?://[^\s)\]]+", src)
            if url_match:
                validate_url_domain(url_match.group(0), "", f"financial_indicators[{idx}].source")

    # ---- table url domains ----
    for tname, tdata in [("financial_tables", tables), ("supplemental_financial_tables", supplemental_tables)]:
        for u, upath in collect_table_urls(tdata, tname):
            validate_url_domain(u, "", upath)

    if data_level == "no_data":
        if availability.get("has_financial_data"):
            fail("no_data requires has_financial_data=false")
        if findings:
            fail("no_data must not include negative_findings")
        if indicators:
            fail("no_data must not include financial_indicators")
        non_empty_tables = [
            key
            for key in FINANCIAL_TABLE_KEYS
            if tables.get(key) or supplemental_tables.get(key)
        ]
        if non_empty_tables:
            fail("no_data must not include financial table data: " + ", ".join(sorted(non_empty_tables)))
        if summary != NO_LATEST_DATA_SUMMARY:
            fail("no_data requires the fixed latest-disclosure no-data summary")

    if freshness.get("is_fresh_enough_for_analysis") is False:
        if data_level != "no_data":
            fail("stale freshness gate requires data_level=no_data")
        if availability.get("has_financial_data"):
            fail("stale freshness gate requires has_financial_data=false")
        if summary != NO_LATEST_DATA_SUMMARY:
            fail("stale freshness gate requires the fixed no-data summary")
        if not freshness.get("stop_reason"):
            fail("stale freshness gate requires stop_reason")

    if not availability.get("has_financial_data"):
        summary_financial_terms = contains_any(summary, FINANCIAL_TERMS)
        if summary_financial_terms:
            fail(
                "Summary mentions financial indicators while has_financial_data=false: "
                + ", ".join(sorted(summary_financial_terms))
            )

    if not data.get("quarterly_report_used_for_analysis"):
        quarter_text_fields = [summary]
        quarter_text_fields.extend(
            str(item.get("finding", "")) + " " + str(item.get("evidence", ""))
            for item in findings
            if isinstance(item, dict)
        )
        quarter_text_fields.extend(
            str(item.get("source", "")) + " " + str(item.get("judgement", ""))
            for item in indicators
            if isinstance(item, dict)
        )
        for text in quarter_text_fields:
            found_terms = contains_any(text, QUARTERLY_TERMS)
            if found_terms:
                fail(
                    "quarterly_report_used_for_analysis=false but quarterly basis appears in "
                    "summary, negative findings, or indicators: "
                    + ", ".join(sorted(found_terms))
                )

    print("[OK] post-loan analysis JSON passed basic validation")


if __name__ == "__main__":
    main()
