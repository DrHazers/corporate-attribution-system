from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from backend.analysis.ownership_penetration import AUTO_NOTE, refresh_company_control_analysis
from backend.crud.control_relationship import create_control_relationship
from backend.crud.country_attribution import create_country_attribution
from backend.crud.shareholder import (
    create_entity_alias,
    create_relationship_source,
    create_shareholder_structure,
)
from backend.models.company import Company
from backend.models.control_relationship import ControlRelationship
from backend.models.control_inference_audit_log import ControlInferenceAuditLog
from backend.models.control_inference_run import ControlInferenceRun
from backend.models.country_attribution import CountryAttribution
from backend.models.shareholder import (
    EntityAlias,
    RelationshipSource,
    ShareholderEntity,
    ShareholderStructure,
    ShareholderStructureHistory,
)
from backend.schemas.control_relationship import ControlRelationshipCreate
from backend.schemas.country_attribution import CountryAttributionCreate
from backend.schemas.shareholder import (
    EntityAliasCreate,
    RelationshipSourceCreate,
    ShareholderStructureCreate,
)



def _unique_token() -> str:
    return uuid4().hex[:8]



def _create_company(db_session, token: str, *, name_prefix: str = "Upgrade Test Company") -> Company:
    company = Company(
        name=f"{name_prefix} {token}",
        stock_code=f"UPG{token[:5].upper()}",
        incorporation_country="China",
        listing_country="Hong Kong",
        headquarters="Shenzhen",
        description="temporary database-upgrade test company",
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    return company



def _create_entity(
    db_session,
    *,
    token: str,
    entity_name: str,
    entity_type: str,
    company_id: int | None = None,
    country: str | None = "China",
) -> ShareholderEntity:
    entity = ShareholderEntity(
        entity_name=f"{entity_name} {token}",
        entity_type=entity_type,
        country=country,
        company_id=company_id,
        identifier_code=None,
        is_listed=None,
        notes="temporary database-upgrade fixture",
    )
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)
    return entity



def _cleanup_fixture_data(
    db_session,
    *,
    company_ids: list[int],
    entity_ids: list[int],
    structure_ids: list[int],
    alias_ids: list[int],
    source_ids: list[int],
) -> None:
    if company_ids:
        (
            db_session.query(ControlInferenceAuditLog)
            .filter(ControlInferenceAuditLog.company_id.in_(company_ids))
            .delete(synchronize_session=False)
        )
        (
            db_session.query(ControlRelationship)
            .filter(ControlRelationship.company_id.in_(company_ids))
            .delete(synchronize_session=False)
        )
        (
            db_session.query(CountryAttribution)
            .filter(CountryAttribution.company_id.in_(company_ids))
            .delete(synchronize_session=False)
        )
        (
            db_session.query(ControlInferenceRun)
            .filter(ControlInferenceRun.company_id.in_(company_ids))
            .delete(synchronize_session=False)
        )
    if structure_ids:
        (
            db_session.query(ShareholderStructureHistory)
            .filter(ShareholderStructureHistory.structure_id.in_(structure_ids))
            .delete(synchronize_session=False)
        )
        (
            db_session.query(RelationshipSource)
            .filter(RelationshipSource.structure_id.in_(structure_ids))
            .delete(synchronize_session=False)
        )
        (
            db_session.query(ShareholderStructure)
            .filter(ShareholderStructure.id.in_(structure_ids))
            .delete(synchronize_session=False)
        )
    if alias_ids:
        (
            db_session.query(EntityAlias)
            .filter(EntityAlias.id.in_(alias_ids))
            .delete(synchronize_session=False)
        )
    if entity_ids:
        (
            db_session.query(EntityAlias)
            .filter(EntityAlias.entity_id.in_(entity_ids))
            .delete(synchronize_session=False)
        )
    if source_ids:
        (
            db_session.query(RelationshipSource)
            .filter(RelationshipSource.id.in_(source_ids))
            .delete(synchronize_session=False)
        )
    if entity_ids:
        (
            db_session.query(ShareholderEntity)
            .filter(ShareholderEntity.id.in_(entity_ids))
            .delete(synchronize_session=False)
        )
    if company_ids:
        (
            db_session.query(Company)
            .filter(Company.id.in_(company_ids))
            .delete(synchronize_session=False)
        )
    db_session.commit()



