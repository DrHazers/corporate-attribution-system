# Ultimate Controller Main Release Summary

## Status

- Date: 2026-04-18
- Recommendation: treat the current unified ultimate-controller algorithm as the mainline release candidate and freeze the main decision rules.
- Scope of this document: summarize the frozen mainline, the final validation pass, the current boundaries, and the recommended next-stage work.

## 1. Mainline Goal

The current mainline is designed to answer one operational question consistently:

- who is the direct controller of a company;
- whether that direct controller should remain terminal or be promoted to an ultimate / actual controller;
- when the algorithm must stop and stay conservative instead of forcing a unique controller.

The current implementation is optimized for:

- stable direct vs. ultimate controller layering;
- conservative blocking when the evidence is weak or structurally ambiguous;
- repeatable batch validation on both the small curated dataset and the enhanced large validation dataset.

## 2. Frozen Mainline Scope

The current mainline already includes the following rule families and should be treated as the frozen v1 mainline behavior.

### 2.1 Direct / Ultimate Controller Resolution

- direct controller identification from equity and supported semantic control paths;
- ultimate / actual controller promotion through upstream parent chains;
- explicit stop vs. look-through handling;
- fallback to incorporation country when no unique controller should be emitted.

### 2.2 Promotion / Look-Through

- standard rollup through `holding_company`, `spv`, `shell_company`, `investment_vehicle`, `control_platform`, `sponsor_vehicle`, `wfoe`, and related intermediary entities;
- promotion gating by target-side control score, upstream control score, and confidence;
- near-threshold rollup support for valid rollup-success cases;
- SPV / holding-company look-through behavior validated on the enhanced dataset.

### 2.3 Blocking / Conservative Stops

- joint control block;
- close competition stop;
- nominee / beneficial owner unknown block;
- low-confidence evidence weak stop;
- insufficient evidence / fallback handling;
- retention of conservative behavior for public-float / dispersed structures that do not justify a unique controller.

### 2.4 Evidence Model

- unified semantic control evidence scoring for:
  - `equity`
  - `agreement`
  - `board_control`
  - `voting_right`
  - `vie`
  - `nominee`
- model lineage:
  - semantic evidence model: `semantic_control_evidence_model_v1_1`
  - edge reliability model: `edge_reliability_model_v1_1`

### 2.5 Tuned Mainline Behaviors Already Included

- mixed-control threshold tuning;
- non-equity / contractual control threshold tuning;
- rollup-success tuning for direct holding companies that should continue upward;
- trust small-rule enhancement:
  - disclosed terminal trust arrangements may remain terminal;
  - trust holding / trust vehicle intermediaries may continue look-through when upstream terminal signals are clear;
  - name-only trust labels do not get a generic boost.

## 3. Structures Covered by the Frozen Mainline

The current mainline is suitable for the following control structures.

- standard direct equity control;
- direct-equals-ultimate cases;
- multi-layer equity rollup to an upstream corporate, family, person, or state terminal entity;
- SPV / holding-company look-through;
- VIE / agreement / board-control / voting-right cases with sufficient semantic and reliability support;
- mixed numeric + semantic control paths;
- nominee and beneficial-owner-unknown blocking scenarios;
- joint-control blocking scenarios;
- low-confidence / weak-evidence fallback scenarios;
- limited trust scenarios where the trust role is explicit and the evidence is structurally clear.

## 4. Mainline Blocking Rules

The following conservative behaviors are part of the frozen mainline and should not be loosened inside the current version unless a new phase is explicitly opened.

- `joint_control` blocks a unique actual controller;
- `beneficial_owner_unknown` blocks a unique actual controller;
- `nominee_without_disclosure` blocks a unique actual controller;
- `low_confidence_evidence_weak` blocks borderline control conclusions;
- `close_competition` prevents forced over-resolution;
- `insufficient_evidence` preserves fallback behavior when no controller should be emitted.

## 5. What Is Intentionally Not Deeply Covered Yet

The following areas are outside the frozen mainline and should be treated as next-stage enhancement topics rather than current-version gaps to patch immediately.

- GP-LP and fund-governance-specific controller logic;
- deeper multi-layer trust hierarchy modeling;
- acting-in-concert modeling;
- dedicated state-ownership special rules beyond current generic handling;
- finer public-float / dispersed-ownership presentation and explanation logic;
- more detailed source-quality, path-independence, and corroboration modeling;
- more explicit provenance weighting across multiple conflicting source chains.

## 6. Final Validation Pass

The frozen mainline was revalidated on both the curated small dataset and the enhanced validation dataset.

### 6.1 Small Curated Dataset

Validation was run on the safe copy:

- `ultimate_controller_test_dataset_mainline_working.db`

Source baseline remained untouched:

- `ultimate_controller_test_dataset.db`

Refresh result:

- total companies: `24`
- refresh success: `24 / 24`
- refresh failures: `0`

Key scenario checks remained correct:

