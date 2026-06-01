#!/usr/bin/env python3
"""run_analysis.py - 城投/发债企业贷后财务数据分析主脚本

用法:
    python scripts/run_analysis.py --input sample_input.json --output analysis_output.json
"""

import argparse, json, math, sys, os
from copy import deepcopy
from typing import Any


# ============================================================
# 阈值配置
# ============================================================

DEFAULT_THRESHOLDS = {
    "城投": {
        "asset_liability_ratio": {"watch": 70, "warning": 75, "serious": 85, "direction": "high"},
        "cash_short_debt_ratio": {"watch": 1.0, "warning": 0.5, "serious": 0.3, "direction": "low"},
        "current_ratio": {"watch": 1.2, "warning": 1.0, "serious": 0.7, "direction": "low"},
        "quick_ratio": {"watch": 1.0, "warning": 0.8, "serious": 0.5, "direction": "low"},
        "net_cash_flow_from_operating_activities": {"kind": "negative_streak"},
        "net_profit": {"kind": "negative_streak"},
        "revenue_yoy": {"watch": -10, "warning": -20, "serious": -40, "direction": "low"},
        "net_profit_yoy": {"watch": -20, "warning": -40, "serious": -60, "direction": "low"},
        "net_cash_flow_from_operating_activities_yoy": {"watch": -20, "warning": -40, "serious": -60, "direction": "low"},
        "short_term_debt_ratio": {"watch": 40, "warning": 60, "serious": 75, "direction": "high"},
        "operating_cash_flow_to_short_debt": {"watch": 0.5, "warning": 0.3, "serious": 0, "direction": "low"},
        "other_receivables_to_total_assets": {"watch": 15, "warning": 25, "serious": 35, "direction": "high"},
        "inventory_to_total_assets": {"watch": 25, "warning": 40, "serious": 50, "direction": "high"},
    },
    "产业": {
        "asset_liability_ratio": {"watch": 70, "warning": 75, "serious": 85, "direction": "high"},
        "cash_short_debt_ratio": {"watch": 1.0, "warning": 0.5, "serious": 0.3, "direction": "low"},
        "current_ratio": {"watch": 1.2, "warning": 1.0, "serious": 0.7, "direction": "low"},
        "quick_ratio": {"watch": 1.0, "warning": 0.8, "serious": 0.5, "direction": "low"},
        "net_cash_flow_from_operating_activities": {"kind": "negative_streak"},
        "net_profit": {"kind": "negative_streak"},
        "revenue_yoy": {"watch": -10, "warning": -20, "serious": -40, "direction": "low"},
        "net_profit_yoy": {"watch": -20, "warning": -40, "serious": -60, "direction": "low"},
        "net_cash_flow_from_operating_activities_yoy": {"watch": -20, "warning": -40, "serious": -60, "direction": "low"},
        "short_term_debt_ratio": {"watch": 40, "warning": 60, "serious": 75, "direction": "high"},
        "operating_cash_flow_to_short_debt": {"watch": 0.5, "warning": 0.3, "serious": 0, "direction": "low"},
        "other_receivables_to_total_assets": {"watch": 15, "warning": 25, "serious": 35, "direction": "high"},
        "inventory_to_total_assets": {"watch": 25, "warning": 40, "serious": 50, "direction": "high"},
    },
}

DEBT_COMPONENTS = [
    "short_term_borrowings",
    "non_current_liabilities_due_within_one_year",
    "long_term_borrowings",
    "bonds_payable",
    "long_term_payables",
]

CORE_INDICATORS = {
    "asset_liability_ratio",
    "cash_short_debt_ratio",
    "current_ratio",
    "quick_ratio",
    "operating_revenue",
    "net_profit",
    "net_cash_flow_from_operating_activities",
    "interest_bearing_debt",
    "short_term_debt_ratio",
    "operating_cash_flow_to_short_debt",
}

# ============================================================
# 字段映射
# ============================================================

FIELD_ALIASES = {
    "total_assets": ["总资产", "资产总计", "资产总额"],
    "total_current_assets": ["current_assets", "流动资产", "流动资产合计"],
    "total_non_current_assets": ["非流动资产", "非流动资产合计"],
    "cash_and_cash_equivalents": ["货币资金", "现金及现金等价物"],
    "inventory": ["存货", "存货净额"],
    "accounts_receivable": ["应收账款"],
    "notes_receivable": ["应收票据", "应收票据及应收账款"],
    "other_receivables": ["其他应收款"],
    "total_liabilities": ["总负债", "负债合计", "负债总额"],
    "total_current_liabilities": ["current_liabilities", "流动负债", "流动负债合计"],
    "total_non_current_liabilities": ["非流动负债", "非流动负债合计"],
    "short_term_borrowings": ["短期借款"],
    "non_current_liabilities_due_within_one_year": ["一年内到期的非流动负债"],
    "long_term_borrowings": ["长期借款"],
    "bonds_payable": ["应付债券"],
    "long_term_payables": ["长期应付款"],
    "total_owner_equity": ["owner_equity", "所有者权益", "归属于母公司所有者权益", "股东权益", "所有者权益合计"],
    "paid_in_capital": ["实收资本", "股本"],
    "capital_reserve": ["资本公积"],
    "other_equity_instruments": ["其他权益工具"],
    "undistributed_profit": ["未分配利润"],
    "operating_revenue": ["营业总收入", "营业收入"],
    "operating_cost": ["营业成本"],
    "operating_total_cost": ["营业总成本"],
    "operating_profit": ["营业利润"],
    "total_profit": ["利润总额"],
    "net_profit": ["净利润"],
    "net_profit_attributable_to_parent": ["归属于母公司股东的净利润", "归属于母公司所有者的净利润"],
    "financial_expenses": ["财务费用"],
    "interest_expense": ["利息费用"],
    "cash_inflow_from_operating_activities": ["经营活动现金流入小计"],
    "cash_outflow_from_operating_activities": ["经营活动现金流出小计"],
    "net_cash_flow_from_operating_activities": ["net_operating_cash_flow", "经营活动现金流量净额", "经营活动产生的现金流量净额"],
    "cash_inflow_from_investing_activities": ["投资活动现金流入小计"],
    "cash_outflow_from_investing_activities": ["投资活动现金流出小计"],
    "net_cash_flow_from_investing_activities": ["net_investing_cash_flow", "投资活动现金流量净额"],
    "cash_inflow_from_financing_activities": ["筹资活动现金流入小计"],
    "cash_outflow_from_financing_activities": ["筹资活动现金流出小计"],
    "net_cash_flow_from_financing_activities": ["net_financing_cash_flow", "筹资活动现金流量净额"],
    "net_increase_in_cash_and_cash_equivalents": ["现金及现金等价物净增加额"],
}

FIELD_CANONICAL = {}
for _std, _aliases in FIELD_ALIASES.items():
    FIELD_CANONICAL[_std] = _std
    for _alias in _aliases:
        FIELD_CANONICAL[_alias] = _std

STANDARD_FIELD_NAMES = set(FIELD_ALIASES)


INDICATOR_LABELS = {
    "asset_liability_ratio": "资产负债率",
    "cash_short_debt_ratio": "现金短债比",
    "current_ratio": "流动比率",
    "quick_ratio": "速动比率",
    "net_cash_flow_from_operating_activities": "经营活动现金流量净额",
    "net_profit": "净利润",
    "revenue_yoy": "营业收入同比",
    "net_profit_yoy": "净利润同比",
    "net_cash_flow_from_operating_activities_yoy": "经营活动现金流净额同比",
    "short_term_debt_ratio": "短期债务占比",
    "operating_cash_flow_to_short_debt": "经营现金流短债覆盖倍数",
    "other_receivables_to_total_assets": "其他应收款占总资产比重",
    "inventory_to_total_assets": "存货占总资产比重",
}

