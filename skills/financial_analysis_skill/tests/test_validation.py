#!/usr/bin/env python3
"""测试输出校验功能"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from run_analysis import run_analysis, validate_output
from validate_analysis_output import validate


def test_validation_rule1_input_fields():
    """规则1: available指标必须有input_fields"""
    indicators = [{
        "indicator_name": "test",
        "status": "available",
        "input_fields": [],
    }]
    result = validate({"financial_indicators": indicators,
                       "negative_findings": [], "analysis_summary": {},
                       "frontend_financial_summary": {},
                       "data_status": "sufficient"})
    assert not result["passed"], "Should fail: available but no input_fields"
    print("  [PASS] test_validation_rule1_input_fields")


def test_validation_rule2_nan():
    """规则2: value不得为NaN"""
    import math
    indicators = [{
        "indicator_name": "test",
        "status": "available",
        "value": float("nan"),
        "input_fields": [{"field": "a"}],
    }]
    result = validate({"financial_indicators": indicators,
                       "negative_findings": [], "analysis_summary": {},
                       "frontend_financial_summary": {},
                       "data_status": "sufficient"})
    assert not result["passed"], "Should fail: NaN value"
    print("  [PASS] test_validation_rule2_nan")


def test_validation_rule3_unavailable_ref():
    """规则3: findings不得引用unavailable指标"""
    indicators = [{
        "indicator_name": "bad_indicator",
        "status": "unavailable",
        "unavailable_reason": "missing",
    }]
    findings = [{
        "finding_id": "F001",
        "finding_type": "confirmed_risk",
        "indicator_name": "bad_indicator",
    }]
    result = validate({"financial_indicators": indicators,
                       "negative_findings": findings,
                       "analysis_summary": {},
                       "frontend_financial_summary": {},
                       "data_status": "sufficient"})
    assert not result["passed"], "Should fail: references unavailable indicator"
    print("  [PASS] test_validation_rule3_unavailable_ref")


def test_validation_rule6_evidence():
    """规则6: confirmed_risk必须有evidence_text"""
    findings = [{
        "finding_id": "F001",
        "finding_type": "confirmed_risk",
        "indicator_name": "ok_ind",
    }]
    indicators = [{
        "indicator_name": "ok_ind",
        "status": "available",
        "value": 80,
        "input_fields": [{"field": "a"}],
    }]
    result = validate({"financial_indicators": indicators,
                       "negative_findings": findings,
                       "analysis_summary": {},
                       "frontend_financial_summary": {},
                       "data_status": "sufficient"})
    assert not result["passed"], "Should fail: confirmed_risk without evidence_text"
    print("  [PASS] test_validation_rule6_evidence")


def test_validation_rule7_forbidden():
    """规则7: analysis_summary禁止投资建议"""
    summary = {"overall_view": "建议买入该公司的债券"}
    result = validate({"financial_indicators": [],
                       "negative_findings": [],
                       "analysis_summary": summary,
                       "frontend_financial_summary": {},
                       "data_status": "sufficient"})
    assert not result["passed"], "Should fail: contains investment advice"
    print("  [PASS] test_validation_rule7_forbidden")


def test_validation_rule9_insufficient():
    """规则9: data_status=insufficient时only data_limitation"""
    findings = [{
        "finding_id": "F001",
        "finding_type": "confirmed_risk",
        "indicator_name": "ok_ind",
        "evidence_text": "test",
        "threshold": ">70",
        "source_document_id": "DOC-001",
    }]
    indicators = [{
        "indicator_name": "ok_ind",
        "status": "available",
        "value": 80,
        "input_fields": [{"field": "a"}],
    }]
    result = validate({"financial_indicators": indicators,
                       "negative_findings": findings,
                       "analysis_summary": {},
                       "frontend_financial_summary": {},
                       "data_status": "insufficient"})
    assert not result["passed"], "Should fail: insufficient but has non-data_limitation findings"
    print("  [PASS] test_validation_rule9_insufficient")


def test_full_output_passes():
    """测试完整正常输出的校验通过"""
    path = os.path.join(os.path.dirname(__file__), "sample_input_success.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = run_analysis(data)
    assert result["validation_result"]["passed"], \
        f"Validation should pass, errors: {result['validation_result']['errors']}"

    # 外部 validator 也应通过
    ext_result = validate(result)
    assert ext_result["passed"], \
        f"External validation should pass, errors: {ext_result['errors']}"

    print("  [PASS] test_full_output_passes")


if __name__ == "__main__":
    print("Running validation tests...")
    test_validation_rule1_input_fields()
    test_validation_rule2_nan()
    test_validation_rule3_unavailable_ref()
    test_validation_rule6_evidence()
    test_validation_rule7_forbidden()
    test_validation_rule9_insufficient()
    test_full_output_passes()
    print("\nAll validation tests passed!")
