"""Shared path helpers for the post-loan analysis orchestrator."""
from __future__ import annotations

import os
from pathlib import Path


def find_project_root() -> Path:
    """Return the packaged project root for the orchestrator distribution."""
    env_root = os.getenv("POST_LOAN_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "orchestrator_pkg").is_dir() and (parent / "skills").is_dir():
            return parent
    for parent in current.parents:
        if (parent / "orchestrator_pkg").is_dir():
            return parent
    return current.parents[1]


PROJECT_ROOT = find_project_root()
SKILLS_DIR = PROJECT_ROOT / "skills"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
PDF_DIR = PROJECT_ROOT / "data" / "pdfs"
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


def as_posix_path(path: str | Path) -> str:
    """Serialize paths with POSIX separators for JSON and zip-safe handoffs."""
    return Path(path).resolve().as_posix()
