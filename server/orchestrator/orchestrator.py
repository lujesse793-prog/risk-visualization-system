"""
总控 Orchestrator —— 贷后分析流水线总控服务

职责：
1. 接收前端输入：企业名称、可选报告期、任务ID
2. 调用 Skill 1 → Skill 2 → Skill 3 → Skill 4 串行执行
3. 统一校验、合并、去重、缓存、错误处理
4. 输出前端可直接展示的 final_json
5. 实时返回任务进度 progress_events

流水线：
  企业名称 → Skill 1 搜索公告 → Skill 2 解析PDF → Skill 3 提取财务字段 → Skill 4 分析财务指标
  → Orchestrator 汇总为 final_json → 前端展示
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore

# ---- 项目根目录：稳定计算，不依赖嵌套层级硬编码 ----
# 从 __file__ 向上找到包含 mx_skills/ 和 server/ 的目录
def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    for _ in range(6):
        if (current / "mx_skills").is_dir() and (current / "server").is_dir():
            return current
        current = current.parent
    # fallback: 假设标准结构 server/orchestrator/orchestrator.py
    return Path(__file__).resolve().parent.parent.parent

PROJECT_ROOT = _find_project_root()
OUTPUT_DIR = PROJECT_ROOT / "mx_skills" / "output"
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
PDF_DIR = PROJECT_ROOT / "data" / "pdfs"
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

# 确保目录存在
for d in (OUTPUT_DIR, CACHE_DIR, PDF_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---- 缓存有效期 ----
SEARCH_CACHE_TTL_HOURS = int(os.environ.get("ORCH_SEARCH_CACHE_TTL_HOURS", "168"))  # 默认 7 天


class OrchestratorError(Exception):
    """Orchestrator 异常"""


# ---- 缓存管理 ----

def _cache_key(enterprise_name: str, data_type: str, identifier: str = "") -> str:
    raw = f"{enterprise_name}|{data_type}|{identifier}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _cache_get(key: str, ttl_hours: int = 0) -> dict[str, Any] | None:
    cache_file = CACHE_DIR / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if ttl_hours > 0:
            cached_at = data.get("_cached_at", 0)
            if time.time() - cached_at > ttl_hours * 3600:
                return None  # expired
        return data
    except Exception:
        return None


def _cache_set(key: str, data: dict[str, Any]) -> None:
    data["_cached_at"] = time.time()
    cache_file = CACHE_DIR / f"{key}.json"
    cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- 进度事件管理 ----

class ProgressTracker:
    """任务进度追踪器"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.events: list[dict[str, Any]] = []
        self.start_time = time.time()

    def add(self, event: str, percent: int, message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        elapsed_ms = int((time.time() - self.start_time) * 1000)
        evt = {
            "event": event,
            "percent": percent,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "elapsed_ms": elapsed_ms,
        }
        if detail:
            evt["detail"] = detail
        self.events.append(evt)
        return evt


# ---- JSON Schema 加载 ----

def _load_schema(name: str) -> dict[str, Any] | None:
    """加载 schema 并解析 $ref 引用"""
    schema = _load_schema(name)
    if schema is None:
        return None
    # 递归解析 $ref 引用
    _resolve_refs(schema, SCHEMA_DIR)
    return schema


def _load_schema(name: str) -> dict[str, Any] | None:
    schema_file = SCHEMA_DIR / f"{name}.schema.json"
    if schema_file.exists():
        return json.loads(schema_file.read_text(encoding="utf-8"))
    return None


# ---- 主 Orchestrator ----

class Orchestrator:
    """贷后分析总控器"""

    def __init__(self, enterprise_name: str, task_id: str | None = None, report_period: str | None = None):
        self.enterprise_name = enterprise_name.strip()
        self.task_id = task_id or f"task_{uuid.uuid4().hex[:12]}"
        self.report_period = report_period
        self.progress = ProgressTracker(self.task_id)
        self._source_documents: list[dict[str, Any]] = []
        self._parsed_documents: list[dict[str, Any]] = []
        self._structured_financial_data: dict[str, Any] = {}
        self._financial_analysis: dict[str, Any] = {}
        self._failed_documents: list[dict[str, Any]] = []
        self._validation_errors: list[str] = []
        self._validation_warnings: list[str] = []
        # Skill 4 状态追踪
        self._skill4_ready: bool = False
        self._is_mock_analysis: bool = False

    # ==================== 公开接口 ====================

    async def run(self) -> dict[str, Any]:
        """执行完整的贷后分析流水线，返回 final_json"""
        self.progress.add("init", 0, f"初始化任务: {self.enterprise_name}",
                          {"enterprise_name": self.enterprise_name, "task_id": self.task_id})

        try:
            # Step 1: 搜索公告
            await self._run_search_stage()

            # Step 2: 解析 PDF
            await self._run_parse_stage()

            # Step 3: 提取财务字段
            await self._run_extraction_stage()

            # Step 4: 分析财务指标
            await self._run_analysis_stage()

        except OrchestratorError:
            # 搜索阶段失败，已在 _run_search_stage 中处理
            pass
        except Exception:
            self._validation_errors.append(f"流水线异常: {traceback.format_exc()}")

        # Step 5: 构建 final_json
        result = self._build_final_json()
        self.progress.add("final_json_built", 98, "最终结果构建完成")
        self.progress.add("complete", 100, "任务完成")
        return result

    async def _run_search_stage(self) -> None:
        """执行 Skill 1: 搜索公告"""
        self.progress.add("search_started", 2, "正在搜索公开披露平台...")

        # 检查缓存（带过期时间）
        cache_key = _cache_key(self.enterprise_name, "search", self.report_period or "")
        cached = _cache_get(cache_key, ttl_hours=SEARCH_CACHE_TTL_HOURS)
        if cached:
            self._source_documents = cached.get("source_documents", [])
            self.progress.add("search_completed", 15,
                              f"搜索完成（缓存命中），{len(self._source_documents)} 个文档")
            return

        try:
            from .adapters.announcement_search_adapter import run_announcement_search
            result = await run_announcement_search(
                enterprise_name=self.enterprise_name,
                task_id=self.task_id,
                report_period=self.report_period,
            )

            if result.get("status") == "error":
                self._validation_errors.append(f"搜索阶段失败: {result.get('errors', ['未知错误'])}")
                self.progress.add("search_completed", 15,
                                  f"搜索失败: {result.get('errors', [])}")
                raise OrchestratorError(f"搜索公告失败: {result.get('errors')}")

            self._source_documents = result.get("source_documents", [])

            # 缓存搜索结果
            _cache_set(cache_key, {"source_documents": self._source_documents})

            has_valid = any(
                d.get("document_status") in ("selected_main", "selected_supplement")
                for d in self._source_documents
            )
            selected_count = sum(1 for d in self._source_documents
                                 if d.get("document_status") in ("selected_main", "selected_supplement"))

            if not has_valid:
                self.progress.add("search_completed", 15,
                                  f"搜索完成，未找到有效的最新公开数据（共 {len(self._source_documents)} 个文档）")
            else:
                self.progress.add("search_completed", 15,
                                  f"搜索完成: {len(self._source_documents)} 个文档, 选中 {selected_count} 个")

        except OrchestratorError:
            raise
        except Exception as e:
            self._validation_errors.append(f"搜索阶段异常: {str(e)}")
            self.progress.add("search_completed", 15, f"搜索异常: {str(e)}")
            raise OrchestratorError(f"搜索公告失败: {e}")

    async def _run_parse_stage(self) -> None:
        """执行 Skill 2: 解析 PDF"""
        self.progress.add("pdf_download_started", 16, "准备下载并解析PDF文件...")

        to_parse = [
            d for d in self._source_documents
            if d.get("needs_deep_pdf_parse") and d.get("document_status") in ("selected_main", "selected_supplement")
            and d.get("pdf_download_status") != "failed"
        ]
        if not to_parse:
            self.progress.add("pdf_parse_completed", 30, "无需解析的文档")
            return

        self.progress.add("pdf_parse_started", 18,
                          f"开始解析 {len(to_parse)} 个PDF文件")

        parsed_successfully: list[dict[str, Any]] = []
        for doc in to_parse:
            doc_id = doc["document_id"]
            pdf_sha256 = doc.get("pdf_sha256", "")

            # 基于真实 SHA256 检查缓存
            if pdf_sha256:
                sha_key = _cache_key(self.enterprise_name, "parse", pdf_sha256)
                cached = _cache_get(sha_key)
                if cached:
                    parsed_successfully.append(cached)
                    self.progress.add("pdf_parse_completed", 25,
                                      f"PDF {doc_id[:8]} 缓存命中，跳过解析")
                    continue

            # 逐个解析
            try:
                from .adapters.pdf_parse_adapter import run_pdf_parse
                pdf_handoff = {
                    "task_id": self.task_id,
                    "enterprise_name": self.enterprise_name,
                    "documents_to_parse": [doc],
                }
                result = await run_pdf_parse(pdf_handoff, self.task_id)
                parsed = result.get("parsed_documents", [])
                failed = result.get("failed_documents", [])
                parsed_successfully.extend(parsed)
                self._failed_documents.extend(failed)

                for p in parsed:
                    sha = p.get("pdf_sha256", "")
                    if sha:
                        _cache_set(_cache_key(self.enterprise_name, "parse", sha), p)

                if failed:
                    self._validation_warnings.append(
                        f"PDF {doc_id[:8]} ({doc.get('title', '')[:20]}) 解析失败")

            except Exception as e:
                self._failed_documents.append({
                    "document_id": doc_id,
                    "title": doc.get("title", ""),
                    "failure_stage": "pdf_parse",
                    "failure_reason": str(e),
                })

        self._parsed_documents = parsed_successfully
        success_count = len([d for d in self._parsed_documents if d.get("parse_status") == "success"])
        self.progress.add("pdf_parse_completed", 30,
                          f"PDF解析完成: {success_count}/{len(to_parse)} 成功, {len(self._failed_documents)} 失败")

    async def _run_extraction_stage(self) -> None:
        """执行 Skill 3: 提取财务字段"""
        self.progress.add("financial_extract_started", 31, "正在提取财务字段...")

        successful = [d for d in self._parsed_documents if d.get("parse_status") != "failed"]
        if not successful:
            self._structured_financial_data = self._empty_extraction_result(
                "无成功解析的PDF文档，无法提取财务数据"
            )
            self.progress.add("financial_extract_completed", 50,
                              "无成功解析的文档，跳过财务字段提取",
                              {"status": "skipped", "reason": "no_parsed_documents"})
            return

        try:
            from .adapters.financial_extraction_adapter import run_financial_extraction
            self._structured_financial_data = await run_financial_extraction(
                parsed_documents=successful,
                source_documents=self._source_documents,
                task_id=self.task_id,
            )
            self._structured_financial_data["enterprise_name"] = self.enterprise_name

            extraction_status = self._structured_financial_data.get("extraction_status", "failed")
            period_count = len(self._structured_financial_data.get("data_periods", []))
            missing_count = len(self._structured_financial_data.get("missing_fields", []))
            self.progress.add("financial_extract_completed", 50,
                              f"财务字段提取完成: {extraction_status}, {period_count} 个期间, 缺少 {missing_count} 个字段")

        except Exception as e:
            self._structured_financial_data = self._empty_extraction_result(
                f"财务字段提取异常: {str(e)}"
            )
            self.progress.add("financial_extract_completed", 50,
                              f"财务字段提取异常", {"error": str(e)})

    async def _run_analysis_stage(self) -> None:
        """执行 Skill 4: 分析财务指标"""
        self.progress.add("financial_analysis_started", 51, "正在分析财务指标...")

        extraction_status = self._structured_financial_data.get("extraction_status", "failed")

        # 如果前面没有数据，直接跳过
        if extraction_status == "failed":
            self._financial_analysis = {
                "analysis_status": "failed",
                "financial_indicators": [],
                "negative_findings": [],
                "negative_summary_under_200_chars": "",
                "analysis_summary": {},
                "frontend_financial_summary": {"periods": [], "key_metrics": []},
                "data_sufficiency": {"has_annual_report": False, "has_semi_annual": False,
                                     "indicator_count": 0, "missing_indicators": []},
            }
            self._skill4_ready = False
            self._is_mock_analysis = False
            self.progress.add("financial_analysis_completed", 75,
                              "财务分析跳过（无可用数据）")
            return

        # 尝试调用真实 Skill 4
        analysis_result = None
        try:
            from .adapters.financial_analysis_adapter import run_financial_analysis
            analysis_result = await run_financial_analysis(
                structured_financial_data=self._structured_financial_data,
                source_documents=self._source_documents,
            )
        except Exception:
            analysis_result = {"analysis_status": "not_ready"}

        is_ready = analysis_result.get("analysis_status") != "not_ready"

        if is_ready:
            self._skill4_ready = True
            self._is_mock_analysis = False
            self._financial_analysis = analysis_result
            indicator_count = len(analysis_result.get("financial_indicators", []))
            finding_count = len(analysis_result.get("negative_findings", []))
            self.progress.add("financial_analysis_completed", 75,
                              f"财务分析完成: {indicator_count} 个指标, {finding_count} 个风险发现")
        else:
            # Skill 4 未接入，使用 mock
            self._skill4_ready = False
            self._is_mock_analysis = True
            try:
                from .adapters.mock_financial_analysis_adapter import run_mock_financial_analysis
                mock_result = await run_mock_financial_analysis(
                    structured_financial_data=self._structured_financial_data,
                    source_documents=self._source_documents,
                )
                self._financial_analysis = mock_result
            except Exception as e:
                self._financial_analysis = {
                    "analysis_status": "not_ready",
                    "financial_indicators": [],
                    "negative_findings": [],
                    "negative_summary_under_200_chars": "",
                    "analysis_summary": {},
                    "frontend_financial_summary": {"periods": [], "key_metrics": []},
                    "data_sufficiency": {"has_annual_report": False, "has_semi_annual": False,
                                         "indicator_count": 0, "missing_indicators": []},
                }

            self._validation_warnings.append(
                "财务分析引擎（Skill 4）尚未接入，当前使用 mock 输出。前三个 Skill 的结果不受影响。"
            )
            self.progress.add("financial_analysis_not_ready", 75,
                              "Skill 4 未接入，使用 mock 输出")

    # ==================== 辅助方法 ====================

    def _empty_extraction_result(self, warning: str) -> dict[str, Any]:
        return {
            "enterprise_name": self.enterprise_name,
            "source_document_id": "",
            "extraction_status": "failed",
            "extraction_confidence": "low",
            "data_periods": [],
            "balance_sheet": [],
            "income_statement": [],
            "cash_flow_statement": [],
            "business_segments": [],
            "extraction_warnings": [warning],
            "missing_fields": [],
        }

    
    # ==================== 结果构建 ====================

    def _build_final_json(self) -> dict[str, Any]:
        """构建前端可展示的最终 JSON"""
        task_status, data_status, message = self._determine_status()
        parsed_summary = self._build_parsed_summary()

        final: dict[str, Any] = {
            "task_id": self.task_id,
            "enterprise_name": self.enterprise_name,
            "task_status": task_status,
            "data_status": data_status,
            "message": message,
            "skill4_ready": self._skill4_ready,
            "is_mock_analysis": self._is_mock_analysis,
            "source_documents": self._source_documents,
            "parsed_documents_summary": parsed_summary,
            "structured_financial_data": self._structured_financial_data,
            "financial_indicators": self._financial_analysis.get("financial_indicators", []),
            "negative_findings": self._financial_analysis.get("negative_findings", []),
            "analysis_summary": self._financial_analysis.get("analysis_summary", {}),
            "frontend_financial_summary": self._financial_analysis.get("frontend_financial_summary", {}),
            "failed_documents": self._failed_documents,
            "progress_events": self.progress.events,
            "validation_result": {"passed": True, "errors": [], "warnings": []},
        }

        # 业务规则校验
        biz_vr = self._validate_business(task_status)
        # schema 结构校验
        schema_vr = self._validate_schema(final)

        final["validation_result"] = {
            "passed": biz_vr["passed"] and schema_vr["passed"],
            "errors": biz_vr["errors"] + schema_vr["errors"],
            "warnings": biz_vr["warnings"] + schema_vr["warnings"],
        }
        return final

    def _validate_business(self, task_status: str) -> dict[str, Any]:
        """业务规则校验"""
        errors: list[str] = list(self._validation_errors)
        warnings: list[str] = list(self._validation_warnings)

        has_selected = any(
            d.get("document_status") in ("selected_main", "selected_supplement")
            for d in self._source_documents
        )
        if has_selected and self._parsed_documents:
            all_failed = all(d.get("parse_status") == "failed" for d in self._parsed_documents)
            if all_failed:
                errors.append("所有选中文档解析均失败")

        valid_platforms = {"中国货币网", "上海证券交易所", "深圳证券交易所"}
        for doc in self._source_documents:
            platform = doc.get("source_platform", "")
            if platform and platform not in valid_platforms:
                errors.append(f"文档 source_platform '{platform}' 不在允许的3个平台中")

        summary = self._financial_analysis.get("negative_summary_under_200_chars", "")
        if summary and len(summary) > 200:
            warnings.append(f"negative_summary_under_200_chars 超过200字符（当前{len(summary)}字符）")

        extraction_ok = self._structured_financial_data.get("extraction_status") in ("success", "partial")
        if not self._skill4_ready and extraction_ok and task_status == "completed":
            errors.append("Skill 4 未接入但存在可用的提取数据时，task_status 不能为 completed")

        return {"passed": len(errors) == 0, "errors": errors, "warnings": warnings}

    def _validate_schema(self, final: dict[str, Any]) -> dict[str, Any]:
        """使用 JSON Schema 校验 final_json 结构"""
        schema = _load_schema("final_json")
        if schema and jsonschema is not None:
            try:
                jsonschema.validate(instance=final, schema=schema)
                return {"passed": True, "errors": [], "warnings": []}
            except jsonschema.ValidationError as e:
                return {"passed": False, "errors": [f"Schema 校验: {e.message}"], "warnings": []}
            except Exception as e:
                return {"passed": True, "errors": [], "warnings": [f"Schema 校验异常: {str(e)}"]}
        return {"passed": True, "errors": [], "warnings": ["Schema 不可用，跳过"]}


    def _determine_status(self) -> tuple[str, str, str]:
        """确定 task_status, data_status, message"""
        has_valid_source = any(
            d.get("document_status") in ("selected_main", "selected_supplement")
            for d in self._source_documents
        )
        extraction_ok = self._structured_financial_data.get("extraction_status") in ("success", "partial")

        if any("搜索阶段" in e for e in self._validation_errors):
            return ("failed", "failed", "搜索阶段发生错误，无法完成分析。")

        if not has_valid_source:
            return ("completed", "no_latest_public_data",
                    "未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。")

        if not extraction_ok:
            return ("partial", "data_insufficient",
                    "已找到公开披露文件但财务数据提取不完整，无法生成完整的财务分析。")

        if not self._skill4_ready or self._is_mock_analysis:
            return ("partial", "financial_analysis_skill_not_ready",
                    "前三个 Skill（搜索、解析、提取）已完成，但财务分析引擎（Skill 4）尚未接入，当前使用 mock 输出。前三个 Skill 的结果可正常查看。")

        return ("completed", "success", "贷后分析已完成，各项数据可供前端展示。")

    def _build_parsed_summary(self) -> list[dict[str, Any]]:
        """构建解析摘要（排除全文内容）"""
        summary = []
        for doc in self._parsed_documents:
            summary.append({
                "document_id": doc.get("document_id", ""),
                "file_type": doc.get("file_type", ""),
                "report_period": doc.get("report_period", ""),
                "parser_used": doc.get("parser_used", ""),
                "ocr_used": doc.get("ocr_used", False),
                "page_count": doc.get("page_count", 0),
                "tables_found_count": doc.get("tables_found_count", 0),
                "parse_status": doc.get("parse_status", ""),
                "parse_confidence": doc.get("parse_confidence", ""),
                "parse_warnings": doc.get("parse_warnings", []),
            })
        return summary


# ---- 便捷函数 ----

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
    orch = Orchestrator(enterprise_name=enterprise_name, task_id=task_id, report_period=report_period)
    return await orch.run()


async def create_and_run_task(
    enterprise_name: str,
    report_period: str | None = None,
) -> dict[str, Any]:
    meta = await create_task(enterprise_name, report_period)
    result = await run_task(enterprise_name, task_id=meta["task_id"], report_period=report_period)
    return result
