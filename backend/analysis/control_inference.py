from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from backend.models.company import Company
from backend.models.shareholder import ShareholderEntity, ShareholderStructure
from backend.shareholder_relations import infer_relation_role, infer_relation_type


ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
PROB_QUANT = Decimal("0.0001")
SUPPORTED_RELATION_TYPES = (
    "equity",
    "agreement",
    "board_control",
    "voting_right",
    "nominee",
    "vie",
)
CONFIDENCE_WEIGHT_MAP = {
    "high": Decimal("0.9"),
    "medium": Decimal("0.7"),
    "low": Decimal("0.4"),
    "unknown": Decimal("0.6"),
}
DEFAULT_PRIORITY_BY_RELATION_TYPE = {
    "equity": 50,
    "board_control": 20,
    "agreement": 30,
    "voting_right": 30,
    "vie": 25,
    "nominee": 40,
}
PROTECTIVE_RIGHTS_KEYWORDS = (
    "protective",
    "veto",
    "negative control",
    "negative covenant",
    "reserved matter",
    "consent right",
)
JOINT_CONTROL_KEYWORDS = (
    "joint control",
    "jointly",
    "unanimous",
    "consent of both",
    "consent of all",
    "all shareholders",
    "together decide",
)
STRONG_CONTROL_KEYWORDS = (
    "full control",
    "exclusive",
    "majority of directors",
    "majority board",
    "majority voting rights",
    "controlling voting rights",
    "decide relevant activities",
    "determine relevant activities",
    "right to appoint majority",
    "right to nominate majority",
    "irrevocable proxy",
    "exclusive service agreement",
)
VOTING_CONTROL_KEYWORDS = (
    "full voting control",
    "super-voting",
    "super voting",
    "founder block",
    "acting in concert",
    "concert party",
    "decisive voting power",
    "decisive vote",
    "control shareholder resolutions",
    "control of shareholder resolutions",
    "majority vote",
    "majority voting",
    "proxy over voting rights",
    "irrevocable voting proxy",
)
NOMINEE_EXPLICIT_CONTROL_KEYWORDS = (
    "beneficial owner retains control",
    "beneficial owner directs voting",
    "beneficial owner exercises control",
    "actual control remains with beneficiary",
    "held on behalf of beneficial owner",
    "ultimate beneficiary controls",
    "beneficiary directs",
)
NOMINEE_INDICATOR_KEYWORDS = (
    "beneficial owner",
    "beneficial ownership",
    "beneficiary",
    "nominee",
    "custodian",
    "custodial",
    "held on behalf",
    "held for the benefit",
)
POWER_KEYWORDS = (
    "operations",
    "finance",
    "financial policies",
    "business operations",
    "relevant activities",
    "appoint",
    "nominate",
    "board",
)
ECONOMIC_KEYWORDS = (
    "variable returns",
    "economics",
    "economic benefits",
    "equity pledge",
    "profit",
    "returns",
)
VIE_POWER_KEYWORDS = POWER_KEYWORDS + (
    "exclusive service agreement",
    "operating decisions",
    "financial policies",
    "power to direct",
    "direct relevant activities",
)
VIE_ECONOMIC_KEYWORDS = ECONOMIC_KEYWORDS + (
    "residual returns",
    "losses",
    "substantially all benefits",
    "economic exposure",
    "economic risks",
)
BOARD_TOTAL_KEYS = (
    "total_board_seats",
    "board_size",
    "total_seats",
    "board_total",
)
PCT_TEXT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")
RATIO_TEXT_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)")


@dataclass(slots=True)
class EdgeFactor:
    structure_id: int
    from_entity_id: int
    to_entity_id: int
    relation_type: str
    relation_role: str | None
    numeric_factor: Decimal
    semantic_factor: Decimal
    confidence_weight: Decimal
    priority: int
    flags: tuple[str, ...]
    evidence: dict[str, Any]


@dataclass(slots=True)
class PathState:
    entity_ids: list[int]
    edge_ids: list[int]
    numeric_prod: Decimal
    semantic_prod: Decimal
    conf_prod: Decimal
    flags: tuple[str, ...]
    edge_factors: tuple[EdgeFactor, ...] = ()


@dataclass(slots=True)
class ControllerCandidate:
    controller_entity_id: int
    total_score: Decimal
    total_confidence: Decimal
    control_level: str
    control_mode: str
    semantic_flags: tuple[str, ...]
    path_states: tuple[PathState, ...]
    top_paths: tuple[PathState, ...]
    evidence_summary: tuple[str, ...]
    is_joint_control: bool


