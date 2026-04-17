from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["CONTROL_INFERENCE_ENGINE"] = "unified"
os.environ["CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK"] = "1"

from backend.analysis.control_inference import build_control_context  # noqa: E402
from backend.analysis.ownership_penetration import (  # noqa: E402
    DEFAULT_DISCLOSURE_THRESHOLD_PCT,
    DEFAULT_MAJORITY_THRESHOLD_PCT,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MIN_PATH_RATIO_PCT,
    _refresh_company_control_analysis_with_unified_context,
)


PROTECTED_DATABASE_NAMES = {
    "company_test_analysis_industry.db",
    "company_test_analysis_industry_v2.db",
    "company_test_analysis_industry_export_source.db",
}
INPUT_TABLES = (
    "companies",
    "shareholder_entities",
    "shareholder_structures",
    "relationship_sources",
)
OUTPUT_TABLES = (
    "control_relationships",
    "country_attributions",
    "control_inference_runs",
    "control_inference_audit_log",
)
DIRECT_RELATION_TYPES = (
    "agreement",
    "board_control",
    "nominee",
    "vie",
    "voting_right",
    "other",
)
SUBJECT_KEYWORDS = {
    "trust": ("trust", "trustee"),
    "gp_lp": ("general partner", "limited partner", " gp ", " lp ", "fund"),
    "state": ("state-owned", "state owned", "government", "sovereign"),
    "acting_in_concert": ("acting in concert", "concert party", "jointly"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a medium/large validation batch for unified control inference.",
    )
    parser.add_argument(
        "--source-db",
        type=Path,
        default=PROJECT_ROOT / "company_test_analysis_working.db",
    )
    parser.add_argument(
        "--target-db",
        type=Path,
        default=PROJECT_ROOT / "tests" / "output" / "large_control_validation.db",
    )
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=PROJECT_ROOT / "tests" / "output" / "large_control_validation_summary.json",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=PROJECT_ROOT / "tests" / "output" / "large_control_validation_summary.md",
    )
    parser.add_argument(
        "--overwrite-target",
        action="store_true",
        help="Replace the target validation DB if it already exists.",
    )
    return parser.parse_args()


def _resolve_project_path(path: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _validate_source_db(path: Path) -> Path:
    path = _resolve_project_path(path)
    if not path.exists():
        raise FileNotFoundError(f"Source database not found: {path}")
    if path.suffix.lower() != ".db":
        raise ValueError(f"Source database must be a .db file: {path}")
    return path


def _validate_target_db(path: Path, *, overwrite: bool) -> Path:
    path = _resolve_project_path(path)
    if path.name in PROTECTED_DATABASE_NAMES:
        raise ValueError(f"Refusing to write protected database: {path}")
    if path.suffix.lower() != ".db":
        raise ValueError(f"Target database must be a .db file: {path}")
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"Target database must be inside project root: {path}") from exc
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Target database already exists: {path}. Use --overwrite-target or a new path."
        )
    return path


def prepare_target_database(source_db: Path, target_db: Path, *, overwrite: bool) -> Path:
    source_db = _validate_source_db(source_db)
    target_db = _validate_target_db(target_db, overwrite=overwrite)
    if source_db.name in PROTECTED_DATABASE_NAMES and source_db == target_db:
        raise ValueError(f"Refusing to run directly against protected database: {source_db}")
    target_db.parent.mkdir(parents=True, exist_ok=True)
    if source_db.resolve() != target_db.resolve():
        if target_db.exists():
            target_db.unlink()
        shutil.copy2(source_db, target_db)
    return target_db


def connect_sqlite(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    return connection


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        is not None
    )


def count_table(connection: sqlite3.Connection, table_name: str) -> int:
    if not table_exists(connection, table_name):
        return 0
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])


def collect_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        table_name: count_table(connection, table_name)
        for table_name in (*INPUT_TABLES, *OUTPUT_TABLES)
    }


