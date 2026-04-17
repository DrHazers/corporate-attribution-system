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
DEFAULT_MAX_DEPTH = 10
DEFAULT_MIN_PATH_SCORE = Decimal("0.0001")
DEFAULT_CONTROL_THRESHOLD = Decimal("0.5")
DEFAULT_SIGNIFICANT_THRESHOLD = Decimal("0.2")
DEFAULT_DISCLOSURE_THRESHOLD = DEFAULT_SIGNIFICANT_THRESHOLD
DEFAULT_RELATIVE_CONTROL_CANDIDATE_THRESHOLD = Decimal("0.35")
DEFAULT_RELATIVE_CONTROL_GAP_THRESHOLD = Decimal("0.08")
DEFAULT_RELATIVE_CONTROL_RATIO_THRESHOLD = Decimal("1.2")
DEFAULT_CLOSE_COMPETITION_GAP_THRESHOLD = Decimal("0.05")
DEFAULT_CLOSE_COMPETITION_RATIO_THRESHOLD = Decimal("1.1")
DEFAULT_AGGREGATOR = "sum_cap"
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

CONTROLLER_STATUS_ACTUAL = "actual_controller_identified"
CONTROLLER_STATUS_LEADING = "no_actual_controller_but_leading_candidate_found"
CONTROLLER_STATUS_NONE = "no_meaningful_controller_signal"
CONTROLLER_STATUS_JOINT = "joint_control_identified"


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
    look_through_allowed: bool
    termination_signal: str | None
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
    min_depth: int


@dataclass(slots=True)
class InferenceAuditEvent:
    action_type: str
    action_reason: str | None
    from_entity_id: int | None
    to_entity_id: int | None
    score_before: Decimal | None
    score_after: Decimal | None
    details: dict[str, Any]


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
    direct_controller_entity_id: int | None
    direct_controller_country: str | None
    actual_controller_entity_id: int | None
    leading_candidate_entity_id: int | None
    leading_candidate_classification: str | None
    actual_control_country: str
    attribution_type: str
    attribution_layer: str
    country_inference_reason: str
    controller_status: str
    joint_controller_entity_ids: tuple[int, ...]
    look_through_applied: bool
    promotion_path_entity_ids: tuple[int, ...]
    promotion_source_by_entity_id: dict[int, int]
    promotion_reason_by_entity_id: dict[int, str]
    terminal_score_by_entity_id: dict[int, Decimal]
    terminal_failure_reason: str | None
    audit_events: tuple[InferenceAuditEvent, ...]


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
    if structure.voting_ratio is not None and metadata.get("voting_ratio") is None:
        metadata["voting_ratio"] = format(_to_decimal(structure.voting_ratio), "f")
    if (
        structure.effective_control_ratio is not None
        and metadata.get("effective_control_ratio") is None
    ):
        metadata["effective_control_ratio"] = format(
            _to_decimal(structure.effective_control_ratio),
            "f",
        )
    if structure.economic_ratio is not None and metadata.get("economic_ratio") is None:
        metadata["economic_ratio"] = format(_to_decimal(structure.economic_ratio), "f")
    if metadata.get("beneficial_owner_disclosed") is None:
        metadata["beneficial_owner_disclosed"] = bool(
            structure.is_beneficial_control
        )
    evidence_text = _coalesce_text(
        structure.control_basis,
        structure.agreement_scope,
        structure.nomination_rights,
        structure.remarks,
    )
    flags = {relation_type}
    numeric_factor = ONE
    semantic_factor = ONE
    look_through_allowed = bool(
        True if structure.look_through_allowed is None else structure.look_through_allowed
    )
    termination_signal = (
        str(structure.termination_signal).strip().lower()
        if structure.termination_signal is not None
        and str(structure.termination_signal).strip()
        else "none"
    )

    if relation_type == "equity":
        numeric_factor = _normalize_ratio_to_unit(
            structure.effective_control_ratio
            if structure.effective_control_ratio is not None
            else structure.holding_ratio
        )
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
        "voting_ratio_raw": (
            format(_to_decimal(structure.voting_ratio), "f")
            if structure.voting_ratio is not None
            else None
        ),
        "economic_ratio_raw": (
            format(_to_decimal(structure.economic_ratio), "f")
            if structure.economic_ratio is not None
            else None
        ),
        "effective_control_ratio_raw": (
            format(_to_decimal(structure.effective_control_ratio), "f")
            if structure.effective_control_ratio is not None
            else None
        ),
        "is_beneficial_control": bool(structure.is_beneficial_control),
        "look_through_allowed": look_through_allowed,
        "termination_signal": termination_signal,
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
        look_through_allowed=look_through_allowed,
        termination_signal=termination_signal,
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
            voting_ratio,
            economic_ratio,
            is_beneficial_control,
            look_through_allowed,
            termination_signal,
            effective_control_ratio,
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


