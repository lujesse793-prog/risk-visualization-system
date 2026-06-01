"""Adapter for Skill4 financial analysis."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from ..paths import OUTPUT_DIR, SKILLS_DIR, as_posix_path
from .mock_financial_analysis_adapter import run_mock_financial_analysis


async def run_financial_analysis(
    task_id: str,
    enterprise_name: str,
    extraction_result: dict[str, Any],
    source_documents: list[dict[str, Any]],
    thresholds_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _build_skill4_input(
        task_id=task_id,
        enterprise_name=enterprise_name,
        extraction_result=extraction_result,
        source_documents=source_documents,
        thresholds_config=thresholds_config or {},
    )

    work_dir = OUTPUT_DIR / "orchestrator" / task_id / "skill4_financial_analysis"
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / "input.json"
    output_path = work_dir / "output.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    script_path = SKILLS_DIR / "financial_analysis_skill" / "scripts" / "run_analysis.py"
    if not script_path.exists():
        return await _fallback_mock(payload, f"Skill4 runner not found: {script_path.as_posix()}")

    cmd = [sys.executable, str(script_path), "--input", str(input_path), "--output", str(output_path)]
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
            cwd=str(script_path.parent.parent),
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "Skill4 financial analysis failed").strip())
        if not output_path.exists():
            raise RuntimeError(f"Skill4 did not write output.json: {output_path.as_posix()}")
        result = json.loads(output_path.read_text(encoding="utf-8"))
        result["input_json_path"] = as_posix_path(input_path)
        result["output_json_path"] = as_posix_path(output_path)
        return result
    except Exception as exc:
        return await _fallback_mock(payload, f"Skill4 call failed, fallback mock used: {exc}")


def _build_skill4_input(
    task_id: str,
    enterprise_name: str,
    extraction_result: dict[str, Any],
    source_documents: list[dict[str, Any]],
    thresholds_config: dict[str, Any],
) -> dict[str, Any]:
    periods = extraction_result.get("data_periods", [])
    main_period = periods[0] if periods else _selected_main_period(source_documents)
    return {
        "task_id": task_id,
        "enterprise_name": enterprise_name,
        "analysis_context": {
            "enterprise_type": "城投",
            "analysis_date": date.today().isoformat(),
            "main_report_period": main_period,
            "expected_periods": periods,
        },
        "structured_financial_data": extraction_result.get("structured_financial_data", {}),
        "field_evidence": extraction_result.get("field_evidence", []),
        "extraction_warnings": extraction_result.get("extraction_warnings", []),
        "source_documents": source_documents,
        "thresholds_config": thresholds_config,
    }


def _selected_main_period(source_documents: list[dict[str, Any]]) -> str:
    for doc in source_documents:
        if doc.get("document_status") == "selected_main":
            return doc.get("report_period", "")
    return ""


async def _fallback_mock(payload: dict[str, Any], warning: str) -> dict[str, Any]:
    result = await run_mock_financial_analysis(payload)
    validation = result.setdefault("validation_result", {"passed": True, "errors": [], "warnings": []})
    validation.setdefault("warnings", []).append(warning)
    result["is_mock_analysis"] = True
    return result
