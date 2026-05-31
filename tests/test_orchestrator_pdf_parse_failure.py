"""Test: PDF parse failure scenarios"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.orchestrator.orchestrator import Orchestrator

def test_partial_failure():
    orch = Orchestrator(enterprise_name="测试企业_部分解析失败", task_id="test_parse_001")
    orch._source_documents = [
        {"document_id":"doc_001","source_platform":"中国货币网","title":"测试企业2025年度报告",
         "file_type":"annual_report","document_status":"selected_main","needs_deep_pdf_parse":True,"pdf_download_status":"success"},
        {"document_id":"doc_002","source_platform":"上海证券交易所","title":"测试企业2025年半年度报告",
         "file_type":"semi_annual_report","document_status":"selected_supplement","needs_deep_pdf_parse":True,"pdf_download_status":"failed"},
    ]
    orch._parsed_documents = [
        {"document_id":"doc_001","file_type":"annual_report","report_period":"2025","parser_used":"marker",
         "ocr_used":False,"page_count":120,"tables_found_count":10,"parse_status":"success","parse_confidence":"high","parse_warnings":[]},
    ]
    orch._failed_documents = [
        {"document_id":"doc_002","title":"测试企业2025年半年度报告","failure_stage":"pdf_parse","failure_reason":"PDF下载失败"},
    ]
    orch._structured_financial_data = {"extraction_status":"partial","data_periods":["2025"]}
    orch._financial_analysis = {"analysis_status":"not_ready","financial_indicators":[],"negative_findings":[]}
    orch._skill4_ready = False; orch._is_mock_analysis = True

    result = orch._build_final_json()
    assert result["task_status"] == "partial"
    assert len(result["parsed_documents_summary"]) == 1
    assert len(result["failed_documents"]) == 1
    print("  PASS test_partial_failure")

def test_all_failure():
    orch = Orchestrator(enterprise_name="测试企业_全部解析失败", task_id="test_parse_002")
    orch._source_documents = [
        {"document_id":"doc_003","source_platform":"深圳证券交易所","title":"测试企业2025年度报告",
         "file_type":"annual_report","document_status":"selected_main","needs_deep_pdf_parse":True},
    ]
    orch._parsed_documents = []
    orch._failed_documents = [
        {"document_id":"doc_003","title":"测试企业2025年度报告","failure_stage":"pdf_parse","failure_reason":"所有解析器均失败"},
    ]
    orch._structured_financial_data = {"extraction_status":"failed"}
    orch._financial_analysis = {"analysis_status":"failed"}
    orch._skill4_ready = False; orch._is_mock_analysis = False

    result = orch._build_final_json()
    assert result["task_status"] == "partial"
    assert result["data_status"] == "data_insufficient"
    print("  PASS test_all_failure")

def test_pdf_download_failed():
    orch = Orchestrator(enterprise_name="测试企业_下载失败", task_id="test_parse_003")
    orch._source_documents = [
        {"document_id":"doc_004","source_platform":"中国货币网","title":"测试企业2025年报",
         "file_type":"annual_report","document_status":"selected_main","needs_deep_pdf_parse":True,"pdf_download_status":"failed"},
    ]
    orch._parsed_documents = []
    orch._failed_documents = [
        {"document_id":"doc_004","title":"测试企业2025年报","failure_stage":"pdf_download","failure_reason":"PDF下载失败: HTTP 404"},
    ]
    orch._structured_financial_data = {"extraction_status":"failed"}
    orch._financial_analysis = {"analysis_status":"failed"}
    orch._skill4_ready = False; orch._is_mock_analysis = False

    result = orch._build_final_json()
    assert result["task_status"] == "partial"
    assert result["data_status"] == "data_insufficient"
    assert any("下载" in d.get("failure_reason","") for d in result["failed_documents"])
    print("  PASS test_pdf_download_failed")

if __name__ == "__main__":
    test_partial_failure(); test_all_failure(); test_pdf_download_failed()
    print("All tests passed")
