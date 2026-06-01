from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_analysis import extract  # noqa: E402

RUNNER = ROOT / "scripts" / "run_analysis.py"
VALIDATOR = ROOT / "scripts" / "validate_output.py"


def run_skill(_tmp_path: Path, payload: dict) -> dict:
    return extract(payload)


def run_skill_cli(tmp_path: Path, payload: dict) -> dict:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--input", str(input_path), "--output", str(output_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(output_path.read_text(encoding="utf-8"))


def base_payload(tables: list[dict], page_texts: dict[str, str] | None = None, report_period: str = "2025") -> dict:
    page_texts = page_texts or {"88": "单位：万元", "89": "单位：万元", "90": "单位：万元"}
    return {
        "enterprise_name": "测试公司",
        "source_documents": [
            {
                "document_id": "doc_001",
                "document_type": "annual_report",
                "report_period": report_period,
                "publication_date": "2026-04-30",
                "source_url": "",
                "pdf_url": "",
                "pdf_sha256": "",
                "is_selected_main": True,
                "is_selected_supplement": False,
            }
        ],
        "parsed_documents": [
            {
                "document_id": "doc_001",
                "document_type": "annual_report",
                "report_period": report_period,
                "parser_used": "marker",
                "ocr_used": False,
                "page_count": 120,
                "page_texts": page_texts,
                "tables_raw": tables,
                "parse_status": "success",
                "parse_confidence": "high",
                "parse_warnings": [],
            }
        ],
    }


def fields(output: dict, statement: str) -> dict[tuple[str, str], dict]:
    rows = output["structured_financial_data"]["financial_tables"][statement]
    return {(row["standard_field_name"], row["period"]): row for row in rows}


def warnings_of(output: dict, warning_type: str) -> list[dict]:
    return [item for item in output["extraction_warnings"] if item.get("warning_type") == warning_type]


def test_extracts_balance_sheet_core_fields(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_bs",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [
                        ["项目", "2025年末", "2024年末"],
                        ["货币资金", "123,456.78", "100000.00"],
                        ["资产总计", "999999.99", "888888.88"],
                        ["负债合计", "600000.00", "500000.00"],
                    ],
                }
            ]
        ),
    )
    bs = fields(output, "balance_sheet")
    assert bs[("total_assets", "2025")]["value"] == 999999.99
    assert bs[("total_liabilities", "2025")]["value"] == 600000.00
    assert bs[("cash_and_cash_equivalents", "2025")]["value"] == 123456.78


def test_detects_wan_yuan_unit(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_bs",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [["项目", "2025年末"], ["资产总计", "999999.99"]],
                }
            ]
        ),
    )
    assert fields(output, "balance_sheet")[("total_assets", "2025")]["unit"] == "万元"


def test_extracts_income_statement_fields(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_is",
                    "page": 89,
                    "table_title": "合并利润表",
                    "rows": [["项目", "2025年度"], ["营业收入", "1000"], ["净利润", "90"]],
                }
            ]
        ),
    )
    income = fields(output, "income_statement")
    assert income[("operating_revenue", "2025")]["value"] == 1000
    assert income[("net_profit", "2025")]["value"] == 90


def test_extracts_cash_flow_statement_field(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_cf",
                    "page": 90,
                    "table_title": "合并现金流量表",
                    "rows": [["项目", "2025年度"], ["经营活动产生的现金流量净额", "321"]],
                }
            ]
        ),
    )
    assert fields(output, "cash_flow_statement")[("net_cash_flow_from_operating_activities", "2025")]["value"] == 321


def test_parses_parentheses_as_negative(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_is",
                    "page": 89,
                    "table_title": "合并利润表",
                    "rows": [["项目", "2025年度"], ["净利润", "（123.45）"]],
                }
            ]
        ),
    )
    assert fields(output, "income_statement")[("net_profit", "2025")]["value"] == -123.45


