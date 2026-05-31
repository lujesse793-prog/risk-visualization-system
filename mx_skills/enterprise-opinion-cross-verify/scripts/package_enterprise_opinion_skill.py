from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


SKILL_NAME = "enterprise-opinion-cross-verify"
SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path.home() / "Desktop" / f"{SKILL_NAME}.zip"


def iter_skill_files() -> list[Path]:
    files: list[Path] = []
    for path in SKILL_DIR.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        files.append(path)
    return sorted(files)


def posix_arcname(path: Path) -> str:
    return f"{SKILL_NAME}/{path.relative_to(SKILL_DIR).as_posix()}"


def package_skill(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in iter_skill_files():
            zf.write(path, posix_arcname(path))


def validate_zip(output: Path) -> list[str]:
    required = {
        f"{SKILL_NAME}/SKILL.md",
        f"{SKILL_NAME}/scripts/cross_verify.py",
        f"{SKILL_NAME}/scripts/package_enterprise_opinion_skill.py",
    }
    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()
    errors: list[str] = []
    if any("\\" in name for name in names):
        errors.append("zip contains Windows-style backslash paths")
    missing = sorted(required - set(names))
    if missing:
        errors.append("zip is missing required entries: " + ", ".join(missing))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Package enterprise opinion skill with POSIX zip paths.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="validate an existing zip instead of writing it")
    args = parser.parse_args()

    if args.check:
        errors = validate_zip(args.output)
    else:
        package_skill(args.output)
        errors = validate_zip(args.output)

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    with zipfile.ZipFile(args.output) as zf:
        for name in zf.namelist():
            print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
