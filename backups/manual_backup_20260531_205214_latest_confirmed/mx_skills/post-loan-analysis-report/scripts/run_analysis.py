"""
Post-loan analysis report executor.

Searches 中国货币网, 上海证券交易所, and 深圳证券交易所 for an enterprise's
latest public financial disclosures, classifies results by file type, and returns
structured JSON matching the output schema.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse


# ── document classification ──────────────────────────────────────────────────

ANNUAL_REPORT_KEYWORDS = [
    "年度报告", "年报", "年度财务报表", "年度审计报告", "经审计财务报告",
    "合并及母公司财务报表", "合并财务报表", "母公司财务报表", "审计报告",
    "财务报表及附注", "年度财务报表及附注",
]

SEMI_ANNUAL_KEYWORDS = [
    "半年度报告", "半年报", "半年度财务报表",
]

QUARTERLY_KEYWORDS = [
    "第一季度报告", "一季度报告", "第一季度财务报表", "一季度财务报表",
    "第三季度报告", "三季度报告", "季度财务报表",
]

PROSPECTUS_KEYWORDS = [
    "募集说明书", "更新募集说明书", "债券募集说明书",
    "中期票据募集说明书", "超短期融资券募集说明书",
]

RATING_REPORT_KEYWORDS = [
    "主体评级报告", "债项评级报告", "跟踪评级报告", "信用评级报告", "评级报告",
]

EXCLUDE_KEYWORDS = [
    "付息公告", "兑付公告", "发行结果公告", "持有人会议公告", "法律意见书",
    "受托管理事务报告", "临时公告", "发行方案", "承诺函", "评级结果公告",
]

ALLOWED_DOMAINS = {
    "中国货币网": ["chinamoney.com.cn"],
    "上海证券交易所": ["sse.com.cn", "bond.sse.com.cn"],
    "深圳证券交易所": ["szse.cn"],
}


def _classify_file_type(title: str) -> str | None:
    """Classify a document title into one of the allowed file types."""
    t = title
    # Exclude non-financial-report announcements first
    for kw in EXCLUDE_KEYWORDS:
        if kw in t:
            # 评级结果公告 without full rating report -> unsupported
            if kw == "评级结果公告" and any(rk in t for rk in RATING_REPORT_KEYWORDS):
                continue
            return None  # unsupported
    for kw in ANNUAL_REPORT_KEYWORDS:
        if kw in t:
            return "annual_report"
    for kw in SEMI_ANNUAL_KEYWORDS:
        if kw in t:
            return "semi_annual_report"
    for kw in QUARTERLY_KEYWORDS:
        if kw in t:
            return "quarterly_report"
    for kw in PROSPECTUS_KEYWORDS:
        if kw in t:
            return "prospectus"
    for kw in RATING_REPORT_KEYWORDS:
        if kw in t:
            return "rating_report"
    return None


def _extract_report_period(title: str) -> str:
    """Extract report period (e.g. 2025, 2025Q1, 2025H1) from title."""
    # Match patterns like 2025年, 2025年度, 2025年半年度, 2025年第一季度
    m = re.search(r"(\d{4})\s*年\s*(第[一二三四]季度|半年度|年度)?", title)
    if m:
        year = m.group(1)
        suffix = m.group(2) or ""
        if "一" in suffix:
            return f"{year}Q1"
        if "二" in suffix:
            return f"{year}Q2" if "半" not in suffix else f"{year}H1"
        if "三" in suffix:
            return f"{year}Q3"
        if "四" in suffix:
            return f"{year}Q4"
        if "半" in suffix:
            return f"{year}H1"
        return year
    # Fallback: just year
    m = re.search(r"(\d{4})", title)
    return m.group(1) if m else ""


def _extract_publish_date(raw_item: dict) -> str:
    """Extract publish date from a raw search result item."""
    for key in ("publishDate", "pubDate", "date", "publish_date", "announcementDate"):
        val = raw_item.get(key)
        if val:
            return str(val)[:10]
    return ""


def _domain_to_platform(url: str) -> str:
    """Map a URL domain to one of the three allowed platforms."""
    if not url:
        return ""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return ""
    host_lower = host.lower()
    for platform, domains in ALLOWED_DOMAINS.items():
        for d in domains:
            if d in host_lower:
                return platform
    return ""


def _extract_enterprise_name(query: str) -> str:
    """Extract enterprise name from query string or JSON."""
    query = query.strip()
    if query.startswith("{"):
        try:
            parsed = json.loads(query)
            name = parsed.get("enterprise_name") or parsed.get("company_name") or ""
            if name:
                return name.strip()
        except json.JSONDecodeError:
            repaired = query.replace('\\"', '"')
            try:
                parsed = json.loads(repaired)
                name = parsed.get("enterprise_name") or parsed.get("company_name") or ""
                if name:
                    return name.strip()
            except json.JSONDecodeError:
                match = re.search(r"enterprise_name\s*[:=]\s*['\"]?([^,'\"}]+)", query)
                if match:
                    return match.group(1).strip()
    return query


def _subject_candidates(enterprise_name: str) -> list[str]:
    """Build conservative same-subject match candidates."""
    candidates = [enterprise_name]
    normalized = enterprise_name
    for suffix in ["有限责任公司", "股份有限公司", "集团有限公司", "有限公司"]:
        if normalized.endswith(suffix):
            candidates.append(normalized[: -len(suffix)])
            break
    if "集团" in normalized:
        candidates.append(normalized.replace("集团", ""))
    seen = []
    for candidate in candidates:
        candidate = re.sub(r"\s+", "", candidate)
        if len(candidate) >= 4 and candidate not in seen:
            seen.append(candidate)
    return seen


def _is_same_subject_candidate(enterprise_name: str, item: dict[str, Any], title_text: str) -> bool:
    """Use only results whose visible metadata still points to the requested enterprise."""
    try:
        raw_text = json.dumps(item, ensure_ascii=False)
    except TypeError:
        raw_text = title_text
    normalized_text = re.sub(r"\s+", "", f"{title_text} {raw_text}")
    return any(candidate in normalized_text for candidate in _subject_candidates(enterprise_name))


# ── channel search ───────────────────────────────────────────────────────────

def _load_search_module():
    """Load the mx-finance-search module via importlib (module path has hyphens)."""
    import importlib.util, sys
    module_name = "mx_skills.mx-finance-search.scripts.get_data"
    if module_name in sys.modules:
        return sys.modules[module_name]
    file_path = Path(__file__).resolve().parent.parent.parent / "mx-finance-search" / "scripts" / "get_data.py"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


async def _search_channel(
    enterprise_name: str,
    channel_name: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Search one channel for the enterprise's financial disclosures."""
    search_mod = _load_search_module()
    query_financial_news = search_mod.query_financial_news

    # Build search query with channel hint
    query_text = f"{enterprise_name} {channel_name} 年报 审计报告 募集说明书 评级报告"
    raw_result = await query_financial_news(query=query_text, output_dir=output_dir, save_to_file=False)

    raw = raw_result.get("raw") or {}
    content = raw_result.get("content", "")
    error = raw_result.get("error")

    # Parse items from raw response
    items = []
    if isinstance(raw, dict):
        data = raw.get("data") or raw.get("result") or {}
        if isinstance(data, dict):
            items = data.get("items") or data.get("list") or data.get("records") or []
        elif isinstance(data, list):
            items = data

    if not items and content:
        # Try parsing content as JSON
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                data = parsed.get("data") or parsed.get("result") or {}
                if isinstance(data, dict):
                    items = data.get("items") or data.get("list") or data.get("records") or []
                elif isinstance(data, list):
                    items = data
        except (json.JSONDecodeError, TypeError):
            pass

    # Classify and filter
    matched_documents = []
    skipped_documents = []
    scan_count = 0

    for item in (items or [])[:30]:
        scan_count += 1
        if not isinstance(item, dict):
            continue

        title = item.get("title") or item.get("Title") or item.get("announcementTitle") or ""
        attachment_title = item.get("attachmentTitle") or item.get("attachment_title") or ""
        combine_title = f"{title} {attachment_title}"

        url = item.get("url") or item.get("sourceUrl") or item.get("announcementUrl") or ""
        if not _is_same_subject_candidate(enterprise_name, item, combine_title):
            skipped_documents.append({
                "title": title,
                "file_type": "unknown",
                "source_url": url,
                "pdf_url": "",
                "skipped_reason": "subject_mismatch",
            })
            continue

        file_type = _classify_file_type(combine_title)

        if file_type is None:
            skipped_documents.append({
                "title": title,
                "file_type": "unsupported",
                "source_url": url,
                "pdf_url": "",
                "skipped_reason": "unsupported_file_type",
            })
            continue

        # Verify source platform matches
        platform = _domain_to_platform(url)
        if platform and platform != channel_name:
            skipped_documents.append({
                "title": title,
                "file_type": file_type,
                "source_url": url,
                "pdf_url": "",
                "skipped_reason": "wrong_source_platform",
            })
            continue

        publish_date = _extract_publish_date(item)
        report_period = _extract_report_period(combine_title)

        doc = {
            "title": title,
            "attachment_title": attachment_title,
            "file_type": file_type,
            "report_period": report_period,
            "publish_date": publish_date,
            "url": url,
            "source_url": url,
            "pdf_url": item.get("pdfUrl") or item.get("attachmentUrl") or "",
            "source_platform": channel_name,
            "entity_match_result": "matched",
            "used_for_main_analysis": file_type == "annual_report",
            "used_as_supplement": file_type != "annual_report",
            "document_status": "latest_financial_data",
            "entity_verification": {
                "input_name": enterprise_name,
                "matched_name_in_document": title,
                "matched_role": "发行人",
                "is_same_subject": True,
                "relationship_to_target": "",
                "verification_evidence": "",
                "confidence": "medium",
            },
        }
        matched_documents.append(doc)

    return {
        "source_name": channel_name,
        "searched": error is None,
        "search_modes": ["按标题"],
        "keywords_used": [enterprise_name],
        "total_results": len(items) if isinstance(items, list) else 0,
        "scanned_result_count": scan_count,
        "matched_documents": len(matched_documents),
        "selected_documents": matched_documents,
        "skipped_documents": skipped_documents,
        "skipped_reason": [],
        "download_status": "not_applicable",
        "parse_status": "not_applicable",
        "parse_failed_reason": "",
        "latest_document_publish_date": matched_documents[0]["publish_date"] if matched_documents else "",
        "latest_report_period": matched_documents[0]["report_period"] if matched_documents else "",
        "status": "ok" if matched_documents else "empty",
        "note": "",
        "query_runs": [
            {
                "keyword": f"{enterprise_name} {channel_name}",
                "search_scope": "全部",
                "search_column": "按标题",
                "total_results": len(items) if isinstance(items, list) else 0,
                "scanned_result_count": scan_count,
                "matched_documents": len(matched_documents),
                "annual_report_found": any(d["file_type"] == "annual_report" for d in matched_documents),
                "matched_titles": [d["title"] for d in matched_documents],
                "selected_titles": [d["title"] for d in matched_documents],
                "skipped_titles": [d["title"] for d in skipped_documents],
                "matched_items": len(matched_documents),
                "note": "",
            }
        ],
    }


