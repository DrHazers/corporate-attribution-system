from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    create_engine,
    false,
    text,
    true,
)
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.schema import DefaultClause

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "final_enhanced_input_tables_csv"

IMPORT_ORDER = [
    "companies",
    "shareholder_entities",
    "shareholder_structures",
    "relationship_sources",
    "entity_aliases",
    "business_segments",
    "business_segment_classifications",
    "shareholder_structure_history",
    "control_inference_runs",
    "control_inference_audit_log",
    "control_relationships",
    "country_attributions",
    "manual_control_overrides",
    "annotation_logs",
]

COUNT_TABLES = [
    "companies",
    "shareholder_entities",
    "shareholder_structures",
    "business_segments",
    "business_segment_classifications",
]

TRUTHY = {"1", "t", "true", "yes", "y", "on"}
FALSY = {"0", "f", "false", "no", "n", "off"}


def raise_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def require_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "DATABASE_URL is required. Refusing to default to SQLite for this import."
        )

    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise SystemExit(
            f"DATABASE_URL must point to PostgreSQL, got backend: {url.get_backend_name()}"
        )
    return database_url


def load_metadata():
    sys.path.insert(0, str(PROJECT_ROOT))
    import backend.models  # noqa: F401
    from backend.database import Base

    # Current app models use SQLite-friendly boolean defaults in a few places.
    # Normalize them only in this one-off PostgreSQL metadata process.
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if not isinstance(column.type, Boolean) or column.server_default is None:
                continue
            default_text = str(column.server_default.arg).strip().lower()
            if default_text in {"0", "false"}:
                column.server_default = DefaultClause(false())
            elif default_text in {"1", "true"}:
                column.server_default = DefaultClause(true())
    return Base


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import final demo CSV tables into PostgreSQL using DATABASE_URL."
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help="Directory containing final demo CSV files.",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Clear target tables first. Without this flag, existing data aborts import.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Number of rows inserted per batch.",
    )
    return parser.parse_args()


def quote_table(connection: Connection, table_name: str) -> str:
    return connection.dialect.identifier_preparer.quote(table_name)


def table_count(connection: Connection, table_name: str) -> int:
    return int(
        connection.execute(
            text(f"SELECT COUNT(*) FROM {quote_table(connection, table_name)}")
        ).scalar_one()
    )


def clear_tables(connection: Connection) -> None:
    for table_name in reversed(IMPORT_ORDER):
        connection.execute(text(f"DELETE FROM {quote_table(connection, table_name)}"))


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


def coerce_integer_value(
    value: str,
    *,
    table_name: str,
    column_name: str,
    original_value: str | None,
) -> int:
    try:
        return int(value)
    except ValueError:
        pass

    try:
        numeric_value = float(value)
    except ValueError as exc:
        raise conversion_error(
            table_name=table_name,
            column_name=column_name,
            value=original_value,
            expected_type="integer",
        ) from exc

    if not numeric_value.is_integer():
        raise conversion_error(
            table_name=table_name,
            column_name=column_name,
            value=original_value,
            expected_type="integer",
        )

    return int(numeric_value)


def coerce_boolean_value(
    value: str,
    *,
    table_name: str,
    column_name: str,
    original_value: str | None,
) -> bool:
    lowered = value.lower()
    if lowered in TRUTHY:
        return True
    if lowered in FALSY:
        return False

    try:
        numeric_value = float(value)
    except ValueError as exc:
        raise conversion_error(
            table_name=table_name,
            column_name=column_name,
            value=original_value,
            expected_type="boolean",
        ) from exc

    if numeric_value.is_integer() and int(numeric_value) in {0, 1}:
        return bool(int(numeric_value))

    raise conversion_error(
        table_name=table_name,
        column_name=column_name,
        value=original_value,
        expected_type="boolean",
    )


def boolean_default_for_column(column) -> bool | None:
    default = column.server_default or column.default
    if default is None:
        return None

    default_text = str(default.arg).strip().lower()
    if default_text in {"0", "false"}:
        return False
    if default_text in {"1", "true"}:
        return True
    return None


