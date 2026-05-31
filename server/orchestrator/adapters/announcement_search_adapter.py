"""
Orchestrator Adapter: Skill 1 – 公告搜索

封装对 announcement_search_skill 的调用，将搜索结果标准化为 source_documents[]。

修复要点：
- 定义标准 Skill 1 输出接口，Orchestrator 只读标准化字段
- 如果仍需要兼容当前 Skill 1，格式转换逻辑在 adapter 内
- 不再直接依赖 Skill 1 内部模块路径
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any

# 项目根目录
def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    for _ in range(6):
        if (current / "mx_skills").is_dir() and (current / "server").is_dir():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent.parent

PROJECT_ROOT = _find_project_root()
OUTPUT_DIR = PROJECT_ROOT / "mx_skills" / "output"


async def run_announcement_search(
    enterprise_name: str,
    task_id: str,
    report_period: str | None = None,
) -> dict[str, Any]:
    """
    调用 Skill 1: 公告搜索。

    返回标准接口：
    {
        "status": "ok" | "empty" | "error",
        "enterprise_name": str,
        "task_id": str,
        "source_documents": [...],
        "search_log": [...],
        "errors": [...],
    }
    """
    try:
        # 动态加载当前 Skill 1 实现
        skill_dir = PROJECT_ROOT / "mx_skills" / "post-loan-analysis-report" / "scripts"
        module_path = skill_dir / "run_analysis.py"

        if not module_path.exists():
            return {
                "status": "error",
                "enterprise_name": enterprise_name,
                "task_id": task_id,
                "source_documents": [],
                "search_log": [],
                "errors": [f"Skill 1 模块不存在: {module_path}"],
            }

        spec = importlib.util.spec_from_file_location("run_analysis_post_loan", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        query_parts = [enterprise_name]
        if report_period:
            query_parts.append(report_period)
        query = " ".join(query_parts)

        result = await asyncio.to_thread(module.run_analysis, query)

        # 标准化转换
        source_docs = _normalize_to_source_documents(result, enterprise_name, task_id)

        return {
            "status": "ok" if source_docs else "empty",
            "enterprise_name": enterprise_name,
            "task_id": task_id,
            "source_documents": source_docs,
            "search_log": result.get("result", {}).get("search_log", []),
            "errors": [],
        }

    except Exception as e:
        return {
            "status": "error",
            "enterprise_name": enterprise_name,
            "task_id": task_id,
            "source_documents": [],
            "search_log": [],
            "errors": [str(e)],
        }


def _normalize_to_source_documents(
    raw_result: dict[str, Any],
    enterprise_name: str,
    task_id: str,
) -> list[dict[str, Any]]:
    """将 Skill 1 原始输出转换为标准 source_documents[]"""
    sources = []
    seen_ids = set()
    inner = raw_result.get("result", {})

    # 从 sources 中提取
    sources_section = inner.get("sources", {})
    for category in ["financial_report", "prospectus", "rating_report"]:
        for item in sources_section.get(category, []):
            title = item.get("title", "")
            doc_id = _make_doc_id(enterprise_name, title, task_id)
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)

            file_type = item.get("file_type", "")
            if file_type not in ("annual_report", "semi_annual_report", "quarterly_report",
                                 "prospectus", "rating_report"):
                file_type = "unsupported_file_type"

            sources.append({
                "document_id": doc_id,
                "source_platform": item.get("source_platform", ""),
                "title": title,
                "attachment_title": item.get("attachment_title", ""),
                "file_type": file_type,
                "report_period": item.get("report_period", ""),
                "publish_date": item.get("publish_date", ""),
                "source_url": item.get("source_url") or item.get("url", ""),
                "pdf_url": item.get("pdf_url", ""),
                "local_pdf_path": item.get("download_path", ""),
                "pdf_download_status": _map_ds(item.get("download_status", "")),
                "pdf_sha256": "",
                "document_status": _map_status(item),
                "selection_reason": "",
                "skipped_reason": "",
                "entity_verification": item.get("entity_verification", {
                    "input_name": enterprise_name,
                    "matched_name_in_document": "",
                    "matched_role": "不确定",
                    "is_same_subject": False,
                    "verification_evidence": "",
                    "confidence": "low",
                }),
                "needs_deep_pdf_parse": file_type not in ("unsupported_file_type",),
            })

    # 从 search_log 中提取 selected_documents
    for log_entry in inner.get("search_log", []):
        for sel in log_entry.get("selected_documents", []):
            title = sel.get("title", "")
            doc_id = _make_doc_id(enterprise_name, title, task_id)
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)

            file_type = sel.get("file_type", "")
            if file_type not in ("annual_report", "semi_annual_report", "quarterly_report",
                                 "prospectus", "rating_report"):
                file_type = "unsupported_file_type"

            sources.append({
                "document_id": doc_id,
                "source_platform": log_entry.get("source_name", ""),
                "title": title,
                "attachment_title": sel.get("attachment_title", ""),
                "file_type": file_type,
                "report_period": sel.get("report_period", ""),
                "publish_date": sel.get("publish_date", ""),
                "source_url": sel.get("source_url") or sel.get("url", ""),
                "pdf_url": sel.get("pdf_url", ""),
                "local_pdf_path": sel.get("download_path", ""),
                "pdf_download_status": _map_ds(sel.get("download_status", "")),
                "pdf_sha256": "",
                "document_status": "selected_main" if sel.get("used_for_main_analysis") else "selected_supplement",
                "selection_reason": "",
                "skipped_reason": "",
                "entity_verification": sel.get("entity_verification", {
                    "input_name": enterprise_name,
                    "matched_name_in_document": "",
                    "matched_role": "不确定",
                    "is_same_subject": False,
                    "verification_evidence": "",
                    "confidence": "low",
                }),
                "needs_deep_pdf_parse": True,
            })

    return sources


def _make_doc_id(enterprise_name: str, title: str, task_id: str) -> str:
    raw = f"{enterprise_name}|{title}|{task_id}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _map_ds(status: str) -> str:
    mapping = {"success": "success", "failed": "failed"}
    return mapping.get(status, "skipped")


def _map_status(item: dict[str, Any]) -> str:
    status = item.get("document_status", "")
    valid = {"selected_main", "selected_supplement", "skipped",
             "stale_or_prior_period_document", "subject_mismatch",
             "unsupported_file_type", "download_failed"}
    return status if status in valid else "skipped"
