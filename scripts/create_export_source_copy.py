from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = BASE_DIR / "company_test_analysis_industry.db"
DEFAULT_TARGET = BASE_DIR / "company_test_analysis_industry_export_source.db"
EXPECTED_SOURCE_NAME = "company_test_analysis_industry.db"
EXPECTED_TARGET_NAME = "company_test_analysis_industry_export_source.db"


def _format_file_status(path: Path) -> str:
    if not path.exists():
        return f"{path} | exists=False"
    stat = path.stat()
    modified_at = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
    return (
        f"{path} | exists=True | size={stat.st_size} bytes | "
        f"modified_at={modified_at}"
    )


def _validate_paths(source: Path, target: Path) -> tuple[Path, Path]:
    source = source.resolve()
    target = target.resolve()
    if source.name != EXPECTED_SOURCE_NAME:
        raise ValueError(
            f"Refusing to use unexpected source database: {source.name}. "
            f"Expected {EXPECTED_SOURCE_NAME}."
        )
    if target.name != EXPECTED_TARGET_NAME:
        raise ValueError(
            f"Refusing to write unexpected target database: {target.name}. "
            f"Expected {EXPECTED_TARGET_NAME}."
        )
    if source == target:
        raise ValueError("Source and target database paths must be different.")
    if not source.exists():
        raise FileNotFoundError(f"Source database not found: {source}")
    return source, target


def create_export_source_copy(source: Path, target: Path) -> dict:
    source, target = _validate_paths(source, target)

    print("[before-copy] source:")
    print(f"  {_format_file_status(source)}")
    print("[before-copy] target:")
    print(f"  {_format_file_status(target)}")

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    shutil.copy2(source, target)

    print("[after-copy] target:")
    print(f"  {_format_file_status(target)}")

    return {
        "source": str(source),
        "target": str(target),
        "target_exists": target.exists(),
        "target_size": target.stat().st_size if target.exists() else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create the only database copy allowed for CSV handoff export. "
            "The original database is never modified."
        )
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()

    result = create_export_source_copy(args.source, args.target)
    print("[summary]")
    print(f"  source={result['source']}")
    print(f"  target={result['target']}")
    print(f"  target_exists={result['target_exists']}")
    print(f"  target_size={result['target_size']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
