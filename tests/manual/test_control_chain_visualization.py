
from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import networkx as nx
from pyvis.network import Network

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.crud.company import get_company_by_id
from backend.crud.control_relationship import get_control_relationships_by_company_id
from backend.crud.shareholder import (
    get_current_shareholder_structures,
    get_entity_by_company_id,
)
from backend.database import DATABASE_URL, SessionLocal
from backend.models.company import Company  # noqa: F401
from backend.models.control_relationship import ControlRelationship  # noqa: F401
from backend.models.country_attribution import CountryAttribution  # noqa: F401
from backend.models.shareholder import ShareholderEntity, ShareholderStructure

OUTPUT_DIR = PROJECT_ROOT / "tests" / "output"
DEFAULT_SAMPLE_COUNT = 5
DEFAULT_MAX_DEPTH = 10
ORIGINAL_CONTROL_TYPE_PATTERN = re.compile(r"original_control_type=([A-Za-z_]+)")
EQUITY_LIKE_CONTROL_TYPES = {
    "equity",
    "indirect",
    "significant_equity",
    "direct_equity",
    "direct_equity_control",
}
EDGE_COLORS = {
    "equity": "#2563eb",
    "indirect": "#1d4ed8",
    "significant_equity": "#0f766e",
    "agreement": "#ea580c",
    "board_control": "#c2410c",
    "voting_right": "#059669",
    "nominee": "#7c3aed",
    "vie": "#b91c1c",
    "other": "#6b7280",
    "unknown": "#64748b",
    "mixed": "#334155",
}
NODE_TYPE_STYLES = {
    "company": {"background": "#dbeafe", "border": "#2563eb", "shape": "box"},
    "person": {"background": "#fee2e2", "border": "#dc2626", "shape": "ellipse"},
    "fund": {"background": "#dcfce7", "border": "#16a34a", "shape": "box"},
    "institution": {"background": "#ede9fe", "border": "#7c3aed", "shape": "box"},
    "public_float": {"background": "#fef3c7", "border": "#d97706", "shape": "box"},
    "government": {"background": "#ccfbf1", "border": "#0f766e", "shape": "box"},
    "other": {"background": "#e5e7eb", "border": "#6b7280", "shape": "box"},
    "unknown": {"background": "#e5e7eb", "border": "#6b7280", "shape": "box"},
}
NODE_ROLE_STYLES = {
    "target_company": {"border": "#b45309", "border_width": 4, "shadow": True},
    "actual_controller": {"border": "#b91c1c", "border_width": 4, "shadow": True},
    "persisted_controller": {"border": "#1d4ed8", "border_width": 3, "shadow": False},
    "intermediate": {"border": None, "border_width": 2, "shadow": False},
}
NODE_ROLE_LABELS = {
    "target_company": "Target Company",
    "actual_controller": "Actual Controller",
    "persisted_controller": "Persisted Controller",
    "intermediate": "Intermediate Holder",
}
NODE_LABEL_WIDTHS = {
    "company": 22,
    "person": 16,
    "fund": 18,
    "institution": 18,
    "public_float": 18,
    "government": 18,
    "other": 18,
    "unknown": 18,
}
MANUAL_COMPANY_ID: int | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate interactive control-chain visualizations from current "
            "shareholder_structures edges."
        ),
    )
    parser.add_argument(
        "--company-id",
        dest="company_ids",
        action="append",
        type=int,
        help="Target company_id. Repeat this argument to render multiple companies.",
    )
    parser.add_argument(
        "--sample-count",
        type=int,
        default=DEFAULT_SAMPLE_COUNT,
        help="When company ids are not provided, auto-select this many sample companies.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        help="Maximum upstream traversal depth.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory for generated HTML and JSON files.",
    )
    return parser.parse_args()


def _serialize_company(company: Company) -> dict[str, Any]:
    return {
        "id": company.id,
        "name": company.name,
        "stock_code": company.stock_code,
        "incorporation_country": company.incorporation_country,
        "listing_country": company.listing_country,
        "headquarters": company.headquarters,
        "description": company.description,
    }


def _serialize_entity(
    entity: ShareholderEntity,
    company_map: dict[int, Company],
) -> dict[str, Any]:
    mapped_company = company_map.get(entity.company_id) if entity.company_id else None
    return {
        "id": entity.id,
        "entity_name": _entity_display_name(entity, company_map),
        "raw_entity_name": entity.entity_name,
        "entity_type": entity.entity_type,
        "visual_category": _resolve_visual_entity_category(entity, company_map),
        "country": entity.country,
        "company_id": entity.company_id,
        "mapped_company_name": mapped_company.name if mapped_company is not None else None,
        "identifier_code": entity.identifier_code,
        "is_listed": entity.is_listed,
    }


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _deserialize_json(value: str | None) -> Any:
    if value in (None, ""):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _extract_original_control_type(remarks: str | None) -> str | None:
    if not remarks:
        return None
    match = ORIGINAL_CONTROL_TYPE_PATTERN.search(remarks)
    if match is None:
        return None
    return match.group(1).strip().lower()


