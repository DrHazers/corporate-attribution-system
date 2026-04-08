from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
import sys
import textwrap
from typing import Any, Iterable

import networkx as nx
from pyvis.network import Network
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload, load_only

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.analysis.control_chain import analyze_control_chain_with_options
from backend.analysis.country_attribution_analysis import (
    analyze_country_attribution_with_options,
)
from backend.database import SessionLocal
from backend.models.shareholder import ShareholderEntity, ShareholderStructure

OUTPUT_HTML_DIR = PROJECT_ROOT / "tests" / "output"
LATEST_OUTPUT_HTML_PATH = OUTPUT_HTML_DIR / "control_graph.html"
DEFAULT_MAX_DEPTH = 3
NODE_BASE_SIZE = 20
ACTUAL_CONTROLLER_SIZE = 34
FOCUSED_CONTROLLER_SIZE = 38
TARGET_NODE_SIZE = 28
PLACEHOLDER_PATH_TOKENS = {
    "contractual arrangement",
    "contractual arrangements",
    "agreement",
    "agreements",
    "board control",
    "board governance",
    "voting right",
    "voting rights",
    "vie",
}
ENTITY_COLORS = {
    "company": "#2563eb",
    "person": "#dc2626",
    "fund": "#16a34a",
    "government": "#ea580c",
    "other": "#6b7280",
}
EDGE_TYPE_PRIORITY = {
    "board_control": 0,
    "vie": 1,
    "agreement": 2,
    "voting_right": 3,
    "nominee": 4,
    "equity": 5,
    "other": 6,
    "unknown": 7,
}
EDGE_VISUAL_STYLES = {
    "equity": {"color": "#111111", "dashes": False},
    "agreement": {"color": "#7c3aed", "dashes": True},
    "board_control": {"color": "#ea580c", "dashes": False},
    "voting_right": {"color": "#0f766e", "dashes": True},
    "nominee": {"color": "#be185d", "dashes": True},
    "vie": {"color": "#0891b2", "dashes": True},
    "other": {"color": "#64748b", "dashes": True},
    "unknown": {"color": "#94a3b8", "dashes": True},
}


@dataclass(slots=True)
class FocusRelationship:
    controller_entity_id: int | None
    controller_name: str | None
    controller_type: str | None
    control_type: str | None
    control_mode: str | None
    control_ratio: str | None
    semantic_flags: list[str]
    review_status: str | None
    is_actual_controller: bool
    basis: dict[str, Any] | None
    control_path: list[dict[str, Any]]


@dataclass(slots=True)
class HighlightContext:
    actual_controller_ids: set[int]
    actual_controller_names: list[str]
    focus_controller_id: int | None
    focus_controller_name: str | None
    highlighted_pairs: set[tuple[int, int]]
    highlighted_entity_ids: set[int]


@dataclass(slots=True)
class ControlGraphAnalysis:
    focus_label: str | None
    controller_count: int
    actual_controller_ids: set[int]
    actual_controller_names: list[str]
    focus_relationship: FocusRelationship | None
    attribution_type: str | None
    actual_control_country: str | None
    country_source_mode: str | None


@dataclass(slots=True)
class ControlGraphContext:
    target_entity: ShareholderEntity
    entities: dict[int, ShareholderEntity]
    edges: list[ShareholderStructure]
    highlights: HighlightContext
    analysis: ControlGraphAnalysis | None
    max_depth: int


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _safe_text(value: Any, *, default: str = "N/A") -> str:
    rendered = str(value).strip() if value is not None else ""
    return escape(rendered) if rendered else default


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


def _company_output_html_path(company_id: int, company_name: str) -> Path:
    return OUTPUT_HTML_DIR / f"control_graph_company_{company_id}_{_slugify(company_name)}.html"


def _normalize_entity_type(entity_type: str | None) -> str:
    normalized = _normalize_text(entity_type)
    if normalized in {"company", "person", "fund", "government"}:
        return normalized
    return "other"


def _normalize_relation_type(edge: ShareholderStructure) -> str:
    relation_type = _normalize_text(edge.relation_type)
    control_type = _normalize_text(edge.control_type)
    if relation_type:
        return relation_type
    if control_type in EDGE_TYPE_PRIORITY:
        return control_type
    return "equity" if edge.holding_ratio is not None else "unknown"


def _normalize_flags(values: Iterable[Any] | None) -> list[str]:
    return [
        str(value).strip()
        for value in values or []
        if str(value).strip()
    ]


