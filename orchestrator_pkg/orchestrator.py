"""Post-loan analysis orchestrator for the four-skill pipeline."""
from __future__ import annotations

import hashlib
import json
import time
import traceback
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .paths import CACHE_DIR, OUTPUT_DIR, SCHEMA_DIR

CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SEARCH_CACHE_TTL = timedelta(days=7)
SAME_DAY_CACHE_TTL = timedelta(days=1)
SKILL1_VERSION = "post_loan_skill1_v20260601_pdf_detail_adapters_v2"
SEARCH_ADAPTER_VERSION = "announcement_search_adapter_v20260601_pdf_detail_v2"
SKILL2_VERSION = "pdf_parse_skill_v20260601_rapidocr_main_statement_v2"
SKILL3_VERSION = "financial_extraction_skill_v20260601_main_statement_units_v3"
SKILL4_VERSION = "financial_analysis_skill_v20260601_main_period_gross_margin_v3"

NO_LATEST_PUBLIC_DATA_MESSAGE = "未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。"

PROGRESS_STEPS = [
    "init",
    "skill1_search_started",
    "skill1_search_completed",
    "skill2_pdf_parse_started",
    "skill2_pdf_parse_completed",
    "skill3_extraction_started",
    "skill3_extraction_completed",
    "skill4_analysis_started",
    "skill4_analysis_completed",
    "final_json_built",
    "complete",
]


class OrchestratorError(Exception):
    """Raised for orchestrator-level failures."""


def _cache_key(enterprise_name: str, data_type: str, identifier: str = "") -> str:
    raw = f"{enterprise_name}|{data_type}|{identifier}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _stable_hash(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str, ttl: timedelta | None = None) -> dict[str, Any] | None:
    cache_file = CACHE_DIR / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        if ttl:
            cached_at_raw = payload.get("_cached_at")
            cached_at = datetime.fromisoformat(cached_at_raw) if cached_at_raw else None
            if not cached_at or datetime.now(timezone.utc) - cached_at > ttl:
                return None
        return payload.get("data", payload)
    except Exception:
        return None


def _cache_set(key: str, data: dict[str, Any]) -> None:
    cache_file = CACHE_DIR / f"{key}.json"
    payload = {"_cached_at": datetime.now(timezone.utc).isoformat(), "data": data}
    cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _inline_local_refs(schema_part: Any, store: dict[str, dict[str, Any]]) -> Any:
    if isinstance(schema_part, dict):
        ref = schema_part.get("$ref")
        if isinstance(ref, str) and ref in store:
            return _inline_local_refs(store[ref], store)
        return {key: _inline_local_refs(value, store) for key, value in schema_part.items()}
    if isinstance(schema_part, list):
        return [_inline_local_refs(item, store) for item in schema_part]
    return schema_part