def test_shareholder_structure_write_infers_relation_semantics_and_new_fields_on_import_db(db_session):
    token = _unique_token()
    company_ids: list[int] = []
    entity_ids: list[int] = []
    structure_ids: list[int] = []

    try:
        company = _create_company(db_session, token)
        company_ids.append(company.id)

        target_entity = _create_entity(
            db_session,
            token=token,
            entity_name="Target Entity",
            entity_type="company",
            company_id=company.id,
        )
        equity_holder = _create_entity(
            db_session,
            token=token,
            entity_name="Equity Holder",
            entity_type="company",
            country="Singapore",
        )
        agreement_holder = _create_entity(
            db_session,
            token=token,
            entity_name="Agreement Holder",
            entity_type="institution",
            country="Cayman Islands",
        )
        board_holder = _create_entity(
            db_session,
            token=token,
            entity_name="Board Holder",
            entity_type="institution",
            country="USA",
        )
        entity_ids.extend([target_entity.id, equity_holder.id, agreement_holder.id, board_holder.id])

        equity_structure = create_shareholder_structure(
            db_session,
            ShareholderStructureCreate(
                from_entity_id=equity_holder.id,
                to_entity_id=target_entity.id,
                holding_ratio=Decimal("55.5000"),
                remarks="legacy equity insert without explicit relation type",
                relation_priority=1,
                confidence_level="high",
            ),
        )
        agreement_structure = create_shareholder_structure(
            db_session,
            ShareholderStructureCreate(
                from_entity_id=agreement_holder.id,
                to_entity_id=target_entity.id,
                relation_type="agreement",
                remarks="Contractual voting arrangement for operating decisions",
                relation_priority=3,
                confidence_level="medium",
            ),
        )
        board_structure = create_shareholder_structure(
            db_session,
            ShareholderStructureCreate(
                from_entity_id=board_holder.id,
                to_entity_id=target_entity.id,
                relation_type="board_control",
                board_seats=3,
                nomination_rights="May nominate 3 of 5 directors",
                control_basis="Board nomination agreement",
                relation_priority=2,
                confidence_level="high",
            ),
        )
        structure_ids.extend([equity_structure.id, agreement_structure.id, board_structure.id])

        assert equity_structure.relation_type == "equity"
        assert equity_structure.control_type == "equity"
        assert equity_structure.has_numeric_ratio is True
        assert equity_structure.relation_role == "ownership"
        assert equity_structure.relation_priority == 1
        assert equity_structure.confidence_level == "high"

        assert agreement_structure.relation_type == "agreement"
        assert agreement_structure.control_type == "agreement"
        assert agreement_structure.holding_ratio is None
        assert agreement_structure.has_numeric_ratio is False
        assert agreement_structure.relation_role == "contractual"
        assert agreement_structure.control_basis is not None
        assert agreement_structure.agreement_scope is not None
        assert agreement_structure.relation_priority == 3
        assert agreement_structure.confidence_level == "medium"

        assert board_structure.relation_type == "board_control"
        assert board_structure.control_type == "board_control"
        assert board_structure.has_numeric_ratio is False
        assert board_structure.relation_role == "governance"
        assert board_structure.board_seats == 3
        assert board_structure.nomination_rights == "May nominate 3 of 5 directors"
        assert board_structure.relation_priority == 2
        assert board_structure.confidence_level == "high"
    finally:
        _cleanup_fixture_data(
            db_session,
            company_ids=company_ids,
            entity_ids=entity_ids,
            structure_ids=structure_ids,
            alias_ids=[],
            source_ids=[],
        )



