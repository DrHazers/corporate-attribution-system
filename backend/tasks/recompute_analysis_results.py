from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import and_, create_engine, func, inspect, not_, or_
from sqlalchemy.orm import Session, sessionmaker

import backend.models  # noqa: F401
from backend.analysis.control_inference import (
    DEFAULT_AGGREGATOR,
    DEFAULT_CONTROL_THRESHOLD,
    DEFAULT_DISCLOSURE_THRESHOLD,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MIN_PATH_SCORE,
    DEFAULT_SIGNIFICANT_THRESHOLD,
    build_control_context,
    infer_controllers,
    unit_to_pct,
)
from backend.analysis.ownership_penetration import (
    _build_unified_basis_payload,
    _build_unified_country_basis_payload,
    _control_type_from_candidate,
    _semantic_flags_for_storage,
    _serialize_unified_paths,
    _prepare_candidate_results,
    _quantize_pct,
    _serialize_decimal,
    _serialize_paths,
    build_ownership_analysis_context,
)
from backend.models.company import Company
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution
from backend.models.shareholder import ShareholderEntity, ShareholderStructure


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_NAME = "company_import_test.db"
REPORT_OUTPUT_DIR = PROJECT_ROOT / "tests" / "output"
RUN_ID_FORMAT = "%Y%m%d_%H%M%S"
DEFAULT_ENGINE_MODE = "unified"
SUPPORTED_ENGINE_MODES = ("unified", "legacy")
CONTROL_MANUAL_STATUSES = (
    "manual_confirmed",
    "manual_rejected",
    "needs_review",
)
COUNTRY_AUTO_SOURCE_MODES = (
    "control_chain_analysis",
    "fallback_rule",
    "control_chain",
    "fallback",
)
REQUIRED_TABLE_COLUMNS = {
    "companies": {
        "id",
        "name",
        "stock_code",
        "incorporation_country",
        "listing_country",
    },
    "shareholder_entities": {
        "id",
        "entity_name",
        "entity_type",
        "country",
        "company_id",
    },
    "shareholder_structures": {
        "id",
        "from_entity_id",
        "to_entity_id",
        "holding_ratio",
        "is_direct",
        "relation_type",
        "control_type",
        "effective_date",
        "expiry_date",
        "is_current",
    },
    "control_relationships": {
        "id",
        "company_id",
        "controller_entity_id",
        "controller_name",
        "controller_type",
        "control_type",
        "control_ratio",
        "control_path",
        "is_actual_controller",
        "basis",
        "notes",
        "control_mode",
        "review_status",
    },
    "country_attributions": {
        "id",
        "company_id",
        "incorporation_country",
        "listing_country",
        "actual_control_country",
        "attribution_type",
        "basis",
        "is_manual",
        "notes",
        "source_mode",
    },
}
LEGACY_CORE_ANALYSIS_FUNCTIONS = [
    "backend.analysis.ownership_penetration.build_ownership_analysis_context",
    "backend.analysis.ownership_penetration._prepare_candidate_results",
    "backend.analysis.ownership_penetration._collect_candidate_paths",
    "backend.shareholder_relations.build_equity_relationship_clause",
]
UNIFIED_CORE_ANALYSIS_FUNCTIONS = [
    "backend.analysis.control_inference.build_control_context",
    "backend.analysis.control_inference.infer_controllers",
    "backend.analysis.ownership_penetration._control_type_from_candidate",
    "backend.analysis.ownership_penetration._serialize_unified_paths",
]


@dataclass(slots=True)
class RecomputePlan:
    database_path: Path
    selected_reason: str
    schema_issues: list[str]
    relevant_columns: dict[str, list[str]]
    holding_ratio_scale: str
    holding_ratio_min: str | None
    holding_ratio_max: str | None
    companies_total: int
    companies_with_mapped_entity: int
    companies_with_current_incoming_edges: int
    control_auto_rows_to_delete: int
    control_manual_rows_to_preserve: int
    control_uncertain_rows_to_preserve: int
    country_auto_rows_to_delete: int
    country_manual_rows_to_preserve: int
    country_uncertain_rows_to_preserve: int
    control_review_status_distribution: dict[str, int]
    country_source_mode_distribution: dict[str, int]
    country_manual_distribution: dict[str, int]
    control_manual_company_ids: set[int]
    control_uncertain_company_ids: set[int]
    country_manual_company_ids: set[int]
    country_uncertain_company_ids: set[int]
    anomalies: list[str]

    @property
    def blocked_control_company_ids(self) -> set[int]:
        return self.control_manual_company_ids | self.control_uncertain_company_ids

    @property
    def blocked_country_company_ids(self) -> set[int]:
        return self.country_manual_company_ids | self.country_uncertain_company_ids

    def to_preview_dict(self, *, engine_mode: str = DEFAULT_ENGINE_MODE) -> dict[str, Any]:
        return {
            "target_database_path": str(self.database_path),
            "selected_reason": self.selected_reason,
            "engine_mode": engine_mode,
            "schema": {
                "compatible": not self.schema_issues,
                "issues": self.schema_issues,
                "relevant_columns": self.relevant_columns,
            },
            "strategy": {
                "mode": "per_company_transaction",
                "reason": (
                    "Use one transaction per company so a single failure rolls back only "
                    "that company's delete-and-rewrite work and does not leave the whole "
                    "database blank."
                ),
            },
            "ratio_scale": {
                "holding_ratio_scale": self.holding_ratio_scale,
                "holding_ratio_min": self.holding_ratio_min,
                "holding_ratio_max": self.holding_ratio_max,
            },
            "delete_plan": [
                {
                    "table": "control_relationships",
                    "row_count": self.control_auto_rows_to_delete,
                    "condition": (
                        "review_status = 'auto' OR notes LIKE 'AUTO:%'; "
                        "only automatic control-analysis rows are deletable"
                    ),
                },
                {
                    "table": "country_attributions",
                    "row_count": self.country_auto_rows_to_delete,
                    "condition": (
                        "is_manual = 0 and source_mode != 'manual_override'; "
                        "legacy source_mode values control_chain/fallback are treated as auto"
                    ),
                },
            ],
            "preserve_plan": [
                {
                    "table": "control_relationships",
                    "row_count": self.control_manual_rows_to_preserve,
                    "condition": (
                        "review_status in "
                        f"{CONTROL_MANUAL_STATUSES}; preserve manual/reviewed records"
                    ),
                },
                {
                    "table": "control_relationships",
                    "row_count": self.control_uncertain_rows_to_preserve,
                    "condition": (
                        "rows not confidently classifiable as auto/manual are preserved "
                        "and their companies are blocked from auto control rewrites"
                    ),
                },
                {
                    "table": "country_attributions",
                    "row_count": self.country_manual_rows_to_preserve,
                    "condition": (
                        "is_manual = 1 OR source_mode = 'manual_override'; "
                        "preserve manual override rows"
                    ),
                },
                {
                    "table": "country_attributions",
                    "row_count": self.country_uncertain_rows_to_preserve,
                    "condition": (
                        "rows not confidently classifiable as auto/manual are preserved "
                        "and their companies are blocked from auto country rewrites"
                    ),
                },
            ],
            "recompute_scope": {
                "companies_total": self.companies_total,
                "companies_with_mapped_entity": self.companies_with_mapped_entity,
                "companies_with_current_incoming_edges": self.companies_with_current_incoming_edges,
                "companies_blocked_for_control_rewrite": len(
                    self.blocked_control_company_ids
                ),
                "companies_blocked_for_country_rewrite": len(
                    self.blocked_country_company_ids
                ),
            },
            "distributions": {
                "control_review_status": self.control_review_status_distribution,
                "country_source_mode": self.country_source_mode_distribution,
                "country_is_manual": self.country_manual_distribution,
            },
            "core_analysis_functions": _core_analysis_functions(engine_mode),
            "anomalies": self.anomalies,
        }