def _append_ids(
    selected: list[int],
    seen: set[int],
    rows: list[sqlite3.Row],
    *,
    limit: int,
) -> None:
    for row in rows:
        company_id = int(row["id"])
        if company_id in seen:
            continue
        seen.add(company_id)
        selected.append(company_id)
        if len(selected) >= limit:
            return


def choose_company_ids(connection: sqlite3.Connection, *, limit: int) -> list[int]:
    if limit < 1:
        raise ValueError("limit must be at least 1.")
    all_rows = connection.execute("SELECT id FROM companies ORDER BY id").fetchall()
    all_ids = [int(row["id"]) for row in all_rows]
    if len(all_ids) <= limit:
        return all_ids

    selected: list[int] = []
    seen: set[int] = set()

    for relation_type in DIRECT_RELATION_TYPES:
        rows = connection.execute(
            """
            SELECT DISTINCT c.id
            FROM companies c
            JOIN shareholder_entities se ON se.company_id = c.id
            JOIN shareholder_structures ss ON ss.to_entity_id = se.id
            WHERE ss.is_current = 1
              AND ss.is_direct = 1
              AND COALESCE(ss.relation_type, '') = ?
            ORDER BY c.id
            LIMIT 120
            """,
            (relation_type,),
        ).fetchall()
        _append_ids(selected, seen, rows, limit=limit)
        if len(selected) >= limit:
            return selected

    targeted_queries = (
        """
        SELECT DISTINCT c.id
        FROM companies c
        JOIN shareholder_entities se ON se.company_id = c.id
        JOIN shareholder_structures ss ON ss.to_entity_id = se.id
        WHERE ss.is_current = 1
          AND ss.is_direct = 1
          AND LOWER(COALESCE(ss.confidence_level, '')) IN ('low', 'unknown')
        ORDER BY c.id
        LIMIT 180
        """,
        """
        SELECT DISTINCT c.id
        FROM companies c
        JOIN shareholder_entities se ON se.company_id = c.id
        JOIN shareholder_structures ss ON ss.to_entity_id = se.id
        WHERE ss.is_current = 1
          AND ss.is_direct = 1
          AND (
            LOWER(COALESCE(ss.relation_metadata, '')) LIKE '%beneficial_owner%'
            OR LOWER(COALESCE(ss.control_basis, '')) LIKE '%beneficial owner%'
            OR LOWER(COALESCE(ss.control_basis, '')) LIKE '%nominee%'
          )
        ORDER BY c.id
        LIMIT 180
        """,
        """
        SELECT c.id
        FROM companies c
        JOIN shareholder_entities se ON se.company_id = c.id
        JOIN shareholder_structures ss ON ss.to_entity_id = se.id
        WHERE ss.is_current = 1
          AND ss.is_direct = 1
        GROUP BY c.id
        ORDER BY COUNT(ss.id) DESC, c.id
        LIMIT 180
        """,
    )
    for query in targeted_queries:
        rows = connection.execute(query).fetchall()
        _append_ids(selected, seen, rows, limit=limit)
        if len(selected) >= limit:
            return selected

    remaining = limit - len(selected)
    if remaining <= 0:
        return selected
    step = max(1, len(all_ids) // remaining)
    evenly_spaced = [{"id": company_id} for company_id in all_ids[::step]]
    _append_ids(selected, seen, evenly_spaced, limit=limit)

    if len(selected) < limit:
        fallback_rows = [{"id": company_id} for company_id in all_ids]
        _append_ids(selected, seen, fallback_rows, limit=limit)

    return selected[:limit]


def create_session_factory(database: Path):
    engine = create_engine(
        f"sqlite:///{database}",
        connect_args={"check_same_thread": False},
    )
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def run_refresh_batch(
    database: Path,
    company_ids: list[int],
    *,
    batch_size: int,
) -> dict[str, Any]:
    engine, session_factory = create_session_factory(database)
    started_at = perf_counter()
    successes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    try:
        with session_factory() as db:
            context = build_control_context(db)
            for batch_start in range(0, len(company_ids), batch_size):
                batch_ids = company_ids[batch_start : batch_start + batch_size]
                batch_success_count = 0
                for company_id in batch_ids:
                    company_started_at = perf_counter()
                    try:
                        with db.begin_nested():
                            result = _refresh_company_control_analysis_with_unified_context(
                                db,
                                company_id,
                                context=context,
                                max_depth=DEFAULT_MAX_DEPTH,
                                min_path_ratio_pct=DEFAULT_MIN_PATH_RATIO_PCT,
                                majority_threshold_pct=DEFAULT_MAJORITY_THRESHOLD_PCT,
                                disclosure_threshold_pct=DEFAULT_DISCLOSURE_THRESHOLD_PCT,
                            )
                        batch_success_count += 1
                        successes.append(
                            {
                                "company_id": company_id,
                                "duration_seconds": round(
                                    perf_counter() - company_started_at,
                                    4,
                                ),
                                "direct_controller_entity_id": result.get(
                                    "direct_controller_entity_id"
                                ),
                                "actual_controller_entity_id": result.get(
                                    "actual_controller_entity_id"
                                ),
                                "leading_candidate_entity_id": result.get(
                                    "leading_candidate_entity_id"
                                ),
                                "controller_status": result.get("controller_status"),
                                "terminal_failure_reason": result.get(
                                    "terminal_failure_reason"
                                ),
                                "control_relationship_count": result.get(
                                    "control_relationship_count"
                                ),
                                "country_attribution_type": result.get(
                                    "country_attribution_type"
                                ),
                                "inference_run_id": result.get("inference_run_id"),
                            }
                        )
                    except Exception as exc:  # noqa: BLE001 - continue validation batch.
                        failures.append(
                            {
                                "company_id": company_id,
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                            }
                        )
                        db.expire_all()
                try:
                    db.commit()
                except Exception as exc:  # noqa: BLE001 - report failed batch commit.
                    db.rollback()
                    failures.append(
                        {
                            "company_id": None,
                            "error_type": type(exc).__name__,
                            "error": (
                                f"batch commit failed at {batch_start + 1}-"
                                f"{batch_start + len(batch_ids)}: {exc}"
                            ),
                        }
                    )
                    for _ in range(batch_success_count):
                        if successes:
                            successes.pop()
    finally:
        engine.dispose()

    return {
        "processed_count": len(company_ids),
        "success_count": len(successes),
        "failed_count": len(failures),
        "duration_seconds": round(perf_counter() - started_at, 4),
        "successes": successes,
        "failures": failures,
    }


def _parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _name_for_entity(connection: sqlite3.Connection, entity_id: int | None) -> str | None:
    if entity_id is None:
        return None
    row = connection.execute(
        "SELECT entity_name FROM shareholder_entities WHERE id=?",
        (entity_id,),
    ).fetchone()
    return str(row["entity_name"]) if row is not None else None


def _controller_payload(
    connection: sqlite3.Connection,
    entity_id: int | None,
) -> dict[str, Any] | None:
    if entity_id is None:
        return None
    return {
        "entity_id": entity_id,
        "name": _name_for_entity(connection, entity_id),
    }


def _selected_placeholders(company_ids: list[int]) -> str:
    return ",".join("?" for _ in company_ids)


def collect_country_rows(
    connection: sqlite3.Connection,
    company_ids: list[int],
) -> list[dict[str, Any]]:
    if not company_ids:
        return []
    placeholders = _selected_placeholders(company_ids)
    rows = connection.execute(
        f"""
        SELECT
            c.id AS company_id,
            c.name AS company_name,
            ca.direct_controller_entity_id,
            ca.actual_controller_entity_id,
            ca.actual_control_country,
            ca.attribution_type,
            ca.attribution_layer,
            ca.country_inference_reason,
            ca.look_through_applied,
            ca.basis
        FROM companies c
        LEFT JOIN country_attributions ca ON ca.company_id = c.id
        WHERE c.id IN ({placeholders})
        ORDER BY c.id
        """,
        company_ids,
    ).fetchall()

    payloads: list[dict[str, Any]] = []
    for row in rows:
        basis = _parse_json(row["basis"]) or {}
        payloads.append(
            {
                "company_id": int(row["company_id"]),
                "company_name": row["company_name"],
                "direct_controller_entity_id": row["direct_controller_entity_id"],
                "actual_controller_entity_id": row["actual_controller_entity_id"],
                "leading_candidate_entity_id": basis.get("leading_candidate_entity_id"),
                "controller_status": basis.get("controller_status"),
                "terminal_failure_reason": basis.get("terminal_failure_reason"),
                "attribution_type": row["attribution_type"],
                "attribution_layer": row["attribution_layer"],
                "country_inference_reason": row["country_inference_reason"],
                "look_through_applied": bool(row["look_through_applied"]),
                "actual_control_country": row["actual_control_country"],
                "promotion_reason_by_entity_id": basis.get("promotion_reason_by_entity_id")
                or {},
                "top_paths": basis.get("top_paths") or [],
                "leading_candidate": basis.get("leading_candidate"),
                "direct_controller": basis.get("direct_controller"),
            }
        )
    return payloads


def collect_relationship_rows(
    connection: sqlite3.Connection,
    company_ids: list[int],
) -> list[dict[str, Any]]:
    if not company_ids:
        return []
    placeholders = _selected_placeholders(company_ids)
    rows = connection.execute(
        f"""
        SELECT
            company_id,
            controller_entity_id,
            controller_name,
            control_type,
            control_mode,
            semantic_flags,
            control_tier,
            terminal_failure_reason,
            basis,
            control_path,
            is_direct_controller,
            is_actual_controller,
            is_ultimate_controller
        FROM control_relationships
        WHERE company_id IN ({placeholders})
        ORDER BY company_id, control_ratio DESC, id ASC
        """,
        company_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def _path_edge_relation_types(path_payload: Any) -> list[str]:
    relation_types: list[str] = []
    paths = _parse_json(path_payload) or []
    if not isinstance(paths, list):
        return relation_types
    for path in paths:
        if not isinstance(path, dict):
            continue
        for edge in path.get("edges") or []:
            if isinstance(edge, dict) and edge.get("relation_type"):
                relation_types.append(str(edge["relation_type"]))
    return relation_types


def build_distribution_summary(
    country_rows: list[dict[str, Any]],
    relationship_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    attribution_layer_counts = Counter(
        row.get("attribution_layer") or "(missing)" for row in country_rows
    )
    attribution_type_counts = Counter(
        row.get("attribution_type") or "(missing)" for row in country_rows
    )
    controller_status_counts = Counter(
        row.get("controller_status") or "(missing)" for row in country_rows
    )
    terminal_failure_counts = Counter(
        row.get("terminal_failure_reason") or "(none)" for row in country_rows
    )
    control_type_counts = Counter(
        row.get("control_type") or "(missing)" for row in relationship_rows
    )
    control_mode_counts = Counter(
        row.get("control_mode") or "(missing)" for row in relationship_rows
    )
    edge_relation_type_counts: Counter[str] = Counter()
    semantic_flag_counts: Counter[str] = Counter()
    for row in relationship_rows:
        edge_relation_type_counts.update(_path_edge_relation_types(row.get("control_path")))
        flags = _parse_json(row.get("semantic_flags")) or []
        if isinstance(flags, list):
            semantic_flag_counts.update(str(flag) for flag in flags)

    direct_count = sum(1 for row in country_rows if row.get("direct_controller_entity_id"))
    ultimate_count = sum(1 for row in country_rows if row.get("actual_controller_entity_id"))
    direct_equals_actual_count = sum(
        1
        for row in country_rows
        if row.get("direct_controller_entity_id")
        and row.get("actual_controller_entity_id")
        and row.get("direct_controller_entity_id")
        == row.get("actual_controller_entity_id")
    )
    promotion_count = sum(
        1
        for row in country_rows
        if row.get("actual_controller_entity_id")
        and row.get("direct_controller_entity_id")
        and row.get("actual_controller_entity_id")
        != row.get("direct_controller_entity_id")
    )

    return {
        "companies_with_direct_controller": direct_count,
        "companies_with_ultimate_controller": ultimate_count,
        "direct_equals_ultimate": direct_equals_actual_count,
        "promotion_occurred": promotion_count,
        "joint_control_blocked": sum(
            1
            for row in country_rows
            if row.get("terminal_failure_reason") == "joint_control"
            or row.get("attribution_type") == "joint_control"
        ),
        "nominee_or_beneficial_owner_blocked": sum(
            1
            for row in country_rows
            if row.get("terminal_failure_reason")
            in {"nominee_without_disclosure", "beneficial_owner_unknown"}
        ),
        "low_confidence_evidence_weak": sum(
            1
            for row in country_rows
            if row.get("terminal_failure_reason") == "low_confidence_evidence_weak"
        ),
        "fallback_incorporation": sum(
            1
            for row in country_rows
            if row.get("attribution_type") == "fallback_incorporation"
        ),
        "leading_candidate_results": sum(
            1
            for row in country_rows
            if row.get("controller_status")
            == "no_actual_controller_but_leading_candidate_found"
        ),
        "no_meaningful_controller_signal": sum(
            1
            for row in country_rows
            if row.get("controller_status") == "no_meaningful_controller_signal"
        ),
        "attribution_layer_counts": dict(attribution_layer_counts),
        "attribution_type_counts": dict(attribution_type_counts),
        "controller_status_counts": dict(controller_status_counts),
        "terminal_failure_reason_counts": dict(terminal_failure_counts),
        "control_type_counts": dict(control_type_counts),
        "control_mode_counts": dict(control_mode_counts),
        "edge_relation_type_counts": dict(edge_relation_type_counts),
        "semantic_flag_counts": dict(semantic_flag_counts),
    }


def _first_relationship_for_company(
    relationship_by_company: dict[int, list[dict[str, Any]]],
    company_id: int,
    predicate,
) -> dict[str, Any] | None:
    for row in relationship_by_company.get(company_id, []):
        if predicate(row):
            return row
    return None


def _sample_payload(
    connection: sqlite3.Connection,
    row: dict[str, Any],
    relationship_by_company: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    company_id = int(row["company_id"])
    promotion_reasons = row.get("promotion_reason_by_entity_id") or {}
    return {
        "company_id": company_id,
        "company_name": row["company_name"],
        "direct_controller": _controller_payload(
            connection,
            row.get("direct_controller_entity_id"),
        ),
        "ultimate_controller": _controller_payload(
            connection,
            row.get("actual_controller_entity_id"),
        ),
        "leading_candidate": _controller_payload(
            connection,
            row.get("leading_candidate_entity_id"),
        ),
        "promotion_reason": (
            list(promotion_reasons.values())[0] if promotion_reasons else None
        ),
        "terminal_failure_reason": row.get("terminal_failure_reason"),
        "attribution_layer": row.get("attribution_layer"),
        "attribution_type": row.get("attribution_type"),
        "actual_control_country": row.get("actual_control_country"),
        "controller_status": row.get("controller_status"),
        "top_relationships": [
            {
                "controller_entity_id": rel.get("controller_entity_id"),
                "controller_name": rel.get("controller_name"),
                "control_type": rel.get("control_type"),
                "control_mode": rel.get("control_mode"),
                "control_tier": rel.get("control_tier"),
                "terminal_failure_reason": rel.get("terminal_failure_reason"),
            }
            for rel in relationship_by_company.get(company_id, [])[:3]
        ],
    }


def choose_representative_samples(
    connection: sqlite3.Connection,
    country_rows: list[dict[str, Any]],
    relationship_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    relationship_by_company: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in relationship_rows:
        relationship_by_company[int(row["company_id"])].append(row)

    def has_relation_type(company_id: int, relation_types: set[str]) -> bool:
        return any(
            relation_type in relation_types
            for rel in relationship_by_company.get(company_id, [])
            for relation_type in _path_edge_relation_types(rel.get("control_path"))
        )

    categories = {
        "direct_is_ultimate": lambda row: row.get("direct_controller_entity_id")
        and row.get("actual_controller_entity_id")
        and row.get("direct_controller_entity_id")
        == row.get("actual_controller_entity_id"),
        "promotion_success": lambda row: row.get("direct_controller_entity_id")
        and row.get("actual_controller_entity_id")
        and row.get("direct_controller_entity_id")
        != row.get("actual_controller_entity_id"),
        "joint_control": lambda row: row.get("terminal_failure_reason")
        == "joint_control"
        or row.get("attribution_type") == "joint_control",
        "nominee_block": lambda row: row.get("terminal_failure_reason")
        == "nominee_without_disclosure",
        "beneficial_owner_unknown": lambda row: row.get("terminal_failure_reason")
        == "beneficial_owner_unknown",
        "fallback": lambda row: row.get("attribution_type") == "fallback_incorporation",
        "board_control": lambda row: has_relation_type(
            int(row["company_id"]),
            {"board_control"},
        ),
        "vie_or_agreement": lambda row: has_relation_type(
            int(row["company_id"]),
            {"vie", "agreement"},
        ),
        "low_confidence_evidence_weak": lambda row: row.get(
            "terminal_failure_reason"
        )
        == "low_confidence_evidence_weak",
        "mixed_control": lambda row: any(
            rel.get("control_type") == "mixed_control"
            or rel.get("control_mode") == "mixed"
            for rel in relationship_by_company.get(int(row["company_id"]), [])
        ),
    }

    samples: dict[str, list[dict[str, Any]]] = {}
    for category, predicate in categories.items():
        matched = [row for row in country_rows if predicate(row)]
        samples[category] = [
            _sample_payload(connection, row, relationship_by_company)
            for row in matched[:3]
        ]
    return samples


def _keyword_company_ids(
    connection: sqlite3.Connection,
    company_ids: list[int],
    keywords: tuple[str, ...],
) -> set[int]:
    if not company_ids:
        return set()
    placeholders = _selected_placeholders(company_ids)
    clauses = []
    params: list[Any] = [*company_ids]
    for keyword in keywords:
        clauses.append(
            """
            LOWER(
                COALESCE(c.name, '') || ' ' ||
                COALESCE(se.entity_name, '') || ' ' ||
                COALESCE(ss.control_basis, '') || ' ' ||
                COALESCE(ss.agreement_scope, '') || ' ' ||
                COALESCE(ss.nomination_rights, '') || ' ' ||
                COALESCE(ss.relation_metadata, '') || ' ' ||
                COALESCE(ss.remarks, '')
            ) LIKE ?
            """
        )
        params.append(f"%{keyword.lower()}%")
    rows = connection.execute(
        f"""
        SELECT DISTINCT c.id
        FROM companies c
        LEFT JOIN shareholder_entities se ON se.company_id = c.id
        LEFT JOIN shareholder_structures ss ON ss.to_entity_id = se.id
        WHERE c.id IN ({placeholders})
          AND ({" OR ".join(clauses)})
        ORDER BY c.id
        """,
        params,
    ).fetchall()
    return {int(row["id"]) for row in rows}


def classify_issue_categories(
    connection: sqlite3.Connection,
    company_ids: list[int],
    country_rows: list[dict[str, Any]],
    relationship_rows: list[dict[str, Any]],
    samples: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    relationship_by_company: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in relationship_rows:
        relationship_by_company[int(row["company_id"])].append(row)

    semantic_conservative_ids: set[int] = set()
    evidence_quality_ids: set[int] = set()
    presentation_ids: set[int] = set()

    for row in relationship_rows:
        company_id = int(row["company_id"])
        flags = _parse_json(row.get("semantic_flags")) or []
        basis = _parse_json(row.get("basis")) or {}
        total_confidence = basis.get("total_confidence")
        try:
            confidence_value = float(total_confidence)
        except (TypeError, ValueError):
            confidence_value = None
        if (
            isinstance(flags, list)
            and "needs_review" in flags
            and any(
                country_row["company_id"] == company_id
                and not country_row.get("actual_controller_entity_id")
                for country_row in country_rows
            )
        ):
            semantic_conservative_ids.add(company_id)
        if (
            isinstance(flags, list)
            and {
                "low_confidence",
                "unknown_confidence",
                "thin_semantic_evidence",
            }.intersection(flags)
        ) or (confidence_value is not None and confidence_value < 0.5):
            evidence_quality_ids.add(company_id)
        controller_name = str(row.get("controller_name") or "").lower()
        if "public float" in controller_name or "dispersed" in controller_name:
            presentation_ids.add(company_id)

    for row in country_rows:
        if row.get("terminal_failure_reason") == "low_confidence_evidence_weak":
            evidence_quality_ids.add(int(row["company_id"]))
        if row.get("controller_status") == "no_meaningful_controller_signal":
            presentation_ids.add(int(row["company_id"]))

    subject_ids_by_type = {
        label: _keyword_company_ids(connection, company_ids, keywords)
        for label, keywords in SUBJECT_KEYWORDS.items()
    }
    subject_ids = set().union(*subject_ids_by_type.values()) if subject_ids_by_type else set()

    def issue_sample(company_id_set: set[int]) -> list[dict[str, Any]]:
        matched_rows = [
            row for row in country_rows if int(row["company_id"]) in company_id_set
        ]
        relationship_by_company_local = relationship_by_company
        return [
            _sample_payload(connection, row, relationship_by_company_local)
            for row in matched_rows[:5]
        ]

    return {
        "complex_semantic_control_still_conservative": {
            "count": len(semantic_conservative_ids),
            "reason": (
                "Semantic paths exist but remain needs_review / significant influence "
                "or are blocked before actual output."
            ),
            "priority": "medium",
            "sample_companies": issue_sample(semantic_conservative_ids),
        },
        "complex_subject_structures_not_fully_modeled": {
            "count": len(subject_ids),
            "keyword_counts": {
                label: len(ids) for label, ids in subject_ids_by_type.items()
            },
            "reason": (
                "Detected trust / GP-LP / state / acting-in-concert style language in "
                "input text or entity names; these are not yet first-class rule families."
            ),
            "priority": "high" if subject_ids else "low",
            "sample_companies": issue_sample(subject_ids),
        },
        "evidence_quality_layer_needs_more_granularity": {
            "count": len(evidence_quality_ids),
            "reason": (
                "Low/unknown/thin reliability still drives many leading-candidate or "
                "manual-review outcomes; source tiering and time consistency are coarse."
            ),
            "priority": "medium",
            "sample_companies": issue_sample(evidence_quality_ids),
        },
        "result_presentation_and_fallback_focus": {
            "count": len(presentation_ids),
            "reason": (
                "Fallback/no-meaningful-controller and public-float style candidates may "
                "need clearer focused-candidate presentation before final UX freeze."
            ),
            "priority": "medium" if presentation_ids else "low",
            "sample_companies": issue_sample(presentation_ids),
        },
        "representative_empty_sample_categories": [
            category for category, items in samples.items() if not items
        ],
    }


def write_markdown(summary: dict[str, Any], output_md: Path) -> None:
    lines: list[str] = []
    lines.append("# Large Control Validation Summary")
    lines.append("")
    lines.append(f"- Generated at: {summary['generated_at']}")
    lines.append(f"- Source DB: `{summary['source_database']}`")
    lines.append(f"- Validation DB: `{summary['validation_database']}`")
    lines.append(f"- Selected companies: {summary['selection']['selected_company_count']}")
    lines.append(f"- Success / failed: {summary['refresh']['success_count']} / {summary['refresh']['failed_count']}")
    lines.append("")
    lines.append("## Input Counts")
    for key, value in summary["pre_counts"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Result Distribution")
    for key, value in summary["distribution"].items():
        if isinstance(value, dict):
            lines.append(f"- {key}:")
            for sub_key, sub_value in value.items():
                lines.append(f"  - {sub_key}: {sub_value}")
        else:
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Representative Samples")
    for category, items in summary["representative_samples"].items():
        lines.append(f"### {category}")
        if not items:
            lines.append("- No sample found in this validation batch.")
            continue
        for item in items:
            lines.append(
                "- "
                f"{item['company_id']} {item['company_name']} | "
                f"direct={item['direct_controller']} | "
                f"ultimate={item['ultimate_controller']} | "
                f"leading={item['leading_candidate']} | "
                f"failure={item['terminal_failure_reason']} | "
                f"layer={item['attribution_layer']} | "
                f"country={item['actual_control_country']}"
            )
    lines.append("")
    lines.append("## Issue Categories")
    for key, payload in summary["issue_categories"].items():
        if not isinstance(payload, dict):
            lines.append(f"- {key}: {payload}")
            continue
        lines.append(f"### {key}")
        lines.append(f"- Count: {payload.get('count')}")
        lines.append(f"- Priority: {payload.get('priority')}")
        lines.append(f"- Reason: {payload.get('reason')}")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    source_db = _validate_source_db(args.source_db)
    target_db = prepare_target_database(
        source_db,
        args.target_db,
        overwrite=args.overwrite_target,
    )

    with connect_sqlite(target_db) as connection:
        pre_counts = collect_counts(connection)
        selected_company_ids = choose_company_ids(connection, limit=args.limit)

    refresh_summary = run_refresh_batch(
        target_db,
        selected_company_ids,
        batch_size=args.batch_size,
    )

    with connect_sqlite(target_db) as connection:
        post_counts = collect_counts(connection)
        country_rows = collect_country_rows(connection, selected_company_ids)
        relationship_rows = collect_relationship_rows(connection, selected_company_ids)
        distribution = build_distribution_summary(country_rows, relationship_rows)
        samples = choose_representative_samples(
            connection,
            country_rows,
            relationship_rows,
        )
        issue_categories = classify_issue_categories(
            connection,
            selected_company_ids,
            country_rows,
            relationship_rows,
            samples,
        )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_database": str(source_db),
        "validation_database": str(target_db),
        "pre_counts": pre_counts,
        "post_counts": post_counts,
        "inserted_or_current_rows_delta": {
            table_name: post_counts.get(table_name, 0) - pre_counts.get(table_name, 0)
            for table_name in OUTPUT_TABLES
        },
        "selection": {
            "strategy": (
                "stratified relation-type / low-confidence / beneficial-owner / "
                "high-edge-count / evenly-spaced sample"
            ),
            "requested_limit": args.limit,
            "selected_company_count": len(selected_company_ids),
            "selected_company_ids": selected_company_ids,
        },
        "refresh": refresh_summary,
        "distribution": distribution,
        "representative_samples": samples,
        "issue_categories": issue_categories,
    }

    output_json = _resolve_project_path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    output_md = _resolve_project_path(args.output_md)
    write_markdown(summary, output_md)

    print(f"source_database: {source_db}")
    print(f"validation_database: {target_db}")
    print(f"selected_company_count: {len(selected_company_ids)}")
    print(f"success_count: {refresh_summary['success_count']}")
    print(f"failed_count: {refresh_summary['failed_count']}")
    print(f"control_relationships_delta: {summary['inserted_or_current_rows_delta']['control_relationships']}")
    print(f"country_attributions_delta: {summary['inserted_or_current_rows_delta']['country_attributions']}")
    print("distribution:")
    for key in (
        "companies_with_direct_controller",
        "companies_with_ultimate_controller",
        "direct_equals_ultimate",
        "promotion_occurred",
        "joint_control_blocked",
        "nominee_or_beneficial_owner_blocked",
        "low_confidence_evidence_weak",
        "fallback_incorporation",
        "leading_candidate_results",
    ):
        print(f"  - {key}: {distribution[key]}")
    print(f"summary_json: {output_json}")
    print(f"summary_md: {output_md}")
    return 0 if refresh_summary["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
