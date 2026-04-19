# Ultimate Controller / Country Attribution 典型样本结果导览

更新日期：2026-04-19

本文档基于当前仓库代码、测试、脚本和可用工作数据库整理，用于给 Deep Research、算法排查、前端联调和论文案例章节快速定位代表性样本。本文档不修改算法，也不修改数据库结构。

配套导出文件：

- `exports/research_samples/typical_control_cases.csv`
- `exports/research_samples/typical_control_cases.json`
- `exports/research_samples/typical_control_cases_snapshot.md`

导出文件只包含高研究价值的聚焦样本集合，不是整库导出。

## 1. 文档目标

这份文档主要回答：

- 哪些样本最适合研究 actual controller、ultimate controller、country attribution 的主链路。
- 哪些样本代表正常强股权控制，哪些代表 rollup、VIE、board control、voting right、agreement、nominee、trust、joint control、fallback、public-float-like 等争议场景。
- 看每个样本时应该优先查看哪些输入特征和输出字段。
- 哪些样本适合前端展示排查，哪些样本适合论文案例描述，哪些样本适合 Deep Research 聚焦算法薄弱点。

## 2. 样本来源与可信度分层

### 2.1 小型标准回归样本

来源：

- `ultimate_controller_test_dataset_mainline_working.db`
- `tests/test_ultimate_controller_dataset_regression.py`
- `scripts/run_refresh_on_test_db.py`

用途：

- 最适合作为算法语义的“白盒样本”。
- 样本规模小、预期明确、case group 清晰。
- 适合 Deep Research 先理解当前规则边界。

### 2.2 增强目标回归样本

来源：

- `ultimate_controller_enhanced_dataset_trust_working.db`
- `scripts/build_enhanced_target_regression_table.py`
- `logs/ultimate_controller_enhanced_target_regression_summary_trust.json`

用途：

- 覆盖更接近大库的 target cases。
- 当前 trust working 版本中，增强目标回归摘要显示 235 个 target case 已通过当前预期分类。
- 适合研究 rollup、SPV、trust、mixed control、non-equity control、nominee 和 close competition 的稳定性。

注意：历史 tuned summary 中曾出现过 rollup 偏保守等调参记录。做当前实现研究时，应优先看 trust working 数据和当前代码；历史 summary 可作为算法演进背景。

### 2.3 大库探索样本

来源：

- `scripts/run_large_control_validation.py`
- `tests/output/large_control_validation_*`
- `logs/ultimate_controller_enhanced_dataset_working_result_summary.json`

用途：

- 适合发现 public-float-like、低置信、多候选竞争、异常 fallback 等现象。
- 不应直接当作全部 ground truth，因为它更偏探索和分层抽样。
- 适合 Deep Research 寻找薄弱点和构造后续人工复核样本。

## 3. 典型样本分类总览

| Case group | 代表问题 | 推荐样本 |
|---|---|---|
| `direct_equals_ultimate` / `A_direct_ultimate` | 直接控制人就是实际/最终控制人 | 2001, 461 |
| `rollup_success` / `B_rollup_success` | 直接 holdco 向上穿透到 parent | 2004, 843 |
| `E_spv_lookthrough` | SPV / holding company look-through | 365 |
| `trust_vehicle_lookthrough` | trust vehicle 穿透 | 1418 |
| `joint_control_block` | 共同控制阻断单一 actual controller | 2007 |
| `F_nominee_unknown` / `nominee_beneficial_owner_unknown` | nominee 或 beneficial owner 未披露导致阻断 | 2016, 672, 1908 |
| `fallback_no_meaningful_signal` | 没有足够控制信号，回退注册地 | 2021 |
| `insufficient_evidence_leading_candidate` | 有 leading candidate，但没过 actual gate | 2010 |
| `low_confidence_evidence_weak` | 控制比例或语义存在，但置信度弱 | 2012 |
| `board_control_mixed_rollup` / `J_mixed_control_board` | board_control 成功构成 mixed control | 2023, 685, 10025 |
| `J_mixed_control_voting_right` | voting_right 与股权混合控制 | 530, 10028 |
| `vie_mixed_rollup` / `I_non_equity_vie` | VIE / 协议安排控制 | 2024, 2116 |
| `D_close_competition` | 多候选接近竞争、分散持股 | 96, 401 |
| `public_float_low_confidence` | public-float-like 候选冲突 | 18 |
| `board_control_low_confidence` | board_control 候选未过 gate | 9 |
| `trust_low_confidence_agreement` | trust/agreement 低置信或保护性条款争议 | 20 |