def _normalize_engine_mode(engine_mode: str | None) -> str:
    normalized = (engine_mode or DEFAULT_ENGINE_MODE).strip().lower()
    if normalized not in SUPPORTED_ENGINE_MODES:
        raise ValueError(
            f"Unsupported engine mode: {engine_mode}. Expected one of {SUPPORTED_ENGINE_MODES}."
        )
    return normalized


def _core_analysis_functions(engine_mode: str) -> list[str]:
    normalized = _normalize_engine_mode(engine_mode)
    if normalized == "legacy":
        return LEGACY_CORE_ANALYSIS_FUNCTIONS
    return UNIFIED_CORE_ANALYSIS_FUNCTIONS


def _sqlite_url(database_path: Path) -> str:
    return f"sqlite:///{database_path}"


def _create_session_factory(database_path: Path):
    engine = create_engine(
        _sqlite_url(database_path),
        connect_args={"check_same_thread": False},
    )
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _resolve_database_path(database_path: str | None) -> tuple[Path, str]:
    if database_path:
        candidate = Path(database_path).expanduser().resolve()
    else:
        candidate = (PROJECT_ROOT / DEFAULT_DATABASE_NAME).resolve()

    if candidate.name == "test.db":
        raise ValueError(
            "Refusing to operate on test.db because it is the temporary test database, "
            "not the import-validation backup database."
        )
    if not candidate.exists():
        raise FileNotFoundError(f"Database file not found: {candidate}")

    if candidate.name == DEFAULT_DATABASE_NAME:
        reason = (
            "Selected company_import_test.db because backend/database.py and "
            "tests/import_db_api/conftest.py both treat it as the import-validation "
            "backup database."
        )
    else:
        reason = (
            "Selected the explicitly requested database path. It is not test.db, "
            "so it is allowed for this recompute task."
        )
    return candidate, reason


def _read_table_columns(inspector, table_name: str) -> list[str]:
    if table_name not in inspector.get_table_names():
        return []
    return [column["name"] for column in inspector.get_columns(table_name)]


def _schema_issues_and_columns(database_path: Path) -> tuple[list[str], dict[str, list[str]]]:
    engine, _ = _create_session_factory(database_path)
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        columns_by_table: dict[str, list[str]] = {}
        issues: list[str] = []

        for table_name, required_columns in REQUIRED_TABLE_COLUMNS.items():
            if table_name not in table_names:
                issues.append(f"Missing required table: {table_name}")
                columns_by_table[table_name] = []
                continue

            columns = _read_table_columns(inspector, table_name)
            columns_by_table[table_name] = columns
            missing_columns = sorted(required_columns - set(columns))
            if missing_columns:
                issues.append(
                    f"Table {table_name} is missing required columns: {missing_columns}"
                )
        return issues, columns_by_table
    finally:
        engine.dispose()


def _control_auto_query(db: Session):
    return db.query(ControlRelationship).filter(
        or_(
            func.lower(func.coalesce(ControlRelationship.review_status, "")) == "auto",
            func.coalesce(ControlRelationship.notes, "").like("AUTO:%"),
        )
    )


def _control_manual_query(db: Session):
    return db.query(ControlRelationship).filter(
        func.lower(func.coalesce(ControlRelationship.review_status, "")).in_(
            CONTROL_MANUAL_STATUSES
        )
    )


def _control_uncertain_query(db: Session):
    auto_expr = or_(
        func.lower(func.coalesce(ControlRelationship.review_status, "")) == "auto",
        func.coalesce(ControlRelationship.notes, "").like("AUTO:%"),
    )
    manual_expr = func.lower(func.coalesce(ControlRelationship.review_status, "")).in_(
        CONTROL_MANUAL_STATUSES
    )
    return (
        db.query(ControlRelationship)
        .filter(not_(or_(auto_expr, manual_expr)))
    )


def _country_manual_query(db: Session):
    manual_expr = or_(
        CountryAttribution.is_manual.is_(True),
        func.lower(func.coalesce(CountryAttribution.source_mode, ""))
        == "manual_override",
    )
    return db.query(CountryAttribution).filter(manual_expr)


def _country_auto_query(db: Session):
    manual_expr = or_(
        CountryAttribution.is_manual.is_(True),
        func.lower(func.coalesce(CountryAttribution.source_mode, ""))
        == "manual_override",
    )
    return db.query(CountryAttribution).filter(
        and_(
            CountryAttribution.is_manual.is_(False),
            not_(manual_expr),
        )
    )

def _country_uncertain_query(db: Session):
    manual_expr = or_(
        CountryAttribution.is_manual.is_(True),
        func.lower(func.coalesce(CountryAttribution.source_mode, ""))
        == "manual_override",
    )
    auto_expr = and_(
        CountryAttribution.is_manual.is_(False),
        not_(manual_expr),
    )
    return (
        db.query(CountryAttribution)
        .filter(not_(or_(manual_expr, auto_expr)))
    )


def _distribution_dict(rows: list[tuple[Any, int]]) -> dict[str, int]:
    output: dict[str, int] = {}
    for value, count in rows:
        output["<NULL>" if value is None else str(value)] = int(count)
    return output


def _distinct_company_ids(query, model) -> set[int]:
    return {
        int(company_id)
        for (company_id,) in query.with_entities(model.company_id).distinct().all()
        if company_id is not None
    }


def _detect_holding_ratio_scale(db: Session) -> tuple[str, str | None, str | None]:
    min_ratio, max_ratio = (
        db.query(
            func.min(ShareholderStructure.holding_ratio),
            func.max(ShareholderStructure.holding_ratio),
        )
        .filter(ShareholderStructure.holding_ratio.is_not(None))
        .one()
    )

    min_text = str(min_ratio) if min_ratio is not None else None
    max_text = str(max_ratio) if max_ratio is not None else None
    if max_ratio is None:
        return "unknown", min_text, max_text
    if Decimal(max_ratio) <= Decimal("1"):
        return "fraction_0_to_1", min_text, max_text
    return "percent_0_to_100", min_text, max_text


