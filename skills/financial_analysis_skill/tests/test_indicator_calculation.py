#!/usr/bin/env python3
"""测试指标计算功能"""

import json
import os
import sys
import math

# 添加 scripts 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from run_analysis import (
    FieldIndex, safe_div, round2, make_indicator, calc_indicators,
    calc_direct_value_indicators, run_analysis,
)


def test_safe_div():
    """测试安全除法"""
    assert safe_div(10, 2) == 5.0
    assert safe_div(10, 0) is None
    assert safe_div(None, 2) is None
    assert safe_div(10, None) is None
    print("  [PASS] test_safe_div")


def test_round2():
    """测试四舍五入"""
    assert round2(1.234) == 1.23
    assert round2(1.235) == 1.24
    assert round2(None) is None
    print("  [PASS] test_round2")


def test_make_indicator():
    """测试指标构造"""
    ind = make_indicator("test_ind", "debt_capacity", "2023-12-31",
                         65.5, "%", "a/b*100", [{"field": "a"}], ["a"], "high")
    assert ind["indicator_name"] == "test_ind"
    assert ind["status"] == "available"
    assert ind["value"] == 65.5

    ind2 = make_indicator("missing_ind", "liquidity", "2023-12-31",
                          None, "%", "a/b", [], [])
    assert ind2["status"] == "unavailable"
    assert "无法计算" in ind2["unavailable_reason"]
    print("  [PASS] test_make_indicator")


def test_full_analysis_success():
    """测试完整分析流程 - 成功场景"""
    sample_path = os.path.join(os.path.dirname(__file__), "sample_input_success.json")
    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = run_analysis(data)

    assert result["analysis_status"] in ("success", "partial"), \
        f"Expected success/partial, got {result['analysis_status']}"
    assert len(result["financial_indicators"]) > 0, "Should have indicators"
    assert result["task_id"] == "TASK-2024-001"
    assert result["enterprise_name"] == "XX城市建设投资集团有限公司"

    # 验证资产负债率
    alr = None
    for ind in result["financial_indicators"]:
        if ind["indicator_name"] == "asset_liability_ratio" and ind["status"] == "available":
            alr = ind["value"]
            break
    assert alr is not None, "Should calculate asset_liability_ratio"
    assert alr == 70.00, f"asset_liability_ratio should be 70.00, got {alr}"

    print("  [PASS] test_full_analysis_success")


def test_analysis_missing_fields():
    """测试缺失字段场景"""
    sample_path = os.path.join(os.path.dirname(__file__), "sample_input_missing_fields.json")
    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = run_analysis(data)

    assert result["analysis_status"] in ("partial", "failed"), \
        f"Expected partial/failed with missing data, got {result['analysis_status']}"
    assert result["data_status"] in ("partial", "insufficient"), \
        f"Expected partial/insufficient, got {result['data_status']}"

    # 某些指标应为 unavailable
    unavailable_count = sum(
        1 for ind in result["financial_indicators"] if ind["status"] == "unavailable"
    )
    assert unavailable_count > 0, "Should have unavailable indicators"

    # 取 unavailable 指标不应生成 confirmed_risk
    confirmed_risks = [f for f in result["negative_findings"]
                       if f["finding_type"] == "confirmed_risk"]
    for cr in confirmed_risks:
        assert cr.get("indicator_name") != "", "Should not reference empty indicator"

    print("  [PASS] test_analysis_missing_fields")


def test_city_investment():
    """测试城投企业分析"""
    sample_path = os.path.join(os.path.dirname(__file__),
                                "sample_input_city_investment_company.json")
    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = run_analysis(data)

    assert result["enterprise_name"] == "ZZ城投开发有限公司"
    assert len(result["financial_indicators"]) > 0

    # 资产负债率 = 620/850*100 = 72.94%
    alr = None
    for ind in result["financial_indicators"]:
        if ind["indicator_name"] == "asset_liability_ratio" and ind["status"] == "available":
            alr = ind["value"]
            break
    assert alr is not None
    assert abs(alr - 72.94) < 0.1, f"Expected ~72.94, got {alr}"

    # 应有 generated summary
    assert result["analysis_summary"]["overall_view"], "Should have overall_view"
    assert "资产负债率" in result["analysis_summary"]["overall_view"]

    print("  [PASS] test_city_investment")


if __name__ == "__main__":
    print("Running indicator calculation tests...")
    test_safe_div()
    test_round2()
    test_make_indicator()
    test_full_analysis_success()
    test_analysis_missing_fields()
    test_city_investment()
    print("\nAll indicator calculation tests passed!")
