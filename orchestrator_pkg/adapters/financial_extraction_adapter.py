"""Adapter for Skill3 financial extraction."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..paths import OUTPUT_DIR, SKILLS_DIR, as_posix_path


async def run_financial_extraction(
    enterprise_name: str,
    parsed_documents: list[dict[str, Any]],
    source_documents: list[dict[str, Any]],
    task_id: str,
) -> dict[str, Any]:
    work_dir = OUTPUT_DIR / "orchestrator" / task_id / "skill3_financial_extraction"
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / "input.json"
    output_path = work_dir / "output.json"

    payload = {
        "enterprise_name": enterprise_name,
        "source_documents": [_to_skill3_source_document(doc) for doc in source_documents],
        "parsed_documents": parsed_documents,
    }
    input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    script_path = SKILLS_DIR / "financial_extraction_skill" / "scripts" / "run_analysis.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Skill3 runner not found: {script_path.as_posix()}")

    cmd = [sys.executable, str(script_path), "--input", str(input_path), "--output", str(output_path)]
    proc = await asyncio.to_thread(
        subprocess.run,
        cmd,
        capture_output=True,
        text=True,
        timeout=900,
        cwd=str(script_path.parent.parent),
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "Skill3 financial extraction failed").strip())
    if not output_path.exists():
        raise RuntimeError(f"Skill3 did not write output.json: {output_path.as_posix()}")

    result = json.loads(output_path.read_text(encoding="utf-8"))
    result["input_json_path"] = as_posix_path(input_path)
    result["output_json_path"] = as_posix_path(output_path)
    return result


def _to_skill3_source_document(doc: dict[str, Any]) -> dict[str, Any]:
    item = dict(doc)
    item["document_type"] = item.get("document_type") or item.get("file_type", "")
    item["publication_date"] = item.get("publication_date") or item.get("publish_date", "")
    item["is_selected_main"] = item.get("document_status") == "selected_main"
    item["is_selected_supplement"] = item.get("document_status") == "selected_supplement"
    return item
