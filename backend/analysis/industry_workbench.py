from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.analysis.industry_classification import (
    _build_llm_messages,
    _build_llm_parse_fallback_suggestion,
    _build_llm_suggestion_from_content,
    _build_peer_lookup,
    classify_business_segment_with_rules,
    evaluate_segment_candidates,
)
from backend.models.business_segment import BusinessSegment
from backend.models.company import Company
from backend.schemas.business_segment_classification import (
    BusinessSegmentClassificationRead,
    BusinessSegmentLlmRequestContext,
    normalize_optional_text,
)
from backend.schemas.industry_workbench import (
    IndustryWorkbenchAnalysisRequest,
    IndustryWorkbenchClassificationRead,
    IndustryWorkbenchLlmAnalysisResponse,
    IndustryWorkbenchLlmSegmentResult,
    IndustryWorkbenchRuleAnalysisResponse,
    IndustryWorkbenchSegmentRead,
)
from backend.services.llm.deepseek_client import DeepSeekChatClient


WORKBENCH_COMPANY_ID = 0
WORKBENCH_SOURCE = "temporary-workbench"
WORKBENCH_DEFAULT_REPORTING_PERIOD = "Temporary Analysis"


def _build_workbench_company(
    request: IndustryWorkbenchAnalysisRequest,
) -> tuple[Company, list[BusinessSegment], dict[int, str]]:
    company = Company(
        id=WORKBENCH_COMPANY_ID,
        name=request.company_name,
        stock_code="WORKBENCH",
        incorporation_country="Unknown",
        listing_country="Unknown",
        headquarters="Workbench",
        description=request.company_description,
    )

    segments: list[BusinessSegment] = []
    local_id_by_numeric_id: dict[int, str] = {}
    for index, segment_in in enumerate(request.segments, start=1):
        local_id = segment_in.local_id or f"workbench-segment-{index}"
        local_id_by_numeric_id[index] = local_id
        segment = BusinessSegment(
            id=index,
            company_id=WORKBENCH_COMPANY_ID,
            segment_name=segment_in.segment_name,
            segment_alias=segment_in.segment_alias,
            segment_type=segment_in.segment_type,
            revenue_ratio=segment_in.revenue_ratio,
            profit_ratio=segment_in.profit_ratio,
            description=segment_in.description,
            source=WORKBENCH_SOURCE,
            reporting_period=(
                segment_in.reporting_period or WORKBENCH_DEFAULT_REPORTING_PERIOD
            ),
            is_current=True,
        )
        segment.company = company
        segments.append(segment)

    company.business_segments = segments
    return company, segments, local_id_by_numeric_id


def _workbench_classification_id(*, local_id: str, source: str) -> str:
    return f"{local_id}-{source}"


def _workbench_classification_from_values(
    *,
    local_id: str,
    standard_system: str,
    level_1: str | None,
    level_2: str | None,
    level_3: str | None,
    level_4: str | None,
    is_primary: bool,
    mapping_basis: str | None,
    review_status: str | None,
    classifier_type: str | None,
    confidence: Decimal | None,
    review_reason: str | None,
) -> IndustryWorkbenchClassificationRead:
    source = "llm" if classifier_type == "llm_assisted" else "rule"
    return IndustryWorkbenchClassificationRead(
        id=_workbench_classification_id(local_id=local_id, source=source),
        business_segment_id=local_id,
        standard_system=standard_system,
        level_1=level_1,
        level_2=level_2,
        level_3=level_3,
        level_4=level_4,
        is_primary=is_primary,
        mapping_basis=mapping_basis,
        review_status=review_status,
        classifier_type=classifier_type,
        confidence=confidence,
        review_reason=review_reason,
    )


def _prompt_classification_from_workbench(
    *,
    numeric_segment_id: int,
    classification: IndustryWorkbenchClassificationRead,
) -> BusinessSegmentClassificationRead:
    now = datetime.utcnow()
    return BusinessSegmentClassificationRead(
        id=numeric_segment_id,
        business_segment_id=numeric_segment_id,
        standard_system=classification.standard_system,
        level_1=classification.level_1,
        level_2=classification.level_2,
        level_3=classification.level_3,
        level_4=classification.level_4,
        is_primary=classification.is_primary,
        mapping_basis=classification.mapping_basis,
        review_status=classification.review_status,
        classifier_type=classification.classifier_type,
        confidence=classification.confidence,
        review_reason=classification.review_reason,
        created_at=now,
        updated_at=now,
    )


