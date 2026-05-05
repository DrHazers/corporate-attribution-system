from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session, joinedload

from backend.analysis.control_chain import analyze_control_chain_with_options
from backend.analysis.manual_control_override import (
    get_current_effective_country_attribution_data,
)
from backend.analysis.ownership_penetration import get_company_country_attribution_data
from backend.crud.annotation_log import (
    deserialize_model_snapshot,
    get_annotation_logs_by_target,
)
from backend.crud.business_segment import (
    get_business_segment_by_id,
    get_business_segments_by_company_id,
    get_business_segments_by_company_id_and_period,
    get_company_reporting_periods,
)
from backend.crud.business_segment_classification import (
    get_business_segment_classification_by_id,
)
from backend.crud.company import get_company_by_id
from backend.models.annotation_log import AnnotationLog
from backend.models.business_segment import BusinessSegment
from backend.models.business_segment_classification import BusinessSegmentClassification
from backend.schemas.business_segment_classification import (
    build_industry_label_from_levels,
)
from backend.schemas.company import CompanyRead


MANUAL_REVIEW_STATUSES = {
    "confirmed",
    "needs_manual_review",
}

SEGMENT_TYPE_LABELS = {
    "primary": "主营",
    "secondary": "补充",
    "emerging": "新兴",
    "other": "其他",
}

SEGMENT_TYPE_SOURCE_LABELS = {
    "suggested_by_ratio": "系统根据收入和利润贡献推断",
    "suggested_by_growth": "系统根据历史增长推断",
    "input_consistent": "输入标签与系统建议一致",
    "input_conflict": "输入标签与系统建议不一致",
    "insufficient_data": "数据不足，暂按其他处理",
    "insufficient_input_use_inferred": "未提供业务类型，使用系统建议",
}


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.strip().lower().split())