TIER_LABELS = {
    "watch": "关注",
    "warning": "预警",
    "serious": "严重",
}


def normalize_page(page):
    try:
        page_int = int(page)
    except (TypeError, ValueError):
        return None
    return page_int if page_int > 0 else None


# ============================================================
# 字段索引
# ============================================================

class FieldIndex:
    """从 structured_financial_data 和 field_evidence 建立的可查询字段索引"""

    def __init__(self, structured_data, field_evidence, source_docs, extraction_warnings):
        self._records = []
        self.source_docs = source_docs or []
        self.source_doc_ids = {d.get("document_id") for d in self.source_docs if d.get("document_id")}
        self.source_doc_map = {d.get("document_id"): d for d in self.source_docs if d.get("document_id")}
        self.extraction_warnings = extraction_warnings or []
        self._build(structured_data, field_evidence)

    @staticmethod
    def normalize_name(name):
        return FIELD_CANONICAL.get(name or "", name or "")

    def _source_pdf_for(self, rec):
        if rec.get("source_pdf"):
            return rec.get("source_pdf")
        doc = self.source_doc_map.get(rec.get("source_document_id"), {})
        return (
            doc.get("source_pdf")
            or doc.get("local_pdf_path")
            or doc.get("pdf_url")
            or doc.get("file_name")
            or ""
        )

    def _evidence_text_for(self, rec):
        raw_row = rec.get("raw_row") or ""
        if raw_row:
            return raw_row
        field_name = rec.get("field_name") or rec.get("standard_field_name") or ""
        value = rec.get("value")
        unit = rec.get("unit") or "亿元"
        if field_name and value is not None:
            return f"{field_name} {round2(value)}{unit}"
        return rec.get("evidence_text") or ""

    def _make_record(self, item, value_key):
        standard = self.normalize_name(item.get("standard_field_name") or item.get("field_name") or "")
        rec = {
            "field_name": item.get("field_name", standard),
            "standard_field_name": standard,
            "period": item.get("period", ""),
            "value": self._safe_float(item.get(value_key)),
            "unit": item.get("unit_normalized") or item.get("unit") or "亿元",
            "source_document_id": item.get("source_document_id", ""),
            "source_pdf": item.get("source_pdf", ""),
            "page": normalize_page(item.get("page")),
            "table_id": item.get("table_id", ""),
            "table_title": item.get("table_title", ""),
            "raw_row": item.get("raw_row", ""),
            "raw_column": item.get("raw_column", ""),
            "evidence_text": item.get("evidence_text", ""),
            "confidence": item.get("confidence", "medium"),
        }
        rec["source_pdf"] = self._source_pdf_for(rec)
        rec["evidence_text"] = self._evidence_text_for(rec)
        return rec

    def _build(self, structured_data, field_evidence):
        for ev in field_evidence:
            self._records.append(self._make_record(ev, "value_normalized"))

        for table_type in ["balance_sheet", "income_statement", "cash_flow_statement"]:
            for row in structured_data.get("financial_tables", {}).get(table_type, []):
                self._records.append(self._make_record(row, "value"))

    @staticmethod
    def _safe_float(val):
        if val is None:
            return None
        try:
            v = float(val)
            if math.isnan(v) or math.isinf(v):
                return None
            return v
        except (ValueError, TypeError):
            return None

    def get_field(self, standard_name, period):
        candidates = []
        standard_name = self.normalize_name(standard_name)
        aliases = set(FIELD_ALIASES.get(standard_name, [])) | {standard_name}
        for rec in self._records:
            rec_standard = self.normalize_name(rec["standard_field_name"])
            rec_field = self.normalize_name(rec["field_name"])
            name_match = (
                rec_standard == standard_name or
                rec_standard in aliases or
                rec_field == standard_name or
                rec["field_name"] in aliases
            )
            if name_match and rec["period"] == period and rec["value"] is not None:
                candidates.append(rec)
        if not candidates:
            return None
        conf_score = {"high": 3, "medium": 2, "low": 1}
        candidates.sort(key=lambda r: conf_score.get(r["confidence"], 2), reverse=True)
        return candidates[0]

    def get_fields(self, standard_names, period):
        result = {}
        for name in standard_names:
            rec = self.get_field(name, period)
            result[name] = rec["value"] if rec else None
        return result


# ============================================================
# 辅助函数
# ============================================================

def safe_div(a, b):
    if a is None or b is None or b == 0:
        return None
    result = a / b
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def round2(val):
    if val is None:
        return None
    return round(val, 2)


def make_source_refs(input_fields):
    refs = []
    seen = set()
    for field in input_fields or []:
        source_id = field.get("source_document_id") or ""
        page = normalize_page(field.get("page"))
        table_id = field.get("table_id") or ""
        raw_row = field.get("raw_row") or ""
        evidence_text = field.get("evidence_text") or ""
        if not any([source_id, page, table_id, raw_row, evidence_text]):
            continue
        ref = {
            "source_document_id": source_id,
            "source_pdf": field.get("source_pdf") or "",
            "page": page,
            "table_id": table_id,
            "table_title": field.get("table_title") or "",
            "raw_row": raw_row,
            "raw_column": field.get("raw_column") or "",
            "evidence_text": evidence_text,
            "confidence": field.get("confidence") or "medium",
        }
        key = tuple(ref.items())
        if key not in seen:
            seen.add(key)
            refs.append(ref)
    return refs


def make_indicator(name, category, period, value, unit, formula,
                   input_fields, source_refs=None, confidence="medium",
                   formula_warning=""):
    status = "available" if value is not None else "unavailable"
    reason = "" if value is not None else f"缺少必要字段，无法计算{name}"
    refs = source_refs if source_refs and not all(isinstance(r, str) for r in source_refs) else make_source_refs(input_fields)
    return {
        "indicator_name": name,
        "indicator_category": category,
        "period": period,
        "value": round2(value),
        "unit": unit,
        "formula": formula,
        "input_fields": input_fields,
        "source_refs": refs,
        "status": status,
        "unavailable_reason": reason,
        "confidence": confidence,
        "formula_warning": formula_warning,
    }


def input_field_dict(field_name, period, value, unit="亿元", source_id="", page=None,
                     rec=None, standard_field_name=None):
    standard = FieldIndex.normalize_name(standard_field_name or field_name)
    rec = rec or {}
    evidence_text = rec.get("evidence_text") or rec.get("raw_row") or ""
    if not evidence_text and value is not None:
        evidence_text = f"{rec.get('field_name') or field_name} {round2(value)}{unit}"
    return {
        "field_name": rec.get("field_name") or field_name,
        "standard_field_name": standard,
        "period": period,
        "value": round2(value),
        "unit": unit,
        "source_document_id": source_id or rec.get("source_document_id", ""),
        "source_pdf": rec.get("source_pdf", ""),
        "page": normalize_page(page if page is not None else rec.get("page")),
        "table_id": rec.get("table_id", ""),
        "table_title": rec.get("table_title", ""),
        "raw_row": rec.get("raw_row", ""),
        "raw_column": rec.get("raw_column", ""),
        "evidence_text": evidence_text,
        "confidence": rec.get("confidence", "medium"),
    }


def normalize_source_documents(source_docs):
    normalized = []
    for doc in source_docs or []:
        item = dict(doc)
        item["source_pdf"] = (
            item.get("source_pdf")
            or item.get("local_pdf_path")
            or item.get("pdf_url")
            or item.get("file_name")
            or ""
        )
        item["file_type"] = item.get("file_type") or item.get("report_type") or ""
        normalized.append(item)
    return normalized