def _segment_read(
    *,
    segment: BusinessSegment,
    local_id: str,
    classification: IndustryWorkbenchClassificationRead,
) -> IndustryWorkbenchSegmentRead:
    return IndustryWorkbenchSegmentRead(
        id=local_id,
        local_id=local_id,
        segment_name=segment.segment_name,
        segment_alias=segment.segment_alias,
        segment_type=segment.segment_type,
        revenue_ratio=segment.revenue_ratio,
        profit_ratio=segment.profit_ratio,
        description=segment.description,
        reporting_period=segment.reporting_period,
        source=WORKBENCH_SOURCE,
        is_current=True,
        confidence=classification.confidence,
        classifications=[classification],
        classification_labels=[classification.industry_label]
        if classification.industry_label
        else [],
    )


def _quality_warnings_from_segments(
    segments: list[IndustryWorkbenchSegmentRead],
) -> list[str]:
    statuses = Counter(
        (
            segment.classifications[0].review_status
            if segment.classifications
            else None
        )
        for segment in segments
    )
    if any(
        statuses.get(status, 0) > 0
        for status in (
            "pending",
            "needs_llm_review",
            "needs_manual_review",
            "conflicted",
            "unmapped",
        )
    ):
        return [
            "当前结果包含待补判、冲突或未映射业务线，建议结合模型建议或人工判断继续研究。"
        ]
    return []


def _build_rule_analysis_from_request(
    request: IndustryWorkbenchAnalysisRequest,
) -> tuple[
    IndustryWorkbenchRuleAnalysisResponse,
    list[BusinessSegment],
    dict[int, str],
    dict[int, IndustryWorkbenchClassificationRead],
    dict[int, BusinessSegmentClassificationRead],
]:
    _, segments, local_id_by_numeric_id = _build_workbench_company(request)
    peer_lookup = _build_peer_lookup(segments)

    segment_reads: list[IndustryWorkbenchSegmentRead] = []
    workbench_rule_map: dict[int, IndustryWorkbenchClassificationRead] = {}
    prompt_rule_map: dict[int, BusinessSegmentClassificationRead] = {}

    for segment in segments:
        proposal = classify_business_segment_with_rules(segment, peer_lookup=peer_lookup)
        local_id = local_id_by_numeric_id[segment.id]
        classification = _workbench_classification_from_values(
            local_id=local_id,
            standard_system=proposal.standard_system,
            level_1=proposal.level_1,
            level_2=proposal.level_2,
            level_3=proposal.level_3,
            level_4=proposal.level_4,
            is_primary=proposal.is_primary,
            mapping_basis=proposal.mapping_basis,
            review_status=proposal.review_status,
            classifier_type=proposal.classifier_type,
            confidence=proposal.confidence,
            review_reason=proposal.review_reason,
        )
        prompt_classification = _prompt_classification_from_workbench(
            numeric_segment_id=segment.id,
            classification=classification,
        )
        workbench_rule_map[segment.id] = classification
        prompt_rule_map[segment.id] = prompt_classification
        segment_reads.append(
            _segment_read(
                segment=segment,
                local_id=local_id,
                classification=classification,
            )
        )

    primary_industries = [
        label
        for label in dict.fromkeys(
            classification.industry_label
            for classification in (
                segment.classifications[0]
                for segment in segment_reads
                if segment.classifications
            )
            if classification.is_primary and classification.industry_label
        )
    ]
    all_industry_labels = [
        label
        for label in dict.fromkeys(
            label
            for segment in segment_reads
            for label in segment.classification_labels
            if label
        )
    ]

    response = IndustryWorkbenchRuleAnalysisResponse(
        company_name=request.company_name,
        company_description=request.company_description,
        selected_reporting_period=(
            segment_reads[0].reporting_period
            if segment_reads
            else WORKBENCH_DEFAULT_REPORTING_PERIOD
        ),
        business_segment_count=len(segment_reads),
        primary_industries=primary_industries,
        all_industry_labels=all_industry_labels,
        quality_warnings=_quality_warnings_from_segments(segment_reads),
        has_manual_adjustment=False,
        primary_segments=[
            segment for segment in segment_reads if segment.segment_type == "primary"
        ],
        secondary_segments=[
            segment for segment in segment_reads if segment.segment_type == "secondary"
        ],
        emerging_segments=[
            segment for segment in segment_reads if segment.segment_type == "emerging"
        ],
        other_segments=[
            segment for segment in segment_reads if segment.segment_type == "other"
        ],
        segments=segment_reads,
    )
    return response, segments, local_id_by_numeric_id, workbench_rule_map, prompt_rule_map


