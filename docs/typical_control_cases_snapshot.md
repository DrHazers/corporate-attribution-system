# Typical Control Cases Snapshot

更新日期：2026-04-19

本文件是 `exports/research_samples/` 导出样本的轻量文档快照。由于当前仓库 `.gitignore` 忽略 `exports/` 目录，CSV/JSON 适合本地 Deep Research 使用，本文件适合长期纳入项目文档。

完整导出：

- `exports/research_samples/typical_control_cases.csv`
- `exports/research_samples/typical_control_cases.json`
- `exports/research_samples/typical_control_cases_snapshot.md`

## 样本快照

| company_id | company_name | case_group | direct_controller | actual_controller | country | attribution_type | terminal_failure_reason | promotion_reason | relation_types | semantic_flags | 研究价值 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2001 | Orion Consumer Tech Ltd. | `direct_equals_ultimate` | Zenith Founder Holdings Ltd. | Zenith Founder Holdings Ltd. | Singapore | `equity_control` |  |  | equity |  | direct=actual=ultimate 基准 |
| 2004 | Nova Grid Systems Ltd. | `rollup_success` | Nova Grid Holdings Ltd. | Continental Power Group | China | `equity_control` |  | `disclosed_ultimate_parent` | equity |  | holding-company rollup |
| 2007 | Lakeshore E-Commerce Group | `joint_control_block` | Lakeshore Holdings Ltd. |  | undetermined | `joint_control` | `joint_control` |  | equity |  | 共同控制阻断 |
| 2010 | Silver Peak Consumer Goods Co. | `insufficient_evidence_leading_candidate` |  |  | China | `fallback_incorporation` | `insufficient_evidence` |  | equity |  | 有 leading candidate 但证据不足 |
| 2012 | Vertex Smart Manufacturing Ltd. | `low_confidence_evidence_weak` |  |  | Singapore | `fallback_incorporation` | `low_confidence_evidence_weak` |  | equity | `evidence_insufficient`, `low_confidence` | 低置信 actual gate |
| 2016 | Clearwave Media Platform Ltd. | `nominee_beneficial_owner_unknown` |  |  | BVI | `fallback_incorporation` | `beneficial_owner_unknown` |  | equity, nominee | nominee / beneficial owner unknown | nominee 阻断 |
| 2021 | Frontier Materials Co. | `fallback_no_meaningful_signal` |  |  | Canada | `fallback_incorporation` |  |  | equity |  | 无可靠控制信号 fallback |
| 2023 | Signal Industrial AI Co. | `board_control_mixed_rollup` | Signal Industrial Control Platform Ltd. | Mr. Zhao Ming | China | `mixed_control` |  | `beneficial_owner_priority` | board_control, equity | `board_control` | board_control mixed-control 成功 |
| 2024 | Jade River Internet Services Ltd. | `vie_mixed_rollup` | Jade River WFOE Co., Ltd. | Ms. Chen Rui | China | `mixed_control` |  | `beneficial_owner_priority` | equity, vie | VIE power/economics/exclusivity | VIE mixed-control 成功 |
| 461 | Boreal Telecom Inc. | `A_direct_ultimate` | Boreal Telecom State Capital Platform | Boreal Telecom State Capital Platform | Canada | `equity_control` |  |  | equity |  | 增强库 direct equity 基准 |
| 365 | Hanse Components AG | `E_spv_lookthrough` | Hanse Components Holdings 10 | Hanse Components Sovereign Technology Fund | Germany | `equity_control` |  | `beneficial_owner_priority` | equity |  | SPV / beneficial-owner priority |
| 843 | Pacific Platform Integrated Group Inc. | `B_rollup_success` | Pacific Platform Holdings Ltd. | Pacific Platform Parent Group | USA | `equity_control` |  | `disclosed_ultimate_parent` | equity |  | 增强库 rollup success |
| 1418 | Lingyun Trust International Holdings Ltd. | `trust_vehicle_lookthrough` | Lingyun Trust Holdings 18 | Lingyun Trust Industrial Group | China | `equity_control` |  | `disclosed_ultimate_parent` | equity |  | trust vehicle look-through |
| 530 | Summit Digital Global Group Inc. | `J_mixed_control_voting_right` | Summit Digital Mixed Control Holdings | Summit Digital Sponsor Group | USA | `mixed_control` |  | `disclosed_ultimate_parent` | equity, voting_right | voting_right / protective_rights | voting_right mixed-control |
| 685 | BlueWave Components Co., Ltd. | `J_mixed_control_board` | BlueWave Components Mixed Control Holdings | BlueWave Components Sponsor Group | South Korea | `mixed_control` |  | `disclosed_ultimate_parent` | board_control, equity | `board_control`, `needs_review` | board_control 成功但需关注 review |
| 2116 | Yunhe LifeScience Industrial Group Co., Ltd. | `I_non_equity_vie` | Yunhe LifeScience Control Platform | Yunhe LifeScience Ultimate Sponsor | China | `mixed_control` |  | `disclosed_ultimate_parent` | equity, vie | VIE power/economics/exclusivity | 增强库 VIE 成功 |
| 10025 | Skybridge Data Systems Ltd. 1 | `I_non_equity_board_control` | Skybridge Data Control Platform | Skybridge Data Ultimate Sponsor | Singapore | `mixed_control` |  | `beneficial_owner_priority` | board_control, equity | `board_control` | 紧凑 board-control 回归样本 |
| 10028 | Meridian Smart Retail Ltd. 1 | `J_mixed_control_voting_right_new` | Meridian Smart Mixed Control Holdings | Meridian Smart Sponsor Group | Singapore | `mixed_control` |  | `disclosed_ultimate_parent` | equity, voting_right | voting_right / protective_rights | 紧凑 voting-right 回归样本 |
| 672 | Taishan Home Digital Holdings Ltd. | `F_nominee_unknown` |  |  | China | `fallback_incorporation` | `beneficial_owner_unknown` |  | equity, nominee | nominee / beneficial_owner_unknown | 增强库 nominee fallback |
| 1908 | BlueOcean Resources Group Holding Limited | `F_nominee_unknown` |  |  | Cayman Islands | `fallback_incorporation` | `beneficial_owner_unknown` |  | equity, nominee | nominee / beneficial_owner_unknown | nominee robustness |
| 96 | Latitude Care Group Holding Limited | `D_close_competition` |  |  | Cayman Islands | `fallback_incorporation` | `insufficient_evidence` |  | equity | `low_confidence` | close competition / dispersed ownership |
| 401 | Crescent Industrial Holdings Inc. | `D_close_competition` |  |  | USA | `fallback_incorporation` | `insufficient_evidence` |  | equity |  | 高股权竞争 / 分散结构 |
| 9 | Mirae Software Advanced Co., Ltd. | `board_control_low_confidence` |  |  | South Korea | `fallback_incorporation` | `low_confidence_evidence_weak` |  | board_control, equity | `board_control`, `low_confidence` | board_control 失败对照 |
| 18 | Crescent Digital Group Inc. | `public_float_low_confidence` |  |  | USA | `fallback_incorporation` | `low_confidence_evidence_weak` |  | equity | `low_confidence` | public-float-like 候选冲突 |
| 20 | Marina Trust Holdings Ltd. | `trust_low_confidence_agreement` |  |  | Singapore | `fallback_incorporation` | `low_confidence_evidence_weak` |  | agreement, equity | `agreement`, `low_confidence` | trust/agreement 低置信边界 |

## 使用提示

- 研究 actual controller：优先看 `control_relationships.is_actual_controller`、`promotion_reason`、`terminal_failure_reason`、`basis`。
- 研究国家归属：优先看 `country_attributions.attribution_type`、`attribution_layer`、`country_inference_reason`、`basis`。
- 研究非股权控制：优先看 board_control、voting_right、agreement、VIE 样本。
- 研究争议边界：优先看 9、18、20、96、401、2012、2016。