def _candidate_min_depth(path_states: list[PathState]) -> int:
    if not path_states:
        return 0
    return min(len(path_state.edge_ids) for path_state in path_states)


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


def _controller_sort_key(item: ControllerCandidate) -> tuple[Any, ...]:
    return (
        item.control_level != "control",
        item.control_level != "joint_control",
        -item.total_score,
        -item.total_confidence,
        item.controller_entity_id,
    )


def _direct_candidate_sort_key(item: ControllerCandidate) -> tuple[Any, ...]:
    return (
        item.min_depth != 1,
        item.control_level != "control",
        item.control_level != "joint_control",
        -item.total_score,
        -item.total_confidence,
        item.controller_entity_id,
    )


def _build_candidates_for_target_entity(
    context: ControlInferenceContext,
    target_entity_id: int,
    *,
    max_depth: int,
    min_path_score: Decimal,
    control_threshold: Decimal,
    significant_threshold: Decimal,
    disclosure_threshold: Decimal,
    aggregator: str,
    top_path_limit: int,
) -> list[ControllerCandidate]:
    aggregate = _resolve_aggregator(aggregator)
    paths_by_entity_id = collect_control_paths(
        context,
        target_entity_id,
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
                min_depth=_candidate_min_depth(sorted_paths),
            )
        )

    candidates.sort(key=_controller_sort_key)
    return candidates


def _candidate_immediate_edge(candidate: ControllerCandidate) -> EdgeFactor | None:
    if not candidate.top_paths:
        return None
    if not candidate.top_paths[0].edge_factors:
        return None
    return candidate.top_paths[0].edge_factors[0]


def _is_close_competition(
    leading_candidate: ControllerCandidate,
    runner_up_candidate: ControllerCandidate | None,
) -> bool:
    if runner_up_candidate is None:
        return False
    lead_gap = leading_candidate.total_score - runner_up_candidate.total_score
    lead_ratio = _score_gap_ratio(
        leading_candidate.total_score,
        runner_up_candidate.total_score,
    )
    return (
        runner_up_candidate.total_score > ZERO
        and lead_gap <= DEFAULT_CLOSE_COMPETITION_GAP_THRESHOLD
        and lead_ratio is not None
        and lead_ratio <= DEFAULT_CLOSE_COMPETITION_RATIO_THRESHOLD
    )


def _entity_prefers_terminal_stop(entity: ShareholderEntity | None) -> bool:
    if entity is None:
        return False
    if bool(getattr(entity, "ultimate_owner_hint", False)):
        return True
    controller_class = (getattr(entity, "controller_class", None) or "").strip().lower()
    if controller_class in {"natural_person", "state"}:
        return True
    if entity.entity_type in {"person", "government"}:
        return True
    if (getattr(entity, "entity_subtype", None) or "").strip().lower() in {
        "government_agency",
        "family_vehicle",
        "founder_vehicle",
    }:
        return True
    return False


def _edge_relation_metadata(edge: EdgeFactor | None) -> dict[str, Any]:
    if edge is None:
        return {}
    metadata = edge.evidence.get("relation_metadata")
    return metadata if isinstance(metadata, dict) else {}


