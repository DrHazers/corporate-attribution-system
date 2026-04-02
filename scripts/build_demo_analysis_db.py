from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import backend.models  # noqa: F401
from backend.analysis.control_chain import analyze_control_chain_with_options
from backend.analysis.country_attribution_analysis import (
    analyze_country_attribution_with_options,
)
from backend.analysis.ownership_penetration import refresh_company_control_analysis
from backend.database import Base, ensure_sqlite_schema


DEFAULT_SOURCE_DB = PROJECT_ROOT / "company_test_analysis.db"
DEFAULT_TARGET_DB = PROJECT_ROOT / "company_test_analysis_demo.db"
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / "tests" / "output" / "demo_analysis_samples.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "tests" / "output" / "demo_analysis_samples.md"

EQUITY_CLAUSE = """
(
    ss.relation_type = 'equity'
    OR (ss.relation_type IS NULL AND ss.control_type = 'equity')
    OR (
        ss.relation_type IS NULL
        AND ss.control_type IS NULL
        AND ss.holding_ratio IS NOT NULL
    )
)
"""
SEMANTIC_RELATION_TYPES = "('agreement', 'board_control', 'voting_right', 'nominee', 'vie')"
JOINT_KEYWORDS = ("joint control", "unanimous", "consent of all", "consent of both")


class SampleDefinition(dict):
    key: str
    label: str
    sql: str
    matcher: Callable[[dict[str, Any]], bool]


