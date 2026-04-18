from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = PROJECT_ROOT / "ultimate_controller_enhanced_dataset_working.db"
DEFAULT_TARGETS_CSV = (
    PROJECT_ROOT / "data_import_tmp" / "ultimate_controller_enhanced_dataset" / "enhanced_company_targets.csv"
)
DEFAULT_CASE_GROUPS_MD = (
    PROJECT_ROOT / "data_import_tmp" / "ultimate_controller_enhanced_dataset" / "expected_case_groups.md"
)
DEFAULT_REFRESH_SUMMARY = (
    PROJECT_ROOT / "logs" / "ultimate_controller_enhanced_dataset_working_refresh_summary.json"
)
DEFAULT_COMPARE_SUMMARY = (
    PROJECT_ROOT / "tests" / "output" / "large_control_validation_full_20260418_summary.json"
)
DEFAULT_OUTPUT_JSON = (
    PROJECT_ROOT / "logs" / "ultimate_controller_enhanced_dataset_working_result_summary.json"
)
PROTECTED_DATABASE_NAMES = {
    "company_test_analysis_industry.db",
    "company_test_analysis_industry_v2.db",
    "company_test_analysis_industry_export_source.db",
    "large_control_validation_imported_20260418.db",
    "large_control_validation_full_20260418.db",
    "ultimate_controller_test_dataset.db",
    "ultimate_controller_enhanced_dataset.db",
}
TARGET_CATEGORY_ORDER = (
    "direct_equals_ultimate",
    "promotion_success",
    "vie_or_agreement",
    "board_control",
    "nominee",
    "beneficial_owner_unknown",
    "low_confidence",
    "fallback",
    "trust",
    "mixed_control",
    "public_float_or_dispersed",
)


def _resolve_path(path: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _validate_database(path: Path) -> Path:
    path = _resolve_path(path)
    if path.name in PROTECTED_DATABASE_NAMES:
        raise ValueError(f"Refusing to summarize protected database: {path}")
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")
    return path


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _parse_json(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _load_targets(path: Path) -> list[dict[str, Any]]:
    path = _resolve_path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader)


def _load_case_group_names(path: Path) -> list[str]:
    path = _resolve_path(path)
    text = path.read_text(encoding="utf-8")
    return re.findall(r"^##\s+(.+)$", text, flags=re.MULTILINE)


def _count_table(connection: sqlite3.Connection, table_name: str) -> int:
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])


def _build_relation_type_map(connection: sqlite3.Connection) -> dict[int, set[str]]:
    rows = connection.execute(
        """
        SELECT c.id AS company_id, COALESCE(ss.relation_type, '') AS relation_type
        FROM companies c
        JOIN shareholder_entities se ON se.company_id = c.id
        JOIN shareholder_structures ss ON ss.to_entity_id = se.id
        WHERE ss.is_current = 1
          AND ss.is_direct = 1
        """
    ).fetchall()
    result: dict[int, set[str]] = defaultdict(set)
    for row in rows:
        relation_type = row["relation_type"].strip() or "unknown"
        result[int(row["company_id"])].add(relation_type)
    return result


def _build_keyword_flags(connection: sqlite3.Connection) -> dict[int, dict[str, bool]]:
    rows = connection.execute(
        """
        SELECT DISTINCT
            c.id AS company_id,
            LOWER(
                COALESCE(c.name, '') || ' ' ||
                COALESCE(c.description, '') || ' ' ||
                COALESCE(se.entity_name, '') || ' ' ||
                COALESCE(se.notes, '') || ' ' ||
                COALESCE(ss.control_basis, '') || ' ' ||
                COALESCE(ss.agreement_scope, '') || ' ' ||
                COALESCE(ss.nomination_rights, '') || ' ' ||
                COALESCE(ss.relation_metadata, '') || ' ' ||
                COALESCE(ss.remarks, '')
            ) AS blob
        FROM companies c
        LEFT JOIN shareholder_entities se ON se.company_id = c.id
        LEFT JOIN shareholder_structures ss ON ss.to_entity_id = se.id
        """
    ).fetchall()
    flags: dict[int, dict[str, bool]] = {}
    for row in rows:
        blob = row["blob"] or ""
        company_id = int(row["company_id"])
        flags[company_id] = {
            "trust": "trust" in blob or "trustee" in blob,
            "public_float": "public float" in blob,
            "dispersed": "dispersed" in blob,
        }
    return flags


