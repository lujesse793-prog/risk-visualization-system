"""
测试: 无最新公开数据场景
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.orchestrator.orchestrator import Orchestrator


def test_no_latest_public_data():
    orch = Orchestrator(enterprise_name="测试企业_无公开数据", task_id="test_no_data_001")
    orch._source_documents = []
    orch._parsed_documents = []
    orch._structured_financial_data = {"extraction_status": "failed"}
    orch._financial_analysis = {"analysis_status": "failed"}
    orch._skill4_ready = False
    orch._is_mock_analysis = True

    result = orch._build_final_json()

    assert result["task_status"] == "completed"
    assert result["data_status"] == "no_latest_public_data"
    assert "未有最新公开财务数据披露" in result["message"]
    assert len(result["financial_indicators"]) == 0
    assert result["validation_result"]["passed"] is True
    print("  PASS test_no_latest_public_data")


def test_skipped_only():
    orch = Orchestrator(enterprise_name="测试企业_仅有跳过文档", task_id="test_no_data_002")
    orch._source_documents = [
        {"document_id": "doc_001", "source_platform": "中国货币网",
         "title": "测试企业2024年度报告", "file_type": "annual_report",
         "report_period": "2024", "document_status": "stale_or_prior_period_document",
         "needs_deep_pdf_parse": False},
        {"document_id": "doc_002", "source_platform": "上海证券交易所",
         "title": "其他企业2025年度报告", "file_type": "annual_report",
         "report_period": "2025", "document_status": "subject_mismatch",
         "needs_deep_pdf_parse": False},
    ]
    orch._parsed_documents = []
    orch._structured_financial_data = {"extraction_status": "failed"}
    orch._financial_analysis = {"analysis_status": "failed"}
    orch._skill4_ready = False
    orch._is_mock_analysis = True

    result = orch._build_final_json()
    assert result["task_status"] == "completed"
    assert result["data_status"] == "no_latest_public_data"
    print("  PASS test_skipped_only")


if __name__ == "__main__":
    test_no_latest_public_data()
    test_skipped_only()
    print("All tests passed")