def run_industry_workbench_rule_analysis(
    request: IndustryWorkbenchAnalysisRequest,
) -> IndustryWorkbenchRuleAnalysisResponse:
    response, _, _, _, _ = _build_rule_analysis_from_request(request)
    return response


def classify_industry_workbench_with_llm(
    db: Session,
    *,
    request: IndustryWorkbenchAnalysisRequest,
) -> IndustryWorkbenchLlmAnalysisResponse:
    del db
    rule_analysis, segments, local_id_by_numeric_id, workbench_rule_map, prompt_rule_map = (
        _build_rule_analysis_from_request(request)
    )
    peer_lookup = _build_peer_lookup(segments)
    llm_client = DeepSeekChatClient()
    llm_results: list[IndustryWorkbenchLlmSegmentResult] = []

    for segment in segments:
        evaluation = evaluate_segment_candidates(segment, peer_lookup=peer_lookup)
        current_rule_classification = prompt_rule_map[segment.id]
        top_rule_keys = [
            candidate.rule.rule_key for candidate in evaluation.rule_candidates[:3]
        ]
        request_context = BusinessSegmentLlmRequestContext(
            company_name=segment.company.name if segment.company else None,
            company_description=(
                segment.company.description if segment.company else None
            ),
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
                "Current business segment context is too incomplete for LLM classification."
            )
        messages = _build_llm_messages(
            segment=segment,
            current_classification=current_rule_classification,
            evaluation=evaluation,
        )

        status_value = "success"
        message = "DeepSeek suggestion generated successfully."
        llm_result = llm_client.create_chat_completion(messages=messages)
        try:
            suggestion = _build_llm_suggestion_from_content(
                content=llm_result.content,
                segment=segment,
            )
        except ValueError:
            suggestion = _build_llm_parse_fallback_suggestion(
                segment=segment,
                raw_content=llm_result.content,
            )
            status_value = "fallback"
            message = (
                "DeepSeek returned a non-standard response. A conservative fallback "
                "suggestion was generated for manual review."
            )

        local_id = local_id_by_numeric_id[segment.id]
        llm_results.append(
            IndustryWorkbenchLlmSegmentResult(
                segment_id=local_id,
                local_id=local_id,
                segment_name=segment.segment_name,
                status=status_value,
                message=message,
                current_rule_classification=workbench_rule_map[segment.id],
                suggested_classification=_workbench_classification_from_values(
                    local_id=local_id,
                    standard_system=suggestion.standard_system,
                    level_1=suggestion.level_1,
                    level_2=suggestion.level_2,
                    level_3=suggestion.level_3,
                    level_4=suggestion.level_4,
                    is_primary=suggestion.is_primary,
                    mapping_basis=suggestion.mapping_basis,
                    review_status=suggestion.review_status,
                    classifier_type=suggestion.classifier_type,
                    confidence=suggestion.confidence,
                    review_reason=suggestion.review_reason,
                ),
                request_context=request_context,
            )
        )

    return IndustryWorkbenchLlmAnalysisResponse(
        company_name=request.company_name,
        company_description=request.company_description,
        rule_analysis=rule_analysis,
        llm_results=llm_results,
    )
