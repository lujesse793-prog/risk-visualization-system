#!/usr/bin/env python
"""Extract standardized financial fields from Skill2 parsed_documents JSON."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


BALANCE_MAPPING = {
    "资产总计": "total_assets",
    "流动资产合计": "total_current_assets",
    "非流动资产合计": "total_non_current_assets",
    "货币资金": "cash_and_cash_equivalents",
    "交易性金融资产": "trading_financial_assets",
    "应收账款": "accounts_receivable",
    "应收款项融资": "receivables_financing",
    "预付款项": "prepayments",
    "其他应收款": "other_receivables",
    "存货": "inventories",
    "合同资产": "contract_assets",
    "其他流动资产": "other_current_assets",
    "长期股权投资": "long_term_equity_investments",
    "投资性房地产": "investment_properties",
    "固定资产": "fixed_assets",
    "在建工程": "construction_in_progress",
    "无形资产": "intangible_assets",
    "其他非流动资产": "other_non_current_assets",
    "负债合计": "total_liabilities",
    "流动负债合计": "total_current_liabilities",
    "非流动负债合计": "total_non_current_liabilities",
    "短期借款": "short_term_borrowings",
    "交易性金融负债": "trading_financial_liabilities",
    "应付票据": "notes_payable",
    "应付账款": "accounts_payable",
    "预收款项": "advances_from_customers",
    "合同负债": "contract_liabilities",
    "其他应付款": "other_payables",
    "一年内到期的非流动负债": "non_current_liabilities_due_within_one_year",
    "其他流动负债": "other_current_liabilities",
    "长期借款": "long_term_borrowings",
    "应付债券": "bonds_payable",
    "长期应付款": "long_term_payables",
    "预计负债": "estimated_liabilities",
    "递延收益": "deferred_income",
    "递延所得税负债": "deferred_tax_liabilities",
    "所有者权益合计": "total_owner_equity",
    "归属于母公司所有者权益合计": "equity_attributable_to_parent",
    "实收资本": "paid_in_capital",
    "股本": "share_capital",
    "资本公积": "capital_reserve",
    "其他权益工具": "other_equity_instruments",
    "永续债": "perpetual_bonds",
    "其他综合收益": "other_comprehensive_income",
    "盈余公积": "surplus_reserve",
    "未分配利润": "undistributed_profit",
    "少数股东权益": "minority_interests",
}

INCOME_MAPPING = {
    "营业收入": "operating_revenue",
    "营业成本": "operating_cost",
    "营业总成本": "operating_total_cost",
    "税金及附加": "taxes_and_surcharges",
    "销售费用": "selling_expenses",
    "管理费用": "administrative_expenses",
    "研发费用": "research_and_development_expenses",
    "财务费用": "financial_expenses",
    "其中：利息费用": "interest_expenses",
    "其中:利息费用": "interest_expenses",
    "利息费用": "interest_expenses",
    "其中：利息收入": "interest_income",
    "其中:利息收入": "interest_income",
    "利息收入": "interest_income",
    "其他收益": "other_income",
    "投资收益": "investment_income",
    "公允价值变动收益": "gains_from_changes_in_fair_value",
    "信用减值损失": "credit_impairment_losses",
    "资产减值损失": "asset_impairment_losses",
    "资产处置收益": "gains_from_asset_disposal",
    "营业利润": "operating_profit",
    "营业外收入": "non_operating_income",
    "营业外支出": "non_operating_expenses",
    "利润总额": "total_profit",
    "所得税费用": "income_tax_expense",
    "净利润": "net_profit",
    "归属于母公司所有者的净利润": "net_profit_attributable_to_parent",
    "少数股东损益": "minority_interest_income",
}

CASH_FLOW_MAPPING = {
    "销售商品、提供劳务收到的现金": "cash_received_from_sales",
    "收到其他与经营活动有关的现金": "other_cash_received_related_to_operating_activities",
    "经营活动现金流入小计": "subtotal_cash_inflows_from_operating_activities",
    "购买商品、接受劳务支付的现金": "cash_paid_for_goods_and_services",
    "支付给职工以及为职工支付的现金": "cash_paid_to_and_for_employees",
    "支付的各项税费": "taxes_and_fees_paid",
    "支付其他与经营活动有关的现金": "other_cash_paid_related_to_operating_activities",
    "经营活动现金流出小计": "subtotal_cash_outflows_from_operating_activities",
    "经营活动产生的现金流量净额": "net_cash_flow_from_operating_activities",
    "收回投资收到的现金": "cash_received_from_recovery_of_investments",
    "取得投资收益收到的现金": "cash_received_from_investment_income",
    "处置固定资产、无形资产和其他长期资产收回的现金净额": "net_cash_received_from_disposal_of_fixed_assets",
    "收到其他与投资活动有关的现金": "other_cash_received_related_to_investing_activities",
    "投资活动现金流入小计": "subtotal_cash_inflows_from_investing_activities",
    "购建固定资产、无形资产和其他长期资产支付的现金": "cash_paid_for_fixed_assets",
    "投资支付的现金": "cash_paid_for_investments",
    "支付其他与投资活动有关的现金": "other_cash_paid_related_to_investing_activities",
    "投资活动现金流出小计": "subtotal_cash_outflows_from_investing_activities",
    "投资活动产生的现金流量净额": "net_cash_flow_from_investing_activities",
    "吸收投资收到的现金": "cash_received_from_capital_contributions",
    "取得借款收到的现金": "cash_received_from_borrowings",
    "发行债券收到的现金": "cash_received_from_bond_issuance",
    "收到其他与筹资活动有关的现金": "other_cash_received_related_to_financing_activities",
    "筹资活动现金流入小计": "subtotal_cash_inflows_from_financing_activities",
    "偿还债务支付的现金": "cash_paid_for_debt_repayment",
    "分配股利、利润或偿付利息支付的现金": "cash_paid_for_dividends_profits_or_interest",
    "支付其他与筹资活动有关的现金": "other_cash_paid_related_to_financing_activities",
    "筹资活动现金流出小计": "subtotal_cash_outflows_from_financing_activities",
    "筹资活动产生的现金流量净额": "net_cash_flow_from_financing_activities",
    "现金及现金等价物净增加额": "net_increase_in_cash_and_cash_equivalents",
    "期初现金及现金等价物余额": "cash_and_cash_equivalents_at_beginning",
    "期末现金及现金等价物余额": "cash_and_cash_equivalents_at_end",
}

FIELD_ALIASES = {
    "货币资金及现金等价物": "cash_and_cash_equivalents",
    "货币资金余额": "cash_and_cash_equivalents",
    "应收票据及应收账款": "accounts_receivable",
    "应收账款及应收票据": "accounts_receivable",
    "其他应收款合计": "other_receivables",
    "存货合计": "inventories",
    "合同资产合计": "contract_assets",
    "固定资产合计": "fixed_assets",
    "在建工程合计": "construction_in_progress",
    "所有者权益或股东权益合计": "total_owner_equity",
    "所有者权益合计（或股东权益合计）": "total_owner_equity",
    "股东权益合计": "total_owner_equity",
    "归属于母公司股东权益合计": "equity_attributable_to_parent",
    "归属于母公司股东权益": "equity_attributable_to_parent",
    "归属于母公司所有者权益": "equity_attributable_to_parent",
    "归属于母公司所有者的权益": "equity_attributable_to_parent",
    "少数股东权益合计": "minority_interests",
    "一年内到期的非流动负债合计": "non_current_liabilities_due_within_one_year",
    "一年内到期的长期借款": "non_current_liabilities_due_within_one_year",
    "一年内到期的应付债券": "non_current_liabilities_due_within_one_year",
    "短期债务": "short_term_borrowings",
    "长期债务": "long_term_borrowings",
    "应付债券合计": "bonds_payable",
    "长期借款合计": "long_term_borrowings",
    "长期应付款合计": "long_term_payables",
    "营业总收入": "operating_revenue",
    "营业总成本": "operating_total_cost",
    "归属于母公司股东的净利润": "net_profit_attributable_to_parent",
    "归属于母公司所有者的净利润": "net_profit_attributable_to_parent",
    "现金及现金等价物余额": "cash_and_cash_equivalents_at_end",
    "期末现金及现金等价物余额": "cash_and_cash_equivalents_at_end",
    "现金及现金等价物期末余额": "cash_and_cash_equivalents_at_end",
    "经营活动现金流量净额": "net_cash_flow_from_operating_activities",
    "经营性现金流量净额": "net_cash_flow_from_operating_activities",
    "经营活动现金净流量": "net_cash_flow_from_operating_activities",
    "投资活动现金流量净额": "net_cash_flow_from_investing_activities",
    "投资活动现金净流量": "net_cash_flow_from_investing_activities",
    "筹资活动现金流量净额": "net_cash_flow_from_financing_activities",
    "筹资活动现金净流量": "net_cash_flow_from_financing_activities",
    "现金及现金等价物净增加额": "net_increase_in_cash_and_cash_equivalents",
}

STATEMENT_MAPPINGS = {
    "balance_sheet": BALANCE_MAPPING,
    "income_statement": INCOME_MAPPING,
    "cash_flow_statement": CASH_FLOW_MAPPING,
}
STANDARD_TO_FIELD = {
    standard: raw
    for mapping in STATEMENT_MAPPINGS.values()
    for raw, standard in mapping.items()
}
STANDARD_TO_FIELD.update({standard: alias for alias, standard in FIELD_ALIASES.items() if standard not in STANDARD_TO_FIELD})
STANDARD_TO_STATEMENT = {
    standard: statement
    for statement, mapping in STATEMENT_MAPPINGS.items()
    for standard in mapping.values()
}
for alias, standard in FIELD_ALIASES.items():
    if standard in STANDARD_TO_STATEMENT:
        STATEMENT_MAPPINGS[STANDARD_TO_STATEMENT[standard]][alias] = standard

KEY_FIELDS = {
    "total_assets",
    "total_liabilities",
    "total_owner_equity",
    "cash_and_cash_equivalents",
    "short_term_borrowings",
    "non_current_liabilities_due_within_one_year",
    "long_term_borrowings",
    "bonds_payable",
    "operating_revenue",
    "net_profit",
    "net_cash_flow_from_operating_activities",
}
DOC_PRIORITY = {
    "annual_report": 1,
    "semi_annual_report": 2,
    "quarterly_report": 3,
    "prospectus": 4,
    "rating_report": 5,
}
NOTE_TITLE_WORDS = ("附注", "明细", "构成", "账龄", "分类", "补充资料")
MISSING_MARKERS = {"", "-", "—", "--", "不适用", "无", "空白", "nan", "None", "null"}
VALID_UNITS = ("亿元", "万元", "千元", "元")
WARNING_DEFAULTS = {
    "source_document_id": "",
    "page": None,
    "statement_type": "",
    "message": "",
}
WARNING_SEVERITY = {
    "stale_financial_data": "fatal",
    "financial_statement_not_found": "important",
    "balance_sheet_not_found": "important",
    "income_statement_not_found": "important",
    "cash_flow_statement_not_found": "important",
    "unit_uncertain": "important",
    "period_uncertain": "important",
    "source_conflict": "important",
    "parent_company_only": "important",
    "no_tables_raw": "debug",
    "text_fallback_used": "debug",
}
STATEMENT_NOT_FOUND_WARNINGS = {
    "balance_sheet": "balance_sheet_not_found",
    "income_statement": "income_statement_not_found",
    "cash_flow_statement": "cash_flow_statement_not_found",
}
CLASSIFICATION_ROWS = {
    "流动资产",
    "非流动资产",
    "流动负债",
    "非流动负债",
    "所有者权益",
    "股东权益",
    "资产",
    "负债",
}


def add_warning(warnings: list[dict[str, Any]], warning_type: str, **kwargs: Any) -> None:
    warning = dict(WARNING_DEFAULTS)
    warning.update(kwargs)
    warning["warning_type"] = warning_type
    warning["severity"] = warning.get("severity") or WARNING_SEVERITY.get(warning_type, "debug")
    if not warning.get("message"):
        warning["message"] = warning_type
    warnings.append(warning)


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\u3000", "").replace(" ", "").strip()
    text = re.sub(r"^[一二三四五六七八九十\d]+[、.．)]", "", text)
    text = re.sub(r"^(加|减)[:：]", "", text)
    text = text.replace("（", "(").replace("）", ")").replace("：", ":")
    return text.strip()


def canonical_row_name(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"\([^)]*\)$", "", text).strip()
    text = text.replace("其中:", "其中：")
    text = text.rstrip(":：")
    return text


def statement_type_from_title(title: str) -> str | None:
    title = title or ""
    if any(word in title for word in NOTE_TITLE_WORDS):
        return None
    if "现金流量表" in title:
        return "cash_flow_statement"
    if "利润表" in title:
        return "income_statement"
    if "资产负债表" in title:
        return "balance_sheet"
    return None


def statement_title(statement_type: str) -> str:
    return {
        "balance_sheet": "资产负债表",
        "income_statement": "利润表",
        "cash_flow_statement": "现金流量表",
    }.get(statement_type, "财务报表")


def is_consolidated(title: str) -> bool:
    return "合并" in (title or "")


def is_parent_company(title: str) -> bool:
    title = title or ""
    return "母公司" in title or ("公司" in title and "合并" not in title)


def parse_number(value: Any) -> float | None:
    text = "" if value is None else str(value).strip()
    text = text.replace(",", "").replace("，", "").replace(" ", "")
    if text in MISSING_MARKERS:
        return None
    text = text.replace("（", "(").replace("）", ")")
    negative = bool(re.fullmatch(r"\([^()]+\)", text))
    if negative:
        text = text[1:-1]
    text = re.sub(r"(万元|亿元|千元|元)$", "", text)
    text = text.strip()
    if text in MISSING_MARKERS:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def detect_unit(title: str, page_text: str, row_text: str = "") -> tuple[str, bool]:
    row_match = re.search(r"(亿元|万元|千元|元)$", normalize_text(row_text))
    if row_match:
        return row_match.group(1), False
    combined = f"{title}\n{page_text}"
    for unit in VALID_UNITS:
        if f"单位：{unit}" in combined or f"单位:{unit}" in combined:
            return unit, False
        if unit == "元" and ("单位：人民币元" in combined or "单位:人民币元" in combined):
            return "元", False
    return "unknown", True


def normalize_to_yi_yuan(value: float, unit: str) -> tuple[float, str]:
    if unit == "亿元":
        return value, unit
    if unit == "万元":
        return value / 10000, "亿元"
    if unit == "千元":
        return value / 100000, "亿元"
    if unit == "元":
        return value / 100000000, "亿元"
    return value, unit


def normalize_report_period(report_period: str, document_type: str) -> str:
    text = str(report_period or "")
    year_match = re.search(r"(20\d{2}|19\d{2})", text)
    year = year_match.group(1) if year_match else ""
    if re.search(r"H1|半年|半年度|中期", text, re.I):
        return f"{year}H1" if year else text
    q_match = re.search(r"Q([1234])|([一二三四])季|第([一二三四])季度", text, re.I)
    if q_match and year:
        q = q_match.group(1)
        if not q:
            cn = q_match.group(2) or q_match.group(3)
            q = {"一": "1", "二": "2", "三": "3", "四": "4"}.get(cn, "")
        return f"{year}Q{q}"
    if document_type == "semi_annual_report" and year:
        return f"{year}H1"
    return year or text


def period_sort_key(period: str) -> tuple[int, int]:
    match = re.match(r"(20\d{2}|19\d{2})(?:H1|Q([1-4]))?", str(period or ""))
    if not match:
        return (0, 0)
    year = int(match.group(1))
    suffix_score = 4
    if "H1" in period:
        suffix_score = 2
    q_match = re.search(r"Q([1-4])", period)
    if q_match:
        suffix_score = int(q_match.group(1))
    return (year, suffix_score)


def comparable_previous_period(period: str) -> str:
    year_match = re.match(r"(20\d{2}|19\d{2})(.*)", period)
    if not year_match:
        return period
    return f"{int(year_match.group(1)) - 1}{year_match.group(2)}"


def previous_year_end(period: str) -> str:
    year_match = re.match(r"(20\d{2}|19\d{2})", period)
    if not year_match:
        return period
    return str(int(year_match.group(1)) - 1)


def infer_period(raw_column: str, statement: str, document_type: str, report_period: str) -> tuple[str | None, str]:
    column = normalize_text(raw_column)
    current = normalize_report_period(report_period, document_type)
    explicit_year = re.search(r"(20\d{2}|19\d{2})", column)
    if explicit_year:
        year = explicit_year.group(1)
        if "H1" in current and statement != "balance_sheet":
            period = f"{year}H1"
        elif "Q" in current and statement != "balance_sheet":
            q = re.search(r"Q([1234])", current)
            period = f"{year}Q{q.group(1)}" if q else year
        else:
            period = year
    elif "期初" in column and statement == "balance_sheet":
        period = previous_year_end(current)
    elif "上期" in column or "同期" in column:
        period = comparable_previous_period(current)
    elif any(word in column for word in ("期末", "本期", "本年", "金额", "发生额")):
        period = current
    else:
        period = current if column else None

    if statement == "balance_sheet":
        if period and "H1" in period:
            period_type = "half_year_end"
        elif period and "Q" in period:
            period_type = "quarter_end"
        else:
            period_type = "year_end"
    else:
        if period and ("H1" in period or "Q" in period):
            period_type = "ytd"
        elif period:
            period_type = "full_year"
        else:
            period_type = "single_period"
    return period, period_type


def doc_meta(input_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    docs = {doc.get("document_id"): dict(doc) for doc in input_data.get("source_documents", [])}
    for meta in docs.values():
        if not meta.get("document_type") and meta.get("file_type"):
            meta["document_type"] = meta.get("file_type")
    for parsed in input_data.get("parsed_documents", []):
        did = parsed.get("document_id")
        existing = docs.setdefault(did, {})
        for key in ("document_id", "document_type", "report_period"):
            if parsed.get(key) and not existing.get(key):
                existing[key] = parsed.get(key)
    return docs


def doc_sort_key(doc: dict[str, Any]) -> tuple[int, tuple[int, int], str]:
    document_type = doc.get("document_type", "")
    report_period = normalize_report_period(str(doc.get("report_period", "")), document_type)
    return (
        -DOC_PRIORITY.get(document_type, 99),
        period_sort_key(report_period),
        str(doc.get("publication_date", "")),
    )


def selected_main_document_id(input_data: dict[str, Any]) -> str | None:
    docs = [doc for doc in input_data.get("source_documents", []) if doc.get("document_id")]
    for doc in docs:
        if doc.get("is_selected_main"):
            return doc.get("document_id")
    if not docs:
        parsed = [doc for doc in input_data.get("parsed_documents", []) if doc.get("document_id")]
        if not parsed:
            return None
        return sorted(parsed, key=doc_sort_key, reverse=True)[0].get("document_id")
    return sorted(docs, key=doc_sort_key, reverse=True)[0].get("document_id")


def table_priority(candidate: dict[str, Any]) -> tuple[int, int, int, int, tuple[int, int], str]:
    document_type = candidate.get("source_document_type")
    title = candidate.get("table_title", "")
    source_kind = candidate.get("source_kind", "structured_table")
    return (
        DOC_PRIORITY.get(document_type, 99),
        0 if is_consolidated(title) else 1,
        0 if source_kind == "structured_table" else 1,
        0 if not is_parent_company(title) else 1,
        tuple(-v for v in period_sort_key(str(candidate.get("period", "")))),
        str(candidate.get("source_document_id", "")),
    )


def is_unit_row(row: list[Any]) -> bool:
    joined = "".join(str(cell) for cell in row)
    return "单位：" in joined or "单位:" in joined


def is_blank_row(row: list[Any]) -> bool:
    return all(normalize_text(cell) == "" for cell in row)


def is_title_row(row: list[Any], table_title: str) -> bool:
    nonblank = [normalize_text(cell) for cell in row if normalize_text(cell)]
    return len(nonblank) == 1 and (nonblank[0] == normalize_text(table_title) or "表" in nonblank[0])


def looks_like_amount_header(value: Any) -> bool:
    text = normalize_text(value)
    return bool(
        re.search(r"(20\d{2}|19\d{2})", text)
        or any(word in text for word in ("期末余额", "期初余额", "本期金额", "上期金额", "本期发生额", "上期发生额", "本年累计"))
    )


def header_score(row: list[Any]) -> int:
    normalized = [normalize_text(cell) for cell in row]
    score = 0
    if any(cell in {"项目", "科目", "财务科目"} or "项目" in cell for cell in normalized):
        score += 3
    score += sum(1 for cell in normalized if looks_like_amount_header(cell))
    if any(cell == "附注" for cell in normalized):
        score += 1
    return score


def find_header_row(rows: list[list[Any]]) -> int | None:
    best_idx: int | None = None
    best_score = 0
    for idx, row in enumerate(rows[:8]):
        score = header_score(row)
        if score > best_score:
            best_idx = idx
            best_score = score
    return best_idx if best_score >= 2 else None


def merge_ocr_split_rows(rows: list[list[Any]]) -> list[list[Any]]:
    merged: list[list[Any]] = []
    idx = 0
    while idx < len(rows):
        row = rows[idx]
        nonblank = [cell for cell in row if normalize_text(cell)]
        if (
            len(nonblank) == 1
            and canonical_row_name(nonblank[0]) in STANDARD_TO_STATEMENT_FROM_NAME
            and idx + 1 < len(rows)
        ):
            next_nonblank = [cell for cell in rows[idx + 1] if normalize_text(cell)]
            if next_nonblank and all(parse_number(cell) is not None for cell in next_nonblank):
                merged.append([nonblank[0], *next_nonblank])
                idx += 2
                continue
        merged.append(row)
        idx += 1
    return merged


def normalize_table_rows(table: dict[str, Any]) -> dict[str, Any] | None:
    raw_rows = [list(row) for row in (table.get("rows") or []) if isinstance(row, list)]
    if not raw_rows:
        return None
    title = str(table.get("table_title", ""))
    filtered = [
        row
        for row in raw_rows
        if not is_blank_row(row) and not is_unit_row(row) and not is_title_row(row, title)
    ]
    filtered = merge_ocr_split_rows(filtered)
    header_idx = find_header_row(filtered)
    if header_idx is None:
        return None
    header = [str(cell) for cell in filtered[header_idx]]
    normalized_header = [normalize_text(cell) for cell in header]
    project_idx = next(
        (
            idx
            for idx, cell in enumerate(normalized_header)
            if cell in {"项目", "科目", "财务科目"} or "项目" in cell
        ),
        0,
    )
    amount_indexes = [
        idx
        for idx, cell in enumerate(normalized_header)
        if idx != project_idx and cell != "附注" and looks_like_amount_header(cell)
    ]
    if not amount_indexes:
        amount_indexes = [
            idx
            for idx, cell in enumerate(normalized_header)
            if idx != project_idx and cell != "附注"
        ]
    rows: list[dict[str, Any]] = []
    for raw_row in filtered[header_idx + 1 :]:
        if len(raw_row) <= project_idx:
            continue
        field_name = canonical_row_name(raw_row[project_idx])
        if not field_name or field_name in CLASSIFICATION_ROWS:
            continue
        values = []
        for idx in amount_indexes:
            raw_value = raw_row[idx] if idx < len(raw_row) else ""
            if parse_number(raw_value) is None:
                continue
            values.append({"raw_column": header[idx] if idx < len(header) else f"column_{idx + 1}", "raw_value": raw_value})
        if values:
            rows.append({"field_name": field_name, "raw_row": str(raw_row[project_idx]), "values": values})
    return {"header": header, "rows": rows}


def table_has_statement(parsed: dict[str, Any], statement: str) -> bool:
    for table in parsed.get("tables_raw", []) or []:
        if statement_type_from_title(str(table.get("table_title", ""))) == statement:
            return True
    return False


def choose_statement_tables(parsed_documents: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    candidates: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any], str]]] = defaultdict(list)
    for parsed in parsed_documents:
        document_id = parsed.get("document_id", "")
        if parsed.get("parse_status") == "failed":
            continue
        if not parsed.get("tables_raw"):
            add_warning(warnings, "no_tables_raw", source_document_id=document_id, message="parsed_document 未包含 tables_raw，后续将尝试 page_texts 兜底")
        for table in parsed.get("tables_raw", []) or []:
            title = str(table.get("table_title", ""))
            statement = statement_type_from_title(title)
            if not statement:
                continue
            key = (document_id, statement)
            candidates[key].append((parsed, table, statement))

    selected: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for (_document_id, statement), items in candidates.items():
        consolidated = [item for item in items if is_consolidated(str(item[1].get("table_title", "")))]
        pool = consolidated or items
        if not consolidated:
            first = items[0]
            add_warning(
                warnings,
                "parent_company_only",
                source_document_id=first[0].get("document_id", ""),
                page=first[1].get("page"),
                statement_type=statement,
                message="未识别到合并报表，已使用非合并/母公司报表作为低优先级来源",
            )
        best = sorted(
            pool,
            key=lambda item: (
                0 if is_consolidated(str(item[1].get("table_title", ""))) else 1,
                0 if not is_parent_company(str(item[1].get("table_title", ""))) else 1,
                int(item[1].get("page") or 0),
            ),
        )[0]
        selected.append(best)
    return selected


def field_from_name(field_name: str, statement: str) -> str | None:
    field_name = canonical_row_name(field_name)
    exact = STATEMENT_MAPPINGS[statement].get(field_name)
    if exact:
        return exact
    matches = [
        (raw_name, standard)
        for raw_name, standard in STATEMENT_MAPPINGS[statement].items()
        if raw_name and raw_name in field_name
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda item: len(item[0]), reverse=True)[0][1]


STANDARD_TO_STATEMENT_FROM_NAME = {
    canonical_row_name(name): statement
    for statement, mapping in STATEMENT_MAPPINGS.items()
    for name in mapping
}


def build_row(
    *,
    field_name: str,
    standard: str,
    statement: str,
    period: str,
    period_type: str,
    value: float,
    unit: str,
    document_id: str,
    document_type: str,
    source_pdf: str,
    page: int | str | None,
    table_id: str,
    table_title: str,
    raw_row: str,
    raw_column: str,
    confidence: str,
    source_kind: str,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if unit == "unknown" and source_kind == "structured_table" and statement_type_from_title(table_title) == statement:
        unit = "元"
    if unit == "unknown":
        confidence = "low"
        add_warning(
            warnings,
            "unit_uncertain",
            source_document_id=document_id,
            page=page,
            statement_type=statement,
            standard_field_name=standard,
            period=period,
            message="未识别到报表单位，unit 标记为 unknown",
        )
    value, unit = normalize_to_yi_yuan(value, unit)
    evidence_text = f"{table_title}第{page}页，{field_name}，{raw_column}金额为{value}{unit}"
    row = {
        "field_name": field_name,
        "standard_field_name": standard,
        "statement_type": statement,
        "period": period,
        "period_type": period_type,
        "value": value,
        "unit": unit,
        "source_document_id": document_id,
        "source_document_type": document_type,
        "source_pdf": source_pdf,
        "page": page,
        "table_id": table_id,
        "table_title": table_title,
        "raw_row": raw_row,
        "raw_column": raw_column,
        "evidence_text": evidence_text,
        "confidence": confidence,
    }
    row["_priority"] = table_priority(
        {
            "source_document_type": document_type,
            "table_title": table_title,
            "source_kind": source_kind,
            "source_document_id": document_id,
            "period": period,
        }
    )
    return row


def extract_from_tables(input_data: dict[str, Any], warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs = doc_meta(input_data)
    page_text_lookup = {
        parsed.get("document_id"): parsed.get("page_texts", {}) or {}
        for parsed in input_data.get("parsed_documents", [])
    }
    rows: list[dict[str, Any]] = []
    for parsed, table, statement in choose_statement_tables(input_data.get("parsed_documents", []), warnings):
        document_id = parsed.get("document_id", "")
        meta = docs.get(document_id, {})
        document_type = parsed.get("document_type") or meta.get("document_type", "")
        source_pdf = meta.get("pdf_url") or meta.get("source_url") or ""
        page = table.get("page")
        table_id = str(table.get("table_id", ""))
        title = str(table.get("table_title", ""))
        page_text = str(page_text_lookup.get(document_id, {}).get(str(page), ""))
        unit, unit_uncertain = detect_unit(title, page_text)
        normalized = normalize_table_rows(table)
        if not normalized:
            add_warning(
                warnings,
                "financial_statement_not_found",
                source_document_id=document_id,
                page=page,
                statement_type=statement,
                message=f"{title} 未识别到有效表头或金额列",
            )
            continue
        for item in normalized["rows"]:
            standard = field_from_name(item["field_name"], statement)
            if not standard:
                continue
            row_unit, row_uncertain = detect_unit("", "", item["raw_row"])
            effective_unit = row_unit if not row_uncertain else unit
            for value_item in item["values"]:
                value = parse_number(value_item["raw_value"])
                if value is None:
                    continue
                raw_column = str(value_item["raw_column"])
                period, period_type = infer_period(raw_column, statement, document_type, parsed.get("report_period", ""))
                if not period:
                    add_warning(
                        warnings,
                        "period_uncertain",
                        source_document_id=document_id,
                        page=page,
                        statement_type=statement,
                        standard_field_name=standard,
                        raw_column=raw_column,
                        message="无法识别字段期间，已跳过该值",
                    )
                    continue
                confidence = "high"
                if parsed.get("ocr_used") or parsed.get("parse_confidence") == "medium":
                    confidence = "medium"
                if document_type in {"prospectus", "rating_report"}:
                    confidence = "medium"
                rows.append(
                    build_row(
                        field_name=item["field_name"],
                        standard=standard,
                        statement=statement,
                        period=period,
                        period_type=period_type,
                        value=value,
                        unit=effective_unit,
                        document_id=document_id,
                        document_type=document_type,
                        source_pdf=source_pdf,
                        page=page,
                        table_id=table_id,
                        table_title=title,
                        raw_row=item["raw_row"],
                        raw_column=raw_column,
                        confidence=confidence,
                        source_kind="structured_table",
                        warnings=warnings,
                    )
                )
    return rows


def infer_statement_from_text(text: str) -> str | None:
    if "现金流量表" in text:
        return "cash_flow_statement"
    if "利润表" in text:
        return "income_statement"
    if "资产负债表" in text:
        return "balance_sheet"
    return None


def parse_text_lines(text: str) -> list[list[str]]:
    lines = [line.strip() for line in re.split(r"[\r\n]+", text or "") if line.strip()]
    parsed: list[list[str]] = []
    for line in lines:
        parts = [p for p in re.split(r"\s{2,}|\t+|[|｜]", line.strip()) if p.strip()]
        if len(parts) <= 1:
            tokens = re.findall(r"\(?-?\d[\d,]*\.?\d*\)?|[（(]-?\d[\d,]*\.?\d*[）)]", line)
            if tokens:
                prefix = line
                for token in tokens:
                    prefix = prefix.replace(token, " ")
                parts = [prefix.strip(), *tokens]
            else:
                parts = [line]
        parsed.append(parts)
    return parsed


def extract_from_page_texts(input_data: dict[str, Any], warnings: list[dict[str, Any]], table_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs = doc_meta(input_data)
    structured_pairs = {(row["source_document_id"], row["statement_type"]) for row in table_rows}
    rows: list[dict[str, Any]] = []
    for parsed in input_data.get("parsed_documents", []):
        document_id = parsed.get("document_id", "")
        if parsed.get("parse_status") == "failed":
            continue
        page_texts = parsed.get("page_texts", {}) or {}
        if not page_texts:
            continue
        missing_statements = {
            statement
            for statement in STATEMENTS
            if (not parsed.get("tables_raw") or not table_has_statement(parsed, statement))
            and (document_id, statement) not in structured_pairs
        }
        if not missing_statements:
            continue
        meta = docs.get(document_id, {})
        document_type = parsed.get("document_type") or meta.get("document_type", "")
        source_pdf = meta.get("pdf_url") or meta.get("source_url") or ""
        extracted_for_doc: set[str] = set()
        for page, text in page_texts.items():
            hinted_statement = infer_statement_from_text(str(text))
            candidate_statements = [hinted_statement] if hinted_statement in missing_statements else list(missing_statements)
            unit, _unit_uncertain = detect_unit("", str(text))
            parsed_lines = parse_text_lines(str(text))
            synthetic_table = {"table_id": f"text_page_{page}", "page": page, "table_title": statement_title(hinted_statement or ""), "rows": parsed_lines}
            normalized = normalize_table_rows(synthetic_table)
            if normalized:
                for statement in candidate_statements:
                    for item in normalized["rows"]:
                        standard = field_from_name(item["field_name"], statement)
                        if not standard:
                            continue
                        for value_item in item["values"]:
                            value = parse_number(value_item["raw_value"])
                            period, period_type = infer_period(str(value_item["raw_column"]), statement, document_type, parsed.get("report_period", ""))
                            if value is None or not period:
                                continue
                            extracted_for_doc.add(statement)
                            rows.append(
                                build_row(
                                    field_name=item["field_name"],
                                    standard=standard,
                                    statement=statement,
                                    period=period,
                                    period_type=period_type,
                                    value=value,
                                    unit=unit,
                                    document_id=document_id,
                                    document_type=document_type,
                                    source_pdf=source_pdf,
                                    page=page,
                                    table_id=f"text_page_{page}",
                                    table_title=statement_title(statement),
                                    raw_row=item["raw_row"],
                                    raw_column=str(value_item["raw_column"]),
                                    confidence="medium" if unit != "unknown" else "low",
                                    source_kind="page_text",
                                    warnings=warnings,
                                )
                            )
                continue

            for line in re.split(r"[\r\n]+", str(text)):
                line = line.strip()
                if not line:
                    continue
                for statement in candidate_statements:
                    for raw_name, standard in STATEMENT_MAPPINGS[statement].items():
                        if raw_name not in line:
                            continue
                        numbers = re.findall(r"[（(]?-?\d[\d,]*\.?\d*[）)]?", line)
                        if not numbers:
                            continue
                        value = parse_number(numbers[-1])
                        if value is None:
                            continue
                        period, period_type = infer_period(line, statement, document_type, parsed.get("report_period", ""))
                        if not period:
                            continue
                        extracted_for_doc.add(statement)
                        rows.append(
                            build_row(
                                field_name=raw_name,
                                standard=standard,
                                statement=statement,
                                period=period,
                                period_type=period_type,
                                value=value,
                                unit=unit,
                                document_id=document_id,
                                document_type=document_type,
                                source_pdf=source_pdf,
                                page=page,
                                table_id=f"text_page_{page}",
                                table_title=statement_title(statement),
                                raw_row=line,
                                raw_column="text_fallback",
                                confidence="medium" if unit != "unknown" else "low",
                                source_kind="page_text",
                                warnings=warnings,
                            )
                        )
        for statement in missing_statements:
            if statement in extracted_for_doc:
                add_warning(
                    warnings,
                    "text_fallback_used",
                    source_document_id=document_id,
                    statement_type=statement,
                    message=f"{statement_title(statement)} 未从 tables_raw 抽取，已使用 page_texts 兜底",
                )
            else:
                add_warning(
                    warnings,
                    STATEMENT_NOT_FOUND_WARNINGS[statement],
                    source_document_id=document_id,
                    statement_type=statement,
                    message=f"未在 tables_raw 或 page_texts 中识别到{statement_title(statement)}主表",
                )
                add_warning(
                    warnings,
                    "financial_statement_not_found",
                    source_document_id=document_id,
                    statement_type=statement,
                    message=f"未能从 page_texts 抽取{statement_title(statement)}字段",
                )
    return rows


STATEMENTS = ("balance_sheet", "income_statement", "cash_flow_statement")


def resolve_conflicts(rows: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["standard_field_name"], row["period"])].append(row)
    selected: list[dict[str, Any]] = []
    for (_standard, _period), items in grouped.items():
        chosen = sorted(items, key=lambda item: item.get("_priority", (99, 99, 99, 99, (0, 0), "")))[0]
        conflicts = []
        for item in items:
            if item is chosen:
                continue
            if item.get("value") != chosen.get("value") or item.get("unit") != chosen.get("unit"):
                conflicts.append(
                    {
                        "value": item.get("value"),
                        "unit": item.get("unit"),
                        "source_document_id": item.get("source_document_id"),
                        "page": item.get("page"),
                        "table_title": item.get("table_title"),
                    }
                )
        if conflicts:
            add_warning(
                warnings,
                "source_conflict",
                source_document_id=chosen.get("source_document_id", ""),
                page=chosen.get("page"),
                statement_type=chosen.get("statement_type", ""),
                standard_field_name=chosen.get("standard_field_name"),
                period=chosen.get("period"),
                selected_value=chosen.get("value"),
                selected_unit=chosen.get("unit"),
                conflicting_values=conflicts,
                resolution=f"selected_{'consolidated_' if is_consolidated(chosen.get('table_title', '')) else ''}{chosen.get('statement_type')}_value",
                message="同一字段期间存在多个来源数值，已按正式主表/合并报表/结构化表格优先级选择",
            )
        chosen.pop("_priority", None)
        selected.append(chosen)
    return sorted(selected, key=lambda r: (r["statement_type"], period_sort_key(r["period"]), r["standard_field_name"]))


def build_missing_fields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    latest_period = sorted({row["period"] for row in rows}, key=period_sort_key, reverse=True)[0]
    present = {(row["standard_field_name"], row["period"]) for row in rows}
    searched_docs = sorted({row["source_document_id"] for row in rows if row.get("source_document_id")})
    searched_pages = sorted({row["page"] for row in rows if row.get("page") is not None}, key=lambda value: str(value))
    missing = []
    for standard, field_name in sorted(STANDARD_TO_FIELD.items()):
        statement = STANDARD_TO_STATEMENT[standard]
        if (standard, latest_period) not in present:
            missing.append(
                {
                    "standard_field_name": standard,
                    "field_name": field_name,
                    "statement_type": statement,
                    "period": latest_period,
                    "reason": "not_found_in_selected_documents",
                    "searched_documents": searched_docs,
                    "searched_pages": searched_pages,
                    "impact_on_analysis": impact_for_field(standard),
                }
            )
    return missing


def impact_for_field(standard: str) -> str:
    impacts = {
        "cash_and_cash_equivalents": "may_affect_cash_short_debt_ratio",
        "short_term_borrowings": "may_affect_short_term_debt_pressure_analysis",
        "non_current_liabilities_due_within_one_year": "may_affect_short_term_debt_pressure_analysis",
        "long_term_borrowings": "may_affect_debt_structure_analysis",
        "bonds_payable": "may_affect_debt_structure_analysis",
        "operating_revenue": "may_affect_profitability_analysis",
        "net_profit": "may_affect_profitability_analysis",
        "net_cash_flow_from_operating_activities": "may_affect_operating_cash_flow_analysis",
    }
    return impacts.get(standard, "may_affect_financial_analysis_completeness")


def build_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": f"ev_{idx:03d}",
            "standard_field_name": row["standard_field_name"],
            "field_name": row["field_name"],
            "period": row["period"],
            "value": row["value"],
            "unit": row["unit"],
            "source_document_id": row["source_document_id"],
            "source_document_type": row["source_document_type"],
            "page": row["page"],
            "table_id": row["table_id"],
            "table_title": row["table_title"],
            "raw_row": row["raw_row"],
            "raw_column": row["raw_column"],
            "evidence_text": row["evidence_text"],
            "confidence": row["confidence"],
        }
        for idx, row in enumerate(rows, start=1)
    ]


def build_document_usage(input_data: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used_by_doc: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        used_by_doc[row["source_document_id"]].append(row["standard_field_name"])
    usage = []
    for doc_id, meta in doc_meta(input_data).items():
        if not doc_id:
            continue
        usage.append(
            {
                "document_id": doc_id,
                "document_type": meta.get("document_type", ""),
                "report_period": meta.get("report_period", ""),
                "usage": "extracted" if doc_id in used_by_doc else "not_used",
                "extracted_field_count": len(used_by_doc.get(doc_id, [])),
            }
        )
    return usage


def document_periods(input_data: dict[str, Any]) -> list[str]:
    periods: list[str] = []
    for doc in input_data.get("source_documents", []) + input_data.get("parsed_documents", []):
        period = normalize_report_period(str(doc.get("report_period", "")), str(doc.get("document_type", "")))
        if period:
            periods.append(period)
    return periods


def mark_stale_data(input_data: dict[str, Any], rows: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> bool:
    latest_acceptable = input_data.get("latest_acceptable_period")
    no_latest = bool(input_data.get("no_latest_public_data"))
    stale = False
    if latest_acceptable:
        threshold = period_sort_key(str(latest_acceptable))
        periods = document_periods(input_data) or [row["period"] for row in rows]
        stale = bool(periods) and all(period_sort_key(period) < threshold for period in periods)
    elif no_latest:
        stale = True
    if stale:
        add_warning(
            warnings,
            "stale_financial_data",
            message="未找到最新公开财务数据，现有数据不足以支持最新贷后分析。",
        )
    return stale


def decide_status(rows: list[dict[str, Any]], input_data: dict[str, Any], stale: bool) -> str:
    parsed = input_data.get("parsed_documents", [])
    if parsed and all(doc.get("parse_status") == "failed" for doc in parsed):
        return "failed"
    if not rows:
        return "failed"
    latest_period = sorted({row["period"] for row in rows}, key=period_sort_key, reverse=True)[0]
    latest_rows = [row for row in rows if row["period"] == latest_period]
    standards = {row["standard_field_name"] for row in latest_rows}
    statements = {row["statement_type"] for row in latest_rows}
    has_unknown_key_unit = any(row["standard_field_name"] in KEY_FIELDS and row["unit"] == "unknown" for row in latest_rows)
    if stale:
        return "partial"
    if (
        KEY_FIELDS.issubset(standards)
        and set(STATEMENTS).issubset(statements)
        and not has_unknown_key_unit
        and not any(row["source_document_type"] in {"prospectus", "rating_report"} for row in latest_rows)
    ):
        return "success"
    return "partial"


def validate_with_local_script(output: dict[str, Any]) -> dict[str, Any]:
    validator_path = Path(__file__).with_name("validate_output.py")
    spec = importlib.util.spec_from_file_location("financial_validate_output", validator_path)
    if spec is None or spec.loader is None:
        return {"passed": False, "errors": ["could not load validate_output.py"], "warnings": []}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_output(output)


def extract(input_data: dict[str, Any]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    if not input_data.get("parsed_documents"):
        add_warning(warnings, "financial_statement_not_found", message="未收到 parsed_documents")

    table_rows = extract_from_tables(input_data, warnings)
    text_rows = extract_from_page_texts(input_data, warnings, table_rows)
    rows = resolve_conflicts(table_rows + text_rows, warnings)
    stale = mark_stale_data(input_data, rows, warnings)
    missing = build_missing_fields(rows)
    evidence = build_evidence(rows)
    tables = {"balance_sheet": [], "income_statement": [], "cash_flow_statement": []}
    for row in rows:
        tables[row["statement_type"]].append(row)
    status = decide_status(rows, input_data, stale)
    selected_supplements = [
        doc.get("document_id")
        for doc in input_data.get("source_documents", [])
        if doc.get("is_selected_supplement") and doc.get("document_id")
    ]
    output = {
        "enterprise_name": input_data.get("enterprise_name", ""),
        "extraction_status": status,
        "data_periods": sorted({row["period"] for row in rows}, key=period_sort_key, reverse=True),
        "selected_main_document_id": selected_main_document_id(input_data),
        "selected_supplement_document_ids": selected_supplements,
        "structured_financial_data": {"financial_tables": tables},
        "field_evidence": evidence,
        "missing_fields": missing,
        "extraction_warnings": warnings,
        "document_usage": build_document_usage(input_data, rows),
        "validation_result": {"passed": True, "errors": [], "warnings": []},
    }
    output["validation_result"] = validate_with_local_script(output)
    if not output["validation_result"]["passed"] and output["extraction_status"] == "success":
        output["extraction_status"] = "partial"
        output["validation_result"] = validate_with_local_script(output)
    return output


def failed_output(input_data: dict[str, Any], error: str) -> dict[str, Any]:
    output = {
        "enterprise_name": input_data.get("enterprise_name", "") if isinstance(input_data, dict) else "",
        "extraction_status": "failed",
        "data_periods": [],
        "selected_main_document_id": None,
        "selected_supplement_document_ids": [],
        "structured_financial_data": {"financial_tables": {"balance_sheet": [], "income_statement": [], "cash_flow_statement": []}},
        "field_evidence": [],
        "missing_fields": [],
        "extraction_warnings": [{"warning_type": "extraction_failed", "severity": "fatal", "source_document_id": "", "page": None, "statement_type": "", "message": error}],
        "document_usage": [],
        "validation_result": {"passed": False, "errors": [error], "warnings": []},
    }
    output["validation_result"] = validate_with_local_script(output)
    if error not in output["validation_result"]["errors"]:
        output["validation_result"]["errors"].append(error)
        output["validation_result"]["passed"] = False
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    input_data: dict[str, Any] = {}
    try:
        input_data = json.loads(input_path.read_text(encoding="utf-8"))
        output = extract(input_data)
    except Exception as exc:
        output = failed_output(input_data, f"{type(exc).__name__}: {exc}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output["generated_at"] = datetime.now().isoformat(timespec="seconds")
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