def combine_warnings(*warnings):
    parts = []
    for warning in warnings:
        if not warning:
            continue
        for piece in str(warning).split("；"):
            piece = piece.strip()
            if piece and piece not in parts:
                parts.append(piece)
    return "；".join(parts)


def dedupe_indicators(indicators):
    confidence_score = {"high": 3, "medium": 2, "low": 1}

    def score(ind):
        available = 1 if ind.get("status") == "available" else 0
        confidence = confidence_score.get(ind.get("confidence", "medium"), 2)
        input_count = len([f for f in ind.get("input_fields", []) if f.get("source_document_id") or f.get("evidence_text")])
        ref_count = len(ind.get("source_refs", []))
        return (available, confidence, input_count + ref_count, 1 if ind.get("formula_warning") else 0)

    best = {}
    order = []
    for ind in indicators:
        key = (ind.get("indicator_name"), ind.get("period"))
        if key not in best:
            best[key] = ind
            order.append(key)
        elif score(ind) > score(best[key]):
            best[key] = ind
    return [best[key] for key in order]


# ============================================================
# 指标计算
# ============================================================

def calc_indicators(fi, period, prev_period, start_period):
    """计算某一期间的所有指标"""
    indicators = []
    field_names = [
        "total_assets", "total_current_assets", "total_non_current_assets",
        "cash_and_cash_equivalents", "inventory", "accounts_receivable",
        "notes_receivable", "other_receivables", "total_liabilities",
        "total_current_liabilities", "total_non_current_liabilities",
        "short_term_borrowings", "non_current_liabilities_due_within_one_year",
        "long_term_borrowings", "bonds_payable", "long_term_payables",
        "total_owner_equity", "paid_in_capital", "capital_reserve",
        "other_equity_instruments", "undistributed_profit",
        "operating_revenue", "operating_cost", "operating_profit",
        "total_profit", "net_profit", "net_profit_attributable_to_parent",
        "financial_expenses", "interest_expense",
        "cash_inflow_from_operating_activities",
        "cash_outflow_from_operating_activities",
        "net_cash_flow_from_operating_activities",
        "cash_inflow_from_investing_activities",
        "cash_outflow_from_investing_activities",
        "net_cash_flow_from_investing_activities",
        "cash_inflow_from_financing_activities",
        "cash_outflow_from_financing_activities",
        "net_cash_flow_from_financing_activities",
        "net_increase_in_cash_and_cash_equivalents",
    ]
    fields = fi.get_fields(field_names, period)

    def get_f(name):
        return fields.get(FieldIndex.normalize_name(name))

    def get_rec(name, p=period):
        return fi.get_field(name, p)

    def get_input(name, p=period):
        canonical = FieldIndex.normalize_name(name)
        rec = get_rec(canonical, p)
        val = rec["value"] if rec else (get_f(canonical) if p == period else None)
        return input_field_dict(
            canonical, p, val,
            rec["unit"] if rec else "亿元",
            rec["source_document_id"] if rec else "",
            rec["page"] if rec else 0,
            rec=rec,
            standard_field_name=canonical,
        )

    def inputs(*names):
        return [get_input(n) for n in names]

    def pct(value):
        return round2(value * 100) if value is not None else None

    ta = get_f("total_assets")
    tl = get_f("total_liabilities")
    cash = get_f("cash_and_cash_equivalents")
    st_borrow = get_f("short_term_borrowings")
    ncl_1y = get_f("non_current_liabilities_due_within_one_year")
    lt_borrow = get_f("long_term_borrowings")
    bonds = get_f("bonds_payable")
    long_pay = get_f("long_term_payables")
    nocf = get_f("net_cash_flow_from_operating_activities")
    eq = get_f("total_owner_equity")
    rev = get_f("operating_revenue")
    cost = get_f("operating_cost")
    np_ = get_f("net_profit")
    inv = get_f("inventory")
    st_borrow_rec = get_rec("short_term_borrowings")
    ncl_1y_rec = get_rec("non_current_liabilities_due_within_one_year")

    short_debt_inputs = inputs("short_term_borrowings", "non_current_liabilities_due_within_one_year")
    st_debt = None
    short_debt_warning = ""
    if st_borrow_rec is not None or ncl_1y_rec is not None:
        st_debt = (st_borrow or 0) + (ncl_1y or 0)
        if st_borrow_rec is None or ncl_1y_rec is None:
            short_debt_warning = "短期有息债务口径不完整，仅基于已取得字段计算。"

    indicators.append(make_indicator(
        "asset_liability_ratio", "debt_capacity", period,
        pct(safe_div(tl, ta)), "%", "total_liabilities / total_assets x 100",
        inputs("total_liabilities", "total_assets")))

    indicators.append(make_indicator(
        "short_term_interest_bearing_debt", "debt_capacity", period,
        st_debt, "亿元", "short_term_borrowings + non_current_liabilities_due_within_one_year",
        short_debt_inputs, formula_warning=short_debt_warning))

    indicators.append(make_indicator(
        "cash_short_debt_ratio", "debt_capacity", period,
        safe_div(cash, st_debt), "倍", "cash_and_cash_equivalents / short_term_interest_bearing_debt",
        [get_input("cash_and_cash_equivalents")] + short_debt_inputs,
        formula_warning=short_debt_warning))

    debt_component_recs = {name: get_rec(name) for name in DEBT_COMPONENTS}
    present_debt_components = [name for name, rec in debt_component_recs.items() if rec is not None]
    missing_debt_components = [name for name, rec in debt_component_recs.items() if rec is None]
    ibd = None
    if present_debt_components:
        ibd = sum(get_f(name) or 0 for name in present_debt_components)
    ibd_warning = short_debt_warning
    if missing_debt_components and present_debt_components:
        ibd_warning = combine_warnings(
            ibd_warning,
            "有息债务口径不完整，部分债务科目缺失，当前结果可能低估有息债务规模。"
        )
    if long_pay is not None:
        ibd_warning = combine_warnings(
            ibd_warning,
            "长期应付款可能包含非债务性质款项，有息债务口径需结合附注确认。"
        )
    ibd_confidence = "low" if 0 < len(present_debt_components) < 2 else "medium"
    debt_inputs = short_debt_inputs + inputs("long_term_borrowings", "bonds_payable", "long_term_payables")
    indicators.append(make_indicator(
        "interest_bearing_debt", "debt_capacity", period,
        ibd, "亿元", "short_term_borrowings + non_current_liabilities_due_within_one_year + long_term_borrowings + bonds_payable + long_term_payables",
        debt_inputs, confidence=ibd_confidence, formula_warning=ibd_warning))

    indicators.append(make_indicator(
        "operating_cash_flow_to_short_debt", "debt_capacity", period,
        safe_div(nocf, st_debt), "倍", "net_cash_flow_from_operating_activities / short_term_interest_bearing_debt",
        [get_input("net_cash_flow_from_operating_activities")] + short_debt_inputs,
        formula_warning=short_debt_warning))

    indicators.append(make_indicator(
        "interest_bearing_debt_to_equity", "debt_capacity", period,
        safe_div(ibd, eq), "倍", "interest_bearing_debt / total_owner_equity",
        debt_inputs + inputs("total_owner_equity"), formula_warning=ibd_warning))

    tp = get_f("total_profit")
    ie = get_f("interest_expense")
    icr = safe_div((tp + ie), ie) if tp is not None and ie not in (None, 0) else None
    indicators.append(make_indicator(
        "interest_coverage_ratio", "debt_capacity", period,
        icr, "倍", "(total_profit + interest_expense) / interest_expense",
        inputs("total_profit", "interest_expense")))

    ca = get_f("total_current_assets")
    cl = get_f("total_current_liabilities")
    indicators.append(make_indicator(
        "current_ratio", "liquidity", period,
        safe_div(ca, cl), "倍", "total_current_assets / total_current_liabilities",
        inputs("total_current_assets", "total_current_liabilities")))

    qr = safe_div(ca - inv, cl) if ca is not None and inv is not None else None
    indicators.append(make_indicator(
        "quick_ratio", "liquidity", period,
        qr, "倍", "(total_current_assets - inventory) / total_current_liabilities",
        inputs("total_current_assets", "inventory", "total_current_liabilities")))

    nr = get_f("notes_receivable")
    ar = get_f("accounts_receivable")
    quick_asset = (cash or 0) + (nr or 0) + (ar or 0) if any(v is not None for v in [cash, nr, ar]) else None
    indicators.append(make_indicator(
        "quick_asset_to_short_debt", "liquidity", period,
        safe_div(quick_asset, st_debt), "倍", "(cash_and_cash_equivalents + notes_receivable + accounts_receivable) / short_term_interest_bearing_debt",
        inputs("cash_and_cash_equivalents", "notes_receivable", "accounts_receivable") + short_debt_inputs))

    indicators.append(make_indicator("operating_revenue", "profitability", period, rev, "亿元", "直接取值", inputs("operating_revenue")))
    indicators.append(make_indicator("net_profit", "profitability", period, np_, "亿元", "直接取值", inputs("net_profit")))

    op = get_f("operating_profit")
    indicators.append(make_indicator(
        "operating_profit_margin", "profitability", period,
        pct(safe_div(op, rev)), "%", "operating_profit / operating_revenue x 100",
        inputs("operating_profit", "operating_revenue")))
    indicators.append(make_indicator(
        "net_profit_margin", "profitability", period,
        pct(safe_div(np_, rev)), "%", "net_profit / operating_revenue x 100",
        inputs("net_profit", "operating_revenue")))
    gpm = pct(safe_div(rev - cost, rev)) if rev is not None and cost is not None else None
    indicators.append(make_indicator(
        "gross_profit_margin", "profitability", period,
        gpm, "%", "(operating_revenue - operating_cost) / operating_revenue x 100",
        inputs("operating_revenue", "operating_cost")))

    av_ta = None
    av_eq = None
    if start_period:
        st_ta = fi.get_fields(["total_assets"], start_period).get("total_assets")
        st_eq = fi.get_fields(["total_owner_equity"], start_period).get("total_owner_equity")
        if ta is not None and st_ta is not None:
            av_ta = (ta + st_ta) / 2
        if eq is not None and st_eq is not None:
            av_eq = (eq + st_eq) / 2
    indicators.append(make_indicator("roa", "profitability", period, pct(safe_div(np_, av_ta)), "%", "net_profit / average total_assets x 100", inputs("net_profit", "total_assets")))
    indicators.append(make_indicator("roe", "profitability", period, pct(safe_div(np_, av_eq)), "%", "net_profit / average total_owner_equity x 100", inputs("net_profit", "total_owner_equity")))

    indicators.append(make_indicator("net_cash_flow_from_operating_activities", "cash_flow", period, nocf, "亿元", "直接取值", inputs("net_cash_flow_from_operating_activities")))
    nicf = get_f("net_cash_flow_from_investing_activities")
    nfcf = get_f("net_cash_flow_from_financing_activities")
    indicators.append(make_indicator("net_cash_flow_from_investing_activities", "cash_flow", period, nicf, "亿元", "直接取值", inputs("net_cash_flow_from_investing_activities")))
    indicators.append(make_indicator("net_cash_flow_from_financing_activities", "cash_flow", period, nfcf, "亿元", "直接取值", inputs("net_cash_flow_from_financing_activities")))
    indicators.append(make_indicator("cf_to_revenue", "cash_flow", period, pct(safe_div(nocf, rev)), "%", "net_cash_flow_from_operating_activities / operating_revenue x 100", inputs("net_cash_flow_from_operating_activities", "operating_revenue")))
    indicators.append(make_indicator("net_cash_flow_to_net_profit", "cash_flow", period, safe_div(nocf, np_), "倍", "net_cash_flow_from_operating_activities / net_profit", inputs("net_cash_flow_from_operating_activities", "net_profit")))

    indicators.append(make_indicator(
        "short_term_debt_ratio", "debt_structure", period,
        pct(safe_div(st_debt, ibd)), "%", "short_term_interest_bearing_debt / interest_bearing_debt x 100",
        debt_inputs, formula_warning=combine_warnings(short_debt_warning, ibd_warning)))

    indicators.append(make_indicator("total_owner_equity", "capital_structure", period, eq, "亿元", "直接取值", inputs("total_owner_equity")))
    up = get_f("undistributed_profit")
    indicators.append(make_indicator("undistributed_profit_ratio", "capital_structure", period, pct(safe_div(up, eq)), "%", "undistributed_profit / total_owner_equity x 100", inputs("undistributed_profit", "total_owner_equity")))
    other_recv = get_f("other_receivables")
    cap_res = get_f("capital_reserve")
    other_eq = get_f("other_equity_instruments")
    indicators.append(make_indicator("other_receivables_to_total_assets", "capital_structure", period, pct(safe_div(other_recv, ta)), "%", "other_receivables / total_assets x 100", inputs("other_receivables", "total_assets")))
    indicators.append(make_indicator("inventory_to_total_assets", "capital_structure", period, pct(safe_div(inv, ta)), "%", "inventory / total_assets x 100", inputs("inventory", "total_assets")))
    indicators.append(make_indicator("capital_reserve_to_owner_equity", "capital_structure", period, pct(safe_div(cap_res, eq)), "%", "capital_reserve / total_owner_equity x 100", inputs("capital_reserve", "total_owner_equity")))
    indicators.append(make_indicator("other_equity_instruments_to_owner_equity", "capital_structure", period, pct(safe_div(other_eq, eq)), "%", "other_equity_instruments / total_owner_equity x 100", inputs("other_equity_instruments", "total_owner_equity")))

    if prev_period:
        def yoy(cur, prev):
            if cur is None or prev is None or prev == 0:
                return None, ""
            warning = "上期值为负数，同比口径需审慎解读。" if prev < 0 else ""
            return round2((cur / prev - 1) * 100), warning

        prev_rev = fi.get_fields(["operating_revenue"], prev_period).get("operating_revenue")
        prev_np = fi.get_fields(["net_profit"], prev_period).get("net_profit")
        prev_nocf = fi.get_fields(["net_cash_flow_from_operating_activities"], prev_period).get("net_cash_flow_from_operating_activities")
        rev_yoy, fw_rev = yoy(rev, prev_rev)
        np_yoy, fw_np = yoy(np_, prev_np)
        nocf_yoy, fw_nocf = yoy(nocf, prev_nocf)
        indicators.append(make_indicator("revenue_yoy", "growth", period, rev_yoy, "%", "current operating_revenue / prior operating_revenue - 1", [get_input("operating_revenue"), get_input("operating_revenue", prev_period)], formula_warning=fw_rev))
        indicators.append(make_indicator("net_profit_yoy", "growth", period, np_yoy, "%", "current net_profit / prior net_profit - 1", [get_input("net_profit"), get_input("net_profit", prev_period)], formula_warning=fw_np))
        indicators.append(make_indicator("net_cash_flow_from_operating_activities_yoy", "growth", period, nocf_yoy, "%", "current net_cash_flow_from_operating_activities / prior net_cash_flow_from_operating_activities - 1", [get_input("net_cash_flow_from_operating_activities"), get_input("net_cash_flow_from_operating_activities", prev_period)], formula_warning=fw_nocf))

    return indicators


