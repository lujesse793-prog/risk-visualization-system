"""Adapter for Skill1 announcement source discovery."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from ..paths import OUTPUT_DIR, PDF_DIR, SKILLS_DIR, as_posix_path


ALLOWED_FILE_TYPES = {
    "annual_report",
    "semi_annual_report",
    "quarterly_report",
    "prospectus",
    "rating_report",
}
ALLOWED_PARSE_STATUSES = {"selected_main", "selected_supplement"}
BLOCKED_PARSE_STATUSES = {
    "subject_mismatch",
    "stale_or_prior_period_document",
    "download_failed",
    "unsupported_file_type",
}


async def run_announcement_search(
    enterprise_name: str,
    task_id: str,
    report_period: str | None = None,
    run_date: str | None = None,
) -> dict[str, Any]:
    """Call Skill1 and preserve its standard handoff contract."""
    raw_result = await _load_skill1_result(enterprise_name, task_id, report_period, run_date)
    result = _unwrap_skill1_result(raw_result, enterprise_name, task_id)

    source_documents = result.get("source_documents", [])
    search_log = result.get("search_log", [])
    freshness_gate = result.get("freshness_gate", {})
    data_availability = result.get("data_availability", {})
    pdf_handoff = result.get("pdf_handoff")

    if not isinstance(pdf_handoff, dict):
        pdf_handoff = _build_compatible_pdf_handoff(source_documents, enterprise_name, task_id)
        result.setdefault("errors", []).append("Skill1 output missing standard pdf_handoff")

    pdf_handoff = _validated_pdf_handoff(pdf_handoff, source_documents, enterprise_name, task_id)
    handoff_path = OUTPUT_DIR / "orchestrator" / task_id / "skill1_pdf_handoff.json"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(json.dumps(pdf_handoff, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "enterprise_name": enterprise_name,
        "task_id": task_id,
        "source_documents": source_documents,
        "search_log": search_log,
        "freshness_gate": freshness_gate,
        "data_availability": data_availability,
        "pdf_handoff": pdf_handoff,
        "pdf_handoff_path": as_posix_path(handoff_path),
        "status": raw_result.get("status") or result.get("status") or "success",
        "errors": result.get("errors", raw_result.get("errors", [])),
        "warnings": result.get("warnings", raw_result.get("warnings", [])),
    }


async def _load_skill1_result(
    enterprise_name: str,
    task_id: str,
    report_period: str | None,
    run_date: str | None,
) -> dict[str, Any]:
    standard_output = OUTPUT_DIR / f"announcement_search_{task_id}.json"
    if standard_output.exists():
        return json.loads(standard_output.read_text(encoding="utf-8"))

    script_path = SKILLS_DIR / "post-loan-analysis-report" / "scripts" / "run_analysis.py"
    if not script_path.exists():
        return {
            "status": "failed",
            "errors": [f"Skill1 script not found: {script_path.as_posix()}"],
            "source_documents": [],
            "search_log": [],
            "freshness_gate": {},
            "data_availability": {},
            "pdf_handoff": _empty_pdf_handoff(enterprise_name, task_id, "Skill1 script not found"),
        }

    spec = importlib.util.spec_from_file_location("post_loan_skill1_run_analysis", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Skill1 script: {script_path.as_posix()}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    payload = {
        "enterprise_name": enterprise_name,
        "task_id": task_id,
        "run_date": run_date or date.today().isoformat(),
        "max_results_per_channel": 30,
        "pdf_dir": as_posix_path(PDF_DIR / task_id),
    }
    if report_period:
        payload["report_period"] = report_period
    query = json.dumps(payload, ensure_ascii=False)

    run_analysis = getattr(module, "run_analysis", None)
    if run_analysis is None:
        raise RuntimeError(f"Skill1 script has no run_analysis entry: {script_path.as_posix()}")

    result = run_analysis(query, output_dir=OUTPUT_DIR / "post-loan-analysis-report")
    if asyncio.iscoroutine(result):
        return await result
    return await asyncio.to_thread(lambda: result)


def _unwrap_skill1_result(raw: dict[str, Any], enterprise_name: str, task_id: str) -> dict[str, Any]:
    if "source_documents" in raw or "pdf_handoff" in raw:
        return raw

    inner = raw.get("result") if isinstance(raw.get("result"), dict) else {}
    source_documents = _source_documents_from_legacy_sources(inner.get("sources", {}), enterprise_name, task_id)
    return {
        "status": raw.get("status", "success"),
        "source_documents": source_documents,
        "search_log": inner.get("search_log", raw.get("search_log", [])),
        "freshness_gate": inner.get("freshness_gate", {}),
        "data_availability": inner.get("data_availability", {}),
        "pdf_handoff": inner.get("pdf_handoff"),
        "errors": raw.get("errors", []),
        "warnings": raw.get("warnings", []),
    }


def _source_documents_from_legacy_sources(
    sources: dict[str, Any],
    enterprise_name: str,
    task_id: str,
) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    groups = [
        *sources.get("financial_report", []),
        *sources.get("prospectus", []),
        *sources.get("rating_report", []),
    ]
    selected_main_seen = False
    for index, doc in enumerate(groups, start=1):
        item = dict(doc)
        item.setdefault("document_id", f"{task_id}_doc_{index:03d}")
        item.setdefault("title", item.get("attachment_title", ""))
        item.setdefault("source_url", item.get("url", ""))
        item.setdefault("pdf_url", "")
        item.setdefault("local_pdf_path", item.get("download_path", ""))
        item.setdefault("pdf_download_status", "success" if item.get("local_pdf_path") else "skipped")
        item.setdefault("pdf_sha256", "")
        item.setdefault("needs_deep_pdf_parse", True)
        if item.get("document_status") == "latest_financial_data":
            item["document_status"] = ""
        if item.get("file_type") in ALLOWED_FILE_TYPES:
            if not selected_main_seen and item["file_type"] == "annual_report":
                item.setdefault("document_status", "selected_main")
                selected_main_seen = True
            else:
                item.setdefault("document_status", "selected_supplement")
        else:
            item.setdefault("document_status", "unsupported_file_type")
        item.setdefault(
            "entity_verification",
            {
                "input_name": enterprise_name,
                "matched_name_in_document": enterprise_name,
                "matched_role": "不确定",
                "is_same_subject": True,
                "verification_evidence": "legacy Skill1 output did not include entity_verification",
                "confidence": "medium",
            },
        )
        docs.append(item)
    return docs


def _validated_pdf_handoff(
    pdf_handoff: dict[str, Any],
    source_documents: list[dict[str, Any]],
    enterprise_name: str,
    task_id: str,
) -> dict[str, Any]:
    handoff = dict(pdf_handoff)
    handoff["enterprise_name"] = handoff.get("enterprise_name") or enterprise_name
    handoff["task_id"] = handoff.get("task_id") or task_id
    handoff["generated_at"] = handoff.get("generated_at") or handoff.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%S")
    handoff.pop("created_at", None)

    source_by_id = {doc.get("document_id"): doc for doc in source_documents}
    docs = handoff.get("documents_needing_pdf_parse", [])
    if not isinstance(docs, list):
        docs = []
    handoff["documents_needing_pdf_parse"] = [
        _merge_doc_for_handoff(doc, source_by_id)
        for doc in docs
        if _can_enter_pdf_parse(_merge_doc_for_handoff(doc, source_by_id))
    ]
    handoff.setdefault("selected_main_documents", [])
    handoff.setdefault("selected_supplement_documents", [])
    handoff.setdefault("no_latest_public_data", len(handoff["documents_needing_pdf_parse"]) == 0)
    handoff.setdefault("message", "")
    return handoff


def _merge_doc_for_handoff(doc: dict[str, Any], source_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = source_by_id.get(doc.get("document_id"), {})
    merged = {**source, **doc}
    if merged.get("local_pdf_path"):
        merged["local_pdf_path"] = Path(merged["local_pdf_path"]).as_posix()
    return merged


def _can_enter_pdf_parse(doc: dict[str, Any]) -> bool:
    if doc.get("document_status") in BLOCKED_PARSE_STATUSES:
        return False
    if doc.get("document_status") not in ALLOWED_PARSE_STATUSES:
        return False
    if doc.get("file_type") not in ALLOWED_FILE_TYPES:
        return False
    if not doc.get("needs_deep_pdf_parse", False):
        return False
    if doc.get("pdf_download_status") != "success":
        return False
    local_pdf_path = doc.get("local_pdf_path")
    if not local_pdf_path or not Path(local_pdf_path).exists():
        return False
    entity = doc.get("entity_verification") or {}
    if entity.get("is_same_subject") is not True:
        return False
    if entity.get("confidence") not in {"high", "medium"}:
        return False
    return True


def _build_compatible_pdf_handoff(
    source_documents: list[dict[str, Any]],
    enterprise_name: str,
    task_id: str,
) -> dict[str, Any]:
    selected_main = [doc for doc in source_documents if doc.get("document_status") == "selected_main"]
    selected_supplement = [doc for doc in source_documents if doc.get("document_status") == "selected_supplement"]
    documents = [doc for doc in source_documents if _can_enter_pdf_parse(doc)]
    return {
        "enterprise_name": enterprise_name,
        "task_id": task_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "selected_main_documents": selected_main,
        "selected_supplement_documents": selected_supplement,
        "documents_needing_pdf_parse": documents,
        "no_latest_public_data": not documents,
        "message": "" if documents else "Skill1 output missing standard pdf_handoff",
    }


def _empty_pdf_handoff(enterprise_name: str, task_id: str, message: str) -> dict[str, Any]:
    return {
        "enterprise_name": enterprise_name,
        "task_id": task_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "selected_main_documents": [],
        "selected_supplement_documents": [],
        "documents_needing_pdf_parse": [],
        "no_latest_public_data": True,
        "message": message,
    }
