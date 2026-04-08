from __future__ import annotations

from sqlalchemy.orm import Session

from backend.analysis.control_chain import analyze_control_chain_with_options
from backend.crud.business_segment import get_business_segments_by_company_id
from backend.crud.company import get_company_by_id
from backend.models.business_segment import BusinessSegment
from backend.models.business_segment_classification import BusinessSegmentClassification
from backend.analysis.ownership_penetration import get_company_country_attribution_data
from backend.schemas.company import CompanyRead


MANUAL_REVIEW_STATUSES = {
    "manual_confirmed",
    "manual_adjusted",
}


def _build_industry_label(
    classification: BusinessSegmentClassification,
) -> str | None:
    levels = [
        value.strip()
        for value in [
            classification.level_1,
            classification.level_2,
            classification.level_3,
            classification.level_4,
        ]
        if value and value.strip()
    ]
    if not levels:
        return None
    return " > ".join(levels)


def build_classification_summary(
    classification: BusinessSegmentClassification,
) -> dict:
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
        "created_at": classification.created_at,
        "updated_at": classification.updated_at,
    }


def _classification_labels(
    segment: BusinessSegment,
) -> list[str]:
    labels = []
    for classification in segment.classifications:
        label = _build_industry_label(classification)
        if label is None or label in labels:
            continue
        labels.append(label)
    return labels


def build_business_segment_detail(
    segment: BusinessSegment,
) -> dict:
    classification_summaries = [
        build_classification_summary(classification)
        for classification in segment.classifications
    ]
    return {
        "id": segment.id,
        "company_id": segment.company_id,
        "segment_name": segment.segment_name,
        "segment_type": segment.segment_type,
        "revenue_ratio": segment.revenue_ratio,
        "profit_ratio": segment.profit_ratio,
        "description": segment.description,
        "source": segment.source,
        "reporting_period": segment.reporting_period,
        "is_current": segment.is_current,
        "confidence": segment.confidence,
        "classification_labels": _classification_labels(segment),
        "classifications": classification_summaries,
        "created_at": segment.created_at,
        "updated_at": segment.updated_at,
    }


def _build_business_segment_headline(
    segment: BusinessSegment,
) -> dict:
    return {
        "id": segment.id,
        "segment_name": segment.segment_name,
        "segment_type": segment.segment_type,
        "revenue_ratio": segment.revenue_ratio,
        "profit_ratio": segment.profit_ratio,
        "reporting_period": segment.reporting_period,
        "is_current": segment.is_current,
        "confidence": segment.confidence,
        "classification_labels": _classification_labels(segment),
    }


def get_company_industry_analysis(
    db: Session,
    company_id: int,
    *,
    include_inactive: bool = False,
) -> dict:
    segments = get_business_segments_by_company_id(
        db,
        company_id=company_id,
        include_inactive=include_inactive,
        with_classifications=True,
    )

    categorized_segments = {
        "primary": [],
        "secondary": [],
        "emerging": [],
        "other": [],
    }
    primary_industries: list[str] = []
    fallback_primary_industries: list[str] = []
    all_industry_labels: list[str] = []
    has_manual_adjustment = False
    detailed_segments = []

    for segment in segments:
        segment_detail = build_business_segment_detail(segment)
        detailed_segments.append(segment_detail)
        categorized_segments[segment.segment_type].append(
            _build_business_segment_headline(segment)
        )

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
                and segment.segment_type == "primary"
                and label not in fallback_primary_industries
            ):
                fallback_primary_industries.append(label)

    return {
        "company_id": company_id,
        "business_segment_count": len(segments),
        "primary_segments": categorized_segments["primary"],
        "secondary_segments": categorized_segments["secondary"],
        "emerging_segments": categorized_segments["emerging"],
        "other_segments": categorized_segments["other"],
        "primary_industries": primary_industries or fallback_primary_industries,
        "all_industry_labels": all_industry_labels,
        "has_manual_adjustment": has_manual_adjustment,
        "segments": detailed_segments,
    }


def get_company_analysis_summary(
    db: Session,
    company_id: int,
) -> dict:
    company = get_company_by_id(db, company_id)
    if company is None:
        raise ValueError("Company not found.")

    control_analysis = analyze_control_chain_with_options(
        db,
        company_id,
        refresh=False,
    )
    country_attribution = get_company_country_attribution_data(db, company_id)
    industry_analysis = get_company_industry_analysis(db, company_id)

    return {
        "company": CompanyRead.model_validate(company).model_dump(),
        "control_analysis": {
            "company_id": company_id,
            "controller_count": control_analysis["controller_count"],
            "actual_controller": control_analysis["actual_controller"],
            "control_relationships": control_analysis["control_relationships"],
        },
        "country_attribution": country_attribution,
        "industry_analysis": industry_analysis,
    }