def _joint_control_entity_ids(
    candidates: list[ControllerCandidate],
    *,
    control_threshold: Decimal,
) -> tuple[int, ...]:
    explicit_joint_ids = sorted(
        candidate.controller_entity_id
        for candidate in candidates
        if candidate.is_joint_control
    )
    if explicit_joint_ids:
        return tuple(explicit_joint_ids)

    control_candidates = sorted(
        [
            candidate
            for candidate in candidates
            if candidate.control_level == "control"
            and candidate.total_score >= control_threshold
        ],
        key=_controller_sort_key,
    )
    if len(control_candidates) < 2:
        return tuple()

    leader = control_candidates[0]
    tied_control_ids = sorted(
        candidate.controller_entity_id
        for candidate in control_candidates
        if abs(candidate.total_score - leader.total_score) <= PROB_QUANT
    )
    if len(tied_control_ids) >= 2:
        return tuple(tied_control_ids)
    return tuple()


def _promotion_block_reason(
    edge: EdgeFactor | None,
    *,
    parent_entity: ShareholderEntity | None = None,
) -> str | None:
    if edge is None:
        return None
    termination_signal = (edge.termination_signal or "none").strip().lower()
    if termination_signal and termination_signal != "none":
        return termination_signal
    metadata = _edge_relation_metadata(edge)
    if _has_truthy_metadata(
        metadata,
        "beneficial_owner_unknown",
        "beneficial_owner_undisclosed",
        "beneficial_owner_not_disclosed",
        "ultimate_owner_unknown",
    ):
        return "beneficial_owner_unknown"
    if edge.relation_type == "nominee":
        disclosed = bool(edge.evidence.get("is_beneficial_control")) or bool(
            getattr(parent_entity, "beneficial_owner_disclosed", False)
        ) or _has_truthy_metadata(
            metadata,
            "beneficial_owner_disclosed",
            "beneficial_owner_confirmed",
            "beneficiary_controls",
            "beneficial_owner_controls",
        )
        if not disclosed:
            return "nominee_without_disclosure"
    if not edge.look_through_allowed:
        return "look_through_not_allowed"
    return None


def _promotion_reason_for_entity(
    current_entity: ShareholderEntity | None,
    parent_entity: ShareholderEntity | None,
) -> str:
    if parent_entity is not None and bool(getattr(parent_entity, "ultimate_owner_hint", False)):
        return "beneficial_owner_priority"
    if parent_entity is not None and bool(
        getattr(parent_entity, "beneficial_owner_disclosed", False)
    ):
        return "disclosed_ultimate_parent"
    entity_subtype = (getattr(current_entity, "entity_subtype", None) or "").strip().lower()
    if entity_subtype in {"holding_company", "spv", "shell_company", "state_owned_vehicle"}:
        return "look_through_holding_vehicle"
    if current_entity is not None and bool(getattr(current_entity, "beneficial_owner_disclosed", False)):
        return "disclosed_ultimate_parent"
    return "controls_direct_controller"


def _override_leading_candidate_from_subset(
    candidates: list[ControllerCandidate],
    *,
    significant_threshold: Decimal,
) -> tuple[int | None, str | None]:
    if not candidates:
        return None, None
    sorted_candidates = sorted(candidates, key=_controller_sort_key)
    return (
        sorted_candidates[0].controller_entity_id,
        _classify_leading_candidate_signal(
            sorted_candidates,
            significant_threshold=significant_threshold,
        ),
    )


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


def _score_gap_ratio(
    leading_score: Decimal,
    trailing_score: Decimal,
) -> Decimal | None:
    if trailing_score <= ZERO:
        return None
    return leading_score / trailing_score