def _load_country_rows(connection: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            ca.company_id,
            ca.actual_control_country,
            ca.attribution_layer,
            ca.attribution_type,
            ca.actual_controller_entity_id,
            ca.direct_controller_entity_id,
            ca.basis,
            ca.country_inference_reason
        FROM country_attributions ca
        """
    ).fetchall()
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        basis = _parse_json(row["basis"])
        leading_candidate = basis.get("leading_candidate") or {}
        leading_candidate_entity_id = basis.get("leading_candidate_entity_id")
        if leading_candidate_entity_id is None:
            leading_candidate_entity_id = leading_candidate.get("entity_id")
        leading_candidate_name = basis.get("leading_candidate_name")
        if leading_candidate_name is None:
            leading_candidate_name = leading_candidate.get("name")
        leading_candidate_classification = basis.get("leading_candidate_classification")
        if leading_candidate_classification is None:
            leading_candidate_classification = leading_candidate.get("classification")
        result[int(row["company_id"])] = {
            "company_id": int(row["company_id"]),
            "actual_control_country": row["actual_control_country"],
            "attribution_layer": row["attribution_layer"],
            "attribution_type": row["attribution_type"],
            "actual_controller_entity_id": row["actual_controller_entity_id"],
            "direct_controller_entity_id": row["direct_controller_entity_id"],
            "basis": basis,
            "controller_status": basis.get("controller_status"),
            "terminal_failure_reason": basis.get("terminal_failure_reason"),
            "leading_candidate_entity_id": leading_candidate_entity_id,
            "leading_candidate_name": leading_candidate_name,
            "leading_candidate_classification": leading_candidate_classification,
            "country_inference_reason": row["country_inference_reason"],
        }
    return result


def _load_control_rows(connection: sqlite3.Connection) -> dict[int, list[dict[str, Any]]]:
    rows = connection.execute(
        """
        SELECT
            cr.company_id,
            cr.controller_entity_id,
            cr.controller_name,
            cr.controller_type,
            cr.control_type,
            cr.control_ratio,
            cr.is_actual_controller,
            cr.is_direct_controller,
            cr.is_ultimate_controller,
            cr.promotion_reason,
            cr.terminal_failure_reason,
            cr.control_tier,
            cr.control_chain_depth,
            cr.is_terminal_inference
        FROM control_relationships cr
        ORDER BY
            cr.company_id,
            COALESCE(cr.is_actual_controller, 0) DESC,
            COALESCE(cr.is_direct_controller, 0) DESC,
            COALESCE(cr.is_ultimate_controller, 0) DESC,
            COALESCE(cr.control_chain_depth, 999999) ASC,
            COALESCE(cr.control_ratio, -1) DESC,
            cr.id ASC
        """
    ).fetchall()
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["company_id"])].append(dict(row))
    return grouped


def _entity_name_lookup(connection: sqlite3.Connection) -> dict[int, str]:
    rows = connection.execute("SELECT id, entity_name FROM shareholder_entities").fetchall()
    return {int(row["id"]): row["entity_name"] for row in rows}


def _company_name_lookup(connection: sqlite3.Connection) -> dict[int, str]:
    rows = connection.execute("SELECT id, name FROM companies").fetchall()
    return {int(row["id"]): row["name"] for row in rows}


def _pick_terminal_failure(country_row: dict[str, Any], control_rows: list[dict[str, Any]]) -> str | None:
    if country_row.get("terminal_failure_reason"):
        return country_row["terminal_failure_reason"]
    for row in control_rows:
        reason = row.get("terminal_failure_reason")
        if reason:
            return reason
    return None


def _pick_promotion_reason(control_rows: list[dict[str, Any]]) -> str | None:
    for row in control_rows:
        reason = row.get("promotion_reason")
        if reason:
            return reason
    return None


def _first_matching_control(
    control_rows: list[dict[str, Any]],
    *,
    field: str,
) -> dict[str, Any] | None:
    for row in control_rows:
        if row.get(field):
            return row
    return None


def _build_company_snapshot(
    *,
    company_id: int,
    company_name: str,
    country_row: dict[str, Any] | None,
    control_rows: list[dict[str, Any]],
    entity_names: dict[int, str],
    relation_types: set[str],
    keyword_flags: dict[str, bool],
    scenario_group: str | None,
) -> dict[str, Any]:
    country_row = country_row or {}
    direct_entity_id = country_row.get("direct_controller_entity_id")
    actual_entity_id = country_row.get("actual_controller_entity_id")
    leading_candidate_entity_id = country_row.get("leading_candidate_entity_id")
    leading_candidate_name = country_row.get("leading_candidate_name")
    if leading_candidate_entity_id and not leading_candidate_name:
        try:
            leading_candidate_name = entity_names.get(int(leading_candidate_entity_id))
        except (TypeError, ValueError):
            leading_candidate_name = country_row.get("leading_candidate_name")
    return {
        "company_id": company_id,
        "company_name": company_name,
        "scenario_group": scenario_group,
        "relation_types": sorted(relation_types),
        "keyword_flags": keyword_flags,
        "direct_controller": {
            "entity_id": direct_entity_id,
            "name": entity_names.get(int(direct_entity_id)) if direct_entity_id else None,
        },
        "ultimate_controller": {
            "entity_id": actual_entity_id,
            "name": entity_names.get(int(actual_entity_id)) if actual_entity_id else None,
        },
        "leading_candidate": {
            "entity_id": leading_candidate_entity_id,
            "name": leading_candidate_name,
        },
        "promotion_reason": _pick_promotion_reason(control_rows),
        "terminal_failure_reason": _pick_terminal_failure(country_row, control_rows),
        "attribution_layer": country_row.get("attribution_layer"),
        "attribution_type": country_row.get("attribution_type"),
        "actual_control_country": country_row.get("actual_control_country"),
        "controller_status": country_row.get("controller_status"),
    }


def _select_samples(
    snapshots: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    categories: dict[str, list[dict[str, Any]]] = {name: [] for name in TARGET_CATEGORY_ORDER}

    def add(category: str, candidate: dict[str, Any]) -> None:
        if len(categories[category]) >= 3:
            return
        if any(existing["company_id"] == candidate["company_id"] for existing in categories[category]):
            return
        categories[category].append(candidate)

    sorted_snapshots = sorted(
        snapshots,
        key=lambda item: (0 if item.get("scenario_group") else 1, item["company_id"]),
    )
    for snapshot in sorted_snapshots:
        direct_id = snapshot["direct_controller"]["entity_id"]
        ultimate_id = snapshot["ultimate_controller"]["entity_id"]
        failure = snapshot.get("terminal_failure_reason")
        relation_types = set(snapshot.get("relation_types", []))
        keywords = snapshot.get("keyword_flags", {})
        scenario = snapshot.get("scenario_group")
        leading_name = (snapshot.get("leading_candidate") or {}).get("name") or ""

        if direct_id and ultimate_id and direct_id == ultimate_id:
            add("direct_equals_ultimate", snapshot)
        if direct_id and ultimate_id and direct_id != ultimate_id:
            add("promotion_success", snapshot)
        if relation_types.intersection({"vie", "agreement"}):
            add("vie_or_agreement", snapshot)
        if "board_control" in relation_types:
            add("board_control", snapshot)
        if failure in {"nominee_without_disclosure", "nominee_blocked"} or scenario == "F_nominee_unknown":
            add("nominee", snapshot)
        if failure == "beneficial_owner_unknown":
            add("beneficial_owner_unknown", snapshot)
        if failure == "low_confidence_evidence_weak":
            add("low_confidence", snapshot)
        if snapshot.get("attribution_type") == "fallback_incorporation" or scenario == "H_fallback":
            add("fallback", snapshot)
        if keywords.get("trust"):
            add("trust", snapshot)
        if snapshot.get("attribution_type") == "mixed_control" or scenario == "J_mixed_control":
            add("mixed_control", snapshot)
        if keywords.get("public_float") or keywords.get("dispersed") or leading_name.startswith("Public Float"):
            add("public_float_or_dispersed", snapshot)

    return categories


def _distribution_summary(
    country_rows: dict[int, dict[str, Any]],
    control_rows: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    companies_with_direct_controller = 0
    companies_with_ultimate_controller = 0
    direct_equals_ultimate = 0
    promotion_companies: set[int] = set()
    leading_candidate_results = 0
    attribution_layer_counts: Counter[str] = Counter()
    attribution_type_counts: Counter[str] = Counter()
    terminal_failure_reason_counts: Counter[str] = Counter()
    controller_status_counts: Counter[str] = Counter()

    for company_id, row in country_rows.items():
        direct = row.get("direct_controller_entity_id")
        ultimate = row.get("actual_controller_entity_id")
        if direct is not None:
            companies_with_direct_controller += 1
        if ultimate is not None:
            companies_with_ultimate_controller += 1
        if direct is not None and ultimate is not None and direct == ultimate:
            direct_equals_ultimate += 1
        if direct is not None and ultimate is not None and direct != ultimate:
            promotion_companies.add(company_id)

        controller_status = row.get("controller_status") or "unknown"
        controller_status_counts[controller_status] += 1

        if row.get("attribution_layer"):
            attribution_layer_counts[row["attribution_layer"]] += 1
        if row.get("attribution_type"):
            attribution_type_counts[row["attribution_type"]] += 1

        failure = _pick_terminal_failure(row, control_rows.get(company_id, [])) or "(none)"
        terminal_failure_reason_counts[failure] += 1
        if ultimate is None and row.get("leading_candidate_entity_id") is not None:
            leading_candidate_results += 1

    promotion_reason_companies = {
        company_id
        for company_id, rows in control_rows.items()
        if any(row.get("promotion_reason") for row in rows)
    }
    promotion_companies |= promotion_reason_companies

    return {
        "companies_with_direct_controller": companies_with_direct_controller,
        "companies_with_ultimate_controller": companies_with_ultimate_controller,
        "direct_equals_ultimate": direct_equals_ultimate,
        "promotion_occurred": len(promotion_companies),
        "joint_control": terminal_failure_reason_counts.get("joint_control", 0),
        "nominee_or_beneficial_owner_unknown": (
            terminal_failure_reason_counts.get("nominee_without_disclosure", 0)
            + terminal_failure_reason_counts.get("beneficial_owner_unknown", 0)
        ),
        "nominee_without_disclosure": terminal_failure_reason_counts.get(
            "nominee_without_disclosure", 0
        ),
        "beneficial_owner_unknown": terminal_failure_reason_counts.get(
            "beneficial_owner_unknown", 0
        ),
        "low_confidence_evidence_weak": terminal_failure_reason_counts.get(
            "low_confidence_evidence_weak", 0
        ),
        "fallback_incorporation": attribution_type_counts.get("fallback_incorporation", 0),
        "leading_candidate_results": leading_candidate_results,
        "attribution_layer_counts": dict(attribution_layer_counts),
        "attribution_type_counts": dict(attribution_type_counts),
        "terminal_failure_reason_counts": dict(terminal_failure_reason_counts),
        "controller_status_counts": dict(controller_status_counts),
    }


def _minimum_input_ready(connection: sqlite3.Connection) -> bool:
    checks = (
        """
        SELECT COUNT(*)
        FROM shareholder_entities se
        LEFT JOIN companies c ON c.id = se.company_id
        WHERE se.company_id IS NOT NULL AND c.id IS NULL
        """,
        """
        SELECT COUNT(*)
        FROM shareholder_structures ss
        LEFT JOIN shareholder_entities se ON se.id = ss.from_entity_id
        WHERE se.id IS NULL
        """,
        """
        SELECT COUNT(*)
        FROM shareholder_structures ss
        LEFT JOIN shareholder_entities se ON se.id = ss.to_entity_id
        WHERE se.id IS NULL
        """,
        """
        SELECT COUNT(*)
        FROM companies c
        LEFT JOIN shareholder_entities se ON se.company_id = c.id
        WHERE se.id IS NULL
        """,
    )
    return (
        _count_table(connection, "companies") > 0
        and _count_table(connection, "shareholder_entities") > 0
        and _count_table(connection, "shareholder_structures") > 0
        and all(int(connection.execute(sql).fetchone()[0]) == 0 for sql in checks)
        and not list(connection.execute("PRAGMA foreign_key_check"))
    )


def _input_relation_type_counts(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT COALESCE(relation_type, '(null)') AS relation_type, COUNT(*) AS count
        FROM shareholder_structures
        GROUP BY COALESCE(relation_type, '(null)')
        ORDER BY count DESC, relation_type
        """
    ).fetchall()
    return {row["relation_type"]: int(row["count"]) for row in rows}


