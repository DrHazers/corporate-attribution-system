from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.crud.business_segment import get_business_segment_by_id
from backend.crud.business_segment_classification import (
    get_business_segment_classifications_by_segment_id,
)
from backend.models.business_segment import BusinessSegment
from backend.models.business_segment_classification import BusinessSegmentClassification
from backend.schemas.business_segment_classification import (
    BusinessSegmentClassificationRefreshSummary,
    BusinessSegmentClassificationSuggestionRead,
    BusinessSegmentLlmSuggestionResponse,
    BusinessSegmentClassificationRead,
)


STANDARD_SYSTEM = "GICS"
GENERIC_TERMS = {
    "business",
    "businesses",
    "group",
    "groups",
    "operations",
    "operation",
    "platform",
    "platforms",
    "product",
    "products",
    "segment",
    "segments",
    "service",
    "services",
    "solution",
    "solutions",
}
EMERGING_TERMS = {
    "emerging",
    "future",
    "incubation",
    "innovation",
    "new venture",
    "new ventures",
    "other business",
    "other businesses",
}


@dataclass(frozen=True, slots=True)
class ClassificationRule:
    key: str
    levels: tuple[str | None, str | None, str | None, str | None]
    keywords: tuple[str, ...]
    confidence: Decimal
    generic: bool = False
    negative_keywords: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuleCandidate:
    rule: ClassificationRule
    score: int
    matched_keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClassificationProposal:
    standard_system: str
    level_1: str | None
    level_2: str | None
    level_3: str | None
    level_4: str | None
    is_primary: bool
    mapping_basis: str | None
    review_status: str
    classifier_type: str
    confidence: Decimal | None
    review_reason: str | None

    def to_model_dict(self) -> dict[str, Any]:
        return {
            "standard_system": self.standard_system,
            "level_1": self.level_1,
            "level_2": self.level_2,
            "level_3": self.level_3,
            "level_4": self.level_4,
            "is_primary": self.is_primary,
            "mapping_basis": self.mapping_basis,
            "review_status": self.review_status,
            "classifier_type": self.classifier_type,
            "confidence": self.confidence,
            "review_reason": self.review_reason,
        }


