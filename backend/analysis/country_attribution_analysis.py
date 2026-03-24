from sqlalchemy.orm import Session

from backend.analysis.control_chain import analyze_control_chain
from backend.models.country_attribution import CountryAttribution


def analyze_country_attribution_with_control_chain(
    db: Session,
    company_id: int,
) -> dict:
    # 联动分析先刷新控制链，再读取最新的归属结果快照。
    control_chain_result = analyze_control_chain(db, company_id)
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
                "basis": item["basis"],
            }
        )

    if country_attribution is None:
        return {
            "company_id": company_id,
            "message": "No country attribution record found for this company.",
            "country_attribution": None,
            "control_chain_basis": control_chain_basis,
        }

    return {
        "company_id": company_id,
        "country_attribution": {
            "id": country_attribution.id,
            "company_id": country_attribution.company_id,
            "incorporation_country": country_attribution.incorporation_country,
            "listing_country": country_attribution.listing_country,
            "actual_control_country": country_attribution.actual_control_country,
            "attribution_type": country_attribution.attribution_type,
            "basis": country_attribution.basis,
            "is_manual": country_attribution.is_manual,
            "notes": country_attribution.notes,
        },
        "control_chain_basis": control_chain_basis,
    }