def _compare_to_previous(current_summary: dict[str, Any], compare_summary_path: Path) -> dict[str, Any]:
    compare_summary_path = _resolve_path(compare_summary_path)
    previous = json.loads(compare_summary_path.read_text(encoding="utf-8"))
    previous_distribution = previous.get("distribution", {})
    previous_edge_types = previous_distribution.get("edge_relation_type_counts", {})
    current_edge_types = current_summary["input_relation_type_counts"]
    current_distribution = current_summary["result_distribution"]

    def _delta(current_key: str, previous_key: str | None = None) -> dict[str, Any]:
        prev_key = previous_key or current_key
        return {
            "current": current_distribution.get(current_key),
            "previous": previous_distribution.get(prev_key),
        }

    return {
        "previous_validation_summary": str(compare_summary_path),
        "input_relation_type_comparison": {
            key: {
                "current": current_edge_types.get(key, 0),
                "previous": previous_edge_types.get(key, 0),
            }
            for key in ("board_control", "agreement", "vie", "nominee", "voting_right", "other")
        },
        "result_distribution_comparison": {
            "promotion_occurred": _delta("promotion_occurred"),
            "joint_control": {
                "current": current_distribution.get("joint_control"),
                "previous": previous_distribution.get("joint_control_blocked"),
            },
            "nominee_or_beneficial_owner_unknown": {
                "current": current_distribution.get("nominee_or_beneficial_owner_unknown"),
                "previous": previous_distribution.get("nominee_or_beneficial_owner_blocked"),
            },
            "low_confidence_evidence_weak": _delta("low_confidence_evidence_weak"),
            "fallback_incorporation": _delta("fallback_incorporation"),
            "leading_candidate_results": _delta("leading_candidate_results"),
            "mixed_control": {
                "current": current_distribution.get("attribution_type_counts", {}).get(
                    "mixed_control",
                    0,
                ),
                "previous": previous_distribution.get("attribution_type_counts", {}).get(
                    "mixed_control",
                    0,
                ),
            },
            "board_control": {
                "current": current_distribution.get("attribution_type_counts", {}).get(
                    "board_control",
                    0,
                ),
                "previous": previous_distribution.get("attribution_type_counts", {}).get(
                    "board_control",
                    0,
                ),
            },
        },
    }


