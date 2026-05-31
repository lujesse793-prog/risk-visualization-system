"""
Orchestrator Adapter: Skill 3 – 财务字段提取

封装对 financial_extraction_skill 的调用。
接收 parsed_documents[]，输出 structured_financial_data。

修复要点：
- 嵌套结构修正：_extract_* 返回 {field: {period: cell}}，外层直接合并
- 单位识别：从表头/上下文识别单位（元/千元/万元/亿元），统一转换为标准化单位
- 保留 raw_value, raw_unit, normalized_value, normalized_unit, scale_factor
"""
from __future__ import annotations

import re
from typing import Any

BALANCE_SHEET_FIELDS = [
    "货币资金", "交易性金融资产", "应收账款", "其他应收款", "存货",
    "一年内到期的非流动资产", "流动资产合计", "长期股权投资", "固定资产",
    "在建工程", "无形资产", "非流动资产合计", "资产总计",
    "短期借款", "应付账款", "其他应付款", "一年内到期的非流动负债",
    "流动负债合计", "长期借款", "应付债券", "长期应付款",
    "非流动负债合计", "负债合计", "所有者权益合计",
]

INCOME_STATEMENT_FIELDS = [
    "营业收入", "营业成本", "税金及附加", "销售费用", "管理费用",
    "研发费用", "财务费用", "其他收益", "投资收益", "公允价值变动收益",
    "资产减值损失", "信用减值损失", "营业利润", "利润总额", "净利润",
    "归属于母公司所有者的净利润",
]

CASH_FLOW_FIELDS = [
    "经营活动现金流入小计", "经营活动现金流出小计", "经营活动产生的现金流量净额",
    "投资活动现金流入小计", "投资活动现金流出小计", "投资活动产生的现金流量净额",
    "筹资活动现金流入小计", "筹资活动现金流出小计", "筹资活动产生的现金流量净额",
    "现金及现金等价物净增加额",
]

# 单位映射：识别模式 → scale factor（统一为亿元）
UNIT_PATTERNS = [
    (r"(?:人民币)?\s*亿\s*元?", 1.0),
    (r"(?:人民币)?\s*万\s*元?", 0.0001),
    (r"(?:人民币)?\s*千\s*元?", 0.0000001),
    (r"(?:人民币)?\s*元(?!\s*[万亿千百])", 0.00000001),
    (r"百\s*万\s*元?", 0.01),
]


def _detect_unit(text: str) -> tuple[str, float]:
    """从表头/上下文检测单位，返回 (raw_unit, scale_to_亿)"""
    for pattern, scale in UNIT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return (re.search(pattern, text).group(0), scale)
    return ("万元", 0.0001)  # 默认万元


def _normalize_value(raw_value: str, raw_unit: str) -> dict[str, Any]:
    """标准化数值，保留原始值和转换值"""
    try:
        num = float(raw_value.replace(",", "").replace(" ", "").replace("％", ""))
    except (ValueError, TypeError):
        return {
            "raw_value": raw_value,
            "raw_unit": raw_unit,
            "normalized_value": raw_value,
            "normalized_unit": raw_unit,
            "scale_factor": 1.0,
        }

    # 找到匹配的单位
    scale = 0.0001  # 默认万元→亿
    detected_unit = raw_unit
    for pattern, s in UNIT_PATTERNS:
        if re.search(pattern, raw_unit, re.IGNORECASE):
            scale = s
            detected_unit = re.search(pattern, raw_unit).group(0).strip()
            break

    normalized = num * scale
    return {
        "raw_value": raw_value,
        "raw_unit": detected_unit,
        "normalized_value": f"{normalized:.4f}",
        "normalized_unit": "亿元",
        "scale_factor": scale,
    }


