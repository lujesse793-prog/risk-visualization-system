#!/usr/bin/env python
"""Validate financial_extraction_skill output JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


STATEMENTS = ("balance_sheet", "income_statement", "cash_flow_statement")
VALID_UNITS = {"元", "千元", "万元", "亿元", "unknown"}
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
REQUIRED_FIELD_KEYS = (
    "field_name",
    "standard_field_name",
    "statement_type",
    "period",
    "period_type",
    "value",
    "unit",
    "source_document_id",
    "source_document_type",
    "source_pdf",
    "page",
    "table_id",
    "table_title",
    "raw_row",
    "raw_column",
    "evidence_text",
    "confidence",
)
REQUIRED_EVIDENCE_KEYS = (
    "evidence_id",
    "standard_field_name",
    "field_name",
    "period",
    "value",
    "unit",
    "source_document_id",
    "source_document_type",
    "page",
    "table_id",
    "table_title",
    "raw_row",
    "raw_column",
    "evidence_text",
    "confidence",
)


def validate_output(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("extraction_status") not in {"success", "partial", "failed"}:
        errors.append("extraction_status must be success, partial, or failed")

    tables = data.get("structured_financial_data", {}).get("financial_tables", {})
    for statement in STATEMENTS:
        if not isinstance(tables.get(statement), list):
            errors.append(f"structured_financial_data.financial_tables.{statement} must be an array")

    evidence = data.get("field_evidence", [])
    if not isinstance(evidence, list):
        errors.append("field_evidence must be an array")
        evidence = []

    evidence_keys = {
        (
            item.get("standard_field_name"),
            item.get("period"),
            item.get("source_document_id"),
            item.get("page"),
            item.get("table_id"),
            item.get("raw_row"),
            item.get("raw_column"),
        )
        for item in evidence
        if isinstance(item, dict)
    }
    extraction_warnings = data.get("extraction_warnings", [])
    if not isinstance(extraction_warnings, list):
        extraction_warnings = []
    unit_uncertain_keys = {
        (
            item.get("standard_field_name"),
            item.get("period"),
            item.get("source_document_id"),
            item.get("page"),
        )
        for item in extraction_warnings
        if isinstance(item, dict) and item.get("warning_type") == "unit_uncertain"
    }

    extracted_count = 0
    success_statement_key_presence = {statement: set() for statement in STATEMENTS}
    success_unknown_key_units: list[str] = []
    for statement in STATEMENTS:
        rows = tables.get(statement, [])
        if not isinstance(rows, list):
            continue
        for idx, field in enumerate(rows):
            extracted_count += 1
            if not isinstance(field, dict):
                errors.append(f"{statement}[{idx}] must be an object")
                continue
            for key in REQUIRED_FIELD_KEYS:
                if key not in field or field.get(key) in (None, ""):
                    if key == "value" and field.get(key) == 0:
                        continue
                    if key == "source_pdf" and key in field:
                        continue
                    errors.append(f"{statement}[{idx}] missing {key}")
            if field.get("statement_type") != statement:
                errors.append(f"{statement}[{idx}] statement_type mismatch")
            if field.get("unit") not in VALID_UNITS:
                errors.append(f"{statement}[{idx}] unit must be one of 元, 千元, 万元, 亿元, unknown")
            if field.get("unit") == "unknown":
                warning_key = (
                    field.get("standard_field_name"),
                    field.get("period"),
                    field.get("source_document_id"),
                    field.get("page"),
                )
                if warning_key not in unit_uncertain_keys:
                    errors.append(f"{statement}[{idx}] unit=unknown without unit_uncertain warning")
                if field.get("standard_field_name") in KEY_FIELDS:
                    success_unknown_key_units.append(field.get("standard_field_name"))
            if field.get("standard_field_name") in KEY_FIELDS:
                success_statement_key_presence[statement].add(field.get("standard_field_name"))
            trace_key = (
                field.get("standard_field_name"),
                field.get("period"),
                field.get("source_document_id"),
                field.get("page"),
                field.get("table_id"),
                field.get("raw_row"),
                field.get("raw_column"),
            )
            if trace_key not in evidence_keys:
                errors.append(f"{statement}[{idx}] has no traceable field_evidence entry")

    for idx, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"field_evidence[{idx}] must be an object")
            continue
        for key in REQUIRED_EVIDENCE_KEYS:
            if key not in item or item.get(key) in (None, ""):
                if key == "value" and item.get(key) == 0:
                    continue
                errors.append(f"field_evidence[{idx}] missing {key}")

    if data.get("extraction_status") == "success":
        standards = set().union(*success_statement_key_presence.values())
        missing = sorted(KEY_FIELDS - standards)
        if missing:
            errors.append("success status is invalid because key fields are missing: " + ", ".join(missing))
        missing_statements = [statement for statement, fields in success_statement_key_presence.items() if not fields]
        if missing_statements:
            errors.append("success status requires key fields in all three statements: " + ", ".join(missing_statements))
        if success_unknown_key_units:
            errors.append("success status cannot include key fields with unit=unknown: " + ", ".join(sorted(set(success_unknown_key_units))))

    if extracted_count == 0 and data.get("extraction_status") != "failed":
        errors.append("outputs with no extracted fields must use failed status")

    if data.get("missing_fields") is None or not isinstance(data.get("missing_fields"), list):
        errors.append("missing_fields must be an array")
    if data.get("extraction_warnings") is None or not isinstance(data.get("extraction_warnings"), list):
        errors.append("extraction_warnings must be an array")

    return {"passed": not errors, "errors": errors, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    path = Path(args.input)
    data = json.loads(path.read_text(encoding="utf-8"))
    result = validate_output(data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
