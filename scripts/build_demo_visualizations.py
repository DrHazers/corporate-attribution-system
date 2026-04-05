from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.analysis.ownership_penetration import refresh_company_control_analysis  # noqa: E402
from backend.visualization.control_graph import (  # noqa: E402
    DEFAULT_MAX_DEPTH,
    build_control_graph_with_session,
)


DEFAULT_DEMO_DB = PROJECT_ROOT / "company_test_analysis_demo.db"
DEFAULT_SAMPLES_JSON = PROJECT_ROOT / "tests" / "output" / "demo_analysis_samples.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tests" / "output_demo_graphs"

FIXED_DEMO_SAMPLES: list[dict[str, Any]] = [
    {
        "order": 1,
        "category": "equity_control",
        "label": "Equity Control",
        "company_name": "Apple Inc.",
        "filename_tag": "equity_control",
        "focus_control_type": "equity_control",
        "focus_semantic_flags": [],
    },
    {
        "order": 2,
        "category": "agreement_control",
        "label": "Agreement Control",
        "company_name": "Harbour Renewables Holdings Ltd.",
        "filename_tag": "agreement_control",
        "focus_control_type": "agreement_control",
        "focus_semantic_flags": ["agreement"],
    },
    {
        "order": 3,
        "category": "board_control",
        "label": "Board Control",
        "company_name": "Alibaba Group Holding Limited",
        "filename_tag": "board_control",
        "focus_control_type": "board_control",
        "focus_semantic_flags": ["board_control"],
    },
    {
        "order": 4,
        "category": "mixed_control",
        "label": "Mixed Control",
        "company_name": "Hikari Grid Advanced Co., Ltd.",
        "filename_tag": "mixed_control",
        "focus_control_type": "mixed_control",
        "focus_semantic_flags": ["board_control"],
    },
    {
        "order": 5,
        "category": "voting_right_semantic",
        "label": "Voting Right Semantic",
        "company_name": "Alphabet Inc.",
        "filename_tag": "voting_right",
        "focus_control_type": "agreement_control",
        "focus_semantic_flags": ["voting_right"],
    },
    {
        "order": 6,
        "category": "nominee_semantic",
        "label": "Nominee Semantic",
        "company_name": "Adler Chemicals SE",
        "filename_tag": "nominee",
        "focus_control_type": "significant_influence",
        "focus_semantic_flags": ["nominee"],
    },
    {
        "order": 7,
        "category": "vie_semantic",
        "label": "VIE Semantic",
        "company_name": "Coral Fintech Holdings Limited",
        "filename_tag": "vie",
        "focus_control_type": "agreement_control",
        "focus_semantic_flags": ["vie"],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build demo control graph HTML files from the demo analysis database.",
    )
    parser.add_argument("--database", default=str(DEFAULT_DEMO_DB), help="Demo database path.")
    parser.add_argument("--samples-json", default=str(DEFAULT_SAMPLES_JSON), help="Sample metadata JSON path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for generated HTML files.")
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="Optional sample category filter. Repeat for multiple categories.",
    )
    parser.add_argument(
        "--company-id",
        type=int,
        action="append",
        dest="company_ids",
        help="Generate demo graph(s) for specific company_id values into the demo output directory.",
    )
    parser.add_argument(
        "--skip-refresh",
        action="store_true",
        help="When using --company-id, skip recomputing and persisting analysis in the demo database.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        help="Upstream traversal depth before backfilling focused edges.",
    )
    return parser.parse_args()


