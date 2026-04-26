from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import json
import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, selectinload

from backend.crud.annotation_log import create_annotation_log, serialize_model_snapshot
from backend.crud.business_segment_classification import (
    get_business_segment_classifications_by_segment_id,
)
from backend.models.business_segment import BusinessSegment
from backend.models.business_segment_classification import BusinessSegmentClassification
from backend.models.company import Company
from backend.schemas.business_segment_classification import (
    BusinessSegmentManualClassificationRequest,
    BusinessSegmentManualClassificationResponse,
    BusinessSegmentLlmConfirmationResponse,
    BusinessSegmentClassificationRead,
    BusinessSegmentClassificationRefreshSummary,
    BusinessSegmentClassificationSuggestionRead,
    BusinessSegmentLlmRequestContext,
    normalize_classification_review_status,
    normalize_classifier_type,
    normalize_optional_text,
    normalize_standard_system,
    BusinessSegmentLlmSuggestionResponse,
)
from backend.services.llm.deepseek_client import DeepSeekChatClient


STANDARD_SYSTEM = "GICS"
logger = logging.getLogger(__name__)
TEXT_SOURCES = ("name", "alias", "description", "company", "peer")
SOURCE_WEIGHTS = {
    "name": 4,
    "alias": 4,
    "description": 2,
    "company": 1,
    "peer": 1,
}
GENERIC_TERMS = {
    "and",
    "business",
    "businesses",
    "device",
    "devices",
    "ecosystem",
    "enterprise",
    "group",
    "groups",
    "integrated",
    "intelligent",
    "mobility",
    "operation",
    "operations",
    "platform",
    "platforms",
    "product",
    "products",
    "segment",
    "segments",
    "service",
    "services",
    "smart",
    "solution",
    "solutions",
}
EMERGING_TERMS = {
    "emerging",
    "exploratory",
    "future",
    "incubation",
    "innovation",
    "new venture",
    "new ventures",
    "other bet",
    "other bets",
    "venture incubation",
}
HIGH_RISK_AMBIGUOUS_PHRASES = (
    "platform services",
    "digital ecosystem",
    "enterprise solutions",
    "smart mobility",
    "intelligent devices",
    "energy solutions",
    "cloud and ai infrastructure",
    "integrated services",
)
NORMALIZATION_RULES: tuple[tuple[str, str], ...] = (
    (r"\be[\-\s]?commerce\b", "ecommerce"),
    (r"\bdata\s+centre\b", "data center"),
    (r"\bsoftware[\-\s]?as[\-\s]?a[\-\s]?service\b", "saas"),
    (r"\bsoftware[\-\s]?as[\-\s]?a[\-\s]?services\b", "saas"),
    (r"\bonline travel agency\b", "ota"),
    (r"\btravel booking platform\b", "ota"),
    (r"\bbusiness process outsourcing\b", "bpo"),
    (r"\bmerchant acquiring\b", "merchant acquiring"),
    (r"\bpoint[\-\s]?of[\-\s]?sale\b", "point of sale"),
    (r"\bdata processing and outsourced services\b", "data processing outsourced services"),
    (r"\bdigital wallets\b", "digital wallet"),
    (r"\bcloud computing\b", "cloud"),
    (r"\bartificial intelligence\b", "ai"),
)


@dataclass(frozen=True, slots=True)
class SegmentContext:
    segment_id: int
    company_id: int
    name_text: str
    alias_text: str
    description_text: str
    company_text: str
    peer_text: str
    combined_text: str


@dataclass(frozen=True, slots=True)
class RuleFamily:
    family: str
    fallback_levels: tuple[str | None, str | None, str | None, str | None]
    strong_phrases: tuple[str, ...] = ()
    support_phrases: tuple[str, ...] = ()
    negative_phrases: tuple[str, ...] = ()
    company_context_phrases: tuple[str, ...] = ()
    max_depth: int = 3
    confirm_threshold: int = 22
    pending_threshold: int = 12


@dataclass(frozen=True, slots=True)
class ClassificationRule:
    rule_key: str
    family: str
    gics_levels: tuple[str | None, str | None, str | None, str | None]
    strong_phrases: tuple[str, ...] = ()
    support_phrases: tuple[str, ...] = ()
    negative_phrases: tuple[str, ...] = ()
    company_context_phrases: tuple[str, ...] = ()
    max_depth: int = 4
    confirm_threshold: int = 26
    pending_threshold: int = 14


@dataclass(frozen=True, slots=True)
class MatchEvidence:
    score: int
    hits_by_source: dict[str, tuple[str, ...]]
    negatives_by_source: dict[str, tuple[str, ...]]

    @property
    def hit_count(self) -> int:
        return sum(len(values) for values in self.hits_by_source.values())


@dataclass(frozen=True, slots=True)
class FamilyCandidate:
    family: RuleFamily
    evidence: MatchEvidence

    @property
    def score(self) -> int:
        return self.evidence.score


@dataclass(frozen=True, slots=True)
class RuleCandidate:
    rule: ClassificationRule
    family_candidate: FamilyCandidate
    evidence: MatchEvidence

    @property
    def score(self) -> int:
        return self.family_candidate.score + self.evidence.score


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    context: SegmentContext
    family_candidates: list[FamilyCandidate]
    rule_candidates: list[RuleCandidate]


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


RULE_FAMILIES: dict[str, RuleFamily] = {
    "digital_commerce": RuleFamily(
        family="digital_commerce",
        fallback_levels=(None, None, None, None),
        strong_phrases=(
            "ecommerce",
            "marketplace",
            "online retail",
            "shopping platform",
            "merchant platform",
            "direct to consumer",
            "ota",
        ),
        support_phrases=(
            "commerce",
            "merchant",
            "fulfillment",
            "shopping",
            "travel booking",
            "delivery",
        ),
        negative_phrases=("advertising", "ad network", "payment processing", "lending"),
        company_context_phrases=("retail", "consumer", "travel"),
        max_depth=2,
    ),
    "media_adtech": RuleFamily(
        family="media_adtech",
        fallback_levels=(
            "Communication Services",
            "Media & Entertainment",
            "Interactive Media & Services",
            None,
        ),
        strong_phrases=(
            "digital advertising",
            "adtech",
            "advertising platform",
            "content platform",
            "streaming",
            "social media",
            "digital media",
        ),
        support_phrases=("creator", "audience", "traffic monetization", "media network"),
        negative_phrases=("payment gateway", "merchant acquiring", "travel booking"),
        company_context_phrases=("media", "advertising", "entertainment"),
        max_depth=3,
    ),
    "fintech": RuleFamily(
        family="fintech",
        fallback_levels=("Financials", "Financial Services", "Financial Services", None),
        strong_phrases=(
            "payment processing",
            "payment gateway",
            "digital wallet",
            "merchant acquiring",
            "remittance",
            "fintech",
            "wealth management",
            "exchange",
            "financial data",
        ),
        support_phrases=(
            "payments",
            "merchant services",
            "brokerage",
            "lending",
            "trading",
            "transaction",
            "checkout",
            "point of sale",
        ),
        negative_phrases=("advertising network", "retail marketplace"),
        company_context_phrases=("banking", "financial", "capital markets"),
        max_depth=3,
    ),
    "software_it_services": RuleFamily(
        family="software_it_services",
        fallback_levels=("Information Technology", "Software & Services", None, None),
        strong_phrases=(
            "saas",
            "enterprise software",
            "cloud software",
            "application software",
            "system software",
            "cybersecurity",
            "data center",
            "colocation",
            "it consulting",
            "managed services",
            "bpo",
        ),
        support_phrases=(
            "cloud",
            "software",
            "developer tools",
            "workflow",
            "integration",
            "database",
            "hosting",
            "outsourced services",
        ),
        negative_phrases=("smartphone", "wearables", "semiconductor", "medical device"),
        company_context_phrases=("software", "technology", "enterprise"),
        max_depth=3,
    ),
    "semiconductors": RuleFamily(
        family="semiconductors",
        fallback_levels=(
            "Information Technology",
            "Semiconductors & Semiconductor Equipment",
            "Semiconductors & Semiconductor Equipment",
            None,
        ),
        strong_phrases=(
            "semiconductor",
            "chip",
            "wafer",
            "foundry",
            "fabless",
            "integrated circuit",
            "osat",
            "lithography",
        ),
        support_phrases=("packaging", "testing", "etch", "deposition", "memory"),
        negative_phrases=("consumer device", "software platform"),
        company_context_phrases=("semiconductor", "electronics"),
        max_depth=3,
    ),
    "technology_hardware": RuleFamily(
        family="technology_hardware",
        fallback_levels=(
            "Information Technology",
            "Technology Hardware & Equipment",
            "Technology Hardware, Storage & Peripherals",
            None,
        ),
        strong_phrases=(
            "smartphone",
            "tablet",
            "laptop",
            "pc",
            "wearables",
            "smartwatch",
            "server",
            "storage",
            "router",
            "switch",
            "consumer electronics",
        ),
        support_phrases=("device", "peripheral", "network equipment", "hardware"),
        negative_phrases=("medical device", "automotive", "industrial equipment"),
        company_context_phrases=("electronics", "hardware"),
        max_depth=3,
    ),
    "automotive_mobility": RuleFamily(
        family="automotive_mobility",
        fallback_levels=(
            "Consumer Discretionary",
            "Automobiles & Components",
            None,
            None,
        ),
        strong_phrases=(
            "electric vehicle",
            "automobile",
            "automotive",
            "vehicle",
            "auto parts",
            "ride hailing",
            "mobility platform",
        ),
        support_phrases=("battery electric", "driver assistance", "fleet", "transport"),
        negative_phrases=("medical mobility", "industrial vehicle rental"),
        company_context_phrases=("automotive", "mobility"),
        max_depth=2,
    ),
    "energy_transition": RuleFamily(
        family="energy_transition",
        fallback_levels=(None, None, None, None),
        strong_phrases=(
            "battery",
            "energy storage",
            "solar",
            "wind",
            "renewable power",
            "electric utility",
            "grid",
            "lng",
            "oil and gas",
            "energy trading",
        ),
        support_phrases=("power", "utility", "charging", "renewable", "transmission"),
        negative_phrases=("payment platform", "software workflow"),
        company_context_phrases=("energy", "power", "utility"),
        max_depth=2,
    ),
    "health_technology": RuleFamily(
        family="health_technology",
        fallback_levels=(
            "Health Care",
            "Health Care Equipment & Services",
            None,
            None,
        ),
        strong_phrases=(
            "medical device",
            "diagnostic",
            "digital health",
            "clinical software",
            "health care technology",
            "healthcare it",
        ),
        support_phrases=("medical", "hospital", "patient", "imaging", "biotech"),
        negative_phrases=("beauty", "consumer wellness"),
        company_context_phrases=("health care", "medical"),
        max_depth=2,
    ),
}