def _normalize_context_holding_ratios(context, *, holding_ratio_scale: str) -> None:
    if holding_ratio_scale != "fraction_0_to_1":
        return

    multiplier = Decimal("100")
    for incoming_edges in context.incoming_map.values():
        for edge in incoming_edges:
            if edge.holding_ratio is None:
                continue
            edge.holding_ratio = Decimal(edge.holding_ratio) * multiplier


def _build_recompute_plan(
    database_path: str | None,
    *,
    engine_mode: str = DEFAULT_ENGINE_MODE,
) -> RecomputePlan:
    normalized_engine_mode = _normalize_engine_mode(engine_mode)
    resolved_path, selected_reason = _resolve_database_path(database_path)
    schema_issues, relevant_columns = _schema_issues_and_columns(resolved_path)

    engine, session_factory = _create_session_factory(resolved_path)
    try:
        with session_factory() as db:
            (
                holding_ratio_scale,
                holding_ratio_min,
                holding_ratio_max,
            ) = _detect_holding_ratio_scale(db)
            companies_total = db.query(Company.id).count()
            companies_with_mapped_entity = (
                db.query(ShareholderEntity.company_id)
                .filter(ShareholderEntity.company_id.is_not(None))
                .distinct()
                .count()
            )
            companies_with_current_incoming_edges = (
                db.query(ShareholderEntity.company_id)
                .join(
                    ShareholderStructure,
                    ShareholderStructure.to_entity_id == ShareholderEntity.id,
                )
                .filter(ShareholderEntity.company_id.is_not(None))
                .filter(ShareholderStructure.is_current.is_(True))
                .filter(ShareholderStructure.is_direct.is_(True))
                .distinct()
                .count()
            )

            control_auto_query = _control_auto_query(db)
            control_manual_query = _control_manual_query(db)
            control_uncertain_query = _control_uncertain_query(db)

            country_auto_query = _country_auto_query(db)
            country_manual_query = _country_manual_query(db)
            country_uncertain_query = _country_uncertain_query(db)

            anomalies: list[str] = []
            if (
                normalized_engine_mode == "legacy"
                and holding_ratio_scale == "fraction_0_to_1"
            ):
                anomalies.append(
                    "Detected shareholder_structures.holding_ratio values in 0~1 scale. "
                    "The recompute task will normalize them to 0~100 in memory before "
                    "calling the legacy ownership-penetration algorithm."
                )
            if control_uncertain_query.count():
                anomalies.append(
                    "Some control_relationships rows could not be safely classified as "
                    "auto/manual; those rows will be preserved and their companies "
                    "will be blocked from auto control rewrites."
                )
            if country_uncertain_query.count():
                anomalies.append(
                    "Some country_attributions rows could not be safely classified as "
                    "auto/manual; those rows will be preserved and their companies "
                    "will be blocked from auto country rewrites."
                )

            control_review_status_distribution = _distribution_dict(
                db.query(ControlRelationship.review_status, func.count())
                .group_by(ControlRelationship.review_status)
                .order_by(func.count().desc())
                .all()
            )
            country_source_mode_distribution = _distribution_dict(
                db.query(CountryAttribution.source_mode, func.count())
                .group_by(CountryAttribution.source_mode)
                .order_by(func.count().desc())
                .all()
            )
            country_manual_distribution = _distribution_dict(
                db.query(CountryAttribution.is_manual, func.count())
                .group_by(CountryAttribution.is_manual)
                .order_by(func.count().desc())
                .all()
            )

            return RecomputePlan(
                database_path=resolved_path,
                selected_reason=selected_reason,
                schema_issues=schema_issues,
                relevant_columns=relevant_columns,
                holding_ratio_scale=holding_ratio_scale,
                holding_ratio_min=holding_ratio_min,
                holding_ratio_max=holding_ratio_max,
                companies_total=companies_total,
                companies_with_mapped_entity=companies_with_mapped_entity,
                companies_with_current_incoming_edges=companies_with_current_incoming_edges,
                control_auto_rows_to_delete=control_auto_query.count(),
                control_manual_rows_to_preserve=control_manual_query.count(),
                control_uncertain_rows_to_preserve=control_uncertain_query.count(),
                country_auto_rows_to_delete=country_auto_query.count(),
                country_manual_rows_to_preserve=country_manual_query.count(),
                country_uncertain_rows_to_preserve=country_uncertain_query.count(),
                control_review_status_distribution=control_review_status_distribution,
                country_source_mode_distribution=country_source_mode_distribution,
                country_manual_distribution=country_manual_distribution,
                control_manual_company_ids=_distinct_company_ids(
                    control_manual_query,
                    ControlRelationship,
                ),
                control_uncertain_company_ids=_distinct_company_ids(
                    control_uncertain_query,
                    ControlRelationship,
                ),
                country_manual_company_ids=_distinct_company_ids(
                    country_manual_query,
                    CountryAttribution,
                ),
                country_uncertain_company_ids=_distinct_company_ids(
                    country_uncertain_query,
                    CountryAttribution,
                ),
                anomalies=anomalies,
            )
    finally:
        engine.dispose()


def preview_recompute(
    database_path: str,
    *,
    engine_mode: str = DEFAULT_ENGINE_MODE,
) -> dict[str, Any]:
    normalized_engine_mode = _normalize_engine_mode(engine_mode)
    return _build_recompute_plan(
        database_path,
        engine_mode=normalized_engine_mode,
    ).to_preview_dict(engine_mode=normalized_engine_mode)


def _recompute_note(
    *,
    run_id: str,
    generated_at: str,
    replaced_old_auto_results: bool,
    analysis_method: str,
) -> str:
    return (
        "AUTO: generated by ownership penetration | "
        f"recompute_run={run_id} | operation=recompute | generated_at={generated_at} | "
        f"method={analysis_method} | "
        f"replaced_old_auto_results={str(replaced_old_auto_results).lower()}"
    )


