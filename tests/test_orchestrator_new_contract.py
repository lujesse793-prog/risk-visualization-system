import asyncio
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator_pkg.adapters.announcement_search_adapter import _validated_pdf_handoff
from orchestrator_pkg.orchestrator import PROGRESS_STEPS, run_task
from orchestrator_pkg.paths import PROJECT_ROOT, SKILLS_DIR


def source_doc(doc_id="doc_main", status="selected_main", file_type="annual_report"):
    return {
        "document_id": doc_id,
        "source_platform": "中国货币网",
        "title": "测试企业2025年度报告",
        "attachment_title": "测试企业2025年度报告.pdf",
        "file_type": file_type,
        "report_period": "2025",
        "publish_date": "2026-04-30",
        "source_url": "https://www.chinamoney.com.cn/a",
        "pdf_url": "https://www.chinamoney.com.cn/a.pdf",
        "local_pdf_path": "C:/tmp/a.pdf",
        "pdf_download_status": "success",
        "pdf_sha256": f"sha-{doc_id}",
        "document_status": status,
        "selection_reason": "最新年度报告",
        "skipped_reason": "",
        "entity_verification": {
            "input_name": "测试企业",
            "matched_name_in_document": "测试企业",
            "matched_role": "发行人",
            "is_same_subject": True,
            "verification_evidence": "发行人一致",
            "confidence": "high",
        },
        "needs_deep_pdf_parse": True,
    }


def skill1_result(no_data=False):
    docs = [] if no_data else [source_doc()]
    return {
        "source_documents": docs,
        "search_log": [{"source_name": "中国货币网", "query_runs": []}],
        "freshness_gate": {"is_fresh_enough_for_analysis": not no_data},
        "data_availability": {"data_level": "no_data" if no_data else "full"},
        "pdf_handoff": {
            "enterprise_name": "测试企业",
            "task_id": "task",
            "generated_at": "2026-06-01T00:00:00",
            "selected_main_documents": docs,
            "selected_supplement_documents": [],
            "documents_needing_pdf_parse": docs,
            "no_latest_public_data": no_data,
            "message": "",
        },
        "errors": [],
    }


def parsed_doc(doc_id="doc_main", status="success"):
    return {
        "document_id": doc_id,
        "file_type": "annual_report",
        "report_period": "2025",
        "parser_used": "marker",
        "ocr_used": False,
        "page_count": 100 if status != "failed" else 0,
        "page_texts": {"1": "资产负债表"},
        "tables_raw": [],
        "parse_status": status,
        "parse_confidence": "high" if status != "failed" else "low",
        "parse_warnings": [],
        "json_output_path": f"C:/tmp/{doc_id}.json",
    }


def extraction_result(status="success"):
    return {
        "enterprise_name": "测试企业",
        "extraction_status": status,
        "data_periods": ["2025", "2024"],
        "selected_main_document_id": "doc_main",
        "selected_supplement_document_ids": [],
        "structured_financial_data": {
            "financial_tables": {
                "balance_sheet": [
                    {
                        "field_name": "资产总计",
                        "standard_field_name": "total_assets",
                        "period": "2025",
                        "value": 100,
                        "unit": "亿元",
                        "source_document_id": "doc_main",
                    }
                ],
                "income_statement": [],
                "cash_flow_statement": [],
            }
        },
        "field_evidence": [
            {
                "field_name": "资产总计",
                "standard_field_name": "total_assets",
                "period": "2025",
                "value_normalized": 100,
                "source_document_id": "doc_main",
            }
        ],
        "missing_fields": [],
        "extraction_warnings": [] if status == "success" else [{"warning_type": "field_missing", "message": "部分字段缺失"}],
        "document_usage": [{"document_id": "doc_main", "used_fields": ["total_assets"]}],
        "validation_result": {"passed": True, "errors": [], "warnings": []},
    }