# ============================================================
# 风险发现
# ============================================================

def _indicator_period_order(indicators):
    order = []
    seen = set()
    for ind in indicators:
        p = ind.get("period", "")
        if p and p not in seen:
            seen.add(p)
            order.append(p)
    return order


def _negative_streak(indicators, indicator_name, period):
    periods = _indicator_period_order(indicators)
    if period not in periods:
        return 0
    by_period = {
        ind.get("period"): ind.get("value")
        for ind in indicators
        if ind.get("indicator_name") == indicator_name and ind.get("status") == "available"
    }
    streak = 0
    for p in periods[periods.index(period):]:
        v = by_period.get(p)
        if v is not None and v < 0:
            streak += 1
        else:
            break
    return streak


def _threshold_tier(ind, thresholds, indicators):
    t = thresholds.get(ind.get("indicator_name"))
    if not t or ind.get("status") != "available":
        return None, None
    if t.get("kind") == "negative_streak":
        streak = _negative_streak(indicators, ind["indicator_name"], ind.get("period", ""))
        if streak >= 3:
            return "serious", "连续三期为负"
        if streak >= 2:
            return "warning", "连续两期为负"
        if streak >= 1:
            return "watch", "当期为负"
        return None, None
    val = ind.get("value")
    if val is None:
        return None, None
    direction = t.get("direction")
    if direction == "high":
        if val >= t.get("serious"):
            return "serious", f">= {t.get('serious')}{ind.get('unit','')}"
        if val >= t.get("warning"):
            return "warning", f">= {t.get('warning')}{ind.get('unit','')}"
        if val >= t.get("watch"):
            return "watch", f">= {t.get('watch')}{ind.get('unit','')}"
    else:
        if val < t.get("serious"):
            return "serious", f"< {t.get('serious')}{ind.get('unit','')}"
        if val < t.get("warning"):
            return "warning", f"< {t.get('warning')}{ind.get('unit','')}"
        if val < t.get("watch"):
            return "watch", f"< {t.get('watch')}{ind.get('unit','')}"
    return None, None


