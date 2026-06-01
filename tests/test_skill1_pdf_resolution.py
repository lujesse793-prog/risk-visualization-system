import asyncio
import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL1_PATH = PROJECT_ROOT / "skills" / "post-loan-analysis-report" / "scripts" / "run_analysis.py"


def load_skill1():
    spec = importlib.util.spec_from_file_location("skill1_pdf_resolution_test", SKILL1_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def fake_pdf_bytes():
    return b"%PDF-1.4\n" + b"0" * 512


def mark_subject_ok(doc, enterprise_name):
    doc["entity_verification"] = {
        "input_name": enterprise_name,
        "matched_name_in_document": enterprise_name,
        "matched_role": "发行人",
        "is_same_subject": True,
        "relationship_to_target": "same_subject",
        "verification_evidence": "mock first page contains enterprise name",
        "confidence": "high",
    }
    return doc


def test_source_url_detail_page_pdf_download(monkeypatch, tmp_path):
    module = load_skill1()

    def fake_fetch(url, referer="", timeout=30, retries=2):
        if url.endswith("/detail.html"):
            return {
                "ok": True,
                "final_url": url,
                "headers": {"Content-Type": "text/html"},
                "content": b"",
                "text": '<a href="/files/annual.pdf">测试企业2025年度报告.pdf</a>',
            }
        return {
            "ok": True,
            "final_url": url,
            "headers": {"Content-Type": "application/pdf"},
            "content": fake_pdf_bytes(),
            "text": "",
        }

    monkeypatch.setattr(module, "_fetch_url", fake_fetch)
    monkeypatch.setattr(module, "_verify_pdf_subject", mark_subject_ok)
    doc = module._standard_doc(
        {
            "title": "测试企业2025年度报告",
            "file_type": "annual_report",
            "report_period": "2025",
            "publish_date": "2026-04-30",
            "source_platform": "上海证券交易所",
            "source_url": "https://example.com/detail.html",
        },
        "测试企业",
        1,
        "selected_main",
        tmp_path,
    )
    assert doc["pdf_download_status"] == "success"
    assert Path(doc["local_pdf_path"]).exists()
    assert doc["pdf_sha256"]


def test_multiple_attachments_prefers_annual_report(monkeypatch, tmp_path):
    module = load_skill1()
    selected_urls = []

    def fake_fetch(url, referer="", timeout=30, retries=2):
        if url.endswith("/detail.html"):
            html = """
            <a href="/files/rating.pdf">测试企业评级报告.pdf</a>
            <a href="/files/annual.pdf">测试企业2025年度报告.pdf</a>
            """
            return {"ok": True, "final_url": url, "headers": {"Content-Type": "text/html"}, "content": b"", "text": html}
        selected_urls.append(url)
        return {"ok": True, "final_url": url, "headers": {"Content-Type": "application/pdf"}, "content": fake_pdf_bytes(), "text": ""}

    monkeypatch.setattr(module, "_fetch_url", fake_fetch)
    monkeypatch.setattr(module, "_verify_pdf_subject", mark_subject_ok)
    doc = module._standard_doc(
        {
            "title": "测试企业2025年度报告",
            "file_type": "annual_report",
            "report_period": "2025",
            "publish_date": "2026-04-30",
            "source_platform": "深圳证券交易所",
            "source_url": "https://example.com/detail.html",
        },
        "测试企业",
        1,
        "selected_main",
        tmp_path,
    )
    assert selected_urls[0].endswith("/files/annual.pdf")
    assert doc["pdf_download_status"] == "success"


def test_missing_pdf_records_attachment_not_found(monkeypatch, tmp_path):
    module = load_skill1()

    def fake_fetch(url, referer="", timeout=30, retries=2):
        return {"ok": True, "final_url": url, "headers": {"Content-Type": "text/html"}, "content": b"", "text": "<html>无附件</html>"}

    monkeypatch.setattr(module, "_fetch_url", fake_fetch)
    doc = module._standard_doc(
        {
            "title": "测试企业2025年度报告",
            "file_type": "annual_report",
            "publish_date": "2026-04-30",
            "source_platform": "中国货币网",
            "source_url": "https://example.com/detail.html",
        },
        "测试企业",
        1,
        "selected_main",
        tmp_path,
    )
    assert doc["pdf_download_status"] == "failed"
    assert doc["skipped_reason"] == "pdf_attachment_not_found"


def test_download_html_response_is_logged(monkeypatch, tmp_path):
    module = load_skill1()

    def fake_fetch(url, referer="", timeout=30, retries=2):
        return {
            "ok": True,
            "final_url": url,
            "headers": {"Content-Type": "text/html"},
            "content": b"<html>" + b"x" * 512 + b"</html>",
            "text": "<html>blocked</html>",
        }

    monkeypatch.setattr(module, "_fetch_url", fake_fetch)
    doc = module._standard_doc(
        {
            "title": "测试企业2025年度报告",
            "file_type": "annual_report",
            "publish_date": "2026-04-30",
            "source_platform": "上海证券交易所",
            "source_url": "https://example.com/detail.html",
            "pdf_url": "https://example.com/annual.pdf",
        },
        "测试企业",
        1,
        "selected_main",
        tmp_path,
    )
    assert doc["pdf_download_status"] == "failed"
    assert "download_failed_html_response" in doc["skipped_reason"]
    assert doc["download_debug_excerpt"].startswith("<html>")


def test_all_platform_search_errors_are_search_failed(monkeypatch, tmp_path):
    module = load_skill1()

    async def bad_search(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(module, "_search_channel", bad_search)
    result = asyncio.run(module.run_analysis('{"enterprise_name":"测试企业","task_id":"all_search_failed"}', output_dir=tmp_path))
    assert result["status"] == "failed"
    assert result["data_availability"]["data_level"] == "search_failed"
    assert result["pdf_handoff"]["no_latest_public_data"] is False


def test_handoff_requires_successful_local_pdf(monkeypatch, tmp_path):
    module = load_skill1()

    async def good_search(enterprise_name, channel_name, output_dir):
        if channel_name != "上海证券交易所":
            return {"source_name": channel_name, "searched": True, "status": "empty", "selected_documents": [], "skipped_documents": []}
        return {
            "source_name": channel_name,
            "searched": True,
            "status": "ok",
            "selected_documents": [{
                "title": "测试企业2025年度报告",
                "file_type": "annual_report",
                "report_period": "2025",
                "publish_date": "2026-04-30",
                "source_platform": channel_name,
                "source_url": "https://example.com/detail.html",
                "entity_verification": {
                    "input_name": "测试企业",
                    "matched_name_in_document": "测试企业",
                    "is_same_subject": True,
                    "confidence": "medium",
                },
            }],
            "skipped_documents": [],
        }

    def fake_fetch(url, referer="", timeout=30, retries=2):
        if url.endswith("/detail.html"):
            return {
                "ok": True,
                "final_url": url,
                "headers": {"Content-Type": "text/html"},
                "content": b"",
                "text": '<a href="/annual.pdf">测试企业2025年度报告.pdf</a>',
            }
        return {"ok": True, "final_url": url, "headers": {"Content-Type": "application/pdf"}, "content": fake_pdf_bytes(), "text": ""}

    monkeypatch.setattr(module, "_search_channel", good_search)
    monkeypatch.setattr(module, "_fetch_url", fake_fetch)
    monkeypatch.setattr(module, "_verify_pdf_subject", mark_subject_ok)
    result = asyncio.run(module.run_analysis('{"enterprise_name":"测试企业","task_id":"handoff_success"}', output_dir=tmp_path))
    docs = result["pdf_handoff"]["documents_needing_pdf_parse"]
    assert len(docs) == 1
    assert docs[0]["pdf_download_status"] == "success"
    assert Path(docs[0]["local_pdf_path"]).exists()
    assert docs[0]["pdf_sha256"]