## 4. 推荐重点样本

### 4.1 强股权控制基准

| company_id | company_name | case group | 当前预期结果 | 代表性 |
|---|---|---|---|---|
| 2001 | Orion Consumer Tech Ltd. | `direct_equals_ultimate` | direct/actual/ultimate 均为 Zenith Founder Holdings Ltd.；国家归属 Singapore | 最简单的正向基准，用来确认 direct=actual=ultimate 的写回和展示是否正常 |
| 461 | Boreal Telecom Inc. | `A_direct_ultimate` | direct/actual/leading 均为 Boreal Telecom State Capital Platform；国家归属 Canada | 大库增强样本中的 direct equity 正向基准 |

重点看：

- `control_relationships.is_direct_controller`
- `control_relationships.is_actual_controller`
- `control_relationships.is_ultimate_controller`
- `country_attributions.attribution_layer=direct_controller_country`
- `country_attributions.attribution_type=equity_control`

### 4.2 Rollup / SPV / Holding Company Look-through

| company_id | company_name | case group | 当前预期结果 | 代表性 |
|---|---|---|---|---|
| 2004 | Nova Grid Systems Ltd. | `rollup_success` | direct 为 Nova Grid Holdings Ltd.；actual/ultimate 为 Continental Power Group；`promotion_reason=disclosed_ultimate_parent` | 小型标准 rollup 成功样本 |
| 843 | Pacific Platform Integrated Group Inc. | `B_rollup_success` | direct 为 Pacific Platform Holdings Ltd.；actual 为 Pacific Platform Parent Group；国家归属 USA | 增强样本中的 holding-company treatment |
| 365 | Hanse Components AG | `E_spv_lookthrough` | direct 为 Hanse Components Holdings 10；actual 为 Hanse Components Sovereign Technology Fund；`promotion_reason=beneficial_owner_priority` | SPV/look-through 与 beneficial-owner priority 研究样本 |

重点看：

- `control_relationships.promotion_source_entity_id`
- `control_relationships.promotion_reason`
- `control_relationships.control_chain_depth`
- `control_relationships.control_path`
- `country_attributions.look_through_applied`
- `country_attributions.attribution_layer=ultimate_controller_country`

### 4.3 Trust Vehicle Look-through

| company_id | company_name | case group | 当前预期结果 | 代表性 |
|---|---|---|---|---|
| 1418 | Lingyun Trust International Holdings Ltd. | `trust_vehicle_lookthrough` | direct 为 Lingyun Trust Holdings 18；actual 为 Lingyun Trust Industrial Group；`promotion_reason=disclosed_ultimate_parent` | trust vehicle 可穿透场景，用于研究 trust 与 nominee 的规则差异 |

重点看：

- `shareholder_entities.entity_subtype`
- `shareholder_entities.controller_class`
- `shareholder_structures.look_through_allowed`
- `control_relationships.promotion_reason`
- `tests/test_trust_control_rules.py`

### 4.4 Joint Control 阻断

| company_id | company_name | case group | 当前预期结果 | 代表性 |
|---|---|---|---|---|
| 2007 | Lakeshore E-Commerce Group | `joint_control_block` | 有 direct controller 候选，但没有单一 actual controller；`terminal_failure_reason=joint_control`；国家归属 undetermined | 研究共同控制如何阻断单一实际控制人的标准样本 |

重点看：

- `control_relationships.terminal_failure_reason=joint_control`
- `country_attributions.attribution_type=joint_control`
- `country_attributions.attribution_layer=joint_control_undetermined`
- `country_attributions.country_inference_reason=joint_control_no_single_country`
- `control_relationships.basis` 中的 competing candidates

### 4.5 Nominee / Beneficial Owner Unknown

| company_id | company_name | case group | 当前预期结果 | 代表性 |
|---|---|---|---|---|
| 2016 | Clearwave Media Platform Ltd. | `nominee_beneficial_owner_unknown` | leading candidate 为 Clearwave Nominee Services Ltd.；actual 为空；fallback 到 BVI；`terminal_failure_reason=beneficial_owner_unknown` | 小型标准 nominee 阻断样本 |
| 672 | Taishan Home Digital Holdings Ltd. | `F_nominee_unknown` | leading candidate 为 Taishan Home Nominee Services；actual 为空；fallback 到 China | 增强样本 nominee unknown |
| 1908 | BlueOcean Resources Group Holding Limited | `F_nominee_unknown` | leading candidate 为 BlueOcean Resources Nominee Services；actual 为空；fallback 到 Cayman Islands | 大库增强 nominee robustness 样本 |

