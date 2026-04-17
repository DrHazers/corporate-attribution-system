from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = BASE_DIR / "company_test_analysis_industry_export_source.db"
DEFAULT_OUTPUT_DIR = BASE_DIR / "exports" / "db_handoff_from_original"
EXPECTED_DATABASE_NAME = "company_test_analysis_industry_export_source.db"

CORE_INPUT_TABLES = (
    "companies",
    "shareholder_entities",
    "shareholder_structures",
)
OPTIONAL_INPUT_TABLES = (
    "relationship_sources",
    "entity_aliases",
)

TEMPLATE_FIELDS = {
    "companies": (
        "id",
        "name",
        "stock_code",
        "incorporation_country",
        "listing_country",
        "headquarters",
        "description",
    ),
    "shareholder_entities": (
        "id",
        "entity_name",
        "entity_type",
        "country",
        "company_id",
        "identifier_code",
        "is_listed",
        "entity_subtype",
        "ultimate_owner_hint",
        "look_through_priority",
        "controller_class",
        "beneficial_owner_disclosed",
        "notes",
    ),
    "shareholder_structures": (
        "id",
        "from_entity_id",
        "to_entity_id",
        "holding_ratio",
        "voting_ratio",
        "economic_ratio",
        "is_direct",
        "control_type",
        "relation_type",
        "has_numeric_ratio",
        "is_beneficial_control",
        "look_through_allowed",
        "termination_signal",
        "effective_control_ratio",
        "relation_role",
        "control_basis",
        "board_seats",
        "nomination_rights",
        "agreement_scope",
        "relation_metadata",
        "relation_priority",
        "confidence_level",
        "reporting_period",
        "effective_date",
        "expiry_date",
        "is_current",
        "source",
        "remarks",
    ),
    "relationship_sources": (
        "id",
        "structure_id",
        "source_type",
        "source_name",
        "source_url",
        "source_date",
        "excerpt",
        "confidence_level",
    ),
    "entity_aliases": (
        "id",
        "entity_id",
        "alias_name",
        "alias_type",
        "is_primary",
    ),
}

TABLE_CLASSIFICATION = {
    "companies": "core_input",
    "shareholder_entities": "core_input",
    "shareholder_structures": "core_input",
    "relationship_sources": "optional_input",
    "entity_aliases": "optional_input",
}


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def _validate_database_path(database_path: Path) -> Path:
    database_path = database_path.resolve()
    if database_path.name != EXPECTED_DATABASE_NAME:
        raise ValueError(
            f"Refusing to export from {database_path.name}. "
            f"Expected the export-source copy: {EXPECTED_DATABASE_NAME}."
        )
    if not database_path.exists():
        raise FileNotFoundError(
            f"Export-source database copy not found: {database_path}. "
            "Run scripts/create_export_source_copy.py first."
        )
    return database_path


def _connect(database_path: Path) -> sqlite3.Connection:
    database_path = _validate_database_path(database_path)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    return [
        row["name"]
        for row in connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    ]


def _table_count(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f'SELECT COUNT(*) AS count FROM "{table_name}"').fetchone()
    return int(row["count"])


def _write_csv_header_and_rows(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    columns: Iterable[str],
    destination: Path,
) -> int:
    selected_columns = list(columns)
    quoted_columns = ", ".join(f'"{column}"' for column in selected_columns)
    query = f'SELECT {quoted_columns} FROM "{table_name}" ORDER BY "id" ASC'

    destination.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    with destination.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(selected_columns)
        for row in connection.execute(query):
            writer.writerow([row[column] for column in selected_columns])
            row_count += 1
    return row_count


def _export_full_table(
    connection: sqlite3.Connection,
    table_name: str,
    output_dir: Path,
) -> dict:
    columns = _table_columns(connection, table_name)
    destination = output_dir / "current_full_tables" / f"{table_name}.csv"
    exported_rows = _write_csv_header_and_rows(
        connection,
        table_name=table_name,
        columns=columns,
        destination=destination,
    )
    return {
        "table": table_name,
        "classification": TABLE_CLASSIFICATION.get(table_name),
        "path": _display_path(destination),
        "columns": columns,
        "row_count": exported_rows,
    }


def _export_template_table(
    connection: sqlite3.Connection,
    table_name: str,
    output_dir: Path,
) -> dict:
    existing_columns = _table_columns(connection, table_name)
    template_columns = [
        column for column in TEMPLATE_FIELDS[table_name] if column in existing_columns
    ]
    destination = (
        output_dir / "recommended_input_templates" / f"{table_name}_input_template.csv"
    )
    exported_rows = _write_csv_header_and_rows(
        connection,
        table_name=table_name,
        columns=template_columns,
        destination=destination,
    )
    return {
        "table": table_name,
        "classification": TABLE_CLASSIFICATION.get(table_name),
        "path": _display_path(destination),
        "columns": template_columns,
        "row_count": exported_rows,
    }


def export_input_csvs(database_path: Path, output_dir: Path) -> dict:
    database_path = _validate_database_path(database_path)
    output_dir = output_dir.resolve()
    with _connect(database_path) as connection:
        manifest: dict = {
            "database": str(database_path),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "encoding": "utf-8-sig",
            "source_policy": (
                "CSV exports are generated only from "
                "company_test_analysis_industry_export_source.db, a copy of the "
                "original company_test_analysis_industry.db."
            ),
            "full_table_exports": [],
            "recommended_input_templates": [],
            "missing_tables": [],
            "table_counts": {},
        }

        for table_name in CORE_INPUT_TABLES + OPTIONAL_INPUT_TABLES:
            if not _table_exists(connection, table_name):
                manifest["missing_tables"].append(table_name)
                continue
            manifest["table_counts"][table_name] = _table_count(
                connection,
                table_name,
            )
            manifest["full_table_exports"].append(
                _export_full_table(connection, table_name, output_dir)
            )
            manifest["recommended_input_templates"].append(
                _export_template_table(connection, table_name, output_dir)
            )

    manifest_path = output_dir / "export_manifest.json"
    manifest["manifest_path"] = _display_path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export input-only handoff CSVs from "
            "company_test_analysis_industry_export_source.db."
        )
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    manifest = export_input_csvs(args.database, args.output_dir)
    print(f"database: {manifest['database']}")
    print(f"output_dir: {args.output_dir.resolve()}")
    print(f"manifest: {manifest['manifest_path']}")
    print("full_table_exports:")
    for item in manifest["full_table_exports"]:
        print(f"  - {item['path']} ({item['row_count']} rows)")
    print("recommended_input_templates:")
    for item in manifest["recommended_input_templates"]:
        print(f"  - {item['path']} ({item['row_count']} rows)")
    if manifest["missing_tables"]:
        print("missing_tables:")
        for table_name in manifest["missing_tables"]:
            print(f"  - {table_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