class ProgressTracker:
    """Collects progress events for frontend polling."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.events: list[dict[str, Any]] = []
        self.start_time = time.time()

    def add(self, event: str, percent: int, message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        item = {
            "event": event,
            "percent": percent,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "elapsed_ms": int((time.time() - self.start_time) * 1000),
        }
        if detail is not None:
            item["detail"] = detail
        self.events.append(item)
        return item


class Orchestrator:
    """Runs Skill1 -> Skill2 -> Skill3 -> Skill4 and builds final_json."""

    def __init__(self, enterprise_name: str, task_id: str | None = None, report_period: str | None = None):
        self.enterprise_name = enterprise_name.strip()
        self.task_id = task_id or f"task_{uuid.uuid4().hex[:12]}"
        self.report_period = report_period
        self.run_date = date.today().isoformat()
        self.progress = ProgressTracker(self.task_id)

        self._source_documents: list[dict[str, Any]] = []
        self._search_log: list[dict[str, Any]] = []
        self._freshness_gate: dict[str, Any] = {}
        self._data_availability: dict[str, Any] = {}
        self._pdf_handoff: dict[str, Any] = {}
        self._parsed_documents: list[dict[str, Any]] = []
        self._failed_documents: list[dict[str, Any]] = []
        self._parse_summary: dict[str, Any] = {"total": 0, "success": 0, "partial": 0, "failed": 0}
        self._financial_extraction: dict[str, Any] = _empty_extraction(self.enterprise_name, "not_started")
        self._financial_analysis: dict[str, Any] = _empty_analysis()
        self._validation_errors: list[str] = []
        self._validation_warnings: list[str] = []

    async def run(self) -> dict[str, Any]:
        self.progress.add("init", 0, f"初始化任务: {self.enterprise_name}")
        try:
            await self._run_search_stage()
            if self._pdf_handoff.get("no_latest_public_data") is True:
                return self._finish()
            await self._run_parse_stage()
            if self._all_pdf_parse_failed():
                return self._finish()
            await self._run_extraction_stage()
            if self._financial_extraction.get("extraction_status") == "failed":
                return self._finish()
            await self._run_analysis_stage()
        except Exception:
            self._validation_errors.append(f"流水线异常: {traceback.format_exc()}")
        return self._finish()

    def _finish(self) -> dict[str, Any]:
        result = self._build_final_json()
        self.progress.add("complete", 100, "任务完成")
        return result

    async def _run_search_stage(self) -> None:
        self.progress.add("skill1_search_started", 5, "正在搜索公开披露文件...")
        cache_identifier = (
            f"{SKILL1_VERSION}|{SEARCH_ADAPTER_VERSION}|{self.run_date}|"
            f"{self.report_period or ''}|{self.enterprise_name}"
        )
        cache_key = _cache_key(self.enterprise_name, "skill1_search", cache_identifier)
        cached = _cache_get(cache_key, ttl=SEARCH_CACHE_TTL)
        if cached:
            self._apply_search_result(cached)
            self.progress.add("skill1_search_completed", 20, "Skill1 搜索结果缓存命中")
            return

        from .adapters.announcement_search_adapter import run_announcement_search

        result = await run_announcement_search(
            enterprise_name=self.enterprise_name,
            task_id=self.task_id,
            report_period=self.report_period,
            run_date=self.run_date,
        )
        self._apply_search_result(result)
        ttl = SAME_DAY_CACHE_TTL if self._pdf_handoff.get("no_latest_public_data") is True else SEARCH_CACHE_TTL
        has_download_failure = (
            result.get("status") == "failed"
            or self._data_availability.get("data_level") in {"search_failed", "download_failed"}
            or any(doc.get("pdf_download_status") == "failed" for doc in self._source_documents)
        )
        if not result.get("errors") and not has_download_failure:
            _cache_set(cache_key, result)
        selected = len(self._pdf_handoff.get("documents_needing_pdf_parse", []))
        message = NO_LATEST_PUBLIC_DATA_MESSAGE if self._pdf_handoff.get("no_latest_public_data") else f"Skill1 完成，待解析文档 {selected} 个"
        self.progress.add("skill1_search_completed", 20, message)

    def _apply_search_result(self, result: dict[str, Any]) -> None:
        self._source_documents = result.get("source_documents", [])
        self._search_log = result.get("search_log", [])
        self._freshness_gate = result.get("freshness_gate", {})
        self._data_availability = result.get("data_availability", {})
        self._pdf_handoff = result.get("pdf_handoff", {})
        self._validation_errors.extend(result.get("errors", []))
        self._validation_warnings.extend(result.get("warnings", []))

    async def _run_parse_stage(self) -> None:
        documents = self._pdf_handoff.get("documents_needing_pdf_parse", [])
        self.progress.add("skill2_pdf_parse_started", 35, f"正在解析 PDF，文档数 {len(documents)}")
        if not documents:
            self._parse_summary = {"total": 0, "success": 0, "partial": 0, "failed": 0}
            self.progress.add("skill2_pdf_parse_completed", 45, "无待解析 PDF")
            return

        cache_key = self._pdf_parse_cache_key(documents)
        if cache_key:
            cached = _cache_get(cache_key)
            if cached:
                self._apply_parse_result(cached)
                self.progress.add("skill2_pdf_parse_completed", 45, "Skill2 PDF 解析结果缓存命中")
                return

        from .adapters.pdf_parse_adapter import run_pdf_parse

        result = await run_pdf_parse(self._pdf_handoff, self.task_id)
        self._apply_parse_result(result)
        if cache_key:
            _cache_set(cache_key, result)
        self.progress.add(
            "skill2_pdf_parse_completed",
            45,
            f"Skill2 完成: 成功 {self._parse_summary.get('success', 0)}，失败 {self._parse_summary.get('failed', 0)}",
        )

    def _apply_parse_result(self, result: dict[str, Any]) -> None:
        self._parsed_documents = result.get("parsed_documents", [])
        self._failed_documents = result.get("failed_documents", [])
        self._parse_summary = result.get("parse_summary") or self._build_parse_summary()

    def _pdf_parse_cache_key(self, documents: list[dict[str, Any]]) -> str | None:
        hashes = [doc.get("pdf_sha256") for doc in documents if doc.get("pdf_sha256")]
        if not hashes or len(hashes) != len(documents):
            return None
        return _cache_key(self.enterprise_name, "skill2_pdf_parse", f"{SKILL2_VERSION}|{'|'.join(sorted(hashes))}")

    async def _run_extraction_stage(self) -> None:
        successful = [doc for doc in self._parsed_documents if doc.get("parse_status") != "failed"]
        self.progress.add("skill3_extraction_started", 60, f"正在抽取财务字段，解析成功文档 {len(successful)} 个")
        if not successful:
            self._financial_extraction = _empty_extraction(self.enterprise_name, "无成功解析的PDF文档")
            self.progress.add("skill3_extraction_completed", 70, "无成功解析文档，Skill3 跳过")
            return

        cache_key = _cache_key(
            self.enterprise_name,
            "skill3_extraction",
            _stable_hash(
                {
                    "version": SKILL3_VERSION,
                    "parsed_documents": successful,
                }
            ),
        )
        cached = _cache_get(cache_key)
        if cached:
            self._financial_extraction = cached
            self.progress.add("skill3_extraction_completed", 70, "Skill3 财务抽取结果缓存命中")
            return

        from .adapters.financial_extraction_adapter import run_financial_extraction

        try:
            self._financial_extraction = await run_financial_extraction(
                enterprise_name=self.enterprise_name,
                parsed_documents=successful,
                source_documents=self._source_documents,
                task_id=self.task_id,
            )
            _cache_set(cache_key, self._financial_extraction)
        except Exception as exc:
            self._financial_extraction = _empty_extraction(self.enterprise_name, f"Skill3 调用异常: {exc}")
            self._validation_errors.append(f"Skill3 调用异常: {exc}")
        status = self._financial_extraction.get("extraction_status", "failed")
        periods = len(self._financial_extraction.get("data_periods", []))
        self.progress.add("skill3_extraction_completed", 70, f"Skill3 完成: {status}，期间 {periods} 个")

    async def _run_analysis_stage(self) -> None:
        self.progress.add("skill4_analysis_started", 82, "正在进行财务指标分析...")
        cache_key = _cache_key(
            self.enterprise_name,
            "skill4_analysis",
            _stable_hash(
                {
                    "version": SKILL4_VERSION,
                    "structured_financial_data": self._financial_extraction.get("structured_financial_data", {}),
                    "field_evidence": self._financial_extraction.get("field_evidence", []),
                    "extraction_warnings": self._financial_extraction.get("extraction_warnings", []),
                    "thresholds_config": {},
                }
            ),
        )
        cached = _cache_get(cache_key)
        if cached:
            self._financial_analysis = cached
            self.progress.add("skill4_analysis_completed", 88, "Skill4 财务分析结果缓存命中")
            return

        from .adapters.financial_analysis_adapter import run_financial_analysis

        self._financial_analysis = await run_financial_analysis(
            task_id=self.task_id,
            enterprise_name=self.enterprise_name,
            extraction_result=self._financial_extraction,
            source_documents=self._source_documents,
            thresholds_config={},
        )
        _cache_set(cache_key, self._financial_analysis)
        status = self._financial_analysis.get("analysis_status", "failed")
        indicators = len(self._financial_analysis.get("financial_indicators", []))
        findings = len(self._financial_analysis.get("negative_findings", []))
        self.progress.add("skill4_analysis_completed", 88, f"Skill4 完成: {status}，指标 {indicators} 个，风险发现 {findings} 个")

    def _build_final_json(self) -> dict[str, Any]:
        self.progress.add("final_json_built", 95, "正在构建最终结果...")
        task_status, data_status, message = self._determine_status()
        final = {
            "task_id": self.task_id,
            "enterprise_name": self.enterprise_name,
            "task_status": task_status,
            "data_status": data_status,
            "message": message,
            "source_documents": self._source_documents,
            "search_log": self._search_log,
            "freshness_gate": self._freshness_gate,
            "data_availability": self._data_availability,
            "pdf_handoff_summary": self._build_pdf_handoff_summary(),
            "parsed_documents_summary": self._build_parsed_summary(),
            "parse_summary": self._parse_summary,
            "financial_extraction": self._financial_extraction,
            "structured_financial_data": self._financial_extraction.get("structured_financial_data", {}),
            "field_evidence": self._financial_extraction.get("field_evidence", []),
            "missing_fields": self._financial_extraction.get("missing_fields", []),
            "extraction_warnings": self._financial_extraction.get("extraction_warnings", []),
            "document_usage": self._financial_extraction.get("document_usage", []),
            "financial_analysis": self._financial_analysis,
            "financial_indicators": self._financial_analysis.get("financial_indicators", []),
            "negative_findings": self._financial_analysis.get("negative_findings", []),
            "unavailable_indicators": self._financial_analysis.get("unavailable_indicators", []),
            "analysis_summary": self._financial_analysis.get("analysis_summary", {}),
            "frontend_financial_summary": self._financial_analysis.get("frontend_financial_summary", {}),
            "risk_level_summary": self._financial_analysis.get("risk_level_summary", {}),
            "failed_documents": self._failed_documents,
            "progress_events": self.progress.events,
            "validation_result": {"passed": True, "errors": [], "warnings": []},
        }
        final["validation_result"] = self._validate(final)
        return final

    def _determine_status(self) -> tuple[str, str, str]:
        if any("all_search_channels_failed" in e for e in self._validation_errors):
            return "failed", "search_failed", "公开披露搜索失败，无法判断是否存在最新公开数据。"
        if any("Skill1" in err or "搜索" in err for err in self._validation_errors):
            return "failed", "failed", "公开披露搜索失败，无法完成贷后分析。"
        if self._pdf_handoff.get("no_latest_public_data") is True:
            return "completed", "no_latest_public_data", NO_LATEST_PUBLIC_DATA_MESSAGE
        if self._all_pdf_parse_failed():
            return "partial", "pdf_parse_failed", "已找到公开披露文件，但PDF解析全部失败，无法继续形成有效财务分析。"

        extraction_status = self._financial_extraction.get("extraction_status", "failed")
        if extraction_status == "failed":
            if any("Skill3 调用异常" in err for err in self._validation_errors):
                return "partial", "financial_extraction_failed", "财务抽取 Skill3 调用失败，无法生成完整财务分析。"
            return "partial", "data_insufficient", "已找到公开披露文件但财务数据提取不完整，无法生成完整的财务分析。"

        analysis_status = self._financial_analysis.get("analysis_status", "failed")
        if analysis_status == "failed":
            return "partial", "financial_analysis_failed", "财务分析 Skill4 执行失败，已保留上游搜索、解析和抽取结果。"
        if analysis_status == "partial" or extraction_status == "partial" or self._financial_analysis.get("data_status") == "partial":
            return "completed", "success_with_data_limitation", "贷后分析已完成，但部分财务字段或指标受公开资料限制。"
        return "completed", "success", "贷后分析已完成。"

    def _all_pdf_parse_failed(self) -> bool:
        total = int(self._parse_summary.get("total", 0) or 0)
        failed = int(self._parse_summary.get("failed", 0) or 0)
        if total == 0:
            return False
        successful = [
            doc for doc in self._parsed_documents
            if doc.get("parse_status") in {"success", "partial"}
        ]
        return failed >= total and not successful

    def _build_parse_summary(self) -> dict[str, int]:
        return {
            "total": len(self._parsed_documents),
            "success": sum(1 for doc in self._parsed_documents if doc.get("parse_status") == "success"),
            "partial": sum(1 for doc in self._parsed_documents if doc.get("parse_status") == "partial"),
            "failed": len(self._failed_documents),
        }

    def _build_parsed_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "document_id": doc.get("document_id", ""),
                "file_type": doc.get("file_type", ""),
                "report_period": doc.get("report_period", ""),
                "parser_used": doc.get("parser_used", ""),
                "ocr_used": doc.get("ocr_used", False),
                "page_count": doc.get("page_count", 0),
                "tables_found_count": len(doc.get("tables_raw", [])),
                "parse_status": doc.get("parse_status", ""),
                "parse_confidence": doc.get("parse_confidence", ""),
                "parse_warnings": doc.get("parse_warnings", []),
                "json_output_path": doc.get("json_output_path", ""),
            }
            for doc in self._parsed_documents
        ]

    def _build_pdf_handoff_summary(self) -> dict[str, Any]:
        docs = self._pdf_handoff.get("documents_needing_pdf_parse", [])
        return {
            "task_id": self._pdf_handoff.get("task_id", self.task_id),
            "enterprise_name": self._pdf_handoff.get("enterprise_name", self.enterprise_name),
            "generated_at": self._pdf_handoff.get("generated_at", ""),
            "no_latest_public_data": self._pdf_handoff.get("no_latest_public_data", False),
            "message": self._pdf_handoff.get("message", ""),
            "documents_needing_pdf_parse_count": len(docs) if isinstance(docs, list) else 0,
            "document_ids": [doc.get("document_id") for doc in docs if isinstance(doc, dict)],
        }

    def _validate(self, final_json: dict[str, Any]) -> dict[str, Any]:
        errors = list(self._validation_errors)
        warnings = list(self._validation_warnings)
        analysis_validation = self._financial_analysis.get("validation_result", {})
        warnings.extend(analysis_validation.get("warnings", []))
        errors.extend(analysis_validation.get("errors", []))
        errors.extend(self._validate_schema(final_json))
        return {"passed": len(errors) == 0, "errors": errors, "warnings": warnings}

    def _validate_schema(self, final_json: dict[str, Any]) -> list[str]:
        try:
            from jsonschema import Draft7Validator
        except Exception as exc:
            return [f"jsonschema 不可用，无法校验 final_json: {exc}"]
        try:
            schema = json.loads((SCHEMA_DIR / "final_json.schema.json").read_text(encoding="utf-8"))
            store = {
                name: json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
                for name in [
                    "source_document.schema.json",
                    "structured_financial_data.schema.json",
                    "parsed_document.schema.json",
                    "financial_analysis.schema.json",
                ]
            }
            validator = Draft7Validator(_inline_local_refs(schema, store))
            return [
                f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
                for error in sorted(validator.iter_errors(final_json), key=lambda e: list(e.absolute_path))
            ]
        except Exception as exc:
            return [f"final_json schema 校验异常: {exc}"]


def _empty_extraction(enterprise_name: str, message: str) -> dict[str, Any]:
    return {
        "enterprise_name": enterprise_name,
        "extraction_status": "failed",
        "data_periods": [],
        "selected_main_document_id": None,
        "selected_supplement_document_ids": [],
        "structured_financial_data": {
            "financial_tables": {
                "balance_sheet": [],
                "income_statement": [],
                "cash_flow_statement": [],
            }
        },
        "field_evidence": [],
        "missing_fields": [],
        "extraction_warnings": [{"warning_type": "not_available", "message": message}],
        "document_usage": [],
        "validation_result": {"passed": False, "errors": [message], "warnings": []},
    }


def _empty_analysis() -> dict[str, Any]:
    return {
        "analysis_status": "failed",
        "data_status": "insufficient",
        "main_period": "",
        "periods_analyzed": [],
        "financial_indicators": [],
        "negative_findings": [],
        "unavailable_indicators": [],
        "analysis_summary": {},
        "frontend_financial_summary": {},
        "risk_level_summary": {},
        "validation_result": {"passed": True, "errors": [], "warnings": []},
    }


async def create_task(enterprise_name: str, report_period: str | None = None) -> dict[str, Any]:
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    return {
        "task_id": task_id,
        "enterprise_name": enterprise_name,
        "report_period": report_period,
        "created_at": datetime.now().isoformat(),
        "status": "created",
    }


async def run_task(
    enterprise_name: str,
    task_id: str | None = None,
    report_period: str | None = None,
) -> dict[str, Any]:
    return await Orchestrator(enterprise_name, task_id=task_id, report_period=report_period).run()


async def create_and_run_task(enterprise_name: str, report_period: str | None = None) -> dict[str, Any]:
    meta = await create_task(enterprise_name, report_period)
    return await run_task(enterprise_name, task_id=meta["task_id"], report_period=report_period)