def test_prefers_consolidated_over_parent_company(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_parent",
                    "page": 80,
                    "table_title": "母公司资产负债表",
                    "rows": [["项目", "2025年末"], ["资产总计", "1"]],
                },
                {
                    "table_id": "tbl_con",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [["项目", "2025年末"], ["资产总计", "2"]],
                },
            ]
        ),
    )
    row = fields(output, "balance_sheet")[("total_assets", "2025")]
    assert row["value"] == 2
    assert row["table_id"] == "tbl_con"


def test_ignores_note_tables_as_primary(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_note",
                    "page": 120,
                    "table_title": "资产负债表附注明细",
                    "rows": [["项目", "2025年末"], ["资产总计", "999"]],
                },
                {
                    "table_id": "tbl_bs",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [["项目", "2025年末"], ["资产总计", "100"]],
                },
            ]
        ),
    )
    row = fields(output, "balance_sheet")[("total_assets", "2025")]
    assert row["value"] == 100
    assert row["table_id"] == "tbl_bs"


def test_missing_fields_are_reported(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_bs",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [["项目", "2025年末"], ["资产总计", "100"]],
                }
            ]
        ),
    )
    assert "cash_and_cash_equivalents" in {item["standard_field_name"] for item in output["missing_fields"]}


def test_source_conflict_warning(tmp_path: Path) -> None:
    payload = base_payload(
        [
            {
                "table_id": "tbl_bs",
                "page": 88,
                "table_title": "合并资产负债表",
                "rows": [["项目", "2025年末"], ["资产总计", "100"]],
            }
        ]
    )
    payload["source_documents"].append(
        {
            "document_id": "doc_002",
            "document_type": "rating_report",
            "report_period": "2025",
            "publication_date": "2026-01-01",
            "source_url": "",
            "pdf_url": "",
            "pdf_sha256": "",
            "is_selected_main": False,
            "is_selected_supplement": True,
        }
    )
    payload["parsed_documents"].append(
        {
            "document_id": "doc_002",
            "document_type": "rating_report",
            "report_period": "2025",
            "parser_used": "marker",
            "ocr_used": False,
            "page_count": 20,
            "page_texts": {"15": "单位：万元"},
            "tables_raw": [
                {
                    "table_id": "tbl_summary",
                    "page": 15,
                    "table_title": "合并资产负债表",
                    "rows": [["项目", "2025年末"], ["资产总计", "90"]],
                }
            ],
            "parse_status": "success",
            "parse_confidence": "high",
            "parse_warnings": [],
        }
    )
    output = run_skill(tmp_path, payload)
    assert fields(output, "balance_sheet")[("total_assets", "2025")]["value"] == 100
    assert warnings_of(output, "source_conflict")


def test_annual_report_beats_later_rating_report_for_same_field(tmp_path: Path) -> None:
    payload = base_payload(
        [
            {
                "table_id": "tbl_annual_bs",
                "page": 88,
                "table_title": "合并资产负债表",
                "rows": [["项目", "2025年末"], ["资产总计", "100"]],
            }
        ]
    )
    payload["source_documents"].append(
        {
            "document_id": "doc_rating",
            "document_type": "rating_report",
            "report_period": "2025",
            "publication_date": "2026-06-01",
            "source_url": "",
            "pdf_url": "",
            "pdf_sha256": "",
            "is_selected_main": False,
            "is_selected_supplement": True,
        }
    )
    payload["parsed_documents"].append(
        {
            "document_id": "doc_rating",
            "document_type": "rating_report",
            "report_period": "2025",
            "parser_used": "marker",
            "ocr_used": False,
            "page_count": 10,
            "page_texts": {"5": "单位：万元"},
            "tables_raw": [
                {
                    "table_id": "tbl_rating_summary",
                    "page": 5,
                    "table_title": "合并资产负债表",
                    "rows": [["项目", "2025年末"], ["资产总计", "90"]],
                }
            ],
            "parse_status": "success",
            "parse_confidence": "high",
            "parse_warnings": [],
        }
    )
    output = run_skill(tmp_path, payload)
    assert fields(output, "balance_sheet")[("total_assets", "2025")]["value"] == 100
    conflict = warnings_of(output, "source_conflict")
    assert conflict
    assert conflict[0]["severity"] == "important"


