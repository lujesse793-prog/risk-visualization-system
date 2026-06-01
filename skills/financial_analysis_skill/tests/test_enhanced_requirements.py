#!/usr/bin/env python3
"""增强需求回归测试"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from run_analysis import CORE_INDICATORS, STANDARD_FIELD_NAMES, run_analysis


def load_sample(name):
    path = os.path.join(os.path.dirname(__file__), name)
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def find_indicator(result, name, period="2023-12-31"):
    return next(
        ind for ind in result["financial_indicators"]
        if ind["indicator_name"] == name and ind.get("period") == period
    )


def serious_city_sample():
    data = load_sample("sample_input_city_investment_company.json")
    data = copy.deepcopy(data)
    for ev in data["field_evidence"]:
        if ev["standard_field_name"] == "总负债" and ev["period"] == "2023-12-31":
            ev["value_normalized"] = 740
            ev["value_raw"] = "740.00"
            ev["raw_row"] = "负债合计"
            ev["table_id"] = ev.get("table_id") or "BS-001"
    return data


def test_source_document_id_not_field_name():
    result = run_analysis(serious_city_sample())
    confirmed = [f for f in result["negative_findings"] if f["finding_type"] == "confirmed_risk"]
    assert confirmed, "should produce at least one confirmed risk"
    for finding in confirmed:
        assert finding["source_document_id"] not in STANDARD_FIELD_NAMES


def test_confirmed_risk_source_document_exists():
    result = run_analysis(serious_city_sample())
    doc_ids = {doc["document_id"] for doc in result["source_documents"]}
    confirmed = [f for f in result["negative_findings"] if f["finding_type"] == "confirmed_risk"]
    assert confirmed
    for finding in confirmed:
        assert finding["source_document_id"] in doc_ids
        assert finding["evidence_text"]


def test_cash_short_debt_ratio_unit_is_times():
    result = run_analysis(load_sample("sample_input_success.json"))
    ind = find_indicator(result, "cash_short_debt_ratio")
    assert ind["unit"] == "倍"
    assert ind["value"] == 0.5


def test_quick_ratio_requires_inventory():
    data = load_sample("sample_input_success.json")
    for rows in data["structured_financial_data"]["financial_tables"].values():
        rows[:] = [
            row for row in rows
            if not (
                row.get("standard_field_name") == "inventory"
                and row.get("period") == "2023-12-31"
            )
        ]
    result = run_analysis(data)
    ind = find_indicator(result, "quick_ratio")
    assert ind["status"] == "unavailable"


def test_operating_cash_flow_yoy():
    data = load_sample("sample_input_success.json")
    data["structured_financial_data"]["financial_tables"]["cash_flow_statement"].append({
        "standard_field_name": "net_operating_cash_flow",
        "period": "2022-12-31",
        "value": 10,
        "unit": "亿元",
        "source_document_id": "DOC-002",
        "confidence": "high",
    })
    result = run_analysis(data)
    ind = find_indicator(result, "net_cash_flow_from_operating_activities_yoy")
    assert ind["status"] == "available"
    assert ind["value"] == -50.0
    assert ind["unit"] == "%"


def test_long_term_payables_in_interest_bearing_debt():
    data = load_sample("sample_input_city_investment_company.json")
    data["field_evidence"].append({
        "field_name": "长期应付款",
        "standard_field_name": "长期应付款",
        "period": "2023-12-31",
        "value_raw": "10.00",
        "value_normalized": 10,
        "unit_raw": "亿元",
        "unit_normalized": "亿元",
        "source_document_id": "DOC-004",
        "source_pdf": "ZZ城投2023年报.pdf",
        "page": 57,
        "table_id": "BS-002",
        "table_title": "合并资产负债表(续)",
        "raw_row": "长期应付款",
        "raw_column": "期末余额",
        "confidence": "high",
    })
    result = run_analysis(data)
    ind = find_indicator(result, "interest_bearing_debt")
    assert ind["value"] == 490
    assert "长期应付款可能包含非债务性质款项" in ind["formula_warning"]


def test_data_limitation_only_for_core_indicators():
    result = run_analysis(load_sample("sample_input_missing_fields.json"))
    for finding in result["negative_findings"]:
        if finding["finding_type"] == "data_limitation" and finding["indicator_name"]:
            assert finding["indicator_name"] in CORE_INDICATORS


def test_no_na_in_analysis_summary():
    result = run_analysis(load_sample("sample_input_missing_fields.json"))
    text = json.dumps(result["analysis_summary"], ensure_ascii=False)
    assert "N/A" not in text


def test_continuous_negative_cash_flow_requires_two_periods():
    data = load_sample("sample_input_success.json")
    for row in data["structured_financial_data"]["financial_tables"]["cash_flow_statement"]:
        if row.get("standard_field_name") == "net_operating_cash_flow" and row.get("period") == "2023-12-31":
            row["value"] = -5
    result = run_analysis(data)
    assert "持续为负" not in json.dumps(result["analysis_summary"], ensure_ascii=False)


def test_frontend_short_term_interest_bearing_debt_not_null_when_fields_exist():
    result = run_analysis(load_sample("sample_input_success.json"))
    assert result["frontend_financial_summary"]["short_term_interest_bearing_debt"] == 90


def test_data_status_based_on_main_period_only():
    data = load_sample("sample_input_success.json")
    data["analysis_context"]["expected_periods"] = ["2023-12-31", "2022-12-31", "2021-12-31"]
    result = run_analysis(data)
    assert result["data_status"] == "sufficient"
    assert result["analysis_status"] == "success"


def test_no_data_limitation_for_auxiliary_period_missing_fields():
    data = load_sample("sample_input_success.json")
    data["analysis_context"]["expected_periods"] = ["2023-12-31", "2022-12-31", "2021-12-31"]
    result = run_analysis(data)
    assert not [
        f for f in result["negative_findings"]
        if f["finding_type"] == "data_limitation" and f.get("period") != result["main_period"]
    ]


def test_negative_findings_include_source_pdf_and_source_refs():
    result = run_analysis(serious_city_sample())
    findings = [f for f in result["negative_findings"] if f["finding_type"] != "data_limitation"]
    assert findings
    for finding in findings:
        assert "source_pdf" in finding
        assert "table_title" in finding
        assert isinstance(finding.get("source_refs"), list)
        assert all(isinstance(ref, dict) for ref in finding["source_refs"])


def test_no_confirmed_risk_when_source_documents_empty():
    data = serious_city_sample()
    data["source_documents"] = []
    result = run_analysis(data)
    assert not [f for f in result["negative_findings"] if f["finding_type"] == "confirmed_risk"]


def test_partial_short_debt_formula_warning():
    data = load_sample("sample_input_success.json")
    rows = data["structured_financial_data"]["financial_tables"]["balance_sheet"]
    rows[:] = [
        row for row in rows
        if not (
            row.get("standard_field_name") == "non_current_liabilities_due_within_one_year"
            and row.get("period") == "2023-12-31"
        )
    ]
    result = run_analysis(data)
    ind = find_indicator(result, "short_term_interest_bearing_debt")
    assert ind["status"] == "available"
    assert ind["value"] == 60
    assert "短期有息债务口径不完整" in ind["formula_warning"]
    dependent = find_indicator(result, "cash_short_debt_ratio")
    assert "短期有息债务口径不完整" in dependent["formula_warning"]


def test_interest_bearing_debt_missing_components_warning():
    result = run_analysis(load_sample("sample_input_success.json"))
    ind = find_indicator(result, "interest_bearing_debt")
    assert ind["status"] == "available"
    assert "有息债务口径不完整" in ind["formula_warning"]


def test_no_duplicate_indicator_name_period():
    result = run_analysis(load_sample("sample_input_success.json"))
    keys = [(ind["indicator_name"], ind["period"]) for ind in result["financial_indicators"]]
    assert len(keys) == len(set(keys))


def test_orchestrator_source_documents_schema_compatible():
    data = load_sample("sample_input_city_investment_company.json")
    for ev in data["field_evidence"]:
        if ev.get("source_document_id") == "DOC-004":
            ev.pop("source_pdf", None)
    data["source_documents"][0] = {
        "document_id": "DOC-004",
        "source_platform": "中国货币网",
        "file_type": "annual_report",
        "report_period": "2023-12-31",
        "publish_date": "2024-04-30",
        "source_url": "https://example.invalid/report",
        "pdf_url": "https://example.invalid/report.pdf",
        "local_pdf_path": r"C:\reports\ZZ城投2023年报.pdf",
        "document_status": "available",
        "entity_verification": {"matched": True},
    }
    result = run_analysis(data)
    assert result["source_documents"][0]["source_pdf"] == r"C:\reports\ZZ城投2023年报.pdf"
    finding = next(f for f in result["negative_findings"] if f.get("source_document_id") == "DOC-004")
    assert finding["source_pdf"] == r"C:\reports\ZZ城投2023年报.pdf"


def test_asset_liability_threshold_70_watch_75_warning_85_serious():
    data = load_sample("sample_input_city_investment_company.json")
    result = run_analysis(data)
    alr_finding = next(f for f in result["negative_findings"] if f["indicator_name"] == "asset_liability_ratio")
    assert alr_finding["risk_level"] == "low"
    assert ">= 70%" in alr_finding["threshold"]

    data = serious_city_sample()
    for ev in data["field_evidence"]:
        if ev["standard_field_name"] == "总负债" and ev["period"] == "2023-12-31":
            ev["value_normalized"] = 660
    result = run_analysis(data)
    alr_finding = next(f for f in result["negative_findings"] if f["indicator_name"] == "asset_liability_ratio")
    assert alr_finding["risk_level"] == "medium"
    assert ">= 75%" in alr_finding["threshold"]

    result = run_analysis(serious_city_sample())
    alr_finding = next(f for f in result["negative_findings"] if f["indicator_name"] == "asset_liability_ratio")
    assert alr_finding["risk_level"] == "high"
    assert alr_finding["finding_type"] == "confirmed_risk"
    assert ">= 85%" in alr_finding["threshold"]


def test_auxiliary_period_missing_only_affects_yoy():
    data = load_sample("sample_input_success.json")
    data["structured_financial_data"]["financial_tables"]["income_statement"] = [
        row for row in data["structured_financial_data"]["financial_tables"]["income_statement"]
        if not (row.get("period") == "2022-12-31" and row.get("standard_field_name") == "operating_revenue")
    ]
    result = run_analysis(data)
    yoy = find_indicator(result, "revenue_yoy")
    assert yoy["status"] == "unavailable"
    assert result["data_status"] == "sufficient"
    assert not [
        ind for ind in result["unavailable_indicators"]
        if ind["period"] == "2022-12-31" and ind["indicator_name"] != "revenue_yoy"
    ]


def test_unknown_page_outputs_null_not_zero():
    result = run_analysis(load_sample("sample_input_success.json"))
    assert all(
        field.get("page") is None
        for ind in result["financial_indicators"]
        for field in ind.get("input_fields", [])
        if not field.get("table_id")
    )


def test_negative_finding_judgement_uses_chinese_name():
    result = run_analysis(load_sample("sample_input_city_investment_company.json"))
    finding = next(f for f in result["negative_findings"] if f["indicator_name"] == "asset_liability_ratio")
    assert "资产负债率" in finding["judgement"]
    assert "asset_liability_ratio" not in finding["judgement"]
    assert "关注阈值" in finding["judgement"]


def test_failed_insufficient_has_frontend_friendly_note():
    data = load_sample("sample_input_success.json")
    data["structured_financial_data"] = {"financial_tables": {"balance_sheet": [], "income_statement": [], "cash_flow_statement": []}}
    data["field_evidence"] = []
    result = run_analysis(data)
    assert result["analysis_status"] == "failed"
    assert result["data_status"] == "insufficient"
    assert result["analysis_summary"]["data_limitation_note"] == "公开财务字段不足，仅能完成有限分析，无法形成完整财务判断。"


if __name__ == "__main__":
    for name, func in sorted(globals().items()):
        if name.startswith("test_"):
            func()
            print(f"  [PASS] {name}")
