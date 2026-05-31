"""Test: Complete success flow"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.orchestrator.orchestrator import Orchestrator

def test_full_success():
    orch = Orchestrator(enterprise_name="测试企业_完整成功", task_id="test_success_001")
    orch.progress.add("init",0,"初始化")
    orch.progress.add("search_started",2,"搜索")
    orch.progress.add("search_completed",15,"搜索完成")
    orch.progress.add("pdf_parse_started",18,"解析")
    orch.progress.add("pdf_parse_completed",30,"解析完成")
    orch.progress.add("financial_extract_started",31,"提取")
    orch.progress.add("financial_extract_completed",50,"提取完成")
    orch.progress.add("financial_analysis_started",51,"分析")
    orch.progress.add("financial_analysis_completed",75,"分析完成")

    orch._source_documents = [
        {"document_id":"doc_main_001","source_platform":"中国货币网","title":"测试企业2025年度报告",
         "file_type":"annual_report","report_period":"2025","publish_date":"2026-04-30",
         "source_url":"https://www.chinamoney.com.cn/xxx","pdf_url":"https://www.chinamoney.com.cn/xxx.pdf",
         "pdf_download_status":"success","pdf_sha256":"abc123","document_status":"selected_main",
         "needs_deep_pdf_parse":True,"entity_verification":{"input_name":"测试企业_完整成功","matched_name_in_document":"测试企业","matched_role":"发行人","is_same_subject":True,"verification_evidence":"一致","confidence":"high"}},
        {"document_id":"doc_supp_001","source_platform":"上海证券交易所","title":"测试企业2026年一季度报告",
         "file_type":"quarterly_report","report_period":"2026Q1","publish_date":"2026-04-30",
         "source_url":"https://www.sse.com.cn/xxx","pdf_url":"https://www.sse.com.cn/xxx.pdf",
         "pdf_download_status":"success","document_status":"selected_supplement","needs_deep_pdf_parse":True},
    ]
    orch._parsed_documents = [
        {"document_id":"doc_main_001","file_type":"annual_report","report_period":"2025","parser_used":"marker","ocr_used":False,"page_count":150,"tables_found_count":20,"parse_status":"success","parse_confidence":"high","parse_warnings":[]},
        {"document_id":"doc_supp_001","file_type":"quarterly_report","report_period":"2026Q1","parser_used":"marker","ocr_used":False,"page_count":40,"tables_found_count":5,"parse_status":"success","parse_confidence":"high","parse_warnings":[]},
    ]
    orch._failed_documents = []
    orch._structured_financial_data = {
        "extraction_status":"success","extraction_confidence":"high","data_periods":["2025","2024","2023"],
        "balance_sheet":[{"field_name":"货币资金","values":{"2025":{"value":"100.5000","unit":"亿元","raw_value":"100.5","raw_unit":"万元","scale_factor":0.0001},"2024":{"value":"90.0000","unit":"亿元","raw_value":"90","raw_unit":"万元","scale_factor":0.0001},"2023":{"value":"80.0000","unit":"亿元","raw_value":"80","raw_unit":"万元","scale_factor":0.0001}}},
         {"field_name":"资产总计","values":{"2025":{"value":"500.0000","unit":"亿元"},"2024":{"value":"450.0000","unit":"亿元"},"2023":{"value":"400.0000","unit":"亿元"}}}],
        "income_statement":[{"field_name":"营业收入","values":{"2025":{"value":"200.0000","unit":"亿元"},"2024":{"value":"180.0000","unit":"亿元"}}}],
        "cash_flow_statement":[],"extraction_warnings":[],"missing_fields":[],
    }
    orch._financial_analysis = {
        "analysis_status":"success","financial_indicators":[
            {"indicator_name":"资产负债率","current_value":"60.0%","previous_value":"58.0%","judgement":"正常","source":"2025年年报","formula":"负债合计 / 资产总计"},
            {"indicator_name":"营业收入同比变动","current_value":"+11.1%","previous_value":"+12.5%","judgement":"正常","source":"2025年年报","formula":"本期营业收入 / 上期营业收入 - 1"},
        ],"negative_findings":[],"negative_summary_under_200_chars":"未识别到可由公开披露文件直接支持的重大负面事项。",
        "analysis_summary":{"data_period_type":"三年一期","analysis_basis":"年度报告","core_indicators_summary":"财务结构稳健","risk_level_indicative":"低风险"},
        "frontend_financial_summary":{"periods":["2025","2024","2023"],"key_metrics":[]},
        "data_sufficiency":{"has_annual_report":True,"has_semi_annual":False,"indicator_count":8,"missing_indicators":[]},
    }
    orch._skill4_ready = True; orch._is_mock_analysis = False

    result = orch._build_final_json()

    assert result["task_id"] == "test_success_001"
    assert result["task_status"] == "completed"
    assert result["data_status"] == "success"
    assert result["skill4_ready"] is True
    assert result["is_mock_analysis"] is False
    assert len(result["source_documents"]) == 2
    assert len(result["parsed_documents_summary"]) == 2
    assert result["structured_financial_data"]["extraction_status"] == "success"
    assert len(result["financial_indicators"]) == 2
    assert result["failed_documents"] == []
    assert len(result["progress_events"]) >= 9
    assert result["validation_result"]["passed"] is True

    # 校验嵌套结构
    bs = result["structured_financial_data"]["balance_sheet"]
    money = [x for x in bs if x["field_name"]=="货币资金"][0]
    assert money["values"]["2025"]["value"] == "100.5000"
    assert money["values"]["2025"]["unit"] == "亿元"
    assert "raw_value" in money["values"]["2025"]
    assert "scale_factor" in money["values"]["2025"]

    print("  PASS test_full_success")

def test_minimal_success():
    orch = Orchestrator(enterprise_name="极简成功", task_id="test_success_min")
    orch.progress.add("init",0,"init")
    orch._source_documents = [{"document_id":"doc_001","source_platform":"深圳证券交易所","title":"极简企业2025年报","file_type":"annual_report","document_status":"selected_main"}]
    orch._parsed_documents = [{"document_id":"doc_001","file_type":"annual_report","parse_status":"success","parser_used":"pypdf","ocr_used":False,"page_count":10,"tables_found_count":2,"parse_confidence":"medium","parse_warnings":[]}]
    orch._structured_financial_data = {"extraction_status":"success","data_periods":["2025"],"balance_sheet":[],"income_statement":[],"cash_flow_statement":[]}
    orch._financial_analysis = {"analysis_status":"success","financial_indicators":[],"negative_findings":[]}
    orch._skill4_ready = True; orch._is_mock_analysis = False

    result = orch._build_final_json()
    assert result["task_status"] == "completed"
    assert result["data_status"] == "success"
    assert result["validation_result"]["passed"] is True
    print("  PASS test_minimal_success")

def test_schema_validation():
    """验证 schema 校验通过"""
    import json
    schema_file = Path(__file__).resolve().parent.parent / "server" / "orchestrator" / "schemas" / "final_json.schema.json"
    assert schema_file.exists(), f"Schema not found: {schema_file}"

    orch = Orchestrator(enterprise_name="Schema测试", task_id="test_schema")
    orch.progress.add("init",0,"init")
    orch._source_documents = [{"document_id":"d1","source_platform":"中国货币网","title":"测试年报","file_type":"annual_report","document_status":"selected_main"}]
    orch._parsed_documents = [{"document_id":"d1","file_type":"annual_report","report_period":"2025","parser_used":"marker","ocr_used":False,"page_count":50,"tables_found_count":3,"parse_status":"success","parse_confidence":"high","parse_warnings":[]}]
    orch._structured_financial_data = {"enterprise_name":"Schema测试","source_document_id":"d1","extraction_status":"success","extraction_confidence":"high","data_periods":["2025"],"balance_sheet":[],"income_statement":[],"cash_flow_statement":[],"business_segments":[],"extraction_warnings":[],"missing_fields":[]}
    orch._financial_analysis = {"analysis_status":"success","financial_indicators":[],"negative_findings":[],"negative_summary_under_200_chars":"未识别到可由公开披露文件直接支持的重大负面事项。","analysis_summary":{"data_period_type":"一期","analysis_basis":"年度报告","core_indicators_summary":"","risk_level_indicative":"低风险"},"frontend_financial_summary":{"periods":["2025"],"key_metrics":[]},"data_sufficiency":{"has_annual_report":True,"has_semi_annual":False,"indicator_count":0,"missing_indicators":[]}}
    orch._skill4_ready = True; orch._is_mock_analysis = False

    result = orch._build_final_json()
    assert result["validation_result"]["passed"] is True, f"Schema errors: {result['validation_result']['errors']}"
    print("  PASS test_schema_validation")

if __name__ == "__main__":
    test_full_success(); test_minimal_success(); test_schema_validation()
    print("All tests passed")