def _indicator_evidence(ind, valid_doc_ids):
    fields = ind.get("input_fields") or []
    first = next((f for f in fields if f.get("source_document_id")), fields[0] if fields else {})
    source_id = first.get("source_document_id", "")
    source_refs = ind.get("source_refs") or make_source_refs(fields)
    first_ref = source_refs[0] if source_refs else {}
    evidence_text = "; ".join(f.get("evidence_text") or f.get("raw_row") or "" for f in fields if f.get("evidence_text") or f.get("raw_row"))
    if not evidence_text:
        evidence_text = "; ".join(
            f"{f.get('field_name','')}{f.get('value','')}{f.get('unit','')}"
            for f in fields[:3]
            if f.get("value") is not None
        )
    page = normalize_page(first.get("page"))
    table_id = first.get("table_id", "") or first_ref.get("table_id", "")
    source_pdf = first.get("source_pdf", "") or first_ref.get("source_pdf", "")
    table_title = first.get("table_title", "") or first_ref.get("table_title", "")
    source_exists = bool(valid_doc_ids) and source_id in valid_doc_ids
    has_location = bool((isinstance(page, int) and page > 0) or table_id)
    complete = bool(source_id and source_exists and evidence_text and has_location and source_refs)
    return source_id, evidence_text, page, table_id, source_pdf, table_title, source_refs, complete


def _format_indicator_value(value, unit):
    if value is None:
        return "无法计算"
    if isinstance(value, (int, float)):
        return f"{value:.2f}{unit or ''}"
    return f"{value}{unit or ''}"


def _build_judgement(ind, tier, threshold_text, direction):
    iname = ind.get("indicator_name", "")
    label = INDICATOR_LABELS.get(iname, iname)
    tier_label = TIER_LABELS.get(tier, tier)
    value_text = _format_indicator_value(ind.get("value"), ind.get("unit", ""))
    threshold_phrase = "达到" if direction == "high" else "低于" if direction == "low" else "触及"
    threshold_clause = f"{threshold_phrase}{tier_label}阈值（{threshold_text}）"

    specific = {
        "asset_liability_ratio": "反映公司债务负担偏重，后续需关注再融资环境和债务滚续压力。",
        "cash_short_debt_ratio": "反映货币资金对短期有息债务覆盖偏弱，需关注短期偿债安排。",
        "operating_cash_flow_to_short_debt": "说明经营活动现金流对短期债务覆盖能力偏弱。",
        "current_ratio": "反映流动资产对流动负债的覆盖偏弱，需关注短期流动性安排。",
        "quick_ratio": "反映剔除存货后的流动性保障偏弱，资产流动性有待关注。",
        "short_term_debt_ratio": "反映债务期限结构偏短，需关注短期债务滚续压力。",
        "revenue_yoy": "反映营业收入出现下滑，需关注主营业务稳定性。",
        "net_profit_yoy": "反映盈利表现下滑，需关注利润质量和成本费用压力。",
        "net_cash_flow_from_operating_activities_yoy": "反映经营活动现金流同比走弱，需关注经营回款和项目支出匹配情况。",
        "other_receivables_to_total_assets": "反映往来款对资产占用较高，资产流动性有待关注。",
        "inventory_to_total_assets": "反映存货占比较高，需关注资产变现能力和项目周转情况。",
        "net_profit": "反映盈利表现承压，需关注利润质量和持续经营表现。",
        "net_cash_flow_from_operating_activities": "反映经营性现金流表现承压，需关注经营回款和项目支出匹配情况。",
    }
    tail = specific.get(iname, "需结合后续期间数据和外部支持稳定性持续跟踪。")
    return f"{label}为{value_text}，{threshold_clause}，{tail}"


def find_negative_findings(indicators, enterprise_type, thresholds_config=None, source_docs=None, main_period=None):
    """根据指标和三档阈值生成风险发现"""
    findings = []
    thresholds = deepcopy(DEFAULT_THRESHOLDS.get(enterprise_type, DEFAULT_THRESHOLDS["城投"]))
    if thresholds_config:
        for key, val in thresholds_config.items():
            if key in thresholds and isinstance(val, dict):
                thresholds[key].update(val)
            elif isinstance(val, dict):
                thresholds[key] = val
    valid_doc_ids = {d.get("document_id") for d in (source_docs or []) if d.get("document_id")}

    counter = 0
    for ind in indicators:
        iname = ind.get("indicator_name", "")
        if main_period and ind.get("period") != main_period:
            continue
        if ind.get("status") != "available":
            if iname not in CORE_INDICATORS or (main_period and ind.get("period") != main_period):
                continue
            counter += 1
            findings.append({
                "finding_id": f"FL{counter:04d}",
                "finding_type": "data_limitation",
                "risk_level": "low",
                "indicator_name": iname,
                "period": ind.get("period", ""),
                "value": None,
                "threshold": "",
                "judgement": f"核心指标{iname}无法计算：{ind.get('unavailable_reason','缺少必要字段')}",
                "evidence_text": "",
                "source_document_id": "",
                "source_pdf": "",
                "page": None,
                "table_id": "",
                "table_title": "",
                "source_refs": [],
                "confidence": "medium",
            })
            continue

        tier, threshold_text = _threshold_tier(ind, thresholds, indicators)
        if not tier:
            continue

        source_id, evidence_text, page, table_id, source_pdf, table_title, source_refs, complete = _indicator_evidence(ind, valid_doc_ids)
        confidence = ind.get("confidence", "medium")
        if tier == "serious" and complete and confidence != "low":
            ftype, rlevel = "confirmed_risk", "high"
        elif tier in ("serious", "warning"):
            ftype, rlevel = "warning_signal", "medium"
        else:
            ftype, rlevel = "warning_signal", "low"

        counter += 1
        direction = thresholds.get(iname, {}).get("direction", "")
        judgement = _build_judgement(ind, tier, threshold_text, direction)
        findings.append({
            "finding_id": f"FL{counter:04d}",
            "finding_type": ftype,
            "risk_level": rlevel,
            "indicator_name": iname,
            "period": ind.get("period", ""),
            "value": ind.get("value"),
            "threshold": threshold_text or "",
            "judgement": judgement,
            "evidence_text": evidence_text,
            "source_document_id": source_id,
            "source_pdf": source_pdf,
            "page": page,
            "table_id": table_id,
            "table_title": table_title,
            "source_refs": source_refs,
            "confidence": confidence,
        })
    return findings