SAMPLE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "equity_control",
        "label": "Equity Control",
        "sql": f"""
            SELECT DISTINCT c.id
            FROM companies c
            JOIN shareholder_entities se ON se.company_id = c.id
            JOIN shareholder_structures ss ON ss.to_entity_id = se.id
            WHERE ss.is_current = 1
              AND ss.is_direct = 1
              AND {EQUITY_CLAUSE}
            ORDER BY c.id ASC
            LIMIT :limit
        """,
        "matcher": lambda summary: summary.get("control_type") == "equity_control",
    },
    {
        "key": "agreement_control",
        "label": "Agreement Control",
        "sql": """
            SELECT DISTINCT c.id
            FROM companies c
            JOIN shareholder_entities se ON se.company_id = c.id
            JOIN shareholder_structures ss ON ss.to_entity_id = se.id
            WHERE ss.is_current = 1
              AND ss.is_direct = 1
              AND ss.relation_type = 'agreement'
            ORDER BY c.id ASC
            LIMIT :limit
        """,
        "matcher": lambda summary: summary.get("control_type") == "agreement_control",
    },
    {
        "key": "board_control",
        "label": "Board Control",
        "sql": """
            SELECT DISTINCT c.id
            FROM companies c
            JOIN shareholder_entities se ON se.company_id = c.id
            JOIN shareholder_structures ss ON ss.to_entity_id = se.id
            WHERE ss.is_current = 1
              AND ss.is_direct = 1
              AND ss.relation_type = 'board_control'
            ORDER BY c.id ASC
            LIMIT :limit
        """,
        "matcher": lambda summary: summary.get("control_type") == "board_control",
    },
    {
        "key": "mixed_control",
        "label": "Mixed Control",
        "sql": f"""
            SELECT c.id
            FROM companies c
            JOIN shareholder_entities se ON se.company_id = c.id
            JOIN shareholder_structures ss ON ss.to_entity_id = se.id
            WHERE ss.is_current = 1
              AND ss.is_direct = 1
            GROUP BY c.id
            HAVING SUM(CASE WHEN {EQUITY_CLAUSE} THEN 1 ELSE 0 END) > 0
               AND SUM(CASE WHEN ss.relation_type IN {SEMANTIC_RELATION_TYPES} THEN 1 ELSE 0 END) > 0
            ORDER BY c.id ASC
            LIMIT :limit
        """,
        "matcher": lambda summary: summary.get("control_type") == "mixed_control" or summary.get("attribution_type") == "mixed_control",
    },
    {
        "key": "joint_control",
        "label": "Joint Control",
        "sql": """
            SELECT DISTINCT c.id
            FROM companies c
            JOIN shareholder_entities se ON se.company_id = c.id
            JOIN shareholder_structures ss ON ss.to_entity_id = se.id
            WHERE ss.is_current = 1
              AND ss.is_direct = 1
              AND ss.relation_type IN ('agreement', 'board_control', 'voting_right', 'nominee', 'vie')
              AND (
                    LOWER(COALESCE(ss.control_basis, '')) LIKE '%joint control%'
                 OR LOWER(COALESCE(ss.control_basis, '')) LIKE '%unanimous%'
                 OR LOWER(COALESCE(ss.agreement_scope, '')) LIKE '%joint control%'
                 OR LOWER(COALESCE(ss.agreement_scope, '')) LIKE '%unanimous%'
                 OR LOWER(COALESCE(ss.remarks, '')) LIKE '%joint control%'
                 OR LOWER(COALESCE(ss.remarks, '')) LIKE '%unanimous%'
              )
            ORDER BY c.id ASC
            LIMIT :limit
        """,
        "matcher": lambda summary: summary.get("control_type") == "joint_control" or summary.get("attribution_type") == "joint_control",
    },
    {
        "key": "significant_influence",
        "label": "Significant Influence",
        "sql": """
            SELECT DISTINCT c.id
            FROM companies c
            JOIN shareholder_entities se ON se.company_id = c.id
            JOIN shareholder_structures ss ON ss.to_entity_id = se.id
            WHERE ss.is_current = 1
              AND ss.is_direct = 1
              AND ss.relation_type IN ('nominee', 'vie', 'agreement', 'voting_right')
            ORDER BY c.id ASC
            LIMIT :limit
        """,
        "matcher": lambda summary: summary.get("control_type") == "significant_influence",
    },
    {
        "key": "voting_right_semantic",
        "label": "Voting Right Semantic",
        "sql": """
            SELECT DISTINCT c.id
            FROM companies c
            JOIN shareholder_entities se ON se.company_id = c.id
            JOIN shareholder_structures ss ON ss.to_entity_id = se.id
            WHERE ss.is_current = 1
              AND ss.is_direct = 1
              AND ss.relation_type = 'voting_right'
            ORDER BY c.id ASC
            LIMIT :limit
        """,
        "matcher": lambda summary: 'voting_right' in summary.get("semantic_flags", []),
    },
    {
        "key": "nominee_semantic",
        "label": "Nominee Semantic",
        "sql": """
            SELECT DISTINCT c.id
            FROM companies c
            JOIN shareholder_entities se ON se.company_id = c.id
            JOIN shareholder_structures ss ON ss.to_entity_id = se.id
            WHERE ss.is_current = 1
              AND ss.is_direct = 1
              AND ss.relation_type = 'nominee'
            ORDER BY c.id ASC
            LIMIT :limit
        """,
        "matcher": lambda summary: 'nominee' in summary.get("semantic_flags", []),
    },
    {
        "key": "vie_semantic",
        "label": "VIE Semantic",
        "sql": """
            SELECT DISTINCT c.id
            FROM companies c
            JOIN shareholder_entities se ON se.company_id = c.id
            JOIN shareholder_structures ss ON ss.to_entity_id = se.id
            WHERE ss.is_current = 1
              AND ss.is_direct = 1
              AND ss.relation_type = 'vie'
            ORDER BY c.id ASC
            LIMIT :limit
        """,
        "matcher": lambda summary: 'vie' in summary.get("semantic_flags", []),
    },
]



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a demo analysis database and export sample summaries.")
    parser.add_argument("--source-db", default=str(DEFAULT_SOURCE_DB), help="Raw source database path.")
    parser.add_argument("--target-db", default=str(DEFAULT_TARGET_DB), help="Demo database path to build.")
    parser.add_argument("--output-json", default=str(DEFAULT_JSON_OUTPUT), help="JSON output path for sample summaries.")
    parser.add_argument("--output-md", default=str(DEFAULT_MD_OUTPUT), help="Markdown output path for sample summaries.")
    parser.add_argument("--company-id", type=int, action="append", dest="company_ids", help="Additional company_id to refresh in the demo database.")
    parser.add_argument("--search-limit", type=int, default=60, help="Candidate search limit per sample category.")
    return parser.parse_args()