def analysis_result(status="success"):
    return {
        "analysis_status": status,
        "data_status": "partial" if status == "partial" else ("insufficient" if status == "failed" else "sufficient"),
        "main_period": "2025",
        "periods_analyzed": ["2025", "2024"],
        "financial_indicators": [
            {
                "indicator_name": "资产负债率",
                "indicator_category": "capital_structure",
                "period": "2025",
                "value": 60,
                "unit": "%",
                "formula": "负债合计/资产总计",
                "input_fields": [],
                "source_refs": [],
                "status": "available",
                "confidence": "high",
            }
        ] if status != "failed" else [],
        "negative_findings": [],
        "unavailable_indicators": [],
        "analysis_summary": {"overall_view": "完成"},
        "frontend_financial_summary": {"total_assets": 100},
        "risk_level_summary": {"highest_risk_level": "none"},
        "validation_result": {"passed": status != "failed", "errors": ["analysis failed"] if status == "failed" else [], "warnings": []},
    }


def patch_cache_off(monkeypatch):
    monkeypatch.setattr("orchestrator_pkg.orchestrator._cache_get", lambda *args, **kwargs: None)
    monkeypatch.setattr("orchestrator_pkg.orchestrator._cache_set", lambda *args, **kwargs: None)


def async_return(value):
    async def _inner(*args, **kwargs):
        return value
    return _inner


def test_selected_main_full_chain_success(monkeypatch):
    patch_cache_off(monkeypatch)
    monkeypatch.setattr("orchestrator_pkg.adapters.announcement_search_adapter.run_announcement_search", async_return(skill1_result()))
    monkeypatch.setattr("orchestrator_pkg.adapters.pdf_parse_adapter.run_pdf_parse", async_return({
        "parsed_documents": [parsed_doc()],
        "failed_documents": [],
        "parse_summary": {"total": 1, "success": 1, "partial": 0, "failed": 0},
    }))
    monkeypatch.setattr("orchestrator_pkg.adapters.financial_extraction_adapter.run_financial_extraction", async_return(extraction_result()))
    monkeypatch.setattr("orchestrator_pkg.adapters.financial_analysis_adapter.run_financial_analysis", async_return(analysis_result()))

    result = asyncio.run(run_task("测试企业", task_id="test_new_success"))

    assert result["task_status"] == "completed"
    assert result["data_status"] == "success"
    assert result["structured_financial_data"]["financial_tables"]["balance_sheet"]
    assert result["field_evidence"]
    assert result["document_usage"]
    assert "page_texts" not in result["parsed_documents_summary"][0]


def test_no_latest_public_data_skips_downstream(monkeypatch):
    patch_cache_off(monkeypatch)
    calls = {"pdf": 0, "extract": 0, "analysis": 0}
    async def pdf_called(*args, **kwargs):
        calls["pdf"] = 1
    async def extract_called(*args, **kwargs):
        calls["extract"] = 1
    async def analysis_called(*args, **kwargs):
        calls["analysis"] = 1

    monkeypatch.setattr("orchestrator_pkg.adapters.announcement_search_adapter.run_announcement_search", async_return(skill1_result(no_data=True)))
    monkeypatch.setattr("orchestrator_pkg.adapters.pdf_parse_adapter.run_pdf_parse", pdf_called)
    monkeypatch.setattr("orchestrator_pkg.adapters.financial_extraction_adapter.run_financial_extraction", extract_called)
    monkeypatch.setattr("orchestrator_pkg.adapters.financial_analysis_adapter.run_financial_analysis", analysis_called)

    result = asyncio.run(run_task("测试企业", task_id="test_new_no_data"))

    assert result["task_status"] == "completed"
    assert result["data_status"] == "no_latest_public_data"
    assert "未有最新公开财务数据披露" in result["message"]
    assert calls == {"pdf": 0, "extract": 0, "analysis": 0}