重点看：

- `shareholder_structures.relation_type=nominee`
- `shareholder_structures.is_beneficial_control`
- `shareholder_structures.look_through_allowed`
- `shareholder_entities.beneficial_owner_disclosed`
- `control_relationships.semantic_flags`
- `control_relationships.terminal_failure_reason=beneficial_owner_unknown`

### 4.6 Fallback / Insufficient Evidence / Low Confidence

| company_id | company_name | case group | 当前预期结果 | 代表性 |
|---|---|---|---|---|
| 2021 | Frontier Materials Co. | `fallback_no_meaningful_signal` | 没有可靠 controller，国家归属 Canada，`attribution_type=fallback_incorporation` | 干净的 fallback-incorporation baseline |
| 2010 | Silver Peak Consumer Goods Co. | `insufficient_evidence_leading_candidate` | leading candidate 为 Pearl Growth Fund；actual 为空；fallback 到 China | 有候选但证据不足 |
| 2012 | Vertex Smart Manufacturing Ltd. | `low_confidence_evidence_weak` | leading candidate 为 Vertex Industrial Sponsor；actual 为空；fallback 到 Singapore；semantic flags 含 `low_confidence` | 51% 但置信度弱，研究 actual gate 是否过严 |

重点看：

- `control_relationships.terminal_failure_reason`
- `control_relationships.review_status`
- `control_relationships.semantic_flags`
- `control_relationships.aggregated_control_score`
- `control_relationships.terminal_control_score`
- `country_attributions.attribution_type=fallback_incorporation`
- `country_attributions.country_inference_reason=fallback_to_incorporation`

### 4.7 Board Control 成功与失败对照

| company_id | company_name | case group | 当前预期结果 | 代表性 |
|---|---|---|---|---|
| 2023 | Signal Industrial AI Co. | `board_control_mixed_rollup` | direct 为 Signal Industrial Control Platform；actual 为 Mr. Zhao Ming；`attribution_type=mixed_control` | 小型标准 board_control 成功样本 |
| 685 | BlueWave Components Co., Ltd. | `J_mixed_control_board` | direct 为 BlueWave Components Mixed Control Holdings；actual 为 BlueWave Components Sponsor Group；flags 含 `board_control`、`needs_review` | 增强样本 board_control 成功但需关注 review |
| 10025 | Skybridge Data Systems Ltd. 1 | `I_non_equity_board_control` | direct 为 Skybridge Data Control Platform；actual 为 Skybridge Data Ultimate Sponsor；`promotion_reason=beneficial_owner_priority` | 紧凑目标回归样本，适合前端图和 basis 检查 |
| 9 | Mirae Software Advanced Co., Ltd. | `board_control_low_confidence` | leading candidate 为 Sophia Davis 6；actual 为空；fallback 到 South Korea；flags 含 `board_control|low_confidence` | board_control 候选未过 actual gate 的失败对照 |

重点看：

- `shareholder_structures.relation_type=board_control`
- `shareholder_structures.board_seats`
- `shareholder_structures.nomination_rights`
- `control_relationships.control_mode`
- `control_relationships.semantic_flags`
- `control_relationships.basis` 中 power / reliability / disclosure signals

### 4.8 Voting Right / Mixed Control

| company_id | company_name | case group | 当前预期结果 | 代表性 |
|---|---|---|---|---|
| 530 | Summit Digital Global Group Inc. | `J_mixed_control_voting_right` | direct 为 Summit Digital Mixed Control Holdings；actual 为 Summit Digital Sponsor Group；flags 含 `voting_right`、`protective_rights` | 研究 voting right、protective right 与 mixed control 的关键样本 |
| 10028 | Meridian Smart Retail Ltd. 1 | `J_mixed_control_voting_right_new` | direct 为 Meridian Smart Mixed Control Holdings；actual 为 Meridian Smart Sponsor Group；国家归属 Singapore | 紧凑 voting-right 目标回归样本 |

重点看：