@dataclass(slots=True)
class ControlInferenceContext:
    as_of: date
    company_map: dict[int, Company]
    entity_map: dict[int, ShareholderEntity]
    entity_by_company_id: dict[int, ShareholderEntity]
    factor_map: dict[int, EdgeFactor]
    incoming_factor_map: dict[int, list[EdgeFactor]]


@dataclass(slots=True)
class ControlInferenceResult:
    company: Company
    target_entity: ShareholderEntity
    aggregator: str
    candidates: tuple[ControllerCandidate, ...]
    actual_controller_entity_id: int | None
    actual_control_country: str
    attribution_type: str
    joint_controller_entity_ids: tuple[int, ...]


def _normalize_as_of(as_of: date | datetime | None) -> date:
    if as_of is None:
        return date.today()
    if isinstance(as_of, datetime):
        return as_of.date()
    return as_of


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _quantize_prob(value: Decimal) -> Decimal:
    return value.quantize(PROB_QUANT, rounding=ROUND_HALF_UP)


def _clamp_probability(value: Decimal) -> Decimal:
    return min(ONE, max(ZERO, _to_decimal(value)))


def _normalize_ratio_to_unit(value: Any) -> Decimal:
    ratio = _to_decimal(value)
    if ratio <= ZERO:
        return ZERO
    if ratio > ONE:
        return _clamp_probability(ratio / HUNDRED)
    return _clamp_probability(ratio)


def _deserialize_json_text(value: str | None) -> dict[str, Any]:
    if value is None or not value.strip():
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _serialize_prob(value: Decimal) -> str:
    return format(_quantize_prob(value), "f")


def unit_to_pct(value: Decimal) -> Decimal:
    return _quantize_prob(_clamp_probability(value) * HUNDRED)


def serialize_unit_score(value: Decimal) -> str:
    return _serialize_prob(_clamp_probability(value))


def serialize_pct_score(value: Decimal) -> str:
    return format(unit_to_pct(value), "f")


def _coalesce_text(*parts: Any) -> str:
    return " | ".join(str(part) for part in parts if part).lower()


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _has_truthy_metadata(metadata: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, bool):
            if value:
                return True
            continue
        if isinstance(value, (int, float, Decimal)):
            if value > 0:
                return True
            continue
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "confirmed", "identified"}:
                return True
    return False


def _try_extract_ratio_from_text(text: str) -> Decimal | None:
    ratio_match = RATIO_TEXT_PATTERN.search(text)
    if ratio_match is not None:
        numerator = Decimal(ratio_match.group(1))
        denominator = Decimal(ratio_match.group(2))
        if denominator > ZERO:
            return _clamp_probability(numerator / denominator)

    pct_match = PCT_TEXT_PATTERN.search(text)
    if pct_match is not None:
        return _clamp_probability(Decimal(pct_match.group(1)) / HUNDRED)

    return None


def _extract_board_total(
    structure: ShareholderStructure,
    metadata: dict[str, Any],
    text: str,
) -> int | None:
    for key in BOARD_TOTAL_KEYS:
        value = metadata.get(key)
        if value is None:
            continue
        try:
            candidate = int(value)
        except (TypeError, ValueError):
            continue
        if candidate > 0:
            return candidate

    ratio_match = RATIO_TEXT_PATTERN.search(text)
    if ratio_match is not None:
        numerator = int(ratio_match.group(1))
        denominator = int(ratio_match.group(2))
        if structure.board_seats is None or structure.board_seats == numerator:
            return denominator

    return None


def _summarize_text(text: str, *, limit: int = 140) -> str | None:
    compact = " ".join(text.split())
    if not compact:
        return None
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _infer_board_control_factor(
    structure: ShareholderStructure,
    metadata: dict[str, Any],
    text: str,
) -> tuple[Decimal, set[str]]:
    flags: set[str] = set()
    board_seats = structure.board_seats
    total_board_seats = _extract_board_total(structure, metadata, text)

    if board_seats is not None and total_board_seats:
        return _clamp_probability(Decimal(board_seats) / Decimal(total_board_seats)), flags

    if _contains_any(text, JOINT_CONTROL_KEYWORDS):
        flags.add("joint_control_candidate")

    flags.add("needs_review")
    if _contains_any(text, ("majority of directors", "majority board", "right to nominate majority")):
        return Decimal("0.55"), flags
    if board_seats is not None and board_seats > 0:
        conservative_ratio = Decimal(board_seats) / Decimal(max(board_seats + 3, 7))
        return _clamp_probability(min(conservative_ratio, Decimal("0.49"))), flags
    return Decimal("0.35"), flags