# ============================================================
# 分析摘要
# ============================================================

def generate_analysis_summary(indicators, findings, enterprise_name,
                               main_period, data_status):
    """生成审慎的分析摘要文字"""

    def get_ind_val(name, period=None):
        for ind in indicators:
            if ind["indicator_name"] == name and ind["status"] == "available" and (period is None or ind.get("period") == period):
                return ind["value"]
        return None

    def fmt_val(val, unit="%"):
        return f"{val}{unit}" if val is not None else None

    def sentence_for_missing(field_text):
        return f"由于未取得{field_text}，本次无法判断相关财务表现。"

    alr = get_ind_val("asset_liability_ratio", main_period)
    rev = get_ind_val("operating_revenue", main_period)
    np_val = get_ind_val("net_profit", main_period)
    nocf_val = get_ind_val("net_cash_flow_from_operating_activities", main_period)
    csdr_val = get_ind_val("cash_short_debt_ratio", main_period)
    std_val = get_ind_val("short_term_debt_ratio", main_period)
    ibd_val = get_ind_val("interest_bearing_debt", main_period)
    eq_val = get_ind_val("total_owner_equity", main_period)
    ta_val = get_ind_val("total_assets", main_period)
    nocf_streak = _negative_streak(indicators, "net_cash_flow_from_operating_activities", main_period)

    unavailable = [ind for ind in indicators if ind["status"] == "unavailable"]
    core_missing = [ind["indicator_name"] for ind in unavailable if ind["indicator_name"] in CORE_INDICATORS]
    non_core_missing = [ind["indicator_name"] for ind in unavailable if ind["indicator_name"] not in CORE_INDICATORS]

    overall = f"根据上游传入的结构化财务数据，{enterprise_name}"
    if ta_val is not None:
        overall += f"报告期末总资产规模约{fmt_val(ta_val, '亿元')}。"
    else:
        overall += "未取得总资产数据，资产规模无法判断。"
    if alr is not None:
        if alr >= 70:
            overall += f"资产负债率{fmt_val(alr)}，债务负担偏重。"
        elif alr >= 60:
            overall += f"资产负债率{fmt_val(alr)}，债务负担处于中等水平。"
        else:
            overall += f"资产负债率{fmt_val(alr)}，债务负担相对可控。"
    else:
        overall += "由于未取得资产负债率计算所需字段，本次无法判断整体债务负担。"
    if data_status != "sufficient":
        overall += "由于部分字段缺失，本次结论仅基于已取得字段审慎形成。"

    if alr is not None:
        dp = f"报告期末资产负债率为{fmt_val(alr)}。"
        if alr >= 65:
            dp += "债务负担偏重，后续需关注再融资环境和外部支持稳定性。"
    else:
        dp = sentence_for_missing("总资产或总负债")
    if ibd_val is not None:
        dp += f"有息债务合计约{fmt_val(ibd_val, '亿元')}。"

    if rev is not None and np_val is not None:
        prof = f"报告期公司实现营业收入{fmt_val(rev, '亿元')}，净利润{fmt_val(np_val, '亿元')}。"
    elif rev is None and np_val is None:
        prof = "由于未取得营业收入和净利润，本次无法判断收入及盈利表现。"
    elif rev is None:
        prof = f"由于未取得营业收入，本次仅识别到净利润{fmt_val(np_val, '亿元')}，无法完整判断盈利质量。"
    else:
        prof = f"营业收入为{fmt_val(rev, '亿元')}，由于未取得净利润，本次无法完整判断盈利水平。"

    if nocf_val is None:
        cf = "由于未取得经营活动现金流量净额，本次无法判断经营性现金流对债务偿付的覆盖情况。"
    elif nocf_val < 0 and nocf_streak >= 2:
        cf = "经营活动现金流量净额连续两期或以上为负，经营性现金流对债务偿付覆盖不足，需关注经营回款和项目支出匹配情况。"
    elif nocf_val < 0:
        cf = "当期经营活动现金流量净额为负，需关注经营回款和项目支出匹配情况。"
    else:
        cf = f"经营活动现金流量净额为{fmt_val(nocf_val, '亿元')}。"

    if csdr_val is None:
        refin = "由于短期有息债务或货币资金字段缺失，无法判断现金短债覆盖水平。"
    else:
        refin = f"现金短债比为{fmt_val(csdr_val, '倍')}。"
        if csdr_val < 1:
            refin += "短期偿债保障偏弱。"
        else:
            refin += "现金对短期有息债务具备一定覆盖。"
    if std_val is not None:
        refin += f"短期债务占比{fmt_val(std_val)}，后续需关注再融资环境和外部支持稳定性。"

    if eq_val is None:
        cap = "由于未取得所有者权益，本次无法判断资本结构稳定性。"
    else:
        cap = f"所有者权益{fmt_val(eq_val, '亿元')}。"
    data_lim_note = ""
    if core_missing:
        data_lim_note += "核心指标缺失：" + "、".join(sorted(set(core_missing))) + "。"
    if non_core_missing:
        data_lim_note += "非核心指标缺失已进入 unavailable_indicators，不单独形成风险发现。"
    if not data_lim_note:
        data_lim_note = "本次分析基于已取得结构化字段，未发现核心指标重大缺失。"

    return {
        "overall_view": overall,
        "debt_pressure": dp,
        "profitability": prof,
        "cash_flow": cf,
        "refinancing_pressure": refin,
        "capital_structure": cap,
        "data_limitation_note": data_lim_note,
    }


# ============================================================
# 前端摘要 + 直接取值指标
# ============================================================

def generate_frontend_summary(indicators, fi, main_period):
    """从前端指标中提取关键字段"""
    def giv(name):
        canonical = FieldIndex.normalize_name(name)
        for ind in indicators:
            if ind["indicator_name"] == canonical and ind["status"] == "available" and ind.get("period") == main_period:
                return ind["value"]
        rec = fi.get_field(canonical, main_period)
        return rec["value"] if rec else None

    return {
        "total_assets": giv("total_assets"),
        "total_liabilities": giv("total_liabilities"),
        "asset_liability_ratio": giv("asset_liability_ratio"),
        "cash_and_cash_equivalents": giv("cash_and_cash_equivalents"),
        "short_term_interest_bearing_debt": giv("short_term_interest_bearing_debt"),
        "cash_short_debt_ratio": giv("cash_short_debt_ratio"),
        "operating_revenue": giv("operating_revenue"),
        "net_profit": giv("net_profit"),
        "net_cash_flow_from_operating_activities": giv("net_cash_flow_from_operating_activities"),
        "total_owner_equity": giv("total_owner_equity"),
        "interest_bearing_debt": giv("interest_bearing_debt"),
        "current_ratio": giv("current_ratio"),
        "quick_ratio": giv("quick_ratio"),
    }