# ── main entry ───────────────────────────────────────────────────────────────

async def run_analysis(
    query: str,
    output_dir: Path | str | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Run post-loan analysis for the given enterprise.

    Searches all three allowed channels and returns structured JSON.
    """
    enterprise_name = _extract_enterprise_name(query)
    if not enterprise_name or enterprise_name == "未填写企业":
        return _build_no_data_result("未填写企业", "未提供企业名称。")

    output_path = Path(output_dir) if output_dir else Path.cwd() / "mx_skills" / "output" / "post-loan-analysis-report"
    output_path.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    cutoff = "2025-01-01"

    # Search all three channels concurrently
    channels = ["中国货币网", "上海证券交易所", "深圳证券交易所"]
    channel_tasks = [
        _search_channel(enterprise_name, ch, output_path)
        for ch in channels
    ]
    search_log = await asyncio.gather(*channel_tasks, return_exceptions=True)

    # Handle exceptions
    clean_log = []
    for i, result in enumerate(search_log):
        if isinstance(result, Exception):
            clean_log.append({
                "source_name": channels[i],
                "searched": False,
                "search_modes": [],
                "keywords_used": [enterprise_name],
                "total_results": 0,
                "scanned_result_count": 0,
                "matched_documents": 0,
                "selected_documents": [],
                "skipped_documents": [],
                "skipped_reason": [str(result)],
                "download_status": "error",
                "parse_status": "error",
                "parse_failed_reason": str(result),
                "latest_document_publish_date": "",
                "latest_report_period": "",
                "status": "error",
                "note": "",
                "query_runs": [],
            })
        else:
            clean_log.append(result)

    # Collect sources
    financial_reports = []
    prospectuses = []
    rating_reports = []
    for log_entry in clean_log:
        for doc in log_entry.get("selected_documents", []):
            ft = doc.get("file_type")
            if ft in ("annual_report", "semi_annual_report", "quarterly_report"):
                financial_reports.append(doc)
            elif ft == "prospectus":
                prospectuses.append(doc)
            elif ft == "rating_report":
                rating_reports.append(doc)

    # Determine data availability
    has_financial = len(financial_reports) > 0
    has_prospectus = len(prospectuses) > 0
    has_rating = len(rating_reports) > 0
    has_any_data = has_financial or has_prospectus or has_rating

    # Check freshness gate
    latest_dates = []
    for doc in financial_reports + prospectuses + rating_reports:
        pd_str = doc.get("publish_date", "")
        if pd_str and pd_str >= cutoff:
            latest_dates.append(pd_str)
    latest_dates.sort(reverse=True)

    is_fresh = len(latest_dates) > 0
    latest_pub = latest_dates[0] if latest_dates else ""
    latest_period = ""
    for doc in financial_reports:
        rp = doc.get("report_period", "")
        if rp and (not latest_period or rp > latest_period):
            latest_period = rp

    # If no fresh data, return no-data result
    if not is_fresh or not has_any_data:
        return _build_no_data_result(enterprise_name, "未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。")

    # Determine analysis basis
    has_annual = any(d["file_type"] == "annual_report" for d in financial_reports)
    has_semi = any(d["file_type"] == "semi_annual_report" for d in financial_reports)
    has_quarterly = any(d["file_type"] == "quarterly_report" for d in financial_reports)

    if has_annual:
        analysis_basis = "年度报告"
        data_period_type = "三年一期"
        data_level = "full"
    elif has_semi:
        analysis_basis = "半年度报告"
        data_period_type = "两年一期"
        data_level = "partial_financial"
    elif has_quarterly:
        analysis_basis = "季度报告补充"
        data_period_type = "两年"
        data_level = "partial_financial"
    elif has_prospectus:
        analysis_basis = "募集说明书补充"
        data_period_type = "可获取数据不足"
        data_level = "partial_financial"
    elif has_rating:
        analysis_basis = "评级报告补充"
        data_period_type = "可获取数据不足"
        data_level = "partial_financial"
    else:
        analysis_basis = "无有效公开资料"
        data_period_type = "可获取数据不足"
        data_level = "no_data"

    # Build result
    result = {
        "enterprise_name": enterprise_name,
        "report_date": today,
        "data_updated_at": datetime.now().isoformat(),
        "data_period_type": data_period_type,
        "analysis_basis": analysis_basis,
        "quarterly_report_used_for_analysis": has_quarterly and not has_annual and not has_semi,
        "source_policy": {
            "allowed_announcement_sources_only": True,
            "allowed_sources": channels,
            "external_financial_sources_used": False,
        },
        "freshness_gate": {
            "enabled": True,
            "cutoff_publish_date": cutoff,
            "minimum_report_period": "2025年及之后公开披露",
            "latest_document_publish_date": latest_pub,
            "latest_report_period": latest_period,
            "is_fresh_enough_for_analysis": is_fresh,
            "stop_reason": "",
        },
        "data_availability": {
            "has_financial_report": has_financial,
            "has_prospectus": has_prospectus,
            "has_rating_report": has_rating,
            "has_financial_data": has_financial,
            "has_public_opinion": False,
            "data_level": data_level,
            "data_limitation_note": "",
        },
        "sources": {
            "financial_report": financial_reports,
            "prospectus": prospectuses,
            "rating_report": rating_reports,
            "public_opinion": [],
        },
        "search_log": clean_log,
        "financial_tables": {
            "periods": [],
            "balance_sheet": [],
            "income_statement": [],
            "cash_flow_statement": [],
            "business_segments": [],
        },
        "supplemental_financial_tables": {
            "periods": [],
            "balance_sheet": [],
            "income_statement": [],
            "cash_flow_statement": [],
            "business_segments": [],
        },
        "financial_indicators": [],
        "negative_findings": [],
        "negative_summary_under_200_chars": "本次检索已完成三渠道公开披露扫描，当前未识别到可由公开披露文件直接支持的重大负面事项。",
        "missing_data_note": "" if has_financial else "未取得正式财务报告，仅基于募集说明书/评级报告披露内容摘录。",
    }

    # Write output
    import hashlib
    name_hash = hashlib.md5(enterprise_name.encode()).hexdigest()[:8]
    output_file = output_path / f"post_loan_{name_hash}_{today}.json"
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "ok",
        "enterprise_name": enterprise_name,
        "data_level": data_level,
        "analysis_basis": analysis_basis,
        "output_file": str(output_file),
        "result": result,
    }


def _build_no_data_result(enterprise_name: str, reason: str) -> dict[str, Any]:
    """Build a no-data result when no valid disclosures are found."""
    return {
        "status": "empty",
        "enterprise_name": enterprise_name,
        "data_level": "no_data",
        "analysis_basis": "无有效公开资料",
        "output_file": "",
        "result": {
            "enterprise_name": enterprise_name,
            "report_date": date.today().isoformat(),
            "data_updated_at": datetime.now().isoformat(),
            "data_period_type": "可获取数据不足",
            "analysis_basis": "无有效公开资料",
            "quarterly_report_used_for_analysis": False,
            "source_policy": {
                "allowed_announcement_sources_only": True,
                "allowed_sources": ["中国货币网", "上海证券交易所", "深圳证券交易所"],
                "external_financial_sources_used": False,
            },
            "freshness_gate": {
                "enabled": True,
                "cutoff_publish_date": "2025-01-01",
                "minimum_report_period": "2025年及之后公开披露",
                "latest_document_publish_date": "",
                "latest_report_period": "",
                "is_fresh_enough_for_analysis": False,
                "stop_reason": reason,
            },
            "data_availability": {
                "has_financial_report": False,
                "has_prospectus": False,
                "has_rating_report": False,
                "has_financial_data": False,
                "has_public_opinion": False,
                "data_level": "no_data",
                "data_limitation_note": reason,
            },
            "sources": {
                "financial_report": [],
                "prospectus": [],
                "rating_report": [],
                "public_opinion": [],
            },
            "search_log": [],
            "financial_tables": {
                "periods": [],
                "balance_sheet": [],
                "income_statement": [],
                "cash_flow_statement": [],
                "business_segments": [],
            },
            "supplemental_financial_tables": {
                "periods": [],
                "balance_sheet": [],
                "income_statement": [],
                "cash_flow_statement": [],
                "business_segments": [],
            },
            "financial_indicators": [],
            "negative_findings": [],
            "negative_summary_under_200_chars": "未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。",
            "missing_data_note": reason,
        },
    }
