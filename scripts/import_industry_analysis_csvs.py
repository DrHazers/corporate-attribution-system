from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import backend.models  # noqa: F401
from backend.database import Base, ensure_sqlite_schema, get_database_path
from backend.database_config import get_default_application_database_path
from backend.models.annotation_log import AnnotationLog
from backend.models.business_segment import BusinessSegment
from backend.models.business_segment_classification import BusinessSegmentClassification
from backend.models.company import Company
CSV_FILE_NAMES = {
    "business_segments": "business_segments.csv",
    "business_segment_classifications": "business_segment_classifications.csv",
    "annotation_logs": "annotation_logs.csv",
}
ALLOWED_TARGET_TYPES = {
    "business_segment",
    "business_segment_classification",
}


def configure_csv_field_limit() -> None:
    max_size = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_size)
            return
        except OverflowError:
            max_size //= 10


configure_csv_field_limit()


@dataclass(slots=True)
class ImportStats:
    inserted: int = 0
    skipped_duplicates: int = 0
    skipped_invalid: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "inserted": self.inserted,
            "skipped_duplicates": self.skipped_duplicates,
            "skipped_invalid": self.skipped_invalid,
        }


@dataclass(slots=True)
class ImportSummary:
    database_path: str
    csv_directory: str
    table_stats: dict[str, dict[str, int]]
    validation_passed: bool
    validation_details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": self.database_path,
            "csv_directory": self.csv_directory,
            "table_stats": self.table_stats,
            "validation_passed": self.validation_passed,
            "validation_details": self.validation_details,
        }


def _default_database_path() -> Path:
    env_database_url = os.getenv("DATABASE_URL")
    env_database_path = get_database_path(env_database_url) if env_database_url else None
    if env_database_path is not None:
        return env_database_path
    return get_default_application_database_path()


def _resolve_database_path(database_path: str | None) -> Path:
    if database_path:
        return Path(database_path).expanduser().resolve()
    return _default_database_path().resolve()


def _resolve_csv_directory(csv_directory: str | None) -> Path:
    if csv_directory:
        directory = Path(csv_directory).expanduser().resolve()
    else:
        directory = (PROJECT_ROOT / "_industry_import_tmp").resolve()

    if not directory.exists():
        raise FileNotFoundError(f"CSV directory not found: {directory}")

    missing_files = [
        file_name
        for file_name in CSV_FILE_NAMES.values()
        if not (directory / file_name).exists()
    ]
    if missing_files:
        raise FileNotFoundError(
            f"Missing required CSV files in {directory}: {missing_files}"
        )
    return directory


def _create_session_factory(database_path: Path):
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    raw_connection = engine.raw_connection()
    try:
        ensure_sqlite_schema(raw_connection)
    finally:
        raw_connection.close()
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized == "" or normalized.lower() in {"null", "none"}:
        return None
    return normalized


def _parse_int(value: str | None) -> int | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    return int(normalized)


def _parse_bool(value: str | None) -> bool | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    lowered = normalized.lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise ValueError(f"Unsupported boolean value: {value}")


def _parse_decimal(value: str | None) -> Decimal | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    return Decimal(normalized)


def _parse_datetime(value: str | None) -> datetime | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    return datetime.fromisoformat(normalized)


def _prepare_business_segment(row: dict[str, str]) -> dict[str, Any]:
    return {
        "id": _parse_int(row.get("id")),
        "company_id": _parse_int(row.get("company_id")),
        "segment_name": _normalize_text(row.get("segment_name")),
        "segment_alias": _normalize_text(row.get("segment_alias")),
        "segment_type": _normalize_text(row.get("segment_type")),
        "revenue_ratio": _parse_decimal(row.get("revenue_ratio")),
        "profit_ratio": _parse_decimal(row.get("profit_ratio")),
        "description": _normalize_text(row.get("description")),
        "currency": _normalize_text(row.get("currency")),
        "source": _normalize_text(row.get("source")),
        "reporting_period": _normalize_text(row.get("reporting_period")),
        "is_current": _parse_bool(row.get("is_current")),
        "confidence": _parse_decimal(row.get("confidence")),
        "created_at": _parse_datetime(row.get("created_at")),
        "updated_at": _parse_datetime(row.get("updated_at")),
    }


def _prepare_business_segment_classification(
    row: dict[str, str],
) -> dict[str, Any]:
    return {
        "id": _parse_int(row.get("id")),
        "business_segment_id": _parse_int(row.get("business_segment_id")),
        "standard_system": _normalize_text(row.get("standard_system")),
        "level_1": _normalize_text(row.get("level_1")),
        "level_2": _normalize_text(row.get("level_2")),
        "level_3": _normalize_text(row.get("level_3")),
        "level_4": _normalize_text(row.get("level_4")),
        "is_primary": _parse_bool(row.get("is_primary")),
        "mapping_basis": _normalize_text(row.get("mapping_basis")),
        "review_status": _normalize_text(row.get("review_status")),
        "created_at": _parse_datetime(row.get("created_at")),
        "updated_at": _parse_datetime(row.get("updated_at")),
    }


