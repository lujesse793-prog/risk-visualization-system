"""Test: Financial extraction failure scenarios"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.orchestrator.orchestrator import Orchestrator

def test_extraction_failed():
    orch = Orchestrator(enterprise_name="测试企业_提取失败", task_id="test_ext_001")
    orch._source_documents = [
        {"document_id":"doc_001","source_platform":"中国货币网","title":"测试企业2025年度报告","file_type":"annual_report","document_status":"selected_main"},
    ]
    orch._parsed_documents = [
        {"document_id":"doc_001","file_type":"annual_report","report_period":"2025","parser_used":"marker","ocr_used":False,"page_count":120,"tables_found_count":15,"parse_status":"success","parse_confidence":"high","parse_warnings":[]},
    ]
    orch._structured_financial_data = {
        "extraction_status":"failed","extraction_confidence":"low","data_periods":[],
        "balance_sheet":[],"income_statement":[],"cash_flow_statement":[],
        "extraction_warnings":["无法从PDF中识别财务报表结构"],
        "missing_fields":["资产负债表: 货币资金","利润表: 营业收入"],
    }
    orch._financial_analysis = {"analysis_status":"failed","financial_indicators":[],"negative_findings":[]}
    orch._skill4_ready = False; orch._is_mock_analysis = False

    result = orch._build_final_json()
    assert result["task_status"] == "partial"
    assert result["data_status"] == "data_insufficient"
    assert "财务数据提取不完整" in result["message"]
    assert len(result["source_documents"]) == 1
    assert len(result["parsed_documents_summary"]) == 1
    assert len(result["financial_indicators"]) == 0
    print("  PASS test_extraction_failed")

def test_extraction_partial():
    orch = Orchestrator(enterprise_name="测试企业_部分提取", task_id="test_ext_002")
    orch._source_documents = [
        {"document_id":"doc_001","source_platform":"上海证券交易所","title":"测试企业2025年度报告","file_type":"annual_report","document_status":"selected_main"},
    ]
    orch._parsed_documents = [
        {"document_id":"doc_001","file_type":"annual_report","report_period":"2025","parser_used":"marker","ocr_used":False,"page_count":100,"tables_found_count":8,"parse_status":"success","parse_confidence":"medium","parse_warnings":[]},
    ]
    orch._structured_financial_data = {
        "extraction_status":"partial","extraction_confidence":"medium","data_periods":["2025"],
        "balance_sheet":[{"field_name":"货币资金","values":{"2025":{"value":"50.0000","unit":"亿元","raw_value":"50","raw_unit":"万元","scale_factor":0.0001}}}],
        "income_statement":[],"cash_flow_statement":[],
        "extraction_warnings":["部分字段未能提取"],"missing_fields":["利润表: 营业收入"],
    }
    orch._financial_analysis = {"analysis_status":"not_ready","financial_indicators":[],"negative_findings":[]}
    orch._skill4_ready = False; orch._is_mock_analysis = True

    result = orch._build_final_json()
    assert result["task_status"] == "partial"
    assert result["data_status"] == "financial_analysis_skill_not_ready"
    assert result["structured_financial_data"]["extraction_status"] == "partial"
    # 验证嵌套结构正确: values[period].value
    bs = result["structured_financial_data"]["balance_sheet"]
    money = [x for x in bs if x["field_name"] == "货币资金"][0]
    assert "50.0000" in money["values"]["2025"]["value"]
    print("  PASS test_extraction_partial")

if __name__ == "__main__":
    test_extraction_failed(); test_extraction_partial()
    print("All tests passed")