def _classify_leading_candidate_signal(
    candidates: list[ControllerCandidate],
    *,
    significant_threshold: Decimal,
) -> str | None:
    if not candidates:
        return None

    leading_candidate = candidates[0]
    if leading_candidate.control_level == "control":
        return "absolute_control"
    if leading_candidate.control_level == "joint_control":
        return "joint_control"
    if leading_candidate.total_score < significant_threshold:
        return None

    runner_up_score = candidates[1].total_score if len(candidates) > 1 else ZERO
    lead_gap = leading_candidate.total_score - runner_up_score
    lead_ratio = _score_gap_ratio(leading_candidate.total_score, runner_up_score)

    if (
        leading_candidate.total_score >= DEFAULT_RELATIVE_CONTROL_CANDIDATE_THRESHOLD
        and lead_gap >= DEFAULT_RELATIVE_CONTROL_GAP_THRESHOLD
        and (
            lead_ratio is None
            or lead_ratio >= DEFAULT_RELATIVE_CONTROL_RATIO_THRESHOLD
        )
    ):
        return "relative_control_candidate"

    if (
        runner_up_score > ZERO
        and lead_gap <= DEFAULT_CLOSE_COMPETITION_GAP_THRESHOLD
        and lead_ratio is not None
        and lead_ratio <= DEFAULT_CLOSE_COMPETITION_RATIO_THRESHOLD
    ):
        return "significant_influence_close_competition"

    return "significant_influence_candidate"


def _resolve_controller_status(
    *,
    actual_controller_entity_id: int | None,
    joint_controller_entity_ids: tuple[int, ...],
    leading_candidate_entity_id: int | None,
) -> str:
    if actual_controller_entity_id is not None:
        return CONTROLLER_STATUS_ACTUAL
    if joint_controller_entity_ids:
        return CONTROLLER_STATUS_JOINT
    if leading_candidate_entity_id is not None:
        return CONTROLLER_STATUS_LEADING
    return CONTROLLER_STATUS_NONE