def _prepare_annotation_log(row: dict[str, str]) -> dict[str, Any]:
    return {
        "id": _parse_int(row.get("id")),
        "target_type": _normalize_text(row.get("target_type")),
        "target_id": _parse_int(row.get("target_id")),
        "action_type": _normalize_text(row.get("action_type")),
        "old_value": _normalize_text(row.get("old_value")),
        "new_value": _normalize_text(row.get("new_value")),
        "reason": _normalize_text(row.get("reason")),
        "operator": _normalize_text(row.get("operator")),
        "created_at": _parse_datetime(row.get("created_at")),
    }


def _validate_business_segment_payload(
    payload: dict[str, Any],
    *,
    company_ids: set[int],
) -> bool:
    return (
        payload["id"] is not None
        and payload["company_id"] in company_ids
        and payload["segment_name"] is not None
        and payload["segment_type"] is not None
        and payload["is_current"] is not None
        and payload["created_at"] is not None
        and payload["updated_at"] is not None
    )


def _validate_business_segment_classification_payload(
    payload: dict[str, Any],
    *,
    business_segment_ids: set[int],
) -> bool:
    return (
        payload["id"] is not None
        and payload["business_segment_id"] in business_segment_ids
        and payload["standard_system"] is not None
        and payload["is_primary"] is not None
        and payload["created_at"] is not None
        and payload["updated_at"] is not None
    )


def _validate_annotation_log_payload(
    payload: dict[str, Any],
    *,
    business_segment_ids: set[int],
    classification_ids: set[int],
) -> bool:
    target_type = payload["target_type"]
    target_id = payload["target_id"]
    if (
        payload["id"] is None
        or target_type not in ALLOWED_TARGET_TYPES
        or target_id is None
        or payload["action_type"] is None
        or payload["created_at"] is None
    ):
        return False

    if target_type == "business_segment":
        return target_id in business_segment_ids
    return target_id in classification_ids