def test_title_unit_rows_and_late_header_are_handled(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_bs",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [
                        ["合并资产负债表", "", ""],
                        ["单位：万元", "", ""],
                        ["项目", "附注", "2025年末"],
                        ["流动资产：", "", ""],
                        ["货币资金", "六、1", "123"],
                        ["资产总计", "六、2", "999"],
                    ],
                }
            ]
        ),
    )
    bs = fields(output, "balance_sheet")
    assert bs[("cash_and_cash_equivalents", "2025")]["value"] == 123
    assert bs[("cash_and_cash_equivalents", "2025")]["raw_column"] == "2025年末"


def test_date_headers_are_periods(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_bs",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [["项目", "2025年12月31日", "2024年12月31日"], ["资产总计", "999", "888"]],
                }
            ]
        ),
    )
    bs = fields(output, "balance_sheet")
    assert bs[("total_assets", "2025")]["value"] == 999
    assert bs[("total_assets", "2024")]["value"] == 888


def test_period_end_and_beginning_headers(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_bs",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [["项目", "期末余额", "期初余额"], ["资产总计", "999", "888"]],
                }
            ]
        ),
    )
    bs = fields(output, "balance_sheet")
    assert bs[("total_assets", "2025")]["value"] == 999
    assert bs[("total_assets", "2024")]["value"] == 888


def test_income_current_and_prior_amount_headers(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_is",
                    "page": 89,
                    "table_title": "合并利润表",
                    "rows": [["项目", "本期金额", "上期金额"], ["营业收入", "1000", "800"]],
                }
            ]
        ),
    )
    income = fields(output, "income_statement")
    assert income[("operating_revenue", "2025")]["value"] == 1000
    assert income[("operating_revenue", "2024")]["value"] == 800


def test_missing_unit_uses_unknown_and_warning(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_bs",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [["项目", "2025年末"], ["资产总计", "999"]],
                }
            ],
            page_texts={"88": "无单位信息"},
        ),
    )
    row = fields(output, "balance_sheet")[("total_assets", "2025")]
    assert row["unit"] == "unknown"
    assert row["confidence"] == "low"
    assert warnings_of(output, "unit_uncertain")


def test_page_texts_fallback_extracts_with_lower_confidence(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [],
            page_texts={
                "88": "合并资产负债表\n单位：万元\n项目  2025年末\n资产总计  999\n货币资金  123",
                "89": "合并利润表\n单位：万元\n项目  本期金额\n营业收入  1000\n净利润  90",
                "90": "合并现金流量表\n单位：万元\n项目  本期金额\n经营活动产生的现金流量净额  321",
            },
        ),
    )
    assert fields(output, "balance_sheet")[("total_assets", "2025")]["confidence"] == "medium"
    assert fields(output, "income_statement")[("operating_revenue", "2025")]["value"] == 1000
    assert fields(output, "cash_flow_statement")[("net_cash_flow_from_operating_activities", "2025")]["value"] == 321
    assert warnings_of(output, "text_fallback_used")
    assert warnings_of(output, "no_tables_raw")


def test_parent_company_only_warning(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_parent",
                    "page": 80,
                    "table_title": "母公司资产负债表",
                    "rows": [["项目", "2025年末"], ["资产总计", "1"]],
                }
            ]
        ),
    )
    assert fields(output, "balance_sheet")[("total_assets", "2025")]["value"] == 1
    assert warnings_of(output, "parent_company_only")