CLASSIFICATION_RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        key="cloud_software",
        levels=(
            "Information Technology",
            "Software & Services",
            "Software",
            "Application Software",
        ),
        keywords=(
            "cloud",
            "saas",
            "software",
            "cybersecurity",
            "subscription software",
            "developer tools",
        ),
        confidence=Decimal("0.94"),
    ),
    ClassificationRule(
        key="semiconductors",
        levels=(
            "Information Technology",
            "Semiconductors & Semiconductor Equipment",
            "Semiconductors & Semiconductor Equipment",
            "Semiconductors",
        ),
        keywords=(
            "chip",
            "chips",
            "semiconductor",
            "foundry",
            "memory",
            "integrated circuit",
        ),
        confidence=Decimal("0.96"),
    ),
    ClassificationRule(
        key="technology_hardware",
        levels=(
            "Information Technology",
            "Technology Hardware & Equipment",
            "Technology Hardware, Storage & Peripherals",
            "Technology Hardware, Storage & Peripherals",
        ),
        keywords=(
            "device",
            "devices",
            "smartphone",
            "iphone",
            "mac",
            "ipad",
            "wearables",
            "pc",
            "laptop",
            "server",
            "storage",
        ),
        confidence=Decimal("0.93"),
    ),
    ClassificationRule(
        key="telecom_services",
        levels=(
            "Communication Services",
            "Telecommunication Services",
            "Diversified Telecommunication Services",
            "Integrated Telecommunication Services",
        ),
        keywords=(
            "telecom",
            "telecommunications",
            "wireless",
            "mobile network",
            "broadband",
            "fiber",
            "carrier",
        ),
        confidence=Decimal("0.93"),
    ),
    ClassificationRule(
        key="interactive_media",
        levels=(
            "Communication Services",
            "Media & Entertainment",
            "Interactive Media & Services",
            "Interactive Media & Services",
        ),
        keywords=(
            "advertising",
            "digital media",
            "digital services",
            "gaming",
            "streaming",
            "social media",
            "subscriptions",
            "content platform",
        ),
        confidence=Decimal("0.89"),
    ),
    ClassificationRule(
        key="financial_services",
        levels=(
            "Financials",
            "Financial Services",
            "Financial Services",
            "Transaction & Payment Processing Services",
        ),
        keywords=(
            "bank",
            "banking",
            "capital markets",
            "consumer finance",
            "financial services",
            "fintech",
            "insurance",
            "investment",
            "payments",
            "wealth",
        ),
        confidence=Decimal("0.91"),
    ),
    ClassificationRule(
        key="health_care",
        levels=(
            "Health Care",
            "Health Care Equipment & Services",
            "Health Care Equipment & Supplies",
            "Health Care Equipment",
        ),
        keywords=(
            "biotech",
            "biotechnology",
            "diagnostic",
            "healthcare",
            "hospital",
            "medical",
            "medical device",
            "pharma",
            "pharmaceutical",
        ),
        confidence=Decimal("0.93"),
    ),
    ClassificationRule(
        key="energy",
        levels=(
            "Energy",
            "Energy",
            "Oil, Gas & Consumable Fuels",
            "Integrated Oil & Gas",
        ),
        keywords=(
            "drilling",
            "energy",
            "fuel",
            "gas",
            "lng",
            "oil",
            "petrochemical",
            "refining",
        ),
        confidence=Decimal("0.91"),
    ),
    ClassificationRule(
        key="utilities",
        levels=(
            "Utilities",
            "Utilities",
            "Multi-Utilities",
            "Multi-Utilities",
        ),
        keywords=(
            "electricity",
            "grid",
            "power",
            "renewable",
            "solar",
            "utility",
            "water",
            "wind",
        ),
        confidence=Decimal("0.89"),
    ),
    ClassificationRule(
        key="industrials",
        levels=(
            "Industrials",
            "Capital Goods",
            "Machinery",
            "Industrial Machinery & Supplies & Components",
        ),
        keywords=(
            "automation",
            "equipment",
            "industrial",
            "logistics",
            "machinery",
            "manufacturing",
            "robotics",
            "transportation",
        ),
        confidence=Decimal("0.88"),
    ),
    ClassificationRule(
        key="consumer_retail",
        levels=(
            "Consumer Discretionary",
            "Consumer Discretionary Distribution & Retail",
            "Broadline Retail",
            "Broadline Retail",
        ),
        keywords=(
            "apparel",
            "consumer products",
            "e commerce",
            "e-commerce",
            "retail",
            "shopping",
            "travel",
        ),
        confidence=Decimal("0.85"),
    ),
    ClassificationRule(
        key="consumer_staples",
        levels=(
            "Consumer Staples",
            "Consumer Staples Distribution & Retail",
            "Consumer Staples Merchandise Retail",
            "Consumer Staples Merchandise Retail",
        ),
        keywords=(
            "agriculture",
            "beverage",
            "food",
            "grocery",
            "household",
            "packaged foods",
            "personal care",
        ),
        confidence=Decimal("0.87"),
    ),
    ClassificationRule(
        key="materials",
        levels=(
            "Materials",
            "Materials",
            "Metals & Mining",
            "Diversified Metals & Mining",
        ),
        keywords=(
            "aluminum",
            "chemicals",
            "copper",
            "materials",
            "metals",
            "mining",
            "paper",
            "steel",
        ),
        confidence=Decimal("0.86"),
    ),
    ClassificationRule(
        key="real_estate",
        levels=(
            "Real Estate",
            "Real Estate Management & Development",
            "Real Estate Management & Development",
            "Real Estate Development",
        ),
        keywords=(
            "construction",
            "property",
            "real estate",
            "residential",
            "shopping mall",
            "township",
        ),
        confidence=Decimal("0.84"),
    ),
)


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    lowered = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(normalized.split())


def _contains_phrase(text_value: str, phrase: str) -> bool:
    if not text_value:
        return False
    normalized_text = f" {text_value} "
    normalized_phrase = f" {_normalize_text(phrase)} "
    return normalized_phrase in normalized_text


def _segment_text_context(segment: BusinessSegment) -> dict[str, str]:
    name_text = _normalize_text(segment.segment_name)
    alias_text = _normalize_text(segment.segment_alias)
    description_text = _normalize_text(segment.description)
    combined_parts = [part for part in (name_text, alias_text, description_text) if part]
    combined_text = " ".join(combined_parts)
    return {
        "name_text": name_text,
        "alias_text": alias_text,
        "description_text": description_text,
        "combined_text": combined_text,
    }


def _score_rule(rule: ClassificationRule, context: dict[str, str]) -> RuleCandidate | None:
    combined_text = context["combined_text"]
    if any(_contains_phrase(combined_text, keyword) for keyword in rule.negative_keywords):
        return None

    matched_keywords: list[str] = []
    score = 0
    for keyword in rule.keywords:
        if _contains_phrase(context["name_text"], keyword) or _contains_phrase(
            context["alias_text"], keyword
        ):
            matched_keywords.append(keyword)
            score += 3
            continue
        if _contains_phrase(context["description_text"], keyword):
            matched_keywords.append(keyword)
            score += 1

    if score <= 0:
        return None

    return RuleCandidate(
        rule=rule,
        score=score,
        matched_keywords=tuple(dict.fromkeys(matched_keywords)),
    )


