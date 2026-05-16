from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, text
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CSV_PATH = (
    PROJECT_ROOT
    / "data"
    / "final_enhanced_input_tables_csv"
    / "industry_refresh"
    / "new_business_segments.csv"
)
REPORT_PATH = PROJECT_ROOT / "export" / "industry_refresh_report.md"
SUMMARY_PATH = PROJECT_ROOT / "logs" / "industry_refresh_import_summary.json"
FINAL_SUMMARY_PATH = PROJECT_ROOT / "logs" / "industry_refresh_summary.json"
TABLE_NAME = "business_segments"
CLASSIFICATION_TABLE_NAME = "business_segment_classifications"
PROTECTED_TABLES = [
    "companies",
    "shareholder_entities",
    "shareholder_structures",
    "relationship_sources",
    "entity_aliases",
    "control_relationships",
    "country_attributions",
    "control_inference_runs",
    "control_inference_audit_log",
    "manual_control_overrides",
    "shareholder_structure_history",
]
TRUTHY = {"1", "1.0", "t", "true", "yes", "y", "on"}
FALSY = {"0", "0.0", "f", "false", "no", "n", "off"}


def raise_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def require_database_url() -> str:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required. Refusing to default to SQLite.")
    if make_url(database_url).get_backend_name() != "postgresql":
        raise SystemExit(
            "DATABASE_URL must point to PostgreSQL, got: "
            f"{render_database_url(database_url)}"
        )
    return database_url


def render_database_url(database_url: str) -> str:
    return make_url(database_url).render_as_string(hide_password=True)


def create_database_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


def load_metadata():
    import backend.models  # noqa: F401
    from backend.database import Base

    return Base


def quote_table(connection: Connection, table_name: str) -> str:
    return connection.dialect.identifier_preparer.quote(table_name)


def table_count(connection: Connection, table_name: str) -> int:
    return int(
        connection.execute(
            text(f"SELECT COUNT(*) FROM {quote_table(connection, table_name)}")
        ).scalar_one()
    )


