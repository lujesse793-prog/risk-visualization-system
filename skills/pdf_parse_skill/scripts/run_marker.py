import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_REPO = Path(os.environ.get("MARKER_REPO", r"C:\Users\user\Documents\marker"))


def _parse_query(query: str) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return {}
    if query.startswith("{"):
        return json.loads(query)
    return {"input_path": query}


def _find_cli() -> str | None:
    return shutil.which("marker_single") or shutil.which("marker")


def _dependency_message() -> dict[str, Any]:
    return {
        "status": "error",
        "error": "Marker is downloaded but not installed in the active Python environment.",
        "repo_path": str(DEFAULT_REPO),
        "install_hint": [
            "Install from the local repo before parsing documents:",
            rf"cd /d {DEFAULT_REPO}",
            "pip install -e .",
        ],
    }


async def run_marker(query: str, output_dir: str | Path | None = None, **_: Any) -> dict[str, Any]:
    params = _parse_query(query)
    input_path = params.get("input_path") or params.get("path") or params.get("file")
    out_dir = Path(params.get("output_dir") or output_dir or Path.cwd() / "marker_output")
    out_dir.mkdir(parents=True, exist_ok=True)

    cli = _find_cli()
    if not cli:
        result = _dependency_message()
        result["requested_input"] = input_path or ""
        return result

    if not input_path:
        return {
            "status": "error",
            "error": "input_path is required.",
            "repo_path": str(DEFAULT_REPO),
        }

    source = Path(input_path).expanduser()
    if not source.exists():
        return {"status": "error", "error": f"Input file not found: {source}"}

    cmd = [cli, str(source), "--output_dir", str(out_dir)]
    proc = await asyncio.to_thread(
        subprocess.run,
        cmd,
        capture_output=True,
        text=True,
        cwd=str(DEFAULT_REPO) if DEFAULT_REPO.exists() else None,
    )
    files = [str(p) for p in out_dir.rglob("*") if p.is_file()]
    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "files": files,
        "repo_path": str(DEFAULT_REPO),
    }


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    result = await run_marker(args.query, output_dir=args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
