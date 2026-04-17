# Reliability Integration Design v1.1

This note describes the v1.1 integration layer for the unified control inference
engine. It does not change the database schema, frontend contracts, or runtime
configuration files. The goal is to make reliability a first-class input to edge,
path, candidate, and actual-controller decisions while preserving the v1 behavior
for the key regression scenarios.

## Scope

v1 already scores semantic control evidence across:

- Power
- Economics
- Exclusivity / irrevocability
- Disclosure / beneficial ownership
- Reliability / confidence

The remaining gap was that reliability was mostly explanatory inside
`evidence_breakdown`, while path confidence still came from the legacy
`confidence_level` mapping. v1.1 replaces that split with a single edge-level
reliability score that feeds path and candidate confidence.

## Edge Reliability

Each supported relationship edge now receives an `EdgeReliabilityScore`:

- `reliability_score`: final 0..1 score used as the edge `confidence_weight`.
- `confidence_adjustment`: currently equal to `reliability_score` for backward
  compatibility with v1 semantic payloads.
- `flags`: reliability-related flags such as `low_confidence`,
  `unknown_confidence`, `thin_semantic_evidence`,
  `nominee_without_disclosure_risk`, `beneficial_owner_unknown`,
  `look_through_not_allowed`, `protective_rights`, and
  `evidence_insufficient`.
- `breakdown`: structured explanation with the base confidence, adjustments,
  caps, matched signals, metadata keys, source count, and notes.

The score starts from the legacy confidence map:

- high: 0.90
- medium: 0.70
- unknown: 0.60
- low: 0.40

It can then move up or down based on evidence quality:

- relation metadata presence and richness
- control basis richness
- agreement scope richness
- nomination rights text
- textual evidence richness
- relationship source records, excerpts, source references, and source
  confidence levels
- disclosed beneficial owner or explicit beneficial-owner control text
- nominee without disclosure risk
- beneficial owner unknown / undisclosed signals
- look-through prohibition
- termination signals
- protective rights
- evidence-insufficient markers

Blocking signals keep their blocking semantics. They may also cap or reduce
reliability, but the cap is not the only enforcement mechanism. Promotion and
actual-controller gates still read explicit block reasons such as
`nominee_without_disclosure`, `beneficial_owner_unknown`,
`look_through_not_allowed`, `protective_right_only`, and
`evidence_insufficient`.

## Path Confidence

Path confidence is the multiplicative product of edge reliability:

`path_confidence = product(edge.reliability_score)`

This keeps the model simple and explainable:

- a low-reliability edge drags down the whole path as the weakest link
- multi-layer paths compound uncertainty naturally
- high semantic strength and low evidence reliability remain distinct signals

The existing `PathState.conf_prod` field is retained for compatibility, but its
input is now unified edge reliability rather than a separate confidence-level
lookup.

## Candidate Confidence

Candidate `total_confidence` is now a path-score-weighted average of unified path
confidence:

`candidate_confidence = sum(path_score * path_confidence) / sum(path_score)`

When a candidate has multiple meaningful, reliable paths, v1.1 applies a small
corroboration boost. The boost is capped and only applies to paths that are both
substantive and above the actual-controller confidence floor. This lets multiple
independent paths modestly improve confidence without changing control strength.

Candidate confidence now reflects:

- semantic strength of each path
- edge reliability of each segment
- compounded uncertainty in multi-hop chains
- whether multiple paths corroborate the same candidate
- nominee, beneficial-owner, disclosure, and weak-evidence risks surfaced as
  reliability flags

## Actual / Ultimate Gates

The existing conservative gate for barely-controlling low-confidence candidates
is retained:

- total score is only slightly above the control threshold
- total confidence is below the actual-controller confidence floor
- output remains a leading candidate, not direct / actual controller

v1.1 extends this gate to semantic and mixed-control candidates. If a semantic or
mixed candidate is below the unified confidence floor, it is blocked from direct
or actual output even if semantic strength is high. This prevents "strong words,
thin proof" paths from becoming actual controllers too easily.

The gate remains conservative:

- thin-majority, low-reliability candidates stay blocked
- strong VIE paths with strong reliability still roll up
- nominee without disclosure and beneficial-owner unknown remain hard blockers
- joint control remains a hard no-single-controller result
- fallback behavior is unchanged when no controlling candidate survives

## Compatibility Notes

No schema changes are required. The persisted payloads reuse existing JSON
fields and add explanatory reliability fields inside path edge payloads and
basis payloads.

The legacy confidence-level mapping is not deleted. It is now the base prior for
edge reliability. The old path and candidate logic is absorbed by the new score:
`confidence_weight` still exists, but it now means "edge reliability score".

Future refinements can tune source-quality tiers, distinguish audited filings
from informal text, split reliability by evidence dimension, or externalize
weights into configuration once the behavior is stable.