| Company ID | Expected Outcome | Final Result |
| --- | --- | --- |
| 2001 | direct = ultimate | passed |
| 2004 | rollup to upstream parent | passed |
| 2007 | joint-control block | passed |
| 2012 | low-confidence fallback | passed |
| 2016 | beneficial-owner-unknown block | passed |
| 2021 | fallback incorporation | passed |
| 2023 | board-control / mixed promotion | passed |
| 2024 | strong VIE / mixed promotion | passed |

### 6.2 Enhanced Validation Dataset

Validation used the current safe working copy:

- `ultimate_controller_enhanced_dataset_trust_working.db`

Refresh result:

- total companies: `10030`
- refresh success: `10030 / 10030`
- refresh failures: `0`

Result distribution snapshot:

- companies with direct controller: `7694`
- companies with ultimate controller: `7666`
- direct = ultimate: `7519`
- promotion occurred: `147`
- joint control: `23`
- nominee / beneficial-owner-unknown blocked: `28`
- low confidence evidence weak: `1294`
- fallback incorporation: `2336`
- leading candidate only: `2350`

Attribution distribution:

- `direct_controller_country`: `7524`
- `ultimate_controller_country`: `147`
- `joint_control_undetermined`: `23`
- `fallback_incorporation`: `2336`

### 6.3 Enhanced 235-Target Regression

The current enhanced regression remained fully green:

- target count: `235`
- `A_direct_ultimate`: all green
- `B_rollup_success`: all green
- `C_joint_block`: all green
- `D_close_competition`: all green
- `E_spv_lookthrough`: all green
- `F_nominee_unknown`: all green
- `G_terminal_person_state_family`: all green
- `H_fallback`: all green
- `I_non_equity`: all green
- `J_mixed_control`: all green

No new `too_aggressive` side effects were introduced in the final trust-enhanced mainline.

### 6.4 Targeted Trust Final Check

The trust enhancement remained intentionally narrow in the final pass.

- trust-related company count in enhanced validation: `155`
- total trust-related actual-controller changes vs. previous rollup baseline: `2`
- both changes were valid trust-vehicle look-through cases:
  - `1112 Apex Advanced Materials Corporation`
  - `4099 Atlantic Media Holdings Inc.`

This is the desired final shape:

- trust support improved in a limited, explainable way;
- no broad relaxation of the mainline controller threshold;
- no regression to family / nominee / fallback stability.

### 6.5 Code-Level Test Suite

The final mainline-related pytest pass completed successfully:

- total selected tests: `31`
- passed: `31`
- failed: `0`

Files included in the final pass:

- `tests/test_ultimate_controller_dataset_regression.py`
- `tests/test_rollup_success_promotion_tuning.py`
- `tests/test_mixed_and_non_equity_threshold_tuning.py`
- `tests/test_trust_control_rules.py`
- `tests/test_reliability_integration.py`
- `tests/test_semantic_control_evidence_model.py`
- `tests/test_terminal_controller_v2.py`

## 7. Freeze Boundary

From this point, the recommended mainline rule boundary is:

- do not continue changing the core control thresholds inside the current main version;
- do not continue expanding new control-structure families inside the current main version;
- only allow bug fixes, documentation, observability, or clearly isolated next-phase feature branches.

## 8. Recommendation

### 8.1 Mainline Completion Judgment

Yes. The current algorithm can now be treated as the completed mainline version for:

- development handoff;
- demo and visualization work;
- project-stage summary and documentation;
- next-phase enhancements on top of a stable baseline.

### 8.2 Freeze Recommendation

Yes. Freeze the current main decision rules.

The current shape is already strong enough for a main release because it now has:

- stable direct / ultimate layering;
- stable blockers;
- stable mixed / non-equity behavior;
- stable rollup behavior;
- stable small trust enhancement;
- fully green 235-target regression;
- no new aggressive side effects in the final pass.

## 9. Recommended Next-Stage Priorities

If development continues, the next work should happen as explicit phase-2 enhancements rather than as more mainline tuning.

Recommended order:

1. GP-LP / fund-governance enhancement
2. deeper trust hierarchy support
3. acting-in-concert / concert-party logic
4. state-ownership specialization
5. source-quality / corroboration / path-independence modeling
6. public-float / dispersed-ownership explanation layer

## 10. Referenced Validation Artifacts

- small dataset refresh report: `tests/output/ultimate_test_refresh_report_mainline.json`
- enhanced refresh report: `logs/ultimate_controller_enhanced_dataset_trust_working_refresh_summary.json`
- enhanced result summary: `logs/ultimate_controller_enhanced_dataset_trust_working_result_summary.json`
- enhanced 235-target summary: `logs/ultimate_controller_enhanced_target_regression_summary_trust.md`

## 11. Bottom Line

The current unified ultimate-controller algorithm is ready to be treated as the frozen mainline release.

The right next move is not more tuning inside the main version. The right next move is to keep this version stable and put any further structural expansion into a clearly separated next-phase enhancement track.
