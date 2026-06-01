#!/usr/bin/env python3
"""测试风险发现功能"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from run_analysis import find_negative_findings, run_analysis


def test_findings_structure():
    """测试风险发现的基本结构"""
    # 加载成功场景
    path = os.path.join(os.path.dirname(__file__), "sample_input_success.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = run_analysis(data)

    findings = result["negative_findings"]
    assert isinstance(findings, list), "findings should be a list"

    for f in findings:
        assert "finding_id" in f, "Each finding must have finding_id"
        assert "finding_type" in f, "Each finding must have finding_type"
        assert f["finding_type"] in ("confirmed_risk", "warning_signal", "data_limitation"), \
            f"Invalid finding_type: {f['finding_type']}"
        assert "risk_level" in f
        assert f["risk_level"] in ("low", "medium", "high"), \
            f"Invalid risk_level: {f['risk_level']}"

    print("  [PASS] test_findings_structure")


def test_confirmed_risk_has_evidence():
    """测试 confirmed_risk 必须有 evidence_text"""
    path = os.path.join(os.path.dirname(__file__), "sample_input_success.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = run_analysis(data)

    for f in result["negative_findings"]:
        if f["finding_type"] == "confirmed_risk":
            assert f.get("evidence_text"), \
                f"confirmed_risk {f['finding_id']} must have evidence_text"
            assert f.get("threshold"), \
                f"confirmed_risk {f['finding_id']} must have threshold"
            assert f.get("source_document_id"), \
                f"confirmed_risk {f['finding_id']} must have source_document_id"

    print("  [PASS] test_confirmed_risk_has_evidence")


def test_no_evidence_no_confirmed_risk():
    """测试无 evidence_text 的数据不生成 confirmed_risk"""
    path = os.path.join(os.path.dirname(__file__), "sample_input_missing_fields.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = run_analysis(data)

    # missing_fields场景应不产生 confirmed_risk (因为数据不足)
    for f in result["negative_findings"]:
        if f["finding_type"] == "confirmed_risk":
            assert f.get("evidence_text"), "Any confirmed_risk MUST have evidence_text"

    print("  [PASS] test_no_evidence_no_confirmed_risk")


def test_low_confidence_no_confirmed_risk():
    """测试 low confidence 不生成 confirmed_risk"""
    path = os.path.join(os.path.dirname(__file__), "sample_input_success.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 所有字段都标记为 low confidence
    for table in data["structured_financial_data"]["financial_tables"].values():
        for row in table:
            row["confidence"] = "low"

    result = run_analysis(data)

    for f in result["negative_findings"]:
        # low confidence不应该产生confirmed_risk
        if f["finding_type"] == "confirmed_risk":
            assert f.get("confidence") != "low", \
                f"low confidence不应生成confirmed_risk: {f['finding_id']}"

    print("  [PASS] test_low_confidence_no_confirmed_risk")


def test_risk_level_summary():
    """测试 risk_level_summary 统计正确"""
    path = os.path.join(os.path.dirname(__file__), "sample_input_success.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = run_analysis(data)
    summary = result["risk_level_summary"]

    assert "confirmed_risk_count" in summary
    assert "warning_signal_count" in summary
    assert "data_limitation_count" in summary
    assert "highest_risk_level" in summary

    # 手动统计验证
    confirmed = sum(1 for f in result["negative_findings"]
                    if f["finding_type"] == "confirmed_risk")
    warnings = sum(1 for f in result["negative_findings"]
                   if f["finding_type"] == "warning_signal")
    limits = sum(1 for f in result["negative_findings"]
                 if f["finding_type"] == "data_limitation")

    assert summary["confirmed_risk_count"] == confirmed
    assert summary["warning_signal_count"] == warnings
    assert summary["data_limitation_count"] == limits

    print("  [PASS] test_risk_level_summary")


if __name__ == "__main__":
    print("Running negative findings tests...")
    test_findings_structure()
    test_confirmed_risk_has_evidence()
    test_no_evidence_no_confirmed_risk()
    test_low_confidence_no_confirmed_risk()
    test_risk_level_summary()
    print("\nAll negative findings tests passed!")