async def run_financial_extraction(
    parsed_documents: list[dict[str, Any]],
    source_documents: list[dict[str, Any]],
    task_id: str,
) -> dict[str, Any]:
    """
    调用 Skill 3: 财务字段提取。
    从 parsed_documents 的 page_texts 和 tables_raw 中提取标准财务字段。
    """
    extracted: dict[str, Any] = {
        "enterprise_name": "",
        "source_document_id": "",
        "extraction_status": "failed",
        "extraction_confidence": "low",
        "data_periods": [],
        "balance_sheet": [],
        "income_statement": [],
        "cash_flow_statement": [],
        "business_segments": [],
        "extraction_warnings": [],
        "missing_fields": [],
    }

    successful_docs = [d for d in parsed_documents if d.get("parse_status") != "failed"]
    if not successful_docs:
        extracted["extraction_warnings"].append("无成功解析的文档，无法提取财务数据")
        return extracted

    all_periods: list[str] = []
    # 结构：{field_name: {period: cell_data}}
    bs_data: dict[str, dict[str, Any]] = {}
    is_data: dict[str, dict[str, Any]] = {}
    cf_data: dict[str, dict[str, Any]] = {}

    for doc in successful_docs:
        doc_id = doc["document_id"]
        # 优先使用 source document 的 report_period，其次用 parsed document 的
        period = doc.get("report_period", "")

        src_doc = _find_source_doc(source_documents, doc_id)
        if src_doc:
            # 用 source document 的 report_period 覆盖（更权威）
            src_period = src_doc.get("report_period", "")
            if src_period:
                period = src_period
            source_title = src_doc.get("title", "")
            source_url = src_doc.get("source_url", "")
        else:
            source_title = ""
            source_url = ""

        if period and period not in all_periods:
            all_periods.append(period)

        # 合并所有页面文本
        page_texts = doc.get("page_texts", {})
        combined_text = "\n".join(page_texts.values()) if page_texts else ""

        # 检测文档单位
        detected_unit, _ = _detect_unit(combined_text[:2000])

        tables = doc.get("tables_raw", [])

        # 提取各类报表字段 —— 返回 {field: {period: cell}}
        for field_map, field_list, storage in [
            (bs_data, BALANCE_SHEET_FIELDS, "bs"),
            (is_data, INCOME_STATEMENT_FIELDS, "is"),
            (cf_data, CASH_FLOW_FIELDS, "cf"),
        ]:
            text_cells = _extract_fields_from_text(
                combined_text, period, source_title, source_url, detected_unit
            )
            table_cells = _extract_fields_from_tables(
                tables, period, source_title, source_url, detected_unit
            )
            merged = {**table_cells, **text_cells}  # tables 优先

            for field_name in field_list:
                if field_name in merged:
                    if field_name not in field_map:
                        field_map[field_name] = {}
                    field_map[field_name][period] = merged[field_name]

    # 组装输出
    missing: list[str] = []
    for statement_name, field_list, storage in [
        ("balance_sheet", BALANCE_SHEET_FIELDS, bs_data),
        ("income_statement", INCOME_STATEMENT_FIELDS, is_data),
        ("cash_flow_statement", CASH_FLOW_FIELDS, cf_data),
    ]:
        result_list = []
        for field_name in field_list:
            if field_name in storage:
                result_list.append({"field_name": field_name, "values": storage[field_name]})
            else:
                result_list.append({"field_name": field_name, "values": {}})
                missing.append(f"{statement_name}: {field_name}")
        extracted[statement_name] = result_list

    extracted["extraction_status"] = "partial" if missing else "success"
    extracted["extraction_confidence"] = "medium" if missing else "high"
    extracted["data_periods"] = all_periods
    extracted["missing_fields"] = missing
    if missing:
        extracted["extraction_warnings"].append(f"缺少 {len(missing)} 个字段")

    if successful_docs:
        extracted["source_document_id"] = successful_docs[0]["document_id"]

    return extracted


def _find_source_doc(source_documents: list[dict[str, Any]], doc_id: str) -> dict[str, Any] | None:
    for doc in source_documents:
        if doc.get("document_id") == doc_id:
            return doc
    return None


def _extract_fields_from_text(
    text: str,
    period: str,
    source_title: str,
    source_url: str,
    detected_unit: str = "万元",
) -> dict[str, Any]:
    """
    从文本中提取财务字段值。
    返回 {field_name: {period: cell_data}}
    """
    all_fields = BALANCE_SHEET_FIELDS + INCOME_STATEMENT_FIELDS + CASH_FLOW_FIELDS
    result: dict[str, Any] = {}

    for field in all_fields:
        pattern = rf"{re.escape(field)}\s*[：:]*\s*(-?[\d,]+\.?\d*)"
        m = re.search(pattern, text)
        if m:
            raw_value = m.group(1).replace(",", "")
            norm = _normalize_value(raw_value, detected_unit)
            result[field] = {
                period: {
                    "value": norm["normalized_value"],
                    "unit": norm["normalized_unit"],
                    "raw_value": norm["raw_value"],
                    "raw_unit": norm["raw_unit"],
                    "scale_factor": norm["scale_factor"],
                    "source_title": source_title,
                    "source_url": source_url,
                    "page": "",
                    "table_name": "",
                    "raw_text": m.group(0),
                }
            }
    return result


def _extract_fields_from_tables(
    tables: list[dict[str, Any]],
    period: str,
    source_title: str,
    source_url: str,
    detected_unit: str = "万元",
) -> dict[str, Any]:
    """
    从表格数据中提取财务字段值。
    返回 {field_name: {period: cell_data}}
    """
    all_fields = BALANCE_SHEET_FIELDS + INCOME_STATEMENT_FIELDS + CASH_FLOW_FIELDS
    result: dict[str, Any] = {}

    for table in tables:
        rows = table.get("rows", [])
        for row in rows:
            if len(row) < 2:
                continue
            row_label = str(row[0]).strip() if row[0] else ""
            for field in all_fields:
                if field in row_label:
                    # 取最后一个非空数值列
                    value_cell = ""
                    for cell in reversed(row[1:]):
                        cleaned = re.sub(r"[^\d.,\-]", "", str(cell)).strip()
                        if cleaned:
                            value_cell = cleaned
                            break
                    if value_cell:
                        norm = _normalize_value(value_cell, detected_unit)
                        result[field] = {
                            period: {
                                "value": norm["normalized_value"],
                                "unit": norm["normalized_unit"],
                                "raw_value": norm["raw_value"],
                                "raw_unit": norm["raw_unit"],
                                "scale_factor": norm["scale_factor"],
                                "source_title": source_title,
                                "source_url": source_url,
                                "page": str(table.get("page", "")),
                                "table_name": table.get("caption", ""),
                                "raw_text": "|".join(str(c) for c in row),
                            }
                        }
    return result
