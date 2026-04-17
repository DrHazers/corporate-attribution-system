from sqlalchemy.orm import Session

from backend.analysis.control_chain import analyze_control_chain_with_options
from backend.analysis.ownership_penetration import (
    _canonical_attribution_type,
    _normalize_country_basis_payload,
)
from backend.models.country_attribution import CountryAttribution


def analyze_country_attribution_with_control_chain(
    db: Session,
    company_id: int,
) -> dict:
    return analyze_country_attribution_with_options(
        db,
        company_id,
        refresh=False,
    )


def analyze_country_attribution_with_options(
    db: Session,
    company_id: int,
    *,
    refresh: bool = False,
) -> dict:
    control_chain_result = analyze_control_chain_with_options(
        db,
        company_id,
        refresh=refresh,
    )
    country_attribution = (
        db.query(CountryAttribution)
        .filter(CountryAttribution.company_id == company_id)
        .order_by(CountryAttribution.id.desc())
        .first()
    )

    control_chain_basis = []
    for item in control_chain_result["control_relationships"]:
        control_chain_basis.append(
            {
                "controller_entity_id": item["controller_entity_id"],
                "controller_name": item["controller_name"],
                "control_type": item["control_type"],
                "control_path": item["control_path"],
                "is_actual_controller": item["is_actual_controller"],
                "control_tier": item.get("control_tier"),
                "is_direct_controller": item.get("is_direct_controller"),
                "is_intermediate_controller": item.get("is_intermediate_controller"),
                "is_ultimate_controller": item.get("is_ultimate_controller"),
                "promotion_source_entity_id": item.get("promotion_source_entity_id"),
                "promotion_reason": item.get("promotion_reason"),
                "control_chain_depth": item.get("control_chain_depth"),
                "is_terminal_inference": item.get("is_terminal_inference"),
                "terminal_failure_reason": item.get("terminal_failure_reason"),
                "immediate_control_ratio": item.get("immediate_control_ratio"),
                "aggregated_control_score": item.get("aggregated_control_score"),
                "terminal_control_score": item.get("terminal_control_score"),
                "inference_run_id": item.get("inference_run_id"),
                "basis": item["basis"],
                "control_mode": item.get("control_mode"),
                "semantic_flags": item.get("semantic_flags"),
                "controller_status": item.get("controller_status"),
                "selection_reason": item.get("selection_reason"),
                "is_leading_candidate": item.get("is_leading_candidate"),
                "whether_actual_controller": item.get("whether_actual_controller"),
                "review_status": item.get("review_status"),
            }
        )

    if country_attribution is None:
        return {
            "company_id": company_id,
            "message": "No country attribution record found for this company.",
            "country_attribution": None,
            "control_chain_basis": control_chain_basis,
        }

    attribution_type = _canonical_attribution_type(country_attribution.attribution_type)
    return {
        "company_id": company_id,
        "country_attribution": {
            "id": country_attribution.id,
            "company_id": country_attribution.company_id,
            "incorporation_country": country_attribution.incorporation_country,
            "listing_country": country_attribution.listing_country,
            "actual_control_country": country_attribution.actual_control_country,
            "attribution_type": attribution_type,
            "actual_controller_entity_id": country_attribution.actual_controller_entity_id,
            "direct_controller_entity_id": country_attribution.direct_controller_entity_id,
            "attribution_layer": country_attribution.attribution_layer,
            "country_inference_reason": country_attribution.country_inference_reason,
            "look_through_applied": country_attribution.look_through_applied,
            "basis": _normalize_country_basis_payload(
                country_attribution.basis,
                attribution_type=attribution_type,
            ),
            "is_manual": country_attribution.is_manual,
            "notes": country_attribution.notes,
            "source_mode": country_attribution.source_mode,
        },
        "control_chain_basis": control_chain_basis,
    }