def test_control_relationship_country_sources_and_aliases_support_new_fields(db_session):
    token = _unique_token()
    company_ids: list[int] = []
    entity_ids: list[int] = []
    structure_ids: list[int] = []
    alias_ids: list[int] = []
    source_ids: list[int] = []

    try:
        company = _create_company(db_session, token)
        company_ids.append(company.id)
        target_entity = _create_entity(
            db_session,
            token=token,
            entity_name="Target Entity",
            entity_type="company",
            company_id=company.id,
        )
        controller_entity = _create_entity(
            db_session,
            token=token,
            entity_name="Controller Entity",
            entity_type="company",
            country="Singapore",
        )
        entity_ids.extend([target_entity.id, controller_entity.id])

        structure = create_shareholder_structure(
            db_session,
            ShareholderStructureCreate(
                from_entity_id=controller_entity.id,
                to_entity_id=target_entity.id,
                holding_ratio=Decimal("42.0000"),
                relation_priority=1,
                confidence_level="high",
            ),
        )
        structure_ids.append(structure.id)

        control_relationship = create_control_relationship(
            db_session,
            ControlRelationshipCreate(
                company_id=company.id,
                controller_entity_id=controller_entity.id,
                controller_name=controller_entity.entity_name,
                controller_type=controller_entity.entity_type,
                control_type="mixed_test",
                control_ratio=Decimal("42.0000"),
                control_path='[{"path_entity_ids": [1, 2]}]',
                is_actual_controller=False,
                basis="mixed control evidence",
                notes="manual test record",
                control_mode="mixed",
                semantic_flags='["agreement", "board_control"]',
                review_status="needs_review",
            ),
        )
        country_attribution = create_country_attribution(
            db_session,
            CountryAttributionCreate(
                company_id=company.id,
                incorporation_country="China",
                listing_country="Hong Kong",
                actual_control_country="Singapore",
                attribution_type="manual_override_case",
                basis="manual basis",
                is_manual=True,
                notes="manual test record",
                source_mode="manual_override",
            ),
        )
        source_one = create_relationship_source(
            db_session,
            structure_id=structure.id,
            relationship_source_in=RelationshipSourceCreate(
                source_type="annual_report",
                source_name="2025 Annual Report",
                source_url="https://example.com/report1",
                excerpt="Ownership disclosure paragraph.",
                confidence_level="high",
            ),
        )
        source_two = create_relationship_source(
            db_session,
            structure_id=structure.id,
            relationship_source_in=RelationshipSourceCreate(
                source_type="filing",
                source_name="Exchange Filing",
                source_url="https://example.com/report2",
                excerpt="Supplemental filing excerpt.",
                confidence_level="medium",
            ),
        )
        alias_one = create_entity_alias(
            db_session,
            entity_id=controller_entity.id,
            entity_alias_in=EntityAliasCreate(
                alias_name=f"Controller EN {token}",
                alias_type="english",
                is_primary=True,
            ),
        )
        alias_two = create_entity_alias(
            db_session,
            entity_id=controller_entity.id,
            entity_alias_in=EntityAliasCreate(
                alias_name=f"Controller CN {token}",
                alias_type="chinese",
                is_primary=False,
            ),
        )
        source_ids.extend([source_one.id, source_two.id])
        alias_ids.extend([alias_one.id, alias_two.id])

        assert control_relationship.control_mode == "mixed"
        assert control_relationship.semantic_flags == '["agreement", "board_control"]'
        assert control_relationship.review_status == "needs_review"

        assert country_attribution.source_mode == "manual_override"

        stored_sources = (
            db_session.query(RelationshipSource)
            .filter(RelationshipSource.structure_id == structure.id)
            .order_by(RelationshipSource.id.asc())
            .all()
        )
        assert len(stored_sources) == 2
        assert {item.source_type for item in stored_sources} == {"annual_report", "filing"}

        stored_aliases = (
            db_session.query(EntityAlias)
            .filter(EntityAlias.entity_id == controller_entity.id)
            .order_by(EntityAlias.id.asc())
            .all()
        )
        assert len(stored_aliases) == 2
        assert sum(1 for item in stored_aliases if item.is_primary) == 1
    finally:
        _cleanup_fixture_data(
            db_session,
            company_ids=company_ids,
            entity_ids=entity_ids,
            structure_ids=structure_ids,
            alias_ids=alias_ids,
            source_ids=source_ids,
        )