def _slugify(value: str) -> str:
    slug_chars: list[str] = []
    for char in value.lower():
        if char.isalnum():
            slug_chars.append(char)
        else:
            slug_chars.append("_")
    slug = "".join(slug_chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug[:80] or "company"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sample_lookup(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    samples = payload.get("samples")
    if not isinstance(samples, list):
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for sample in samples:
        if isinstance(sample, dict) and sample.get("category"):
            lookup[str(sample["category"])] = sample
    return lookup


def _sample_lookup_by_company_id(payload: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    samples = payload.get("samples")
    if not isinstance(samples, list):
        return {}

    lookup: dict[int, list[dict[str, Any]]] = {}
    for sample in samples:
        if not isinstance(sample, dict) or not sample.get("available"):
            continue
        company_id = sample.get("company_id")
        if not isinstance(company_id, int):
            continue
        lookup.setdefault(company_id, []).append(sample)
    return lookup


def _query_company_by_name(db: Session, company_name: str) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT id, name
            FROM companies
            WHERE LOWER(name) = LOWER(:company_name)
            LIMIT 1
            """
        ),
        {"company_name": company_name},
    ).mappings().first()
    return dict(row) if row is not None else None


def _query_company_by_id(db: Session, company_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT id, name
            FROM companies
            WHERE id = :company_id
            LIMIT 1
            """
        ),
        {"company_id": company_id},
    ).mappings().first()
    return dict(row) if row is not None else None


def _resolve_sample_entry(
    db: Session,
    definition: dict[str, Any],
    lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    sample = lookup.get(definition["category"])
    if sample and sample.get("available"):
        return {
            "available": True,
            "company_id": int(sample["company_id"]),
            "company_name": str(sample["company_name"]),
            "focus_controller_name": sample.get("actual_controller_or_candidate"),
            "focus_control_type": sample.get("control_type") or definition.get("focus_control_type"),
            "focus_semantic_flags": sample.get("semantic_flags") or definition.get("focus_semantic_flags") or [],
            "metadata_source": "demo_analysis_samples.json",
        }

    company_row = _query_company_by_name(db, definition["company_name"])
    if company_row is None:
        reason = (
            sample.get("reason")
            if sample and sample.get("reason")
            else f"Company '{definition['company_name']}' not found in demo database."
        )
        return {
            "available": False,
            "reason": str(reason),
        }

    return {
        "available": True,
        "company_id": int(company_row["id"]),
        "company_name": str(company_row["name"]),
        "focus_controller_name": sample.get("actual_controller_or_candidate") if sample else None,
        "focus_control_type": sample.get("control_type") if sample else definition.get("focus_control_type"),
        "focus_semantic_flags": sample.get("semantic_flags") if sample else definition.get("focus_semantic_flags") or [],
        "metadata_source": "fallback_company_name_match",
    }


def _pick_company_focus_metadata(
    company_id: int,
    *,
    company_samples: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    sample_entries = company_samples.get(company_id) or []
    if sample_entries:
        sample = sample_entries[0]
        label = sample.get("label") or sample.get("category") or f"Company {company_id}"
        return {
            "focus_label": str(label),
            "focus_controller_name": sample.get("actual_controller_or_candidate"),
            "focus_control_type": sample.get("control_type"),
            "focus_semantic_flags": sample.get("semantic_flags") or [],
            "metadata_source": "demo_analysis_samples.json",
        }

    return {
        "focus_label": f"Company {company_id}",
        "focus_controller_name": None,
        "focus_control_type": None,
        "focus_semantic_flags": [],
        "metadata_source": "direct_company_id",
    }


def _build_output_filename(definition: dict[str, Any], company_name: str) -> str:
    return f"{definition['order']:03d}_{definition['filename_tag']}_{_slugify(company_name)}.html"


def _build_company_output_filename(company_id: int, company_name: str) -> str:
    return f"company_{company_id}_{_slugify(company_name)}.html"


def _resolve_existing_company_ids(
    db: Session,
    company_ids: list[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    existing: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for company_id in company_ids:
        company_row = _query_company_by_id(db, company_id)
        if company_row is None:
            missing.append(
                {
                    "category": f"company_{company_id}",
                    "label": f"Company {company_id}",
                    "reason": f"company_id={company_id} not found in demo database.",
                }
            )
            continue
        existing.append(company_row)

    return existing, missing


def _refresh_company_analyses(
    db: Session,
    *,
    company_rows: list[dict[str, Any]],
) -> list[int]:
    refreshed_company_ids: list[int] = []
    for company_row in company_rows:
        company_id = int(company_row["id"])
        refresh_company_control_analysis(db, company_id)
        refreshed_company_ids.append(company_id)
    return refreshed_company_ids


def _build_specific_company_graphs(
    db: Session,
    *,
    company_rows: list[dict[str, Any]],
    output_dir: Path,
    max_depth: int,
    company_samples: dict[int, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    generated: list[dict[str, Any]] = []

    for company_row in company_rows:
        company_id = int(company_row["id"])
        company_name = str(company_row["name"])
        focus = _pick_company_focus_metadata(
            company_id,
            company_samples=company_samples,
        )
        file_name = _build_company_output_filename(company_id, company_name)
        html_path = build_control_graph_with_session(
            db,
            company_id,
            output_path=output_dir / file_name,
            latest_output_path=None,
            max_depth=max_depth,
            focus_label=focus["focus_label"],
            focus_controller_name=focus["focus_controller_name"],
            focus_control_type=focus["focus_control_type"],
            focus_semantic_flags=focus["focus_semantic_flags"],
        )
        generated.append(
            {
                "category": f"company_{company_id}",
                "label": focus["focus_label"],
                "company_id": company_id,
                "company_name": company_name,
                "focus_controller_name": focus.get("focus_controller_name"),
                "file_name": file_name,
                "html_path": str(html_path),
                "metadata_source": focus["metadata_source"],
            }
        )

    return generated


def _write_index(
    output_path: Path,
    *,
    database_path: Path,
    generated: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cards = []
    for item in generated:
        cards.append(
            f"""
            <li class=\"card\"> 
              <div class=\"tag\">{escape(item['label'])}</div>
              <h2>{escape(item['company_name'])}</h2>
              <p>{escape(item.get('focus_controller_name') or 'Controller not specified in metadata')}</p>
              <p><strong>File:</strong> <a href=\"{escape(item['file_name'])}\">{escape(item['file_name'])}</a></p>
            </li>
            """
        )
    missing_blocks = []
    for item in missing:
        missing_blocks.append(
            f"<li><strong>{escape(item['label'])}</strong>: {escape(item['reason'])}</li>"
        )

    output_path.write_text(
        f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Demo Graph Index</title>
    <style>
      body {{
        margin: 0;
        font-family: \"Segoe UI\", \"PingFang SC\", sans-serif;
        background: linear-gradient(180deg, #f8fbff 0%, #eef4ff 100%);
        color: #0f172a;
      }}
      main {{
        max-width: 1080px;
        margin: 0 auto;
        padding: 32px 20px 48px;
      }}
      h1 {{
        margin: 0 0 8px 0;
        font-size: 32px;
      }}
      .meta {{
        color: #475569;
        line-height: 1.6;
        margin-bottom: 24px;
      }}
      .grid {{
        list-style: none;
        padding: 0;
        margin: 0;
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: 16px;
      }}
      .card {{
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid rgba(148, 163, 184, 0.24);
        border-radius: 18px;
        padding: 18px;
        box-shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
      }}
      .card h2 {{
        margin: 8px 0 8px;
        font-size: 20px;
      }}
      .card p {{
        margin: 8px 0;
        line-height: 1.55;
      }}
      .tag {{
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        background: #dbeafe;
        color: #1d4ed8;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }}
      .missing {{
        margin-top: 28px;
        padding: 18px;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid rgba(248, 113, 113, 0.28);
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>Demo Control Graphs</h1>
      <div class=\"meta\">
        <div><strong>Database:</strong> {escape(str(database_path))}</div>
        <div><strong>Generated files:</strong> {len(generated)}</div>
      </div>
      <ul class=\"grid\">
        {''.join(cards)}
      </ul>
      <section class=\"missing\">
        <h2>Missing Samples</h2>
        <ul>
          {''.join(missing_blocks) if missing_blocks else '<li>None</li>'}
        </ul>
      </section>
    </main>
  </body>
</html>
""",
        encoding="utf-8",
    )


def build_demo_visualizations(
    *,
    database_path: Path = DEFAULT_DEMO_DB,
    samples_json_path: Path = DEFAULT_SAMPLES_JSON,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    selected_categories: list[str] | None = None,
    selected_company_ids: list[int] | None = None,
    refresh_selected_company_ids: bool = True,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> dict[str, Any]:
    database_path = Path(database_path).resolve()
    samples_json_path = Path(samples_json_path).resolve()
    output_dir = Path(output_dir).resolve()
    payload = _load_json(samples_json_path)
    lookup = _sample_lookup(payload)
    company_samples = _sample_lookup_by_company_id(payload)
    selected = set(selected_categories or [item["category"] for item in FIXED_DEMO_SAMPLES])
    company_ids = sorted(set(selected_company_ids or []))

    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    generated: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    refreshed_company_ids: list[int] = []

    with session_factory() as db:
        if company_ids:
            company_rows, company_missing = _resolve_existing_company_ids(db, company_ids)
            missing.extend(company_missing)
            if refresh_selected_company_ids and company_rows:
                refreshed_company_ids.extend(
                    _refresh_company_analyses(db, company_rows=company_rows)
                )
            generated.extend(
                _build_specific_company_graphs(
                    db,
                    company_rows=company_rows,
                    output_dir=output_dir,
                    max_depth=max_depth,
                    company_samples=company_samples,
                )
            )
        else:
            for definition in FIXED_DEMO_SAMPLES:
                if definition["category"] not in selected:
                    continue
                sample = _resolve_sample_entry(db, definition, lookup)
                if not sample.get("available"):
                    missing.append(
                        {
                            "category": definition["category"],
                            "label": definition["label"],
                            "reason": sample["reason"],
                        }
                    )
                    continue

                file_name = _build_output_filename(definition, sample["company_name"])
                html_path = build_control_graph_with_session(
                    db,
                    int(sample["company_id"]),
                    output_path=output_dir / file_name,
                    latest_output_path=None,
                    max_depth=max_depth,
                    focus_label=definition["label"],
                    focus_controller_name=sample.get("focus_controller_name"),
                    focus_control_type=sample.get("focus_control_type"),
                    focus_semantic_flags=sample.get("focus_semantic_flags"),
                )
                generated.append(
                    {
                        "category": definition["category"],
                        "label": definition["label"],
                        "company_id": int(sample["company_id"]),
                        "company_name": sample["company_name"],
                        "focus_controller_name": sample.get("focus_controller_name"),
                        "file_name": file_name,
                        "html_path": str(html_path),
                        "metadata_source": sample.get("metadata_source"),
                    }
                )

    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "index.html"
    _write_index(
        index_path,
        database_path=database_path,
        generated=generated,
        missing=missing,
    )

    return {
        "database_path": str(database_path),
        "samples_json_path": str(samples_json_path),
        "output_dir": str(output_dir),
        "index_path": str(index_path),
        "generated": generated,
        "missing": missing,
        "refreshed_company_ids": refreshed_company_ids,
    }


def main() -> None:
    args = parse_args()
    result = build_demo_visualizations(
        database_path=Path(args.database),
        samples_json_path=Path(args.samples_json),
        output_dir=Path(args.output_dir),
        selected_categories=args.categories,
        selected_company_ids=args.company_ids,
        refresh_selected_company_ids=not args.skip_refresh,
        max_depth=args.max_depth,
    )

    print(f"Database: {result['database_path']}")
    print(f"Samples JSON: {result['samples_json_path']}")
    print(f"Output dir: {result['output_dir']}")
    print(f"Index: {result['index_path']}")
    if result["refreshed_company_ids"]:
        print(f"Refreshed company ids: {result['refreshed_company_ids']}")
    print(f"Generated: {len(result['generated'])}")
    for item in result["generated"]:
        print(f"  - {item['label']}: {item['company_name']} -> {item['html_path']}")
    if result["missing"]:
        print("Missing samples:")
        for item in result["missing"]:
            print(f"  - {item['label']}: {item['reason']}")


if __name__ == "__main__":
    main()