def _normalize_reporting_period(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _reporting_period_sort_key(period: str | None) -> tuple[int, int, int, int, int, str]:
    normalized = _normalize_reporting_period(period)
    if normalized is None:
        return (0, 0, 0, 0, 0, "")

    upper_value = normalized.upper()

    date_match = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", upper_value)
    if date_match:
        return (
            5,
            int(date_match.group(1)),
            int(date_match.group(2)),
            int(date_match.group(3)),
            0,
            upper_value,
        )

    quarter_match = re.fullmatch(r"(\d{4})[-/]?Q([1-4])", upper_value)
    if quarter_match:
        return (
            4,
            int(quarter_match.group(1)),
            int(quarter_match.group(2)),
            0,
            0,
            upper_value,
        )

    half_match = re.fullmatch(r"(\d{4})[-/]?H([1-2])", upper_value)
    if half_match:
        return (
            3,
            int(half_match.group(1)),
            int(half_match.group(2)),
            0,
            0,
            upper_value,
        )

    year_match = re.fullmatch(r"(\d{4})", upper_value)
    if year_match:
        return (2, int(year_match.group(1)), 0, 0, 0, upper_value)

    numeric_parts = [int(item) for item in re.findall(r"\d+", upper_value)[:4]]
    while len(numeric_parts) < 4:
        numeric_parts.append(0)
    return (
        1,
        numeric_parts[0],
        numeric_parts[1],
        numeric_parts[2],
        numeric_parts[3],
        upper_value,
    )


def _sort_reporting_periods(periods: list[str]) -> list[str]:
    unique_periods: list[str] = []
    seen: set[str] = set()

    for period in periods:
        normalized = _normalize_reporting_period(period)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        unique_periods.append(normalized)

    return sorted(unique_periods, key=_reporting_period_sort_key, reverse=True)


def _unique_preserving_order(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _build_industry_label(
    classification: BusinessSegmentClassification,
) -> str | None:
    return build_industry_label_from_levels(
        level_1=classification.level_1,
        level_2=classification.level_2,
        level_3=classification.level_3,
        level_4=classification.level_4,
    )


def build_classification_summary(
    classification: BusinessSegmentClassification,
) -> dict[str, Any]:
    return {
        "id": classification.id,
        "business_segment_id": classification.business_segment_id,
        "standard_system": classification.standard_system,
        "level_1": classification.level_1,
        "level_2": classification.level_2,
        "level_3": classification.level_3,
        "level_4": classification.level_4,
        "industry_label": _build_industry_label(classification),
        "is_primary": classification.is_primary,
        "mapping_basis": classification.mapping_basis,
        "review_status": classification.review_status,
        "classifier_type": classification.classifier_type,
        "confidence": classification.confidence,
        "review_reason": classification.review_reason,
        "created_at": classification.created_at,
        "updated_at": classification.updated_at,
    }


def _numeric_ratio(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0:
        return None
    return numeric / 100 if numeric > 1 else numeric


def _rank_lookup(
    rows: list[tuple[int, float]],
) -> dict[int, int]:
    ranked_rows = sorted(rows, key=lambda item: (-item[1], item[0]))
    return {segment_id: index + 1 for index, (segment_id, _) in enumerate(ranked_rows)}


def _previous_same_name_segment(
    segment: BusinessSegment,
    all_segments: list[BusinessSegment],
) -> BusinessSegment | None:
    current_period = _normalize_reporting_period(segment.reporting_period)
    if current_period is None:
        return None
    current_key = _reporting_period_sort_key(current_period)
    normalized_name = _normalize_text(segment.segment_name)
    candidates = [
        candidate
        for candidate in all_segments
        if candidate.company_id == segment.company_id
        and candidate.id != segment.id
        and _normalize_text(candidate.segment_name) == normalized_name
        and _normalize_reporting_period(candidate.reporting_period) is not None
        and _reporting_period_sort_key(candidate.reporting_period) < current_key
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda candidate: _reporting_period_sort_key(candidate.reporting_period),
    )


def _build_segment_type_inferences(
    segments: list[BusinessSegment],
    all_segments: list[BusinessSegment],
) -> dict[int, dict[str, Any]]:
    revenue_values = {
        segment.id: _numeric_ratio(segment.revenue_ratio)
        for segment in segments
    }
    profit_values = {
        segment.id: _numeric_ratio(segment.profit_ratio)
        for segment in segments
    }
    contribution_scores = {
        segment.id: 0.6 * (revenue_values[segment.id] or 0) + 0.4 * (profit_values[segment.id] or 0)
        for segment in segments
    }
    revenue_ranks = _rank_lookup(
        [(segment.id, revenue_values[segment.id] or 0) for segment in segments]
    )
    profit_ranks = _rank_lookup(
        [(segment.id, profit_values[segment.id] or 0) for segment in segments]
    )
    contribution_ranks = _rank_lookup(
        [(segment.id, contribution_scores[segment.id]) for segment in segments]
    )

    inferences: dict[int, dict[str, Any]] = {}
    for segment in segments:
        revenue_ratio = revenue_values[segment.id]
        profit_ratio = profit_values[segment.id]
        contribution_score = contribution_scores[segment.id]
        revenue_rank = revenue_ranks.get(segment.id)
        profit_rank = profit_ranks.get(segment.id)
        contribution_rank = contribution_ranks.get(segment.id)
        previous_segment = _previous_same_name_segment(segment, all_segments)
        previous_revenue_ratio = (
            _numeric_ratio(previous_segment.revenue_ratio) if previous_segment else None
        )
        previous_profit_ratio = (
            _numeric_ratio(previous_segment.profit_ratio) if previous_segment else None
        )
        revenue_change = (
            revenue_ratio - previous_revenue_ratio
            if revenue_ratio is not None and previous_revenue_ratio is not None
            else None
        )
        profit_change = (
            profit_ratio - previous_profit_ratio
            if profit_ratio is not None and previous_profit_ratio is not None
            else None
        )

        has_ratio_data = revenue_ratio is not None or profit_ratio is not None
        is_primary_candidate = (
            contribution_rank == 1 and contribution_score >= 0.35
        ) or (
            revenue_rank == 1 and (revenue_ratio or 0) >= 0.40
        ) or (
            profit_rank == 1 and (profit_ratio or 0) >= 0.40
        )
        is_emerging_candidate = (
            previous_segment is not None
            and ((revenue_ratio is not None and revenue_ratio < 0.15) or (profit_ratio is not None and profit_ratio < 0.15))
            and ((revenue_change is not None and revenue_change >= 0.05) or (profit_change is not None and profit_change >= 0.05))
        )
        is_secondary_candidate = (
            not is_primary_candidate
            and ((revenue_ratio or 0) >= 0.10 or (profit_ratio or 0) >= 0.10)
        )

        if is_primary_candidate:
            inferred_type = "primary"
            inference_reason_source = "suggested_by_ratio"
        elif is_emerging_candidate:
            inferred_type = "emerging"
            inference_reason_source = "suggested_by_growth"
        elif is_secondary_candidate:
            inferred_type = "secondary"
            inference_reason_source = "suggested_by_ratio"
        else:
            inferred_type = "other"
            inference_reason_source = "suggested_by_ratio" if has_ratio_data else "insufficient_data"

        input_type = _normalize_text(segment.segment_type)
        inferred_label = SEGMENT_TYPE_LABELS[inferred_type]
        input_label = SEGMENT_TYPE_LABELS.get(input_type, input_type or "")
        if not input_type:
            segment_type_source = "insufficient_input_use_inferred"
            warning = "未提供业务类型，当前展示为系统建议结果。"
        elif input_type == inferred_type:
            segment_type_source = "input_consistent"
            warning = None
        else:
            segment_type_source = "input_conflict"
            warning = f"输入业务类型为{input_label}，但系统根据收入和利润贡献建议标记为{inferred_label}。"

        inferences[segment.id] = {
            "inferred_segment_type": inferred_type,
            "inferred_segment_type_label": inferred_label,
            "segment_type_source": segment_type_source,
            "segment_type_warning": warning,
            "segment_type_evidence": {
                "revenue_ratio": revenue_ratio,
                "profit_ratio": profit_ratio,
                "contribution_score": contribution_score,
                "revenue_rank": revenue_rank,
                "profit_rank": profit_rank,
                "contribution_rank": contribution_rank,
                "previous_reporting_period": previous_segment.reporting_period if previous_segment else None,
                "previous_revenue_ratio": previous_revenue_ratio,
                "previous_profit_ratio": previous_profit_ratio,
                "revenue_change": revenue_change,
                "profit_change": profit_change,
                "inference_source": inference_reason_source,
                "inference_source_label": SEGMENT_TYPE_SOURCE_LABELS[inference_reason_source],
            },
        }

    return inferences


def _classification_labels(segment: BusinessSegment) -> list[str]:
    labels: list[str] = []
    for classification in segment.classifications:
        label = _build_industry_label(classification)
        if label is None or label in labels:
            continue
        labels.append(label)
    return labels


def _segment_primary_industry_labels(segment: BusinessSegment) -> list[str]:
    primary_labels: list[str] = []
    fallback_labels: list[str] = []

    for classification in segment.classifications:
        label = _build_industry_label(classification)
        if label is None:
            continue
        if classification.is_primary and label not in primary_labels:
            primary_labels.append(label)
        if segment.segment_type == "primary" and label not in fallback_labels:
            fallback_labels.append(label)

    return primary_labels or fallback_labels


def build_business_segment_detail(
    segment: BusinessSegment,
    segment_type_inference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    classification_summaries = [
        build_classification_summary(classification)
        for classification in segment.classifications
    ]
    return {
        "id": segment.id,
        "company_id": segment.company_id,
        "segment_name": segment.segment_name,
        "segment_alias": segment.segment_alias,
        "segment_type": _normalize_text(segment.segment_type) or None,
        "revenue_ratio": segment.revenue_ratio,
        "profit_ratio": segment.profit_ratio,
        "description": segment.description,
        "currency": segment.currency,
        "source": segment.source,
        "reporting_period": segment.reporting_period,
        "is_current": segment.is_current,
        "confidence": segment.confidence,
        "classification_labels": _classification_labels(segment),
        "classifications": classification_summaries,
        "inferred_segment_type": (
            segment_type_inference or {}
        ).get("inferred_segment_type"),
        "inferred_segment_type_label": (
            segment_type_inference or {}
        ).get("inferred_segment_type_label"),
        "segment_type_source": (
            segment_type_inference or {}
        ).get("segment_type_source"),
        "segment_type_warning": (
            segment_type_inference or {}
        ).get("segment_type_warning"),
        "segment_type_evidence": (
            segment_type_inference or {}
        ).get("segment_type_evidence", {}),
        "created_at": segment.created_at,
        "updated_at": segment.updated_at,
    }


def _build_business_segment_headline(
    segment: BusinessSegment,
    segment_type_inference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": segment.id,
        "segment_name": segment.segment_name,
        "segment_alias": segment.segment_alias,
        "segment_type": _normalize_text(segment.segment_type) or None,
        "revenue_ratio": segment.revenue_ratio,
        "profit_ratio": segment.profit_ratio,
        "currency": segment.currency,
        "reporting_period": segment.reporting_period,
        "is_current": segment.is_current,
        "confidence": segment.confidence,
        "classification_labels": _classification_labels(segment),
        "inferred_segment_type": (
            segment_type_inference or {}
        ).get("inferred_segment_type"),
        "inferred_segment_type_label": (
            segment_type_inference or {}
        ).get("inferred_segment_type_label"),
        "segment_type_source": (
            segment_type_inference or {}
        ).get("segment_type_source"),
        "segment_type_warning": (
            segment_type_inference or {}
        ).get("segment_type_warning"),
        "segment_type_evidence": (
            segment_type_inference or {}
        ).get("segment_type_evidence", {}),
    }


def _select_effective_segments(
    segments: list[BusinessSegment],
    *,
    include_inactive: bool,
) -> list[BusinessSegment]:
    if include_inactive:
        return list(segments)

    current_segments = [segment for segment in segments if segment.is_current]
    if current_segments:
        return current_segments
    return list(segments)


def _select_default_reporting_period(
    all_segments: list[BusinessSegment],
    available_reporting_periods: list[str],
) -> str | None:
    current_periods = _sort_reporting_periods(
        [
            normalized_period
            for segment in all_segments
            if segment.is_current
            for normalized_period in [_normalize_reporting_period(segment.reporting_period)]
            if normalized_period is not None
        ]
    )
    if current_periods:
        return current_periods[0]

    if any(
        segment.is_current and _normalize_reporting_period(segment.reporting_period) is None
        for segment in all_segments
    ):
        return None

    if available_reporting_periods:
        return available_reporting_periods[0]

    return None


def _segments_for_reporting_period(
    all_segments: list[BusinessSegment],
    reporting_period: str | None,
) -> list[BusinessSegment]:
    return [
        segment
        for segment in all_segments
        if _normalize_reporting_period(segment.reporting_period) == reporting_period
    ]


def _resolve_industry_analysis_context(
    db: Session,
    company_id: int,
    *,
    reporting_period: str | None = None,
    with_classifications: bool = True,
) -> dict[str, Any]:
    normalized_reporting_period = _normalize_reporting_period(reporting_period)
    if reporting_period is not None and normalized_reporting_period is None:
        raise ValueError("reporting_period must not be blank.")

    all_segments = get_business_segments_by_company_id(
        db,
        company_id=company_id,
        include_inactive=True,
        with_classifications=with_classifications,
    )
    available_reporting_periods = _sort_reporting_periods(
        get_company_reporting_periods(
            db,
            company_id=company_id,
        )
    )
    latest_reporting_period = (
        available_reporting_periods[0] if available_reporting_periods else None
    )

    if normalized_reporting_period is not None:
        selected_reporting_period = normalized_reporting_period
        selected_candidates = _segments_for_reporting_period(
            all_segments,
            normalized_reporting_period,
        )
        if not selected_candidates:
            raise LookupError(
                f"Industry analysis data not found for reporting_period '{normalized_reporting_period}'."
            )
    else:
        selected_reporting_period = _select_default_reporting_period(
            all_segments,
            available_reporting_periods,
        )
        selected_candidates = _segments_for_reporting_period(
            all_segments,
            selected_reporting_period,
        )

    return {
        "all_segments": all_segments,
        "available_reporting_periods": available_reporting_periods,
        "latest_reporting_period": latest_reporting_period,
        "selected_reporting_period": selected_reporting_period,
        "selected_candidates": selected_candidates,
    }


def _segment_names_by_condition(
    segments: list[BusinessSegment],
    predicate,
) -> list[str]:
    return _unique_preserving_order(
        [segment.segment_name for segment in segments if predicate(segment)]
    )


def _duplicate_segment_names(
    segments: list[BusinessSegment],
) -> list[str]:
    names_by_key: dict[str, list[str]] = defaultdict(list)
    for segment in segments:
        names_by_key[_normalize_text(segment.segment_name)].append(segment.segment_name)

    duplicate_names: list[str] = []
    for normalized_name, original_names in names_by_key.items():
        if not normalized_name or len(original_names) < 2:
            continue
        duplicate_names.append(original_names[0])
    return _unique_preserving_order(duplicate_names)


def _build_quality_assessment(
    *,
    company_id: int,
    selected_reporting_period: str | None,
    segments: list[BusinessSegment],
) -> dict[str, Any]:
    duplicate_segment_names = _duplicate_segment_names(segments)
    segments_without_classifications = _segment_names_by_condition(
        segments,
        lambda segment: not segment.classifications,
    )
    primary_segments_without_classifications = _segment_names_by_condition(
        segments,
        lambda segment: segment.segment_type == "primary" and not segment.classifications,
    )
    segments_with_multiple_primary_classifications = _segment_names_by_condition(
        segments,
        lambda segment: sum(1 for item in segment.classifications if item.is_primary) > 1,
    )

    has_primary_segment = any(segment.segment_type == "primary" for segment in segments)
    has_classifications = any(segment.classifications for segment in segments)
    has_conflicting_primary_classification = bool(
        segments_with_multiple_primary_classifications
    )

    warnings: list[str] = []
    if not segments:
        warnings.append("No business segments found for the selected reporting period.")
    if not has_primary_segment:
        warnings.append("No primary segment found for selected reporting period.")
    if segments_without_classifications:
        warnings.append(
            f"{len(segments_without_classifications)} segment(s) do not have classification mappings."
        )
    if primary_segments_without_classifications:
        warnings.append(
            f"{len(primary_segments_without_classifications)} primary segment(s) do not have classification mappings."
        )
    if duplicate_segment_names:
        warnings.append(
            "Duplicate segment names detected: "
            + ", ".join(duplicate_segment_names)
        )
    if has_conflicting_primary_classification:
        warnings.append(
            "Conflicting primary classifications detected for: "
            + ", ".join(segments_with_multiple_primary_classifications)
        )

    return {
        "company_id": company_id,
        "selected_reporting_period": selected_reporting_period,
        "has_primary_segment": has_primary_segment,
        "has_classifications": has_classifications,
        "duplicate_segment_names": duplicate_segment_names,
        "segments_without_classifications": segments_without_classifications,
        "primary_segments_without_classifications": primary_segments_without_classifications,
        "segments_with_multiple_primary_classifications": (
            segments_with_multiple_primary_classifications
        ),
        "warnings": warnings,
        "quality_summary": {
            "duplicate_segment_count": len(duplicate_segment_names),
            "segments_without_classification_count": len(
                segments_without_classifications
            ),
            "primary_segments_without_classification_count": len(
                primary_segments_without_classifications
            ),
            "has_conflicting_primary_classification": (
                has_conflicting_primary_classification
            ),
        },
    }


def _augment_quality_with_segment_type_inferences(
    quality_assessment: dict[str, Any],
    segment_type_inferences: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    quality_summary = {
        **quality_assessment["quality_summary"],
        "segment_type_conflict_count": sum(
            1
            for inference in segment_type_inferences.values()
            if inference.get("segment_type_source") == "input_conflict"
        ),
        "segment_type_inferred_without_input_count": sum(
            1
            for inference in segment_type_inferences.values()
            if inference.get("segment_type_source")
            == "insufficient_input_use_inferred"
        ),
    }
    warnings = list(quality_assessment["warnings"])
    if quality_summary["segment_type_conflict_count"]:
        warnings.append(
            f"{quality_summary['segment_type_conflict_count']} segment(s) have input business type conflicting with system suggestion."
        )
    if quality_summary["segment_type_inferred_without_input_count"]:
        warnings.append(
            f"{quality_summary['segment_type_inferred_without_input_count']} segment(s) do not provide business type; system suggestion is shown."
        )
    return {
        **quality_assessment,
        "warnings": warnings,
        "quality_summary": quality_summary,
    }


def _build_history_item(
    company_id: int,
    reporting_period: str,
    segments: list[BusinessSegment],
) -> dict[str, Any]:
    effective_segments = _select_effective_segments(
        segments,
        include_inactive=False,
    )
    analysis = _build_industry_analysis_payload(
        company_id=company_id,
        segments=effective_segments,
        all_segments=segments,
        selected_reporting_period=reporting_period,
        available_reporting_periods=[],
        latest_reporting_period=reporting_period,
        history_items=[],
    )
    return {
        "reporting_period": reporting_period,
        "business_segment_count": analysis["business_segment_count"],
        "primary_industries": analysis["primary_industries"],
        "primary_segments_count": len(analysis["primary_segments"]),
        "emerging_segments_count": len(analysis["emerging_segments"]),
    }


def _build_industry_analysis_payload(
    *,
    company_id: int,
    segments: list[BusinessSegment],
    all_segments: list[BusinessSegment] | None = None,
    selected_reporting_period: str | None,
    available_reporting_periods: list[str],
    latest_reporting_period: str | None,
    history_items: list[dict[str, Any]],
) -> dict[str, Any]:
    categorized_segments: dict[str, list[dict[str, Any]]] = {
        "primary": [],
        "secondary": [],
        "emerging": [],
        "other": [],
    }
    primary_industries: list[str] = []
    fallback_primary_industries: list[str] = []
    all_industry_labels: list[str] = []
    has_manual_adjustment = False
    has_classifications = False
    has_revenue_ratio = False
    detailed_segments: list[dict[str, Any]] = []
    segment_type_inferences = _build_segment_type_inferences(
        segments,
        all_segments or segments,
    )

    for segment in segments:
        segment_type_inference = segment_type_inferences.get(segment.id, {})
        segment_detail = build_business_segment_detail(
            segment,
            segment_type_inference=segment_type_inference,
        )
        detailed_segments.append(segment_detail)
        segment_category_type = (
            _normalize_text(segment.segment_type)
            or segment_type_inference.get("inferred_segment_type")
            or "other"
        )
        categorized_segments.setdefault(segment_category_type, []).append(
            _build_business_segment_headline(
                segment,
                segment_type_inference=segment_type_inference,
            )
        )

        if segment.classifications:
            has_classifications = True
        if segment.revenue_ratio is not None:
            has_revenue_ratio = True

        for classification in segment.classifications:
            label = _build_industry_label(classification)
            if label and label not in all_industry_labels:
                all_industry_labels.append(label)
            if classification.review_status in MANUAL_REVIEW_STATUSES:
                has_manual_adjustment = True
            if label and classification.is_primary and label not in primary_industries:
                primary_industries.append(label)
            if (
                label
                and segment_category_type == "primary"
                and label not in fallback_primary_industries
            ):
                fallback_primary_industries.append(label)

    resolved_primary_industries = primary_industries or fallback_primary_industries
    quality_assessment = _build_quality_assessment(
        company_id=company_id,
        selected_reporting_period=selected_reporting_period,
        segments=segments,
    )
    quality_assessment = _augment_quality_with_segment_type_inferences(
        quality_assessment,
        segment_type_inferences,
    )

    return {
        "company_id": company_id,
        "selected_reporting_period": selected_reporting_period,
        "available_reporting_periods": available_reporting_periods,
        "latest_reporting_period": latest_reporting_period,
        "business_segment_count": len(segments),
        "primary_segments": categorized_segments["primary"],
        "secondary_segments": categorized_segments["secondary"],
        "emerging_segments": categorized_segments["emerging"],
        "other_segments": categorized_segments["other"],
        "primary_industries": resolved_primary_industries,
        "all_industry_labels": all_industry_labels,
        "has_manual_adjustment": has_manual_adjustment,
        "data_completeness": {
            "has_primary_segment": bool(categorized_segments["primary"]),
            "has_classifications": has_classifications,
            "has_revenue_ratio": has_revenue_ratio,
            "has_manual_adjustment": has_manual_adjustment,
        },
        "structure_flags": {
            "is_multi_segment": len(segments) > 1,
            "has_emerging_segment": bool(categorized_segments["emerging"]),
            "has_secondary_segment": bool(categorized_segments["secondary"]),
            "has_primary_industry_mapping": bool(resolved_primary_industries),
        },
        "quality_warnings": quality_assessment["warnings"],
        "quality_summary": quality_assessment["quality_summary"],
        "segments": detailed_segments,
        "history": history_items,
    }


def get_company_industry_analysis(
    db: Session,
    company_id: int,
    *,
    include_inactive: bool = False,
    reporting_period: str | None = None,
    include_history: bool = False,
) -> dict[str, Any]:
    context = _resolve_industry_analysis_context(
        db,
        company_id,
        reporting_period=reporting_period,
        with_classifications=True,
    )

    selected_segments = _select_effective_segments(
        context["selected_candidates"],
        include_inactive=include_inactive,
    )

    history_items: list[dict[str, Any]] = []
    if include_history:
        for history_period in context["available_reporting_periods"]:
            if history_period == context["selected_reporting_period"]:
                continue
            period_segments = _segments_for_reporting_period(
                context["all_segments"],
                history_period,
            )
            if not period_segments:
                continue
            history_items.append(
                _build_history_item(
                    company_id,
                    history_period,
                    period_segments,
                )
            )

    return _build_industry_analysis_payload(
        company_id=company_id,
        segments=selected_segments,
        all_segments=context["all_segments"],
        selected_reporting_period=context["selected_reporting_period"],
        available_reporting_periods=context["available_reporting_periods"],
        latest_reporting_period=context["latest_reporting_period"],
        history_items=history_items,
    )


def get_company_industry_analysis_periods(
    db: Session,
    company_id: int,
) -> dict[str, Any]:
    context = _resolve_industry_analysis_context(
        db,
        company_id,
        with_classifications=False,
    )
    return {
        "company_id": company_id,
        "available_reporting_periods": context["available_reporting_periods"],
        "latest_reporting_period": context["latest_reporting_period"],
        "current_reporting_period": context["selected_reporting_period"],
        "period_count": len(context["available_reporting_periods"]),
    }


def get_company_industry_analysis_quality(
    db: Session,
    company_id: int,
    *,
    reporting_period: str | None = None,
) -> dict[str, Any]:
    context = _resolve_industry_analysis_context(
        db,
        company_id,
        reporting_period=reporting_period,
        with_classifications=True,
    )
    selected_segments = _select_effective_segments(
        context["selected_candidates"],
        include_inactive=False,
    )
    quality_assessment = _build_quality_assessment(
        company_id=company_id,
        selected_reporting_period=context["selected_reporting_period"],
        segments=selected_segments,
    )
    return _augment_quality_with_segment_type_inferences(
        quality_assessment,
        _build_segment_type_inferences(
            selected_segments,
            context["all_segments"],
        ),
    )


def _select_primary_classification(
    segment: BusinessSegment,
) -> BusinessSegmentClassification | None:
    primary_classification = next(
        (
            classification
            for classification in segment.classifications
            if classification.is_primary
        ),
        None,
    )
    return primary_classification or (
        segment.classifications[0] if segment.classifications else None
    )


def _ratio_change(
    earliest: BusinessSegment,
    latest: BusinessSegment,
    field_name: str,
) -> float | None:
    earliest_value = getattr(earliest, field_name)
    latest_value = getattr(latest, field_name)
    if earliest_value is None or latest_value is None:
        return None
    return float(latest_value) - float(earliest_value)


def get_business_segment_history(
    db: Session,
    *,
    company_id: int,
    segment_id: int,
) -> dict[str, Any]:
    segment = get_business_segment_by_id(db, segment_id)
    if segment is None or segment.company_id != company_id:
        raise LookupError("Business segment not found.")

    normalized_segment_name = segment.segment_name.strip()
    history_segments = (
        db.query(BusinessSegment)
        .options(joinedload(BusinessSegment.classifications))
        .filter(BusinessSegment.company_id == company_id)
        .filter(BusinessSegment.segment_name == normalized_segment_name)
        .order_by(BusinessSegment.id.asc())
        .all()
    )
    history_segments = sorted(
        history_segments,
        key=lambda item: _reporting_period_sort_key(item.reporting_period),
    )
    history_inferences = _build_segment_type_inferences(
        history_segments,
        get_business_segments_by_company_id(
            db,
            company_id=company_id,
            include_inactive=True,
            with_classifications=False,
        ),
    )

    available_reporting_periods = _sort_reporting_periods(
        [
            reporting_period
            for item in history_segments
            for reporting_period in [_normalize_reporting_period(item.reporting_period)]
            if reporting_period is not None
        ]
    )

    items: list[dict[str, Any]] = []
    classification_labels: list[str | None] = []
    for history_segment in history_segments:
        classification = _select_primary_classification(history_segment)
        classification_summary = (
            build_classification_summary(classification) if classification else None
        )
        classification_labels.append(
            classification_summary["industry_label"] if classification_summary else None
        )
        items.append(
            {
                "business_segment_id": history_segment.id,
                "reporting_period": history_segment.reporting_period,
                "segment_name": history_segment.segment_name,
                "segment_type": history_segment.segment_type,
                "revenue_ratio": history_segment.revenue_ratio,
                "profit_ratio": history_segment.profit_ratio,
                "source": history_segment.source,
                "confidence": history_segment.confidence,
                "description": history_segment.description,
                "classification": classification_summary,
                **history_inferences.get(history_segment.id, {}),
            }
        )

    earliest_segment = history_segments[0] if history_segments else None
    latest_segment = history_segments[-1] if history_segments else None
    unique_classification_labels = {
        label
        for label in classification_labels
        if label is not None
    }

    return {
        "company_id": company_id,
        "business_segment_id": segment.id,
        "segment_name": segment.segment_name,
        "available_reporting_periods": available_reporting_periods,
        "items": items,
        "trend_summary": {
            "history_count": len(items),
            "latest_reporting_period": (
                available_reporting_periods[0] if available_reporting_periods else None
            ),
            "revenue_change": (
                _ratio_change(earliest_segment, latest_segment, "revenue_ratio")
                if earliest_segment is not None and latest_segment is not None
                else None
            ),
            "profit_change": (
                _ratio_change(earliest_segment, latest_segment, "profit_ratio")
                if earliest_segment is not None and latest_segment is not None
                else None
            ),
            "classification_changed": len(unique_classification_labels) > 1,
        },
    }


def _serialize_annotation_log(log: AnnotationLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "action_type": log.action_type,
        "old_value": deserialize_model_snapshot(log.old_value),
        "new_value": deserialize_model_snapshot(log.new_value),
        "reason": log.reason,
        "operator": log.operator,
        "created_at": log.created_at,
    }


def get_business_segment_annotation_logs(
    db: Session,
    segment_id: int,
) -> dict[str, Any]:
    segment = get_business_segment_by_id(db, segment_id)
    if segment is None:
        raise LookupError("Business segment not found.")

    logs = get_annotation_logs_by_target(
        db,
        target_type="business_segment",
        target_id=segment_id,
    )
    return {
        "target_type": "business_segment",
        "target_id": segment_id,
        "segment": build_business_segment_detail(segment),
        "classification": None,
        "annotation_logs": [_serialize_annotation_log(log) for log in logs],
        "total_count": len(logs),
    }


def get_business_segment_classification_annotation_logs(
    db: Session,
    classification_id: int,
) -> dict[str, Any]:
    classification = get_business_segment_classification_by_id(db, classification_id)
    if classification is None:
        raise LookupError("Business segment classification not found.")

    logs = get_annotation_logs_by_target(
        db,
        target_type="business_segment_classification",
        target_id=classification_id,
    )
    return {
        "target_type": "business_segment_classification",
        "target_id": classification_id,
        "segment": None,
        "classification": build_classification_summary(classification),
        "annotation_logs": [_serialize_annotation_log(log) for log in logs],
        "total_count": len(logs),
    }


def _build_change_segment_item(
    record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "segment_name": record["segment_name"],
        "segment_type": record["segment_type"],
        "classification_labels": list(record["classification_labels"]),
        "reporting_period": record["reporting_period"],
        "is_current": record["is_current"],
    }


def _build_change_transition_item(
    *,
    current_record: dict[str, Any],
    previous_record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "segment_name": current_record["segment_name"],
        "previous_segment_type": previous_record["segment_type"],
        "current_segment_type": current_record["segment_type"],
        "previous_classification_labels": list(previous_record["classification_labels"]),
        "current_classification_labels": list(current_record["classification_labels"]),
        "previous_reporting_period": previous_record["reporting_period"],
        "current_reporting_period": current_record["reporting_period"],
    }


def _extract_primary_industries_from_records(
    records: list[dict[str, Any]],
) -> list[str]:
    primary_industries: list[str] = []
    fallback_primary_industries: list[str] = []

    for record in records:
        for label in record["primary_industries"]:
            if label not in primary_industries:
                primary_industries.append(label)
        if record["segment_type"] == "primary":
            for label in record["classification_labels"]:
                if label not in fallback_primary_industries:
                    fallback_primary_industries.append(label)

    return primary_industries or fallback_primary_industries


def _segment_record(segment: BusinessSegment) -> dict[str, Any]:
    return {
        "segment_id": segment.id,
        "segment_name": segment.segment_name,
        "segment_name_key": _normalize_text(segment.segment_name),
        "segment_type": segment.segment_type,
        "classification_labels": tuple(_classification_labels(segment)),
        "primary_industries": tuple(_segment_primary_industry_labels(segment)),
        "reporting_period": _normalize_reporting_period(segment.reporting_period),
        "is_current": segment.is_current,
    }


def _match_score(
    current_record: dict[str, Any],
    previous_record: dict[str, Any],
) -> tuple[int, int, int]:
    current_labels = {
        _normalize_text(label) for label in current_record["classification_labels"]
    }
    previous_labels = {
        _normalize_text(label) for label in previous_record["classification_labels"]
    }
    current_primary_labels = {
        _normalize_text(label) for label in current_record["primary_industries"]
    }
    previous_primary_labels = {
        _normalize_text(label) for label in previous_record["primary_industries"]
    }
    classification_overlap = len(current_labels & previous_labels)
    primary_overlap = len(current_primary_labels & previous_primary_labels)
    same_segment_type = int(
        current_record["segment_type"] == previous_record["segment_type"]
    )
    return (classification_overlap, primary_overlap, same_segment_type)


def _match_records(
    current_records: list[dict[str, Any]],
    previous_records: list[dict[str, Any]],
) -> tuple[
    list[tuple[dict[str, Any], dict[str, Any]]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    previous_buckets: dict[str, list[int]] = defaultdict(list)
    for previous_index, previous_record in enumerate(previous_records):
        previous_buckets[previous_record["segment_name_key"]].append(previous_index)

    matched_previous_indices: set[int] = set()
    matched_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    unmatched_current: list[dict[str, Any]] = []

    for current_record in current_records:
        candidate_indices = [
            previous_index
            for previous_index in previous_buckets.get(
                current_record["segment_name_key"], []
            )
            if previous_index not in matched_previous_indices
        ]
        if not candidate_indices:
            unmatched_current.append(current_record)
            continue

        best_previous_index = max(
            candidate_indices,
            key=lambda previous_index: _match_score(
                current_record,
                previous_records[previous_index],
            ),
        )
        matched_previous_indices.add(best_previous_index)
        matched_pairs.append((current_record, previous_records[best_previous_index]))

    unmatched_previous = [
        previous_record
        for previous_index, previous_record in enumerate(previous_records)
        if previous_index not in matched_previous_indices
    ]
    return matched_pairs, unmatched_current, unmatched_previous


def _build_change_summary(
    *,
    previous_primary_industries: list[str],
    current_primary_industries: list[str],
    primary_industry_changed: bool,
    new_segments: list[dict[str, Any]],
    removed_segments: list[dict[str, Any]],
    promoted_to_primary: list[dict[str, Any]],
    demoted_from_primary: list[dict[str, Any]],
    new_emerging_segments: list[dict[str, Any]],
    removed_emerging_segments: list[dict[str, Any]],
) -> str:
    summary_parts: list[str] = []

    if primary_industry_changed:
        previous_label = ", ".join(previous_primary_industries) or "unmapped"
        current_label = ", ".join(current_primary_industries) or "unmapped"
        if previous_primary_industries and current_primary_industries:
            summary_parts.append(
                f"Primary industry shifted from {previous_label} to {current_label}"
            )
        elif current_primary_industries:
            summary_parts.append(f"Primary industry updated to {current_label}")
        else:
            summary_parts.append(
                f"Primary industry mapping changed from {previous_label} to unmapped"
            )

    if new_segments:
        new_summary = f"Added {len(new_segments)} segment(s)"
        if new_emerging_segments:
            new_summary += (
                f", including {len(new_emerging_segments)} emerging segment(s)"
            )
        summary_parts.append(new_summary)

    if removed_segments:
        removed_summary = f"Removed {len(removed_segments)} segment(s)"
        if removed_emerging_segments:
            removed_summary += (
                f", including {len(removed_emerging_segments)} emerging segment(s)"
            )
        summary_parts.append(removed_summary)

    for transition in promoted_to_primary:
        summary_parts.append(
            f"{transition['segment_name']} moved from "
            f"{transition['previous_segment_type']} to primary"
        )

    for transition in demoted_from_primary:
        summary_parts.append(
            f"{transition['segment_name']} moved from primary to "
            f"{transition['current_segment_type']}"
        )

    if not summary_parts:
        return "No significant industry structure change detected."

    return "; ".join(summary_parts)


def analyze_industry_structure_change(
    company_id: int,
    current_period: str,
    previous_period: str,
    session: Session,
) -> dict[str, Any]:
    normalized_current_period = _normalize_reporting_period(current_period)
    normalized_previous_period = _normalize_reporting_period(previous_period)

    if normalized_current_period is None or normalized_previous_period is None:
        raise ValueError("current_period and previous_period must not be blank.")
    if normalized_current_period == normalized_previous_period:
        raise ValueError("current_period and previous_period must be different.")

    available_reporting_periods = _sort_reporting_periods(
        get_company_reporting_periods(
            session,
            company_id=company_id,
        )
    )
    for period in [normalized_current_period, normalized_previous_period]:
        if period not in available_reporting_periods:
            raise LookupError(
                f"Industry analysis data not found for reporting_period '{period}'."
            )

    current_segments = get_business_segments_by_company_id_and_period(
        session,
        company_id=company_id,
        reporting_period=normalized_current_period,
        include_inactive=True,
        with_classifications=True,
    )
    previous_segments = get_business_segments_by_company_id_and_period(
        session,
        company_id=company_id,
        reporting_period=normalized_previous_period,
        include_inactive=True,
        with_classifications=True,
    )

    current_records = [
        _segment_record(segment)
        for segment in _select_effective_segments(
            current_segments,
            include_inactive=False,
        )
    ]
    previous_records = [
        _segment_record(segment)
        for segment in _select_effective_segments(
            previous_segments,
            include_inactive=False,
        )
    ]

    matched_pairs, unmatched_current, unmatched_previous = _match_records(
        current_records,
        previous_records,
    )

    promoted_to_primary = [
        _build_change_transition_item(
            current_record=current_record,
            previous_record=previous_record,
        )
        for current_record, previous_record in matched_pairs
        if previous_record["segment_type"] != "primary"
        and current_record["segment_type"] == "primary"
    ]
    demoted_from_primary = [
        _build_change_transition_item(
            current_record=current_record,
            previous_record=previous_record,
        )
        for current_record, previous_record in matched_pairs
        if previous_record["segment_type"] == "primary"
        and current_record["segment_type"] != "primary"
    ]

    new_segments = [_build_change_segment_item(record) for record in unmatched_current]
    removed_segments = [
        _build_change_segment_item(record) for record in unmatched_previous
    ]
    new_emerging_segments = [
        _build_change_segment_item(record)
        for record in unmatched_current
        if record["segment_type"] == "emerging"
    ]
    removed_emerging_segments = [
        _build_change_segment_item(record)
        for record in unmatched_previous
        if record["segment_type"] == "emerging"
    ]

    current_primary_industries = _extract_primary_industries_from_records(current_records)
    previous_primary_industries = _extract_primary_industries_from_records(
        previous_records
    )
    primary_industry_changed = set(current_primary_industries) != set(
        previous_primary_industries
    )

    return {
        "company_id": company_id,
        "current_period": normalized_current_period,
        "previous_period": normalized_previous_period,
        "new_segments": new_segments,
        "removed_segments": removed_segments,
        "promoted_to_primary": promoted_to_primary,
        "demoted_from_primary": demoted_from_primary,
        "new_emerging_segments": new_emerging_segments,
        "removed_emerging_segments": removed_emerging_segments,
        "primary_industry_changed": primary_industry_changed,
        "previous_primary_industries": previous_primary_industries,
        "current_primary_industries": current_primary_industries,
        "change_summary": _build_change_summary(
            previous_primary_industries=previous_primary_industries,
            current_primary_industries=current_primary_industries,
            primary_industry_changed=primary_industry_changed,
            new_segments=new_segments,
            removed_segments=removed_segments,
            promoted_to_primary=promoted_to_primary,
            demoted_from_primary=demoted_from_primary,
            new_emerging_segments=new_emerging_segments,
            removed_emerging_segments=removed_emerging_segments,
        ),
    }


def get_company_analysis_summary(
    db: Session,
    company_id: int,
) -> dict[str, Any]:
    company = get_company_by_id(db, company_id)
    if company is None:
        raise ValueError("Company not found.")

    control_analysis = analyze_control_chain_with_options(
        db,
        company_id,
        refresh=False,
    )
    country_attribution = get_current_effective_country_attribution_data(db, company_id)
    automatic_control_analysis = analyze_control_chain_with_options(
        db,
        company_id,
        refresh=False,
        result_layer="auto",
    )
    automatic_country_attribution = get_company_country_attribution_data(db, company_id)
    industry_analysis = get_company_industry_analysis(db, company_id)

    return {
        "company": CompanyRead.model_validate(company).model_dump(),
        "control_analysis": {
            "company_id": company_id,
            "controller_count": control_analysis["controller_count"],
            "direct_controller": control_analysis.get("direct_controller"),
            "actual_controller": control_analysis["actual_controller"],
            "leading_candidate": control_analysis.get("leading_candidate"),
            "focused_candidate": control_analysis.get("focused_candidate"),
            "display_controller": control_analysis.get("display_controller"),
            "display_controller_role": control_analysis.get("display_controller_role"),
            "identification_status": control_analysis.get("identification_status"),
            "controller_status": control_analysis.get("controller_status"),
            "control_relationships": control_analysis["control_relationships"],
            "result_layer": control_analysis.get("result_layer"),
            "result_source": control_analysis.get("result_source"),
            "source_type": control_analysis.get("source_type"),
            "manual_label": control_analysis.get("manual_label"),
            "is_manual_effective": control_analysis.get("is_manual_effective", False),
            "manual_override": control_analysis.get("manual_override"),
        },
        "country_attribution": country_attribution,
        "automatic_control_analysis": automatic_control_analysis,
        "automatic_country_attribution": automatic_country_attribution,
        "manual_override": control_analysis.get("manual_override")
        or country_attribution.get("manual_override"),
        "industry_analysis": industry_analysis,
    }
