# PostgreSQL Demo Refresh Report

## Target
- Database: `postgresql+psycopg://postgres:***@localhost:5432/corp_attribution_system`
- Duration seconds: 147.423

## Pre-refresh Input Counts
- companies: 10041
- shareholder_entities: 27206
- shareholder_structures: 104134

## Cleared Output Counts
- control_inference_audit_log: 0
- control_relationships: 0
- country_attributions: 0
- control_inference_runs: 0

## Refresh Outcome
- Processed companies: 10041
- Successful refresh companies: 10041
- Failed companies: 0

## Post-refresh Output Counts
- control_inference_runs: 10041
- control_relationships: 19140
- country_attributions: 10041
- control_inference_audit_log: 23193

## Attribution Type Distribution
- fallback_incorporation: 7873
- equity_control: 1470
- agreement_control: 291
- mixed_control: 221
- board_control: 162
- joint_control: 24

## Control Type Distribution
- equity_control: 9500
- significant_influence: 8741
- agreement_control: 358
- mixed_control: 276
- board_control: 264
- joint_control: 1

## Country Attribution Coverage
- Companies without country_attributions: 0

## Failures
- None
