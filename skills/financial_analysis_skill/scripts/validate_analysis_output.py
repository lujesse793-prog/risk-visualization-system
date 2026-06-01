#!/usr/bin/env python3
"""validate_analysis_output.py - 验证分析输出JSON是否符合规范

用法:
    python scripts/validate_analysis_output.py --input analysis_output.json
"""

import argparse
import json
import math
import sys


def validate(data):
    """执行增强校验规则，返回(通过, 错误列表, 警告列表)"""
    errors = []
    warnings = []

    indicators = data.get("financial_indicators", [])
    findings = data.get("negative_findings", [])
    summary = data.get("analysis_summary", {})
    frontend = data.get("frontend_financial_summary", {})
    data_status = data.get("data_status", "")
    analysis_status = data.get("analysis_status", "")
    main_period = data.get("main_period", "")
    source_docs = data.get("source_documents", [])
    valid_doc_ids = {d.get("document_id") for d in source_docs if d.get("document_id")}
    debt_components = [
        "short_term_borrowings",
        "non_current_liabilities_due_within_one_year",
        "long_term_borrowings",
        "bonds_payable",
        "long_term_payables",
    ]

    standard_field_names = {
        "total_assets", "total_current_assets", "total_non_current_assets",
        "cash_and_cash_equivalents", "inventory", "accounts_receivable",
        "notes_receivable", "other_receivables", "total_liabilities",
        "total_current_liabilities", "total_non_current_liabilities",
        "short_term_borrowings", "non_current_liabilities_due_within_one_year",
        "long_term_borrowings", "bonds_payable", "long_term_payables",
        "total_owner_equity", "paid_in_capital", "capital_reserve",
        "other_equity_instruments", "undistributed_profit", "operating_revenue",
        "operating_cost", "operating_profit", "total_profit", "net_profit",
        "net_profit_attributable_to_parent", "financial_expenses", "interest_expense",
        "net_cash_flow_from_operating_activities", "net_cash_flow_from_investing_activities",
        "net_cash_flow_from_financing_activities",
    }
    core_indicators = {
        "asset_liability_ratio", "cash_short_debt_ratio", "current_ratio", "quick_ratio",
        "operating_revenue", "net_profit", "net_cash_flow_from_operating_activities",
        "interest_bearing_debt", "short_term_debt_ratio", "operating_cash_flow_to_short_debt",
    }

    def negative_streak(indicator_name):
        vals = [
            ind.get("value") for ind in indicators
            if ind.get("indicator_name") == indicator_name and ind.get("status") == "available"
        ]
        streak = 0
        for v in vals:
            if v is not None and v < 0:
                streak += 1
            else:
                break
        return streak

    seen_indicator_keys = set()
    for ind in indicators:
        name = ind.get("indicator_name", "?")
        key = (name, ind.get("period", ""))
        if key in seen_indicator_keys:
            errors.append(f"[R13] 同一 indicator_name + period 不得重复: {name}({ind.get('period', '')})")
        seen_indicator_keys.add(key)
        if ind.get("status") == "available" and not ind.get("input_fields"):
            errors.append(f"[R1] 指标 {name} status=available 但缺少 input_fields")
        v = ind.get("value")
        if v is not None:
            try:
                fv = float(v)
                if math.isnan(fv) or math.isinf(fv):
                    errors.append(f"[R2] 指标 {name} value 为 NaN/Infinity")
            except (ValueError, TypeError):
                pass
        if name == "cash_short_debt_ratio" and ind.get("status") == "available" and ind.get("unit") != "倍":
            errors.append("[R6] cash_short_debt_ratio 单位必须是“倍”，不得是“%”")
        if name == "quick_ratio" and ind.get("status") == "available":
            has_inventory = any(
                f.get("standard_field_name") == "inventory" and f.get("value") is not None
                for f in ind.get("input_fields", [])
            )
            if not has_inventory:
                errors.append("[R7] quick_ratio 如果 inventory 缺失，不得计算")
        for ref in ind.get("source_refs", []):
            if isinstance(ref, str):
                errors.append(f"[R12] {name}.source_refs 必须是证据引用对象，不得只是字段名字符串")
        if name == "short_term_interest_bearing_debt" and ind.get("status") == "available":
            fields = {f.get("standard_field_name"): f.get("value") for f in ind.get("input_fields", [])}
            has_st = fields.get("short_term_borrowings") is not None
            has_due = fields.get("non_current_liabilities_due_within_one_year") is not None
            if has_st != has_due and "短期有息债务口径不完整" not in ind.get("formula_warning", ""):
                errors.append("[R14] short_term_interest_bearing_debt 缺少短债组成字段时必须有 formula_warning")
        if name == "interest_bearing_debt" and ind.get("status") == "available":
            fields = {f.get("standard_field_name"): f.get("value") for f in ind.get("input_fields", [])}
            missing_debt = [component for component in debt_components if fields.get(component) is None]
            if missing_debt and "有息债务口径不完整" not in ind.get("formula_warning", ""):
                errors.append("[R15] interest_bearing_debt 存在缺失债务字段时必须有 formula_warning")

    unavailable_keys = {
        (ind.get("indicator_name", ""), ind.get("period", ""))
        for ind in indicators
        if ind.get("status") == "unavailable"
    }
    for f in findings:
        fid = f.get("finding_id", "?")
        if f.get("finding_type") in ("confirmed_risk", "warning_signal"):
            key = (f.get("indicator_name", ""), f.get("period", ""))
            if key in unavailable_keys:
                errors.append(f"[R3] finding {fid} 引用了 unavailable 指标 {key[0]}({key[1]})")
            if not f.get("threshold"):
                errors.append(f"[R4] finding {fid} 缺少 threshold")
        if f.get("source_document_id") in standard_field_names:
            errors.append(f"[R5] finding {fid} source_document_id 不得等于字段名")
        if f.get("finding_type") == "data_limitation" and f.get("indicator_name"):
            if f.get("indicator_name") not in core_indicators:
                errors.append(f"[R8] data_limitation finding 只能针对 core_indicators: {f.get('indicator_name')}")
            if main_period and f.get("period") != main_period:
                errors.append(f"[R16] data_limitation finding 默认只能针对 main_period: {f.get('indicator_name')}({f.get('period')})")
        if f.get("source_refs") is not None:
            if not isinstance(f.get("source_refs"), list) or any(isinstance(ref, str) for ref in f.get("source_refs", [])):
                errors.append(f"[R17] finding {fid}.source_refs 必须是对象数组，不能是字符串")
        if f.get("finding_type") == "confirmed_risk":
            if not valid_doc_ids:
                errors.append(f"[R18] source_documents 为空时不得存在 confirmed_risk: {fid}")
            if not f.get("source_document_id"):
                errors.append(f"[R5] finding {fid} confirmed_risk 缺少 source_document_id")
            if f.get("source_document_id") not in valid_doc_ids:
                errors.append(f"[R5] finding {fid} source_document_id 不存在于 source_documents[].document_id")
            if not f.get("evidence_text"):
                errors.append(f"[R6] finding {fid} confirmed_risk 缺少 evidence_text")
            page = f.get("page")
            has_page = isinstance(page, int) and page > 0
            if not (has_page or f.get("table_id")):
                errors.append(f"[R6] finding {fid} confirmed_risk 的 page 必须为正整数，或 table_id 非空")
            if not f.get("source_pdf"):
                warnings.append(f"[R19] finding {fid} confirmed_risk 建议提供 source_pdf")
            if not f.get("source_refs"):
                errors.append(f"[R20] finding {fid} confirmed_risk 必须至少有一条 source_refs")
            if f.get("confidence") == "low":
                errors.append(f"[R21] finding {fid} confirmed_risk 置信度不能为 low")

    forbidden = [
        "建议买入", "建议卖出", "建议持有", "信用评级为", "投资建议",
        "推荐买入", "推荐卖出", "N/A",
    ]
    for key, text in summary.items():
        if isinstance(text, str):
            for word in forbidden:
                if word in text:
                    errors.append(f"[R9] analysis_summary.{key} 包含禁止词汇或 N/A: {word}")
    if any("持续为负" in text for text in summary.values() if isinstance(text, str)):
        if negative_streak("net_cash_flow_from_operating_activities") < 2:
            errors.append("[R10] analysis_summary 中“持续为负”必须有连续两期为负的数据支持")

    for k, v in frontend.items():
        if v is not None:
            try:
                fv = float(v)
                if math.isnan(fv) or math.isinf(fv):
                    errors.append(f"[R8] frontend_financial_summary.{k} 值为 NaN/Infinity")
            except (ValueError, TypeError):
                pass
    std_ind = next((
        ind for ind in indicators
        if ind.get("indicator_name") == "short_term_interest_bearing_debt" and ind.get("status") == "available"
    ), None)
    if std_ind and frontend.get("short_term_interest_bearing_debt") is None:
        errors.append("[R11] frontend_financial_summary.short_term_interest_bearing_debt 必须来自计算指标，不得长期为 null")

    if data_status == "insufficient":
        non_lim = [f for f in findings if f.get("finding_type") != "data_limitation"]
        if non_lim:
            errors.append(f"[R9] data_status=insufficient 但存在 {len(non_lim)} 条非 data_limitation 的 finding")
    if data_status in ("success", "sufficient"):
        aux_limits = [
            f for f in findings
            if f.get("finding_type") == "data_limitation" and main_period and f.get("period") != main_period
        ]
        if aux_limits:
            errors.append("[R22] data_status=sufficient 时不得因辅助期间缺失生成 data_limitation")

    if not indicators and analysis_status == "success":
        errors.append("[R10] 无任何 financial_indicators 但 analysis_status=success")
    if analysis_status == "failed" and data_status == "insufficient":
        expected_note = "公开财务字段不足，仅能完成有限分析，无法形成完整财务判断。"
        if summary.get("data_limitation_note") != expected_note:
            errors.append("[R23] failed/insufficient 时 data_limitation_note 必须提供前端友好说明")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "rules_checked": 23,
    }


def main():
    parser = argparse.ArgumentParser(description="验证分析输出JSON")
    parser.add_argument("--input", required=True, help="分析输出JSON文件路径")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = validate(data)

    print(f"校验结果: {'通过' if result['passed'] else '未通过'}")
    print(f"校验规则: {result['rules_checked']} 项")
    print(f"错误: {len(result['errors'])} 项")
    for e in result['errors']:
        print(f"  {e}")
    print(f"警告: {len(result['warnings'])} 项")
    for w in result['warnings']:
        print(f"  {w}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
