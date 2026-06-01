"""Adapter for Skill2 PDF parsing.

The adapter only converts Skill1's handoff into Skill2 input, invokes the
Skill2 runner, and returns the runner's JSON output.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..paths import OUTPUT_DIR, SKILLS_DIR, as_posix_path


async def run_pdf_parse(
    pdf_handoff: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    documents = pdf_handoff.get("documents_needing_pdf_parse", [])
    if not isinstance(documents, list):
        documents = []

    work_dir = OUTPUT_DIR / "orchestrator" / task_id / "skill2_pdf_parse"
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / "input.json"
    output_path = work_dir / "output.json"

    payload = {
        "task_id": task_id,
        "enterprise_name": pdf_handoff.get("enterprise_name", ""),
        "documents_to_parse": [_to_skill2_document(doc) for doc in documents],
        "output_dir": as_posix_path(work_dir / "parsed"),
    }
    input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if not payload["documents_to_parse"]:
        result = {
            "status": "success",
            "parsed_documents": [],
            "failed_documents": [],
            "parse_summary": {"total": 0, "success": 0, "partial": 0, "failed": 0},
            "input_json_path": as_posix_path(input_path),
            "output_json_path": as_posix_path(output_path),
        }
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    script_path = _skill2_script_path()
    if not script_path.exists():
        raise FileNotFoundError(f"Skill2 runner not found: {script_path.as_posix()}")

    query = json.dumps(payload, ensure_ascii=False)
    cmd = [
        sys.executable,
        str(script_path),
        "--query",
        query,
        "--output-dir",
        payload["output_dir"],
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    proc = await asyncio.to_thread(
        subprocess.run,
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        cwd=str(script_path.parent.parent),
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "Skill2 PDF parse failed").strip())

    result = _read_json_from_stdout(proc.stdout)
    result.setdefault("parsed_documents", [])
    result.setdefault("failed_documents", [])
    result.setdefault("parse_summary", _parse_summary(result["parsed_documents"], result["failed_documents"]))
    result["input_json_path"] = as_posix_path(input_path)
    result["output_json_path"] = as_posix_path(output_path)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _skill2_script_path() -> Path:
    return SKILLS_DIR / "pdf_parse_skill" / "scripts" / "run_pdf_parse.py"


def _to_skill2_document(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": doc.get("document_id", ""),
        "file_type": doc.get("file_type", ""),
        "report_period": doc.get("report_period", ""),
        "title": doc.get("title", ""),
        "local_pdf_path": doc.get("local_pdf_path", ""),
        "pdf_url": doc.get("pdf_url", ""),
        "pdf_sha256": doc.get("pdf_sha256", ""),
        "source_url": doc.get("source_url", ""),
        "publish_date": doc.get("publish_date", ""),
        "source_platform": doc.get("source_platform", ""),
    }


def _read_json_from_stdout(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise RuntimeError("Skill2 did not print JSON output")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _parse_summary(parsed_documents: list[dict[str, Any]], failed_documents: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(parsed_documents),
        "success": sum(1 for doc in parsed_documents if doc.get("parse_status") == "success"),
        "partial": sum(1 for doc in parsed_documents if doc.get("parse_status") == "partial"),
        "failed": len(failed_documents),
    }