def test_legacy_equity_rows_remain_compatible_and_non_equity_edges_are_not_multiplied(db_session):
    token = _unique_token()
    company_ids: list[int] = []
    entity_ids: list[int] = []
    structure_ids: list[int] = []

    try:
        company = _create_company(db_session, token)
        company_ids.append(company.id)
        target_entity = _create_entity(
            db_session,
            token=token,
            entity_name="Legacy Target",
            entity_type="company",
            company_id=company.id,
        )
        legacy_controller = _create_entity(
            db_session,
            token=token,
            entity_name="Legacy Controller",
            entity_type="company",
            country="Singapore",
        )
        agreement_holder = _create_entity(
            db_session,
            token=token,
            entity_name="Agreement Holder",
            entity_type="institution",
            country="USA",
        )
        vie_holder = _create_entity(
            db_session,
            token=token,
            entity_name="VIE Holder",
            entity_type="institution",
            country="Cayman Islands",
        )
        entity_ids.extend([target_entity.id, legacy_controller.id, agreement_holder.id, vie_holder.id])

        legacy_equity = ShareholderStructure(
            from_entity_id=legacy_controller.id,
            to_entity_id=target_entity.id,
            holding_ratio=Decimal("61.0000"),
            is_direct=True,
            control_type=None,
            relation_type=None,
            has_numeric_ratio=False,
            relation_role=None,
            reporting_period="2025-12-31",
            is_current=True,
            source="legacy_import",
            remarks="legacy equity path for compatibility",
        )
        agreement_edge = ShareholderStructure(
            from_entity_id=agreement_holder.id,
            to_entity_id=target_entity.id,
            holding_ratio=None,
            is_direct=True,
            control_type="agreement",
            relation_type="agreement",
            has_numeric_ratio=False,
            relation_role="contractual",
            control_basis="Non-equity operating agreement",
            agreement_scope="Reserved matters agreement",
            reporting_period="2025-12-31",
            is_current=True,
            source="legacy_import",
            remarks="agreement edge",
        )
        vie_edge = ShareholderStructure(
            from_entity_id=vie_holder.id,
            to_entity_id=target_entity.id,
            holding_ratio=None,
            is_direct=True,
            control_type="vie",
            relation_type="vie",
            has_numeric_ratio=False,
            relation_role="contractual",
            control_basis="Variable interest entity contract",
            agreement_scope="Exclusive service agreement",
            reporting_period="2025-12-31",
            is_current=True,
            source="legacy_import",
            remarks="vie edge",
        )
        db_session.add_all([legacy_equity, agreement_edge, vie_edge])
        db_session.commit()
        structure_ids.extend([legacy_equity.id, agreement_edge.id, vie_edge.id])

        result = refresh_company_control_analysis(db_session, company.id)
        persisted_relationships = (
            db_session.query(ControlRelationship)
            .filter(ControlRelationship.company_id == company.id)
            .filter(ControlRelationship.notes == AUTO_NOTE)
            .order_by(ControlRelationship.id.asc())
            .all()
        )
        persisted_country = (
            db_session.query(CountryAttribution)
            .filter(CountryAttribution.company_id == company.id)
            .order_by(CountryAttribution.id.desc())
            .first()
        )

        assert result["actual_controller_entity_id"] == vie_holder.id
        assert any(
            item.controller_entity_id == vie_holder.id
            and item.control_type == "agreement_control"
            and item.control_mode == "semantic"
            and item.review_status == "auto"
            for item in persisted_relationships
        )
        assert any(
            item.controller_entity_id == legacy_controller.id
            and item.control_type == "equity_control"
            and item.control_mode == "numeric"
            and item.review_status == "auto"
            for item in persisted_relationships
        )
        assert all(
            item.control_mode != "numeric" or item.controller_entity_id == legacy_controller.id
            for item in persisted_relationships
        )
        assert persisted_country is not None
        assert persisted_country.source_mode == "control_chain_analysis"
    finally:
        _cleanup_fixture_data(
            db_session,
            company_ids=company_ids,
            entity_ids=entity_ids,
            structure_ids=structure_ids,
            alias_ids=[],
            source_ids=[],
        )