def _prepare_demo_database(source_db: Path, target_db: Path) -> sessionmaker:
    if target_db.exists():
        target_db.unlink()
    shutil.copy2(source_db, target_db)

    engine = create_engine(
        f"sqlite:///{target_db}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    raw_connection = engine.raw_connection()
    try:
        ensure_sqlite_schema(raw_connection)
    finally:
        raw_connection.close()

    return sessionmaker(autocommit=False, autoflush=False, bind=engine)



def _query_company_name(db: Session, company_id: int) -> str:
    row = db.execute(
        text("SELECT name FROM companies WHERE id = :company_id"),
        {"company_id": company_id},
    ).mappings().first()
    return str(row["name"]) if row is not None else f"Company {company_id}"



def _collect_candidate_ids(db: Session, sql: str, limit: int) -> list[int]:
    rows = db.execute(text(sql), {"limit": limit}).fetchall()
    return [int(row[0]) for row in rows]



def _pick_primary_relationship(control_chain: dict[str, Any]) -> dict[str, Any] | None:
    actual_controller = control_chain.get("actual_controller")
    if actual_controller is not None:
        return actual_controller
    relationships = control_chain.get("control_relationships") or []
    return relationships[0] if relationships else None



def _pick_relationship_for_category(
    control_chain: dict[str, Any],
    category_key: str,
) -> dict[str, Any] | None:
    relationships = control_chain.get("control_relationships") or []
    if not relationships:
        return None

    def by_control_type(expected: str) -> dict[str, Any] | None:
        return next(
            (item for item in relationships if item.get("control_type") == expected),
            None,
        )

    def by_semantic_flag(expected: str) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in relationships
                if expected in (item.get("semantic_flags") or [])
            ),
            None,
        )

    if category_key == "equity_control":
        return by_control_type("equity_control") or _pick_primary_relationship(control_chain)
    if category_key == "agreement_control":
        return by_control_type("agreement_control") or _pick_primary_relationship(control_chain)
    if category_key == "board_control":
        return by_control_type("board_control") or by_semantic_flag("board_control") or _pick_primary_relationship(control_chain)
    if category_key == "mixed_control":
        return by_control_type("mixed_control") or _pick_primary_relationship(control_chain)
    if category_key == "joint_control":
        return by_control_type("joint_control") or _pick_primary_relationship(control_chain)
    if category_key == "significant_influence":
        return by_control_type("significant_influence") or _pick_primary_relationship(control_chain)
    if category_key == "voting_right_semantic":
        return by_semantic_flag("voting_right") or _pick_primary_relationship(control_chain)
    if category_key == "nominee_semantic":
        return by_semantic_flag("nominee") or _pick_primary_relationship(control_chain)
    if category_key == "vie_semantic":
        return by_semantic_flag("vie") or _pick_primary_relationship(control_chain)
    return _pick_primary_relationship(control_chain)



def _basis_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return {
        "classification": payload.get("classification"),
        "total_score_pct": payload.get("total_score_pct"),
        "total_confidence": payload.get("total_confidence"),
        "evidence_summary": (payload.get("evidence_summary") or [])[:3],
    }



def _load_analysis_payload(db: Session, company_id: int) -> dict[str, Any]:
    return {
        "company_name": _query_company_name(db, company_id),
        "control_chain": analyze_control_chain_with_options(db, company_id, refresh=False),
        "country_result": analyze_country_attribution_with_options(db, company_id, refresh=False),
    }



def _build_company_summary(
    company_id: int,
    analysis_payload: dict[str, Any],
    *,
    category_key: str,
) -> dict[str, Any]:
    control_chain = analysis_payload["control_chain"]
    country_result = analysis_payload["country_result"]
    primary_relationship = _pick_relationship_for_category(control_chain, category_key)
    country_attribution = country_result.get("country_attribution")

    return {
        "company_id": company_id,
        "company_name": analysis_payload["company_name"],
        "actual_controller_or_candidate": (
            primary_relationship.get("controller_name") if primary_relationship else None
        ),
        "control_type": primary_relationship.get("control_type") if primary_relationship else None,
        "control_mode": primary_relationship.get("control_mode") if primary_relationship else None,
        "attribution_type": (
            country_attribution.get("attribution_type")
            if isinstance(country_attribution, dict)
            else None
        ),
        "actual_control_country": (
            country_attribution.get("actual_control_country")
            if isinstance(country_attribution, dict)
            else None
        ),
        "semantic_flags": (
            primary_relationship.get("semantic_flags") or []
            if primary_relationship
            else []
        ),
        "basis_summary": _basis_summary(
            primary_relationship.get("basis") if primary_relationship else None
        ),
        "controller_count": control_chain.get("controller_count", 0),
        "suitable_for_demo": bool(primary_relationship),
    }



