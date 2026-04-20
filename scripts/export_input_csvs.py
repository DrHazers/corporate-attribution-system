from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.database_config import get_default_application_database_path


DEFAULT_DATABASE = get_default_application_database_path()
DEFAULT_OUTPUT_DIR = BASE_DIR / "exports" / "db_handoff"

CORE_INPUT_TABLES = (
    "companies",
    "shareholder_entities",
    "shareholder_structures",
)
OPTIONAL_INPUT_TABLES = (
    "relationship_sources",
    "entity_aliases",
)
OUTPUT_REFERENCE_TABLES = (
    "control_relationships",
    "country_attributions",
    "control_inference_runs",
    "control_inference_audit_log",
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
    "control_relationships": "algorithm_output",
    "country_attributions": "algorithm_output",
    "control_inference_runs": "process_trace",
    "control_inference_audit_log": "process_trace",
}


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def _connect(database_path: Path) -> sqlite3.Connection:
    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")
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


def _write_header_only_csv(
    *,
    columns: Iterable[str],
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(list(columns))


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


def _export_output_header(
    connection: sqlite3.Connection,
    table_name: str,
    output_dir: Path,
) -> dict:
    columns = _table_columns(connection, table_name)
    destination = output_dir / "output_table_headers" / f"{table_name}_headers.csv"
    _write_header_only_csv(columns=columns, destination=destination)
    return {
        "table": table_name,
        "classification": TABLE_CLASSIFICATION.get(table_name),
        "path": _display_path(destination),
        "columns": columns,
        "row_count": _table_count(connection, table_name),
        "exported_data_rows": 0,
    }


def export_handoff(database_path: Path, output_dir: Path) -> dict:
    database_path = database_path.resolve()
    output_dir = output_dir.resolve()
    with _connect(database_path) as connection:
        manifest: dict = {
            "database": str(database_path),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "encoding": "utf-8-sig",
            "full_table_exports": [],
            "recommended_input_templates": [],
            "output_table_headers": [],
            "missing_tables": [],
            "table_counts": {},
        }

        all_known_tables = (
            CORE_INPUT_TABLES + OPTIONAL_INPUT_TABLES + OUTPUT_REFERENCE_TABLES
        )
        for table_name in all_known_tables:
            if _table_exists(connection, table_name):
                manifest["table_counts"][table_name] = _table_count(
                    connection,
                    table_name,
                )
            else:
                manifest["missing_tables"].append(table_name)

        for table_name in CORE_INPUT_TABLES + OPTIONAL_INPUT_TABLES:
            if not _table_exists(connection, table_name):
                continue
            manifest["full_table_exports"].append(
                _export_full_table(connection, table_name, output_dir)
            )
            manifest["recommended_input_templates"].append(
                _export_template_table(connection, table_name, output_dir)
            )

        for table_name in OUTPUT_REFERENCE_TABLES:
            if not _table_exists(connection, table_name):
                continue
            manifest["output_table_headers"].append(
                _export_output_header(connection, table_name, output_dir)
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
            "Export current database handoff CSVs: complete input tables, "
            "recommended input templates, and output table header references."
        )
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    manifest = export_handoff(args.database, args.output_dir)
    print(f"database: {manifest['database']}")
    print(f"output_dir: {args.output_dir.resolve()}")
    print(f"manifest: {manifest['manifest_path']}")
    print("full_table_exports:")
    for item in manifest["full_table_exports"]:
        print(f"  - {item['path']} ({item['row_count']} rows)")
    print("recommended_input_templates:")
    for item in manifest["recommended_input_templates"]:
        print(f"  - {item['path']} ({item['row_count']} rows)")
    print("output_table_headers:")
    for item in manifest["output_table_headers"]:
        print(f"  - {item['path']} (headers only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