def test_shareholder_structures_api_filters_and_history_auto_record_on_import_db(client, db_session):
    token = _unique_token()
    company_ids: list[int] = []
    entity_ids: list[int] = []
    structure_ids: list[int] = []

    try:
        company = _create_company(db_session, token, name_prefix="API History Company")
        company_ids.append(company.id)
        target_entity = _create_entity(
            db_session,
            token=token,
            entity_name="API Target",
            entity_type="company",
            company_id=company.id,
        )
        board_holder = _create_entity(
            db_session,
            token=token,
            entity_name="API Board Holder",
            entity_type="institution",
        )
        agreement_holder = _create_entity(
            db_session,
            token=token,
            entity_name="API Agreement Holder",
            entity_type="institution",
        )
        entity_ids.extend([target_entity.id, board_holder.id, agreement_holder.id])

        board_response = client.post(
            "/shareholders/structures",
            json={
                "from_entity_id": board_holder.id,
                "to_entity_id": target_entity.id,
                "relation_type": "board_control",
                "board_seats": 2,
                "nomination_rights": "Can appoint 2 directors",
                "control_basis": "Shareholders agreement board clause",
                "relation_priority": 1,
                "confidence_level": "high",
                "is_current": True,
                "source": "api_test",
            },
        )
        assert board_response.status_code == 201
        board_structure = board_response.json()
        structure_ids.append(board_structure["id"])

        agreement_response = client.post(
            "/shareholders/structures",
            json={
                "from_entity_id": agreement_holder.id,
                "to_entity_id": target_entity.id,
                "relation_type": "agreement",
                "control_basis": "Contract clause",
                "agreement_scope": "Operating matters",
                "relation_priority": 2,
                "confidence_level": "medium",
                "is_current": True,
                "source": "api_test",
            },
        )
        assert agreement_response.status_code == 201
        structure_ids.append(agreement_response.json()["id"])

        filter_response = client.get(
            f"/shareholders/structures?to_entity_id={target_entity.id}"
            "&relation_role=governance&has_numeric_ratio=false&confidence_level=high"
        )
        assert filter_response.status_code == 200
        payload = filter_response.json()
        assert len(payload) == 1
        edge = payload[0]
        assert edge["id"] == board_structure["id"]
        assert edge["relation_type"] == "board_control"
        assert edge["relation_role"] == "governance"
        assert edge["board_seats"] == 2
        assert edge["relation_priority"] == 1
        assert edge["confidence_level"] == "high"

        update_response = client.put(
            f"/shareholders/structures/{board_structure['id']}",
            json={"board_seats": 3, "remarks": "Updated board clause"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["board_seats"] == 3

        history_response = client.get(
            f"/shareholder-structures/{board_structure['id']}/history"
        )
        assert history_response.status_code == 200
        history_payload = history_response.json()
        assert len(history_payload) >= 2
        assert history_payload[0]["change_type"] == "insert"
        assert history_payload[-1]["change_type"] == "update"
    finally:
        _cleanup_fixture_data(
            db_session,
            company_ids=company_ids,
            entity_ids=entity_ids,
            structure_ids=structure_ids,
            alias_ids=[],
            source_ids=[],
        )



def test_relationship_sources_and_entity_aliases_api_crud_and_empty_results(client, db_session):
    token = _unique_token()
    company_ids: list[int] = []
    entity_ids: list[int] = []
    structure_ids: list[int] = []

    try:
        company = _create_company(db_session, token, name_prefix="API Metadata Company")
        company_ids.append(company.id)
        target_entity = _create_entity(
            db_session,
            token=token,
            entity_name="Metadata Target",
            entity_type="company",
            company_id=company.id,
        )
        holder_entity = _create_entity(
            db_session,
            token=token,
            entity_name="Metadata Holder",
            entity_type="company",
        )
        entity_ids.extend([target_entity.id, holder_entity.id])

        structure = create_shareholder_structure(
            db_session,
            ShareholderStructureCreate(
                from_entity_id=holder_entity.id,
                to_entity_id=target_entity.id,
                holding_ratio=Decimal("28.0000"),
                relation_priority=1,
                confidence_level="high",
            ),
        )
        structure_ids.append(structure.id)

        empty_sources = client.get(f"/shareholder-structures/{structure.id}/sources")
        assert empty_sources.status_code == 200
        assert empty_sources.json() == []

        source_one = client.post(
            f"/shareholder-structures/{structure.id}/sources",
            json={
                "source_type": "annual_report",
                "source_name": "Annual Report",
                "source_url": "https://example.com/ar",
                "excerpt": "Primary disclosure",
                "confidence_level": "high",
            },
        )
        assert source_one.status_code == 201
        source_two = client.post(
            f"/shareholder-structures/{structure.id}/sources",
            json={
                "source_type": "filing",
                "source_name": "Exchange Filing",
                "source_url": "https://example.com/filing",
                "excerpt": "Supplemental disclosure",
                "confidence_level": "medium",
            },
        )
        assert source_two.status_code == 201

        source_list = client.get(f"/shareholder-structures/{structure.id}/sources")
        assert source_list.status_code == 200
        assert len(source_list.json()) == 2

        source_id = source_one.json()["id"]
        source_detail = client.get(f"/relationship-sources/{source_id}")
        assert source_detail.status_code == 200
        assert source_detail.json()["source_type"] == "annual_report"

        source_update = client.patch(
            f"/relationship-sources/{source_id}",
            json={"confidence_level": "medium", "source_name": "Updated Annual Report"},
        )
        assert source_update.status_code == 200
        assert source_update.json()["confidence_level"] == "medium"

        delete_source = client.delete(f"/relationship-sources/{source_id}")
        assert delete_source.status_code == 204
        assert len(client.get(f"/shareholder-structures/{structure.id}/sources").json()) == 1

        empty_aliases = client.get(f"/entities/{holder_entity.id}/aliases")
        assert empty_aliases.status_code == 200
        assert empty_aliases.json() == []

        alias_one = client.post(
            f"/entities/{holder_entity.id}/aliases",
            json={"alias_name": f"Alias EN {token}", "alias_type": "english", "is_primary": True},
        )
        assert alias_one.status_code == 201
        alias_two = client.post(
            f"/entities/{holder_entity.id}/aliases",
            json={"alias_name": f"Alias CN {token}", "alias_type": "chinese", "is_primary": False},
        )
        assert alias_two.status_code == 201

        alias_list = client.get(f"/entities/{holder_entity.id}/aliases")
        assert alias_list.status_code == 200
        assert len(alias_list.json()) == 2

        alias_id = alias_two.json()["id"]
        alias_detail = client.get(f"/entity-aliases/{alias_id}")
        assert alias_detail.status_code == 200
        assert alias_detail.json()["alias_type"] == "chinese"

        alias_update = client.patch(
            f"/entity-aliases/{alias_id}",
            json={"is_primary": True, "alias_name": f"Alias CN Updated {token}"},
        )
        assert alias_update.status_code == 200
        assert alias_update.json()["is_primary"] is True

        alias_list_after = client.get(f"/entities/{holder_entity.id}/aliases").json()
        assert sum(1 for item in alias_list_after if item["is_primary"]) == 1

        delete_alias = client.delete(f"/entity-aliases/{alias_id}")
        assert delete_alias.status_code == 204
        assert len(client.get(f"/entities/{holder_entity.id}/aliases").json()) == 1
    finally:
        _cleanup_fixture_data(
            db_session,
            company_ids=company_ids,
            entity_ids=entity_ids,
            structure_ids=structure_ids,
            alias_ids=[],
            source_ids=[],
        )



def test_relationship_graph_and_special_relations_handle_empty_company_without_edges(client, db_session):
    token = _unique_token()
    company_ids: list[int] = []
    entity_ids: list[int] = []

    try:
        company = _create_company(db_session, token, name_prefix="Empty Graph Company")
        company_ids.append(company.id)
        target_entity = _create_entity(
            db_session,
            token=token,
            entity_name="Empty Graph Target",
            entity_type="company",
            company_id=company.id,
        )
        entity_ids.append(target_entity.id)

        graph_response = client.get(f"/companies/{company.id}/relationship-graph")
        assert graph_response.status_code == 200
        graph_payload = graph_response.json()
        assert graph_payload["company_id"] == company.id
        assert graph_payload["target_entity_id"] == target_entity.id
        assert graph_payload["node_count"] == 1
        assert graph_payload["edge_count"] == 0
        assert graph_payload["edges"] == []

        special_response = client.get(f"/companies/{company.id}/special-control-relations")
        assert special_response.status_code == 200
        special_payload = special_response.json()
        assert special_payload["company_id"] == company.id
        assert special_payload["has_special_control_relations"] is False
        assert special_payload["total_count"] == 0
        assert special_payload["relations"] == []
    finally:
        _cleanup_fixture_data(
            db_session,
            company_ids=company_ids,
            entity_ids=entity_ids,
            structure_ids=[],
            alias_ids=[],
            source_ids=[],
        )



