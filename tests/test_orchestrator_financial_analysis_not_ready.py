"""Test: Skill 4 not ready scenarios"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.orchestrator.orchestrator import Orchestrator

def test_skill4_not_ready_with_data():
    orch = Orchestrator(enterprise_name="测试企业_Skill4未接入", task_id="test_sk4_001")
    orch._source_documents = [
        {"document_id":"doc_001","source_platform":"中国货币网","title":"测试企业2025年度报告","file_type":"annual_report","report_period":"2025","document_status":"selected_main"},
        {"document_id":"doc_002","source_platform":"上海证券交易所","title":"测试企业2025年度报告","file_type":"annual_report","report_period":"2025","document_status":"selected_supplement"},
    ]
    orch._parsed_documents = [
        {"document_id":"doc_001","file_type":"annual_report","report_period":"2025","parser_used":"marker","ocr_used":False,"page_count":150,"tables_found_count":12,"parse_status":"success","parse_confidence":"high","parse_warnings":[]},
    ]
    orch._structured_financial_data = {
        "extraction_status":"success","extraction_confidence":"high","data_periods":["2025","2024","2023"],
        "balance_sheet":[{"field_name":"货币资金","values":{"2025":{"value":"80.0000","unit":"亿元","raw_value":"80","raw_unit":"万元","scale_factor":0.0001}}}],
        "income_statement":[],"cash_flow_statement":[],"extraction_warnings":[],"missing_fields":[],
    }
    orch._financial_analysis = {"analysis_status":"not_ready","financial_indicators":[],"negative_findings":[]}
    orch._skill4_ready = False; orch._is_mock_analysis = True

    result = orch._build_final_json()
    assert result["task_status"] == "partial", f"expected partial, got {result['task_status']}"
    assert result["data_status"] == "financial_analysis_skill_not_ready"
    assert "尚未接入" in result["message"] or "mock" in result["message"]
    assert result["skill4_ready"] is False
    assert result["is_mock_analysis"] is True
    assert len(result["source_documents"]) == 2
    assert len(result["parsed_documents_summary"]) == 1
    print("  PASS test_skill4_not_ready_with_data")

def test_skill4_not_ready_no_data():
    orch = Orchestrator(enterprise_name="测试企业_无数据", task_id="test_sk4_002")
    orch._source_documents = []
    orch._parsed_documents = []
    orch._structured_financial_data = {"extraction_status":"failed"}
    orch._financial_analysis = {"analysis_status":"not_ready"}
    orch._skill4_ready = False; orch._is_mock_analysis = True

    result = orch._build_final_json()
    assert result["task_status"] == "completed"
    assert result["data_status"] == "no_latest_public_data"
    print("  PASS test_skill4_not_ready_no_data")

def test_skill4_ready():
    """Skill 4 真实接入的场景"""
    orch = Orchestrator(enterprise_name="测试企业_Skill4已接入", task_id="test_sk4_003")
    orch._source_documents = [
        {"document_id":"doc_001","source_platform":"深圳证券交易所","title":"测试企业2025年报","file_type":"annual_report","document_status":"selected_main"},
    ]
    orch._parsed_documents = [
        {"document_id":"doc_001","file_type":"annual_report","report_period":"2025","parser_used":"marker","ocr_used":False,"page_count":100,"tables_found_count":5,"parse_status":"success","parse_confidence":"high","parse_warnings":[]},
    ]
    orch._structured_financial_data = {
        "extraction_status":"success","data_periods":["2025","2024"],
        "balance_sheet":[],"income_statement":[],"cash_flow_statement":[],
        "extraction_warnings":[],"missing_fields":[],
    }
    orch._financial_analysis = {
        "analysis_status":"success",
        "financial_indicators":[{"indicator_name":"资产负债率","current_value":"60%","previous_value":"58%","judgement":"正常","source":"2025年报"}],
        "negative_findings":[],
        "analysis_summary":{"risk_level_indicative":"低风险"},
        "frontend_financial_summary":{"periods":["2025","2024"],"key_metrics":[]},
        "data_sufficiency":{"has_annual_report":True,"indicator_count":1},
    }
    orch._skill4_ready = True; orch._is_mock_analysis = False

    result = orch._build_final_json()
    assert result["task_status"] == "completed"
    assert result["data_status"] == "success"
    assert result["skill4_ready"] is True
    assert result["is_mock_analysis"] is False
    assert len(result["financial_indicators"]) == 1
    print("  PASS test_skill4_ready")

if __name__ == "__main__":
    test_skill4_not_ready_with_data(); test_skill4_not_ready_no_data(); test_skill4_ready()
    print("All tests passed")