def test_stale_data_warning_and_not_success(tmp_path: Path) -> None:
    payload = base_payload(
        [
            {
                "table_id": "tbl_bs",
                "page": 88,
                "table_title": "合并资产负债表",
                "rows": [["项目", "2024年末"], ["资产总计", "999"]],
            }
        ],
        report_period="2024",
    )
    payload["latest_acceptable_period"] = "2025"
    output = run_skill(tmp_path, payload)
    assert warnings_of(output, "stale_financial_data")
    assert output["extraction_status"] != "success"


def test_field_aliases_map_correctly(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_bs",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [
                        ["项目", "2025年末"],
                        ["股东权益合计", "400"],
                        ["归属于母公司股东权益合计", "350"],
                        ["应付债券合计", "60"],
                        ["货币资金余额", "50"],
                        ["短期债务", "30"],
                        ["长期债务", "70"],
                    ],
                },
                {
                    "table_id": "tbl_is",
                    "page": 89,
                    "table_title": "合并利润表",
                    "rows": [["项目", "2025年度"], ["营业总收入", "1000"], ["归属于母公司股东的净利润", "80"]],
                },
                {
                    "table_id": "tbl_cf",
                    "page": 90,
                    "table_title": "合并现金流量表",
                    "rows": [["项目", "2025年度"], ["经营活动现金净流量", "321"], ["现金及现金等价物期末余额", "120"]],
                },
            ]
        ),
    )
    bs = fields(output, "balance_sheet")
    income = fields(output, "income_statement")
    cf = fields(output, "cash_flow_statement")
    assert bs[("total_owner_equity", "2025")]["value"] == 400
    assert bs[("equity_attributable_to_parent", "2025")]["value"] == 350
    assert bs[("bonds_payable", "2025")]["value"] == 60
    assert bs[("cash_and_cash_equivalents", "2025")]["value"] == 50
    assert bs[("short_term_borrowings", "2025")]["value"] == 30
    assert bs[("long_term_borrowings", "2025")]["value"] == 70
    assert income[("operating_revenue", "2025")]["value"] == 1000
    assert income[("net_profit_attributable_to_parent", "2025")]["value"] == 80
    assert cf[("net_cash_flow_from_operating_activities", "2025")]["value"] == 321
    assert cf[("cash_and_cash_equivalents_at_end", "2025")]["value"] == 120


def test_simple_ocr_split_row_is_merged(tmp_path: Path) -> None:
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_bs",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [["项目", "2025年末"], ["资产总计", ""], ["999"]],
                }
            ]
        ),
    )
    assert fields(output, "balance_sheet")[("total_assets", "2025")]["value"] == 999


def test_selected_main_document_uses_type_period_and_publication_date(tmp_path: Path) -> None:
    payload = base_payload([])
    payload["source_documents"] = [
        {"document_id": "old_annual", "document_type": "annual_report", "report_period": "2024", "publication_date": "2025-04-30"},
        {"document_id": "new_annual", "document_type": "annual_report", "report_period": "2025", "publication_date": "2026-04-30"},
        {"document_id": "new_quarter", "document_type": "quarterly_report", "report_period": "2026Q1", "publication_date": "2026-05-01"},
    ]
    output = run_skill(tmp_path, payload)
    assert output["selected_main_document_id"] == "new_annual"


def test_cli_entrypoint_writes_output_json(tmp_path: Path) -> None:
    output = run_skill_cli(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_bs",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [["项目", "2025年末"], ["资产总计", "100"]],
                }
            ]
        ),
    )
    assert output["enterprise_name"] == "测试公司"
    assert fields(output, "balance_sheet")[("total_assets", "2025")]["value"] == 100


def test_output_passes_validator(tmp_path: Path) -> None:
    output_path = tmp_path / "output.json"
    output = run_skill(
        tmp_path,
        base_payload(
            [
                {
                    "table_id": "tbl_bs",
                    "page": 88,
                    "table_title": "合并资产负债表",
                    "rows": [["项目", "2025年末"], ["资产总计", "100"]],
                }
            ]
        ),
    )
    output_path.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--input", str(output_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output["validation_result"]["passed"] is True
