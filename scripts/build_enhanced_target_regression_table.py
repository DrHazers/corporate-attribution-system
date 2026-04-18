from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_DATABASE = PROJECT_ROOT / "ultimate_controller_enhanced_dataset_working.db"
DEFAULT_TARGETS_CSV = (
    PROJECT_ROOT
    / "data_import_tmp"
    / "ultimate_controller_enhanced_dataset"
    / "enhanced_company_targets.csv"
)
DEFAULT_CASE_GROUPS_MD = (
    PROJECT_ROOT
    / "data_import_tmp"
    / "ultimate_controller_enhanced_dataset"
    / "expected_case_groups.md"
)
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT / "logs" / "ultimate_controller_enhanced_target_regression_table.csv"
)
DEFAULT_OUTPUT_JSON = (
    PROJECT_ROOT / "logs" / "ultimate_controller_enhanced_target_regression_table.json"
)
DEFAULT_OUTPUT_MD = (
    PROJECT_ROOT / "logs" / "ultimate_controller_enhanced_target_regression_summary.md"
)
DEFAULT_OUTPUT_SUMMARY_JSON = (
    PROJECT_ROOT / "logs" / "ultimate_controller_enhanced_target_regression_summary.json"
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
NON_EQUITY_RELATION_TYPES = {"agreement", "board_control", "voting_right", "vie", "nominee"}
TARGETED_PRIORITY_GROUPS = (
    "I_non_equity",
    "J_mixed_control",
    "D_close_competition",
    "F_nominee_unknown",
)
STABILITY_BASE_GROUPS = (
    "A_direct_ultimate",
    "B_rollup_success",
    "C_joint_block",
    "E_spv_lookthrough",
    "G_terminal_person_state_family",
    "H_fallback",
)
TABLE_FIELDS = [
    "company_id",
    "company_name",
    "case_group",
    "case_intent",
    "target_entity_id",
    "has_direct_controller",
    "direct_controller_name",
    "has_ultimate_controller",
    "ultimate_controller_name",
    "leading_candidate_name",
    "promotion_reason",
    "terminal_failure_reason",
    "attribution_layer",
    "actual_control_country",
    "attribution_type",
    "control_mode",
    "relation_types",
    "hit_fallback",
    "hit_joint_control",
    "hit_nominee_or_beneficial_owner_unknown",
    "hit_low_confidence_evidence_weak",
    "result_label",
    "label_reason",
    "top_candidate_summary",
    "top_path_summary",
    "evidence_summary",
]


def _resolve_path(path: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _validate_database(path: Path) -> Path:
    path = _resolve_path(path)
    if path.name in PROTECTED_DATABASE_NAMES:
        raise ValueError(f"Refusing to analyze protected database directly: {path}")
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")
    return path


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _normalize_id(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none"}:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return None
    if numeric.is_integer():
        return int(numeric)
    return None


def _load_targets(path: Path) -> list[dict[str, Any]]:
    path = _resolve_path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _load_case_group_descriptions(path: Path) -> dict[str, str]:
    path = _resolve_path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    descriptions: dict[str, str] = {}
    current_group: str | None = None
    for line in lines:
        if line.startswith("## "):
            current_group = line[3:].strip()
            continue
        if current_group and line.startswith("- 说明："):
            descriptions[current_group] = line.split("：", 1)[1].strip()
    return descriptions


def _parse_json(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _company_names(connection: sqlite3.Connection) -> dict[int, str]:
    rows = connection.execute("SELECT id, name FROM companies").fetchall()
    return {int(row["id"]): row["name"] for row in rows}


def _entity_names(connection: sqlite3.Connection) -> dict[int, str]:
    rows = connection.execute("SELECT id, entity_name FROM shareholder_entities").fetchall()
    return {int(row["id"]): row["entity_name"] for row in rows}


def _relation_types_by_company(connection: sqlite3.Connection) -> dict[int, set[str]]:
    rows = connection.execute(
        """
        SELECT c.id AS company_id, COALESCE(ss.relation_type, '') AS relation_type
        FROM companies c
        JOIN shareholder_entities se ON se.company_id = c.id
        JOIN shareholder_structures ss ON ss.to_entity_id = se.id
        WHERE ss.is_current = 1
        """
    ).fetchall()
    result: dict[int, set[str]] = defaultdict(set)
    for row in rows:
        relation_type = (row["relation_type"] or "").strip() or "unknown"
        result[int(row["company_id"])].add(relation_type)
    return result


def _country_rows(connection: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            company_id,
            actual_control_country,
            attribution_layer,
            attribution_type,
            actual_controller_entity_id,
            direct_controller_entity_id,
            basis
        FROM country_attributions
        """
    ).fetchall()
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        basis = _parse_json(row["basis"])
        leading_candidate = basis.get("leading_candidate") or {}
        direct_controller = basis.get("direct_controller") or {}
        leading_candidate_entity_id = basis.get("leading_candidate_entity_id")
        if leading_candidate_entity_id is None:
            leading_candidate_entity_id = leading_candidate.get("entity_id")
        leading_candidate_name = basis.get("leading_candidate_name")
        if leading_candidate_name is None:
            leading_candidate_name = leading_candidate.get("name")
        result[int(row["company_id"])] = {
            "actual_control_country": row["actual_control_country"],
            "attribution_layer": row["attribution_layer"],
            "attribution_type": row["attribution_type"],
            "actual_controller_entity_id": row["actual_controller_entity_id"],
            "direct_controller_entity_id": row["direct_controller_entity_id"],
            "basis": basis,
            "leading_candidate_entity_id": leading_candidate_entity_id,
            "leading_candidate_name": leading_candidate_name,
            "controller_status": basis.get("controller_status"),
            "terminal_failure_reason": basis.get("terminal_failure_reason"),
            "direct_controller_payload": direct_controller,
            "leading_candidate_payload": leading_candidate,
        }
    return result


def _control_rows(connection: sqlite3.Connection) -> dict[int, list[dict[str, Any]]]:
    rows = connection.execute(
        """
        SELECT
            company_id,
            controller_entity_id,
            controller_name,
            control_type,
            control_mode,
            is_actual_controller,
            is_direct_controller,
            is_ultimate_controller,
            promotion_reason,
            terminal_failure_reason,
            control_ratio,
            control_chain_depth
        FROM control_relationships
        ORDER BY
            company_id,
            COALESCE(is_actual_controller, 0) DESC,
            COALESCE(is_direct_controller, 0) DESC,
            COALESCE(is_ultimate_controller, 0) DESC,
            COALESCE(control_ratio, -1) DESC,
            COALESCE(control_chain_depth, 999999) ASC,
            id ASC
        """
    ).fetchall()
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["company_id"])].append(dict(row))
    return grouped


def _best_candidate_payload(country_row: dict[str, Any]) -> dict[str, Any]:
    basis = country_row.get("basis") or {}
    leading = country_row.get("leading_candidate_payload") or {}
    direct = country_row.get("direct_controller_payload") or {}
    top_candidates = basis.get("top_candidates") or []
    if leading:
        return leading
    if top_candidates:
        first = top_candidates[0]
        return first if isinstance(first, dict) else {}
    if direct:
        return direct
    return {}


def _candidate_name(
    payload: dict[str, Any],
    *,
    entity_id: int | None,
    entity_names: dict[int, str],
) -> str | None:
    if payload.get("controller_name"):
        return str(payload["controller_name"])
    if payload.get("name"):
        return str(payload["name"])
    if entity_id is not None:
        return entity_names.get(entity_id)
    return None


def _control_mode(country_row: dict[str, Any]) -> str | None:
    best = _best_candidate_payload(country_row)
    if best.get("control_mode"):
        return str(best["control_mode"])
    direct = country_row.get("direct_controller_payload") or {}
    if direct.get("control_mode"):
        return str(direct["control_mode"])
    return None


def _first_non_empty(values: list[Any]) -> Any:
    for value in values:
        if value is None:
            continue
        if value == "":
            continue
        if value == []:
            continue
        if value == {}:
            continue
            return value
    return None


def _promotion_reason(control_rows: list[dict[str, Any]], country_row: dict[str, Any]) -> str | None:
    for row in control_rows:
        reason = row.get("promotion_reason")
        if reason:
            return str(reason)
    basis = country_row.get("basis") or {}
    reasons = basis.get("promotion_reason_by_entity_id") or {}
    if isinstance(reasons, dict):
        for value in reasons.values():
            if value:
                return str(value)
    best = _best_candidate_payload(country_row)
    reason = best.get("promotion_reason")
    return str(reason) if reason else None


def _terminal_failure_reason(control_rows: list[dict[str, Any]], country_row: dict[str, Any]) -> str | None:
    country_reason = country_row.get("terminal_failure_reason")
    if country_reason:
        return str(country_reason)
    for row in control_rows:
        reason = row.get("terminal_failure_reason")
        if reason:
            return str(reason)
    best = _best_candidate_payload(country_row)
    reason = best.get("terminal_failure_reason")
    return str(reason) if reason else None


def _top_candidate_summary(
    *,
    country_row: dict[str, Any],
    entity_names: dict[int, str],
) -> str | None:
    best = _best_candidate_payload(country_row)
    if not best:
        return None
    entity_id = _normalize_id(
        _first_non_empty(
            [
                best.get("controller_entity_id"),
                best.get("entity_id"),
                country_row.get("leading_candidate_entity_id"),
                country_row.get("actual_controller_entity_id"),
                country_row.get("direct_controller_entity_id"),
            ]
        )
    )
    name = _candidate_name(best, entity_id=entity_id, entity_names=entity_names)
    parts = [name or "(unknown)"]
    for label, key in (
        ("class", "classification"),
        ("mode", "control_mode"),
        ("score", "aggregated_control_score"),
        ("ratio_pct", "control_ratio"),
        ("select", "selection_reason"),
    ):
        value = best.get(key)
        if value not in {None, ""}:
            parts.append(f"{label}={value}")
    return " | ".join(parts)


def _top_path_summary(country_row: dict[str, Any]) -> str | None:
    basis = country_row.get("basis") or {}
    top_paths = basis.get("top_paths") or []
    path = top_paths[0] if top_paths else None
    if not isinstance(path, dict):
        best = _best_candidate_payload(country_row)
        control_path = best.get("control_path") or []
        path = control_path[0] if control_path else None
    if not isinstance(path, dict):
        return None

    names = path.get("path_entity_names") or []
    edges = path.get("edges") or []
    relation_types = []
    for edge in edges:
        if isinstance(edge, dict):
            relation_type = edge.get("relation_type")
            if relation_type:
                relation_types.append(str(relation_type))
    parts = []
    if names:
        parts.append(" -> ".join(str(item) for item in names))
    if relation_types:
        parts.append("relations=" + "/".join(relation_types))
    for label, key in (
        ("score_pct", "path_score_pct"),
        ("score", "path_score"),
        ("conf", "confidence_prod"),
    ):
        value = path.get(key)
        if value not in {None, ""}:
            parts.append(f"{label}={value}")
    return " | ".join(parts) if parts else None


def _evidence_summary(country_row: dict[str, Any]) -> str | None:
    best = _best_candidate_payload(country_row)
    candidate_summary = best.get("evidence_summary")
    if candidate_summary:
        return str(candidate_summary)
    basis = country_row.get("basis") or {}
    basis_summary = basis.get("evidence_summary")
    if isinstance(basis_summary, list) and basis_summary:
        return " ; ".join(str(item) for item in basis_summary[:3])
    if isinstance(basis_summary, str) and basis_summary:
        return basis_summary
    path = _top_path_summary(country_row)
    return path


def _label_for_row(
    *,
    case_group: str,
    has_direct: bool,
    has_ultimate: bool,
    direct_equals_ultimate: bool,
    promoted: bool,
    fallback: bool,
    joint_control: bool,
    nominee_unknown: bool,
    low_confidence: bool,
    leading_candidate_name: str | None,
    terminal_failure_reason: str | None,
    attribution_type: str | None,
    relation_types: set[str],
) -> tuple[str, str]:
    if case_group == "A_direct_ultimate":
        if has_ultimate and direct_equals_ultimate:
            return "looks_good", "direct controller is also ultimate as intended"
        if has_ultimate and promoted:
            return "too_aggressive", "promoted beyond the expected direct=ultimate stop"
        return "too_conservative", "expected a stable direct=ultimate controller outcome"

    if case_group == "B_rollup_success":
        if has_ultimate and promoted:
            return "looks_good", "promotion to upstream unique controller succeeded"
        if has_ultimate and direct_equals_ultimate:
            return "too_conservative", "stopped at the direct layer instead of rolling up"
        return "too_conservative", "expected roll-up success but no promoted ultimate controller"

    if case_group == "C_joint_block":
        if joint_control and not has_ultimate:
            return "looks_good", "joint-control block was explicitly recognized"
        if has_ultimate:
            return "too_aggressive", "joint-control case still resolved to a unique controller"
        return "too_conservative", "case blocked without a clear joint-control classification"

    if case_group == "D_close_competition":
        if has_ultimate:
            return "too_aggressive", "close-competition case still resolved to a unique controller"
        if terminal_failure_reason in {"close_competition", "insufficient_evidence"} and leading_candidate_name:
            return "looks_good", "kept a leading candidate / insufficient-evidence posture"
        if leading_candidate_name and low_confidence:
            return "needs_manual_review", "close-competition intent is mixing with low-confidence gating"
        if leading_candidate_name:
            return "needs_manual_review", "no unique controller, but failure bucket is not very clean"
        return "too_conservative", "expected at least a leading candidate signal"

    if case_group == "E_spv_lookthrough":
        if has_ultimate and promoted:
            return "looks_good", "look-through promotion across SPV / holding layer succeeded"
        if has_ultimate and direct_equals_ultimate:
            return "too_conservative", "did not look through the expected intermediate SPV layer"
        return "too_conservative", "expected look-through promotion but ultimate controller was not resolved"

    if case_group == "F_nominee_unknown":
        if nominee_unknown and not has_ultimate:
            return "looks_good", "nominee / beneficial-owner unknown block is working"
        if has_ultimate:
            return "too_aggressive", "nominee / unknown-owner case still resolved to a unique controller"
        if fallback:
            return "needs_manual_review", "blocked, but the failure reason is less explicit than intended"
        return "needs_manual_review", "nominee case did not land in a clean expected bucket"

    if case_group == "G_terminal_person_state_family":
        if has_ultimate:
            return "looks_good", "terminal person / state / family style case resolved to an ultimate controller"
        return "too_conservative", "expected terminal controller recognition but fell back"

    if case_group == "H_fallback":
        if fallback and not has_ultimate:
            return "looks_good", "fallback case stayed in fallback as intended"
        if has_ultimate:
            return "too_aggressive", "fallback case still resolved to a unique controller"
        return "needs_manual_review", "fallback case ended in a non-clean bucket"

    if case_group == "I_non_equity":
        if has_ultimate and attribution_type in {"agreement_control", "board_control", "mixed_control"}:
            return "looks_good", "non-equity / semantic control signals were reflected in the final result"
        if has_ultimate and NON_EQUITY_RELATION_TYPES.intersection(relation_types):
            return "needs_manual_review", "controller resolved, but semantic edges did not clearly drive the final attribution type"
        return "too_conservative", "non-equity structure still fell back instead of resolving control"

    if case_group == "J_mixed_control":
        if has_ultimate and attribution_type == "mixed_control":
            return "looks_good", "mixed-control aggregation reached an explicit mixed-control outcome"
        if has_ultimate:
            return "needs_manual_review", "controller resolved, but mixed-control signal did not become the final label"
        return "too_conservative", "mixed-control case still fell back to a non-controller outcome"

    return "needs_manual_review", "no rule-based expectation was defined for this case group"


def _bool_text(value: bool) -> str:
    return "1" if value else "0"


def _markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    align = ["---"] * len(header)
    body = rows[1:]
    output = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(align) + " |",
    ]
    for row in body:
        output.append("| " + " | ".join(row) + " |")
    return "\n".join(output)


def build_regression_outputs(
    *,
    database: Path,
    targets_csv: Path,
    case_groups_md: Path,
    output_csv: Path,
    output_json: Path,
    output_md: Path,
    output_summary_json: Path,
) -> dict[str, Any]:
    database = _validate_database(database)
    targets = _load_targets(targets_csv)
    case_descriptions = _load_case_group_descriptions(case_groups_md)

    with _connect(database) as connection:
        company_names = _company_names(connection)
        entity_names = _entity_names(connection)
        relation_types = _relation_types_by_company(connection)
        country_rows = _country_rows(connection)
        control_rows = _control_rows(connection)

    regression_rows: list[dict[str, Any]] = []
    group_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for target in targets:
        company_id = _normalize_id(target.get("company_id"))
        if company_id is None:
            continue
        case_group = (target.get("scenario_group") or "unknown").strip()
        country_row = country_rows.get(company_id, {})
        company_control_rows = control_rows.get(company_id, [])
        direct_entity_id = _normalize_id(country_row.get("direct_controller_entity_id"))
        ultimate_entity_id = _normalize_id(country_row.get("actual_controller_entity_id"))
        leading_entity_id = _normalize_id(country_row.get("leading_candidate_entity_id"))
        current_relation_types = relation_types.get(company_id, set())
        promotion_reason = _promotion_reason(company_control_rows, country_row)
        terminal_failure_reason = _terminal_failure_reason(company_control_rows, country_row)
        leading_name = country_row.get("leading_candidate_name")
        if leading_name is None and leading_entity_id is not None:
            leading_name = entity_names.get(leading_entity_id)

        has_direct = direct_entity_id is not None
        has_ultimate = ultimate_entity_id is not None
        direct_equals_ultimate = has_direct and has_ultimate and direct_entity_id == ultimate_entity_id
        promoted = has_direct and has_ultimate and direct_entity_id != ultimate_entity_id
        hit_fallback = country_row.get("attribution_type") == "fallback_incorporation"
        hit_joint_control = (
            country_row.get("attribution_type") == "joint_control"
            or country_row.get("attribution_layer") == "joint_control_undetermined"
            or terminal_failure_reason == "joint_control"
        )
        hit_nominee_unknown = terminal_failure_reason in {
            "nominee_without_disclosure",
            "beneficial_owner_unknown",
        }
        hit_low_confidence = terminal_failure_reason == "low_confidence_evidence_weak"
        result_label, label_reason = _label_for_row(
            case_group=case_group,
            has_direct=has_direct,
            has_ultimate=has_ultimate,
            direct_equals_ultimate=direct_equals_ultimate,
            promoted=promoted,
            fallback=hit_fallback,
            joint_control=hit_joint_control,
            nominee_unknown=hit_nominee_unknown,
            low_confidence=hit_low_confidence,
            leading_candidate_name=leading_name,
            terminal_failure_reason=terminal_failure_reason,
            attribution_type=country_row.get("attribution_type"),
            relation_types=current_relation_types,
        )

        row = {
            "company_id": company_id,
            "company_name": company_names.get(company_id, target.get("name") or ""),
            "case_group": case_group,
            "case_intent": case_descriptions.get(case_group),
            "target_entity_id": _normalize_id(target.get("target_entity_id")),
            "has_direct_controller": has_direct,
            "direct_controller_name": entity_names.get(direct_entity_id) if direct_entity_id else None,
            "has_ultimate_controller": has_ultimate,
            "ultimate_controller_name": entity_names.get(ultimate_entity_id) if ultimate_entity_id else None,
            "leading_candidate_name": leading_name,
            "promotion_reason": promotion_reason,
            "terminal_failure_reason": terminal_failure_reason,
            "attribution_layer": country_row.get("attribution_layer"),
            "actual_control_country": country_row.get("actual_control_country"),
            "attribution_type": country_row.get("attribution_type"),
            "control_mode": _control_mode(country_row),
            "relation_types": sorted(current_relation_types),
            "hit_fallback": hit_fallback,
            "hit_joint_control": hit_joint_control,
            "hit_nominee_or_beneficial_owner_unknown": hit_nominee_unknown,
            "hit_low_confidence_evidence_weak": hit_low_confidence,
            "result_label": result_label,
            "label_reason": label_reason,
            "top_candidate_summary": _top_candidate_summary(
                country_row=country_row,
                entity_names=entity_names,
            ),
            "top_path_summary": _top_path_summary(country_row),
            "evidence_summary": _evidence_summary(country_row),
        }
        regression_rows.append(row)
        group_rows[case_group].append(row)

    regression_rows.sort(key=lambda item: (item["case_group"], item["company_id"]))

    group_summary: dict[str, Any] = {}
    for case_group, rows in sorted(group_rows.items()):
        label_counts = Counter(row["result_label"] for row in rows)
        failure_counts = Counter(row["terminal_failure_reason"] or "(none)" for row in rows)
        attribution_counts = Counter(row["attribution_type"] or "(none)" for row in rows)
        group_summary[case_group] = {
            "count": len(rows),
            "label_counts": dict(label_counts),
            "looks_good_rate": round(label_counts.get("looks_good", 0) / len(rows), 4),
            "too_conservative_rate": round(
                label_counts.get("too_conservative", 0) / len(rows),
                4,
            ),
            "too_aggressive_rate": round(
                label_counts.get("too_aggressive", 0) / len(rows),
                4,
            ),
            "needs_manual_review_rate": round(
                label_counts.get("needs_manual_review", 0) / len(rows),
                4,
            ),
            "fallback_hits": sum(1 for row in rows if row["hit_fallback"]),
            "joint_hits": sum(1 for row in rows if row["hit_joint_control"]),
            "nominee_unknown_hits": sum(
                1 for row in rows if row["hit_nominee_or_beneficial_owner_unknown"]
            ),
            "low_confidence_hits": sum(
                1 for row in rows if row["hit_low_confidence_evidence_weak"]
            ),
            "ultimate_controller_hits": sum(
                1 for row in rows if row["has_ultimate_controller"]
            ),
            "promotion_hits": sum(1 for row in rows if row["promotion_reason"]),
            "top_terminal_failure_reasons": dict(failure_counts.most_common(5)),
            "top_attribution_types": dict(attribution_counts.most_common(5)),
        }

    stable_groups = sorted(
        STABILITY_BASE_GROUPS,
        key=lambda group: (
            -group_summary.get(group, {}).get("looks_good_rate", 0),
            group_summary.get(group, {}).get("too_conservative_rate", 0),
            group,
        ),
    )
    priority_groups = sorted(
        TARGETED_PRIORITY_GROUPS,
        key=lambda group: (
            -(
                group_summary.get(group, {}).get("too_conservative_rate", 0) * 2
                + group_summary.get(group, {}).get("needs_manual_review_rate", 0)
                + group_summary.get(group, {}).get("too_aggressive_rate", 0) * 2
            ),
            group,
        ),
    )

    most_stable_group = stable_groups[0] if stable_groups else None
    most_conservative_group = max(
        group_summary,
        key=lambda group: (
            group_summary[group]["too_conservative_rate"],
            group_summary[group]["count"],
        ),
    )
    top_priority_group = priority_groups[0] if priority_groups else None

    recommendation = {
        "most_stable_group": most_stable_group,
        "most_conservative_group": most_conservative_group,
        "top_priority_group": top_priority_group,
        "recommended_next_rule_focus": (
            "non-equity / mixed-control evidence threshold"
            if top_priority_group in {"I_non_equity", "J_mixed_control"}
            else "close competition thresholding"
            if top_priority_group == "D_close_competition"
            else "nominee / unknown owner boundary"
            if top_priority_group == "F_nominee_unknown"
            else "non-equity / mixed-control evidence threshold"
        ),
    }

    output_csv = _resolve_path(output_csv)
    output_json = _resolve_path(output_json)
    output_md = _resolve_path(output_md)
    output_summary_json = _resolve_path(output_summary_json)
    for path in (output_csv, output_json, output_md, output_summary_json):
        path.parent.mkdir(parents=True, exist_ok=True)

    with output_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=TABLE_FIELDS)
        writer.writeheader()
        for row in regression_rows:
            writer.writerow(
                {
                    **row,
                    "has_direct_controller": _bool_text(row["has_direct_controller"]),
                    "has_ultimate_controller": _bool_text(row["has_ultimate_controller"]),
                    "relation_types": "|".join(row["relation_types"]),
                    "hit_fallback": _bool_text(row["hit_fallback"]),
                    "hit_joint_control": _bool_text(row["hit_joint_control"]),
                    "hit_nominee_or_beneficial_owner_unknown": _bool_text(
                        row["hit_nominee_or_beneficial_owner_unknown"]
                    ),
                    "hit_low_confidence_evidence_weak": _bool_text(
                        row["hit_low_confidence_evidence_weak"]
                    ),
                }
            )

    output_json.write_text(
        json.dumps(regression_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary_payload = {
        "database": str(database),
        "targets_csv": str(_resolve_path(targets_csv)),
        "case_groups_md": str(_resolve_path(case_groups_md)),
        "target_count": len(regression_rows),
        "group_summary": group_summary,
        "recommendation": recommendation,
    }
    output_summary_json.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    overview_rows = [["Case Group", "Count", "Looks Good", "Too Conservative", "Too Aggressive", "Needs Review"]]
    for case_group, stats in group_summary.items():
        overview_rows.append(
            [
                case_group,
                str(stats["count"]),
                str(stats["label_counts"].get("looks_good", 0)),
                str(stats["label_counts"].get("too_conservative", 0)),
                str(stats["label_counts"].get("too_aggressive", 0)),
                str(stats["label_counts"].get("needs_manual_review", 0)),
            ]
        )

    priority_lines = []
    for group in priority_groups:
        stats = group_summary.get(group, {})
        priority_lines.append(
            f"- `{group}`: looks_good={stats.get('label_counts', {}).get('looks_good', 0)}, "
            f"too_conservative={stats.get('label_counts', {}).get('too_conservative', 0)}, "
            f"needs_manual_review={stats.get('label_counts', {}).get('needs_manual_review', 0)}, "
            f"top_failures={stats.get('top_terminal_failure_reasons', {})}"
        )

    stable_lines = []
    for group in stable_groups[:4]:
        stats = group_summary.get(group, {})
        stable_lines.append(
            f"- `{group}`: looks_good_rate={stats.get('looks_good_rate', 0):.2%}, "
            f"fallback_hits={stats.get('fallback_hits', 0)}, "
            f"joint_hits={stats.get('joint_hits', 0)}"
        )

    common_issue_rows = [["Case Group", "Top Failure Reasons", "Top Attribution Types"]]
    for case_group, stats in group_summary.items():
        common_issue_rows.append(
            [
                case_group,
                ", ".join(
                    f"{key}:{value}"
                    for key, value in stats["top_terminal_failure_reasons"].items()
                ),
                ", ".join(
                    f"{key}:{value}"
                    for key, value in stats["top_attribution_types"].items()
                ),
            ]
        )

    summary_md = "\n".join(
        [
            "# Enhanced Target Regression Summary",
            "",
            f"- Database: `{database}`",
            f"- Target count: `{len(regression_rows)}`",
            f"- Regression CSV: `{output_csv}`",
            f"- Regression JSON: `{output_json}`",
            "",
            "## Case Group Distribution",
            _markdown_table(overview_rows),
            "",
            "## Stable Groups",
            *stable_lines,
            "",
            "## Priority Groups",
            *priority_lines,
            "",
            "## Common Failure / Attribution Patterns",
            _markdown_table(common_issue_rows),
            "",
            "## Recommendation",
            f"- Most stable group: `{recommendation['most_stable_group']}`",
            f"- Most obviously conservative group: `{recommendation['most_conservative_group']}`",
            f"- Next priority group: `{recommendation['top_priority_group']}`",
            f"- Recommended next rule focus: `{recommendation['recommended_next_rule_focus']}`",
            "",
            "## Notes",
            "- `looks_good` means the current result broadly matches the scenario design intent.",
            "- `too_conservative` means the result stayed in fallback / under-resolution where the scenario was meant to resolve further.",
            "- `too_aggressive` means the result resolved to a unique controller when the scenario was designed to block or stay cautious.",
            "- `needs_manual_review` means the direction is plausible but the bucket or reasoning still looks noisy.",
            "",
        ]
    )
    output_md.write_text(summary_md, encoding="utf-8")

    return {
        "csv_path": str(output_csv),
        "json_path": str(output_json),
        "md_path": str(output_md),
        "summary_json_path": str(output_summary_json),
        "target_count": len(regression_rows),
        "group_summary": group_summary,
        "recommendation": recommendation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a regression table for the enhanced target company set."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--targets-csv", type=Path, default=DEFAULT_TARGETS_CSV)
    parser.add_argument("--case-groups-md", type=Path, default=DEFAULT_CASE_GROUPS_MD)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument(
        "--output-summary-json",
        type=Path,
        default=DEFAULT_OUTPUT_SUMMARY_JSON,
    )
    args = parser.parse_args()

    result = build_regression_outputs(
        database=args.database,
        targets_csv=args.targets_csv,
        case_groups_md=args.case_groups_md,
        output_csv=args.output_csv,
        output_json=args.output_json,
        output_md=args.output_md,
        output_summary_json=args.output_summary_json,
    )

    print(f"target_count: {result['target_count']}")
    for group, stats in result["group_summary"].items():
        print(
            f"{group}: count={stats['count']} "
            f"looks_good={stats['label_counts'].get('looks_good', 0)} "
            f"too_conservative={stats['label_counts'].get('too_conservative', 0)} "
            f"too_aggressive={stats['label_counts'].get('too_aggressive', 0)} "
            f"needs_manual_review={stats['label_counts'].get('needs_manual_review', 0)}"
        )
    print("recommendation:")
    for key, value in result["recommendation"].items():
        print(f"  - {key}: {value}")
    print(f"csv_path: {result['csv_path']}")
    print(f"json_path: {result['json_path']}")
    print(f"md_path: {result['md_path']}")
    print(f"summary_json_path: {result['summary_json_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