def test_skill2_partial_failure_continues_to_skill3(monkeypatch):
    patch_cache_off(monkeypatch)
    docs = [source_doc("doc_main"), source_doc("doc_supp", "selected_supplement", "semi_annual_report")]
    s1 = skill1_result()
    s1["source_documents"] = docs
    s1["pdf_handoff"]["documents_needing_pdf_parse"] = docs
    s1["pdf_handoff"]["selected_main_documents"] = [docs[0]]
    s1["pdf_handoff"]["selected_supplement_documents"] = [docs[1]]
    monkeypatch.setattr("orchestrator_pkg.adapters.announcement_search_adapter.run_announcement_search", async_return(s1))
    monkeypatch.setattr("orchestrator_pkg.adapters.pdf_parse_adapter.run_pdf_parse", async_return({
        "parsed_documents": [parsed_doc("doc_main"), parsed_doc("doc_supp", "failed")],
        "failed_documents": [{"document_id": "doc_supp", "failure_stage": "pdf_parse", "failure_reason": "bad pdf"}],
        "parse_summary": {"total": 2, "success": 1, "partial": 0, "failed": 1},
    }))
    monkeypatch.setattr("orchestrator_pkg.adapters.financial_extraction_adapter.run_financial_extraction", async_return(extraction_result()))
    monkeypatch.setattr("orchestrator_pkg.adapters.financial_analysis_adapter.run_financial_analysis", async_return(analysis_result()))

    result = asyncio.run(run_task("测试企业", task_id="test_new_parse_partial"))

    assert result["data_status"] == "success"
    assert len(result["failed_documents"]) == 1
    assert result["financial_indicators"]


def test_skill3_partial_still_runs_skill4_and_marks_limitation(monkeypatch):
    patch_cache_off(monkeypatch)
    monkeypatch.setattr("orchestrator_pkg.adapters.announcement_search_adapter.run_announcement_search", async_return(skill1_result()))
    monkeypatch.setattr("orchestrator_pkg.adapters.pdf_parse_adapter.run_pdf_parse", async_return({
        "parsed_documents": [parsed_doc()],
        "failed_documents": [],
        "parse_summary": {"total": 1, "success": 1, "partial": 0, "failed": 0},
    }))
    monkeypatch.setattr("orchestrator_pkg.adapters.financial_extraction_adapter.run_financial_extraction", async_return(extraction_result("partial")))
    monkeypatch.setattr("orchestrator_pkg.adapters.financial_analysis_adapter.run_financial_analysis", async_return(analysis_result()))

    result = asyncio.run(run_task("测试企业", task_id="test_new_extract_partial"))

    assert result["task_status"] == "completed"
    assert result["data_status"] == "success_with_data_limitation"
    assert result["financial_extraction"]["extraction_status"] == "partial"


def test_skill4_failed_marks_financial_analysis_failed(monkeypatch):
    patch_cache_off(monkeypatch)
    monkeypatch.setattr("orchestrator_pkg.adapters.announcement_search_adapter.run_announcement_search", async_return(skill1_result()))
    monkeypatch.setattr("orchestrator_pkg.adapters.pdf_parse_adapter.run_pdf_parse", async_return({
        "parsed_documents": [parsed_doc()],
        "failed_documents": [],
        "parse_summary": {"total": 1, "success": 1, "partial": 0, "failed": 0},
    }))
    monkeypatch.setattr("orchestrator_pkg.adapters.financial_extraction_adapter.run_financial_extraction", async_return(extraction_result()))
    monkeypatch.setattr("orchestrator_pkg.adapters.financial_analysis_adapter.run_financial_analysis", async_return(analysis_result("failed")))

    result = asyncio.run(run_task("测试企业", task_id="test_new_analysis_failed"))

    assert result["task_status"] == "partial"
    assert result["data_status"] == "financial_analysis_failed"


