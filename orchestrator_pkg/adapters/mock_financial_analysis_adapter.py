"""Fallback Skill4 output used only when the real Skill4 runner is unavailable."""
from __future__ import annotations

from typing import Any


async def run_mock_financial_analysis(skill4_input: dict[str, Any]) -> dict[str, Any]:
    task_id = skill4_input.get("task_id", "")
    enterprise_name = skill4_input.get("enterprise_name", "")
    context = skill4_input.get("analysis_context", {})
    periods = context.get("expected_periods", [])
    main_period = context.get("main_report_period", "")
    return {
        "task_id": task_id,
        "enterprise_name": enterprise_name,
        "analysis_status": "partial",
        "data_status": "partial",
        "main_period": main_period,
        "periods_analyzed": periods,
        "financial_indicators": [],
        "negative_findings": [],
        "unavailable_indicators": [],
        "analysis_summary": {
            "overall_view": "真实 Skill4 暂不可用，本次未生成正式财务分析结论。",
            "data_limitation_note": "已回退到 mock，仅保留上游结构化数据，不形成风险判断。",
        },
        "frontend_financial_summary": {},
        "risk_level_summary": {
            "confirmed_risk_count": 0,
            "warning_signal_count": 0,
            "data_limitation_count": 1,
            "highest_risk_level": "medium",
        },
        "validation_result": {"passed": True, "errors": [], "warnings": []},
    }