def import_industry_analysis_csvs(
    *,
    database_path: str | None = None,
    csv_directory: str | None = None,
) -> ImportSummary:
    resolved_database_path = _resolve_database_path(database_path)
    resolved_csv_directory = _resolve_csv_directory(csv_directory)

    engine, session_factory = _create_session_factory(resolved_database_path)
    try:
        business_segment_rows = _read_csv_rows(
            resolved_csv_directory / CSV_FILE_NAMES["business_segments"]
        )
        classification_rows = _read_csv_rows(
            resolved_csv_directory / CSV_FILE_NAMES["business_segment_classifications"]
        )
        annotation_rows = _read_csv_rows(
            resolved_csv_directory / CSV_FILE_NAMES["annotation_logs"]
        )

        with session_factory() as read_session:
            company_ids = set(read_session.execute(select(Company.id)).scalars().all())
            existing_segment_ids = set(
                read_session.execute(select(BusinessSegment.id)).scalars().all()
            )
            existing_classification_ids = set(
                read_session.execute(
                    select(BusinessSegmentClassification.id)
                ).scalars().all()
            )
            existing_annotation_ids = set(
                read_session.execute(select(AnnotationLog.id)).scalars().all()
            )

        segment_stats = ImportStats()
        classification_stats = ImportStats()
        annotation_stats = ImportStats()

        inserted_segment_ids: set[int] = set()
        inserted_classification_ids: set[int] = set()
        inserted_annotation_ids: set[int] = set()

        with session_factory() as write_session:
            with write_session.begin():
                for row in business_segment_rows:
                    try:
                        payload = _prepare_business_segment(row)
                    except Exception:
                        segment_stats.skipped_invalid += 1
                        continue

                    row_id = payload["id"]
                    if row_id in existing_segment_ids or row_id in inserted_segment_ids:
                        segment_stats.skipped_duplicates += 1
                        continue

                    if not _validate_business_segment_payload(
                        payload,
                        company_ids=company_ids,
                    ):
                        segment_stats.skipped_invalid += 1
                        continue

                    write_session.add(BusinessSegment(**payload))
                    inserted_segment_ids.add(row_id)
                    segment_stats.inserted += 1

                write_session.flush()
                valid_business_segment_ids = existing_segment_ids | inserted_segment_ids

                for row in classification_rows:
                    try:
                        payload = _prepare_business_segment_classification(row)
                    except Exception:
                        classification_stats.skipped_invalid += 1
                        continue

                    row_id = payload["id"]
                    if (
                        row_id in existing_classification_ids
                        or row_id in inserted_classification_ids
                    ):
                        classification_stats.skipped_duplicates += 1
                        continue

                    if not _validate_business_segment_classification_payload(
                        payload,
                        business_segment_ids=valid_business_segment_ids,
                    ):
                        classification_stats.skipped_invalid += 1
                        continue

                    write_session.add(BusinessSegmentClassification(**payload))
                    inserted_classification_ids.add(row_id)
                    classification_stats.inserted += 1

                write_session.flush()
                valid_classification_ids = (
                    existing_classification_ids | inserted_classification_ids
                )

                for row in annotation_rows:
                    try:
                        payload = _prepare_annotation_log(row)
                    except Exception:
                        annotation_stats.skipped_invalid += 1
                        continue

                    row_id = payload["id"]
                    if row_id in existing_annotation_ids or row_id in inserted_annotation_ids:
                        annotation_stats.skipped_duplicates += 1
                        continue

                    if not _validate_annotation_log_payload(
                        payload,
                        business_segment_ids=valid_business_segment_ids,
                        classification_ids=valid_classification_ids,
                    ):
                        annotation_stats.skipped_invalid += 1
                        continue

                    write_session.add(AnnotationLog(**payload))
                    inserted_annotation_ids.add(row_id)
                    annotation_stats.inserted += 1

        inserted_segment_ids_sorted = sorted(inserted_segment_ids)
        inserted_classification_ids_sorted = sorted(inserted_classification_ids)
        inserted_annotation_ids_sorted = sorted(inserted_annotation_ids)

        with session_factory() as validation_session:
            segment_count_check = (
                validation_session.query(BusinessSegment)
                .filter(BusinessSegment.id.in_(inserted_segment_ids_sorted))
                .count()
                if inserted_segment_ids_sorted
                else 0
            )
            classification_count_check = (
                validation_session.query(BusinessSegmentClassification)
                .filter(
                    BusinessSegmentClassification.id.in_(
                        inserted_classification_ids_sorted
                    )
                )
                .count()
                if inserted_classification_ids_sorted
                else 0
            )
            annotation_count_check = (
                validation_session.query(AnnotationLog)
                .filter(AnnotationLog.id.in_(inserted_annotation_ids_sorted))
                .count()
                if inserted_annotation_ids_sorted
                else 0
            )

            sample_segments = (
                validation_session.query(BusinessSegment.id, BusinessSegment.company_id)
                .filter(BusinessSegment.id.in_(inserted_segment_ids_sorted[:3]))
                .all()
                if inserted_segment_ids_sorted
                else []
            )
            sample_classifications = (
                validation_session.query(
                    BusinessSegmentClassification.id,
                    BusinessSegmentClassification.business_segment_id,
                )
                .filter(
                    BusinessSegmentClassification.id.in_(
                        inserted_classification_ids_sorted[:3]
                    )
                )
                .all()
                if inserted_classification_ids_sorted
                else []
            )
            sample_annotations = (
                validation_session.query(
                    AnnotationLog.id,
                    AnnotationLog.target_type,
                    AnnotationLog.target_id,
                )
                .filter(AnnotationLog.id.in_(inserted_annotation_ids_sorted[:3]))
                .all()
                if inserted_annotation_ids_sorted
                else []
            )

        validation_details = {
            "segment_count_check": segment_count_check,
            "classification_count_check": classification_count_check,
            "annotation_count_check": annotation_count_check,
            "sample_segments": [
                {"id": row.id, "company_id": row.company_id}
                for row in sample_segments
            ],
            "sample_classifications": [
                {"id": row.id, "business_segment_id": row.business_segment_id}
                for row in sample_classifications
            ],
            "sample_annotations": [
                {
                    "id": row.id,
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                }
                for row in sample_annotations
            ],
        }
        validation_passed = (
            segment_count_check == segment_stats.inserted
            and classification_count_check == classification_stats.inserted
            and annotation_count_check == annotation_stats.inserted
        )

        return ImportSummary(
            database_path=str(resolved_database_path),
            csv_directory=str(resolved_csv_directory),
            table_stats={
                "business_segments": segment_stats.to_dict(),
                "business_segment_classifications": classification_stats.to_dict(),
                "annotation_logs": annotation_stats.to_dict(),
            },
            validation_passed=validation_passed,
            validation_details=validation_details,
        )
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import industry-analysis CSVs into the current analysis SQLite database."
    )
    parser.add_argument(
        "--database-path",
        default=None,
        help=(
            "Target SQLite database path. Defaults to DATABASE_URL sqlite path "
            "or the configured application database."
        ),
    )
    parser.add_argument(
        "--csv-directory",
        default=None,
        help="Directory containing business_segments.csv, business_segment_classifications.csv, annotation_logs.csv.",
    )
    args = parser.parse_args(argv)

    summary = import_industry_analysis_csvs(
        database_path=args.database_path,
        csv_directory=args.csv_directory,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