def _format_rule_basis(candidate: RuleCandidate) -> str:
    matched = ", ".join(candidate.matched_keywords[:5])
    return f"Matched rule '{candidate.rule.key}' via keywords: {matched}."


def _build_special_case_proposal(
    segment: BusinessSegment,
    *,
    review_status: str,
    review_reason: str,
    mapping_basis: str,
    confidence: Decimal,
    levels: tuple[str | None, str | None, str | None, str | None] = (None, None, None, None),
) -> ClassificationProposal:
    return ClassificationProposal(
        standard_system=STANDARD_SYSTEM,
        level_1=levels[0],
        level_2=levels[1],
        level_3=levels[2],
        level_4=levels[3],
        is_primary=segment.segment_type == "primary",
        mapping_basis=mapping_basis,
        review_status=review_status,
        classifier_type="rule_based",
        confidence=confidence,
        review_reason=review_reason,
    )


def _common_levels(
    candidates: list[RuleCandidate],
) -> tuple[str | None, str | None, str | None, str | None]:
    if not candidates:
        return (None, None, None, None)
    level_lists = [candidate.rule.levels for candidate in candidates]
    common: list[str | None] = []
    for index in range(4):
        current_values = {levels[index] for levels in level_lists}
        if len(current_values) != 1:
            break
        value = next(iter(current_values))
        common.append(value)
    while len(common) < 4:
        common.append(None)
    return tuple(common)  # type: ignore[return-value]


def classify_business_segment_with_rules(
    segment: BusinessSegment,
) -> ClassificationProposal:
    context = _segment_text_context(segment)
    combined_text = context["combined_text"]
    token_set = set(combined_text.split())

    if not combined_text or token_set.issubset(GENERIC_TERMS):
        return _build_special_case_proposal(
            segment,
            review_status="needs_llm_review",
            review_reason="insufficient_description",
            mapping_basis=(
                "Segment text is too generic to map safely with rules. "
                "Need richer segment description or LLM/manual review."
            ),
            confidence=Decimal("0.15"),
        )

    if any(_contains_phrase(combined_text, term) for term in EMERGING_TERMS):
        return _build_special_case_proposal(
            segment,
            review_status="needs_llm_review",
            review_reason="emerging_business",
            mapping_basis=(
                "Detected emerging or exploratory business wording; rules avoid "
                "assigning a narrow GICS classification."
            ),
            confidence=Decimal("0.20"),
        )

    candidates = [
        candidate
        for candidate in (
            _score_rule(rule, context) for rule in CLASSIFICATION_RULES
        )
        if candidate is not None
    ]
    if not candidates:
        return _build_special_case_proposal(
            segment,
            review_status="unmapped",
            review_reason="rule_not_matched",
            mapping_basis=(
                "No stable GICS rule matched segment_name, segment_alias, or description."
            ),
            confidence=Decimal("0.00"),
        )

    candidates.sort(key=lambda item: (item.score, item.rule.confidence), reverse=True)
    top_score = candidates[0].score
    top_candidates = [candidate for candidate in candidates if candidate.score == top_score]

    if len(top_candidates) > 1:
        common_levels = _common_levels(top_candidates)
        top_level_1_values = {candidate.rule.levels[0] for candidate in top_candidates}
        top_level_2_values = {candidate.rule.levels[1] for candidate in top_candidates}
        basis = (
            "Multiple rule candidates matched with similar strength: "
            + ", ".join(candidate.rule.key for candidate in top_candidates[:4])
            + "."
        )
        if len(top_level_1_values) > 1:
            return _build_special_case_proposal(
                segment,
                review_status="conflicted",
                review_reason="multi_candidate_conflict",
                mapping_basis=basis + " Cross-domain conflict left unmapped for safety.",
                confidence=Decimal("0.25"),
            )
        if len(top_level_2_values) > 1 or common_levels[1] is None:
            return _build_special_case_proposal(
                segment,
                review_status="needs_llm_review",
                review_reason="cross_domain_segment",
                mapping_basis=basis + " Sector is similar but industry detail is unstable.",
                confidence=Decimal("0.32"),
                levels=common_levels,
            )
        return _build_special_case_proposal(
            segment,
            review_status="needs_llm_review",
            review_reason="multi_candidate_conflict",
            mapping_basis=basis + " Holding the shared upper-level mapping only.",
            confidence=Decimal("0.35"),
            levels=common_levels,
        )

    best = candidates[0]
    mapping_basis = _format_rule_basis(best)
    levels = best.rule.levels
    if best.score >= 6:
        return ClassificationProposal(
            standard_system=STANDARD_SYSTEM,
            level_1=levels[0],
            level_2=levels[1],
            level_3=levels[2],
            level_4=levels[3],
            is_primary=segment.segment_type == "primary",
            mapping_basis=mapping_basis,
            review_status="confirmed",
            classifier_type="rule_based",
            confidence=best.rule.confidence,
            review_reason=None,
        )
    if best.score >= 3:
        return ClassificationProposal(
            standard_system=STANDARD_SYSTEM,
            level_1=levels[0],
            level_2=levels[1],
            level_3=levels[2],
            level_4=None,
            is_primary=segment.segment_type == "primary",
            mapping_basis=mapping_basis + " Retained conservative depth because support is moderate.",
            review_status="pending",
            classifier_type="rule_based",
            confidence=min(best.rule.confidence, Decimal("0.70")),
            review_reason="low_confidence",
        )
    return _build_special_case_proposal(
        segment,
        review_status="needs_llm_review",
        review_reason="low_confidence",
        mapping_basis=mapping_basis + " Rule signal is too weak for a stable final mapping.",
        confidence=Decimal("0.40"),
        levels=(levels[0], levels[1], None, None),
    )