def table_columns(connection: Connection, table_name: str) -> list[str]:
    rows = connection.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
            ORDER BY ordinal_position
            """
        ),
        {"table_name": table_name},
    ).fetchall()
    return [str(row[0]) for row in rows]


def conversion_error(
    *,
    table_name: str,
    column_name: str,
    value: str | None,
    expected_type: str,
) -> ValueError:
    return ValueError(
        f"Invalid {expected_type} value for {table_name}.{column_name}: {value!r}"
    )


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def coerce_integer(value: str, *, column_name: str, original_value: str | None) -> int:
    try:
        return int(value)
    except ValueError:
        pass
    try:
        numeric = float(value)
    except ValueError as exc:
        raise conversion_error(
            table_name=TABLE_NAME,
            column_name=column_name,
            value=original_value,
            expected_type="integer",
        ) from exc
    if not numeric.is_integer():
        raise conversion_error(
            table_name=TABLE_NAME,
            column_name=column_name,
            value=original_value,
            expected_type="integer",
        )
    return int(numeric)


def coerce_boolean(value: str, *, column_name: str, original_value: str | None) -> bool:
    lowered = value.lower()
    if lowered in TRUTHY:
        return True
    if lowered in FALSY:
        return False
    raise conversion_error(
        table_name=TABLE_NAME,
        column_name=column_name,
        value=original_value,
        expected_type="boolean",
    )


def coerce_value(value: str | None, column, *, table_name: str = TABLE_NAME) -> Any:
    original_value = value
    value = clean_text(value)
    if value is None:
        return None

    column_type = column.type
    if isinstance(column_type, Boolean):
        return coerce_boolean(value, column_name=column.name, original_value=original_value)
    if isinstance(column_type, Integer):
        return coerce_integer(value, column_name=column.name, original_value=original_value)
    if isinstance(column_type, Numeric):
        try:
            return Decimal(value)
        except Exception as exc:
            raise conversion_error(
                table_name=table_name,
                column_name=column.name,
                value=original_value,
                expected_type="numeric",
            ) from exc
    if isinstance(column_type, DateTime):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise conversion_error(
                table_name=table_name,
                column_name=column.name,
                value=original_value,
                expected_type="datetime",
            ) from exc
    if isinstance(column_type, Date):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise conversion_error(
                table_name=table_name,
                column_name=column.name,
                value=original_value,
                expected_type="date",
            ) from exc
    return value


def has_insert_default(column) -> bool:
    return column.default is not None or column.server_default is not None or column.autoincrement


def read_business_segment_csv(csv_path: Path, table) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    raise_csv_field_limit()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file has no header row: {csv_path}")

        csv_columns = [name for name in reader.fieldnames if name]
        table_column_names = set(table.c.keys())
        unknown_columns = sorted(set(csv_columns) - table_column_names)
        if unknown_columns:
            raise ValueError(
                "CSV contains columns not present in business_segments: "
                + ", ".join(unknown_columns)
            )

        missing_columns = [
            column.name for column in table.c if column.name not in csv_columns
        ]
        required_missing = [
            column.name
            for column in table.c
            if column.name not in csv_columns
            and not column.nullable
            and not has_insert_default(column)
        ]
        if required_missing:
            raise ValueError(
                "CSV is missing required business_segments columns without defaults: "
                + ", ".join(required_missing)
            )

        rows: list[dict[str, Any]] = []
        ids: list[int] = []
        empty_segment_names = 0
        for index, row in enumerate(reader, start=2):
            payload: dict[str, Any] = {}
            try:
                for column_name in csv_columns:
                    payload[column_name] = coerce_value(
                        row.get(column_name),
                        table.c[column_name],
                    )
            except Exception as exc:
                raise ValueError(f"Failed to parse {csv_path.name} row {index}: {exc}") from exc

            if "id" in payload and payload["id"] is not None:
                ids.append(int(payload["id"]))
            if not clean_text(row.get("segment_name")):
                empty_segment_names += 1
            rows.append(payload)

    duplicate_ids = len(ids) - len(set(ids))
    diagnostics = {
        "csv_columns": csv_columns,
        "missing_database_columns": missing_columns,
        "row_count": len(rows),
        "duplicate_id_count": duplicate_ids,
        "empty_segment_name_count": empty_segment_names,
    }
    return csv_columns, rows, diagnostics


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    period_counts = Counter(str(row.get("reporting_period") or "") for row in rows)
    current_counts = Counter(str(bool(row.get("is_current"))) for row in rows)
    company_ids = {int(row["company_id"]) for row in rows if row.get("company_id") is not None}
    ratio_sums: dict[tuple[int, str], Decimal] = defaultdict(lambda: Decimal("0"))
    ratio_row_counts: Counter[tuple[int, str]] = Counter()
    for row in rows:
        company_id = row.get("company_id")
        period = row.get("reporting_period")
        if company_id is None or period is None:
            continue
        ratio = row.get("revenue_ratio")
        if ratio is None:
            continue
        key = (int(company_id), str(period))
        ratio_sums[key] += Decimal(ratio)
        ratio_row_counts[key] += 1

    invalid_ratio_sums = [
        {
            "company_id": company_id,
            "reporting_period": period,
            "revenue_ratio_sum": str(total),
            "segment_count_with_ratio": ratio_row_counts[(company_id, period)],
        }
        for (company_id, period), total in ratio_sums.items()
        if total < Decimal("0.99") or total > Decimal("1.01")
    ]
    invalid_ratio_sums.sort(key=lambda item: (item["company_id"], item["reporting_period"]))

    return {
        "company_count": len(company_ids),
        "reporting_period_distribution": dict(sorted(period_counts.items())),
        "is_current_distribution": dict(sorted(current_counts.items())),
        "invalid_revenue_ratio_group_count": len(invalid_ratio_sums),
        "invalid_revenue_ratio_examples": invalid_ratio_sums[:20],
    }


def collect_database_checks(connection: Connection, rows: list[dict[str, Any]]) -> dict[str, Any]:
    company_ids = sorted(
        {int(row["company_id"]) for row in rows if row.get("company_id") is not None}
    )
    existing_ids: set[int] = set()
    for start in range(0, len(company_ids), 5000):
        chunk = company_ids[start : start + 5000]
        if not chunk:
            continue
        result = connection.execute(
            text("SELECT id FROM companies WHERE id = ANY(:company_ids)"),
            {"company_ids": chunk},
        )
        existing_ids.update(int(row[0]) for row in result.fetchall())
    missing_company_ids = sorted(set(company_ids) - existing_ids)
    return {
        "orphan_company_id_count": len(missing_company_ids),
        "orphan_company_id_examples": missing_company_ids[:20],
    }


def reset_id_sequence(connection: Connection, table_name: str) -> None:
    sequence_name = connection.execute(
        text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
        {"table_name": f"public.{table_name}"},
    ).scalar()
    if not sequence_name:
        return
    table_sql = quote_table(connection, table_name)
    max_id = connection.execute(text(f"SELECT MAX(id) FROM {table_sql}")).scalar()
    if max_id is None:
        connection.execute(
            text("SELECT setval(CAST(:sequence_name AS regclass), 1, false)"),
            {"sequence_name": sequence_name},
        )
    else:
        connection.execute(
            text("SELECT setval(CAST(:sequence_name AS regclass), :max_id, true)"),
            {"sequence_name": sequence_name, "max_id": int(max_id)},
        )


def count_protected_tables(connection: Connection) -> dict[str, int]:
    return {table_name: table_count(connection, table_name) for table_name in PROTECTED_TABLES}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def merge_final_summary(import_summary: dict[str, Any]) -> None:
    payload: dict[str, Any] = {}
    if FINAL_SUMMARY_PATH.exists():
        payload = json.loads(FINAL_SUMMARY_PATH.read_text(encoding="utf-8"))
    payload["import"] = import_summary
    write_json(FINAL_SUMMARY_PATH, payload)


def write_partial_report(import_summary: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Industry Refresh Report",
        "",
        f"- DATABASE_URL: `{import_summary['database_url']}`",
        f"- Status: `{import_summary['status']}`",
        f"- Apply mode: `{import_summary['apply']}`",
        f"- CSV path: `{import_summary['csv_path']}`",
        "",
        "## Import",
        "",
        f"- Pre business_segments rows: `{import_summary['pre_counts']['business_segments']}`",
        f"- Pre business_segment_classifications rows: `{import_summary['pre_counts']['business_segment_classifications']}`",
        f"- Post business_segments rows: `{import_summary.get('post_counts', {}).get('business_segments', 'not applied')}`",
        f"- Covered companies: `{import_summary['csv_summary']['company_count']}`",
        f"- CSV rows: `{import_summary['csv_diagnostics']['row_count']}`",
        f"- Orphan company_id count: `{import_summary['database_checks']['orphan_company_id_count']}`",
        f"- Invalid revenue_ratio group count: `{import_summary['csv_summary']['invalid_revenue_ratio_group_count']}`",
        "",
        "## Reporting Period Distribution",
        "",
    ]
    for period, count in import_summary["csv_summary"]["reporting_period_distribution"].items():
        lines.append(f"- `{period}`: `{count}`")
    lines.extend(["", "## Current Flag Distribution", ""])
    for flag, count in import_summary["csv_summary"]["is_current_distribution"].items():
        lines.append(f"- `{flag}`: `{count}`")
    lines.extend(["", "Classification rebuild has not been run in this report yet."])
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replace only business_segments in PostgreSQL from new_business_segments.csv."
    )
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=5000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = args.csv_path
    if not csv_path.is_absolute():
        csv_path = PROJECT_ROOT / csv_path
    csv_path = csv_path.resolve()
    if not csv_path.exists():
        raise SystemExit(f"CSV file not found: {csv_path}")

    database_url = require_database_url()
    Base = load_metadata()
    table = Base.metadata.tables[TABLE_NAME]
    _, rows, csv_diagnostics = read_business_segment_csv(csv_path, table)
    csv_summary = summarize_rows(rows)

    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            db_columns = table_columns(connection, TABLE_NAME)
            pre_counts = {
                TABLE_NAME: table_count(connection, TABLE_NAME),
                CLASSIFICATION_TABLE_NAME: table_count(connection, CLASSIFICATION_TABLE_NAME),
            }
            protected_counts_before = count_protected_tables(connection)
            database_checks = collect_database_checks(connection, rows)

        status = "dry_run_ok"
        post_counts: dict[str, int] = {}
        protected_counts_after: dict[str, int] = {}
        if args.apply:
            if database_checks["orphan_company_id_count"]:
                raise SystemExit(
                    "Refusing to apply: CSV contains business_segments.company_id values "
                    "that do not exist in companies."
                )
            with engine.begin() as connection:
                connection.execute(text(f"DELETE FROM {quote_table(connection, CLASSIFICATION_TABLE_NAME)}"))
                connection.execute(text(f"DELETE FROM {quote_table(connection, TABLE_NAME)}"))
                insert_statement = table.insert()
                for start in range(0, len(rows), args.batch_size):
                    connection.execute(insert_statement, rows[start : start + args.batch_size])
                reset_id_sequence(connection, TABLE_NAME)
                reset_id_sequence(connection, CLASSIFICATION_TABLE_NAME)

            with engine.connect() as connection:
                post_counts = {
                    TABLE_NAME: table_count(connection, TABLE_NAME),
                    CLASSIFICATION_TABLE_NAME: table_count(connection, CLASSIFICATION_TABLE_NAME),
                }
                protected_counts_after = count_protected_tables(connection)
            status = "import_applied"

        protected_table_deltas = {
            table_name: protected_counts_after.get(table_name, protected_counts_before[table_name])
            - protected_counts_before[table_name]
            for table_name in PROTECTED_TABLES
        }
        summary = {
            "status": status,
            "apply": args.apply,
            "database_url": render_database_url(database_url),
            "csv_path": str(csv_path),
            "database_columns": db_columns,
            "csv_diagnostics": csv_diagnostics,
            "csv_summary": csv_summary,
            "database_checks": database_checks,
            "pre_counts": {
                "business_segments": pre_counts[TABLE_NAME],
                "business_segment_classifications": pre_counts[CLASSIFICATION_TABLE_NAME],
            },
            "post_counts": {
                "business_segments": post_counts.get(TABLE_NAME),
                "business_segment_classifications": post_counts.get(CLASSIFICATION_TABLE_NAME),
            },
            "protected_table_deltas": protected_table_deltas,
        }
        write_json(SUMMARY_PATH, summary)
        merge_final_summary(summary)
        write_partial_report(summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