def summarize(
    *,
    database: Path,
    targets_csv: Path,
    case_groups_md: Path,
    refresh_summary_path: Path,
    compare_summary_path: Path,
    output_json: Path,
) -> dict[str, Any]:
    database = _validate_database(database)
    targets = _load_targets(targets_csv)
    case_group_names = _load_case_group_names(case_groups_md)
    refresh_summary = json.loads(_resolve_path(refresh_summary_path).read_text(encoding="utf-8"))

    with _connect(database) as connection:
        input_counts = {
            table_name: _count_table(connection, table_name)
            for table_name in (
                "companies",
                "shareholder_entities",
                "shareholder_structures",
                "relationship_sources",
                "entity_aliases",
                "control_relationships",
                "country_attributions",
                "control_inference_runs",
                "control_inference_audit_log",
            )
        }
        minimum_input_ready = _minimum_input_ready(connection)
        relation_type_map = _build_relation_type_map(connection)
        keyword_flags = _build_keyword_flags(connection)
        entity_names = _entity_name_lookup(connection)
        company_names = _company_name_lookup(connection)
        country_rows = _load_country_rows(connection)
        control_rows = _load_control_rows(connection)
        input_relation_type_counts = _input_relation_type_counts(connection)

    target_scenario_counts = Counter(row.get("scenario_group") or "unknown" for row in targets)
    target_lookup = {int(float(row["company_id"])): row for row in targets}
    snapshots: list[dict[str, Any]] = []
    for company_id, company_name in company_names.items():
        target_row = target_lookup.get(company_id)
        snapshots.append(
            _build_company_snapshot(
                company_id=company_id,
                company_name=company_name,
                country_row=country_rows.get(company_id),
                control_rows=control_rows.get(company_id, []),
                entity_names=entity_names,
                relation_types=relation_type_map.get(company_id, set()),
                keyword_flags=keyword_flags.get(
                    company_id,
                    {"trust": False, "public_float": False, "dispersed": False},
                ),
                scenario_group=(target_row or {}).get("scenario_group"),
            )
        )

    result_distribution = _distribution_summary(country_rows, control_rows)
    samples_by_category = _select_samples(snapshots)

    summary = {
        "database": str(database),
        "input_counts": input_counts,
        "minimum_input_ready_for_refresh": minimum_input_ready,
        "enhanced_company_targets": {
            "csv_path": str(_resolve_path(targets_csv)),
            "target_count": len(targets),
            "scenario_counts": dict(target_scenario_counts),
        },
        "expected_case_groups": {
            "path": str(_resolve_path(case_groups_md)),
            "scenario_groups": case_group_names,
        },
        "refresh_summary": refresh_summary,
        "input_relation_type_counts": input_relation_type_counts,
        "result_distribution": result_distribution,
        "sample_validation": samples_by_category,
    }
    summary["comparison_to_large_control_validation_full_20260418"] = _compare_to_previous(
        summary,
        compare_summary_path,
    )

    output_json = _resolve_path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize refresh results for the enhanced ultimate-controller working DB."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--targets-csv", type=Path, default=DEFAULT_TARGETS_CSV)
    parser.add_argument("--case-groups-md", type=Path, default=DEFAULT_CASE_GROUPS_MD)
    parser.add_argument("--refresh-summary", type=Path, default=DEFAULT_REFRESH_SUMMARY)
    parser.add_argument("--compare-summary", type=Path, default=DEFAULT_COMPARE_SUMMARY)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()

    summary = summarize(
        database=args.database,
        targets_csv=args.targets_csv,
        case_groups_md=args.case_groups_md,
        refresh_summary_path=args.refresh_summary,
        compare_summary_path=args.compare_summary,
        output_json=args.output_json,
    )
    print(f"database: {summary['database']}")
    print("input_counts:")
    for table_name, count in summary["input_counts"].items():
        print(f"  - {table_name}: {count}")
    print(f"minimum_input_ready_for_refresh: {summary['minimum_input_ready_for_refresh']}")
    print(f"enhanced_target_count: {summary['enhanced_company_targets']['target_count']}")
    print(
        "expected_case_groups: "
        + ", ".join(summary["expected_case_groups"]["scenario_groups"])
    )
    print("result_distribution:")
    for key, value in summary["result_distribution"].items():
        if isinstance(value, dict):
            print(f"  - {key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
        else:
            print(f"  - {key}: {value}")
    print(f"output_json: {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