def _replace_classification_rows(
    db: Session,
    *,
    segments: list[BusinessSegment],
    segment_ids: list[int] | None = None,
) -> list[BusinessSegmentClassification]:
    created_rows: list[BusinessSegmentClassification] = []
    delete_query = db.query(BusinessSegmentClassification)
    if segment_ids:
        delete_query = delete_query.filter(
            BusinessSegmentClassification.business_segment_id.in_(segment_ids)
        )
    delete_query.delete(synchronize_session=False)

    for segment in segments:
        proposal = classify_business_segment_with_rules(segment)
        classification = BusinessSegmentClassification(
            business_segment_id=segment.id,
            **proposal.to_model_dict(),
        )
        db.add(classification)
        created_rows.append(classification)
    db.flush()
    return created_rows


def refresh_business_segment_classifications(
    db: Session,
    *,
    segment_ids: list[int] | None = None,
) -> BusinessSegmentClassificationRefreshSummary:
    query = db.query(BusinessSegment).order_by(BusinessSegment.id.asc())
    if segment_ids:
        query = query.filter(BusinessSegment.id.in_(segment_ids))
    segments = query.all()

    backup_table: str | None = None
    if segment_ids is None:
        existing_rows = db.query(BusinessSegmentClassification).count()
        if existing_rows >= 0:
            backup_table = (
                "business_segment_classifications_backup_"
                + datetime.now().strftime("%Y%m%d_%H%M%S")
            )
            db.execute(
                text(
                    f'CREATE TABLE "{backup_table}" AS '
                    "SELECT * FROM business_segment_classifications"
                )
            )
    created_rows = _replace_classification_rows(
        db,
        segments=segments,
        segment_ids=segment_ids,
    )
    db.commit()

    status_counts = Counter(row.review_status for row in created_rows)
    return BusinessSegmentClassificationRefreshSummary(
        total_segments=len(segments),
        classification_rows=len(created_rows),
        confirmed_count=status_counts.get("confirmed", 0),
        pending_count=status_counts.get("pending", 0),
        needs_llm_review_count=status_counts.get("needs_llm_review", 0),
        needs_manual_review_count=status_counts.get("needs_manual_review", 0),
        conflicted_count=status_counts.get("conflicted", 0),
        unmapped_count=status_counts.get("unmapped", 0),
        backup_table=backup_table,
    )


def classify_business_segment_with_llm(
    db: Session,
    *,
    segment_id: int,
) -> BusinessSegmentLlmSuggestionResponse:
    segment = get_business_segment_by_id(db, segment_id)
    if segment is None:
        raise LookupError("Business segment not found.")

    current_classification = None
    current_rows = get_business_segment_classifications_by_segment_id(
        db,
        business_segment_id=segment_id,
    )
    if current_rows:
        current_classification = BusinessSegmentClassificationRead.model_validate(
            current_rows[0]
        )

    suggestion = BusinessSegmentClassificationSuggestionRead(
        standard_system=STANDARD_SYSTEM,
        level_1=None,
        level_2=None,
        level_3=None,
        level_4=None,
        is_primary=segment.segment_type == "primary",
        mapping_basis=(
            "TODO: connect the real LLM classifier. This placeholder reserves the "
            "response contract for a single-segment model-assisted classification."
        ),
        review_status="needs_manual_review",
        classifier_type="llm_assisted",
        confidence=Decimal("0.00"),
        review_reason="llm_suggested",
    )
    return BusinessSegmentLlmSuggestionResponse(
        segment_id=segment_id,
        status="placeholder",
        message=(
            "LLM classification endpoint shape is ready, but real model inference "
            "is not connected yet."
        ),
        current_classification=current_classification,
        suggested_classification=suggestion,
    )
