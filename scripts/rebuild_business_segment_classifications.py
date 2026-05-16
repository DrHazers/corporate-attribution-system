from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy import text
from sqlalchemy.orm import selectinload, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORT_PATH = PROJECT_ROOT / "export" / "industry_refresh_report.md"
SUMMARY_PATH = PROJECT_ROOT / "logs" / "industry_refresh_summary.json"
FAILED_ROWS_PATH = PROJECT_ROOT / "logs" / "industry_classification_failed_rows.json"
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


def quote_table(engine, table_name: str) -> str:
    return engine.dialect.identifier_preparer.quote(table_name)


def count_table(session, table_name: str) -> int:
    return int(
        session.execute(text(f"SELECT COUNT(*) FROM {quote_table(session.bind, table_name)}")).scalar_one()
    )


def count_protected_tables(session) -> dict[str, int]:
    return {table_name: count_table(session, table_name) for table_name in PROTECTED_TABLES}


def reset_id_sequence(session, table_name: str) -> None:
    sequence_name = session.execute(
        text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
        {"table_name": f"public.{table_name}"},
    ).scalar()
    if not sequence_name:
        return
    table_sql = quote_table(session.bind, table_name)
    max_id = session.execute(text(f"SELECT MAX(id) FROM {table_sql}")).scalar()
    if max_id is None:
        session.execute(
            text("SELECT setval(CAST(:sequence_name AS regclass), 1, false)"),
            {"sequence_name": sequence_name},
        )
    else:
        session.execute(
            text("SELECT setval(CAST(:sequence_name AS regclass), :max_id, true)"),
            {"sequence_name": sequence_name, "max_id": int(max_id)},
        )


def distribution(session, sql: str) -> dict[str, int]:
    rows = session.execute(text(sql)).fetchall()
    return {str(row[0] if row[0] is not None else ""): int(row[1]) for row in rows}