def _render_flag_text(values: Iterable[Any] | None) -> str:
    flags = _normalize_flags(values)
    return ", ".join(flags) if flags else "none"


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _format_decimal(value: Any) -> str | None:
    numeric_value = _to_decimal(value)
    if numeric_value is None:
        return None
    quantized = numeric_value.quantize(Decimal("0.01"))
    rendered = format(quantized.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _ratio_to_percent(value: Any) -> Decimal | None:
    ratio = _to_decimal(value)
    if ratio is None:
        return None
    return ratio * Decimal("100") if ratio <= Decimal("1") else ratio


def _format_percent(value: Any) -> str | None:
    ratio_pct = _ratio_to_percent(value)
    if ratio_pct is None:
        return None
    rendered = _format_decimal(ratio_pct)
    return f"{rendered}%" if rendered is not None else None


def _format_score_pct(value: Any) -> str | None:
    rendered = _format_decimal(value)
    return f"{rendered}%" if rendered is not None else None


def _wrap_label(value: str, *, width: int = 18, max_lines: int = 3) -> str:
    compact = " ".join(value.split()).strip()
    if not compact:
        return "unknown"
    lines = textwrap.wrap(
        compact,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if not lines:
        lines = [compact]
    if len(lines) > max_lines:
        tail = lines[max_lines - 1][: max(1, width - 1)].rstrip()
        lines = lines[: max_lines - 1] + [f"{tail}..."]
    return "\n".join(lines)


def _node_tooltip(
    entity: ShareholderEntity,
    *,
    is_target: bool,
    is_actual_controller: bool,
    is_focus_controller: bool,
) -> str:
    roles = []
    if is_target:
        roles.append("target company")
    if is_focus_controller:
        roles.append("focused controller / candidate")
    if is_actual_controller:
        roles.append("actual controller")
    role_text = " / ".join(roles) if roles else "upstream entity"
    return "<br/>".join(
        [
            f"<b>{_safe_text(entity.entity_name)}</b>",
            f"Name: {_safe_text(entity.entity_name)}",
            f"Type: {_safe_text(entity.entity_type, default='other')}",
            f"Country: {_safe_text(entity.country, default='unknown')}",
            f"Role: {_safe_text(role_text)}",
        ]
    )


def _edge_tooltip(
    source_entity: ShareholderEntity,
    target_entity: ShareholderEntity,
    relations: list[ShareholderStructure],
    *,
    highlighted: bool,
) -> str:
    lines = [
        f"<b>{_safe_text(source_entity.entity_name)}</b> -> <b>{_safe_text(target_entity.entity_name)}</b>",
        f"Focused path: {'yes' if highlighted else 'no'}",
    ]
    for index, relation in enumerate(relations, start=1):
        lines.extend(
            [
                "",
                f"<b>Relationship {index}</b>",
                f"relation_type: {_safe_text(_normalize_relation_type(relation))}",
                f"relation_role: {_safe_text(relation.relation_role, default='unknown')}",
                f"control_type: {_safe_text(relation.control_type or _normalize_relation_type(relation))}",
                f"holding_ratio: {_safe_text(_format_percent(relation.holding_ratio))}",
                f"has_numeric_ratio: {'true' if relation.has_numeric_ratio else 'false'}",
                f"confidence_level: {_safe_text(relation.confidence_level, default='unknown')}",
            ]
        )
    return "<br/>".join(lines)


def _current_structure_filters(as_of: date) -> list[Any]:
    return [
        ShareholderStructure.is_current.is_(True),
        ShareholderStructure.is_direct.is_(True),
        or_(
            ShareholderStructure.effective_date.is_(None),
            ShareholderStructure.effective_date <= as_of,
        ),
        or_(
            ShareholderStructure.expiry_date.is_(None),
            ShareholderStructure.expiry_date >= as_of,
        ),
    ]


def _get_target_entity(db: Session, company_id: int) -> ShareholderEntity:
    target_entity = (
        db.query(ShareholderEntity)
        .filter(ShareholderEntity.company_id == company_id)
        .order_by(ShareholderEntity.id.asc())
        .first()
    )
    if target_entity is None:
        raise ValueError(f"No shareholder_entity mapped to company_id={company_id}.")
    return target_entity


def _load_upstream_edges(
    db: Session,
    *,
    target_entity: ShareholderEntity,
    max_depth: int,
) -> tuple[dict[int, ShareholderEntity], dict[int, ShareholderStructure]]:
    as_of = date.today()
    entities = {target_entity.id: target_entity}
    edges_by_id: dict[int, ShareholderStructure] = {}
    frontier = {target_entity.id}
    visited_upstream_nodes = {target_entity.id}

    for _ in range(max_depth):
        if not frontier:
            break

        edges = (
            db.query(ShareholderStructure)
            .options(
                load_only(
                    ShareholderStructure.id,
                    ShareholderStructure.from_entity_id,
                    ShareholderStructure.to_entity_id,
                    ShareholderStructure.holding_ratio,
                    ShareholderStructure.control_type,
                    ShareholderStructure.relation_type,
                    ShareholderStructure.has_numeric_ratio,
                    ShareholderStructure.relation_role,
                    ShareholderStructure.confidence_level,
                ),
                joinedload(ShareholderStructure.from_entity).load_only(
                    ShareholderEntity.id,
                    ShareholderEntity.entity_name,
                    ShareholderEntity.entity_type,
                    ShareholderEntity.country,
                    ShareholderEntity.company_id,
                ),
                joinedload(ShareholderStructure.to_entity).load_only(
                    ShareholderEntity.id,
                    ShareholderEntity.entity_name,
                    ShareholderEntity.entity_type,
                    ShareholderEntity.country,
                    ShareholderEntity.company_id,
                ),
            )
            .filter(ShareholderStructure.to_entity_id.in_(frontier))
            .filter(*_current_structure_filters(as_of))
            .order_by(ShareholderStructure.id.asc())
            .all()
        )

        next_frontier: set[int] = set()
        for edge in edges:
            if edge.from_entity_id == edge.to_entity_id:
                continue
            edges_by_id[edge.id] = edge
            if edge.from_entity is not None:
                entities[edge.from_entity_id] = edge.from_entity
            if edge.to_entity is not None:
                entities[edge.to_entity_id] = edge.to_entity
            if edge.from_entity_id not in visited_upstream_nodes:
                next_frontier.add(edge.from_entity_id)

        visited_upstream_nodes.update(next_frontier)
        frontier = next_frontier

    return entities, edges_by_id


def _build_name_index(entities: Iterable[ShareholderEntity]) -> dict[str, set[int]]:
    mapping: dict[str, set[int]] = defaultdict(set)
    for entity in entities:
        mapping[_normalize_text(entity.entity_name)].add(entity.id)
    return mapping


def _is_semantic_path_token(token: str) -> bool:
    normalized = _normalize_text(token)
    if normalized in PLACEHOLDER_PATH_TOKENS:
        return True
    return any(fragment in normalized for fragment in PLACEHOLDER_PATH_TOKENS)


def _iter_control_path_items(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        items: list[Any] = []
        if "path_entity_ids" in payload or "path" in payload:
            items.append(payload)
        best_path = payload.get("best_path")
        if best_path is not None:
            items.append(best_path)
        top_k = payload.get("paths_top_k")
        if isinstance(top_k, list):
            items.extend(top_k)
        return items
    return [payload]


def _normalize_control_path_payload(payload: Any) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    for item in _iter_control_path_items(payload):
        if isinstance(item, dict):
            normalized_items.append(item)
    return normalized_items


def _resolve_path_from_string(
    path_text: str,
    *,
    controller_entity_id: int | None,
    target_entity_id: int,
    name_index: dict[str, set[int]],
) -> list[int] | None:
    tokens = [segment.strip() for segment in path_text.split("->") if segment.strip()]
    if not tokens:
        return None

    named_tokens = [token for token in tokens if not _is_semantic_path_token(token)]
    resolved_ids: list[int] = []
    for token in named_tokens:
        candidate_ids = name_index.get(_normalize_text(token), set())
        if len(candidate_ids) != 1:
            resolved_ids = []
            break
        resolved_ids.append(next(iter(candidate_ids)))

    if len(resolved_ids) >= 2:
        return resolved_ids

    if controller_entity_id is not None:
        return [controller_entity_id, target_entity_id]
    return None


def _extract_highlight_sequences(
    control_path_payload: Any,
    *,
    controller_entity_id: int | None,
    target_entity_id: int,
    name_index: dict[str, set[int]],
) -> list[list[int]]:
    sequences: list[list[int]] = []

    for item in _iter_control_path_items(control_path_payload):
        if isinstance(item, dict):
            path_entity_ids = item.get("path_entity_ids")
            if (
                isinstance(path_entity_ids, list)
                and len(path_entity_ids) >= 2
                and all(isinstance(entity_id, int) for entity_id in path_entity_ids)
            ):
                sequences.append(path_entity_ids)
                continue

            path_text = item.get("path")
            if isinstance(path_text, str):
                sequence = _resolve_path_from_string(
                    path_text,
                    controller_entity_id=controller_entity_id,
                    target_entity_id=target_entity_id,
                    name_index=name_index,
                )
                if sequence is not None:
                    sequences.append(sequence)
        elif isinstance(item, str):
            sequence = _resolve_path_from_string(
                item,
                controller_entity_id=controller_entity_id,
                target_entity_id=target_entity_id,
                name_index=name_index,
            )
            if sequence is not None:
                sequences.append(sequence)

    if not sequences and controller_entity_id is not None:
        sequences.append([controller_entity_id, target_entity_id])

    return sequences


def _load_entities_by_ids(
    db: Session,
    entity_ids: set[int],
) -> dict[int, ShareholderEntity]:
    if not entity_ids:
        return {}
    rows = (
        db.query(ShareholderEntity)
        .options(
            load_only(
                ShareholderEntity.id,
                ShareholderEntity.entity_name,
                ShareholderEntity.entity_type,
                ShareholderEntity.country,
                ShareholderEntity.company_id,
            )
        )
        .filter(ShareholderEntity.id.in_(entity_ids))
        .order_by(ShareholderEntity.id.asc())
        .all()
    )
    return {row.id: row for row in rows}


def _load_current_edges_for_pairs(
    db: Session,
    *,
    pairs: set[tuple[int, int]],
) -> dict[int, ShareholderStructure]:
    if not pairs:
        return {}

    as_of = date.today()
    pair_clauses = [
        and_(
            ShareholderStructure.from_entity_id == from_entity_id,
            ShareholderStructure.to_entity_id == to_entity_id,
        )
        for from_entity_id, to_entity_id in sorted(pairs)
    ]
    rows = (
        db.query(ShareholderStructure)
        .options(
            load_only(
                ShareholderStructure.id,
                ShareholderStructure.from_entity_id,
                ShareholderStructure.to_entity_id,
                ShareholderStructure.holding_ratio,
                ShareholderStructure.control_type,
                ShareholderStructure.relation_type,
                ShareholderStructure.has_numeric_ratio,
                ShareholderStructure.relation_role,
                ShareholderStructure.confidence_level,
            ),
            joinedload(ShareholderStructure.from_entity).load_only(
                ShareholderEntity.id,
                ShareholderEntity.entity_name,
                ShareholderEntity.entity_type,
                ShareholderEntity.country,
                ShareholderEntity.company_id,
            ),
            joinedload(ShareholderStructure.to_entity).load_only(
                ShareholderEntity.id,
                ShareholderEntity.entity_name,
                ShareholderEntity.entity_type,
                ShareholderEntity.country,
                ShareholderEntity.company_id,
            ),
        )
        .filter(or_(*pair_clauses))
        .filter(*_current_structure_filters(as_of))
        .order_by(ShareholderStructure.id.asc())
        .all()
    )
    return {row.id: row for row in rows}


def _relationship_match_score(
    relationship: dict[str, Any],
    *,
    preferred_controller_name: str | None,
    preferred_control_type: str | None,
    preferred_semantic_flags: set[str],
) -> int:
    score = 0
    relationship_name = _normalize_text(relationship.get("controller_name"))
    relationship_type = _normalize_text(relationship.get("control_type"))
    relationship_flags = {
        _normalize_text(flag)
        for flag in relationship.get("semantic_flags") or []
        if str(flag).strip()
    }

    if preferred_controller_name:
        preferred_name = _normalize_text(preferred_controller_name)
        if relationship_name == preferred_name:
            score += 10
        elif preferred_name and preferred_name in relationship_name:
            score += 5

    if preferred_control_type:
        preferred_type = _normalize_text(preferred_control_type)
        if relationship_type == preferred_type:
            score += 6

    if preferred_semantic_flags:
        if preferred_semantic_flags.issubset(relationship_flags):
            score += 6
        elif relationship_flags.intersection(preferred_semantic_flags):
            score += 3

    if relationship.get("is_actual_controller"):
        score += 1

    return score


def _pick_focus_relationship_payload(
    relationships: list[dict[str, Any]],
    *,
    preferred_controller_name: str | None,
    preferred_control_type: str | None,
    preferred_semantic_flags: Iterable[str] | None,
) -> dict[str, Any] | None:
    if not relationships:
        return None

    preferred_flags = {
        _normalize_text(flag)
        for flag in preferred_semantic_flags or []
        if str(flag).strip()
    }

    scored_relationships: list[tuple[int, int, Decimal, int, dict[str, Any]]] = []
    for index, relationship in enumerate(relationships):
        match_score = _relationship_match_score(
            relationship,
            preferred_controller_name=preferred_controller_name,
            preferred_control_type=preferred_control_type,
            preferred_semantic_flags=preferred_flags,
        )
        is_actual_controller = 1 if relationship.get("is_actual_controller") else 0
        ratio = _to_decimal(relationship.get("control_ratio")) or Decimal("-1")
        scored_relationships.append(
            (match_score, is_actual_controller, ratio, -index, relationship)
        )

    best_match = max(scored_relationships, key=lambda item: item[:4])
    return best_match[-1]


def _build_focus_relationship(relationship: dict[str, Any] | None) -> FocusRelationship | None:
    if relationship is None:
        return None
    basis = relationship.get("basis") if isinstance(relationship.get("basis"), dict) else None
    return FocusRelationship(
        controller_entity_id=relationship.get("controller_entity_id"),
        controller_name=relationship.get("controller_name"),
        controller_type=relationship.get("controller_type"),
        control_type=relationship.get("control_type"),
        control_mode=relationship.get("control_mode"),
        control_ratio=relationship.get("control_ratio"),
        semantic_flags=_normalize_flags(relationship.get("semantic_flags")),
        review_status=relationship.get("review_status"),
        is_actual_controller=bool(relationship.get("is_actual_controller")),
        basis=basis,
        control_path=_normalize_control_path_payload(relationship.get("control_path")),
    )


def _build_analysis_context(
    db: Session,
    *,
    company_id: int,
    focus_label: str | None,
    preferred_controller_name: str | None,
    preferred_control_type: str | None,
    preferred_semantic_flags: Iterable[str] | None,
) -> ControlGraphAnalysis:
    control_chain = analyze_control_chain_with_options(db, company_id, refresh=False)
    relationships = control_chain.get("control_relationships") or []
    actual_controller_ids = {
        relationship.get("controller_entity_id")
        for relationship in relationships
        if relationship.get("is_actual_controller")
        and relationship.get("controller_entity_id") is not None
    }
    actual_controller_names = [
        relationship.get("controller_name")
        for relationship in relationships
        if relationship.get("is_actual_controller") and relationship.get("controller_name")
    ]
    focus_payload = _pick_focus_relationship_payload(
        relationships,
        preferred_controller_name=preferred_controller_name,
        preferred_control_type=preferred_control_type,
        preferred_semantic_flags=preferred_semantic_flags,
    )

    country_result = analyze_country_attribution_with_options(
        db,
        company_id,
        refresh=False,
    )
    country_attribution = (
        country_result.get("country_attribution")
        if isinstance(country_result, dict)
        else None
    )
    if not isinstance(country_attribution, dict):
        country_attribution = {}

    return ControlGraphAnalysis(
        focus_label=focus_label,
        controller_count=int(control_chain.get("controller_count", 0)),
        actual_controller_ids={entity_id for entity_id in actual_controller_ids if entity_id is not None},
        actual_controller_names=[
            str(name)
            for name in actual_controller_names
            if str(name).strip()
        ],
        focus_relationship=_build_focus_relationship(focus_payload),
        attribution_type=country_attribution.get("attribution_type"),
        actual_control_country=country_attribution.get("actual_control_country"),
        country_source_mode=country_attribution.get("source_mode"),
    )


def _build_highlight_context(
    db: Session,
    *,
    target_entity: ShareholderEntity,
    entities: dict[int, ShareholderEntity],
    edges_by_id: dict[int, ShareholderStructure],
    analysis: ControlGraphAnalysis,
) -> HighlightContext:
    focus_controller_id = (
        analysis.focus_relationship.controller_entity_id
        if analysis.focus_relationship is not None
        else None
    )
    missing_entity_ids = set(analysis.actual_controller_ids)
    if focus_controller_id is not None:
        missing_entity_ids.add(focus_controller_id)
    missing_entity_ids -= set(entities)
    if missing_entity_ids:
        entities.update(_load_entities_by_ids(db, missing_entity_ids))

    name_index = _build_name_index(entities.values())
    highlighted_pairs: set[tuple[int, int]] = set()
    highlighted_entity_ids: set[int] = set()

    if analysis.focus_relationship is not None:
        sequences = _extract_highlight_sequences(
            analysis.focus_relationship.control_path,
            controller_entity_id=focus_controller_id,
            target_entity_id=target_entity.id,
            name_index=name_index,
        )
        for sequence in sequences:
            highlighted_entity_ids.update(sequence)
            for index in range(len(sequence) - 1):
                highlighted_pairs.add((sequence[index], sequence[index + 1]))

    missing_highlight_entity_ids = highlighted_entity_ids - set(entities)
    if missing_highlight_entity_ids:
        entities.update(_load_entities_by_ids(db, missing_highlight_entity_ids))

    existing_pairs = {
        (edge.from_entity_id, edge.to_entity_id)
        for edge in edges_by_id.values()
    }
    missing_pairs = highlighted_pairs - existing_pairs
    if missing_pairs:
        edges_by_id.update(_load_current_edges_for_pairs(db, pairs=missing_pairs))

    existing_pairs = {
        (edge.from_entity_id, edge.to_entity_id)
        for edge in edges_by_id.values()
    }
    resolved_highlight_pairs = highlighted_pairs & existing_pairs
    resolved_highlight_entity_ids = {
        entity_id
        for pair in resolved_highlight_pairs
        for entity_id in pair
    }

    for edge in edges_by_id.values():
        if edge.from_entity is not None:
            entities[edge.from_entity_id] = edge.from_entity
        if edge.to_entity is not None:
            entities[edge.to_entity_id] = edge.to_entity

    return HighlightContext(
        actual_controller_ids=set(analysis.actual_controller_ids),
        actual_controller_names=list(analysis.actual_controller_names),
        focus_controller_id=focus_controller_id,
        focus_controller_name=(
            analysis.focus_relationship.controller_name
            if analysis.focus_relationship is not None
            else None
        ),
        highlighted_pairs=resolved_highlight_pairs,
        highlighted_entity_ids=resolved_highlight_entity_ids,
    )


def _load_control_graph_context(
    db: Session,
    *,
    company_id: int,
    max_depth: int = DEFAULT_MAX_DEPTH,
    focus_label: str | None = None,
    preferred_controller_name: str | None = None,
    preferred_control_type: str | None = None,
    preferred_semantic_flags: Iterable[str] | None = None,
) -> ControlGraphContext:
    target_entity = _get_target_entity(db, company_id)
    entities, edges_by_id = _load_upstream_edges(
        db,
        target_entity=target_entity,
        max_depth=max_depth,
    )
    analysis = _build_analysis_context(
        db,
        company_id=company_id,
        focus_label=focus_label,
        preferred_controller_name=preferred_controller_name,
        preferred_control_type=preferred_control_type,
        preferred_semantic_flags=preferred_semantic_flags,
    )
    highlights = _build_highlight_context(
        db,
        target_entity=target_entity,
        entities=entities,
        edges_by_id=edges_by_id,
        analysis=analysis,
    )
    return ControlGraphContext(
        target_entity=target_entity,
        entities=entities,
        edges=list(edges_by_id.values()),
        highlights=highlights,
        analysis=analysis,
        max_depth=max_depth,
    )


def _compute_distance_to_target(
    target_entity_id: int,
    edges: Iterable[ShareholderStructure],
) -> dict[int, int]:
    incoming_map: dict[int, set[int]] = defaultdict(set)
    for edge in edges:
        incoming_map[edge.to_entity_id].add(edge.from_entity_id)

    distance_to_target = {target_entity_id: 0}
    frontier = {target_entity_id}
    current_distance = 0
    while frontier:
        next_frontier: set[int] = set()
        for entity_id in frontier:
            for upstream_entity_id in incoming_map.get(entity_id, set()):
                if upstream_entity_id in distance_to_target:
                    continue
                distance_to_target[upstream_entity_id] = current_distance + 1
                next_frontier.add(upstream_entity_id)
        frontier = next_frontier
        current_distance += 1
    return distance_to_target


def _build_node_attributes(
    entity: ShareholderEntity,
    *,
    target_entity_id: int,
    actual_controller_ids: set[int],
    focus_controller_id: int | None,
    highlighted_entity_ids: set[int],
    level: int,
) -> dict[str, Any]:
    entity_type = _normalize_entity_type(entity.entity_type)
    fill_color = ENTITY_COLORS[entity_type]
    is_target = entity.id == target_entity_id
    is_actual_controller = entity.id in actual_controller_ids
    is_focus_controller = entity.id == focus_controller_id
    is_path_node = entity.id in highlighted_entity_ids

    shape = "ellipse" if entity_type == "person" else "box"

    if is_focus_controller:
        border_color = "#be123c"
        border_width = 5
        size = FOCUSED_CONTROLLER_SIZE
        shadow = True
    elif is_actual_controller:
        border_color = "#7c3aed"
        border_width = 4
        size = ACTUAL_CONTROLLER_SIZE
        shadow = True
    elif is_target:
        border_color = "#0f172a"
        border_width = 4
        size = TARGET_NODE_SIZE
        shadow = True
    elif is_path_node:
        border_color = "#f59e0b"
        border_width = 3
        size = NODE_BASE_SIZE + 2
        shadow = False
    else:
        border_color = "#dbeafe" if entity_type == "company" else "#e5e7eb"
        border_width = 2
        size = NODE_BASE_SIZE
        shadow = False

    font_size = 16 if (is_target or is_focus_controller) else 14
    min_height = 74 if is_focus_controller else 68 if is_actual_controller else 64 if is_target else 56
    min_width = 178 if is_focus_controller else 168 if is_actual_controller else 156 if is_target else 132

    return {
        "label": _wrap_label(entity.entity_name, width=18),
        "title": _node_tooltip(
            entity,
            is_target=is_target,
            is_actual_controller=is_actual_controller,
            is_focus_controller=is_focus_controller,
        ),
        "shape": shape,
        "size": size,
        "level": level,
        "borderWidth": border_width,
        "shadow": shadow,
        "margin": {
            "top": 12,
            "right": 14,
            "bottom": 12,
            "left": 14,
        },
        "widthConstraint": {
            "minimum": min_width,
            "maximum": 186,
        },
        "heightConstraint": {
            "minimum": min_height,
        },
        "shapeProperties": {
            "borderRadius": 10,
        },
        "color": {
            "background": fill_color,
            "border": border_color,
            "highlight": {
                "background": fill_color,
                "border": border_color,
            },
        },
        "font": {
            "color": "#ffffff",
            "size": font_size,
            "face": "Segoe UI",
            "strokeWidth": 0,
            "multi": True,
            "bold": {
                "color": "#ffffff",
                "size": font_size,
                "face": "Segoe UI",
                "mod": "bold",
            },
        },
    }


def _edge_style_key(relation_type: str) -> str:
    return relation_type if relation_type in EDGE_VISUAL_STYLES else "other"


def _non_equity_label(edge: ShareholderStructure, relation_type: str) -> str:
    control_type = _normalize_text(edge.control_type)
    if relation_type == "vie" or control_type == "vie":
        return "VIE"
    if relation_type:
        return relation_type
    if control_type:
        return control_type
    return "other"


def _edge_label(edge: ShareholderStructure) -> str:
    relation_type = _normalize_relation_type(edge)
    if relation_type == "equity":
        return _format_percent(edge.holding_ratio) or "equity"
    return _non_equity_label(edge, relation_type)


def _edge_width(relations: list[ShareholderStructure], *, highlighted: bool) -> float:
    numeric_ratios = [
        ratio
        for ratio in (
            _ratio_to_percent(relation.holding_ratio)
            for relation in relations
        )
        if ratio is not None
    ]
    max_ratio = max(numeric_ratios) if numeric_ratios else Decimal("0")

    if numeric_ratios:
        width = 2.0 + min(float(max_ratio) / 12.0, 5.0)
    else:
        width = 3.0

    if highlighted:
        width = max(width + 2.0, 5.2)
    return round(width, 2)


def _pick_primary_relation(relations: list[ShareholderStructure]) -> ShareholderStructure:
    return min(
        relations,
        key=lambda relation: (
            EDGE_TYPE_PRIORITY.get(_normalize_relation_type(relation), 99),
            relation.id,
        ),
    )


def _edge_style(relations: list[ShareholderStructure], *, highlighted: bool) -> dict[str, Any]:
    primary_relation = _pick_primary_relation(relations)
    primary_relation_type = _normalize_relation_type(primary_relation)
    style = EDGE_VISUAL_STYLES[_edge_style_key(primary_relation_type)]
    color = "#dc2626" if highlighted else style["color"]
    dashes = style["dashes"]

    unique_labels = list(dict.fromkeys(_edge_label(relation) for relation in relations))
    display_label = unique_labels[0] if unique_labels else ""
    if len(unique_labels) > 1:
        display_label = f"{display_label} +"

    return {
        "label": display_label,
        "color": color,
        "dashes": dashes,
        "width": _edge_width(relations, highlighted=highlighted),
        "smooth": {
            "enabled": True,
            "type": "cubicBezier",
            "forceDirection": "vertical",
            "roundness": 0.06 if highlighted else 0.03,
        },
    }


def _build_visual_graph(context: ControlGraphContext) -> nx.DiGraph:
    graph = nx.DiGraph()
    distance_to_target = _compute_distance_to_target(
        context.target_entity.id,
        context.edges,
    )
    max_distance = max(distance_to_target.values(), default=0)

    for entity_id, entity in sorted(context.entities.items()):
        if entity_id not in distance_to_target and entity_id != context.target_entity.id:
            continue
        graph.add_node(
            entity_id,
            **_build_node_attributes(
                entity,
                target_entity_id=context.target_entity.id,
                actual_controller_ids=context.highlights.actual_controller_ids,
                focus_controller_id=context.highlights.focus_controller_id,
                highlighted_entity_ids=context.highlights.highlighted_entity_ids,
                level=max_distance - distance_to_target.get(entity_id, 0),
            ),
        )

    edge_groups: dict[tuple[int, int], list[ShareholderStructure]] = defaultdict(list)
    for edge in sorted(context.edges, key=lambda item: item.id):
        if edge.from_entity_id not in graph.nodes or edge.to_entity_id not in graph.nodes:
            continue
        edge_groups[(edge.from_entity_id, edge.to_entity_id)].append(edge)

    for (from_entity_id, to_entity_id), relations in edge_groups.items():
        source_entity = context.entities[from_entity_id]
        target_entity = context.entities[to_entity_id]
        highlighted = (from_entity_id, to_entity_id) in context.highlights.highlighted_pairs
        graph.add_edge(
            from_entity_id,
            to_entity_id,
            title=_edge_tooltip(
                source_entity,
                target_entity,
                relations,
                highlighted=highlighted,
            ),
            relation_types=sorted(
                {
                    _normalize_relation_type(relation)
                    for relation in relations
                }
            ),
            highlighted=highlighted,
            structure_ids=[relation.id for relation in relations],
            **_edge_style(relations, highlighted=highlighted),
        )

    return graph


def _basis_evidence_lines(basis: dict[str, Any] | None) -> list[str]:
    if not isinstance(basis, dict):
        return []
    evidence_summary = basis.get("evidence_summary")
    if not isinstance(evidence_summary, list):
        return []
    return [
        str(item).strip()
        for item in evidence_summary
        if str(item).strip()
    ][:3]


def _path_summary_lines(focus_relationship: FocusRelationship | None) -> list[str]:
    if focus_relationship is None:
        return []

    lines: list[str] = []
    for item in focus_relationship.control_path[:3]:
        path_names = [
            str(name).strip()
            for name in item.get("path_entity_names") or []
            if str(name).strip()
        ]
        if not path_names:
            path_names = [
                f"Entity {entity_id}"
                for entity_id in item.get("path_entity_ids") or []
            ]
        relation_types = [
            _normalize_text(edge.get("relation_type"))
            for edge in item.get("edges") or []
            if _normalize_text(edge.get("relation_type"))
        ]
        relation_text = " + ".join(dict.fromkeys(relation_types)) if relation_types else "unknown"
        score_text = _format_score_pct(item.get("path_score_pct"))
        path_text = " -> ".join(path_names) if path_names else "unresolved path"
        if score_text:
            lines.append(f"{path_text} [{relation_text}] ({score_text})")
        else:
            lines.append(f"{path_text} [{relation_text}]")
    return lines


def _render_summary_list(items: list[str], *, empty_message: str) -> str:
    if not items:
        return f"<div class=\"control-graph-empty\">{_safe_text(empty_message)}</div>"
    rendered_items = "".join(
        f"<li>{_safe_text(item)}</li>"
        for item in items
    )
    return f"<ul class=\"control-graph-list\">{rendered_items}</ul>"


def _build_summary_card(context: ControlGraphContext, graph: nx.DiGraph) -> str:
    analysis = context.analysis
    focus_relationship = analysis.focus_relationship if analysis is not None else None
    focus_label = analysis.focus_label if analysis is not None and analysis.focus_label else "Control Graph"
    relation_types = sorted({_normalize_relation_type(edge) for edge in context.edges})
    relation_text = ", ".join(relation_types) if relation_types else "none"
    focus_controller_text = (
        focus_relationship.controller_name
        if focus_relationship is not None and focus_relationship.controller_name
        else "not identified"
    )
    actual_controller_text = (
        " / ".join(dict.fromkeys(context.highlights.actual_controller_names))
        if context.highlights.actual_controller_names
        else "not identified"
    )
    evidence_lines = _basis_evidence_lines(
        focus_relationship.basis if focus_relationship is not None else None
    )
    path_lines = _path_summary_lines(focus_relationship)

    return f"""
    <style>
      body {{
        margin: 0;
        font-family: "Segoe UI", "PingFang SC", sans-serif;
        background:
          radial-gradient(circle at top left, rgba(37, 99, 235, 0.12), transparent 30%),
          radial-gradient(circle at top right, rgba(234, 88, 12, 0.12), transparent 28%),
          linear-gradient(180deg, #f8fbff 0%, #eef4ff 100%);
      }}
      #mynetwork {{
        height: calc(100vh - 40px) !important;
        width: calc(100vw - 40px) !important;
        margin: 20px !important;
        border-radius: 24px !important;
        box-shadow: 0 24px 60px rgba(15, 23, 42, 0.14) !important;
        background: rgba(255, 255, 255, 0.85) !important;
        border: 1px solid rgba(148, 163, 184, 0.28) !important;
      }}
      .control-graph-card {{
        position: fixed;
        z-index: 9999;
        background: rgba(255, 255, 255, 0.94);
        backdrop-filter: blur(14px);
        border: 1px solid rgba(148, 163, 184, 0.24);
        border-radius: 20px;
        box-shadow: 0 18px 45px rgba(15, 23, 42, 0.16);
        color: #0f172a;
      }}
      #control-graph-summary {{
        top: 28px;
        left: 28px;
        width: 420px;
        padding: 18px 20px;
      }}
      #control-graph-legend {{
        top: 28px;
        right: 28px;
        width: 280px;
        padding: 16px 18px;
      }}
      .control-graph-kicker {{
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #475569;
        margin-bottom: 8px;
      }}
      .control-graph-title {{
        font-size: 24px;
        font-weight: 800;
        line-height: 1.2;
        margin: 0 0 10px 0;
      }}
      .control-graph-subtitle {{
        font-size: 13px;
        color: #475569;
        line-height: 1.55;
        margin: 0 0 14px 0;
      }}
      .control-graph-meta {{
        font-size: 13px;
        line-height: 1.6;
      }}
      .control-graph-meta-row {{
        margin: 6px 0;
      }}
      .control-graph-meta strong {{
        color: #0f172a;
      }}
      .control-graph-section-title {{
        margin-top: 14px;
        margin-bottom: 6px;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #475569;
      }}
      .control-graph-list {{
        margin: 0;
        padding-left: 18px;
        font-size: 13px;
        line-height: 1.55;
      }}
      .control-graph-list li {{
        margin: 4px 0;
      }}
      .control-graph-empty {{
        font-size: 13px;
        color: #64748b;
      }}
      .legend-item {{
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 13px;
        line-height: 1.45;
        margin: 8px 0;
      }}
      .legend-dot {{
        width: 12px;
        height: 12px;
        border-radius: 999px;
        flex: 0 0 auto;
      }}
      .legend-line {{
        width: 26px;
        height: 0;
        border-top: 3px solid;
        flex: 0 0 auto;
      }}
      .legend-line.dashed {{
        border-top-style: dashed;
      }}
      .legend-chip {{
        width: 18px;
        height: 18px;
        border-radius: 6px;
        flex: 0 0 auto;
        background: #ffffff;
        border: 3px solid;
      }}
      @media (max-width: 1100px) {{
        .control-graph-card {{
          position: static;
          width: auto !important;
          margin: 20px;
        }}
        #mynetwork {{
          height: 70vh !important;
          width: calc(100vw - 40px) !important;
          margin-top: 0 !important;
        }}
      }}
    </style>
    <div id="control-graph-summary" class="control-graph-card">
      <div class="control-graph-kicker">{_safe_text(focus_label)}</div>
      <div class="control-graph-title">{_safe_text(context.target_entity.entity_name)}</div>
      <div class="control-graph-subtitle">
        Built from current shareholder structures plus persisted control analysis results.
        The focused path is highlighted in red and reflects the selected demo relationship or candidate.
      </div>
      <div class="control-graph-meta">
        <div class="control-graph-meta-row"><strong>Focused controller / candidate:</strong> {_safe_text(focus_controller_text)}</div>
        <div class="control-graph-meta-row"><strong>Focus control type:</strong> {_safe_text(focus_relationship.control_type if focus_relationship else None)}</div>
        <div class="control-graph-meta-row"><strong>Control mode:</strong> {_safe_text(focus_relationship.control_mode if focus_relationship else None)}</div>
        <div class="control-graph-meta-row"><strong>Focus score:</strong> {_safe_text(_format_score_pct(focus_relationship.control_ratio) if focus_relationship else None)}</div>
        <div class="control-graph-meta-row"><strong>Semantic flags:</strong> {_safe_text(_render_flag_text(focus_relationship.semantic_flags if focus_relationship else []), default='none')}</div>
        <div class="control-graph-meta-row"><strong>Attribution type:</strong> {_safe_text(analysis.attribution_type if analysis else None)}</div>
        <div class="control-graph-meta-row"><strong>Actual control country:</strong> {_safe_text(analysis.actual_control_country if analysis else None)}</div>
        <div class="control-graph-meta-row"><strong>Country source mode:</strong> {_safe_text(analysis.country_source_mode if analysis else None)}</div>
        <div class="control-graph-meta-row"><strong>Actual controller:</strong> {_safe_text(actual_controller_text)}</div>
        <div class="control-graph-meta-row"><strong>Controllers in result set:</strong> {_safe_text(analysis.controller_count if analysis else None, default='0')}</div>
        <div class="control-graph-meta-row"><strong>Nodes / edges:</strong> {graph.number_of_nodes()} / {graph.number_of_edges()}</div>
        <div class="control-graph-meta-row"><strong>Relation types present:</strong> {_safe_text(relation_text, default='none')}</div>
      </div>
      <div class="control-graph-section-title">Basis Summary</div>
      {_render_summary_list(evidence_lines, empty_message='No evidence summary available.')}
      <div class="control-graph-section-title">Key Control Paths</div>
      {_render_summary_list(path_lines, empty_message='No normalized control path available.')}
    </div>
    <div id="control-graph-legend" class="control-graph-card">
      <div class="control-graph-kicker">Legend</div>
      <div class="legend-item"><span class="legend-dot" style="background:#2563eb;"></span><span>Company</span></div>
      <div class="legend-item"><span class="legend-dot" style="background:#dc2626;"></span><span>Person</span></div>
      <div class="legend-item"><span class="legend-dot" style="background:#16a34a;"></span><span>Fund</span></div>
      <div class="legend-item"><span class="legend-dot" style="background:#ea580c;"></span><span>Government</span></div>
      <div class="legend-item"><span class="legend-dot" style="background:#6b7280;"></span><span>Other</span></div>
      <div class="legend-item"><span class="legend-chip" style="border-color:#0f172a;"></span><span>Target company</span></div>
      <div class="legend-item"><span class="legend-chip" style="border-color:#be123c;"></span><span>Focused controller / candidate</span></div>
      <div class="legend-item"><span class="legend-chip" style="border-color:#7c3aed;"></span><span>Actual controller</span></div>
      <div class="legend-item"><span class="legend-line" style="border-color:#111111;"></span><span>Equity</span></div>
      <div class="legend-item"><span class="legend-line dashed" style="border-color:#7c3aed;"></span><span>Agreement</span></div>
      <div class="legend-item"><span class="legend-line" style="border-color:#ea580c;"></span><span>Board control</span></div>
      <div class="legend-item"><span class="legend-line dashed" style="border-color:#0f766e;"></span><span>Voting right</span></div>
      <div class="legend-item"><span class="legend-line dashed" style="border-color:#be185d;"></span><span>Nominee</span></div>
      <div class="legend-item"><span class="legend-line dashed" style="border-color:#0891b2;"></span><span>VIE</span></div>
      <div class="legend-item"><span class="legend-line" style="border-color:#dc2626;border-width:4px;"></span><span>Focused control path</span></div>
    </div>
    <script>
      window.addEventListener("load", function () {{
        if (typeof network !== "undefined") {{
          network.once("stabilized", function () {{
            network.fit({{
              animation: {{
                duration: 700,
                easingFunction: "easeInOutCubic"
              }}
            }});
          }});
        }}
      }});
    </script>
    """


def _decorate_html(
    html_path: Path,
    *,
    context: ControlGraphContext,
    graph: nx.DiGraph,
) -> None:
    raw_html = html_path.read_text(encoding="utf-8")
    raw_html = raw_html.replace("<body>", f"<body>{_build_summary_card(context, graph)}", 1)
    html_path.write_text(raw_html, encoding="utf-8")


def _export_html_graph(
    context: ControlGraphContext,
    graph: nx.DiGraph,
    html_path: Path,
) -> None:
    html_path.parent.mkdir(parents=True, exist_ok=True)

    net = Network(
        height="100vh",
        width="100%",
        directed=True,
        bgcolor="#ffffff",
        font_color="#0f172a",
        notebook=False,
        cdn_resources="in_line",
    )
    net.heading = ""

    for node_id, attrs in graph.nodes(data=True):
        net.add_node(node_id, **attrs)

    for source, target, attrs in graph.edges(data=True):
        net.add_edge(
            source,
            target,
            label=attrs["label"],
            title=attrs["title"],
            arrows={
                "to": {
                    "enabled": True,
                    "scaleFactor": 0.65,
                }
            },
            color=attrs["color"],
            dashes=attrs["dashes"],
            width=attrs["width"],
            smooth=attrs["smooth"],
            shadow=attrs["highlighted"],
            font={
                "align": "top",
                "size": 13,
                "strokeWidth": 6,
                "strokeColor": "rgba(255,255,255,0.96)",
                "background": "rgba(255,255,255,0.92)",
                "face": "Segoe UI",
                "vadjust": -4,
            },
            labelHighlightBold=False,
        )

    net.set_options(
        """
        {
          "layout": {
            "hierarchical": {
              "enabled": true,
              "direction": "UD",
              "sortMethod": "directed",
              "levelSeparation": 180,
              "nodeSpacing": 170,
              "treeSpacing": 190,
              "blockShifting": true,
              "edgeMinimization": true,
              "parentCentralization": true
            }
          },
          "interaction": {
            "hover": true,
            "dragNodes": true,
            "dragView": true,
            "zoomView": true,
            "navigationButtons": true,
            "keyboard": true,
            "multiselect": true,
            "selectConnectedEdges": false
          },
          "physics": {
            "enabled": true,
            "hierarchicalRepulsion": {
              "centralGravity": 0.02,
              "springLength": 150,
              "springConstant": 0.01,
              "nodeDistance": 165,
              "damping": 0.22
            },
            "solver": "hierarchicalRepulsion",
            "stabilization": {
              "enabled": true,
              "iterations": 1000,
              "fit": true
            }
          },
          "nodes": {
            "borderWidthSelected": 5,
            "shape": "box",
            "font": {
              "multi": true
            }
          },
          "edges": {
            "selectionWidth": 1.4,
            "hoverWidth": 0.6,
            "arrowStrikethrough": false,
            "smooth": {
              "enabled": true,
              "type": "cubicBezier",
              "forceDirection": "vertical",
              "roundness": 0.03
            },
            "font": {
              "align": "top"
            }
          }
        }
        """
    )
    rendered_html = net.generate_html(notebook=False)
    html_path.write_text(rendered_html, encoding="utf-8")
    _decorate_html(html_path, context=context, graph=graph)


def build_control_graph_with_session(
    db: Session,
    company_id: int,
    *,
    output_path: str | Path | None = None,
    latest_output_path: str | Path | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    focus_label: str | None = None,
    focus_controller_name: str | None = None,
    focus_control_type: str | None = None,
    focus_semantic_flags: Iterable[str] | None = None,
) -> Path:
    context = _load_control_graph_context(
        db,
        company_id=company_id,
        max_depth=max_depth,
        focus_label=focus_label,
        preferred_controller_name=focus_controller_name,
        preferred_control_type=focus_control_type,
        preferred_semantic_flags=focus_semantic_flags,
    )
    graph = _build_visual_graph(context)
    company_html_path = (
        Path(output_path)
        if output_path is not None
        else _company_output_html_path(company_id, context.target_entity.entity_name)
    )
    _export_html_graph(context, graph, company_html_path)

    if latest_output_path is not None:
        latest_path = Path(latest_output_path)
        if latest_path != company_html_path:
            latest_path.parent.mkdir(parents=True, exist_ok=True)
            latest_path.write_text(
                company_html_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

    return company_html_path.resolve()


def build_control_graph(company_id: int) -> str:
    db = SessionLocal()
    try:
        output_path = build_control_graph_with_session(
            db,
            company_id,
            latest_output_path=LATEST_OUTPUT_HTML_PATH,
        )
    finally:
        db.close()
    return str(output_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an interactive control graph HTML for a company.",
    )
    parser.add_argument(
        "company_id",
        type=int,
        help="Mapped company_id in shareholder_entities.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        help="Upstream traversal depth before filling focused path edges.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    db = SessionLocal()
    try:
        print(
            build_control_graph_with_session(
                db,
                args.company_id,
                max_depth=args.max_depth,
                latest_output_path=LATEST_OUTPUT_HTML_PATH,
            )
        )
    finally:
        db.close()