def resolve_display_control_type(
    control_type: str | None,
    holding_ratio: Any = None,
    *,
    remarks: str | None = None,
) -> str:
    original_control_type = _extract_original_control_type(remarks)
    if original_control_type:
        return original_control_type

    normalized_control_type = (control_type or "").strip().lower()
    if normalized_control_type and normalized_control_type != "null":
        return normalized_control_type

    if _to_decimal(holding_ratio) is not None:
        return "equity"
    return "unknown"


def is_equity_like(control_type: str | None) -> bool:
    normalized_control_type = (control_type or "").strip().lower()
    return (
        normalized_control_type in EQUITY_LIKE_CONTROL_TYPES
        or normalized_control_type.endswith("_equity")
    )


def _format_percentage(value: Any) -> str | None:
    ratio = _to_decimal(value)
    if ratio is None:
        return None

    quantized_ratio = ratio.quantize(Decimal("0.01"))
    if quantized_ratio == quantized_ratio.to_integral():
        return format(quantized_ratio.quantize(Decimal("1")), "f")

    rendered = format(quantized_ratio.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _pick_preferred_ratio(
    *,
    holding_ratio: Any = None,
    control_ratio: Any = None,
    contribution_ratio: Any = None,
) -> Decimal | None:
    for candidate in (holding_ratio, control_ratio, contribution_ratio):
        ratio = _to_decimal(candidate)
        if ratio is not None and ratio > 0:
            return ratio
    return None


def build_edge_label(
    control_type: str | None,
    *,
    holding_ratio: Any = None,
    control_ratio: Any = None,
    contribution_ratio: Any = None,
    remarks: str | None = None,
) -> str:
    display_control_type = resolve_display_control_type(
        control_type,
        holding_ratio,
        remarks=remarks,
    )
    preferred_ratio = _pick_preferred_ratio(
        holding_ratio=holding_ratio,
        control_ratio=control_ratio,
        contribution_ratio=contribution_ratio,
    )
    if preferred_ratio is None:
        return display_control_type

    formatted_ratio = _format_percentage(preferred_ratio)
    if formatted_ratio is None:
        return display_control_type
    return f"{display_control_type} {formatted_ratio}%"


def _entity_display_name(
    entity: ShareholderEntity,
    company_map: dict[int, Company],
) -> str:
    if entity.entity_name and entity.entity_name.strip():
        return entity.entity_name.strip()

    if entity.company_id is not None:
        mapped_company = company_map.get(entity.company_id)
        if mapped_company is not None and mapped_company.name:
            return mapped_company.name

    return f"entity:{entity.id}"


def _resolve_visual_entity_category(
    entity: ShareholderEntity,
    company_map: dict[int, Company],
) -> str:
    display_name = _entity_display_name(entity, company_map)
    normalized_name = display_name.strip().lower()
    if normalized_name.startswith("public float"):
        return "public_float"

    normalized_entity_type = (entity.entity_type or "").strip().lower()
    if normalized_entity_type in NODE_TYPE_STYLES:
        return normalized_entity_type
    return "other"


def _wrap_node_label(
    value: str,
    *,
    width: int,
    max_lines: int = 3,
) -> str:
    compact_value = re.sub(r"\s+", " ", value).strip()
    if not compact_value:
        return "unknown"

    lines = textwrap.wrap(
        compact_value,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if not lines:
        lines = [compact_value]

    adjusted_lines: list[str] = []
    for line in lines:
        if len(line) <= width:
            adjusted_lines.append(line)
            continue
        adjusted_lines.extend(
            textwrap.wrap(
                line,
                width=width,
                break_long_words=True,
                break_on_hyphens=True,
            )
        )

    lines = adjusted_lines or [compact_value]
    if len(lines) > max_lines:
        truncated_tail = lines[max_lines - 1][: max(1, width - 1)].rstrip()
        lines = lines[: max_lines - 1] + [f"{truncated_tail}..."]
    return "\n".join(lines)


def _entity_title(
    entity: ShareholderEntity,
    company_map: dict[int, Company],
    *,
    role_label: str,
) -> str:
    mapped_company = company_map.get(entity.company_id) if entity.company_id else None
    visual_category = _resolve_visual_entity_category(entity, company_map)
    title_lines = [
        f"<b>{_entity_display_name(entity, company_map)}</b>",
        f"Entity ID: {entity.id}",
        f"Visual Category: {visual_category}",
        f"Raw Entity Type: {entity.entity_type or 'unknown'}",
        f"Country: {entity.country or 'N/A'}",
        f"Role: {role_label}",
    ]
    if mapped_company is not None:
        title_lines.append(
            f"Mapped Company: {mapped_company.name} (company_id={mapped_company.id})"
        )
    return "<br/>".join(title_lines)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").lower()
    return slug[:80] or "company"


def _make_output_base_name(company: dict[str, Any]) -> str:
    return f"control_chain_full_company_{company['id']}_{_slugify(company['name'])}"


def load_visualization_context(db) -> dict[str, Any]:
    companies = db.query(Company).order_by(Company.id.asc()).all()
    company_map = {company.id: company for company in companies}

    entities = db.query(ShareholderEntity).order_by(ShareholderEntity.id.asc()).all()
    entity_map = {entity.id: entity for entity in entities}

    entity_by_company_id: dict[int, ShareholderEntity] = {}
    for entity_id in sorted(entity_map):
        entity = entity_map[entity_id]
        if entity.company_id is None:
            continue
        entity_by_company_id.setdefault(entity.company_id, entity)

    incoming_map: dict[int, list[ShareholderStructure]] = defaultdict(list)
    skipped_edge_counts: dict[str, int] = defaultdict(int)
    for edge in get_current_shareholder_structures(db):
        if edge.from_entity_id == edge.to_entity_id:
            skipped_edge_counts["self_loop"] += 1
            continue
        incoming_map[edge.to_entity_id].append(edge)

    for to_entity_id, incoming_edges in incoming_map.items():
        incoming_map[to_entity_id] = sorted(
            incoming_edges,
            key=lambda item: (
                _to_decimal(item.holding_ratio) is None,
                -(_to_decimal(item.holding_ratio) or Decimal("0")),
                item.id,
            ),
        )

    return {
        "database_url": DATABASE_URL,
        "company_map": company_map,
        "entity_map": entity_map,
        "entity_by_company_id": entity_by_company_id,
        "incoming_map": incoming_map,
        "filter_rules": {
            "is_current": True,
            "effective_date": "effective_date is null or <= today",
            "expiry_date": "expiry_date is null or >= today",
            "data_source": "shareholder_structures (primary), control_relationships (optional highlight)",
        },
        "context_skip_counts": dict(skipped_edge_counts),
    }

def _serialize_structure_edge(
    edge: ShareholderStructure,
    *,
    company_map: dict[int, Company],
    entity_map: dict[int, ShareholderEntity],
) -> dict[str, Any] | None:
    from_entity = entity_map.get(edge.from_entity_id)
    to_entity = entity_map.get(edge.to_entity_id)
    if from_entity is None or to_entity is None:
        return None

    display_control_type = resolve_display_control_type(
        edge.control_type,
        edge.holding_ratio,
        remarks=edge.remarks,
    )
    label = build_edge_label(
        edge.control_type,
        holding_ratio=edge.holding_ratio,
        remarks=edge.remarks,
    )

    return {
        "id": edge.id,
        "from_entity_id": edge.from_entity_id,
        "to_entity_id": edge.to_entity_id,
        "from_entity_name": _entity_display_name(from_entity, company_map),
        "to_entity_name": _entity_display_name(to_entity, company_map),
        "from_entity_type": from_entity.entity_type,
        "to_entity_type": to_entity.entity_type,
        "holding_ratio": _serialize_decimal(_to_decimal(edge.holding_ratio)),
        "control_ratio": None,
        "contribution_ratio": None,
        "control_type": edge.control_type,
        "display_control_type": display_control_type,
        "label": label,
        "is_direct": bool(edge.is_direct),
        "is_current": bool(edge.is_current),
        "effective_date": (
            edge.effective_date.isoformat() if edge.effective_date is not None else None
        ),
        "expiry_date": (
            edge.expiry_date.isoformat() if edge.expiry_date is not None else None
        ),
        "reporting_period": edge.reporting_period,
        "source": edge.source,
        "remarks": edge.remarks,
    }


def _is_mixed_control_sequence(control_types: list[str]) -> bool:
    has_equity_like = any(is_equity_like(control_type) for control_type in control_types)
    has_non_equity = any(
        control_type not in {"unknown", ""}
        and not is_equity_like(control_type)
        for control_type in control_types
    )
    return has_equity_like and has_non_equity


def collect_upstream_subgraph(
    target_entity_id: int,
    *,
    context: dict[str, Any],
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> dict[str, Any]:
    company_map = context["company_map"]
    entity_map = context["entity_map"]
    incoming_map = context["incoming_map"]

    target_entity = entity_map.get(target_entity_id)
    target_name = (
        _entity_display_name(target_entity, company_map)
        if target_entity is not None
        else f"entity:{target_entity_id}"
    )

    visited_edge_ids: set[int] = set()
    raw_edges: list[dict[str, Any]] = []
    skipped_counts: dict[str, int] = defaultdict(int)
    control_types: set[str] = set()
    mixed_path_examples: list[dict[str, Any]] = []
    seen_mixed_path_keys: set[tuple[int, ...]] = set()
    distance_to_target: dict[int, int] = {target_entity_id: 0}
    max_depth_found = 0

    stack: list[tuple[int, list[int], list[str], list[str], int]] = [
        (target_entity_id, [target_entity_id], [target_name], [], 0)
    ]

    while stack:
        current_entity_id, path_entity_ids, path_entity_names, path_control_types, depth = stack.pop()
        incoming_edges = incoming_map.get(current_entity_id, [])
        if depth >= max_depth:
            if incoming_edges:
                skipped_counts["max_depth_cutoff"] += len(incoming_edges)
            continue

        for edge in incoming_edges:
            if edge.from_entity_id in path_entity_ids:
                skipped_counts["cycle_guard"] += 1
                continue

            serialized_edge = _serialize_structure_edge(
                edge,
                company_map=company_map,
                entity_map=entity_map,
            )
            if serialized_edge is None:
                skipped_counts["missing_entity"] += 1
                continue

            if edge.id not in visited_edge_ids:
                raw_edges.append(serialized_edge)
                visited_edge_ids.add(edge.id)
                control_types.add(serialized_edge["display_control_type"])

            upstream_entity = entity_map.get(edge.from_entity_id)
            if upstream_entity is None:
                skipped_counts["missing_upstream_entity"] += 1
                continue

            upstream_entity_name = _entity_display_name(upstream_entity, company_map)
            next_path_entity_ids = [edge.from_entity_id, *path_entity_ids]
            next_path_entity_names = [upstream_entity_name, *path_entity_names]
            next_path_control_types = [
                serialized_edge["display_control_type"],
                *path_control_types,
            ]
            next_depth = depth + 1
            distance_to_target[edge.from_entity_id] = min(
                distance_to_target.get(edge.from_entity_id, next_depth),
                next_depth,
            )
            max_depth_found = max(max_depth_found, next_depth)

            if _is_mixed_control_sequence(next_path_control_types):
                mixed_path_key = tuple(next_path_entity_ids)
                if mixed_path_key not in seen_mixed_path_keys and len(mixed_path_examples) < 5:
                    mixed_path_examples.append(
                        {
                            "path_entity_ids": next_path_entity_ids,
                            "path_entity_names": next_path_entity_names,
                            "control_types": next_path_control_types,
                        }
                    )
                    seen_mixed_path_keys.add(mixed_path_key)

            stack.append(
                (
                    edge.from_entity_id,
                    next_path_entity_ids,
                    next_path_entity_names,
                    next_path_control_types,
                    next_depth,
                )
            )

    return {
        "raw_edges": sorted(raw_edges, key=lambda item: item["id"]),
        "control_types": sorted(control_types),
        "mixed_path_visible": bool(mixed_path_examples),
        "mixed_path_examples": mixed_path_examples,
        "skipped_counts": dict(skipped_counts),
        "distance_to_target": distance_to_target,
        "max_depth": max_depth_found,
    }


def _parse_path_items_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        path_items: list[dict[str, Any]] = []
        best_path = payload.get("best_path")
        paths_top_k = payload.get("paths_top_k")
        if isinstance(best_path, dict):
            path_items.append(best_path)
        if isinstance(paths_top_k, list):
            path_items.extend(item for item in paths_top_k if isinstance(item, dict))
        if not path_items and "path_entity_names" in payload:
            path_items.append(payload)
        return path_items
    return []


def collect_persisted_control_context(db, company_id: int) -> dict[str, Any]:
    relationships = get_control_relationships_by_company_id(db, company_id)
    controller_entity_ids: set[int] = set()
    actual_controller_entity_ids: set[int] = set()
    highlighted_path_pairs: set[tuple[int, int]] = set()
    warnings: list[str] = []

    serialized_relationships = []
    for relationship in relationships:
        if relationship.controller_entity_id is not None:
            controller_entity_ids.add(relationship.controller_entity_id)
            if relationship.is_actual_controller:
                actual_controller_entity_ids.add(relationship.controller_entity_id)

        control_path_payload = _deserialize_json(relationship.control_path)
        for path_item in _parse_path_items_from_payload(control_path_payload):
            path_entity_ids = path_item.get("path_entity_ids")
            if not isinstance(path_entity_ids, list) or len(path_entity_ids) < 2:
                continue
            if not all(isinstance(entity_id, int) for entity_id in path_entity_ids):
                warnings.append(
                    f"Relationship {relationship.id} contains non-integer path ids and was only partially highlighted."
                )
                continue
            for index in range(len(path_entity_ids) - 1):
                highlighted_path_pairs.add(
                    (path_entity_ids[index], path_entity_ids[index + 1])
                )

        serialized_relationships.append(
            {
                "id": relationship.id,
                "controller_entity_id": relationship.controller_entity_id,
                "controller_name": relationship.controller_name,
                "controller_type": relationship.controller_type,
                "control_type": relationship.control_type,
                "control_ratio": _serialize_decimal(_to_decimal(relationship.control_ratio)),
                "is_actual_controller": relationship.is_actual_controller,
                "notes": relationship.notes,
                "control_path": control_path_payload,
            }
        )

    return {
        "controller_entity_ids": sorted(controller_entity_ids),
        "actual_controller_entity_ids": sorted(actual_controller_entity_ids),
        "highlighted_path_pairs": [list(item) for item in sorted(highlighted_path_pairs)],
        "persisted_control_relationships": serialized_relationships,
        "warnings": warnings,
    }


def summarize_company_control_graph(
    db,
    company_id: int,
    *,
    context: dict[str, Any],
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> dict[str, Any] | None:
    company = get_company_by_id(db, company_id)
    if company is None:
        return None

    target_entity = get_entity_by_company_id(db, company_id)
    if target_entity is None:
        return None

    subgraph_data = collect_upstream_subgraph(
        target_entity.id,
        context=context,
        max_depth=max_depth,
    )
    control_types = set(subgraph_data["control_types"])
    has_non_equity = any(
        control_type not in {"unknown", ""} and not is_equity_like(control_type)
        for control_type in control_types
    )

    return {
        "company_id": company.id,
        "company_name": company.name,
        "target_entity_id": target_entity.id,
        "raw_edge_count": len(subgraph_data["raw_edges"]),
        "max_depth": subgraph_data["max_depth"],
        "control_types": subgraph_data["control_types"],
        "has_non_equity": has_non_equity,
        "mixed_path_visible": subgraph_data["mixed_path_visible"],
    }


def load_company_visualization_data(
    db,
    company_id: int,
    *,
    context: dict[str, Any] | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> dict[str, Any] | None:
    if context is None:
        context = load_visualization_context(db)

    company = get_company_by_id(db, company_id)
    if company is None:
        return None

    target_entity = get_entity_by_company_id(db, company_id)
    if target_entity is None:
        return None

    subgraph_data = collect_upstream_subgraph(
        target_entity.id,
        context=context,
        max_depth=max_depth,
    )
    persisted_context = collect_persisted_control_context(db, company_id)

    return {
        "company": _serialize_company(company),
        "target_entity": _serialize_entity(target_entity, context["company_map"]),
        "database_url": context["database_url"],
        "filter_rules": context["filter_rules"],
        "raw_edges": subgraph_data["raw_edges"],
        "raw_edge_count": len(subgraph_data["raw_edges"]),
        "control_types": subgraph_data["control_types"],
        "mixed_path_visible": subgraph_data["mixed_path_visible"],
        "mixed_path_examples": subgraph_data["mixed_path_examples"],
        "distance_to_target": subgraph_data["distance_to_target"],
        "max_depth": subgraph_data["max_depth"],
        "skipped_counts": {
            **context["context_skip_counts"],
            **subgraph_data["skipped_counts"],
        },
        "persisted_control_relationships": persisted_context[
            "persisted_control_relationships"
        ],
        "controller_entity_ids": persisted_context["controller_entity_ids"],
        "actual_controller_entity_ids": persisted_context[
            "actual_controller_entity_ids"
        ],
        "highlighted_path_pairs": persisted_context["highlighted_path_pairs"],
        "warnings": persisted_context["warnings"],
    }

def _node_role_for_entity(
    entity_id: int,
    *,
    target_entity_id: int,
    actual_controller_ids: set[int],
    controller_ids: set[int],
) -> str:
    if entity_id == target_entity_id:
        return "target_company"
    if entity_id in actual_controller_ids:
        return "actual_controller"
    if entity_id in controller_ids:
        return "persisted_controller"
    return "intermediate"


def _edge_title(edge: dict[str, Any], *, highlighted: bool) -> str:
    title_lines = [
        f"<b>{edge['from_entity_name']}</b> -> <b>{edge['to_entity_name']}</b>",
        f"Structure ID: {edge['id']}",
        f"Display Label: {edge['label']}",
        f"Raw Control Type: {edge['control_type'] or 'NULL'}",
        f"Holding Ratio: {edge['holding_ratio'] or 'N/A'}",
        f"Source: {edge['source'] or 'N/A'}",
        f"Current Edge: {edge['is_current']}",
        f"Effective Date: {edge['effective_date'] or 'N/A'}",
        f"Expiry Date: {edge['expiry_date'] or 'N/A'}",
        f"Highlighted by persisted path: {'yes' if highlighted else 'no'}",
    ]
    if edge.get("remarks"):
        title_lines.append(f"Remarks: {edge['remarks']}")
    return "<br/>".join(title_lines)


def _build_node_style(
    *,
    visual_category: str,
    node_role: str,
) -> dict[str, Any]:
    type_style = NODE_TYPE_STYLES.get(visual_category, NODE_TYPE_STYLES["other"])
    role_style = NODE_ROLE_STYLES.get(node_role, NODE_ROLE_STYLES["intermediate"])
    border_color = role_style["border"] or type_style["border"]
    return {
        "color": {
            "background": type_style["background"],
            "border": border_color,
            "highlight": {
                "background": type_style["background"],
                "border": border_color,
            },
        },
        "shape": "box" if node_role == "target_company" else type_style["shape"],
        "borderWidth": role_style["border_width"],
        "shadow": role_style["shadow"],
        "font": {
            "color": "#0f172a",
            "size": 18 if node_role == "target_company" else 15,
            "face": "Segoe UI",
        },
        "margin": 12,
    }


def build_visual_graph(
    visualization_data: dict[str, Any],
    *,
    context: dict[str, Any],
) -> nx.DiGraph:
    company = visualization_data["company"]
    target_entity = visualization_data["target_entity"]
    raw_edges = visualization_data["raw_edges"]
    highlighted_path_pairs = {
        (item[0], item[1])
        for item in visualization_data["highlighted_path_pairs"]
        if isinstance(item, list) and len(item) == 2
    }
    actual_controller_ids = set(visualization_data["actual_controller_entity_ids"])
    controller_ids = set(visualization_data["controller_entity_ids"])
    entity_map = context["entity_map"]
    company_map = context["company_map"]
    distance_to_target = visualization_data["distance_to_target"]
    max_distance = max(distance_to_target.values(), default=0)

    graph = nx.DiGraph()
    target_node_key = f"company:{company['id']}"

    target_entity_record = entity_map.get(target_entity["id"])
    target_display_name = company["name"]
    target_title = (
        _entity_title(
            target_entity_record,
            company_map,
            role_label=NODE_ROLE_LABELS["target_company"],
        )
        if target_entity_record is not None
        else (
            f"<b>{company['name']}</b><br/>"
            f"Company ID: {company['id']}<br/>"
            f"Target Entity ID: {target_entity['id']}"
        )
    )
    graph.add_node(
        target_node_key,
        label=_wrap_node_label(
            target_display_name,
            width=NODE_LABEL_WIDTHS["company"],
        ),
        display_name=target_display_name,
        level=max_distance,
        node_role="target_company",
        role_label=NODE_ROLE_LABELS["target_company"],
        entity_id=target_entity["id"],
        entity_type=target_entity.get("entity_type") or "company",
        visual_category="company",
        title=target_title,
    )

    for edge in raw_edges:
        source_entity = entity_map.get(edge["from_entity_id"])
        target_entity_record = entity_map.get(edge["to_entity_id"])
        if source_entity is None or target_entity_record is None:
            continue

        source_key = f"entity:{edge['from_entity_id']}"
        target_key = (
            target_node_key
            if edge["to_entity_id"] == target_entity["id"]
            else f"entity:{edge['to_entity_id']}"
        )

        for entity, node_key in (
            (source_entity, source_key),
            (target_entity_record, target_key),
        ):
            if graph.has_node(node_key):
                continue
            node_role = _node_role_for_entity(
                entity.id,
                target_entity_id=target_entity["id"],
                actual_controller_ids=actual_controller_ids,
                controller_ids=controller_ids,
            )
            role_label = NODE_ROLE_LABELS[node_role]
            visual_category = _resolve_visual_entity_category(entity, company_map)
            display_name = _entity_display_name(entity, company_map)
            graph.add_node(
                node_key,
                label=_wrap_node_label(
                    display_name,
                    width=NODE_LABEL_WIDTHS.get(visual_category, 18),
                ),
                display_name=display_name,
                level=max_distance - distance_to_target.get(entity.id, 0),
                node_role=node_role,
                role_label=role_label,
                entity_id=entity.id,
                entity_type=entity.entity_type or "unknown",
                visual_category=visual_category,
                title=_entity_title(entity, company_map, role_label=role_label),
            )

        edge_pair = (edge["from_entity_id"], edge["to_entity_id"])
        highlighted = edge_pair in highlighted_path_pairs
        edge_title = _edge_title(edge, highlighted=highlighted)

        if graph.has_edge(source_key, target_key):
            existing = graph[source_key][target_key]
            if edge["label"] not in existing["labels"]:
                existing["labels"].append(edge["label"])
            existing["titles"].append(edge_title)
            if edge["display_control_type"] not in existing["control_types"]:
                existing["control_types"].append(edge["display_control_type"])
            existing["highlighted"] = existing["highlighted"] or highlighted
            existing["structure_ids"].append(edge["id"])
        else:
            graph.add_edge(
                source_key,
                target_key,
                labels=[edge["label"]],
                titles=[edge_title],
                control_types=[edge["display_control_type"]],
                highlighted=highlighted,
                structure_ids=[edge["id"]],
            )

    return graph


def export_html_graph(
    graph: nx.DiGraph,
    company: dict[str, Any],
    html_path: Path,
) -> None:
    html_path.parent.mkdir(parents=True, exist_ok=True)

    net = Network(
        height="920px",
        width="100%",
        directed=True,
        bgcolor="#f8fafc",
        font_color="#0f172a",
        notebook=False,
        cdn_resources="remote",
    )
    net.heading = f"Full Control Chain Visualization - {company['name']}"

    for node_key, attrs in graph.nodes(data=True):
        style = _build_node_style(
            visual_category=attrs.get("visual_category", "other"),
            node_role=attrs["node_role"],
        )
        net.add_node(
            node_key,
            label=attrs["label"],
            title=attrs["title"],
            level=attrs["level"],
            color=style["color"],
            shape=style["shape"],
            borderWidth=style["borderWidth"],
            shadow=style["shadow"],
            font=style["font"],
            margin=style["margin"],
        )

    for source, target, attrs in graph.edges(data=True):
        control_types = attrs["control_types"]
        label = " | ".join(attrs["labels"])
        if len(control_types) == 1:
            edge_color = EDGE_COLORS.get(control_types[0], EDGE_COLORS["other"])
        else:
            edge_color = EDGE_COLORS["mixed"]
        uses_non_equity = any(not is_equity_like(item) for item in control_types)

        net.add_edge(
            source,
            target,
            label=label,
            title="<br/><br/>".join(attrs["titles"]),
            arrows="to",
            color=edge_color,
            width=3.4 if attrs["highlighted"] else 2.4,
            dashes=uses_non_equity,
        )

    net.set_options(
        """
        {
          "layout": {
            "hierarchical": {
              "enabled": true,
              "direction": "UD",
              "sortMethod": "directed",
              "levelSeparation": 160,
              "nodeSpacing": 210,
              "treeSpacing": 250
            }
          },
          "physics": {
            "enabled": true,
            "hierarchicalRepulsion": {
              "nodeDistance": 180
            },
            "solver": "hierarchicalRepulsion"
          },
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true
          },
          "nodes": {
            "shape": "box",
            "font": {
              "multi": false,
              "size": 15,
              "strokeWidth": 0
            }
          },
          "edges": {
            "smooth": {
              "enabled": true,
              "type": "cubicBezier",
              "roundness": 0.3
            },
            "font": {
              "align": "middle",
              "size": 15,
              "strokeWidth": 0
            }
          }
        }
        """
    )
    net.write_html(str(html_path), open_browser=False, notebook=False)


def export_debug_json(json_path: Path, payload: dict[str, Any]) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def generate_company_visualization(
    db,
    company_id: int,
    *,
    context: dict[str, Any] | None = None,
    output_dir: Path = OUTPUT_DIR,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> dict[str, Any]:
    if context is None:
        context = load_visualization_context(db)

    visualization_data = load_company_visualization_data(
        db,
        company_id,
        context=context,
        max_depth=max_depth,
    )
    if visualization_data is None:
        return {
            "company_id": company_id,
            "status": "failed",
            "error": "Company or mapped target entity not found.",
        }

    company = visualization_data["company"]
    graph = build_visual_graph(visualization_data, context=context)
    output_base_name = _make_output_base_name(company)
    html_path = output_dir / f"{output_base_name}.html"
    json_path = output_dir / f"{output_base_name}.json"

    export_html_graph(graph, company, html_path)
    export_debug_json(json_path, visualization_data)

    return {
        "company_id": company["id"],
        "company_name": company["name"],
        "status": "success",
        "html_path": str(html_path.resolve()),
        "json_path": str(json_path.resolve()),
        "raw_edge_count": visualization_data["raw_edge_count"],
        "graph_node_count": graph.number_of_nodes(),
        "graph_edge_count": graph.number_of_edges(),
        "control_types": visualization_data["control_types"],
        "mixed_path_visible": visualization_data["mixed_path_visible"],
        "mixed_path_examples": visualization_data["mixed_path_examples"],
        "skipped_counts": visualization_data["skipped_counts"],
        "warnings": visualization_data["warnings"],
    }

def select_sample_companies(
    db,
    *,
    context: dict[str, Any] | None = None,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> list[dict[str, Any]]:
    if context is None:
        context = load_visualization_context(db)

    if sample_count < 1:
        return []

    preferred_categories = [
        (
            "direct_equity",
            lambda summary: summary["raw_edge_count"] > 0
            and summary["max_depth"] == 1
            and not summary["has_non_equity"],
        ),
        (
            "multi_layer_equity",
            lambda summary: summary["raw_edge_count"] > 0
            and summary["max_depth"] >= 3
            and not summary["has_non_equity"],
        ),
        ("mixed_path", lambda summary: summary["mixed_path_visible"]),
        (
            "voting_right",
            lambda summary: "voting_right" in summary["control_types"],
        ),
        (
            "board_control",
            lambda summary: "board_control" in summary["control_types"],
        ),
    ]

    selected_samples: list[dict[str, Any]] = []
    selected_company_ids: set[int] = set()
    filled_categories: set[str] = set()
    summary_cache: dict[int, dict[str, Any]] = {}

    ordered_company_ids = sorted(context["company_map"])
    for company_id in ordered_company_ids:
        target_entity = context["entity_by_company_id"].get(company_id)
        if target_entity is None:
            continue
        if not context["incoming_map"].get(target_entity.id):
            continue

        summary = summarize_company_control_graph(
            db,
            company_id,
            context=context,
            max_depth=max_depth,
        )
        if summary is None or summary["raw_edge_count"] == 0:
            continue
        summary_cache[company_id] = summary

        for category, matcher in preferred_categories:
            if category in filled_categories or company_id in selected_company_ids:
                continue
            if not matcher(summary):
                continue

            selected_samples.append(
                {
                    "category": category,
                    "company_id": company_id,
                    "company_name": summary["company_name"],
                    "summary": summary,
                }
            )
            selected_company_ids.add(company_id)
            filled_categories.add(category)
            break

        if len(selected_samples) >= sample_count and len(filled_categories) >= min(
            sample_count,
            len(preferred_categories),
        ):
            break

    if len(selected_samples) < sample_count:
        for company_id in ordered_company_ids:
            if company_id in selected_company_ids:
                continue
            summary = summary_cache.get(company_id)
            if summary is None:
                target_entity = context["entity_by_company_id"].get(company_id)
                if target_entity is None or not context["incoming_map"].get(target_entity.id):
                    continue
                summary = summarize_company_control_graph(
                    db,
                    company_id,
                    context=context,
                    max_depth=max_depth,
                )
                if summary is None or summary["raw_edge_count"] == 0:
                    continue
                summary_cache[company_id] = summary

            fallback_category = (
                "non_equity"
                if summary["has_non_equity"]
                else "additional_equity"
            )
            selected_samples.append(
                {
                    "category": fallback_category,
                    "company_id": company_id,
                    "company_name": summary["company_name"],
                    "summary": summary,
                }
            )
            selected_company_ids.add(company_id)
            if len(selected_samples) >= sample_count:
                break

    return selected_samples[:sample_count]


def generate_visualization_batch(
    db,
    company_ids: list[int],
    *,
    context: dict[str, Any] | None = None,
    output_dir: Path = OUTPUT_DIR,
    max_depth: int = DEFAULT_MAX_DEPTH,
    selection_metadata: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if context is None:
        context = load_visualization_context(db)

    metadata_by_company_id = {
        item["company_id"]: item
        for item in (selection_metadata or [])
        if "company_id" in item
    }

    results: list[dict[str, Any]] = []
    for company_id in company_ids:
        result = generate_company_visualization(
            db,
            company_id,
            context=context,
            output_dir=output_dir,
            max_depth=max_depth,
        )
        metadata = metadata_by_company_id.get(company_id)
        if metadata is not None:
            result["selected_category"] = metadata.get("category")
        results.append(result)

    report = {
        "database_url": context["database_url"],
        "read_only_visualization": True,
        "data_source": {
            "primary": "shareholder_structures",
            "supplementary": "control_relationships.control_path (highlight only)",
        },
        "filter_rules": context["filter_rules"],
        "requested_company_ids": company_ids,
        "success_count": sum(1 for item in results if item["status"] == "success"),
        "failure_count": sum(1 for item in results if item["status"] != "success"),
        "results": results,
    }

    report_path = output_dir / "control_chain_full_visualization_report.json"
    export_debug_json(report_path, report)
    report["report_path"] = str(report_path.resolve())
    return report


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir

    db = SessionLocal()
    try:
        context = load_visualization_context(db)

        if args.company_ids:
            company_ids = args.company_ids
            selection_metadata = [
                {
                    "category": "manual",
                    "company_id": company_id,
                    "company_name": context["company_map"].get(company_id).name
                    if context["company_map"].get(company_id) is not None
                    else f"company_{company_id}",
                }
                for company_id in args.company_ids
            ]
        else:
            sample_count = args.sample_count
            if MANUAL_COMPANY_ID is not None:
                company_ids = [MANUAL_COMPANY_ID]
                selection_metadata = [
                    {
                        "category": "manual_default",
                        "company_id": MANUAL_COMPANY_ID,
                        "company_name": context["company_map"].get(MANUAL_COMPANY_ID).name
                        if context["company_map"].get(MANUAL_COMPANY_ID) is not None
                        else f"company_{MANUAL_COMPANY_ID}",
                    }
                ]
            else:
                selection_metadata = select_sample_companies(
                    db,
                    context=context,
                    sample_count=sample_count,
                    max_depth=args.max_depth,
                )
                company_ids = [item["company_id"] for item in selection_metadata]

        if not company_ids:
            print("No companies were selected for visualization.")
            return 1

        report = generate_visualization_batch(
            db,
            company_ids,
            context=context,
            output_dir=output_dir,
            max_depth=args.max_depth,
            selection_metadata=selection_metadata,
        )

        print(f"Database: {report['database_url']}")
        print("Visualization data source: shareholder_structures (primary)")
        print(
            "Effective edge filter: is_current=true and date window compatible with today"
        )
        print(f"Requested companies: {len(company_ids)}")
        print(f"Success count: {report['success_count']}")
        print(f"Failure count: {report['failure_count']}")
        print(f"Report output: {report['report_path']}")

        for result in report["results"]:
            if result["status"] != "success":
                print(
                    f"[FAIL] company_id={result['company_id']} error={result['error']}"
                )
                continue
            print(
                "[OK] "
                f"company_id={result['company_id']} "
                f"category={result.get('selected_category', 'n/a')} "
                f"edges={result['raw_edge_count']} "
                f"control_types={','.join(result['control_types']) or 'none'} "
                f"mixed_path={result['mixed_path_visible']} "
                f"html={result['html_path']}"
            )

        return 0 if report["failure_count"] == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())