def _infer_agreement_factor(
    metadata: dict[str, Any],
    text: str,
) -> tuple[Decimal, set[str]]:
    flags: set[str] = set()
    factor = Decimal("0.15")

    if _contains_any(text, PROTECTIVE_RIGHTS_KEYWORDS):
        flags.add("protective_rights")
        factor = Decimal("0.05")

    if _contains_any(text, JOINT_CONTROL_KEYWORDS):
        flags.add("joint_control_candidate")
        factor = max(factor, Decimal("0.50"))

    if _contains_any(text, STRONG_CONTROL_KEYWORDS):
        factor = max(factor, ONE)
    if _contains_any(text, POWER_KEYWORDS) and _contains_any(text, ECONOMIC_KEYWORDS):
        factor = max(factor, ONE)

    voting_ratio = _normalize_ratio_to_unit(metadata.get("voting_ratio"))
    if voting_ratio > ZERO:
        factor = max(factor, voting_ratio)

    text_ratio = _try_extract_ratio_from_text(text)
    if text_ratio is not None:
        factor = max(factor, text_ratio)

    legacy_ratio_proxy = _normalize_ratio_to_unit(metadata.get("legacy_ratio_proxy"))
    if legacy_ratio_proxy > ZERO and factor < Decimal("0.20"):
        factor = max(factor, min(Decimal("0.35"), legacy_ratio_proxy * Decimal("3")))

    if factor < Decimal("0.50") and "protective_rights" not in flags:
        flags.add("needs_review")

    return _clamp_probability(factor), flags


def _infer_voting_right_factor(
    metadata: dict[str, Any],
    text: str,
) -> tuple[Decimal, set[str]]:
    flags: set[str] = set()
    factor = Decimal("0.18")
    voting_ratio = _normalize_ratio_to_unit(
        metadata.get("effective_voting_ratio") or metadata.get("voting_ratio")
    )

    if _contains_any(text, PROTECTIVE_RIGHTS_KEYWORDS):
        return Decimal("0.05"), {"protective_rights"}

    if _contains_any(text, JOINT_CONTROL_KEYWORDS):
        flags.add("joint_control_candidate")
        factor = max(factor, Decimal("0.50"))

    if voting_ratio >= Decimal("0.50"):
        factor = max(factor, voting_ratio)
    elif voting_ratio > ZERO:
        factor = max(factor, min(Decimal("0.40"), voting_ratio * Decimal("2")))

    if _contains_any(text, STRONG_CONTROL_KEYWORDS) or _contains_any(
        text,
        VOTING_CONTROL_KEYWORDS,
    ):
        factor = max(factor, Decimal("0.70"))
    if "super-voting" in text or "super voting" in text:
        boosted_factor = max(Decimal("0.65"), voting_ratio * Decimal("6"))
        factor = max(factor, _clamp_probability(boosted_factor))
    if _contains_any(text, ("full voting control", "controlling voting rights")):
        factor = max(factor, ONE)

    if factor < Decimal("0.50") and "protective_rights" not in flags:
        flags.add("needs_review")

    return _clamp_probability(factor), flags


def _infer_nominee_factor(metadata: dict[str, Any], text: str) -> tuple[Decimal, set[str]]:
    flags: set[str] = {"beneficial_owner_candidate"}
    factor = Decimal("0.25")
    disclosed = _has_truthy_metadata(
        metadata,
        "beneficial_owner_disclosed",
        "beneficial_owner_confirmed",
        "beneficiary_controls",
        "beneficial_owner_controls",
    )
    explicit_control = _contains_any(text, NOMINEE_EXPLICIT_CONTROL_KEYWORDS)
    nominee_indicator = _contains_any(text, NOMINEE_INDICATOR_KEYWORDS)

    if _contains_any(text, PROTECTIVE_RIGHTS_KEYWORDS):
        return Decimal("0.05"), {
            "beneficial_owner_candidate",
            "protective_rights",
        }

    if disclosed and explicit_control:
        factor = Decimal("0.85")
    elif disclosed:
        factor = Decimal("0.65")
    elif explicit_control:
        factor = Decimal("0.75")
    elif nominee_indicator:
        factor = Decimal("0.30")
        flags.add("needs_review")
    else:
        factor = Decimal("0.22")
        flags.add("needs_review")

    if _contains_any(text, JOINT_CONTROL_KEYWORDS):
        flags.add("joint_control_candidate")
        factor = max(factor, Decimal("0.50"))

    if factor < Decimal("0.50"):
        flags.add("needs_review")

    return _clamp_probability(factor), flags


