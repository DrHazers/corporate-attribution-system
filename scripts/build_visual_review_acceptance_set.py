from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from html import escape
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import backend.models  # noqa: F401,E402
from backend.database import Base, ensure_sqlite_schema  # noqa: E402
from backend.visualization.control_graph import (  # noqa: E402
    DEFAULT_MAX_DEPTH,
    build_control_graph_with_session,
)


DATABASES = {
    "mainline": PROJECT_ROOT / "ultimate_controller_test_dataset_mainline_working.db",
    "enhanced": PROJECT_ROOT / "ultimate_controller_enhanced_dataset_working.db",
}


SAMPLES: list[dict[str, Any]] = [
    {
        "db_key": "mainline",
        "company_id": 2001,
        "review_group": "第一组：算法主干样本",
        "case_group": "direct_equals_ultimate",
        "scenario": "direct = actual = ultimate",
        "attention": "看直接控制人、实际控制人、ultimate 是否为同一主体；图和表都应很干净。",
    },
    {
        "db_key": "mainline",
        "company_id": 2004,
        "review_group": "第一组：算法主干样本",
        "case_group": "rollup_success",
        "scenario": "direct controller 存在，actual/ultimate 上卷成功",
        "attention": "看 direct holdco 是否继续上卷到 Continental Power Group，摘要国别是否来自 ultimate。",
    },
    {
        "db_key": "enhanced",
        "company_id": 365,
        "review_group": "第一组：算法主干样本",
        "case_group": "E_spv_lookthrough",
        "scenario": "SPV / holding company look-through 成功",
        "attention": "看 SPV/holding company 是否作为中间层，actual 是否落到 sovereign technology fund。",
    },
    {
        "db_key": "enhanced",
        "company_id": 1418,
        "review_group": "第一组：算法主干样本",
        "case_group": "trust_vehicle_lookthrough",
        "scenario": "trust vehicle look-through 成功",
        "attention": "看 trust vehicle 是否没有停留为 actual，而是穿透到 industrial group。",
    },
    {
        "db_key": "mainline",
        "company_id": 2023,
        "review_group": "第一组：算法主干样本",
        "case_group": "board_control_mixed_rollup",
        "scenario": "mixed control 成功：board_control",
        "attention": "看 board_control 语义是否进入 mixed control，并上卷到自然人实际控制人。",
    },
    {
        "db_key": "mainline",
        "company_id": 2024,
        "review_group": "第一组：算法主干样本",
        "case_group": "vie_mixed_rollup",
        "scenario": "mixed control 成功：VIE / agreement",
        "attention": "看 VIE power/economics/exclusivity 路径是否作为 mixed control 主路径展示。",
    },
    {
        "db_key": "mainline",
        "company_id": 2007,
        "review_group": "第一组：算法主干样本",
        "case_group": "joint_control_block",
        "scenario": "joint_control 阻断",
        "attention": "看是否没有强行给唯一 actual controller，国别是否为 undetermined。",
    },
    {
        "db_key": "mainline",
        "company_id": 2016,
        "review_group": "第一组：算法主干样本",
        "case_group": "nominee_beneficial_owner_unknown",
        "scenario": "beneficial_owner_unknown / nominee 阻断",
        "attention": "看 nominee/beneficial owner unknown 是否阻断 actual，摘要是否 fallback 到注册地。",
    },
    {
        "db_key": "mainline",
        "company_id": 2021,
        "review_group": "第一组：算法主干样本",
        "case_group": "fallback_no_meaningful_signal",
        "scenario": "fallback_no_meaningful_signal",
        "attention": "看无可靠控制信号时，图/表是否保持空或辅助说明，国别是否仅按注册地 fallback。",
    },
    {
        "db_key": "mainline",
        "company_id": 2010,
        "review_group": "第二组：边界和争议样本",
        "case_group": "insufficient_evidence_leading_candidate",
        "scenario": "insufficient_evidence：有 leading candidate 但不过 actual gate",
        "attention": "看 leading candidate 是否保留为候选说明，而不是变成实际控制人。",
    },
    {
        "db_key": "mainline",
        "company_id": 2012,
        "review_group": "第二组：边界和争议样本",
        "case_group": "low_confidence_evidence_weak",
        "scenario": "low_confidence_evidence_weak",
        "attention": "看低置信标记是否阻断 actual，明细表说明是否表达证据不足。",
    },
    {
        "db_key": "enhanced",
        "company_id": 20,
        "review_group": "第二组：边界和争议样本",
        "case_group": "trust_low_confidence_agreement",
        "scenario": "agreement / trust 低置信边界",
        "attention": "看 agreement control 的 100% 语义强度是否仍因 low confidence 被阻断。",
    },
    {
        "db_key": "enhanced",
        "company_id": 847,
        "review_group": "第二组：边界和争议样本",
        "case_group": "close_competition",
        "scenario": "close competition",
        "attention": "看多个候选接近时是否保留对照，不硬选单一实际控制人。",
    },
    {
        "db_key": "enhanced",
        "company_id": 7755,
        "review_group": "第二组：边界和争议样本",
        "case_group": "ownership_aggregation_high_ratio",
        "scenario": "aggregation-like candidate 比例很高但被排除",
        "attention": "看 Public Float 高比例是否只作为结构信号，不进入 actual controller。",
    },
    {
        "db_key": "enhanced",
        "company_id": 2001,
        "review_group": "第二组：边界和争议样本",
        "case_group": "identifiable_blockholder_plus_public_float",
        "scenario": "identifiable blockholder + dispersed ownership",
        "attention": "看可识别 blockholder 与 Public Float 同时存在时，Public Float 是否不冒充 actual。",
    },
    {
        "db_key": "enhanced",
        "company_id": 18,
        "review_group": "第二组：边界和争议样本",
        "case_group": "public_float_low_confidence",
        "scenario": "public float / ownership aggregation 结构信号",
        "attention": "看 ownership aggregation 是否被标为 pattern only，且国别回退而非归属给 Public Float。",
    },
    {
        "db_key": "enhanced",
        "company_id": 5353,
        "review_group": "第二组：边界和争议样本",
        "case_group": "nominee_without_disclosure",
        "scenario": "nominee_without_disclosure 阻断",
        "attention": "看 nominee 未披露是否阻断，Public Float/nominee 相关候选是否只做参考。",
    },
    {
        "db_key": "enhanced",
        "company_id": 2021,
        "review_group": "第二组：边界和争议样本",
        "case_group": "no_unique_actual_controller_aggregation_only",
        "scenario": "无唯一实际控制人，仅 aggregation-like candidate",
        "attention": "看没有可识别 actual 时，摘要是否 fallback_no_identifiable_terminal_controller。",
    },
    {
        "db_key": "enhanced",
        "company_id": 9737,
        "review_group": "第三组：人工结果联动样本",
        "case_group": "manual_override_active_name_snapshot",
        "scenario": "人工征订生效：仅名称快照",
        "attention": "看当前人工名称快照是否只做说明，不应作为正式 entity 节点驱动 Path Builder。",
    },
    {
        "db_key": "enhanced",
        "company_id": 240,
        "review_group": "第三组：人工结果联动样本",
        "case_group": "manual_override_history_restored",
        "scenario": "人工征订覆盖 / 恢复自动结果历史",
        "attention": "看历史 manual_override/auto_restored 记录；当前若无 active override，应恢复自动口径。",
    },
    {
        "db_key": "enhanced",
        "company_id": 3003,
        "review_group": "第三组：人工结果联动样本",
        "case_group": "manual_judgment_history_same_subject_auto",
        "scenario": "人工判定覆盖自动结果，同主体自动参考",
        "attention": "看 Crown AI Global plc 人工判定历史；用于验证同主体自动参考不应重复成两行。",
    },
    {
        "db_key": "enhanced",
        "company_id": 170,
        "review_group": "第三组：人工结果联动样本",
        "case_group": "manual_confirmed_history_restored",
        "scenario": "人工确认 / 恢复自动结果历史",
        "attention": "看 manual_confirmed 历史记录；当前若无 active override，应以自动结果为准。",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a visual review company set and static HTML graphs without refreshing algorithms.",
    )
    parser.add_argument(
        "--output-json",
        default=str(PROJECT_ROOT / "exports" / "research_samples" / "visual_review_company_set.json"),
    )
    parser.add_argument(
        "--output-md",
        default=str(PROJECT_ROOT / "logs" / "visual_review_company_set_terminal_profile.md"),
    )
    parser.add_argument(
        "--html-dir",
        default=str(PROJECT_ROOT / "exports" / "visual_review_html"),
    )
    parser.add_argument("--skip-html", action="store_true")
    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    return parser.parse_args()


def connect_sqlite(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "select name from sqlite_master where type='table' and name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def parse_json(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def percent_text(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def path_text(path_payload: Any) -> str:
    paths = parse_json(path_payload, [])
    if not isinstance(paths, list) or not paths:
        return ""
    first = paths[0]
    if not isinstance(first, dict):
        return ""
    names = first.get("path_entity_names")
    if isinstance(names, list) and names:
        return " -> ".join(str(item) for item in names if item)
    ids = first.get("path_entity_ids")
    if isinstance(ids, list) and ids:
        return " -> ".join(f"entity {item}" for item in ids if item is not None)
    return str(first.get("path_text") or "")


def load_company(connection: sqlite3.Connection, company_id: int) -> dict[str, Any]:
    row = connection.execute(
        "select id, name, incorporation_country, listing_country from companies where id=?",
        (company_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"company_id={company_id} not found")
    return dict(row)


def load_latest_auto_country(connection: sqlite3.Connection, company_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        """
        select *
        from country_attributions
        where company_id=? and coalesce(is_manual, 0)=0
        order by id desc
        limit 1
        """,
        (company_id,),
    ).fetchone()
    if row is None:
        row = connection.execute(
            """
            select *
            from country_attributions
            where company_id=?
            order by id desc
            limit 1
            """,
            (company_id,),
        ).fetchone()
    return dict(row) if row else None


def load_active_manual(connection: sqlite3.Connection, company_id: int) -> dict[str, Any] | None:
    if not table_exists(connection, "manual_control_overrides"):
        return None
    row = connection.execute(
        """
        select *
        from manual_control_overrides
        where company_id=? and is_current_effective=1
        order by id desc
        limit 1
        """,
        (company_id,),
    ).fetchone()
    return dict(row) if row else None


def load_manual_history(connection: sqlite3.Connection, company_id: int) -> list[dict[str, Any]]:
    if not table_exists(connection, "manual_control_overrides"):
        return []
    rows = connection.execute(
        """
        select id, source_type, is_current_effective, actual_controller_entity_id,
               actual_controller_name, actual_control_country, reason, evidence, created_at
        from manual_control_overrides
        where company_id=?
        order by id
        """,
        (company_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def relationship_basis(row: dict[str, Any]) -> dict[str, Any]:
    basis = parse_json(row.get("basis"), {})
    return basis if isinstance(basis, dict) else {}


def load_relationships(connection: sqlite3.Connection, company_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select *
        from control_relationships
        where company_id=?
          and (notes is null or notes not like 'MANUAL_OVERRIDE:%')
        order by
          case when is_actual_controller=1 then 0 else 1 end,
          case when is_direct_controller=1 then 0 else 1 end,
          case when control_tier='ultimate' then 0 when control_tier='direct' then 1 else 2 end,
          coalesce(control_ratio, 0) desc,
          id
        """,
        (company_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def summarize_relationship(row: dict[str, Any]) -> dict[str, Any]:
    basis = relationship_basis(row)
    control_path = path_text(row.get("control_path"))
    return {
        "controller_entity_id": row.get("controller_entity_id"),
        "controller_name": row.get("controller_name"),
        "controller_type": row.get("controller_type"),
        "control_type": row.get("control_type"),
        "control_ratio": row.get("control_ratio"),
        "control_ratio_text": percent_text(row.get("control_ratio")),
        "control_tier": row.get("control_tier"),
        "is_actual_controller": bool(row.get("is_actual_controller")),
        "is_direct_controller": bool(row.get("is_direct_controller")),
        "is_ultimate_controller": bool(row.get("is_ultimate_controller")),
        "promotion_reason": row.get("promotion_reason"),
        "terminal_failure_reason": row.get("terminal_failure_reason"),
        "terminal_identifiability": basis.get("terminal_identifiability"),
        "terminal_suitability": basis.get("terminal_suitability"),
        "selection_reason": basis.get("selection_reason"),
        "semantic_flags": parse_json(row.get("semantic_flags"), row.get("semantic_flags")),
        "primary_path": control_path,
    }


def pick_core_relationships(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    picked: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    def add_matching(predicate) -> None:
        for row in rows:
            row_id = int(row["id"])
            if row_id in seen_ids:
                continue
            if predicate(row, relationship_basis(row)):
                picked.append(summarize_relationship(row))
                seen_ids.add(row_id)
                if len(picked) >= 5:
                    return

    add_matching(lambda row, _basis: bool(row.get("is_actual_controller")))
    add_matching(lambda row, _basis: bool(row.get("is_direct_controller")))
    add_matching(lambda row, basis: basis.get("selection_reason", "").startswith("leading_candidate"))
    add_matching(lambda row, basis: basis.get("terminal_identifiability") == "aggregation_like")
    add_matching(lambda row, _basis: row.get("terminal_failure_reason") is not None)
    add_matching(lambda _row, _basis: True)
    return picked[:5]


def current_conclusion(
    country: dict[str, Any] | None,
    relationships: list[dict[str, Any]],
    active_manual: dict[str, Any] | None,
) -> dict[str, Any]:
    actual = next((row for row in relationships if row.get("is_actual_controller")), None)
    direct = next((row for row in relationships if row.get("is_direct_controller")), None)
    if active_manual:
        return {
            "result_source": active_manual.get("source_type") or "manual",
            "actual_controller": active_manual.get("actual_controller_name") or (
                actual.get("controller_name") if actual else None
            ),
            "actual_controller_entity_id": active_manual.get("actual_controller_entity_id"),
            "actual_control_country": active_manual.get("actual_control_country")
            or (country or {}).get("actual_control_country"),
            "attribution_type": active_manual.get("source_type"),
            "country_inference_reason": "active_manual_override",
            "terminal_failure_reason": None,
            "direct_controller": direct.get("controller_name") if direct else None,
            "manual_note": (
                "active manual name snapshot without entity_id"
                if active_manual.get("actual_controller_name")
                and not active_manual.get("actual_controller_entity_id")
                else "active manual result"
            ),
        }

    failure = None
    for row in relationships:
        if row.get("terminal_failure_reason"):
            failure = row.get("terminal_failure_reason")
            break
    return {
        "result_source": "automatic",
        "actual_controller": actual.get("controller_name") if actual else None,
        "actual_controller_entity_id": actual.get("controller_entity_id") if actual else None,
        "actual_control_country": (country or {}).get("actual_control_country"),
        "attribution_type": (country or {}).get("attribution_type"),
        "country_inference_reason": (country or {}).get("country_inference_reason"),
        "terminal_failure_reason": failure,
        "direct_controller": direct.get("controller_name") if direct else None,
        "manual_note": None,
    }


def build_sample_records() -> list[dict[str, Any]]:
    connections = {key: connect_sqlite(path) for key, path in DATABASES.items()}
    try:
        records: list[dict[str, Any]] = []
        for index, sample in enumerate(SAMPLES, start=1):
            db_key = sample["db_key"]
            connection = connections[db_key]
            company = load_company(connection, int(sample["company_id"]))
            country = load_latest_auto_country(connection, int(sample["company_id"]))
            active_manual = load_active_manual(connection, int(sample["company_id"]))
            manual_history = load_manual_history(connection, int(sample["company_id"]))
            relationships = load_relationships(connection, int(sample["company_id"]))
            conclusion = current_conclusion(country, relationships, active_manual)
            record = {
                "order": index,
                "sample_key": f"{db_key}_{sample['company_id']}",
                "db_key": db_key,
                "database_path": str(DATABASES[db_key]),
                "company_id": sample["company_id"],
                "company_name": company["name"],
                "incorporation_country": company.get("incorporation_country"),
                "listing_country": company.get("listing_country"),
                "review_group": sample["review_group"],
                "case_group": sample["case_group"],
                "scenario": sample["scenario"],
                "attention": sample["attention"],
                "current_conclusion": conclusion,
                "core_relationship_rows": pick_core_relationships(relationships),
                "manual_history": manual_history,
                "manual_history_summary": {
                    source: sum(1 for item in manual_history if item.get("source_type") == source)
                    for source in sorted({item.get("source_type") for item in manual_history})
                },
            }
            records.append(record)
        return records
    finally:
        for connection in connections.values():
            connection.close()


def slugify(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "_" for char in value)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")[:90] or "company"


def generate_html(records: list[dict[str, Any]], output_dir: Path, max_depth: int) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    by_db: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_db[record["db_key"]].append(record)

    html_paths: dict[str, str] = {}
    for db_key, items in by_db.items():
        db_path = prepare_visualization_database(db_key, output_dir).resolve()
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db_output_dir = output_dir / db_key
        db_output_dir.mkdir(parents=True, exist_ok=True)
        with session_factory() as session:
            for record in items:
                file_name = f"{record['order']:02d}_{record['sample_key']}_{slugify(record['company_name'])}.html"
                html_path = build_control_graph_with_session(
                    session,
                    int(record["company_id"]),
                    output_path=db_output_dir / file_name,
                    latest_output_path=None,
                    max_depth=max_depth,
                    focus_label=record["scenario"],
                    focus_controller_name=record["current_conclusion"].get("actual_controller")
                    or record["current_conclusion"].get("direct_controller"),
                    focus_control_type=record["current_conclusion"].get("attribution_type"),
                    focus_semantic_flags=[],
                )
                html_paths[record["sample_key"]] = str(html_path)
        engine.dispose()

    for record in records:
        record["html_path"] = html_paths.get(record["sample_key"])
    write_html_index(records, output_dir / "index.html")
    return html_paths


def prepare_visualization_database(db_key: str, output_dir: Path) -> Path:
    source_path = DATABASES[db_key].resolve()
    with connect_sqlite(source_path) as connection:
        needs_compat_copy = not table_exists(connection, "manual_control_overrides")
    if not needs_compat_copy:
        return source_path

    copy_dir = output_dir / "_db_copies"
    copy_dir.mkdir(parents=True, exist_ok=True)
    copy_path = copy_dir / source_path.name
    shutil.copy2(source_path, copy_path)

    engine = create_engine(f"sqlite:///{copy_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    raw_connection = engine.raw_connection()
    try:
        ensure_sqlite_schema(raw_connection)
    finally:
        raw_connection.close()
        engine.dispose()
    return copy_path


def write_html_index(records: list[dict[str, Any]], output_path: Path) -> None:
    cards = []
    for record in records:
        html_path = Path(record["html_path"]) if record.get("html_path") else None
        href = html_path.relative_to(output_path.parent).as_posix() if html_path else ""
        conclusion = record["current_conclusion"]
        cards.append(
            f"""
            <li class="card">
              <div class="tag">{escape(record['review_group'].split('：', 1)[-1])}</div>
              <h2>{escape(str(record['order']))}. {escape(record['company_name'])}</h2>
              <p><strong>Case:</strong> {escape(record['case_group'])}</p>
              <p><strong>Scenario:</strong> {escape(record['scenario'])}</p>
              <p><strong>Actual:</strong> {escape(str(conclusion.get('actual_controller') or 'None'))}</p>
              <p><strong>Country:</strong> {escape(str(conclusion.get('actual_control_country') or ''))} / {escape(str(conclusion.get('attribution_type') or ''))}</p>
              <p><a href="{escape(href)}">Open graph HTML</a></p>
            </li>
            """
        )
    output_path.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Visual Review Company Set</title>
    <style>
      body {{ margin: 0; font-family: "Segoe UI", "PingFang SC", sans-serif; color: #1f2f3d; background: #f7fafc; }}
      main {{ max-width: 1180px; margin: 0 auto; padding: 28px 20px 48px; }}
      h1 {{ margin: 0 0 8px; font-size: 30px; }}
      .meta {{ color: #65758a; line-height: 1.7; margin-bottom: 20px; }}
      .grid {{ list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }}
      .card {{ border: 1px solid #d9e2ec; border-radius: 8px; padding: 14px; background: #fff; }}
      .card h2 {{ margin: 8px 0; font-size: 18px; }}
      .card p {{ margin: 6px 0; line-height: 1.55; }}
      .tag {{ color: #315f85; font-size: 12px; font-weight: 700; }}
      a {{ color: #2368a2; font-weight: 700; }}
    </style>
  </head>
  <body>
    <main>
      <h1>Visual Review Company Set</h1>
      <div class="meta">Generated: {escape(datetime.now().isoformat(timespec='seconds'))}; samples: {len(records)}</div>
      <ul class="grid">{''.join(cards)}</ul>
    </main>
  </body>
</html>
""",
        encoding="utf-8",
    )


def markdown_table(records: list[dict[str, Any]]) -> str:
    lines = [
        "| # | DB | company_id | company_name | case_group | actual controller | country / attribution | failure | 关注点 |",
        "|---|---|---:|---|---|---|---|---|---|",
    ]
    for record in records:
        conclusion = record["current_conclusion"]
        lines.append(
            "| {order} | `{db_key}` | {company_id} | {company_name} | `{case_group}` | {actual} | {country} / `{attrib}` | `{failure}` | {attention} |".format(
                order=record["order"],
                db_key=record["db_key"],
                company_id=record["company_id"],
                company_name=record["company_name"].replace("|", "\\|"),
                case_group=record["case_group"],
                actual=(conclusion.get("actual_controller") or "无").replace("|", "\\|"),
                country=conclusion.get("actual_control_country") or "",
                attrib=conclusion.get("attribution_type") or "",
                failure=conclusion.get("terminal_failure_reason") or "",
                attention=record["attention"].replace("|", "\\|"),
            )
        )
    return "\n".join(lines)


def write_markdown(records: list[dict[str, Any]], output_path: Path, html_dir: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_group[record["review_group"]].append(record)

    lines = [
        "# Visual Review Company Set / Terminal Profile",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Sample count: `{len(records)}`",
        f"- HTML index: `{html_dir / 'index.html'}`",
        "- Databases:",
    ]
    for key, path in DATABASES.items():
        lines.append(f"  - `{key}`: `{path}`")
    lines.extend(
        [
            "",
            "## 总览清单",
            "",
            markdown_table(records),
            "",
        ]
    )

    for group, items in by_group.items():
        lines.extend([f"## {group}", ""])
        for record in items:
            conclusion = record["current_conclusion"]
            lines.extend(
                [
                    f"### {record['order']}. {record['company_name']} (`{record['db_key']}` / company_id={record['company_id']})",
                    "",
                    f"- case_group: `{record['case_group']}`",
                    f"- 代表场景: {record['scenario']}",
                    f"- 当前结果来源: `{conclusion.get('result_source')}`",
                    f"- actual controller: {conclusion.get('actual_controller') or '无'}",
                    f"- actual control country: {conclusion.get('actual_control_country') or '无'}",
                    f"- attribution_type: `{conclusion.get('attribution_type') or ''}`",
                    f"- terminal_failure_reason: `{conclusion.get('terminal_failure_reason') or ''}`",
                    f"- 最该关注: {record['attention']}",
                    f"- HTML: `{record.get('html_path') or 'not generated'}`",
                ]
            )
            if conclusion.get("manual_note"):
                lines.append(f"- 人工结果备注: {conclusion['manual_note']}")
            if record["manual_history_summary"]:
                lines.append(f"- 人工历史: `{record['manual_history_summary']}`")
            lines.extend(["", "核心明细行："])
            if not record["core_relationship_rows"]:
                lines.append("- 无控制关系明细行。")
            for row in record["core_relationship_rows"]:
                role = []
                if row["is_actual_controller"]:
                    role.append("actual")
                if row["is_direct_controller"]:
                    role.append("direct")
                if row["is_ultimate_controller"]:
                    role.append("ultimate")
                if row["terminal_identifiability"] == "aggregation_like":
                    role.append("aggregation_like")
                lines.append(
                    "- {name} | {ctype} | {ratio} | {role} | failure=`{failure}` | selection=`{selection}` | path={path}".format(
                        name=row.get("controller_name") or "无名主体",
                        ctype=row.get("control_type") or "",
                        ratio=row.get("control_ratio_text") or "",
                        role="/".join(role) or row.get("control_tier") or "",
                        failure=row.get("terminal_failure_reason") or "",
                        selection=row.get("selection_reason") or "",
                        path=row.get("primary_path") or "无",
                    )
                )
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    html_dir = Path(args.html_dir)

    records = build_sample_records()
    if not args.skip_html:
        generate_html(records, html_dir, args.max_depth)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(records, output_md, html_dir)

    print(f"Samples: {len(records)}")
    print(f"JSON: {output_json}")
    print(f"Markdown: {output_md}")
    if not args.skip_html:
        print(f"HTML index: {html_dir / 'index.html'}")


if __name__ == "__main__":
    main()