def _control_basis_payload(
    *,
    prepared_result: dict[str, Any],
    candidate: dict[str, Any],
    run_id: str,
    generated_at: str,
    replaced_old_auto_results: bool,
) -> str:
    target_entity: ShareholderEntity = prepared_result["target_entity"]
    payload = {
        "analysis": "ownership_penetration",
        "as_of": generated_at[:10],
        "path_count": len(candidate["paths"]),
        "target_entity_id": target_entity.id,
        "total_ratio_pct": _serialize_decimal(candidate["total_ratio_pct"]),
        "audit": {
            "operation": "recompute",
            "run_id": run_id,
            "generated_at": generated_at,
            "method": "current algorithm recompute",
            "replaced_old_auto_results": replaced_old_auto_results,
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _country_basis_payload(
    *,
    prepared_result: dict[str, Any],
    run_id: str,
    generated_at: str,
    replaced_old_auto_results: bool,
) -> str:
    payload = {
        "analysis": "ownership_penetration",
        "as_of": generated_at[:10],
        "attribution_type": prepared_result["attribution_type"],
        "actual_control_country": prepared_result["actual_control_country"],
        "actual_controller_entity_id": prepared_result["actual_controller_entity_id"],
        "audit": {
            "operation": "recompute",
            "run_id": run_id,
            "generated_at": generated_at,
            "method": "current algorithm recompute",
            "replaced_old_auto_results": replaced_old_auto_results,
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _unified_control_basis_payload(
    *,
    result,
    candidate,
    context,
    run_id: str,
    generated_at: str,
    replaced_old_auto_results: bool,
) -> str:
    payload = json.loads(
        _build_unified_basis_payload(
            result=result,
            candidate=candidate,
            context=context,
        )
    )
    payload["audit"] = {
        "operation": "recompute",
        "run_id": run_id,
        "generated_at": generated_at,
        "method": "unified_control_inference_v2",
        "replaced_old_auto_results": replaced_old_auto_results,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _unified_country_basis_payload(
    *,
    result,
    context,
    run_id: str,
    generated_at: str,
    replaced_old_auto_results: bool,
) -> str:
    payload = json.loads(
        _build_unified_country_basis_payload(
            result=result,
            context=context,
        )
    )
    payload["audit"] = {
        "operation": "recompute",
        "run_id": run_id,
        "generated_at": generated_at,
        "method": "unified_control_inference_v2",
        "replaced_old_auto_results": replaced_old_auto_results,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _company_from_context(context, company_id: int) -> tuple[Company, ShareholderEntity]:
    company = context.company_map.get(company_id)
    target_entity = context.entity_by_company_id.get(company_id)
    if company is None:
        raise ValueError("Company not found in ownership analysis context.")
    if target_entity is None:
        raise ValueError("Mapped shareholder entity not found for company.")
    return company, target_entity


def _backup_database(database_path: Path, run_id: str) -> Path:
    backup_path = database_path.with_name(
        f"{database_path.stem}_before_recompute_{run_id}{database_path.suffix}"
    )
    shutil.copy2(database_path, backup_path)
    return backup_path


def _insert_control_rows(
    db: Session,
    *,
    prepared_result: dict[str, Any],
    run_id: str,
    generated_at: str,
    replaced_old_auto_results: bool,
) -> int:
    company: Company = prepared_result["company"]
    candidate_results: list[dict[str, Any]] = prepared_result["candidate_results"]
    actual_controller = prepared_result["actual_controller"]
    inserted = 0

    for candidate in candidate_results:
        controller_entity = candidate["entity"]
        is_actual_controller = (
            actual_controller is not None
            and controller_entity.id == actual_controller["entity_id"]
        )
        db.add(
            ControlRelationship(
                company_id=company.id,
                controller_entity_id=controller_entity.id,
                controller_name=controller_entity.entity_name,
                controller_type=controller_entity.entity_type,
                control_type=(
                    "direct_equity_control"
                    if is_actual_controller
                    else "significant_equity"
                ),
                control_ratio=_quantize_pct(candidate["total_ratio_pct"]),
                control_path=_serialize_paths(candidate["paths"]),
                is_actual_controller=is_actual_controller,
                basis=_control_basis_payload(
                    prepared_result=prepared_result,
                    candidate=candidate,
                    run_id=run_id,
                    generated_at=generated_at,
                    replaced_old_auto_results=replaced_old_auto_results,
                ),
                notes=_recompute_note(
                    run_id=run_id,
                    generated_at=generated_at,
                    replaced_old_auto_results=replaced_old_auto_results,
                    analysis_method="ownership_penetration_legacy",
                ),
                control_mode="numeric",
                semantic_flags=None,
                review_status="auto",
            )
        )
        inserted += 1
    return inserted


def _insert_country_row(
    db: Session,
    *,
    prepared_result: dict[str, Any],
    run_id: str,
    generated_at: str,
    replaced_old_auto_results: bool,
) -> int:
    company: Company = prepared_result["company"]
    attribution_type: str = prepared_result["attribution_type"]

    db.add(
        CountryAttribution(
            company_id=company.id,
            incorporation_country=company.incorporation_country,
            listing_country=company.listing_country,
            actual_control_country=prepared_result["actual_control_country"],
            attribution_type=attribution_type,
            basis=_country_basis_payload(
                prepared_result=prepared_result,
                run_id=run_id,
                generated_at=generated_at,
                replaced_old_auto_results=replaced_old_auto_results,
            ),
            is_manual=False,
            notes=_recompute_note(
                run_id=run_id,
                generated_at=generated_at,
                replaced_old_auto_results=replaced_old_auto_results,
                analysis_method="ownership_penetration_legacy",
            ),
            source_mode=(
                "fallback_rule"
                if attribution_type.startswith("fallback_")
                else "control_chain_analysis"
            ),
        )
    )
    return 1


def _insert_control_rows_unified(
    db: Session,
    *,
    result,
    context,
    run_id: str,
    generated_at: str,
    replaced_old_auto_results: bool,
) -> int:
    inserted = 0

    for candidate in result.candidates:
        controller_entity = context.entity_map[candidate.controller_entity_id]
        is_actual_controller = (
            result.actual_controller_entity_id is not None
            and controller_entity.id == result.actual_controller_entity_id
        )
        semantic_flags = _semantic_flags_for_storage(candidate.semantic_flags)
        review_status = (
            "needs_review"
            if semantic_flags and "needs_review" in semantic_flags
            else "auto"
        )

        db.add(
            ControlRelationship(
                company_id=result.company.id,
                controller_entity_id=controller_entity.id,
                controller_name=controller_entity.entity_name,
                controller_type=controller_entity.entity_type,
                control_type=_control_type_from_candidate(candidate),
                control_ratio=_quantize_pct(unit_to_pct(candidate.total_score)),
                control_path=_serialize_unified_paths(
                    candidate.path_states,
                    context=context,
                ),
                is_actual_controller=is_actual_controller,
                basis=_unified_control_basis_payload(
                    result=result,
                    candidate=candidate,
                    context=context,
                    run_id=run_id,
                    generated_at=generated_at,
                    replaced_old_auto_results=replaced_old_auto_results,
                ),
                notes=_recompute_note(
                    run_id=run_id,
                    generated_at=generated_at,
                    replaced_old_auto_results=replaced_old_auto_results,
                    analysis_method="unified_control_inference_v2",
                ),
                control_mode=candidate.control_mode,
                semantic_flags=(
                    json.dumps(semantic_flags, ensure_ascii=False, sort_keys=True)
                    if semantic_flags is not None
                    else None
                ),
                review_status=review_status,
            )
        )
        inserted += 1
    return inserted


def _insert_country_row_unified(
    db: Session,
    *,
    result,
    context,
    run_id: str,
    generated_at: str,
    replaced_old_auto_results: bool,
) -> int:
    attribution_type = result.attribution_type
    if attribution_type.startswith("fallback_"):
        source_mode = "fallback_rule"
    elif attribution_type in {"mixed_control", "joint_control"}:
        source_mode = "hybrid"
    else:
        source_mode = "control_chain_analysis"

    db.add(
        CountryAttribution(
            company_id=result.company.id,
            incorporation_country=result.company.incorporation_country,
            listing_country=result.company.listing_country,
            actual_control_country=result.actual_control_country,
            attribution_type=attribution_type,
            basis=_unified_country_basis_payload(
                result=result,
                context=context,
                run_id=run_id,
                generated_at=generated_at,
                replaced_old_auto_results=replaced_old_auto_results,
            ),
            is_manual=False,
            notes=_recompute_note(
                run_id=run_id,
                generated_at=generated_at,
                replaced_old_auto_results=replaced_old_auto_results,
                analysis_method="unified_control_inference_v2",
            ),
            source_mode=source_mode,
        )
    )
    return 1


def _delete_auto_control_rows(db: Session, company_id: int) -> int:
    return (
        _control_auto_query(db)
        .filter(ControlRelationship.company_id == company_id)
        .delete(synchronize_session=False)
    )


def _delete_auto_country_rows(db: Session, company_id: int) -> int:
    return (
        _country_auto_query(db)
        .filter(CountryAttribution.company_id == company_id)
        .delete(synchronize_session=False)
    )


def _safe_json_loads(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _collect_validation_summary(
    database_path: Path,
    *,
    run_id: str,
) -> dict[str, Any]:
    engine, session_factory = _create_session_factory(database_path)
    try:
        with session_factory() as db:
            control_generated = (
                db.query(ControlRelationship)
                .filter(ControlRelationship.notes.like(f"%recompute_run={run_id}%"))
                .count()
            )
            country_generated = (
                db.query(CountryAttribution)
                .filter(CountryAttribution.notes.like(f"%recompute_run={run_id}%"))
                .count()
            )
            companies_without_control = (
                db.query(Company.id)
                .filter(
                    ~Company.id.in_(
                        db.query(ControlRelationship.company_id).distinct()
                    )
                )
                .order_by(Company.id.asc())
                .all()
            )
            companies_without_country = (
                db.query(Company.id)
                .filter(
                    ~Company.id.in_(
                        db.query(CountryAttribution.company_id).distinct()
                    )
                )
                .order_by(Company.id.asc())
                .all()
            )
            companies_without_any_analysis = (
                db.query(Company.id)
                .filter(
                    ~Company.id.in_(
                        db.query(ControlRelationship.company_id).distinct()
                    )
                )
                .filter(
                    ~Company.id.in_(
                        db.query(CountryAttribution.company_id).distinct()
                    )
                )
                .order_by(Company.id.asc())
                .all()
            )

            duplicate_control_rows = (
                db.query(
                    ControlRelationship.company_id,
                    ControlRelationship.controller_entity_id,
                    ControlRelationship.review_status,
                )
                .group_by(
                    ControlRelationship.company_id,
                    ControlRelationship.controller_entity_id,
                    ControlRelationship.review_status,
                )
                .having(func.count() > 1)
                .count()
            )
            duplicate_new_control_rows = (
                db.query(
                    ControlRelationship.company_id,
                    ControlRelationship.controller_entity_id,
                )
                .filter(ControlRelationship.notes.like(f"%recompute_run={run_id}%"))
                .group_by(
                    ControlRelationship.company_id,
                    ControlRelationship.controller_entity_id,
                )
                .having(func.count() > 1)
                .count()
            )
            duplicate_country_rows = (
                db.query(CountryAttribution.company_id)
                .group_by(CountryAttribution.company_id)
                .having(func.count() > 1)
                .count()
            )
            duplicate_new_country_rows = (
                db.query(CountryAttribution.company_id)
                .filter(CountryAttribution.notes.like(f"%recompute_run={run_id}%"))
                .group_by(CountryAttribution.company_id)
                .having(func.count() > 1)
                .count()
            )

            invalid_control_ratio_rows = (
                db.query(ControlRelationship)
                .filter(ControlRelationship.control_ratio.is_not(None))
                .filter(
                    or_(
                        ControlRelationship.control_ratio < Decimal("0"),
                        ControlRelationship.control_ratio > Decimal("100"),
                    )
                )
                .count()
            )
            invalid_new_control_ratio_rows = (
                db.query(ControlRelationship)
                .filter(ControlRelationship.notes.like(f"%recompute_run={run_id}%"))
                .filter(ControlRelationship.control_ratio.is_not(None))
                .filter(
                    or_(
                        ControlRelationship.control_ratio < Decimal("0"),
                        ControlRelationship.control_ratio > Decimal("100"),
                    )
                )
                .count()
            )
            null_control_company_id_rows = (
                db.query(ControlRelationship)
                .filter(ControlRelationship.company_id.is_(None))
                .count()
            )
            null_country_company_id_rows = (
                db.query(CountryAttribution)
                .filter(CountryAttribution.company_id.is_(None))
                .count()
            )

            invalid_control_path_rows = 0
            invalid_new_control_path_rows = 0
            for relationship in db.query(ControlRelationship).all():
                payload = _safe_json_loads(relationship.control_path)
                is_valid = (
                    isinstance(payload, list)
                    and all(
                        isinstance(item, dict)
                        and isinstance(item.get("path_entity_ids"), list)
                        and isinstance(item.get("path_entity_names"), list)
                        for item in payload
                    )
                )
                if not is_valid:
                    invalid_control_path_rows += 1
                    if relationship.notes and f"recompute_run={run_id}" in relationship.notes:
                        invalid_new_control_path_rows += 1

            return {
                "control_relationships_generated": control_generated,
                "country_attributions_generated": country_generated,
                "companies_without_control_relationships": [
                    int(company_id) for (company_id,) in companies_without_control
                ],
                "companies_without_country_attributions": [
                    int(company_id) for (company_id,) in companies_without_country
                ],
                "companies_without_any_analysis": [
                    int(company_id) for (company_id,) in companies_without_any_analysis
                ],
                "duplicate_control_rows_overall": duplicate_control_rows,
                "duplicate_control_rows_new_run": duplicate_new_control_rows,
                "duplicate_country_rows_overall": duplicate_country_rows,
                "duplicate_country_rows_new_run": duplicate_new_country_rows,
                "null_control_company_id_rows": null_control_company_id_rows,
                "null_country_company_id_rows": null_country_company_id_rows,
                "invalid_control_ratio_rows_overall": invalid_control_ratio_rows,
                "invalid_control_ratio_rows_new_run": invalid_new_control_ratio_rows,
                "invalid_control_path_rows_overall": invalid_control_path_rows,
                "invalid_control_path_rows_new_run": invalid_new_control_path_rows,
            }
    finally:
        engine.dispose()


def _sample_company_ids(company_ids: list[int], *, run_id: str, limit: int = 3) -> list[int]:
    if not company_ids:
        return []
    if len(company_ids) <= limit:
        return sorted(company_ids)
    rng = random.Random(run_id)
    return sorted(rng.sample(company_ids, limit))


def _build_sample_entry(
    context,
    company_id: int,
    *,
    engine_mode: str = DEFAULT_ENGINE_MODE,
) -> dict[str, Any]:
    company, target_entity = _company_from_context(context, company_id)
    normalized_engine_mode = _normalize_engine_mode(engine_mode)

    if normalized_engine_mode == "legacy":
        prepared_result = _prepare_candidate_results(
            company=company,
            target_entity=target_entity,
            context=context,
            max_depth=DEFAULT_MAX_DEPTH,
            min_path_ratio_pct=unit_to_pct(DEFAULT_MIN_PATH_SCORE),
            majority_threshold_pct=unit_to_pct(DEFAULT_CONTROL_THRESHOLD),
            disclosure_threshold_pct=unit_to_pct(DEFAULT_DISCLOSURE_THRESHOLD),
        )
        unified_result = None
    else:
        unified_result = infer_controllers(
            context,
            company_id,
            max_depth=DEFAULT_MAX_DEPTH,
            min_path_score=DEFAULT_MIN_PATH_SCORE,
            control_threshold=DEFAULT_CONTROL_THRESHOLD,
            significant_threshold=DEFAULT_SIGNIFICANT_THRESHOLD,
            disclosure_threshold=DEFAULT_DISCLOSURE_THRESHOLD,
            aggregator=DEFAULT_AGGREGATOR,
        )
        prepared_result = None

    base_edges = []
    if normalized_engine_mode == "legacy":
        for edge in context.incoming_map.get(target_entity.id, []):
            controller_entity = context.entity_map.get(edge.from_entity_id)
            base_edges.append(
                {
                    "from_entity_id": edge.from_entity_id,
                    "from_entity_name": (
                        controller_entity.entity_name if controller_entity is not None else None
                    ),
                    "holding_ratio_pct": (
                        _serialize_decimal(edge.holding_ratio)
                        if edge.holding_ratio is not None
                        else None
                    ),
                    "relation_type": edge.relation_type,
                    "control_type": edge.control_type,
                }
            )
    else:
        for factor in context.incoming_factor_map.get(target_entity.id, []):
            controller_entity = context.entity_map.get(factor.from_entity_id)
            base_edges.append(
                {
                    "from_entity_id": factor.from_entity_id,
                    "from_entity_name": (
                        controller_entity.entity_name if controller_entity is not None else None
                    ),
                    "holding_ratio_pct": _serialize_decimal(unit_to_pct(factor.numeric_factor))
                    if factor.relation_type == "equity"
                    else None,
                    "relation_type": factor.relation_type,
                    "control_type": factor.relation_type,
                }
            )

    control_chain = []
    if normalized_engine_mode == "legacy":
        for candidate in prepared_result["candidate_results"][:3]:
            paths = _safe_json_loads(_serialize_paths(candidate["paths"])) or []
            control_chain.append(
                {
                    "controller_entity_id": candidate["entity_id"],
                    "controller_name": candidate["entity"].entity_name,
                    "total_ratio_pct": _serialize_decimal(candidate["total_ratio_pct"]),
                    "path_count": len(candidate["paths"]),
                    "paths": paths[:2],
                    "is_actual_controller": (
                        prepared_result["actual_controller"] is not None
                        and candidate["entity_id"]
                        == prepared_result["actual_controller"]["entity_id"]
                    ),
                }
            )
    else:
        for candidate in unified_result.candidates[:3]:
            paths = _safe_json_loads(
                _serialize_unified_paths(candidate.top_paths, context=context)
            ) or []
            control_chain.append(
                {
                    "controller_entity_id": candidate.controller_entity_id,
                    "controller_name": context.entity_map[candidate.controller_entity_id].entity_name,
                    "total_ratio_pct": _serialize_decimal(unit_to_pct(candidate.total_score)),
                    "path_count": len(candidate.path_states),
                    "paths": paths[:2],
                    "is_actual_controller": (
                        unified_result.actual_controller_entity_id is not None
                        and candidate.controller_entity_id
                        == unified_result.actual_controller_entity_id
                    ),
                }
            )

    actual_controller = None
    if normalized_engine_mode == "legacy":
        if prepared_result["actual_controller"] is not None:
            actual_controller = {
                "entity_id": prepared_result["actual_controller"]["entity_id"],
                "entity_name": prepared_result["actual_controller"]["entity"].entity_name,
                "total_ratio_pct": _serialize_decimal(
                    prepared_result["actual_controller"]["total_ratio_pct"]
                ),
            }
    elif unified_result.actual_controller_entity_id is not None:
        winning_candidate = next(
            (
                candidate
                for candidate in unified_result.candidates
                if candidate.controller_entity_id == unified_result.actual_controller_entity_id
            ),
            None,
        )
        if winning_candidate is not None:
            actual_controller = {
                "entity_id": winning_candidate.controller_entity_id,
                "entity_name": context.entity_map[
                    winning_candidate.controller_entity_id
                ].entity_name,
                "total_ratio_pct": _serialize_decimal(
                    unit_to_pct(winning_candidate.total_score)
                ),
            }

    return {
        "company_id": company.id,
        "company_name": company.name,
        "target_entity_id": target_entity.id,
        "base_edges": base_edges[:5],
        "control_chain": control_chain,
        "actual_controller": actual_controller,
        "country_attribution": {
            "actual_control_country": (
                prepared_result["actual_control_country"]
                if normalized_engine_mode == "legacy"
                else unified_result.actual_control_country
            ),
            "attribution_type": (
                prepared_result["attribution_type"]
                if normalized_engine_mode == "legacy"
                else unified_result.attribution_type
            ),
        },
    }


def _write_report(
    *,
    report_path: Path,
    summary: dict[str, Any],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Recompute Report {summary['run_id']}",
        "",
        "## Database",
        f"- Target database path: `{summary['target_database_path']}`",
        f"- Backup database path: `{summary['backup_database_path']}`",
        f"- Selected reason: {summary['selected_reason']}",
        (
            f"- holding_ratio scale detected: {summary['ratio_scale']['holding_ratio_scale']} "
            f"(min={summary['ratio_scale']['holding_ratio_min']}, "
            f"max={summary['ratio_scale']['holding_ratio_max']})"
        ),
        "",
        "## Strategy",
        "- Strategy: company-granular transaction (`per_company_transaction`)",
        (
            "- Reason: compute first, then delete old auto rows and write new rows "
            "inside one company transaction so a single failure only rolls back that "
            "company."
        ),
        "",
        "## Delete Plan Applied",
        (
            f"- control_relationships auto rows deleted: "
            f"{summary['deleted_rows']['control_relationships']}"
        ),
        (
            f"- country_attributions auto rows deleted: "
            f"{summary['deleted_rows']['country_attributions']}"
        ),
        "",
        "## Preserved Manual Or Suspected Manual Rows",
        (
            f"- Preserved manual control rows: "
            f"{summary['preserved_rows']['control_relationships_manual']}"
        ),
        (
            f"- Preserved uncertain control rows: "
            f"{summary['preserved_rows']['control_relationships_uncertain']}"
        ),
        (
            f"- Preserved manual country rows: "
            f"{summary['preserved_rows']['country_attributions_manual']}"
        ),
        (
            f"- Preserved uncertain country rows: "
            f"{summary['preserved_rows']['country_attributions_uncertain']}"
        ),
        (
            f"- Companies blocked from auto control rewrites: "
            f"{summary['blocked_company_counts']['control']}"
        ),
        (
            f"- Companies blocked from auto country rewrites: "
            f"{summary['blocked_company_counts']['country']}"
        ),
        "",
        "## Recompute Outcome",
        f"- Companies processed: {summary['companies_processed']}",
        f"- Success count: {summary['success_count']}",
        f"- Failure count: {summary['failure_count']}",
        (
            f"- Control rewrite skipped due to manual/uncertain rows: "
            f"{summary['control_write_skipped_count']}"
        ),
        (
            f"- Country rewrite skipped due to manual/uncertain rows: "
            f"{summary['country_write_skipped_count']}"
        ),
        (
            f"- New control_relationships rows inserted: "
            f"{summary['inserted_rows']['control_relationships']}"
        ),
        (
            f"- New country_attributions rows inserted: "
            f"{summary['inserted_rows']['country_attributions']}"
        ),
        "",
        "## Validation",
        (
            f"- control_relationships generated in this run: "
            f"{summary['validation']['control_relationships_generated']}"
        ),
        (
            f"- country_attributions generated in this run: "
            f"{summary['validation']['country_attributions_generated']}"
        ),
        (
            f"- Companies without control_relationships after run: "
            f"{len(summary['validation']['companies_without_control_relationships'])}"
        ),
        (
            f"- Companies without country_attributions after run: "
            f"{len(summary['validation']['companies_without_country_attributions'])}"
        ),
        (
            f"- Companies without any analysis after run: "
            f"{len(summary['validation']['companies_without_any_analysis'])}"
        ),
        (
            f"- Duplicate control rows overall: "
            f"{summary['validation']['duplicate_control_rows_overall']}"
        ),
        (
            f"- Duplicate control rows from this run: "
            f"{summary['validation']['duplicate_control_rows_new_run']}"
        ),
        (
            f"- Duplicate country rows overall: "
            f"{summary['validation']['duplicate_country_rows_overall']}"
        ),
        (
            f"- Duplicate country rows from this run: "
            f"{summary['validation']['duplicate_country_rows_new_run']}"
        ),
        (
            f"- Null company_id rows in control_relationships: "
            f"{summary['validation']['null_control_company_id_rows']}"
        ),
        (
            f"- Null company_id rows in country_attributions: "
            f"{summary['validation']['null_country_company_id_rows']}"
        ),
        (
            f"- Invalid control_ratio rows overall: "
            f"{summary['validation']['invalid_control_ratio_rows_overall']}"
        ),
        (
            f"- Invalid control_ratio rows from this run: "
            f"{summary['validation']['invalid_control_ratio_rows_new_run']}"
        ),
        (
            f"- Invalid control_path rows overall: "
            f"{summary['validation']['invalid_control_path_rows_overall']}"
        ),
        (
            f"- Invalid control_path rows from this run: "
            f"{summary['validation']['invalid_control_path_rows_new_run']}"
        ),
        "",
        "## Failed Companies",
    ]

    if summary["failed_company_ids"]:
        lines.extend(
            [
                f"- Failed company IDs: {summary['failed_company_ids']}",
                f"- Failure details: {json.dumps(summary['failure_details'], ensure_ascii=False, indent=2)}",
            ]
        )
    else:
        lines.append("- Failed company IDs: []")

    lines.extend(
        [
            "",
            "## Core Analysis Functions",
        ]
    )
    for function_name in summary["core_analysis_functions"]:
        lines.append(f"- {function_name}")

    lines.extend(
        [
            "",
            "## Random Samples",
        ]
    )
    if summary["samples"]:
        for sample in summary["samples"]:
            lines.append(
                f"- Company {sample['company_id']} / {sample['company_name']}: "
                f"{json.dumps(sample, ensure_ascii=False)}"
            )
    else:
        lines.append("- No sample companies were available for this run.")

    lines.extend(
        [
            "",
            "## Anomalies",
        ]
    )
    if summary["anomalies"]:
        for anomaly in summary["anomalies"]:
            lines.append(f"- {anomaly}")
    else:
        lines.append("- None.")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_recompute(
    database_path: str,
    *,
    engine_mode: str = DEFAULT_ENGINE_MODE,
) -> dict[str, Any]:
    normalized_engine_mode = _normalize_engine_mode(engine_mode)
    plan = _build_recompute_plan(
        database_path,
        engine_mode=normalized_engine_mode,
    )
    if plan.schema_issues:
        raise RuntimeError(
            "Current database schema is incompatible with recompute task: "
            + "; ".join(plan.schema_issues)
        )

    run_started_at = datetime.now().astimezone()
    run_id = run_started_at.strftime(RUN_ID_FORMAT)
    generated_at = run_started_at.isoformat()
    backup_path = _backup_database(plan.database_path, run_id)

    read_engine, read_session_factory = _create_session_factory(plan.database_path)
    try:
        with read_session_factory() as read_db:
            if normalized_engine_mode == "legacy":
                context = build_ownership_analysis_context(
                    read_db,
                    as_of=run_started_at.date(),
                )
                _normalize_context_holding_ratios(
                    context,
                    holding_ratio_scale=plan.holding_ratio_scale,
                )
            else:
                context = build_control_context(
                    read_db,
                    as_of=run_started_at.date(),
                )
    finally:
        read_engine.dispose()

    write_engine, write_session_factory = _create_session_factory(plan.database_path)
    try:
        inserted_control_rows = 0
        inserted_country_rows = 0
        deleted_control_rows = 0
        deleted_country_rows = 0
        success_count = 0
        failed_company_ids: list[int] = []
        failure_details: dict[int, str] = {}
        control_write_skipped_count = 0
        country_write_skipped_count = 0
        samples_source_company_ids: list[int] = []

        company_ids = sorted(context.company_map)

        for company_id in company_ids:
            try:
                if normalized_engine_mode == "legacy":
                    company, target_entity = _company_from_context(context, company_id)
                    prepared_result = _prepare_candidate_results(
                        company=company,
                        target_entity=target_entity,
                        context=context,
                        max_depth=DEFAULT_MAX_DEPTH,
                        min_path_ratio_pct=unit_to_pct(DEFAULT_MIN_PATH_SCORE),
                        majority_threshold_pct=unit_to_pct(DEFAULT_CONTROL_THRESHOLD),
                        disclosure_threshold_pct=unit_to_pct(DEFAULT_DISCLOSURE_THRESHOLD),
                    )
                    unified_result = None
                else:
                    unified_result = infer_controllers(
                        context,
                        company_id,
                        max_depth=DEFAULT_MAX_DEPTH,
                        min_path_score=DEFAULT_MIN_PATH_SCORE,
                        control_threshold=DEFAULT_CONTROL_THRESHOLD,
                        significant_threshold=DEFAULT_SIGNIFICANT_THRESHOLD,
                        disclosure_threshold=DEFAULT_DISCLOSURE_THRESHOLD,
                        aggregator=DEFAULT_AGGREGATOR,
                    )
                    prepared_result = None

                deleted_control_for_company = 0
                deleted_country_for_company = 0
                inserted_control_for_company = 0
                inserted_country_for_company = 0
                control_write_skipped = False
                country_write_skipped = False

                with write_session_factory() as db:
                    with db.begin():
                        deleted_control_for_company = _delete_auto_control_rows(db, company_id)
                        deleted_country_for_company = _delete_auto_country_rows(db, company_id)

                        if company_id in plan.blocked_control_company_ids:
                            control_write_skipped = True
                        else:
                            if normalized_engine_mode == "legacy":
                                inserted_control_for_company = _insert_control_rows(
                                    db,
                                    prepared_result=prepared_result,
                                    run_id=run_id,
                                    generated_at=generated_at,
                                    replaced_old_auto_results=deleted_control_for_company > 0,
                                )
                            else:
                                inserted_control_for_company = _insert_control_rows_unified(
                                    db,
                                    result=unified_result,
                                    context=context,
                                    run_id=run_id,
                                    generated_at=generated_at,
                                    replaced_old_auto_results=deleted_control_for_company > 0,
                                )

                        if company_id in plan.blocked_country_company_ids:
                            country_write_skipped = True
                        else:
                            if normalized_engine_mode == "legacy":
                                inserted_country_for_company = _insert_country_row(
                                    db,
                                    prepared_result=prepared_result,
                                    run_id=run_id,
                                    generated_at=generated_at,
                                    replaced_old_auto_results=deleted_country_for_company > 0,
                                )
                            else:
                                inserted_country_for_company = _insert_country_row_unified(
                                    db,
                                    result=unified_result,
                                    context=context,
                                    run_id=run_id,
                                    generated_at=generated_at,
                                    replaced_old_auto_results=deleted_country_for_company > 0,
                                )

                deleted_control_rows += deleted_control_for_company
                deleted_country_rows += deleted_country_for_company
                inserted_control_rows += inserted_control_for_company
                inserted_country_rows += inserted_country_for_company
                if control_write_skipped:
                    control_write_skipped_count += 1
                if country_write_skipped:
                    country_write_skipped_count += 1
                success_count += 1
                if company_id not in plan.blocked_control_company_ids:
                    samples_source_company_ids.append(company_id)
            except Exception as exc:
                failed_company_ids.append(company_id)
                failure_details[company_id] = str(exc)

        validation = _collect_validation_summary(plan.database_path, run_id=run_id)
        sample_company_ids = _sample_company_ids(samples_source_company_ids, run_id=run_id)
        samples = [
            _build_sample_entry(
                context,
                company_id,
                engine_mode=normalized_engine_mode,
            )
            for company_id in sample_company_ids
        ]

        anomalies = list(plan.anomalies)
        if validation["invalid_control_path_rows_overall"]:
            anomalies.append(
                "At least some control_path payloads in the database are not valid list-shaped "
                "JSON. Newly written recompute rows are checked separately in validation."
            )
        if validation["duplicate_country_rows_overall"]:
            anomalies.append(
                "country_attributions contains more than one row for some companies overall; "
                "this can be caused by preserved manual rows and should be reviewed."
            )

        report_path = REPORT_OUTPUT_DIR / f"recompute_report_{run_id}.md"
        summary = {
            "run_id": run_id,
            "target_database_path": str(plan.database_path),
            "backup_database_path": str(backup_path),
            "selected_reason": plan.selected_reason,
            "engine_mode": normalized_engine_mode,
            "ratio_scale": {
                "holding_ratio_scale": plan.holding_ratio_scale,
                "holding_ratio_min": plan.holding_ratio_min,
                "holding_ratio_max": plan.holding_ratio_max,
            },
            "deleted_rows": {
                "control_relationships": deleted_control_rows,
                "country_attributions": deleted_country_rows,
            },
            "preserved_rows": {
                "control_relationships_manual": plan.control_manual_rows_to_preserve,
                "control_relationships_uncertain": plan.control_uncertain_rows_to_preserve,
                "country_attributions_manual": plan.country_manual_rows_to_preserve,
                "country_attributions_uncertain": plan.country_uncertain_rows_to_preserve,
            },
            "blocked_company_counts": {
                "control": len(plan.blocked_control_company_ids),
                "country": len(plan.blocked_country_company_ids),
            },
            "companies_processed": len(company_ids),
            "success_count": success_count,
            "failure_count": len(failed_company_ids),
            "failed_company_ids": failed_company_ids,
            "failure_details": failure_details,
            "control_write_skipped_count": control_write_skipped_count,
            "country_write_skipped_count": country_write_skipped_count,
            "inserted_rows": {
                "control_relationships": inserted_control_rows,
                "country_attributions": inserted_country_rows,
            },
            "validation": validation,
            "core_analysis_functions": _core_analysis_functions(normalized_engine_mode),
            "samples": samples,
            "anomalies": anomalies,
            "report_path": str(report_path),
        }
        _write_report(report_path=report_path, summary=summary)
        return summary
    finally:
        write_engine.dispose()


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview or run an audited recompute of analysis-result tables."
    )
    parser.add_argument(
        "--database-path",
        default=str(PROJECT_ROOT / DEFAULT_DATABASE_NAME),
        help="Path to the target SQLite database. Defaults to company_import_test.db.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually back up the database and perform the recompute. Without this flag only preview is shown.",
    )
    parser.add_argument(
        "--engine",
        default=DEFAULT_ENGINE_MODE,
        choices=SUPPORTED_ENGINE_MODES,
        help="Analysis engine used by preview/execute. Defaults to unified.",
    )
    args = parser.parse_args(argv)

    if args.execute:
        result = run_recompute(args.database_path, engine_mode=args.engine)
    else:
        result = preview_recompute(args.database_path, engine_mode=args.engine)

    _print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
