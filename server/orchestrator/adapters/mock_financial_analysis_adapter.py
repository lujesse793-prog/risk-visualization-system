"""
Orchestrator Adapter: Mock Skill 4 – 财务分析（模拟）

当 financial_analysis_skill 尚未接入时，提供合理的 mock 输出。
不编造具体财务数值，但保持结构完整性。
"""
from __future__ import annotations

from typing import Any


async def run_mock_financial_analysis(
    structured_financial_data: dict[str, Any],
    source_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Mock Skill 4 输出。
    在真实 skill 就绪前，返回结构完整的占位数据。
    不编造具体的财务指标数值。
    """
    has_data = (
        structured_financial_data.get("extraction_status") == "success"
        or structured_financial_data.get("extraction_status") == "partial"
    )
    periods = structured_financial_data.get("data_periods", [])

    if not has_data:
        return _empty_analysis()

    all_indicators = [
        ("资产负债率", "负债合计 / 资产总计"),
        ("流动比率", "流动资产合计 / 流动负债合计"),
        ("现金短债比", "货币资金 / (短期借款 + 一年内到期的非流动负债)"),
        ("短期有息债务占比", "(短期借款 + 一年内到期的非流动负债) / (短期借款 + 一年内到期的非流动负债 + 长期借款 + 应付债券)"),
        ("营业收入同比变动", "本期营业收入 / 上期营业收入 - 1"),
        ("净利润同比变动", "本期净利润 / 上期净利润 - 1"),
        ("经营性净现金流÷营业收入", "经营活动产生的现金流量净额 / 营业收入"),
        ("财务费用率", "财务费用 / 营业收入"),
    ]

    return {
        "analysis_status": "partial",
        "is_mock": True,
        "financial_indicators": [
            {
                "indicator_name": name,
                "current_value": "数据已提取，等待 Skill 4 接入计算",
                "previous_value": "",
                "judgement": "",
                "source": "Skill 4 未接入 - 数据来自 Skill 3",
                "formula": formula,
            }
            for name, formula in all_indicators
        ],
        "negative_findings": [],
        "negative_summary_under_200_chars": (
            "财务数据已从公开披露文件中提取，但财务分析引擎（Skill 4）尚未接入，"
            "当前无法生成风险判断。已提取的原始数据可供前端查阅。"
        ),
        "analysis_summary": {
            "data_period_type": " | ".join(periods) if periods else "数据期间不明确",
            "analysis_basis": "Skill 3 提取的数据（Skill 4 未接入）",
            "core_indicators_summary": (
                f"已提取 {len(periods)} 个报告期的财务报表数据，"
                f"等待 Skill 4 接入后计算完整指标。"
            ),
            "risk_level_indicative": "数据不足",
        },
        "frontend_financial_summary": {
            "periods": periods,
            "key_metrics": [
                {
                    "label": "数据状态",
                    "values": ["Skill 4 未接入"],
                    "trend": "",
                }
            ],
        },
        "data_sufficiency": {
            "has_annual_report": any("Q" not in p for p in periods),
            "has_semi_annual": any("H" in p for p in periods),
            "indicator_count": 8,
            "missing_indicators": [],
        },
    }


def _empty_analysis() -> dict[str, Any]:
    """无数据时的空分析结果"""
    return {
        "analysis_status": "failed",
        "is_mock": True,
        "financial_indicators": [],
        "negative_findings": [],
        "negative_summary_under_200_chars": "",
        "analysis_summary": {
            "data_period_type": "",
            "analysis_basis": "",
            "core_indicators_summary": "",
            "risk_level_indicative": "数据不足",
        },
        "frontend_financial_summary": {
            "periods": [],
            "key_metrics": [],
        },
        "data_sufficiency": {
            "has_annual_report": False,
            "has_semi_annual": False,
            "indicator_count": 0,
            "missing_indicators": [
                "资产负债率", "流动比率", "现金短债比", "短期有息债务占比",
                "营业收入同比变动", "净利润同比变动", "经营性净现金流÷营业收入", "财务费用率",
            ],
        },
    }