- `shareholder_structures.voting_ratio`
- `shareholder_structures.economic_ratio`
- `shareholder_structures.control_basis`
- `shareholder_structures.agreement_scope`
- `control_relationships.control_mode=mixed`
- `control_relationships.semantic_flags` 中 `power_rights`、`protective_rights`、`qualified_protective_rights`

### 4.9 VIE / Non-equity Strong Control

| company_id | company_name | case group | 当前预期结果 | 代表性 |
|---|---|---|---|---|
| 2024 | Jade River Internet Services Ltd. | `vie_mixed_rollup` | direct 为 Jade River WFOE；actual 为 Ms. Chen Rui；flags 含 `vie`、`power_rights`、`economic_benefits`、`exclusive_control_arrangement` | 小型标准 VIE mixed-control 成功样本 |
| 2116 | Yunhe LifeScience Industrial Group Co., Ltd. | `I_non_equity_vie` | direct 为 Yunhe LifeScience Control Platform；actual 为 Yunhe LifeScience Ultimate Sponsor；`attribution_type=mixed_control` | 增强 VIE 成功样本，适合研究 power/economics/exclusivity |

重点看：

- `shareholder_structures.relation_type=vie`
- `shareholder_structures.control_basis`
- `shareholder_structures.relation_metadata`
- `control_relationships.semantic_flags`
- `control_relationships.control_mode`
- `country_attributions.attribution_type=mixed_control`

### 4.10 Close Competition / Public-float-like

| company_id | company_name | case group | 当前预期结果 | 代表性 |
|---|---|---|---|---|
| 96 | Latitude Care Group Holding Limited | `D_close_competition` | leading candidate 为 Latitude Care Sponsor Vehicle；actual 为空；fallback 到 Cayman Islands；`terminal_failure_reason=insufficient_evidence` | 多候选或分散持股候选研究入口 |
| 401 | Crescent Industrial Holdings Inc. | `D_close_competition` | leading candidate 为 Crescent Industrial Sponsor Vehicle；actual 为空；fallback 到 USA | 高股权竞争和分散结构研究入口 |
| 18 | Crescent Digital Group Inc. | `public_float_low_confidence` | leading candidate 为 Public Float - US；actual 为空；fallback 到 USA；`terminal_failure_reason=low_confidence_evidence_weak` | public-float-like 候选是否可能错误上位的重点样本 |
| 20 | Marina Trust Holdings Ltd. | `trust_low_confidence_agreement` | leading candidate 为 Yvonne Teo；actual 为空；fallback 到 Singapore；relation types 含 `agreement|equity` | agreement/protective-rights 与 public-float-like 交互研究样本 |

重点看：

- `control_relationships.controller_name`
- `control_relationships.control_ratio`
- `control_relationships.aggregated_control_score`
- `control_relationships.terminal_failure_reason`
- `control_relationships.basis` 中候选排序、score gap、证据解释
- `exports/research_samples/typical_control_cases.csv` 中 `has_public_float_like`、`has_dispersed_hint`

注意：导出文件中的 `has_public_float_like` 是研究辅助标记，用于快速过滤可能相关样本，不等同于当前数据库中的正式业务字段或 ground truth。

## 5. 建议重点查看的输出字段

### 5.1 `control_relationships`

| 字段 | 研究用途 |
|---|---|
| `controller_entity_id` / `controller_name` | 定位候选控制人是谁 |
| `control_type` | 区分 equity_control、significant_influence、mixed_control 等 |
| `control_ratio` | 当前候选控制比例或综合控制比例 |
| `immediate_control_ratio` | 直接边比例，适合对比 direct vs rollup |
| `aggregated_control_score` | 综合候选分数，适合看候选排序 |
| `terminal_control_score` | 终端控制分数，适合研究 ultimate 选择 |
| `control_path` | 控制路径、路径边、路径得分和路径解释 |
| `is_direct_controller` | 是否被认定为直接控制人 |
| `is_actual_controller` | 当前主流程最重要的实际控制人标记 |
| `is_ultimate_controller` | 最终/兼容标记，常与 actual 搭配看 |
| `control_tier` | candidate/direct/intermediate/ultimate 等层级 |
| `promotion_source_entity_id` | 上推来源实体，研究 rollup 必看 |
| `promotion_reason` | 为什么从 direct 上推到 actual/ultimate |
| `control_chain_depth` | 控制链深度，研究多层穿透必看 |
| `is_terminal_inference` | 是否终止推断 |
| `terminal_failure_reason` | 为什么无法得到 actual controller 或无法继续穿透 |
| `control_mode` | numeric/semantic/mixed，用于区分股权和非股权控制 |
| `semantic_flags` | board_control、vie、agreement、nominee、low_confidence 等语义标签 |
| `basis` | 解释性 payload，Deep Research 最值得看的字段 |
| `review_status` | 是否需要人工复核或存在风险 |