def _infer_vie_factor(metadata: dict[str, Any], text: str) -> tuple[Decimal, set[str]]:
    flags: set[str] = set()
    has_power = _contains_any(text, VIE_POWER_KEYWORDS)
    has_economics = _contains_any(text, VIE_ECONOMIC_KEYWORDS)

    if has_power:
        flags.add("power_rights")
    if has_economics:
        flags.add("economic_benefits")

    if _contains_any(text, PROTECTIVE_RIGHTS_KEYWORDS):
        return Decimal("0.08"), {"protective_rights", "needs_review"}

    if _contains_any(text, JOINT_CONTROL_KEYWORDS):
        flags.add("joint_control_candidate")
        factor_floor = Decimal("0.50")
    else:
        factor_floor = ZERO

    if has_power and has_economics:
        factor = Decimal("0.90")
    elif has_power or has_economics:
        factor = Decimal("0.45")
        flags.add("needs_review")
    else:
        factor = max(
            Decimal("0.18"),
            min(
                Decimal("0.35"),
                _normalize_ratio_to_unit(metadata.get("legacy_ratio_proxy"))
                * Decimal("3"),
            ),
        )
        flags.add("needs_review")

    return _clamp_probability(max(factor, factor_floor)), flags


def edge_to_factor(structure: ShareholderStructure) -> EdgeFactor | None:
    relation_type = infer_relation_type(
        relation_type=structure.relation_type,
        control_type=structure.control_type,
        holding_ratio=structure.holding_ratio,
        remarks=structure.remarks,
    )
    if relation_type not in SUPPORTED_RELATION_TYPES:
        return None

    relation_role = infer_relation_role(
        relation_type=relation_type,
        relation_role=structure.relation_role,
    )
    metadata = _deserialize_json_text(structure.relation_metadata)
    evidence_text = _coalesce_text(
        structure.control_basis,
        structure.agreement_scope,
        structure.nomination_rights,
        structure.remarks,
    )
    flags = {relation_type}
    numeric_factor = ONE
    semantic_factor = ONE

    if relation_type == "equity":
        numeric_factor = _normalize_ratio_to_unit(structure.holding_ratio)
        semantic_factor = ONE
        if numeric_factor <= ZERO:
            return None
    elif relation_type == "board_control":
        semantic_factor, extra_flags = _infer_board_control_factor(
            structure,
            metadata,
            evidence_text,
        )
        flags.update(extra_flags)
    elif relation_type == "agreement":
        semantic_factor, extra_flags = _infer_agreement_factor(
            metadata,
            evidence_text,
        )
        flags.update(extra_flags)
    elif relation_type == "voting_right":
        semantic_factor, extra_flags = _infer_voting_right_factor(
            metadata,
            evidence_text,
        )
        flags.update(extra_flags)
    elif relation_type == "nominee":
        semantic_factor, extra_flags = _infer_nominee_factor(metadata, evidence_text)
        flags.update(extra_flags)
    elif relation_type == "vie":
        semantic_factor, extra_flags = _infer_vie_factor(metadata, evidence_text)
        flags.update(extra_flags)

    confidence_weight = CONFIDENCE_WEIGHT_MAP.get(
        (structure.confidence_level or "unknown").lower(),
        Decimal("0.6"),
    )
    priority = structure.relation_priority or DEFAULT_PRIORITY_BY_RELATION_TYPE[relation_type]

    evidence = {
        "structure_id": structure.id,
        "relation_type": relation_type,
        "relation_role": relation_role,
        "holding_ratio_raw": (
            format(_to_decimal(structure.holding_ratio), "f")
            if structure.holding_ratio is not None
            else None
        ),
        "agreement_scope": structure.agreement_scope,
        "control_basis": structure.control_basis,
        "board_seats": structure.board_seats,
        "nomination_rights": structure.nomination_rights,
        "confidence_level": structure.confidence_level,
        "relation_priority": structure.relation_priority,
        "relation_metadata": metadata,
        "remarks": structure.remarks,
        "evidence_summary": _summarize_text(evidence_text),
    }

    return EdgeFactor(
        structure_id=structure.id,
        from_entity_id=structure.from_entity_id,
        to_entity_id=structure.to_entity_id,
        relation_type=relation_type,
        relation_role=relation_role,
        numeric_factor=_clamp_probability(numeric_factor),
        semantic_factor=_clamp_probability(semantic_factor),
        confidence_weight=_clamp_probability(confidence_weight),
        priority=priority,
        flags=tuple(sorted(flags)),
        evidence=evidence,
    )


