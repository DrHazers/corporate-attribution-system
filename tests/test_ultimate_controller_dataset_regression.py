from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.analysis.control_inference import build_control_context, infer_controllers


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DB = PROJECT_ROOT / "ultimate_controller_test_dataset.db"


@pytest.mark.skipif(
    not DATASET_DB.exists(),
    reason="ultimate controller test dataset DB is not available",
)
def test_ultimate_controller_dataset_key_scenarios_regression():
    engine = create_engine(
        f"sqlite:///{DATASET_DB}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        with session_factory() as db:
            context = build_control_context(db)

            direct_is_ultimate = infer_controllers(context, 2001)
            assert direct_is_ultimate.direct_controller_entity_id == 3001
            assert direct_is_ultimate.actual_controller_entity_id == 3001
            assert direct_is_ultimate.attribution_layer == "direct_controller_country"

            rolled_up = infer_controllers(context, 2004)
            assert rolled_up.direct_controller_entity_id == 3013
            assert rolled_up.actual_controller_entity_id == 3014
            assert rolled_up.attribution_layer == "ultimate_controller_country"

            joint_blocked = infer_controllers(context, 2007)
            assert joint_blocked.direct_controller_entity_id == 3025
            assert joint_blocked.actual_controller_entity_id is None
            assert joint_blocked.terminal_failure_reason == "joint_control"
            assert joint_blocked.attribution_layer == "joint_control_undetermined"

            nominee_blocked = infer_controllers(context, 2016)
            assert nominee_blocked.direct_controller_entity_id is None
            assert nominee_blocked.actual_controller_entity_id is None
            assert nominee_blocked.terminal_failure_reason == "beneficial_owner_unknown"
            assert nominee_blocked.attribution_type == "fallback_incorporation"

            fallback = infer_controllers(context, 2021)
            assert fallback.direct_controller_entity_id is None
            assert fallback.actual_controller_entity_id is None
            assert fallback.attribution_type == "fallback_incorporation"
            assert fallback.actual_control_country == "Canada"

            board_control = infer_controllers(context, 2023)
            assert board_control.direct_controller_entity_id == 3095
            assert board_control.actual_controller_entity_id == 3096
            assert board_control.attribution_type == "mixed_control"
            assert board_control.attribution_layer == "ultimate_controller_country"

            low_confidence = infer_controllers(context, 2012)
            assert low_confidence.direct_controller_entity_id is None
            assert low_confidence.actual_controller_entity_id is None
            assert low_confidence.leading_candidate_entity_id == 3050
            assert low_confidence.terminal_failure_reason == (
                "low_confidence_evidence_weak"
            )

            strong_vie = infer_controllers(context, 2024)
            assert strong_vie.direct_controller_entity_id == 3099
            assert strong_vie.actual_controller_entity_id == 3100
            assert strong_vie.attribution_type == "mixed_control"
            assert strong_vie.actual_control_country == "China"
    finally:
        engine.dispose()