def infer_controllers(
    context: ControlInferenceContext,
    company_id: int,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    min_path_score: Decimal = DEFAULT_MIN_PATH_SCORE,
    control_threshold: Decimal = DEFAULT_CONTROL_THRESHOLD,
    significant_threshold: Decimal = DEFAULT_SIGNIFICANT_THRESHOLD,
    disclosure_threshold: Decimal = DEFAULT_DISCLOSURE_THRESHOLD,
    aggregator: str = DEFAULT_AGGREGATOR,
    top_path_limit: int = 5,
) -> ControlInferenceResult:
    company, target_entity = _resolve_company_and_target_entity(context, company_id)
    candidates = _build_candidates_for_target_entity(
        context,
        target_entity.id,
        max_depth=max_depth,
        min_path_score=min_path_score,
        control_threshold=control_threshold,
        significant_threshold=significant_threshold,
        disclosure_threshold=disclosure_threshold,
        aggregator=aggregator,
        top_path_limit=top_path_limit,
    )
    company_candidate_map = {
        candidate.controller_entity_id: candidate for candidate in candidates
    }

    leading_candidate_entity_id = candidates[0].controller_entity_id if candidates else None
    leading_candidate_classification = (
        _classify_leading_candidate_signal(
            candidates,
            significant_threshold=significant_threshold,
        )
        if candidates
        else None
    )

    direct_candidates = sorted(
        [candidate for candidate in candidates if candidate.min_depth == 1],
        key=_direct_candidate_sort_key,
    )
    direct_candidate = direct_candidates[0] if direct_candidates else None
    direct_joint_controller_entity_ids = _joint_control_entity_ids(
        direct_candidates,
        control_threshold=control_threshold,
    )
    direct_candidate_block_reason = (
        _promotion_block_reason(
            _candidate_immediate_edge(direct_candidate),
            parent_entity=(
                context.entity_map.get(direct_candidate.controller_entity_id)
                if direct_candidate is not None
                else None
            ),
        )
        if direct_candidate is not None
        else None
    )
    direct_controller_entity_id = (
        direct_candidate.controller_entity_id
        if (
            direct_candidate is not None
            and direct_candidate.control_level == "control"
            and not direct_joint_controller_entity_ids
            and direct_candidate_block_reason
            not in {"beneficial_owner_unknown", "nominee_without_disclosure"}
        )
        else None
    )
    direct_controller_country = (
        _resolve_controller_country(
            context.entity_map.get(direct_controller_entity_id)
        )
        if direct_controller_entity_id is not None
        else None
    )

    actual_controller_entity_id: int | None = None
    actual_control_country = company.incorporation_country
    attribution_type = "fallback_incorporation"
    attribution_layer = "fallback_incorporation"
    country_inference_reason = "fallback_to_incorporation"
    joint_controller_entity_ids: tuple[int, ...] = tuple()
    look_through_applied = False
    promotion_path_entity_ids: list[int] = []
    promotion_source_by_entity_id: dict[int, int] = {}
    promotion_reason_by_entity_id: dict[int, str] = {}
    terminal_score_by_entity_id: dict[int, Decimal] = {}
    terminal_failure_reason: str | None = None
    audit_events: list[InferenceAuditEvent] = []
    leading_override_entity_id: int | None = None
    leading_override_classification: str | None = None

    if direct_candidate is not None:
        audit_events.append(
            InferenceAuditEvent(
                action_type="candidate_selected",
                action_reason=(
                    "direct_controller_candidate"
                    if direct_controller_entity_id is not None
                    else "leading_direct_candidate"
                ),
                from_entity_id=direct_candidate.controller_entity_id,
                to_entity_id=target_entity.id,
                score_before=direct_candidate.total_score,
                score_after=direct_candidate.total_score,
                details={
                    "company_candidate_score": serialize_unit_score(
                        direct_candidate.total_score
                    ),
                    "control_level": direct_candidate.control_level,
                    "min_depth": direct_candidate.min_depth,
                    "is_structural_joint_control": bool(
                        direct_joint_controller_entity_ids
                    ),
                    "direct_block_reason": direct_candidate_block_reason,
                },
            )
        )

    if direct_candidate is None:
        pass
    elif direct_joint_controller_entity_ids:
        joint_controller_entity_ids = direct_joint_controller_entity_ids
        terminal_failure_reason = "joint_control"
        actual_control_country = "undetermined"
        attribution_type = "joint_control"
        attribution_layer = "joint_control_undetermined"
        country_inference_reason = "joint_control_no_single_country"
        leading_override_entity_id = joint_controller_entity_ids[0]
        leading_override_classification = "joint_control"
        audit_events.append(
            InferenceAuditEvent(
                action_type="joint_control_detected",
                action_reason="direct_layer_joint_control",
                from_entity_id=joint_controller_entity_ids[0],
                to_entity_id=target_entity.id,
                score_before=direct_candidate.total_score,
                score_after=None,
                details={
                    "joint_controller_entity_ids": list(joint_controller_entity_ids)
                },
            )
        )
    elif direct_candidate_block_reason in {
        "beneficial_owner_unknown",
        "nominee_without_disclosure",
    }:
        terminal_failure_reason = direct_candidate_block_reason
        leading_override_entity_id = direct_candidate.controller_entity_id
        leading_override_classification = "absolute_control"
        audit_events.append(
            InferenceAuditEvent(
                action_type="promotion_blocked",
                action_reason=direct_candidate_block_reason,
                from_entity_id=direct_candidate.controller_entity_id,
                to_entity_id=target_entity.id,
                score_before=direct_candidate.total_score,
                score_after=None,
                details={"stage": "direct_layer"},
            )
        )
    else:
        if direct_controller_entity_id is not None:
            promotion_path_entity_ids.append(direct_candidate.controller_entity_id)
            terminal_score_by_entity_id[direct_candidate.controller_entity_id] = (
                direct_candidate.total_score
            )
        current_company_candidate = direct_candidate
        current_entity_id = direct_candidate.controller_entity_id
        visited_entity_ids = {current_entity_id}

        while True:
            current_entity = context.entity_map.get(current_entity_id)
            if _entity_prefers_terminal_stop(current_entity):
                if current_company_candidate.control_level == "control":
                    actual_controller_entity_id = current_entity_id
                    audit_events.append(
                        InferenceAuditEvent(
                            action_type="terminal_confirmed",
                            action_reason="terminal_entity_preferred",
                            from_entity_id=current_entity_id,
                            to_entity_id=target_entity.id,
                            score_before=current_company_candidate.total_score,
                            score_after=terminal_score_by_entity_id.get(current_entity_id),
                            details={},
                        )
                    )
                else:
                    terminal_failure_reason = "insufficient_evidence"
                    audit_events.append(
                        InferenceAuditEvent(
                            action_type="promotion_blocked",
                            action_reason="insufficient_evidence",
                            from_entity_id=current_entity_id,
                            to_entity_id=target_entity.id,
                            score_before=current_company_candidate.total_score,
                            score_after=None,
                            details={"stage": "terminal_entity_preferred"},
                        )
                    )
                break

            parent_candidates = [
                candidate
                for candidate in _build_candidates_for_target_entity(
                    context,
                    current_entity_id,
                    max_depth=max_depth,
                    min_path_score=min_path_score,
                    control_threshold=control_threshold,
                    significant_threshold=significant_threshold,
                    disclosure_threshold=disclosure_threshold,
                    aggregator=aggregator,
                    top_path_limit=top_path_limit,
                )
                if candidate.min_depth == 1
            ]

            parent_joint_controller_entity_ids = _joint_control_entity_ids(
                parent_candidates,
                control_threshold=control_threshold,
            )

            if parent_joint_controller_entity_ids:
                joint_controller_entity_ids = parent_joint_controller_entity_ids
                terminal_failure_reason = "joint_control"
                leading_override_entity_id = joint_controller_entity_ids[0]
                leading_override_classification = "joint_control"
                actual_control_country = "undetermined"
                attribution_type = "joint_control"
                attribution_layer = "joint_control_undetermined"
                country_inference_reason = "joint_control_no_single_country"
                audit_events.append(
                    InferenceAuditEvent(
                        action_type="joint_control_detected",
                        action_reason="promotion_blocked_by_joint_control",
                        from_entity_id=current_entity_id,
                        to_entity_id=target_entity.id,
                        score_before=current_company_candidate.total_score,
                        score_after=None,
                        details={
                            "joint_controller_entity_ids": list(
                                joint_controller_entity_ids
                            )
                        },
                    )
                )
                break

            parent_control_candidates = sorted(
                [
                    candidate
                    for candidate in parent_candidates
                    if candidate.control_level == "control"
                ],
                key=_controller_sort_key,
            )

            if not parent_control_candidates:
                stop_reason = (
                    "upstream_significant_influence_only"
                    if parent_candidates
                    else "no_parent_control_above_threshold"
                )
                if current_company_candidate.control_level == "control":
                    actual_controller_entity_id = current_entity_id
                    audit_events.append(
                        InferenceAuditEvent(
                            action_type="terminal_confirmed",
                            action_reason=stop_reason,
                            from_entity_id=current_entity_id,
                            to_entity_id=target_entity.id,
                            score_before=current_company_candidate.total_score,
                            score_after=terminal_score_by_entity_id.get(current_entity_id),
                            details={},
                        )
                    )
                else:
                    terminal_failure_reason = "insufficient_evidence"
                    audit_events.append(
                        InferenceAuditEvent(
                            action_type="promotion_blocked",
                            action_reason=stop_reason,
                            from_entity_id=current_entity_id,
                            to_entity_id=target_entity.id,
                            score_before=current_company_candidate.total_score,
                            score_after=None,
                            details={},
                        )
                    )
                break

            winner = parent_control_candidates[0]
            runner_up = (
                parent_control_candidates[1]
                if len(parent_control_candidates) > 1
                else None
            )
            winner_company_candidate = company_candidate_map.get(
                winner.controller_entity_id
            )

            if _is_close_competition(winner, runner_up):
                terminal_failure_reason = "close_competition"
                relevant_candidates = [
                    company_candidate_map[candidate.controller_entity_id]
                    for candidate in parent_control_candidates[:2]
                    if candidate.controller_entity_id in company_candidate_map
                ]
                leading_override_entity_id, leading_override_classification = (
                    _override_leading_candidate_from_subset(
                        relevant_candidates,
                        significant_threshold=significant_threshold,
                    )
                )
                audit_events.append(
                    InferenceAuditEvent(
                        action_type="promotion_blocked",
                        action_reason="close_competition",
                        from_entity_id=current_entity_id,
                        to_entity_id=winner.controller_entity_id,
                        score_before=current_company_candidate.total_score,
                        score_after=winner.total_score,
                        details={
                            "runner_up_entity_id": (
                                runner_up.controller_entity_id
                                if runner_up is not None
                                else None
                            )
                        },
                    )
                )
                break

            if winner.controller_entity_id in visited_entity_ids:
                if current_company_candidate.control_level == "control":
                    actual_controller_entity_id = current_entity_id
                    audit_events.append(
                        InferenceAuditEvent(
                            action_type="terminal_confirmed",
                            action_reason="promotion_cycle_detected",
                            from_entity_id=current_entity_id,
                            to_entity_id=target_entity.id,
                            score_before=current_company_candidate.total_score,
                            score_after=terminal_score_by_entity_id.get(current_entity_id),
                            details={"cycle_to_entity_id": winner.controller_entity_id},
                        )
                    )
                else:
                    terminal_failure_reason = "insufficient_evidence"
                    audit_events.append(
                        InferenceAuditEvent(
                            action_type="promotion_blocked",
                            action_reason="promotion_cycle_detected",
                            from_entity_id=current_entity_id,
                            to_entity_id=winner.controller_entity_id,
                            score_before=current_company_candidate.total_score,
                            score_after=winner.total_score,
                            details={},
                        )
                    )
                break

            if (
                winner_company_candidate is None
                or winner_company_candidate.control_level != "control"
            ):
                stop_reason = "no_parent_control_above_target_threshold"
                if (
                    winner_company_candidate is not None
                    and winner_company_candidate.control_level == "significant_influence"
                ):
                    stop_reason = "upstream_significant_influence_only"
                if current_company_candidate.control_level == "control":
                    actual_controller_entity_id = current_entity_id
                    audit_events.append(
                        InferenceAuditEvent(
                            action_type="terminal_confirmed",
                            action_reason=stop_reason,
                            from_entity_id=current_entity_id,
                            to_entity_id=target_entity.id,
                            score_before=current_company_candidate.total_score,
                            score_after=terminal_score_by_entity_id.get(current_entity_id),
                            details={
                                "candidate_parent_entity_id": winner.controller_entity_id
                            },
                        )
                    )
                else:
                    terminal_failure_reason = "insufficient_evidence"
                    audit_events.append(
                        InferenceAuditEvent(
                            action_type="promotion_blocked",
                            action_reason=stop_reason,
                            from_entity_id=current_entity_id,
                            to_entity_id=winner.controller_entity_id,
                            score_before=current_company_candidate.total_score,
                            score_after=winner.total_score,
                            details={
                                "reason": "parent_does_not_control_target_above_threshold"
                            },
                        )
                    )
                break

            block_reason = _promotion_block_reason(
                _candidate_immediate_edge(winner),
                parent_entity=context.entity_map.get(winner.controller_entity_id),
            )
            if block_reason in {"beneficial_owner_unknown", "nominee_without_disclosure"}:
                terminal_failure_reason = block_reason
                leading_override_entity_id = winner_company_candidate.controller_entity_id
                leading_override_classification = (
                    "significant_influence_candidate"
                    if winner_company_candidate.control_level == "significant_influence"
                    else "absolute_control"
                )
                audit_events.append(
                    InferenceAuditEvent(
                        action_type="promotion_blocked",
                        action_reason=block_reason,
                        from_entity_id=current_entity_id,
                        to_entity_id=winner.controller_entity_id,
                        score_before=current_company_candidate.total_score,
                        score_after=winner.total_score,
                        details={},
                    )
                )
                break

            if block_reason in {"protective_right_only", "look_through_not_allowed"}:
                if current_company_candidate.control_level == "control":
                    actual_controller_entity_id = current_entity_id
                    audit_events.append(
                        InferenceAuditEvent(
                            action_type="terminal_confirmed",
                            action_reason=block_reason,
                            from_entity_id=current_entity_id,
                            to_entity_id=target_entity.id,
                            score_before=current_company_candidate.total_score,
                            score_after=terminal_score_by_entity_id.get(current_entity_id),
                            details={},
                        )
                    )
                else:
                    terminal_failure_reason = "insufficient_evidence"
                    audit_events.append(
                        InferenceAuditEvent(
                            action_type="promotion_blocked",
                            action_reason=block_reason,
                            from_entity_id=current_entity_id,
                            to_entity_id=winner.controller_entity_id,
                            score_before=current_company_candidate.total_score,
                            score_after=winner.total_score,
                            details={},
                        )
                    )
                break

            look_through_applied = True
            promotion_path_entity_ids.append(winner.controller_entity_id)
            promotion_source_by_entity_id[winner.controller_entity_id] = current_entity_id
            promotion_reason_by_entity_id[winner.controller_entity_id] = (
                _promotion_reason_for_entity(
                    current_entity,
                    context.entity_map.get(winner.controller_entity_id),
                )
            )
            terminal_score_by_entity_id[winner.controller_entity_id] = winner.total_score
            audit_events.append(
                InferenceAuditEvent(
                    action_type="promotion_to_parent",
                    action_reason=promotion_reason_by_entity_id[
                        winner.controller_entity_id
                    ],
                    from_entity_id=current_entity_id,
                    to_entity_id=winner.controller_entity_id,
                    score_before=current_company_candidate.total_score,
                    score_after=winner.total_score,
                    details={
                        "company_target_score_after_promotion": serialize_unit_score(
                            winner_company_candidate.total_score
                        )
                    },
                )
            )

            current_entity_id = winner.controller_entity_id
            current_company_candidate = winner_company_candidate
            visited_entity_ids.add(current_entity_id)

        if actual_controller_entity_id is not None:
            actual_candidate = company_candidate_map.get(actual_controller_entity_id)
            controller_entity = context.entity_map.get(actual_controller_entity_id)
            actual_control_country = (
                _resolve_controller_country(controller_entity)
                or company.incorporation_country
            )
            if actual_candidate is not None:
                attribution_type = _resolve_country_attribution_type(actual_candidate)
            attribution_layer = (
                "ultimate_controller_country"
                if look_through_applied
                or actual_controller_entity_id != direct_controller_entity_id
                else "direct_controller_country"
            )
            country_inference_reason = (
                "derived_from_ultimate_controller"
                if attribution_layer == "ultimate_controller_country"
                else "derived_from_direct_controller"
            )
        elif direct_candidate is not None:
            if (
                terminal_failure_reason not in {"joint_control"}
                and direct_controller_country
                and direct_candidate.control_level == "control"
            ):
                actual_control_country = direct_controller_country
                attribution_type = _resolve_country_attribution_type(direct_candidate)
                attribution_layer = "direct_controller_country"
                country_inference_reason = "derived_from_direct_controller"

    if actual_controller_entity_id is not None:
        leading_candidate_entity_id = actual_controller_entity_id
        leading_candidate_classification = "absolute_control"
    elif leading_override_entity_id is not None:
        leading_candidate_entity_id = leading_override_entity_id
        leading_candidate_classification = leading_override_classification

    controller_status = _resolve_controller_status(
        actual_controller_entity_id=actual_controller_entity_id,
        joint_controller_entity_ids=joint_controller_entity_ids,
        leading_candidate_entity_id=leading_candidate_entity_id,
    )

    return ControlInferenceResult(
        company=company,
        target_entity=target_entity,
        aggregator=aggregator,
        candidates=tuple(candidates),
        direct_controller_entity_id=direct_controller_entity_id,
        direct_controller_country=direct_controller_country,
        actual_controller_entity_id=actual_controller_entity_id,
        leading_candidate_entity_id=leading_candidate_entity_id,
        leading_candidate_classification=leading_candidate_classification,
        actual_control_country=actual_control_country,
        attribution_type=attribution_type,
        attribution_layer=attribution_layer,
        country_inference_reason=country_inference_reason,
        controller_status=controller_status,
        joint_controller_entity_ids=joint_controller_entity_ids,
        look_through_applied=look_through_applied,
        promotion_path_entity_ids=tuple(promotion_path_entity_ids),
        promotion_source_by_entity_id=promotion_source_by_entity_id,
        promotion_reason_by_entity_id=promotion_reason_by_entity_id,
        terminal_score_by_entity_id=terminal_score_by_entity_id,
        terminal_failure_reason=terminal_failure_reason,
        audit_events=tuple(audit_events),
    )