def _load_company_map(db: Session) -> dict[int, Company]:
    companies = db.query(Company).order_by(Company.id.asc()).all()
    return {company.id: company for company in companies}


def _load_entity_map(db: Session) -> dict[int, ShareholderEntity]:
    entities = (
        db.query(ShareholderEntity)
        .options(joinedload(ShareholderEntity.company))
        .order_by(ShareholderEntity.id.asc())
        .all()
    )
    return {entity.id: entity for entity in entities}


def _build_entity_by_company_id(
    entity_map: dict[int, ShareholderEntity],
) -> dict[int, ShareholderEntity]:
    entity_by_company_id: dict[int, ShareholderEntity] = {}
    for entity_id in sorted(entity_map):
        entity = entity_map[entity_id]
        if entity.company_id is None:
            continue
        entity_by_company_id.setdefault(entity.company_id, entity)
    return entity_by_company_id


def build_control_context(
    db: Session,
    as_of: date | datetime | None = None,
) -> ControlInferenceContext:
    as_of_date = _normalize_as_of(as_of)
    company_map = _load_company_map(db)
    entity_map = _load_entity_map(db)
    edge_rows = db.execute(
        text(
            """
            SELECT
                id,
                from_entity_id,
                to_entity_id,
                holding_ratio,
                is_direct,
                control_type,
                relation_type,
                has_numeric_ratio,
                relation_role,
                control_basis,
                board_seats,
                nomination_rights,
                agreement_scope,
                relation_metadata,
                relation_priority,
                confidence_level,
                reporting_period,
                effective_date,
                expiry_date,
                is_current,
                source,
                remarks
            FROM shareholder_structures
            WHERE is_current = 1
              AND is_direct = 1
              AND (effective_date IS NULL OR date(effective_date) <= :as_of_date)
              AND (expiry_date IS NULL OR date(expiry_date) >= :as_of_date)
            ORDER BY id ASC
            """
        ),
        {"as_of_date": as_of_date.isoformat()},
    ).mappings()

    factor_map: dict[int, EdgeFactor] = {}
    incoming_factor_map: dict[int, list[EdgeFactor]] = defaultdict(list)
    for edge_row in edge_rows:
        edge = SimpleNamespace(**dict(edge_row))
        factor = edge_to_factor(edge)
        if factor is None:
            continue
        factor_map[factor.structure_id] = factor
        incoming_factor_map[factor.to_entity_id].append(factor)

    for to_entity_id, incoming_factors in incoming_factor_map.items():
        incoming_factor_map[to_entity_id] = sorted(
            incoming_factors,
            key=lambda item: (
                item.priority,
                -(item.semantic_factor * item.numeric_factor),
                item.structure_id,
            ),
        )

    return ControlInferenceContext(
        as_of=as_of_date,
        company_map=company_map,
        entity_map=entity_map,
        entity_by_company_id=_build_entity_by_company_id(entity_map),
        factor_map=factor_map,
        incoming_factor_map=incoming_factor_map,
    )