def calc_direct_value_indicators(fi, period):
    """补充直接取值字段，便于前端读取"""
    indicators = []

    def make_direct(name, category):
        canonical = FieldIndex.normalize_name(name)
        rec = fi.get_field(canonical, period)
        val = rec["value"] if rec else None
        input_f = [input_field_dict(canonical, period, val, rec["unit"], rec["source_document_id"], rec["page"], rec=rec)] if rec else []
        return make_indicator(canonical, category, period, val,
            rec["unit"] if rec else "亿元", "直接取值",
            input_f,
            confidence=rec["confidence"] if rec else "medium")

    for name, cat in [
        ("total_assets", "capital_structure"),
        ("total_liabilities", "debt_structure"),
        ("cash_and_cash_equivalents", "liquidity"),
        ("total_owner_equity", "capital_structure"),
    ]:
        indicators.append(make_direct(name, cat))
    return indicators


def calc_auxiliary_period_indicators(fi, period):
    """Only keep auxiliary-period values needed for YoY and negative-streak checks."""
    indicators = []

    for name, cat in [
        ("operating_revenue", "profitability"),
        ("net_profit", "profitability"),
        ("net_cash_flow_from_operating_activities", "cash_flow"),
    ]:
        rec = fi.get_field(name, period)
        if not rec:
            continue
        val = rec["value"]
        input_f = [input_field_dict(name, period, val, rec["unit"], rec["source_document_id"], rec["page"], rec=rec)]
        indicators.append(make_indicator(
            name, cat, period, val, rec["unit"], "辅助期间直接取值",
            input_f, confidence=rec["confidence"]))
    return indicators


# ============================================================
# 输出验证
# ============================================================

def validate_output(indicators, findings, summary, frontend, data_status, fi, source_docs=None):
    """验证输出是否符合规范"""
    errors = []
    warnings = []
    valid_doc_ids = {d.get("document_id") for d in (source_docs or []) if d.get("document_id")}
    main_period = indicators[0].get("period", "") if indicators else ""
    seen_indicator_keys = set()

    for ind in indicators:
        key = (ind.get("indicator_name"), ind.get("period"))
        if key in seen_indicator_keys:
            errors.append(f"指标{ind.get('indicator_name')}({ind.get('period')})重复")
        seen_indicator_keys.add(key)
        if ind["status"] == "available" and not ind.get("input_fields"):
            errors.append(f"指标{ind['indicator_name']}status=available但缺少input_fields")
        if ind.get("indicator_name") == "cash_short_debt_ratio" and ind.get("status") == "available" and ind.get("unit") != "倍":
            errors.append("cash_short_debt_ratio单位必须为倍")
        if ind.get("indicator_name") == "quick_ratio" and ind.get("status") == "available":
            has_inventory = any(f.get("standard_field_name") == "inventory" and f.get("value") is not None for f in ind.get("input_fields", []))
            if not has_inventory:
                errors.append("quick_ratio在inventory缺失时不得计算")
        for ref in ind.get("source_refs", []):
            if isinstance(ref, str):
                errors.append(f"指标{ind['indicator_name']}source_refs不得是字段名字符串")
        if ind.get("indicator_name") == "short_term_interest_bearing_debt" and ind.get("status") == "available":
            fields = {f.get("standard_field_name"): f.get("value") for f in ind.get("input_fields", [])}
            has_st = fields.get("short_term_borrowings") is not None
            has_due = fields.get("non_current_liabilities_due_within_one_year") is not None
            if has_st != has_due and "短期有息债务口径不完整" not in ind.get("formula_warning", ""):
                errors.append("short_term_interest_bearing_debt缺少短债组成字段时必须提示口径不完整")
        if ind.get("indicator_name") == "interest_bearing_debt" and ind.get("status") == "available":
            fields = {f.get("standard_field_name"): f.get("value") for f in ind.get("input_fields", [])}
            missing_debt = [name for name in DEBT_COMPONENTS if fields.get(name) is None]
            if missing_debt and "有息债务口径不完整" not in ind.get("formula_warning", ""):
                errors.append("interest_bearing_debt部分债务科目缺失时必须提示口径不完整")

    for ind in indicators:
        v = ind.get("value")
        if v is not None and isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            errors.append(f"指标{ind['indicator_name']}value为NaN/Infinity")

    unavailable_keys = {(ind["indicator_name"], ind["period"]) for ind in indicators if ind["status"] == "unavailable"}
    for f in findings:
        if f["finding_type"] in ("confirmed_risk", "warning_signal"):
            key = (f.get("indicator_name",""), f.get("period",""))
            if key in unavailable_keys:
                errors.append(f"finding{f['finding_id']}引用了unavailable指标{f['indicator_name']}({f.get('period','')})")
            if not f.get("threshold"):
                errors.append(f"finding{f['finding_id']}缺少threshold")
        if f.get("source_document_id") in STANDARD_FIELD_NAMES:
            errors.append(f"finding{f.get('finding_id','?')}source_document_id错误使用字段名")
        if f.get("finding_type") == "data_limitation" and f.get("indicator_name") and f.get("indicator_name") not in CORE_INDICATORS:
            errors.append(f"data_limitation只能针对核心指标: {f.get('indicator_name')}")
        if f.get("finding_type") == "data_limitation" and f.get("indicator_name") and main_period and f.get("period") != main_period:
            errors.append(f"data_limitation默认只允许针对主报告期核心指标: {f.get('indicator_name')}({f.get('period')})")
        if f.get("source_refs") is not None:
            if not isinstance(f.get("source_refs"), list) or any(isinstance(ref, str) for ref in f.get("source_refs", [])):
                errors.append(f"finding{f.get('finding_id','?')}source_refs必须是证据对象数组")
        if f["finding_type"] == "confirmed_risk":
            if not valid_doc_ids:
                errors.append(f"finding{f['finding_id']}confirmed_risk要求source_documents非空")
            if not f.get("source_document_id"):
                errors.append(f"finding{f['finding_id']}confirmed_risk缺少source_document_id")
            if f.get("source_document_id") not in valid_doc_ids:
                errors.append(f"finding{f['finding_id']}source_document_id不存在于source_documents")
            if not f.get("evidence_text"):
                errors.append(f"finding{f['finding_id']}confirmed_risk缺少evidence_text")
            page = f.get("page")
            has_page = isinstance(page, int) and page > 0
            if not (has_page or f.get("table_id")):
                errors.append(f"finding{f['finding_id']}confirmed_risk缺少正整数page或table_id")
            if not f.get("source_pdf"):
                warnings.append(f"finding{f['finding_id']}confirmed_risk建议提供source_pdf")
            if not f.get("source_refs"):
                errors.append(f"finding{f['finding_id']}confirmed_risk必须提供source_refs")
            if f.get("confidence") == "low":
                errors.append(f"finding{f['finding_id']}confirmed_risk置信度不能为low")

    forbidden = ["建议买入", "建议卖出", "建议持有", "信用评级为", "投资建议", "推荐买入", "推荐卖出", "N/A"]
    for key, text in summary.items():
        if isinstance(text, str):
            for word in forbidden:
                if word in text:
                    errors.append(f"analysis_summary.{key}包含禁止词汇:{word}")
    if any("持续为负" in text for text in summary.values() if isinstance(text, str)):
        main_period = indicators[0].get("period", "") if indicators else ""
        if _negative_streak(indicators, "net_cash_flow_from_operating_activities", main_period) < 2:
            errors.append("analysis_summary中持续为负必须有连续两期为负数据支持")

    for k, v in frontend.items():
        if v is not None and isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            errors.append(f"frontend_financial_summary.{k}值为NaN/Infinity")
    std_ind = next((ind for ind in indicators if ind.get("indicator_name") == "short_term_interest_bearing_debt" and ind.get("status") == "available"), None)
    if std_ind and frontend.get("short_term_interest_bearing_debt") is None:
        errors.append("frontend_financial_summary.short_term_interest_bearing_debt必须来自计算指标")

    if data_status == "insufficient":
        non_lim = [f for f in findings if f["finding_type"] != "data_limitation"]
        if non_lim:
            errors.append(f"data_status=insufficient但存在{len(non_lim)}条非data_limitation的finding")

    return {"passed": len(errors) == 0, "errors": errors, "warnings": warnings}