CLASSIFICATION_RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        rule_key="broadline_retail_marketplace",
        family="digital_commerce",
        gics_levels=(
            "Consumer Discretionary",
            "Consumer Discretionary Distribution & Retail",
            "Broadline Retail",
            "Broadline Retail",
        ),
        strong_phrases=("ecommerce", "online retail", "marketplace", "merchant platform"),
        support_phrases=("shopping", "direct to consumer", "merchant services", "fulfillment"),
        negative_phrases=("advertising network", "payment processing", "travel booking"),
        confirm_threshold=28,
        pending_threshold=16,
    ),
    ClassificationRule(
        rule_key="internet_travel_ota",
        family="digital_commerce",
        gics_levels=(
            "Consumer Discretionary",
            "Consumer Services",
            "Hotels, Restaurants & Leisure",
            "Hotels, Resorts & Cruise Lines",
        ),
        strong_phrases=("ota", "travel booking", "hotel booking", "airline booking"),
        support_phrases=("travel marketplace", "accommodation", "flight booking"),
        negative_phrases=("digital wallet", "payment gateway"),
        confirm_threshold=26,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="interactive_media_and_advertising",
        family="media_adtech",
        gics_levels=(
            "Communication Services",
            "Media & Entertainment",
            "Interactive Media & Services",
            "Interactive Media & Services",
        ),
        strong_phrases=(
            "digital advertising",
            "advertising platform",
            "adtech",
            "social media",
            "content platform",
            "streaming platform",
        ),
        support_phrases=("audience", "traffic monetization", "media network", "creator"),
        negative_phrases=("merchant acquiring", "travel booking"),
        confirm_threshold=27,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="transaction_and_payment_processing",
        family="fintech",
        gics_levels=(
            "Financials",
            "Financial Services",
            "Financial Services",
            "Transaction & Payment Processing Services",
        ),
        strong_phrases=(
            "payment processing",
            "payment gateway",
            "merchant acquiring",
            "digital wallet",
            "remittance",
            "point of sale",
        ),
        support_phrases=("payments", "checkout", "merchant services", "card issuing"),
        negative_phrases=("advertising network", "travel booking"),
        confirm_threshold=28,
        pending_threshold=16,
    ),
    ClassificationRule(
        rule_key="wealth_and_market_infrastructure",
        family="fintech",
        gics_levels=(
            "Financials",
            "Financial Services",
            "Capital Markets",
            "Financial Exchanges & Data",
        ),
        strong_phrases=("exchange", "financial data", "market data", "trading venue"),
        support_phrases=("wealth management", "brokerage", "asset management", "investment platform"),
        negative_phrases=("payment gateway", "consumer lending"),
        confirm_threshold=26,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="application_software",
        family="software_it_services",
        gics_levels=(
            "Information Technology",
            "Software & Services",
            "Software",
            "Application Software",
        ),
        strong_phrases=(
            "saas",
            "enterprise software",
            "application software",
            "workflow software",
            "erp",
            "crm",
            "developer tools",
        ),
        support_phrases=("cloud software", "software platform", "collaboration", "subscription software"),
        negative_phrases=("data center", "it consulting", "semiconductor"),
        confirm_threshold=28,
        pending_threshold=16,
    ),
    ClassificationRule(
        rule_key="systems_software",
        family="software_it_services",
        gics_levels=(
            "Information Technology",
            "Software & Services",
            "Software",
            "Systems Software",
        ),
        strong_phrases=(
            "system software",
            "operating system",
            "database software",
            "cybersecurity",
            "network security",
            "middleware",
        ),
        support_phrases=("infrastructure software", "endpoint security", "identity security"),
        negative_phrases=("it consulting", "data center"),
        confirm_threshold=28,
        pending_threshold=16,
    ),
    ClassificationRule(
        rule_key="data_processing_and_outsourced_services",
        family="software_it_services",
        gics_levels=(
            "Information Technology",
            "Software & Services",
            "IT Services",
            "Data Processing & Outsourced Services",
        ),
        strong_phrases=(
            "data center",
            "colocation",
            "bpo",
            "data processing outsourced services",
            "managed infrastructure",
            "hosting services",
        ),
        support_phrases=("data processing", "managed services", "outsourced services", "cloud infrastructure"),
        negative_phrases=("application software", "erp", "crm"),
        max_depth=3,
        confirm_threshold=26,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="it_consulting_and_integration",
        family="software_it_services",
        gics_levels=(
            "Information Technology",
            "Software & Services",
            "IT Services",
            "IT Consulting & Other Services",
        ),
        strong_phrases=(
            "it consulting",
            "digital transformation services",
            "systems integration",
            "enterprise consulting",
        ),
        support_phrases=("implementation services", "technology consulting", "managed services"),
        negative_phrases=("saas", "system software", "data center"),
        max_depth=3,
        confirm_threshold=25,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="semiconductor_manufacturing",
        family="semiconductors",
        gics_levels=(
            "Information Technology",
            "Semiconductors & Semiconductor Equipment",
            "Semiconductors & Semiconductor Equipment",
            "Semiconductors",
        ),
        strong_phrases=("semiconductor", "foundry", "wafer", "fabless", "integrated circuit", "memory chip"),
        support_phrases=("logic chip", "chip design", "advanced node"),
        negative_phrases=("lithography equipment", "test equipment"),
        confirm_threshold=28,
        pending_threshold=16,
    ),
    ClassificationRule(
        rule_key="semiconductor_equipment_materials",
        family="semiconductors",
        gics_levels=(
            "Information Technology",
            "Semiconductors & Semiconductor Equipment",
            "Semiconductors & Semiconductor Equipment",
            "Semiconductor Materials & Equipment",
        ),
        strong_phrases=(
            "semiconductor equipment",
            "lithography",
            "etching equipment",
            "deposition equipment",
            "wafer equipment",
        ),
        support_phrases=("test equipment", "packaging", "semiconductor materials", "osat"),
        negative_phrases=("fabless", "memory chip"),
        confirm_threshold=27,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="technology_hardware_devices",
        family="technology_hardware",
        gics_levels=(
            "Information Technology",
            "Technology Hardware & Equipment",
            "Technology Hardware, Storage & Peripherals",
            "Technology Hardware, Storage & Peripherals",
        ),
        strong_phrases=("smartphone", "tablet", "laptop", "wearables", "smartwatch", "server", "storage"),
        support_phrases=("consumer electronics", "device", "peripheral", "pc"),
        negative_phrases=("medical device", "automotive"),
        confirm_threshold=27,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="communications_equipment",
        family="technology_hardware",
        gics_levels=(
            "Information Technology",
            "Technology Hardware & Equipment",
            "Communications Equipment",
            "Communications Equipment",
        ),
        strong_phrases=("router", "switch", "telecom equipment", "base station", "optical networking"),
        support_phrases=("network equipment", "communications hardware", "broadband equipment"),
        negative_phrases=("it consulting", "wireless services"),
        confirm_threshold=26,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="automobile_manufacturers",
        family="automotive_mobility",
        gics_levels=(
            "Consumer Discretionary",
            "Automobiles & Components",
            "Automobiles",
            "Automobile Manufacturers",
        ),
        strong_phrases=("electric vehicle", "automobile", "passenger vehicle", "vehicle manufacturing"),
        support_phrases=("vehicle", "ev", "automotive brand"),
        negative_phrases=("auto parts", "ride hailing"),
        confirm_threshold=27,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="automotive_parts_and_equipment",
        family="automotive_mobility",
        gics_levels=(
            "Consumer Discretionary",
            "Automobiles & Components",
            "Auto Components",
            "Automotive Parts & Equipment",
        ),
        strong_phrases=("auto parts", "automotive components", "powertrain", "braking system", "cockpit electronics"),
        support_phrases=("vehicle systems", "automotive supply"),
        negative_phrases=("ride hailing", "vehicle retail"),
        confirm_threshold=26,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="renewable_power_producers",
        family="energy_transition",
        gics_levels=(
            "Utilities",
            "Utilities",
            "Independent Power and Renewable Electricity Producers",
            "Renewable Electricity",
        ),
        strong_phrases=("renewable power", "solar generation", "wind farm", "independent power producer"),
        support_phrases=("solar", "wind", "renewable", "power generation"),
        negative_phrases=("battery pack", "energy trading"),
        confirm_threshold=26,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="electric_utilities",
        family="energy_transition",
        gics_levels=(
            "Utilities",
            "Utilities",
            "Electric Utilities",
            "Electric Utilities",
        ),
        strong_phrases=("electric utility", "grid operations", "regulated utility", "transmission distribution"),
        support_phrases=("power grid", "utility", "distribution network"),
        negative_phrases=("payment processing", "renewable developer"),
        confirm_threshold=26,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="battery_and_storage_equipment",
        family="energy_transition",
        gics_levels=(
            "Industrials",
            "Capital Goods",
            "Electrical Equipment",
            "Electrical Components & Equipment",
        ),
        strong_phrases=("battery", "energy storage", "battery pack", "charging hardware"),
        support_phrases=("storage system", "power electronics", "charging"),
        negative_phrases=("regulated utility", "oil and gas"),
        confirm_threshold=25,
        pending_threshold=14,
    ),
    ClassificationRule(
        rule_key="integrated_oil_and_gas",
        family="energy_transition",
        gics_levels=(
            "Energy",
            "Energy",
            "Oil, Gas & Consumable Fuels",
            "Integrated Oil & Gas",
        ),
        strong_phrases=("oil and gas", "lng", "refining", "drilling", "petrochemical"),
        support_phrases=("upstream", "midstream", "downstream", "fuel"),
        negative_phrases=("renewable power", "energy storage"),
        confirm_threshold=26,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="health_care_technology",
        family="health_technology",
        gics_levels=(
            "Health Care",
            "Health Care Equipment & Services",
            "Health Care Technology",
            "Health Care Technology",
        ),
        strong_phrases=("digital health", "clinical software", "health care technology", "healthcare it"),
        support_phrases=("electronic medical record", "clinical workflow", "medical software"),
        negative_phrases=("medical device", "pharmaceutical"),
        confirm_threshold=26,
        pending_threshold=15,
    ),
    ClassificationRule(
        rule_key="health_care_equipment",
        family="health_technology",
        gics_levels=(
            "Health Care",
            "Health Care Equipment & Services",
            "Health Care Equipment & Supplies",
            "Health Care Equipment",
        ),
        strong_phrases=("medical device", "diagnostic imaging", "surgical equipment", "patient monitor"),
        support_phrases=("diagnostic", "imaging", "medical equipment"),
        negative_phrases=("clinical software", "consumer wellness"),
        confirm_threshold=26,
        pending_threshold=15,
    ),
)


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""

    normalized = value.lower()
    normalized = normalized.replace("&", " and ")
    normalized = normalized.replace("@", " at ")
    normalized = re.sub(r"[\(\)\[\]\{\}]", " ", normalized)
    normalized = re.sub(r"[-_/]+", " ", normalized)
    for pattern, replacement in NORMALIZATION_RULES:
        normalized = re.sub(pattern, replacement, normalized)
    normalized = re.sub(r"[^a-z0-9\s]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _contains_phrase(text_value: str, phrase: str) -> bool:
    if not text_value:
        return False
    normalized_text = f" {text_value} "
    normalized_phrase = f" {_normalize_text(phrase)} "
    return normalized_phrase in normalized_text


def _unique_phrases(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _merge_source_phrase_maps(
    *maps: dict[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    merged: dict[str, list[str]] = {source: [] for source in TEXT_SOURCES}
    for source_map in maps:
        for source in TEXT_SOURCES:
            merged[source].extend(source_map.get(source, ()))
    return {
        source: _unique_phrases(values)
        for source, values in merged.items()
        if values
    }


def _format_source_hits(source_map: dict[str, tuple[str, ...]]) -> str:
    parts: list[str] = []
    for source in TEXT_SOURCES:
        values = list(source_map.get(source, ()))
        rendered = ", ".join(values[:4])
        parts.append(f"{source}[{rendered}]")
    return " ".join(parts)


def _format_source_negatives(source_map: dict[str, tuple[str, ...]]) -> str:
    values: list[str] = []
    for source in TEXT_SOURCES:
        values.extend(source_map.get(source, ()))
    return f"[{', '.join(_unique_phrases(values)[:5])}]"


def _depth_label(levels: tuple[str | None, str | None, str | None, str | None]) -> str:
    depth = sum(1 for value in levels if value)
    return f"level_{depth}" if depth > 0 else "none"


def _truncate_levels(
    levels: tuple[str | None, str | None, str | None, str | None],
    max_depth: int,
) -> tuple[str | None, str | None, str | None, str | None]:
    truncated = list(levels)
    for index in range(max_depth, 4):
        truncated[index] = None
    return tuple(truncated)  # type: ignore[return-value]


def _common_levels(
    levels_list: list[tuple[str | None, str | None, str | None, str | None]],
) -> tuple[str | None, str | None, str | None, str | None]:
    if not levels_list:
        return (None, None, None, None)
    common: list[str | None] = []
    for index in range(4):
        values = {levels[index] for levels in levels_list}
        if len(values) != 1:
            break
        common.append(next(iter(values)))
    while len(common) < 4:
        common.append(None)
    return tuple(common)  # type: ignore[return-value]


def _mapping_basis(
    *,
    decision: str,
    rules: list[str],
    hits: dict[str, tuple[str, ...]],
    negatives: dict[str, tuple[str, ...]] | None = None,
    levels: tuple[str | None, str | None, str | None, str | None] = (None, None, None, None),
    comment: str | None = None,
) -> str:
    parts = [
        f"decision={decision}",
        f"rules={','.join(rules) if rules else 'none_stable'}",
        f"hits={_format_source_hits(hits)}",
        f"negatives={_format_source_negatives(negatives or {})}",
        f"depth={_depth_label(levels)}",
    ]
    if comment:
        parts.append(f"comment={comment}")
    return " | ".join(parts)


def _build_peer_lookup(segments: list[BusinessSegment]) -> dict[tuple[int, str | None], list[str]]:
    lookup: dict[tuple[int, str | None], list[str]] = defaultdict(list)
    for segment in segments:
        key = (segment.company_id, segment.reporting_period)
        lookup[key].append(segment.segment_name)
        if segment.segment_alias:
            lookup[key].append(segment.segment_alias)
    return lookup


def build_segment_context(
    segment: BusinessSegment,
    *,
    peer_lookup: dict[tuple[int, str | None], list[str]] | None = None,
) -> SegmentContext:
    company: Company | None = getattr(segment, "company", None)
    company_parts = []
    if company is not None:
        company_parts.extend(
            value
            for value in (
                company.name,
                company.description,
            )
            if value
        )
    company_text = _normalize_text(" ".join(company_parts))

    peer_values: list[str] = []
    if peer_lookup is not None:
        key = (segment.company_id, segment.reporting_period)
        peer_values = [
            value
            for value in peer_lookup.get(key, [])
            if _normalize_text(value) not in {
                _normalize_text(segment.segment_name),
                _normalize_text(segment.segment_alias),
            }
        ][:8]
    elif company is not None:
        peer_values = [
            other.segment_name
            for other in company.business_segments
            if other.id != segment.id
        ][:8]

    name_text = _normalize_text(segment.segment_name)
    alias_text = _normalize_text(segment.segment_alias)
    description_text = _normalize_text(segment.description)
    peer_text = _normalize_text(" ".join(peer_values))
    combined_text = " ".join(
        value
        for value in (
            name_text,
            alias_text,
            description_text,
            company_text,
            peer_text,
        )
        if value
    )
    return SegmentContext(
        segment_id=segment.id,
        company_id=segment.company_id,
        name_text=name_text,
        alias_text=alias_text,
        description_text=description_text,
        company_text=company_text,
        peer_text=peer_text,
        combined_text=combined_text,
    )


def _text_for_source(context: SegmentContext, source: str) -> str:
    return {
        "name": context.name_text,
        "alias": context.alias_text,
        "description": context.description_text,
        "company": context.company_text,
        "peer": context.peer_text,
    }[source]


def _score_match_evidence(
    context: SegmentContext,
    *,
    strong_phrases: tuple[str, ...],
    support_phrases: tuple[str, ...],
    negative_phrases: tuple[str, ...],
    company_context_phrases: tuple[str, ...],
) -> MatchEvidence:
    hits_by_source: dict[str, list[str]] = defaultdict(list)
    negatives_by_source: dict[str, list[str]] = defaultdict(list)
    score = 0

    for source in TEXT_SOURCES:
        source_text = _text_for_source(context, source)
        if not source_text:
            continue
        weight = SOURCE_WEIGHTS[source]

        for phrase in strong_phrases:
            if _contains_phrase(source_text, phrase):
                hits_by_source[source].append(_normalize_text(phrase))
                score += weight * 3
        for phrase in support_phrases:
            if _contains_phrase(source_text, phrase):
                hits_by_source[source].append(_normalize_text(phrase))
                score += weight
        if source in {"company", "peer"}:
            for phrase in company_context_phrases:
                if _contains_phrase(source_text, phrase):
                    hits_by_source[source].append(_normalize_text(phrase))
                    score += weight * 2
        for phrase in negative_phrases:
            if _contains_phrase(source_text, phrase):
                negatives_by_source[source].append(_normalize_text(phrase))
                score -= max(2, weight * 2)

    return MatchEvidence(
        score=score,
        hits_by_source={
            source: _unique_phrases(values)
            for source, values in hits_by_source.items()
            if values
        },
        negatives_by_source={
            source: _unique_phrases(values)
            for source, values in negatives_by_source.items()
            if values
        },
    )


def _collect_family_candidates(context: SegmentContext) -> list[FamilyCandidate]:
    candidates: list[FamilyCandidate] = []
    for family in RULE_FAMILIES.values():
        evidence = _score_match_evidence(
            context,
            strong_phrases=family.strong_phrases,
            support_phrases=family.support_phrases,
            negative_phrases=family.negative_phrases,
            company_context_phrases=family.company_context_phrases,
        )
        if evidence.score > 0 and evidence.hit_count > 0:
            candidates.append(FamilyCandidate(family=family, evidence=evidence))
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


def _eligible_families(family_candidates: list[FamilyCandidate]) -> list[FamilyCandidate]:
    if not family_candidates:
        return []
    top_score = family_candidates[0].score
    return [
        candidate
        for candidate in family_candidates
        if candidate.score >= candidate.family.pending_threshold
        or candidate.score >= max(6, top_score - 4)
    ]


def _collect_rule_candidates(
    context: SegmentContext,
    family_candidates: list[FamilyCandidate],
) -> list[RuleCandidate]:
    candidates: list[RuleCandidate] = []
    family_by_name = {candidate.family.family: candidate for candidate in family_candidates}
    for rule in CLASSIFICATION_RULES:
        family_candidate = family_by_name.get(rule.family)
        if family_candidate is None:
            continue
        evidence = _score_match_evidence(
            context,
            strong_phrases=rule.strong_phrases,
            support_phrases=rule.support_phrases,
            negative_phrases=rule.negative_phrases,
            company_context_phrases=rule.company_context_phrases,
        )
        if evidence.score > 0 and evidence.hit_count > 0:
            candidates.append(
                RuleCandidate(
                    rule=rule,
                    family_candidate=family_candidate,
                    evidence=evidence,
                )
            )
    candidates.sort(key=lambda item: (item.score, item.evidence.hit_count), reverse=True)
    return candidates


def evaluate_segment_candidates(
    segment: BusinessSegment,
    *,
    peer_lookup: dict[tuple[int, str | None], list[str]] | None = None,
) -> RuleEvaluation:
    context = build_segment_context(segment, peer_lookup=peer_lookup)
    family_candidates = _collect_family_candidates(context)
    eligible_families = _eligible_families(family_candidates)
    rule_candidates = _collect_rule_candidates(context, eligible_families)
    return RuleEvaluation(
        context=context,
        family_candidates=family_candidates,
        rule_candidates=rule_candidates,
    )


def _build_special_case_proposal(
    segment: BusinessSegment,
    *,
    review_status: str,
    review_reason: str,
    confidence: Decimal,
    comment: str,
    levels: tuple[str | None, str | None, str | None, str | None] = (None, None, None, None),
    rules: list[str] | None = None,
    hits: dict[str, tuple[str, ...]] | None = None,
    negatives: dict[str, tuple[str, ...]] | None = None,
) -> ClassificationProposal:
    return ClassificationProposal(
        standard_system=STANDARD_SYSTEM,
        level_1=levels[0],
        level_2=levels[1],
        level_3=levels[2],
        level_4=levels[3],
        is_primary=segment.segment_type == "primary",
        mapping_basis=_mapping_basis(
            decision=review_status,
            rules=rules or [],
            hits=hits or {},
            negatives=negatives or {},
            levels=levels,
            comment=comment,
        ),
        review_status=review_status,
        classifier_type="rule_based",
        confidence=confidence,
        review_reason=review_reason,
    )


def _is_generic_only_context(context: SegmentContext) -> bool:
    combined_tokens = set(context.combined_text.split())
    if not combined_tokens:
        return True
    return combined_tokens.issubset(GENERIC_TERMS)


def _detect_emerging_terms(context: SegmentContext) -> tuple[str, ...]:
    hits = [
        term
        for term in sorted(EMERGING_TERMS)
        if _contains_phrase(context.name_text, term)
        or _contains_phrase(context.alias_text, term)
        or _contains_phrase(context.description_text, term)
    ]
    return _unique_phrases(hits)


def _detect_ambiguous_terms(context: SegmentContext) -> tuple[str, ...]:
    hits = [
        phrase
        for phrase in HIGH_RISK_AMBIGUOUS_PHRASES
        if _contains_phrase(context.name_text, phrase)
        or _contains_phrase(context.alias_text, phrase)
    ]
    return _unique_phrases(hits)


def _family_conflict_reason(
    top_family: FamilyCandidate,
    second_family: FamilyCandidate | None,
) -> str | None:
    if second_family is None:
        return None
    if top_family.score <= 0:
        return None
    if second_family.score >= top_family.score - 2:
        return "multi_candidate_conflict"
    if second_family.score >= top_family.score - 4:
        return "cross_domain_segment"
    return None


def _family_fallback_proposal(
    segment: BusinessSegment,
    *,
    family_candidate: FamilyCandidate,
    rule_keys: list[str],
    review_status: str,
    review_reason: str,
    confidence: Decimal,
    comment: str,
    extra_hits: dict[str, tuple[str, ...]] | None = None,
    extra_negatives: dict[str, tuple[str, ...]] | None = None,
) -> ClassificationProposal:
    levels = _truncate_levels(
        family_candidate.family.fallback_levels,
        family_candidate.family.max_depth,
    )
    return _build_special_case_proposal(
        segment,
        review_status=review_status,
        review_reason=review_reason,
        confidence=confidence,
        comment=comment,
        levels=levels,
        rules=rule_keys,
        hits=_merge_source_phrase_maps(
            family_candidate.evidence.hits_by_source,
            extra_hits or {},
        ),
        negatives=_merge_source_phrase_maps(
            family_candidate.evidence.negatives_by_source,
            extra_negatives or {},
        ),
    )


def classify_business_segment_with_rules(
    segment: BusinessSegment,
    *,
    peer_lookup: dict[tuple[int, str | None], list[str]] | None = None,
) -> ClassificationProposal:
    evaluation = evaluate_segment_candidates(segment, peer_lookup=peer_lookup)
    context = evaluation.context

    if _is_generic_only_context(context):
        return _build_special_case_proposal(
            segment,
            review_status="needs_llm_review",
            review_reason="insufficient_description",
            confidence=Decimal("0.12"),
            comment="text too generic, require richer context",
        )

    emerging_hits = _detect_emerging_terms(context)
    if emerging_hits:
        return _build_special_case_proposal(
            segment,
            review_status="needs_llm_review",
            review_reason="emerging_business",
            confidence=Decimal("0.18"),
            comment="emerging wording detected, withheld narrow rule mapping",
            hits={"name": emerging_hits},
        )

    ambiguous_hits = _detect_ambiguous_terms(context)
    if ambiguous_hits and not evaluation.family_candidates:
        return _build_special_case_proposal(
            segment,
            review_status="needs_llm_review",
            review_reason="insufficient_description",
            confidence=Decimal("0.20"),
            comment="high-risk generic segment label without stabilizing evidence",
            hits={"name": ambiguous_hits},
        )

    if not evaluation.family_candidates:
        return _build_special_case_proposal(
            segment,
            review_status="unmapped",
            review_reason="rule_not_matched",
            confidence=Decimal("0.00"),
            comment="no stable family rule matched current text context",
        )

    top_family = evaluation.family_candidates[0]
    second_family = (
        evaluation.family_candidates[1]
        if len(evaluation.family_candidates) > 1
        else None
    )

    if ambiguous_hits and top_family.score < top_family.family.confirm_threshold:
        return _family_fallback_proposal(
            segment,
            family_candidate=top_family,
            rule_keys=[top_family.family.family],
            review_status="needs_llm_review",
            review_reason="insufficient_description",
            confidence=Decimal("0.28"),
            comment="generic boundary phrase needs deeper business-model evidence",
            extra_hits={"name": ambiguous_hits},
        )

    if not evaluation.rule_candidates:
        conflict_reason = _family_conflict_reason(top_family, second_family)
        if conflict_reason == "multi_candidate_conflict":
            return _build_special_case_proposal(
                segment,
                review_status="conflicted",
                review_reason="multi_candidate_conflict",
                confidence=Decimal("0.24"),
                comment="family gate remained cross-sector and leaf refinement was not stable",
                rules=[top_family.family.family, second_family.family.family] if second_family else [top_family.family.family],
                hits=_merge_source_phrase_maps(
                    top_family.evidence.hits_by_source,
                    second_family.evidence.hits_by_source if second_family else {},
                ),
                negatives=_merge_source_phrase_maps(
                    top_family.evidence.negatives_by_source,
                    second_family.evidence.negatives_by_source if second_family else {},
                ),
            )
        if top_family.family.fallback_levels[0] is not None:
            return _family_fallback_proposal(
                segment,
                family_candidate=top_family,
                rule_keys=[top_family.family.family],
                review_status="needs_llm_review",
                review_reason=conflict_reason or "low_confidence",
                confidence=Decimal("0.34"),
                comment="family gate passed, but no stable leaf rule was confirmed",
            )
        return _build_special_case_proposal(
            segment,
            review_status="needs_llm_review",
            review_reason=conflict_reason or "cross_domain_segment",
            confidence=Decimal("0.30"),
            comment="cross-domain platform-style segment requires richer context",
            rules=[top_family.family.family],
            hits=top_family.evidence.hits_by_source,
            negatives=top_family.evidence.negatives_by_source,
        )

    top_rule = evaluation.rule_candidates[0]
    second_rule = evaluation.rule_candidates[1] if len(evaluation.rule_candidates) > 1 else None

    if (
        second_rule is not None
        and second_rule.family_candidate.family.family != top_rule.family_candidate.family.family
        and second_rule.score >= top_rule.score - 3
    ):
        return _build_special_case_proposal(
            segment,
            review_status="conflicted",
            review_reason="multi_candidate_conflict",
            confidence=Decimal("0.26"),
            comment="multiple family candidates remained too close after leaf refinement",
            rules=[top_rule.rule.rule_key, second_rule.rule.rule_key],
            hits=_merge_source_phrase_maps(
                top_rule.family_candidate.evidence.hits_by_source,
                top_rule.evidence.hits_by_source,
                second_rule.family_candidate.evidence.hits_by_source,
                second_rule.evidence.hits_by_source,
            ),
            negatives=_merge_source_phrase_maps(
                top_rule.family_candidate.evidence.negatives_by_source,
                top_rule.evidence.negatives_by_source,
                second_rule.family_candidate.evidence.negatives_by_source,
                second_rule.evidence.negatives_by_source,
            ),
        )

    if (
        second_rule is not None
        and second_rule.family_candidate.family.family == top_rule.family_candidate.family.family
        and second_rule.score >= top_rule.score - 2
    ):
        common_levels = _common_levels(
            [top_rule.rule.gics_levels, second_rule.rule.gics_levels]
        )
        retained_levels = _truncate_levels(
            common_levels if common_levels[0] is not None else top_rule.family_candidate.family.fallback_levels,
            min(3, top_rule.family_candidate.family.max_depth),
        )
        return _build_special_case_proposal(
            segment,
            review_status="needs_llm_review",
            review_reason="multi_candidate_conflict",
            confidence=Decimal("0.38"),
            comment="same-family leaf rules competed closely, held only stable upper depth",
            levels=retained_levels,
            rules=[top_rule.rule.rule_key, second_rule.rule.rule_key],
            hits=_merge_source_phrase_maps(
                top_rule.family_candidate.evidence.hits_by_source,
                top_rule.evidence.hits_by_source,
                second_rule.evidence.hits_by_source,
            ),
            negatives=_merge_source_phrase_maps(
                top_rule.family_candidate.evidence.negatives_by_source,
                top_rule.evidence.negatives_by_source,
                second_rule.evidence.negatives_by_source,
            ),
        )

    full_levels = _truncate_levels(top_rule.rule.gics_levels, top_rule.rule.max_depth)
    merged_hits = _merge_source_phrase_maps(
        top_rule.family_candidate.evidence.hits_by_source,
        top_rule.evidence.hits_by_source,
    )
    merged_negatives = _merge_source_phrase_maps(
        top_rule.family_candidate.evidence.negatives_by_source,
        top_rule.evidence.negatives_by_source,
    )

    if top_rule.score >= top_rule.rule.confirm_threshold:
        return ClassificationProposal(
            standard_system=STANDARD_SYSTEM,
            level_1=full_levels[0],
            level_2=full_levels[1],
            level_3=full_levels[2],
            level_4=full_levels[3],
            is_primary=segment.segment_type == "primary",
            mapping_basis=_mapping_basis(
                decision="confirmed",
                rules=[top_rule.rule.rule_key],
                hits=merged_hits,
                negatives=merged_negatives,
                levels=full_levels,
            ),
            review_status="confirmed",
            classifier_type="rule_based",
            confidence=Decimal("0.94"),
            review_reason=None,
        )

    if top_rule.score >= top_rule.rule.pending_threshold:
        pending_levels = _truncate_levels(full_levels, min(3, top_rule.rule.max_depth))
        return ClassificationProposal(
            standard_system=STANDARD_SYSTEM,
            level_1=pending_levels[0],
            level_2=pending_levels[1],
            level_3=pending_levels[2],
            level_4=pending_levels[3],
            is_primary=segment.segment_type == "primary",
            mapping_basis=_mapping_basis(
                decision="pending",
                rules=[top_rule.rule.rule_key],
                hits=merged_hits,
                negatives=merged_negatives,
                levels=pending_levels,
                comment="leaf withheld for safety",
            ),
            review_status="pending",
            classifier_type="rule_based",
            confidence=Decimal("0.68"),
            review_reason="low_confidence",
        )

    llm_levels = _truncate_levels(
        top_rule.family_candidate.family.fallback_levels
        if top_rule.family_candidate.family.fallback_levels[0] is not None
        else full_levels,
        min(2, top_rule.family_candidate.family.max_depth or 2),
    )
    return _build_special_case_proposal(
        segment,
        review_status="needs_llm_review",
        review_reason="low_confidence",
        confidence=Decimal("0.36"),
        comment="family recognized but rule evidence is still too weak for stable leaf mapping",
        levels=llm_levels,
        rules=[top_rule.rule.rule_key],
        hits=merged_hits,
        negatives=merged_negatives,
    )


def _protected_segment_ids(
    db: Session,
    *,
    segment_ids: list[int] | None = None,
) -> set[int]:
    protected_types = ("manual", "llm_assisted", "hybrid")
    query = db.query(BusinessSegmentClassification.business_segment_id).filter(
        BusinessSegmentClassification.classifier_type.in_(protected_types)
    )
    if segment_ids:
        query = query.filter(BusinessSegmentClassification.business_segment_id.in_(segment_ids))
    return {row[0] for row in query.distinct().all()}


def _protected_segment_counts(
    db: Session,
    *,
    segment_ids: list[int] | None = None,
) -> dict[str, int]:
    protected_types = ("manual", "llm_assisted", "hybrid")
    query = db.query(
        BusinessSegmentClassification.classifier_type,
        BusinessSegmentClassification.business_segment_id,
    ).filter(BusinessSegmentClassification.classifier_type.in_(protected_types))
    if segment_ids:
        query = query.filter(BusinessSegmentClassification.business_segment_id.in_(segment_ids))

    distinct_pairs = {
        (classifier_type or "", business_segment_id)
        for classifier_type, business_segment_id in query.all()
    }
    manual_ids = {
        business_segment_id
        for classifier_type, business_segment_id in distinct_pairs
        if classifier_type == "manual"
    }
    llm_ids = {
        business_segment_id
        for classifier_type, business_segment_id in distinct_pairs
        if classifier_type == "llm_assisted"
    }
    hybrid_ids = {
        business_segment_id
        for classifier_type, business_segment_id in distinct_pairs
        if classifier_type == "hybrid"
    }
    protected_ids = manual_ids | llm_ids | hybrid_ids
    return {
        "skipped_protected_count": len(protected_ids),
        "skipped_manual_count": len(manual_ids),
        "skipped_llm_assisted_count": len(llm_ids),
        "skipped_hybrid_count": len(hybrid_ids),
    }


def _replace_rule_based_classification_rows(
    db: Session,
    *,
    segments: list[BusinessSegment],
    peer_lookup: dict[tuple[int, str | None], list[str]],
    segment_ids: list[int] | None = None,
) -> None:
    protected_ids = _protected_segment_ids(db, segment_ids=segment_ids)
    delete_query = db.query(BusinessSegmentClassification).filter(
        BusinessSegmentClassification.classifier_type == "rule_based"
    )
    if segment_ids:
        delete_query = delete_query.filter(
            BusinessSegmentClassification.business_segment_id.in_(segment_ids)
        )
    delete_query.delete(synchronize_session=False)

    for segment in segments:
        if segment.id in protected_ids:
            continue
        proposal = classify_business_segment_with_rules(segment, peer_lookup=peer_lookup)
        classification = BusinessSegmentClassification(
            business_segment_id=segment.id,
            **proposal.to_model_dict(),
        )
        db.add(classification)
    db.flush()


def _build_refresh_summary(
    db: Session,
    *,
    total_segments: int,
    segment_ids: list[int] | None = None,
    backup_table: str | None,
    protected_counts: dict[str, int] | None = None,
) -> BusinessSegmentClassificationRefreshSummary:
    query = db.query(BusinessSegmentClassification.review_status)
    if segment_ids:
        query = query.filter(BusinessSegmentClassification.business_segment_id.in_(segment_ids))
    rows = query.all()
    status_counts = Counter(row[0] for row in rows)
    protected_counts = protected_counts or {}
    return BusinessSegmentClassificationRefreshSummary(
        total_segments=total_segments,
        classification_rows=len(rows),
        confirmed_count=status_counts.get("confirmed", 0),
        pending_count=status_counts.get("pending", 0),
        needs_llm_review_count=status_counts.get("needs_llm_review", 0),
        needs_manual_review_count=status_counts.get("needs_manual_review", 0),
        conflicted_count=status_counts.get("conflicted", 0),
        unmapped_count=status_counts.get("unmapped", 0),
        skipped_protected_count=protected_counts.get("skipped_protected_count", 0),
        skipped_manual_count=protected_counts.get("skipped_manual_count", 0),
        skipped_llm_assisted_count=protected_counts.get("skipped_llm_assisted_count", 0),
        skipped_hybrid_count=protected_counts.get("skipped_hybrid_count", 0),
        backup_table=backup_table,
    )


def refresh_business_segment_classifications(
    db: Session,
    *,
    segment_ids: list[int] | None = None,
    create_backup: bool = False,
) -> BusinessSegmentClassificationRefreshSummary:
    query = (
        db.query(BusinessSegment)
        .options(selectinload(BusinessSegment.company))
        .order_by(BusinessSegment.id.asc())
    )
    if segment_ids:
        query = query.filter(BusinessSegment.id.in_(segment_ids))
    segments = query.all()
    peer_lookup = _build_peer_lookup(segments)
    protected_counts = _protected_segment_counts(db, segment_ids=segment_ids)

    backup_table: str | None = None
    if create_backup and segment_ids is None:
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

    _replace_rule_based_classification_rows(
        db,
        segments=segments,
        peer_lookup=peer_lookup,
        segment_ids=segment_ids,
    )
    db.commit()
    return _build_refresh_summary(
        db,
        total_segments=len(segments),
        segment_ids=segment_ids,
        backup_table=backup_table,
        protected_counts=protected_counts,
    )


def classify_business_segment_with_llm(
    db: Session,
    *,
    segment_id: int,
) -> BusinessSegmentLlmSuggestionResponse:
    segment = (
        db.query(BusinessSegment)
        .options(
            selectinload(BusinessSegment.company),
            selectinload(BusinessSegment.classifications),
        )
        .filter(BusinessSegment.id == segment_id)
        .first()
    )
    if segment is None:
        raise LookupError("Business segment not found.")

    peer_lookup = _build_peer_lookup(
        db.query(BusinessSegment)
        .filter(BusinessSegment.company_id == segment.company_id)
        .order_by(BusinessSegment.id.asc())
        .all()
    )
    evaluation = evaluate_segment_candidates(segment, peer_lookup=peer_lookup)

    current_classification = _get_current_classification(db, segment_id=segment_id)

    top_rule_keys = [candidate.rule.rule_key for candidate in evaluation.rule_candidates[:3]]
    request_context = BusinessSegmentLlmRequestContext(
        company_name=segment.company.name if segment.company else None,
        company_description=segment.company.description if segment.company else None,
        segment_name=segment.segment_name,
        segment_alias=segment.segment_alias,
        description=segment.description,
        segment_type=segment.segment_type,
        reporting_period=segment.reporting_period,
        company_text=evaluation.context.company_text or None,
        peer_text=evaluation.context.peer_text or None,
        rule_candidates=top_rule_keys,
    )

    if not any(
        [
            normalize_optional_text(segment.segment_name),
            normalize_optional_text(segment.segment_alias),
            normalize_optional_text(segment.description),
        ]
    ):
        raise ValueError(
            "Business segment context is too incomplete for LLM classification."
        )

    messages = _build_llm_messages(
        segment=segment,
        current_classification=current_classification,
        evaluation=evaluation,
    )
    llm_result = DeepSeekChatClient().create_chat_completion(messages=messages)

    try:
        suggestion = _build_llm_suggestion_from_content(
            content=llm_result.content,
            segment=segment,
        )
        status_value = "success"
        message = "DeepSeek suggestion generated successfully."
    except ValueError as exc:
        logger.warning(
            "DeepSeek returned non-JSON or invalid JSON for segment %s: %s",
            segment_id,
            exc,
        )
        suggestion = _build_llm_parse_fallback_suggestion(
            segment=segment,
            raw_content=llm_result.content,
        )
        status_value = "fallback"
        message = (
            "DeepSeek returned a non-standard response. A conservative fallback "
            "suggestion was generated for manual review."
        )

    return BusinessSegmentLlmSuggestionResponse(
        segment_id=segment_id,
        status=status_value,
        message=message,
        current_classification=current_classification,
        suggested_classification=suggestion,
        request_context=request_context,
    )


def _select_confirmation_target_row(
    rows: list[BusinessSegmentClassification],
) -> BusinessSegmentClassification | None:
    if not rows:
        return None
    return sorted(
        rows,
        key=lambda row: (
            not row.is_primary,
            row.classifier_type != "llm_assisted",
            row.classifier_type != "rule_based",
            row.id,
        ),
    )[0]


def _serialize_classification_snapshot(
    classification: BusinessSegmentClassification | BusinessSegmentClassificationRead | None,
) -> str | None:
    if classification is None:
        return None
    if isinstance(classification, BusinessSegmentClassification):
        return serialize_model_snapshot(classification)
    return json.dumps(
        classification.model_dump(),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _serialize_classification_summary(
    classification: BusinessSegmentClassification | BusinessSegmentClassificationRead | None,
) -> str | None:
    if classification is None:
        return None
    payload = {
        "business_segment_id": classification.business_segment_id,
        "standard_system": classification.standard_system,
        "level_1": classification.level_1,
        "level_2": classification.level_2,
        "level_3": classification.level_3,
        "level_4": classification.level_4,
        "industry_label": _build_label_from_levels(classification),
        "is_primary": classification.is_primary,
        "classifier_type": classification.classifier_type,
        "review_status": classification.review_status,
        "review_reason": classification.review_reason,
        "confidence": classification.confidence,
        "mapping_basis": classification.mapping_basis,
    }
    if hasattr(classification, "id"):
        payload["classification_id"] = getattr(classification, "id")
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def confirm_business_segment_llm_classification(
    db: Session,
    *,
    segment_id: int,
    suggested_classification: BusinessSegmentClassificationSuggestionRead,
    reason: str | None = None,
    operator: str | None = "api",
) -> BusinessSegmentLlmConfirmationResponse:
    segment = (
        db.query(BusinessSegment)
        .options(selectinload(BusinessSegment.classifications))
        .filter(BusinessSegment.id == segment_id)
        .first()
    )
    if segment is None:
        raise LookupError("Business segment not found.")

    current_rows = get_business_segment_classifications_by_segment_id(
        db,
        business_segment_id=segment_id,
    )
    previous_current = _get_current_classification(db, segment_id=segment_id)
    previous_current_snapshot = _serialize_classification_snapshot(previous_current)
    target_row = _select_confirmation_target_row(current_rows)
    removed_classification_ids = [
        row.id for row in current_rows if target_row is None or row.id != target_row.id
    ]
    annotation_reason = normalize_optional_text(reason) or "llm_suggested"
    previous_target_snapshot = serialize_model_snapshot(target_row)

    if target_row is None:
        target_row = BusinessSegmentClassification(business_segment_id=segment_id)
        db.add(target_row)

    target_row.standard_system = suggested_classification.standard_system
    target_row.level_1 = suggested_classification.level_1
    target_row.level_2 = suggested_classification.level_2
    target_row.level_3 = suggested_classification.level_3
    target_row.level_4 = suggested_classification.level_4
    target_row.is_primary = suggested_classification.is_primary
    target_row.mapping_basis = suggested_classification.mapping_basis
    target_row.review_status = "confirmed"
    target_row.classifier_type = "llm_assisted"
    target_row.confidence = suggested_classification.confidence
    target_row.review_reason = "llm_suggested"
    db.flush()

    for row in current_rows:
        if row.id == target_row.id:
            continue
        create_annotation_log(
            db,
            target_type="business_segment_classification",
            target_id=row.id,
            action_type="delete",
            old_value=serialize_model_snapshot(row),
            new_value=None,
            reason=annotation_reason,
            operator=operator,
        )
        db.delete(row)

    new_target_snapshot = serialize_model_snapshot(target_row)
    create_annotation_log(
        db,
        target_type="business_segment_classification",
        target_id=target_row.id,
        action_type="confirm_llm",
        old_value=previous_target_snapshot,
        new_value=new_target_snapshot,
        reason=annotation_reason,
        operator=operator,
    )
    create_annotation_log(
        db,
        target_type="business_segment",
        target_id=segment_id,
        action_type="confirm_llm",
        old_value=previous_current_snapshot,
        new_value=new_target_snapshot,
        reason=annotation_reason,
        operator=operator,
    )
    db.commit()
    db.refresh(target_row)

    return BusinessSegmentLlmConfirmationResponse(
        segment_id=segment_id,
        status="confirmed",
        message="LLM suggestion has been adopted as the formal classification result.",
        previous_classification=previous_current,
        confirmed_classification=BusinessSegmentClassificationRead.model_validate(
            target_row
        ),
        removed_classification_ids=removed_classification_ids,
        annotation_action="confirm_llm",
    )


def confirm_business_segment_manual_classification(
    db: Session,
    *,
    segment_id: int,
    manual_classification: BusinessSegmentManualClassificationRequest,
    operator: str | None = "api",
) -> BusinessSegmentManualClassificationResponse:
    segment = (
        db.query(BusinessSegment)
        .options(selectinload(BusinessSegment.classifications))
        .filter(BusinessSegment.id == segment_id)
        .first()
    )
    if segment is None:
        raise LookupError("Business segment not found.")

    levels = [
        manual_classification.level_1,
        manual_classification.level_2,
        manual_classification.level_3,
        manual_classification.level_4,
    ]
    if not any(levels):
        raise ValueError("At least one classification level must be provided.")

    annotation_reason = normalize_optional_text(manual_classification.mapping_basis)
    if annotation_reason is None:
        raise ValueError("Manual classification reason is required.")

    current_rows = get_business_segment_classifications_by_segment_id(
        db,
        business_segment_id=segment_id,
    )
    previous_current = _get_current_classification(db, segment_id=segment_id)
    previous_current_summary = _serialize_classification_summary(previous_current)

    target_row = next(
        (row for row in current_rows if row.classifier_type == "manual"),
        None,
    )
    if target_row is None:
        target_row = _select_confirmation_target_row(current_rows)

    removed_classification_ids = [
        row.id for row in current_rows if target_row is None or row.id != target_row.id
    ]
    previous_target_summary = _serialize_classification_summary(target_row)

    if target_row is None:
        target_row = BusinessSegmentClassification(business_segment_id=segment_id)
        db.add(target_row)

    target_row.standard_system = manual_classification.standard_system
    target_row.level_1 = manual_classification.level_1
    target_row.level_2 = manual_classification.level_2
    target_row.level_3 = manual_classification.level_3
    target_row.level_4 = manual_classification.level_4
    target_row.is_primary = (
        manual_classification.is_primary
        if manual_classification.is_primary is not None
        else segment.segment_type == "primary"
    )
    target_row.mapping_basis = annotation_reason
    target_row.review_status = "confirmed"
    target_row.classifier_type = "manual"
    target_row.confidence = manual_classification.confidence or Decimal("1.0")
    target_row.review_reason = (
        "manual_confirmed"
        if manual_classification.mark_as_final
        else "manual_override"
    )
    db.flush()

    for row in current_rows:
        if row.id == target_row.id:
            continue
        create_annotation_log(
            db,
            target_type="business_segment_classification",
            target_id=row.id,
            action_type="delete",
            old_value=_serialize_classification_summary(row),
            new_value=None,
            reason=annotation_reason,
            operator=operator,
        )
        db.delete(row)

    new_target_summary = _serialize_classification_summary(target_row)
    create_annotation_log(
        db,
        target_type="business_segment_classification",
        target_id=target_row.id,
        action_type="manual_override",
        old_value=previous_target_summary or previous_current_summary,
        new_value=new_target_summary,
        reason=annotation_reason,
        operator=operator,
    )
    create_annotation_log(
        db,
        target_type="business_segment",
        target_id=segment_id,
        action_type="manual_override",
        old_value=previous_current_summary,
        new_value=new_target_summary,
        reason=annotation_reason,
        operator=operator,
    )
    db.commit()
    db.refresh(target_row)

    return BusinessSegmentManualClassificationResponse(
        segment_id=segment_id,
        status="confirmed",
        message="Manual classification has been written back as the formal current result.",
        previous_classification=previous_current,
        confirmed_classification=BusinessSegmentClassificationRead.model_validate(
            target_row
        ),
        removed_classification_ids=removed_classification_ids,
        annotation_action="manual_override",
    )


def _get_current_classification(
    db: Session,
    *,
    segment_id: int,
) -> BusinessSegmentClassificationRead | None:
    current_rows = get_business_segment_classifications_by_segment_id(
        db,
        business_segment_id=segment_id,
    )
    if not current_rows:
        return None
    return BusinessSegmentClassificationRead.model_validate(current_rows[0])


def _truncate_text(value: str | None, *, limit: int = 320) -> str | None:
    normalized = normalize_optional_text(value)
    if normalized is None:
        return None
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."


def _format_ratio(value: Decimal | None) -> str | None:
    if value is None:
        return None
    numeric = Decimal(value)
    normalized = numeric * Decimal("100") if numeric <= 1 else numeric
    return f"{normalized.quantize(Decimal('0.01'))}%"


def _build_label_from_levels(
    classification: BusinessSegmentClassification | BusinessSegmentClassificationRead,
) -> str | None:
    levels = [
        normalize_optional_text(classification.level_1),
        normalize_optional_text(classification.level_2),
        normalize_optional_text(classification.level_3),
        normalize_optional_text(classification.level_4),
    ]
    filtered_levels = [value for value in levels if value]
    return " > ".join(filtered_levels) if filtered_levels else None


def _build_peer_segment_payload(
    segment: BusinessSegment,
) -> list[dict[str, Any]]:
    if segment.company is None:
        return []

    peers: list[dict[str, Any]] = []
    for peer in segment.company.business_segments:
        if peer.id == segment.id:
            continue
        peers.append(
            {
                "segment_name": peer.segment_name,
                "segment_alias": peer.segment_alias,
                "segment_type": peer.segment_type,
                "reporting_period": peer.reporting_period,
                "industry_labels": [
                    label
                    for label in (
                        _build_label_from_levels(classification)
                        for classification in peer.classifications
                    )
                    if label is not None
                ][:2],
            }
        )
        if len(peers) >= 6:
            break
    return peers


def _serialize_classification_for_prompt(
    classification: BusinessSegmentClassificationRead | None,
) -> dict[str, Any] | None:
    if classification is None:
        return None
    return {
        "standard_system": classification.standard_system,
        "level_1": classification.level_1,
        "level_2": classification.level_2,
        "level_3": classification.level_3,
        "level_4": classification.level_4,
        "industry_label": classification.industry_label,
        "is_primary": classification.is_primary,
        "confidence": (
            float(classification.confidence)
            if classification.confidence is not None
            else None
        ),
        "classifier_type": classification.classifier_type,
        "review_status": classification.review_status,
        "review_reason": classification.review_reason,
        "mapping_basis": _truncate_text(classification.mapping_basis, limit=220),
    }


def _build_llm_messages(
    *,
    segment: BusinessSegment,
    current_classification: BusinessSegmentClassificationRead | None,
    evaluation: RuleEvaluation,
) -> list[dict[str, str]]:
    company = segment.company
    user_payload = {
        "classification_task": {
            "standard_system": STANDARD_SYSTEM,
            "goal": (
                "Map the target business segment into the current system's industry "
                "classification hierarchy."
            ),
            "conservative_policy": (
                "If evidence is not strong enough, keep deeper levels null instead "
                "of forcing a detailed mapping."
            ),
        },
        "company_context": {
            "company_name": company.name if company else None,
            "company_description": _truncate_text(
                company.description if company else None,
                limit=320,
            ),
            "incorporation_country": company.incorporation_country if company else None,
            "listing_country": company.listing_country if company else None,
            "headquarters": company.headquarters if company else None,
        },
        "business_segment": {
            "segment_id": segment.id,
            "segment_name": segment.segment_name,
            "segment_alias": segment.segment_alias,
            "description": _truncate_text(segment.description, limit=480),
            "segment_type": segment.segment_type,
            "reporting_period": segment.reporting_period,
            "revenue_ratio": _format_ratio(segment.revenue_ratio),
            "profit_ratio": _format_ratio(segment.profit_ratio),
            "currency": segment.currency,
            "source": segment.source,
        },
        "current_rule_result": _serialize_classification_for_prompt(
            current_classification
        ),
        "rule_reference": {
            "top_rule_candidates": [
                candidate.rule.rule_key
                for candidate in evaluation.rule_candidates[:3]
            ],
            "company_text": _truncate_text(evaluation.context.company_text, limit=220),
            "peer_text": _truncate_text(evaluation.context.peer_text, limit=220),
        },
        "peer_segments": _build_peer_segment_payload(segment),
        "required_output_schema": {
            "standard_system": "GICS",
            "level_1": "string or null",
            "level_2": "string or null",
            "level_3": "string or null",
            "level_4": "string or null",
            "is_primary": segment.segment_type == "primary",
            "confidence": "number between 0 and 1",
            "mapping_basis": "short concrete human-readable explanation",
            "review_status": (
                "one of confirmed, pending, needs_llm_review, "
                "needs_manual_review, conflicted, unmapped"
            ),
            "classifier_type": "llm_assisted",
            "review_reason": "short snake_case string",
        },
    }

    system_message = (
        "You are assisting an industry analysis system. Your task is to map one "
        "business segment to the industry's hierarchical classification used by "
        "this system, defaulting to GICS. Be conservative: if the evidence is "
        "weak or ambiguous, do not over-specify deeper levels. Use current "
        "rule-based output only as a reference, not as mandatory truth. Return "
        "only one JSON object and no extra commentary. mapping_basis must be "
        "brief, concrete, and understandable by a human reviewer."
    )

    return [
        {"role": "system", "content": system_message},
        {
            "role": "user",
            "content": json.dumps(
                user_payload,
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]


def _extract_json_object(content: str) -> dict[str, Any]:
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = re.sub(r"^```(?:json)?\s*", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\s*```$", "", normalized)

    candidates = [normalized]
    start_index = normalized.find("{")
    end_index = normalized.rfind("}")
    if start_index != -1 and end_index != -1 and end_index > start_index:
        candidates.append(normalized[start_index : end_index + 1])

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("DeepSeek response JSON root must be an object.")

    raise ValueError("DeepSeek response did not contain valid JSON.") from last_error


def _normalize_confidence(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        normalized = Decimal(str(value).strip())
    except Exception as exc:
        raise ValueError("Model confidence is not a valid number.") from exc
    if normalized > 1 and normalized <= 100:
        normalized = normalized / Decimal("100")
    if normalized < 0 or normalized > 1:
        raise ValueError("Model confidence must be between 0 and 1.")
    return normalized.quantize(Decimal("0.0001"))


def _normalize_levels(
    payload: dict[str, Any],
) -> tuple[str | None, str | None, str | None, str | None]:
    levels = [
        normalize_optional_text(payload.get("level_1")),
        normalize_optional_text(payload.get("level_2")),
        normalize_optional_text(payload.get("level_3")),
        normalize_optional_text(payload.get("level_4")),
    ]
    first_gap_seen = False
    for index, level in enumerate(levels):
        if level is None:
            first_gap_seen = True
            continue
        if first_gap_seen:
            for clear_index in range(index, len(levels)):
                levels[clear_index] = None
            break
    return tuple(levels)  # type: ignore[return-value]


def _normalize_review_status_for_llm(
    value: Any,
    *,
    has_any_level: bool,
) -> str:
    normalized = None
    if isinstance(value, str) and value.strip():
        normalized = normalize_classification_review_status(value)
    if normalized is not None:
        return normalized
    return "needs_manual_review" if has_any_level else "unmapped"


def _build_llm_suggestion_from_content(
    *,
    content: str,
    segment: BusinessSegment,
) -> BusinessSegmentClassificationSuggestionRead:
    payload = _extract_json_object(content)
    levels = _normalize_levels(payload)
    has_any_level = any(levels)
    mapping_basis = normalize_optional_text(payload.get("mapping_basis"))
    review_reason = normalize_optional_text(payload.get("review_reason")) or (
        "llm_suggested" if has_any_level else "llm_inconclusive"
    )
    review_status = _normalize_review_status_for_llm(
        payload.get("review_status"),
        has_any_level=has_any_level,
    )
    classifier_type = normalize_classifier_type(payload.get("classifier_type"))
    if classifier_type is None:
        classifier_type = "llm_assisted"
    standard_system = normalize_standard_system(payload.get("standard_system"))

    return BusinessSegmentClassificationSuggestionRead(
        standard_system=standard_system,
        level_1=levels[0],
        level_2=levels[1],
        level_3=levels[2],
        level_4=levels[3],
        is_primary=bool(payload.get("is_primary", segment.segment_type == "primary")),
        mapping_basis=(
            mapping_basis
            or (
                "LLM suggested a conservative classification based on the segment "
                "description and company context."
                if has_any_level
                else "LLM could not derive a stable mapping from the available context."
            )
        ),
        review_status=review_status,
        classifier_type=classifier_type,
        confidence=_normalize_confidence(payload.get("confidence")),
        review_reason=review_reason,
    )


def _build_llm_parse_fallback_suggestion(
    *,
    segment: BusinessSegment,
    raw_content: str,
) -> BusinessSegmentClassificationSuggestionRead:
    compact_content = _truncate_text(raw_content, limit=160)
    mapping_basis = "LLM returned a non-JSON response, so the suggestion was downgraded for manual review."
    if compact_content:
        mapping_basis = f"{mapping_basis} Response summary: {compact_content}"

    return BusinessSegmentClassificationSuggestionRead(
        standard_system=STANDARD_SYSTEM,
        level_1=None,
        level_2=None,
        level_3=None,
        level_4=None,
        is_primary=segment.segment_type == "primary",
        mapping_basis=mapping_basis,
        review_status="needs_manual_review",
        classifier_type="llm_assisted",
        confidence=Decimal("0.1000"),
        review_reason="llm_response_parse_failed",
    )