def collect_control_paths(
    context: ControlInferenceContext,
    target_entity_id: int,
    *,
    max_depth: int = 10,
    min_path_score: Decimal = Decimal("0.0001"),
) -> dict[int, list[PathState]]:
    if max_depth < 1:
        raise ValueError("max_depth must be at least 1.")
    if min_path_score < ZERO:
        raise ValueError("min_path_score must be non-negative.")

    collected: dict[int, list[PathState]] = defaultdict(list)
    initial_state = PathState(
        entity_ids=[target_entity_id],
        edge_ids=[],
        numeric_prod=ONE,
        semantic_prod=ONE,
        conf_prod=ONE,
        flags=tuple(),
        edge_factors=tuple(),
    )

    def dfs(
        current_entity_id: int,
        state: PathState,
        visited_entity_ids: set[int],
    ) -> None:
        if len(state.edge_ids) >= max_depth:
            return

        for factor in context.incoming_factor_map.get(current_entity_id, []):
            upstream_entity_id = factor.from_entity_id
            if upstream_entity_id in visited_entity_ids:
                continue

            next_state = PathState(
                entity_ids=[upstream_entity_id, *state.entity_ids],
                edge_ids=[factor.structure_id, *state.edge_ids],
                numeric_prod=_clamp_probability(state.numeric_prod * factor.numeric_factor),
                semantic_prod=_clamp_probability(state.semantic_prod * factor.semantic_factor),
                conf_prod=_clamp_probability(state.conf_prod * factor.confidence_weight),
                flags=tuple(sorted({*state.flags, *factor.flags})),
                edge_factors=(factor, *state.edge_factors),
            )
            path_score = _clamp_probability(next_state.numeric_prod * next_state.semantic_prod)
            if path_score < min_path_score:
                continue

            collected[upstream_entity_id].append(next_state)
            dfs(
                upstream_entity_id,
                next_state,
                visited_entity_ids | {upstream_entity_id},
            )

    dfs(target_entity_id, initial_state, {target_entity_id})
    return collected


def aggregate_scores_sum_cap(scores: list[Decimal]) -> Decimal:
    return _clamp_probability(sum((_to_decimal(score) for score in scores), ZERO))


def aggregate_scores_noisy_or(scores: list[Decimal]) -> Decimal:
    remaining = ONE
    for score in scores:
        remaining *= ONE - _clamp_probability(score)
    return _clamp_probability(ONE - remaining)


def _resolve_aggregator(
    aggregator: str,
) -> Callable[[list[Decimal]], Decimal]:
    if aggregator == "sum_cap":
        return aggregate_scores_sum_cap
    if aggregator == "noisy_or":
        return aggregate_scores_noisy_or
    raise ValueError(f"Unsupported aggregator: {aggregator}")


def _path_score(path_state: PathState) -> Decimal:
    return _clamp_probability(path_state.numeric_prod * path_state.semantic_prod)


def _path_mode(path_state: PathState) -> str:
    relation_types = {
        flag for flag in path_state.flags if flag in SUPPORTED_RELATION_TYPES
    }
    has_equity = "equity" in relation_types
    has_semantic = bool(relation_types - {"equity"})
    if has_equity and has_semantic:
        return "mixed"
    if has_semantic:
        return "semantic"
    return "numeric"


def _candidate_control_mode(path_states: list[PathState]) -> str:
    modes = {_path_mode(path_state) for path_state in path_states}
    if "mixed" in modes or modes == {"numeric", "semantic"}:
        return "mixed"
    if "semantic" in modes:
        return "semantic"
    return "numeric"


def _candidate_flags(path_states: list[PathState]) -> tuple[str, ...]:
    flags: set[str] = set()
    for path_state in path_states:
        flags.update(path_state.flags)
    return tuple(sorted(flags))


def _candidate_confidence(path_states: list[PathState]) -> Decimal:
    total_score = ZERO
    weighted_confidence = ZERO
    for path_state in path_states:
        score = _path_score(path_state)
        total_score += score
        weighted_confidence += score * path_state.conf_prod
    if total_score <= ZERO:
        return ZERO
    return _clamp_probability(weighted_confidence / total_score)


def _candidate_evidence_summary(path_states: list[PathState]) -> tuple[str, ...]:
    summaries: list[str] = []
    seen: set[str] = set()
    for path_state in sorted(path_states, key=_path_score, reverse=True):
        for factor in path_state.edge_factors:
            summary = factor.evidence.get("evidence_summary")
            if not summary or summary in seen:
                continue
            seen.add(summary)
            summaries.append(summary)
            if len(summaries) >= 6:
                return tuple(summaries)
    return tuple(summaries)


def _classify_control_level(
    *,
    total_score: Decimal,
    semantic_flags: tuple[str, ...],
    control_threshold: Decimal,
    significant_threshold: Decimal,
) -> str:
    if "joint_control_candidate" in semantic_flags and total_score >= significant_threshold:
        return "joint_control"
    if total_score >= control_threshold:
        return "control"
    if total_score >= significant_threshold:
        return "significant_influence"
    return "weak_link"


