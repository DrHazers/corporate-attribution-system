from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_DB = PROJECT_ROOT / "ultimate_controller_enhanced_dataset.db"
DEFAULT_TARGET_DB = PROJECT_ROOT / "ultimate_controller_enhanced_dataset_working.db"
DEFAULT_SUMMARY_PATH = (
    PROJECT_ROOT / "logs" / "ultimate_controller_enhanced_dataset_working_clone_summary.json"
)
PROTECTED_TARGET_NAMES = {
    "company_test_analysis_industry.db",
    "company_test_analysis_industry_v2.db",
    "company_test_analysis_industry_export_source.db",
    "large_control_validation_imported_20260418.db",
    "large_control_validation_full_20260418.db",
    "ultimate_controller_test_dataset.db",
    "ultimate_controller_enhanced_dataset.db",
}


def _resolve_project_path(path: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _validate_source(path: Path) -> Path:
    path = _resolve_project_path(path)
    if not path.exists():
        raise FileNotFoundError(f"Source database not found: {path}")
    if path.suffix.lower() != ".db":
        raise ValueError(f"Source database must be a .db file: {path}")
    return path


def _validate_target(path: Path) -> Path:
    path = _resolve_project_path(path)
    if path.name in PROTECTED_TARGET_NAMES:
        raise ValueError(f"Refusing to overwrite protected database name: {path}")
    if path.suffix.lower() != ".db":
        raise ValueError(f"Target database must be a .db file: {path}")
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"Target database must be inside project root: {path}") from exc
    return path


def _file_stat(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size": stat.st_size,
        "modified_at": stat.st_mtime,
        "modified_at_iso": path.stat().st_mtime_ns,
    }


def _file_stat_summary(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size": stat.st_size,
        "modified_at": stat.st_mtime,
        "modified_at_iso": __import__("datetime").datetime.fromtimestamp(
            stat.st_mtime
        ).isoformat(timespec="seconds"),
    }


def clone_database(
    *,
    source_db: Path,
    target_db: Path,
    summary_path: Path,
    overwrite: bool,
) -> dict[str, Any]:
    source_db = _validate_source(source_db)
    target_db = _validate_target(target_db)
    if source_db.resolve() == target_db.resolve():
        raise ValueError("Source and target databases must be different.")

    source_before = _file_stat_summary(source_db)
    if target_db.exists():
        if not overwrite:
            raise FileExistsError(
                f"Target database already exists: {target_db}. Use --overwrite to replace it."
            )
        target_db.unlink()
    target_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_db, target_db)
    target_after = _file_stat_summary(target_db)
    source_after = _file_stat_summary(source_db)

    summary = {
        "source_before_copy": source_before,
        "target_after_copy": target_after,
        "source_after_copy": source_after,
        "source_unchanged_during_clone": (
            source_before["size"] == source_after["size"]
            and source_before["modified_at"] == source_after["modified_at"]
        ),
        "working_database_for_refresh": str(target_db),
    }
    summary_path = _resolve_project_path(summary_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clone the clean enhanced ultimate-controller DB to a working copy."
    )
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--target-db", type=Path, default=DEFAULT_TARGET_DB)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    summary = clone_database(
        source_db=args.source_db,
        target_db=args.target_db,
        summary_path=args.summary,
        overwrite=args.overwrite,
    )
    print(f"source_db: {summary['source_before_copy']['path']}")
    print(f"source_size: {summary['source_before_copy']['size']} bytes")
    print(f"source_modified_at: {summary['source_before_copy']['modified_at_iso']}")
    print(f"working_db: {summary['target_after_copy']['path']}")
    print(f"working_size: {summary['target_after_copy']['size']} bytes")
    print(f"working_modified_at: {summary['target_after_copy']['modified_at_iso']}")
    print(f"source_unchanged_during_clone: {summary['source_unchanged_during_clone']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