def _refresh_and_load_analysis(
    db: Session,
    company_id: int,
    cache: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    if company_id not in cache:
        refresh_company_control_analysis(db, company_id)
        cache[company_id] = _load_analysis_payload(db, company_id)
    return cache[company_id]



def _find_sample_for_category(
    db: Session,
    definition: dict[str, Any],
    *,
    search_limit: int,
    cache: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    candidate_ids = _collect_candidate_ids(db, definition["sql"], search_limit)
    for company_id in candidate_ids:
        analysis_payload = _refresh_and_load_analysis(db, company_id, cache)
        summary = _build_company_summary(
            company_id,
            analysis_payload,
            category_key=definition["key"],
        )
        if definition["matcher"](summary):
            return {
                "category": definition["key"],
                "label": definition["label"],
                "available": True,
                **summary,
            }

    return {
        "category": definition["key"],
        "label": definition["label"],
        "available": False,
        "reason": "No suitable real sample found in current demo database candidate search.",
    }



def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")



def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Demo Analysis Samples",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Source DB: `{payload['source_db']}`",
        f"- Target DB: `{payload['target_db']}`",
        f"- Refreshed company ids: `{payload['refreshed_company_ids']}`",
        "",
    ]
    for sample in payload["samples"]:
        lines.append(f"## {sample['label']}")
        lines.append("")
        if not sample.get("available"):
            lines.append(f"- Status: unavailable")
            lines.append(f"- Reason: {sample.get('reason')}")
            lines.append("")
            continue
        lines.append(f"- Company: `{sample['company_id']}` / {sample['company_name']}")
        lines.append(f"- Controller or candidate: {sample.get('actual_controller_or_candidate')}")
        lines.append(f"- Control type: {sample.get('control_type')}")
        lines.append(f"- Control mode: {sample.get('control_mode')}")
        lines.append(f"- Attribution type: {sample.get('attribution_type')}")
        lines.append(f"- Actual control country: {sample.get('actual_control_country')}")
        lines.append(f"- Semantic flags: {sample.get('semantic_flags')}")
        lines.append(f"- Basis summary: {sample.get('basis_summary')}")
        lines.append(f"- Suitable for demo: {sample.get('suitable_for_demo')}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")



def main() -> None:
    args = parse_args()
    source_db = Path(args.source_db).resolve()
    target_db = Path(args.target_db).resolve()
    output_json = Path(args.output_json).resolve()
    output_md = Path(args.output_md).resolve()

    session_factory = _prepare_demo_database(source_db, target_db)
    refreshed_company_ids: list[int] = []
    summary_cache: dict[int, dict[str, Any]] = {}

    with session_factory() as db:
        for company_id in sorted(set(args.company_ids or [])):
            _refresh_and_load_analysis(db, company_id, summary_cache)
            refreshed_company_ids.append(company_id)

        samples = []
        for definition in SAMPLE_DEFINITIONS:
            sample = _find_sample_for_category(
                db,
                definition,
                search_limit=args.search_limit,
                cache=summary_cache,
            )
            if sample.get("available"):
                refreshed_company_ids.append(sample["company_id"])
            samples.append(sample)

    refreshed_company_ids = sorted(dict.fromkeys(refreshed_company_ids))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_db": str(source_db),
        "target_db": str(target_db),
        "refreshed_company_ids": refreshed_company_ids,
        "samples": samples,
    }
    _write_json(output_json, payload)
    _write_markdown(output_md, payload)

    print(f"Source DB: {source_db}")
    print(f"Target DB: {target_db}")
    print(f"Refreshed company ids: {refreshed_company_ids}")
    print(f"JSON summary: {output_json}")
    print(f"Markdown summary: {output_md}")


if __name__ == "__main__":
    main()