def _resolve_company_and_target_entity(
    context: ControlInferenceContext,
    company_id: int,
) -> tuple[Company, ShareholderEntity]:
    company = context.company_map.get(company_id)
    target_entity = context.entity_by_company_id.get(company_id)
    if company is None:
        raise ValueError("Company not found.")
    if target_entity is None:
        raise ValueError("Mapped shareholder entity not found for company.")
    return company, target_entity


def _resolve_controller_country(controller_entity: ShareholderEntity | None) -> str | None:
    if controller_entity is None:
        return None
    if controller_entity.country:
        return controller_entity.country
    if controller_entity.company is not None:
        return controller_entity.company.incorporation_country
    return None


def _resolve_country_attribution_type(candidate: ControllerCandidate) -> str:
    flags = set(candidate.semantic_flags)
    if candidate.is_joint_control:
        return "joint_control"
    if candidate.control_mode == "numeric":
        return "equity_control"
    if candidate.control_mode == "mixed":
        return "mixed_control"
    if "board_control" in flags:
        return "board_control"
    return "agreement_control"


def infer_controllers(
    context: ControlInferenceContext,
    company_id: int,
    *,
    max_depth: int = 10,
    min_path_score: Decimal = Decimal("0.0001"),
    control_threshold: Decimal = Decimal("0.5"),
    significant_threshold: Decimal = Decimal("0.2"),
    disclosure_threshold: Decimal = Decimal("0.25"),
    aggregator: str = "sum_cap",
    top_path_limit: int = 5,
) -> ControlInferenceResult:
    company, target_entity = _resolve_company_and_target_entity(context, company_id)
    aggregate = _resolve_aggregator(aggregator)
    paths_by_entity_id = collect_control_paths(
        context,
        target_entity.id,
        max_depth=max_depth,
        min_path_score=min_path_score,
    )

    candidates: list[ControllerCandidate] = []
    for entity_id, path_states in paths_by_entity_id.items():
        path_scores = [_path_score(path_state) for path_state in path_states]
        total_score = aggregate(path_scores)
        if total_score < disclosure_threshold:
            continue

        semantic_flags = _candidate_flags(path_states)
        control_mode = _candidate_control_mode(path_states)
        control_level = _classify_control_level(
            total_score=total_score,
            semantic_flags=semantic_flags,
            control_threshold=control_threshold,
            significant_threshold=significant_threshold,
        )
        sorted_paths = sorted(
            path_states,
            key=lambda item: (_path_score(item), item.conf_prod, -len(item.edge_ids)),
            reverse=True,
        )
        candidates.append(
            ControllerCandidate(
                controller_entity_id=entity_id,
                total_score=total_score,
                total_confidence=_candidate_confidence(path_states),
                control_level=control_level,
                control_mode=control_mode,
                semantic_flags=semantic_flags,
                path_states=tuple(sorted_paths),
                top_paths=tuple(sorted_paths[:top_path_limit]),
                evidence_summary=_candidate_evidence_summary(sorted_paths),
                is_joint_control=control_level == "joint_control",
            )
        )

    candidates.sort(
        key=lambda item: (
            item.control_level != "control",
            item.control_level != "joint_control",
            -item.total_score,
            -item.total_confidence,
            item.controller_entity_id,
        )
    )

    control_candidates = [
        candidate
        for candidate in candidates
        if candidate.control_level in {"control", "joint_control"}
    ]
    joint_candidates = [
        candidate.controller_entity_id
        for candidate in control_candidates
        if candidate.is_joint_control
    ]

    actual_controller_entity_id: int | None = None
    actual_control_country = company.incorporation_country
    attribution_type = "fallback_incorporation"

    if joint_candidates:
        actual_control_country = "undetermined"
        attribution_type = "joint_control"
    elif control_candidates:
        winner = control_candidates[0]
        actual_controller_entity_id = winner.controller_entity_id
        controller_entity = context.entity_map.get(winner.controller_entity_id)
        actual_control_country = (
            _resolve_controller_country(controller_entity)
            or company.incorporation_country
        )
        attribution_type = _resolve_country_attribution_type(winner)

    return ControlInferenceResult(
        company=company,
        target_entity=target_entity,
        aggregator=aggregator,
        candidates=tuple(candidates),
        actual_controller_entity_id=actual_controller_entity_id,
        actual_control_country=actual_control_country,
        attribution_type=attribution_type,
        joint_controller_entity_ids=tuple(sorted(joint_candidates)),
    )