def coerce_value(value: str | None, column, *, table_name: str) -> Any:
    original_value = value
    if value is None:
        return None

    value = value.strip()
    column_type = column.type
    if value == "":
        if isinstance(column_type, Boolean) and not column.nullable:
            default_value = boolean_default_for_column(column)
            if default_value is not None:
                return default_value
        return None

    if isinstance(column_type, Boolean):
        return coerce_boolean_value(
            value,
            table_name=table_name,
            column_name=column.name,
            original_value=original_value,
        )

    if isinstance(column_type, Integer):
        return coerce_integer_value(
            value,
            table_name=table_name,
            column_name=column.name,
            original_value=original_value,
        )

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


def iter_csv_rows(csv_path: Path, table) -> tuple[list[str], list[dict[str, Any]]]:
    raise_csv_field_limit()
    if csv_path.stat().st_size == 0:
        return [], []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            return [], []

        columns = [name for name in reader.fieldnames if name]
        table_columns = set(table.c.keys())
        unknown_columns = sorted(set(columns) - table_columns)
        if unknown_columns:
            raise RuntimeError(
                f"{csv_path.name} contains columns not present in model "
                f"{table.name}: {', '.join(unknown_columns)}"
            )

        rows = []
        for row in reader:
            rows.append(
                {
                    column_name: coerce_value(
                        row.get(column_name),
                        table.c[column_name],
                        table_name=table.name,
                    )
                    for column_name in columns
                }
            )
        return columns, rows


def insert_csv_table(
    connection: Connection,
    *,
    input_dir: Path,
    table_name: str,
    table,
    batch_size: int,
) -> int:
    csv_path = input_dir / f"{table_name}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Required CSV not found: {csv_path}")

    columns, rows = iter_csv_rows(csv_path, table)
    if not columns or not rows:
        return 0

    inserted = 0
    insert_statement = table.insert()
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        connection.execute(insert_statement, batch)
        inserted += len(batch)
    return inserted


def reset_id_sequence(connection: Connection, table_name: str) -> None:
    table_sql = quote_table(connection, table_name)
    sequence_name = connection.execute(
        text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
        {"table_name": f"public.{table_name}"},
    ).scalar()
    if not sequence_name:
        return

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


def main() -> None:
    raise_csv_field_limit()
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    database_url = require_database_url()
    Base = load_metadata()
    engine = create_engine(database_url, future=True)

    missing_tables = [name for name in IMPORT_ORDER if name not in Base.metadata.tables]
    if missing_tables:
        raise SystemExit(f"Missing SQLAlchemy table definitions: {', '.join(missing_tables)}")

    with engine.begin() as connection:
        Base.metadata.create_all(bind=connection)

        existing_counts = {
            table_name: table_count(connection, table_name) for table_name in IMPORT_ORDER
        }
        non_empty_tables = {
            table_name: count for table_name, count in existing_counts.items() if count > 0
        }
        if non_empty_tables and not args.truncate:
            details = ", ".join(
                f"{table_name}={count}" for table_name, count in non_empty_tables.items()
            )
            raise SystemExit(
                "Target PostgreSQL tables already contain data. "
                "Re-run with --truncate only if you want to clear these tables first: "
                f"{details}"
            )

        if args.truncate:
            clear_tables(connection)

        imported_counts: dict[str, int] = {}
        for table_name in IMPORT_ORDER:
            imported_counts[table_name] = insert_csv_table(
                connection,
                input_dir=input_dir,
                table_name=table_name,
                table=Base.metadata.tables[table_name],
                batch_size=args.batch_size,
            )

        for table_name in IMPORT_ORDER:
            table = Base.metadata.tables[table_name]
            if "id" in table.c:
                reset_id_sequence(connection, table_name)

    print(f"Imported CSV directory: {input_dir}")
    print("Imported row counts:")
    for table_name in IMPORT_ORDER:
        print(f"{table_name}\t{imported_counts[table_name]}")

    print("Post-import key table totals:")
    with engine.connect() as connection:
        for table_name in COUNT_TABLES:
            print(f"{table_name}\t{table_count(connection, table_name)}")


if __name__ == "__main__":
    main()