def test_progress_event_contract_names_are_updated():
    assert PROGRESS_STEPS == [
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


def test_paths_resolve_real_skill_scripts():
    assert (PROJECT_ROOT / "orchestrator_pkg").is_dir()
    assert (PROJECT_ROOT / "skills").is_dir()
    assert (SKILLS_DIR / "post-loan-analysis-report" / "scripts" / "run_analysis.py").exists()
    assert (SKILLS_DIR / "mx-finance-search" / "scripts" / "get_data.py").exists()
    assert (SKILLS_DIR / "pdf_parse_skill" / "scripts" / "run_pdf_parse.py").exists()
    assert (SKILLS_DIR / "financial_extraction_skill" / "scripts" / "run_analysis.py").exists()
    assert (SKILLS_DIR / "financial_analysis_skill" / "scripts" / "run_analysis.py").exists()


def load_skill1_module():
    script = SKILLS_DIR / "post-loan-analysis-report" / "scripts" / "run_analysis.py"
    spec = importlib.util.spec_from_file_location("skill1_contract_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill1_output_contract():
    module = load_skill1_module()
    payload = {"enterprise_name": "测试企业", "task_id": "skill1_no_data_contract", "sample_mode": "no_data"}
    result = asyncio.run(module.run_analysis(json.dumps(payload, ensure_ascii=False)))

    assert "source_documents" in result
    assert "pdf_handoff" in result
    assert result["pdf_handoff"]["no_latest_public_data"] is True
    assert result["pdf_handoff"]["documents_needing_pdf_parse"] == []


def test_orchestrator_no_mock_no_data(monkeypatch):
    patch_cache_off(monkeypatch)
    result = asyncio.run(run_task("未填写企业", task_id="test_real_no_data"))

    assert result["task_status"] == "completed"
    assert result["data_status"] == "no_latest_public_data"
    assert "script not found" not in json.dumps(result["validation_result"], ensure_ascii=False).lower()


def test_pdf_handoff_filters_invalid_docs(tmp_path):
    valid_pdf = tmp_path / "valid.pdf"
    valid_pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")

    docs = []
    for status in [
        "selected_main",
        "subject_mismatch",
        "download_failed",
        "stale_or_prior_period_document",
        "unsupported_file_type",
    ]:
        doc = source_doc(f"doc_{status}", status=status)
        doc["local_pdf_path"] = valid_pdf.as_posix()
        doc["pdf_download_status"] = "success"
        if status == "download_failed":
            doc["pdf_download_status"] = "failed"
        if status == "unsupported_file_type":
            doc["file_type"] = "unsupported_file_type"
        if status == "subject_mismatch":
            doc["entity_verification"]["is_same_subject"] = False
        docs.append(doc)

    handoff = {
        "enterprise_name": "测试企业",
        "task_id": "filter_test",
        "generated_at": "2026-06-01T00:00:00",
        "documents_needing_pdf_parse": docs,
        "no_latest_public_data": False,
    }
    filtered = _validated_pdf_handoff(handoff, docs, "测试企业", "filter_test")

    assert [d["document_id"] for d in filtered["documents_needing_pdf_parse"]] == ["doc_selected_main"]


def test_skill1_selected_main_status():
    module = load_skill1_module()
    payload = {"enterprise_name": "测试企业", "task_id": "skill1_sample_contract", "mode": "sample"}
    result = asyncio.run(module.run_analysis(json.dumps(payload, ensure_ascii=False)))

    statuses = {doc["file_type"]: doc["document_status"] for doc in result["source_documents"]}
    assert statuses["annual_report"] == "selected_main"
    assert statuses["semi_annual_report"] == "selected_supplement"
    assert "latest_financial_data" not in {doc["document_status"] for doc in result["source_documents"]}


def test_skill1_all_channels_error_not_no_data(monkeypatch):
    module = load_skill1_module()

    async def broken_search(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "_search_channel", broken_search)
    result = asyncio.run(module.run_analysis(json.dumps({"enterprise_name": "测试企业", "task_id": "all_error"}, ensure_ascii=False)))

    assert result["status"] == "failed"
    assert result["pdf_handoff"]["no_latest_public_data"] is False
    assert result["data_availability"]["data_level"] == "search_failed"
    assert any("all_search_channels_failed" in error for error in result["errors"])


def test_skill1_missing_search_dependency_returns_failed(monkeypatch):
    module = load_skill1_module()

    def missing_dependency():
        raise RuntimeError("mx-finance-search dependency not found")

    monkeypatch.setattr(module, "_load_search_module", missing_dependency)
    result = asyncio.run(module.run_analysis(json.dumps({"enterprise_name": "测试企业", "task_id": "missing_dep"}, ensure_ascii=False)))

    assert result["status"] == "failed"
    assert result["pdf_handoff"]["no_latest_public_data"] is False
    assert result["errors"]


def test_orchestrator_search_failed_status(monkeypatch):
    patch_cache_off(monkeypatch)
    failed_skill1 = {
        "status": "failed",
        "enterprise_name": "测试企业",
        "task_id": "search_failed",
        "source_documents": [],
        "search_log": [],
        "freshness_gate": {"stop_reason": "公开披露搜索失败，无法判断是否存在最新公开数据"},
        "data_availability": {"data_level": "search_failed"},
        "pdf_handoff": {
            "enterprise_name": "测试企业",
            "task_id": "search_failed",
            "generated_at": "2026-06-01T00:00:00",
            "selected_main_documents": [],
            "selected_supplement_documents": [],
            "documents_needing_pdf_parse": [],
            "no_latest_public_data": False,
            "message": "公开披露搜索失败，无法判断是否存在最新公开数据",
        },
        "errors": ["all_search_channels_failed: boom"],
    }
    monkeypatch.setattr("orchestrator_pkg.adapters.announcement_search_adapter.run_announcement_search", async_return(failed_skill1))

    result = asyncio.run(run_task("测试企业", task_id="test_search_failed"))

    assert result["task_status"] == "failed"
    assert result["data_status"] == "search_failed"
    assert "无法判断是否存在最新公开数据" in result["message"]


def test_skill2_pypdf_fallback(monkeypatch, tmp_path):
    script = SKILLS_DIR / "pdf_parse_skill" / "scripts" / "run_pdf_parse.py"
    spec = importlib.util.spec_from_file_location("skill2_pypdf_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_command_from_env_or_path", lambda *args, **kwargs: None)

    pdf_path = tmp_path / "text.pdf"
    write_text_pdf(pdf_path, ["Balance Sheet", "Unit: RMB 100m", "Total Assets 100 90"])
    payload = {
        "documents_to_parse": [
            {
                "document_id": "text_pdf",
                "file_type": "annual_report",
                "report_period": "2025",
                "local_pdf_path": pdf_path.as_posix(),
            }
        ],
        "output_dir": (tmp_path / "out").as_posix(),
    }
    result = asyncio.run(module.run_pdf_parse(json.dumps(payload, ensure_ascii=False)))

    assert result["status"] == "success"
    assert result["parsed_documents"][0]["parser_used"] in {"pypdf", "pymupdf"}
    assert result["parsed_documents"][0]["parse_status"] in {"partial", "success"}
    assert "Total Assets" in "".join(result["parsed_documents"][0]["page_texts"].values())


def write_text_pdf(path: Path, lines: list[str]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("STSong-Light", 11)
    y = 800
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.save()


def test_real_chain_sample_to_skill3_skill4():
    from orchestrator_pkg.adapters.pdf_parse_adapter import run_pdf_parse
    from orchestrator_pkg.adapters.financial_extraction_adapter import run_financial_extraction
    from orchestrator_pkg.adapters.financial_analysis_adapter import run_financial_analysis

    module = load_skill1_module()
    task_id = "test_real_sample_chain"

    async def run_chain():
        skill1 = await module.run_analysis(json.dumps({"enterprise_name": "测试企业", "task_id": task_id, "mode": "sample"}, ensure_ascii=False))
        skill2 = await run_pdf_parse(skill1["pdf_handoff"], task_id)
        skill3 = await run_financial_extraction("测试企业", skill2["parsed_documents"], skill1["source_documents"], task_id)
        skill4 = await run_financial_analysis(task_id, "测试企业", skill3, skill1["source_documents"], {})
        return skill1, skill2, skill3, skill4

    skill1, skill2, skill3, skill4 = asyncio.run(run_chain())

    assert skill1["status"] == "ok"
    assert skill2["parse_summary"]["failed"] == 0
    assert skill3["extraction_status"] in {"success", "partial"}
    assert skill3["field_evidence"]
    assert skill4["analysis_status"] in {"success", "partial"}
    assert skill4["financial_indicators"]
