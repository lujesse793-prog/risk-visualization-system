"""
Orchestrator Adapter: Skill 4 – 财务分析

封装对 financial_analysis_skill 的调用。
接收 structured_financial_data，输出 financial_indicators 和 negative_findings。

注意：此 skill 目前还不可用，返回 analysis_status=not_ready。
"""
from __future__ import annotations

from typing import Any


async def run_financial_analysis(
    structured_financial_data: dict[str, Any],
    source_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    调用 Skill 4: 财务分析。
    当前为占位实现，返回 not_ready 状态，
    由 Orchestrator 的 mock 分支接管。
    """
    return {
        "analysis_status": "not_ready",
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
            "missing_indicators": [],
        },
    }