### 5.2 `country_attributions`

| 字段 | 研究用途 |
|---|---|
| `actual_control_country` | 最终输出国家 |
| `attribution_type` | equity_control、mixed_control、joint_control、fallback_incorporation 等 |
| `actual_controller_entity_id` | 国家归属基于哪个 actual controller |
| `direct_controller_entity_id` | 直接控制人 ID，适合看 direct vs actual 差异 |
| `attribution_layer` | direct_controller_country、ultimate_controller_country、fallback_incorporation、joint_control_undetermined |
| `country_inference_reason` | 国家归属原因，定位 fallback 或 joint 的关键 |
| `look_through_applied` | 是否应用穿透 |
| `basis` | 国家归属解释性 payload |
| `source_mode` | 当前来源模式，区分自动/人工/历史结果 |

### 5.3 输入侧字段

| 表 | 字段 | 研究用途 |
|---|---|---|
| `shareholder_structures` | `relation_type` | equity、voting_right、board_control、agreement、vie、nominee 等控制边类型 |
| `shareholder_structures` | `holding_ratio` / `voting_ratio` / `economic_ratio` / `effective_ratio` | 数值控制基础 |
| `shareholder_structures` | `confidence_level` | actual gate 和低置信阻断 |
| `shareholder_structures` | `control_basis` / `agreement_scope` | 语义控制解释来源 |
| `shareholder_structures` | `board_seats` / `nomination_rights` | board_control 证据 |
| `shareholder_structures` | `is_beneficial_control` / `look_through_allowed` | nominee、trust、beneficial owner 穿透 |
| `shareholder_structures` | `termination_signal` | 是否应终止穿透 |
| `shareholder_structures` | `relation_metadata` | VIE、协议、特殊控制结构扩展证据 |
| `shareholder_entities` | `entity_type` / `entity_subtype` | person/company/fund/trust/nominee 等主体类型 |
| `shareholder_entities` | `controller_class` | 实控人类别，影响 rollup 或解释 |
| `shareholder_entities` | `ultimate_owner_hint` | 上推和披露线索 |
| `shareholder_entities` | `beneficial_owner_disclosed` | nominee/trust 是否可穿透的重要依据 |
| `shareholder_entities` | `country` | 控制人国家和国家归属基础 |
| `relationship_sources` | 来源 payload | reliability scoring 和证据质量 |

## 6. 字段如何用于定位典型问题

### 6.1 为什么没能成为 actual controller

优先看：

- `control_relationships.terminal_failure_reason`
- `control_relationships.review_status`
- `control_relationships.semantic_flags`
- `control_relationships.basis`
- `control_relationships.aggregated_control_score`
- `control_relationships.terminal_control_score`
- `basis` 中的 candidate ranking、evidence breakdown、block reason

典型样本：2010、2012、9、18、20。

### 6.2 为什么会 fallback

优先看：

- `country_attributions.attribution_type`
- `country_attributions.attribution_layer`
- `country_attributions.country_inference_reason`
- `country_attributions.actual_controller_entity_id`
- `control_relationships.is_actual_controller`
- `control_relationships.terminal_failure_reason`
- `country_attributions.basis`

典型样本：2021、2010、2012、2016、672、1908、18。

### 6.3 为什么 public float 类候选会上位或进入 leading candidate

优先看：

- `control_relationships.controller_name`
- `control_relationships.control_ratio`
- `control_relationships.aggregated_control_score`
- `control_relationships.basis`
- `control_relationships.terminal_failure_reason`
- `shareholder_entities.entity_type` / `entity_subtype`
- `shareholder_structures.relation_type`
- 导出文件中的 `has_public_float_like` 和 `top_candidate_summary`

典型样本：18、96、401、20。

### 6.4 为什么 board_control / agreement / voting_right 只成了候选没过 gate

优先看：