def collect_validation(session) -> dict[str, Any]:
    orphan_classifications = int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM business_segment_classifications c
                LEFT JOIN business_segments b ON b.id = c.business_segment_id
                WHERE b.id IS NULL
                """
            )
        ).scalar_one()
    )
    duplicate_segment_ids = int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT business_segment_id
                    FROM business_segment_classifications
                    GROUP BY business_segment_id
                    HAVING COUNT(*) > 1
                ) duplicated
                """
            )
        ).scalar_one()
    )
    empty_or_unmapped = int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM business_segment_classifications
                WHERE COALESCE(level_1, '') = ''
                  AND COALESCE(level_2, '') = ''
                  AND COALESCE(level_3, '') = ''
                  AND COALESCE(level_4, '') = ''
                """
            )
        ).scalar_one()
    )
    low_confidence = int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM business_segment_classifications
                WHERE confidence IS NULL OR confidence < 0.5
                """
            )
        ).scalar_one()
    )
    orphan_segments = int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM business_segments b
                LEFT JOIN companies c ON c.id = b.company_id
                WHERE c.id IS NULL
                """
            )
        ).scalar_one()
    )
    return {
        "orphan_classification_count": orphan_classifications,
        "duplicate_business_segment_id_count": duplicate_segment_ids,
        "empty_classification_count": empty_or_unmapped,
        "low_confidence_count": low_confidence,
        "orphan_business_segment_company_id_count": orphan_segments,
    }


def collect_summary(session, *, status: str, apply: bool, database_url: str) -> dict[str, Any]:
    validation = collect_validation(session)
    return {
        "status": status,
        "apply": apply,
        "database_url": render_database_url(database_url),
        "business_segments_count": count_table(session, "business_segments"),
        "business_segment_classifications_count": count_table(
            session, "business_segment_classifications"
        ),
        "reporting_period_distribution": distribution(
            session,
            """
            SELECT COALESCE(reporting_period, '') AS reporting_period, COUNT(*)
            FROM business_segments
            GROUP BY COALESCE(reporting_period, '')
            ORDER BY COALESCE(reporting_period, '')
            """,
        ),
        "classification_source_distribution": distribution(
            session,
            """
            SELECT COALESCE(classifier_type, '') AS classifier_type, COUNT(*)
            FROM business_segment_classifications
            GROUP BY COALESCE(classifier_type, '')
            ORDER BY COALESCE(classifier_type, '')
            """,
        ),
        "review_status_distribution": distribution(
            session,
            """
            SELECT COALESCE(review_status, '') AS review_status, COUNT(*)
            FROM business_segment_classifications
            GROUP BY COALESCE(review_status, '')
            ORDER BY COALESCE(review_status, '')
            """,
        ),
        "sector_distribution_top20": distribution(
            session,
            """
            SELECT COALESCE(level_1, '') AS level_1, COUNT(*)
            FROM business_segment_classifications
            GROUP BY COALESCE(level_1, '')
            ORDER BY COUNT(*) DESC, COALESCE(level_1, '')
            LIMIT 20
            """,
        ),
        "industry_group_distribution_top20": distribution(
            session,
            """
            SELECT COALESCE(level_2, '') AS level_2, COUNT(*)
            FROM business_segment_classifications
            GROUP BY COALESCE(level_2, '')
            ORDER BY COUNT(*) DESC, COALESCE(level_2, '')
            LIMIT 20
            """,
        ),
        "industry_distribution_top20": distribution(
            session,
            """
            SELECT COALESCE(level_3, '') AS level_3, COUNT(*)
            FROM business_segment_classifications
            GROUP BY COALESCE(level_3, '')
            ORDER BY COUNT(*) DESC, COALESCE(level_3, '')
            LIMIT 20
            """,
        ),
        "validation": validation,
    }


def load_existing_summary() -> dict[str, Any]:
    if SUMMARY_PATH.exists():
        return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_failed_rows(rows: list[dict[str, Any]]) -> None:
    write_json(
        FAILED_ROWS_PATH,
        {
            "failed_count": len(rows),
            "failed_rows": rows,
        },
    )


def write_report(payload: dict[str, Any]) -> None:
    import_summary = payload.get("import", {})
    rebuild_summary = payload.get("classification_rebuild", {})
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Industry Refresh Report",
        "",
        f"- DATABASE_URL: `{rebuild_summary.get('database_url') or import_summary.get('database_url', '')}`",
        f"- Success: `{payload.get('success', False)}`",
        "",
        "## Import",
        "",
        f"- Pre business_segments rows: `{import_summary.get('pre_counts', {}).get('business_segments', '')}`",
        f"- Pre business_segment_classifications rows: `{import_summary.get('pre_counts', {}).get('business_segment_classifications', '')}`",
        f"- Post business_segments rows: `{import_summary.get('post_counts', {}).get('business_segments', '')}`",
        f"- Covered company count: `{import_summary.get('csv_summary', {}).get('company_count', '')}`",
        f"- Orphan company_id count: `{import_summary.get('database_checks', {}).get('orphan_company_id_count', '')}`",
        f"- Invalid revenue_ratio group count: `{import_summary.get('csv_summary', {}).get('invalid_revenue_ratio_group_count', '')}`",
        "",
        "## Classification Rebuild",
        "",
        f"- Business segment rows: `{rebuild_summary.get('business_segments_count', '')}`",
        f"- Classification rows: `{rebuild_summary.get('business_segment_classifications_count', '')}`",
        f"- Orphan classification count: `{rebuild_summary.get('validation', {}).get('orphan_classification_count', '')}`",
        f"- Duplicate business_segment_id count: `{rebuild_summary.get('validation', {}).get('duplicate_business_segment_id_count', '')}`",
        f"- Empty classification count: `{rebuild_summary.get('validation', {}).get('empty_classification_count', '')}`",
        f"- Low confidence count: `{rebuild_summary.get('validation', {}).get('low_confidence_count', '')}`",
        f"- Failed row count: `{rebuild_summary.get('failed_count', '')}`",
        "",
        "## Reporting Period Distribution",
        "",
    ]
    for period, count in (rebuild_summary.get("reporting_period_distribution") or {}).items():
        lines.append(f"- `{period}`: `{count}`")

    lines.extend(["", "## Classification Source Distribution", ""])
    for source, count in (rebuild_summary.get("classification_source_distribution") or {}).items():
        lines.append(f"- `{source}`: `{count}`")

    lines.extend(["", "## Sector Distribution Top 20", ""])
    for sector, count in (rebuild_summary.get("sector_distribution_top20") or {}).items():
        lines.append(f"- `{sector or '(empty)'}`: `{count}`")

    lines.extend(["", "## Industry Group Distribution Top 20", ""])
    for group, count in (rebuild_summary.get("industry_group_distribution_top20") or {}).items():
        lines.append(f"- `{group or '(empty)'}`: `{count}`")

    lines.extend(["", "## Industry Distribution Top 20", ""])
    for industry, count in (rebuild_summary.get("industry_distribution_top20") or {}).items():
        lines.append(f"- `{industry or '(empty)'}`: `{count}`")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_peer_lookup(session, *, batch_size: int) -> dict[tuple[int, str | None], list[str]]:
    from backend.models.business_segment import BusinessSegment  # noqa: WPS433

    lookup: dict[tuple[int, str | None], list[str]] = defaultdict(list)
    rows = (
        session.query(
            BusinessSegment.company_id,
            BusinessSegment.reporting_period,
            BusinessSegment.segment_name,
            BusinessSegment.segment_alias,
        )
        .order_by(BusinessSegment.id.asc())
        .yield_per(batch_size)
    )
    for company_id, reporting_period, segment_name, segment_alias in rows:
        key = (company_id, reporting_period)
        lookup[key].append(segment_name)
        if segment_alias:
            lookup[key].append(segment_alias)
    return lookup


def fallback_payload(segment, *, reason: str, error: str | None = None) -> dict[str, Any]:
    basis = "本地规则未形成稳定映射，已写入保守兜底分类，供后续人工复核。"
    if error:
        basis = f"{basis} 错误摘要：{error[:240]}"
    return {
        "business_segment_id": segment.id,
        "standard_system": "GICS",
        "level_1": "Unknown",
        "level_2": "Unclassified",
        "level_3": "Other",
        "level_4": None,
        "is_primary": segment.segment_type == "primary",
        "mapping_basis": basis,
        "review_status": "needs_manual_review" if error else "unmapped",
        "classifier_type": "rule_based",
        "confidence": Decimal("0.0000"),
        "review_reason": reason,
    }


def normalize_payload(segment, proposal) -> dict[str, Any]:
    payload = {
        "business_segment_id": segment.id,
        **proposal.to_model_dict(),
    }
    levels = [
        payload.get("level_1"),
        payload.get("level_2"),
        payload.get("level_3"),
        payload.get("level_4"),
    ]
    if not any(levels):
        fallback = fallback_payload(segment, reason=payload.get("review_reason") or "rule_not_matched")
        fallback["mapping_basis"] = payload.get("mapping_basis") or fallback["mapping_basis"]
        fallback["review_status"] = payload.get("review_status") or fallback["review_status"]
        fallback["confidence"] = payload.get("confidence") if payload.get("confidence") is not None else fallback["confidence"]
        return fallback
    return payload


def fetch_segment_batch(session, *, last_id: int, batch_size: int):
    from backend.models.business_segment import BusinessSegment  # noqa: WPS433

    return (
        session.query(BusinessSegment)
        .options(selectinload(BusinessSegment.company))
        .filter(BusinessSegment.id > last_id)
        .order_by(BusinessSegment.id.asc())
        .limit(batch_size)
        .all()
    )


def clear_classifications(session) -> None:
    from backend.models.business_segment_classification import (  # noqa: WPS433
        BusinessSegmentClassification,
    )

    session.query(BusinessSegmentClassification).delete(synchronize_session=False)
    reset_id_sequence(session, "business_segment_classifications")


def rebuild_classifications(
    SessionLocal,
    *,
    total_segments: int,
    batch_size: int,
) -> dict[str, Any]:
    from backend.analysis.industry_classification import (  # noqa: WPS433
        classify_business_segment_with_rules,
    )
    from backend.models.business_segment_classification import (  # noqa: WPS433
        BusinessSegmentClassification,
    )

    started_at = monotonic()
    with SessionLocal() as session:
        peer_lookup = build_peer_lookup(session, batch_size=batch_size)

    inserted = 0
    processed = 0
    failed_rows: list[dict[str, Any]] = []
    last_id = 0
    batch_index = 0

    while True:
        with SessionLocal() as read_session:
            segments = fetch_segment_batch(
                read_session,
                last_id=last_id,
                batch_size=batch_size,
            )
        if not segments:
            break

        batch_index += 1
        batch_payloads: list[dict[str, Any]] = []
        batch_failed = 0
        batch_first_id = segments[0].id
        batch_last_id = segments[-1].id

        for segment in segments:
            try:
                proposal = classify_business_segment_with_rules(segment, peer_lookup=peer_lookup)
                batch_payloads.append(normalize_payload(segment, proposal))
            except Exception as exc:  # noqa: BLE001 - keep one bad row from blocking the rebuild.
                batch_failed += 1
                failed_rows.append(
                    {
                        "segment_id": segment.id,
                        "company_id": segment.company_id,
                        "segment_name": segment.segment_name,
                        "reporting_period": segment.reporting_period,
                        "error": str(exc),
                    }
                )
                batch_payloads.append(
                    fallback_payload(
                        segment,
                        reason="rule_exception_fallback",
                        error=str(exc),
                    )
                )

        with SessionLocal() as write_session:
            with write_session.begin():
                write_session.bulk_insert_mappings(
                    BusinessSegmentClassification,
                    batch_payloads,
                )

        inserted += len(batch_payloads)
        processed += len(segments)
        last_id = batch_last_id
        write_failed_rows(failed_rows)
        elapsed = monotonic() - started_at
        print(
            "batch "
            f"{batch_index}: processed={processed}/{total_segments} "
            f"inserted={inserted} failed={len(failed_rows)} "
            f"elapsed={elapsed:.1f}s range={batch_first_id}-{batch_last_id}",
            flush=True,
        )

    with SessionLocal() as session:
        with session.begin():
            reset_id_sequence(session, "business_segment_classifications")

    return {
        "inserted": inserted,
        "processed": processed,
        "failed_count": len(failed_rows),
        "failed_rows_path": str(FAILED_ROWS_PATH),
        "elapsed_seconds": round(monotonic() - started_at, 3),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild business_segment_classifications from existing rule logic."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=5000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_url = require_database_url()
    import backend.models  # noqa: F401,WPS433

    engine = create_database_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    try:
        with SessionLocal() as session:
            protected_counts_before = count_protected_tables(session)
            total_segments = count_table(session, "business_segments")
            current_classifications = count_table(session, "business_segment_classifications")

        print(f"database: {render_database_url(database_url)}", flush=True)
        print(f"apply: {args.apply}", flush=True)
        print(f"business_segments total: {total_segments}", flush=True)
        print(
            "business_segment_classifications current: "
            f"{current_classifications}",
            flush=True,
        )
        print(f"batch_size: {args.batch_size}", flush=True)

        status = "dry_run_ok"
        rebuild_stats = {
            "inserted": 0,
            "processed": 0,
            "failed_count": 0,
            "failed_rows_path": str(FAILED_ROWS_PATH),
            "elapsed_seconds": 0,
        }
        if args.apply:
            with SessionLocal() as session:
                with session.begin():
                    clear_classifications(session)
            print("cleared business_segment_classifications", flush=True)
            rebuild_stats = rebuild_classifications(
                SessionLocal,
                total_segments=total_segments,
                batch_size=args.batch_size,
            )
            status = "classification_rebuild_applied"
        else:
            print(
                "dry-run only: no rows cleared or inserted; "
                f"would process {total_segments} business_segments",
                flush=True,
            )
            write_failed_rows([])

        with SessionLocal() as session:
            protected_counts_after = count_protected_tables(session)
            rebuild_summary = collect_summary(
                session,
                status=status,
                apply=args.apply,
                database_url=database_url,
            )
            rebuild_summary["inserted_classification_count"] = rebuild_stats["inserted"]
            rebuild_summary["processed_segment_count"] = rebuild_stats["processed"]
            rebuild_summary["failed_count"] = rebuild_stats["failed_count"]
            rebuild_summary["failed_rows_path"] = rebuild_stats["failed_rows_path"]
            rebuild_summary["elapsed_seconds"] = rebuild_stats["elapsed_seconds"]
            rebuild_summary["protected_table_deltas"] = {
                table_name: protected_counts_after[table_name] - protected_counts_before[table_name]
                for table_name in PROTECTED_TABLES
            }

        payload = load_existing_summary()
        payload["classification_rebuild"] = rebuild_summary
        validation = rebuild_summary["validation"]
        payload["success"] = bool(
            args.apply
            and rebuild_summary["business_segments_count"] > 0
            and rebuild_summary["business_segment_classifications_count"]
            == rebuild_summary["business_segments_count"]
            and validation["orphan_classification_count"] == 0
            and validation["orphan_business_segment_company_id_count"] == 0
            and all(delta == 0 for delta in rebuild_summary["protected_table_deltas"].values())
        )
        write_json(SUMMARY_PATH, payload)
        write_report(payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