# ============================================================
# 主流程
# ============================================================

def run_analysis(input_data):
    """执行完整的财务分析"""
    task_id = input_data.get("task_id", "")
    enterprise_name = input_data.get("enterprise_name", "")
    ctx = input_data.get("analysis_context", {})
    enterprise_type = ctx.get("enterprise_type", "城投")
    main_period = ctx.get("main_report_period", "")
    expected_periods = ctx.get("expected_periods", [])
    thresholds_config = input_data.get("thresholds_config", {})

    structured_data = input_data.get("structured_financial_data", {})
    field_evidence = input_data.get("field_evidence", [])
    source_docs = normalize_source_documents(input_data.get("source_documents", []))
    extraction_warnings = input_data.get("extraction_warnings", [])

    has_data = field_evidence or any(
        structured_data.get("financial_tables", {}).get(t, [])
        for t in ["balance_sheet", "income_statement", "cash_flow_statement"]
    )

    if not has_data:
        return {
            "task_id": task_id, "enterprise_name": enterprise_name,
            "analysis_status": "failed", "data_status": "insufficient",
            "main_period": main_period, "periods_analyzed": [],
            "source_documents": source_docs,
            "financial_indicators": [],
            "negative_findings": [{
                "finding_id": "FL0001", "finding_type": "data_limitation",
                "risk_level": "medium", "indicator_name": "", "period": "",
                "value": None, "threshold": "",
                "judgement": "上游未提供任何有效财务字段，无法进行分析",
                "evidence_text": "", "source_document_id": "", "page": None,
                "source_pdf": "", "table_id": "", "table_title": "", "source_refs": [],
                "confidence": "medium",
            }],
            "analysis_summary": {
                "overall_view": "由于上游未提供任何有效的结构化财务数据，本次分析无法进行。",
                "debt_pressure": "", "profitability": "",
                "cash_flow": "", "refinancing_pressure": "",
                "capital_structure": "",
                "data_limitation_note": "公开财务字段不足，仅能完成有限分析，无法形成完整财务判断。",
            },
            "frontend_financial_summary": {},
            "unavailable_indicators": [],
            "risk_level_summary": {
                "confirmed_risk_count": 0, "warning_signal_count": 0,
                "data_limitation_count": 1, "highest_risk_level": "medium",
            },
            "validation_result": {"passed": True, "errors": [], "warnings": []},
        }

    fi = FieldIndex(structured_data, field_evidence, source_docs, extraction_warnings)

    if expected_periods:
        periods = list(expected_periods)
        if main_period and main_period not in periods:
            periods.insert(0, main_period)
    elif main_period:
        periods = [main_period]
    if not periods:
        all_periods = sorted({r["period"] for r in fi._records if r["period"]}, reverse=True)
        periods = all_periods
        if periods:
            main_period = periods[0]

    all_indicators = []
    prev_period = None
    for i, period in enumerate(periods):
        start_period = periods[i + 1] if i + 1 < len(periods) else None
        prev_period = periods[i + 1] if i + 1 < len(periods) else None
        if period == main_period:
            indicators = calc_indicators(fi, period, prev_period, start_period)
            indicators += calc_direct_value_indicators(fi, period)
        else:
            indicators = calc_auxiliary_period_indicators(fi, period)
        all_indicators.extend(indicators)

    all_indicators = dedupe_indicators(all_indicators)

    negative_findings = find_negative_findings(
        all_indicators, enterprise_type, thresholds_config, source_docs, main_period
    )

    core_indicators = [
        ind for ind in all_indicators
        if ind["indicator_name"] in CORE_INDICATORS and ind.get("period") == main_period
    ]
    unavail = sum(1 for ind in core_indicators if ind["status"] == "unavailable")
    total = len(core_indicators)
    if total == 0:
        data_status = "insufficient"
    elif unavail / total > 0.5:
        data_status = "insufficient"
    elif unavail / total > 0.2:
        data_status = "partial"
    else:
        data_status = "sufficient"

    if data_status == "insufficient":
        negative_findings = [f for f in negative_findings if f["finding_type"] == "data_limitation"]

    analysis_status = {"insufficient": "failed", "partial": "partial"}.get(data_status, "success")

    analysis_summary = generate_analysis_summary(
        all_indicators, negative_findings, enterprise_name, main_period, data_status)
    if data_status == "insufficient":
        analysis_summary["data_limitation_note"] = "公开财务字段不足，仅能完成有限分析，无法形成完整财务判断。"

    frontend = generate_frontend_summary(all_indicators, fi, main_period)

    confirmed = sum(1 for f in negative_findings if f["finding_type"] == "confirmed_risk")
    warnings_c = sum(1 for f in negative_findings if f["finding_type"] == "warning_signal")
    limitations = sum(1 for f in negative_findings if f["finding_type"] == "data_limitation")
    risk_levels = [f["risk_level"] for f in negative_findings if f["finding_type"] != "data_limitation"]
    highest = "none"
    if "high" in risk_levels:
        highest = "high"
    elif "medium" in risk_levels:
        highest = "medium"
    elif "low" in risk_levels:
        highest = "low"

    unavailable_indicators = [
        {
            "indicator_name": ind["indicator_name"],
            "period": ind.get("period", ""),
            "unavailable_reason": ind.get("unavailable_reason", ""),
            "is_core_indicator": ind["indicator_name"] in CORE_INDICATORS,
        }
        for ind in all_indicators
        if ind["status"] == "unavailable"
    ]

    validation = validate_output(all_indicators, negative_findings, analysis_summary,
                                  frontend, data_status, fi, source_docs)
    validation["warnings"].extend(
        f"非核心指标缺失: {item['indicator_name']}({item['period']})"
        for item in unavailable_indicators
        if not item["is_core_indicator"]
    )

    return {
        "task_id": task_id, "enterprise_name": enterprise_name,
        "analysis_status": analysis_status, "data_status": data_status,
        "main_period": main_period, "periods_analyzed": periods,
        "source_documents": source_docs,
        "financial_indicators": all_indicators,
        "negative_findings": negative_findings,
        "unavailable_indicators": unavailable_indicators,
        "analysis_summary": analysis_summary,
        "frontend_financial_summary": {
            k: round2(v) if isinstance(v, (int, float)) else v
            for k, v in frontend.items()
        },
        "risk_level_summary": {
            "confirmed_risk_count": confirmed,
            "warning_signal_count": warnings_c,
            "data_limitation_count": limitations,
            "highest_risk_level": highest,
        },
        "validation_result": validation,
    }


# ============================================================
# CLI入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="城投/发债企业贷后财务数据分析")
    parser.add_argument("--input", required=True, help="输入JSON文件路径")
    parser.add_argument("--output", required=True, help="输出JSON文件路径")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        input_data = json.load(f)

    result = run_analysis(input_data)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"分析完成: {result['analysis_status']}")
    print(f"数据状态: {result['data_status']}")
    print(f"指标数: {len(result['financial_indicators'])}")
    print(f"风险发现: {len(result['negative_findings'])}")
    print(f"验证: {'通过' if result['validation_result']['passed'] else '失败'}")
    for e in result['validation_result']['errors']:
        print(f"  [ERROR] {e}")
    print(f"输出已保存至: {args.output}")


if __name__ == "__main__":
    main()