- `shareholder_structures.confidence_level`
- `shareholder_structures.control_basis`
- `shareholder_structures.agreement_scope`
- `control_relationships.control_mode`
- `control_relationships.semantic_flags`
- `control_relationships.basis`
- `control_relationships.review_status`
- `control_relationships.terminal_failure_reason`

成功对照：2023、685、10025、530、10028。

失败对照：9、20。

## 7. Deep Research 推荐阅读顺序

建议按以下顺序看样本：

1. 正常强股权控制基准：2001、461。
2. 成功 rollup / look-through：2004、843、365。
3. trust vehicle look-through：1418。
4. 非股权或混合控制成功：2023、685、10025、530、10028、2024、2116。
5. fallback 和低置信失败：2021、2010、2012。
6. nominee / beneficial owner unknown 阻断：2016、672、1908。
7. joint control 阻断：2007。
8. public-float-like / close competition / agreement 争议：18、96、401、20、9。

这样排序的好处是：先建立“算法正常工作时应该长什么样”的基准，再看成功穿透，再看非股权成功，最后看最容易争议的失败和边界样本。

## 8. 配套导出字段说明

`exports/research_samples/typical_control_cases.csv` 和 JSON 中每行代表一个公司样本，主要字段包括：

| 字段 | 含义 |
|---|---|
| `source_database` | 样本来自哪个工作 DB |
| `company_id` / `company_name` | 公司标识 |
| `case_group` | 样本分组 |
| `why_representative` | 为什么值得研究 |
| `direct_controller` | 当前 direct controller 摘要 |
| `actual_controller` | 当前 actual controller 摘要 |
| `leading_candidate` | 若无 actual，最主要候选 |
| `actual_control_country` | 当前国家归属 |
| `attribution_type` | 国家归属类型 |
| `attribution_layer` | 国家归属层级 |
| `country_inference_reason` | 国家归属原因 |
| `controller_status` | 控制人识别状态 |
| `terminal_failure_reason` | 未成为 actual 或终止穿透原因 |
| `promotion_reason` | direct 上推到 actual/ultimate 的原因 |
| `look_through_applied` | 是否进行了穿透 |
| `control_modes` | numeric/semantic/mixed 汇总 |
| `relation_types` | 样本涉及的关系类型 |
| `semantic_flags` | 语义控制标签 |
| `has_board_control` / `has_agreement` / `has_voting_right` / `has_vie` / `has_nominee` | 快速过滤语义 case |
| `has_public_float_like` / `has_dispersed_hint` | 研究辅助标记，不是正式业务字段 |
| `top_candidate_summary` | 首要候选摘要 |
| `top_path_summary` | 主要路径摘要 |
| `notes` | 人工整理备注 |

## 9. 需要手工补充或谨慎解释的内容

1. `has_public_float_like` 是导出时基于名称、关系和候选特征整理的研究辅助标记，不是当前 schema 中的正式字段，也不是严格 ground truth。
2. 大库探索样本适合发现问题，但不能替代人工标注。特别是 close competition、public float、agreement/protective rights 需要结合原始数据来源复核。
3. 某些 case group 来自测试和增强目标回归脚本，命名服务于回归验证，不一定等同于论文中的最终分类术语。
4. 如果要写论文案例，建议先用本文档筛选样本，再打开对应 `control_relationships.basis`、`country_attributions.basis` 和原始 `shareholder_structures` 验证叙述。
5. 历史文档中可能有旧字段名或旧算法描述。当前样本解释以 `backend/analysis/control_inference.py` 和 `backend/analysis/ownership_penetration.py` 的当前写回字段为准。

## 10. 最小使用建议

- 给 Deep Research：优先附上本文档、`docs/algorithm_core_code_map.md` 和 `exports/research_samples/typical_control_cases.json`。
- 给前端同学：重点看第 5 节字段说明和第 4 节样本，尤其是 2004、2023、2024、2016、18。
- 给算法同学：重点看第 6、7 节，并回到核心函数 `_actual_control_evidence_block_reason()`、`_promotion_block_reason()`、`_controller_sort_key()`、`_score_semantic_evidence()`。
- 给论文写作：优先使用 2001、2004、2007、2016、2023、2024，再选择 18 或 20 作为边界/争议案例。
- 给数据抓取同学：重点看输入侧字段，尤其是 `relation_type`、`confidence_level`、`control_basis`、`relationship_sources`，这些字段会直接影响候选评分和可解释性。
