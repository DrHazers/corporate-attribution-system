# 原始库副本完整数据库设计说明

本文基于 `company_test_analysis_industry_export_source.db` 编写。该库是 `company_test_analysis_industry.db` 的导出专用副本，本轮没有使用 `company_test_analysis_industry_v2.db` 的数据内容。

## 1. 当前数据库整体设计

当前数据库围绕“企业控制关系识别”和“国家归属分析”设计，整体分成事实输入、辅助证据、算法输出、过程留痕和行业分析几层。

核心事实输入层由三张表组成：

- `companies`：公司主数据和分析入口。
- `shareholder_entities`：控制图中的主体节点。
- `shareholder_structures`：控制图中的关系边。

辅助层由两张对接价值较高的表组成：

- `relationship_sources`：关系边证据来源。
- `entity_aliases`：主体别名。

算法输出层由两张表组成：

- `control_relationships`：控制人和控制链结果。
- `country_attributions`：实际控制国家和归属类型结果。

过程留痕层包括：

- `control_inference_runs`：控制推断运行记录。
- `control_inference_audit_log`：控制推断步骤审计。
- `shareholder_structure_history`：关系边变更历史。
- `annotation_logs`：人工标注和修订日志。

行业分析层包括：

- `business_segments`
- `business_segment_classifications`

这套设计的重点是：输入事实和算法结论分离；控制关系边既能表达传统股权比例，也能表达协议、董事会、表决权、代持、VIE 等复杂控制事实。

## 2. 当前副本表和行数

| 表 | 行数 | 角色 |
| --- | ---: | --- |
| `companies` | 10000 | 公司主数据输入 |
| `shareholder_entities` | 26000 | 控制图节点输入 |
| `shareholder_structures` | 105000 | 控制图边输入 |
| `relationship_sources` | 25016 | 证据来源辅助输入 |
| `entity_aliases` | 50000 | 实体匹配辅助输入 |
| `control_relationships` | 18971 | 控制分析输出 |
| `country_attributions` | 10000 | 国家归属输出 |
| `control_inference_runs` | 0 | 推断运行留痕 |
| `control_inference_audit_log` | 0 | 推断步骤留痕 |
| `shareholder_structure_history` | 12000 | 结构边变更留痕 |
| `business_segments` | 21282 | 行业分析输入 |
| `business_segment_classifications` | 26787 | 行业分类结果 |
| `annotation_logs` | 6941 | 通用人工操作留痕 |

## 3. 各表完整设计说明

### `companies`

业务作用：保存公司主数据，是控制分析和行业分析的入口。

核心字段：

- `id`：公司主键。
- `name`：公司名称。
- `stock_code`：股票代码或内部代码。
- `incorporation_country`：注册地，当前 fallback 国家归属的关键字段。
- `listing_country`：上市地，当前主要用于输出展示和结果表快照。
- `headquarters`：总部所在地。
- `description`：公司描述。

表间关系：

- `shareholder_entities.company_id` 可映射到 `companies.id`。
- `control_relationships.company_id`、`country_attributions.company_id`、`control_inference_runs.company_id` 引用公司。
- `business_segments.company_id` 引用公司。

读写角色：输入表。算法读取公司基本事实，不应由控制分析算法反向生成。

### `shareholder_entities`

业务作用：保存控制图中的主体节点，包括公司、自然人、机构、基金、政府等。

核心字段：

- `id`：主体主键。
- `entity_name`：主体名称。
- `entity_type`：主体类型。
- `country`：主体国家，控制人国家归属优先取该字段。
- `company_id`：可选公司映射。目标公司必须有映射实体。
- `identifier_code`：注册号、统一代码或 LEI。
- `is_listed`：是否上市。
- `entity_subtype`：主体子类型，如 holding_company、spv、family_vehicle。
- `ultimate_owner_hint`：是否提示为终局所有人。
- `look_through_priority`：穿透优先级预留字段。
- `controller_class`：控制人类别，如 natural_person、state、corporate_group。
- `beneficial_owner_disclosed`：是否披露受益所有人。
- `notes`：说明备注。

表间关系：

- 作为 `shareholder_structures.from_entity_id` 和 `shareholder_structures.to_entity_id` 的节点。
- 作为 `control_relationships.controller_entity_id` 的控制主体。
- 作为 `entity_aliases.entity_id` 的被别名对象。

读写角色：输入表。算法读取主体类型、国家、公司映射和终局识别相关字段。

### `shareholder_structures`

业务作用：保存控制图中的关系边，是 ultimate controller / direct controller 分析的核心输入。

核心字段：

- `from_entity_id`：上游控制或持股主体。
- `to_entity_id`：下游被控制或被持股主体。
- `relation_type`：标准关系类型，支持 `equity`、`agreement`、`board_control`、`voting_right`、`nominee`、`vie`、`other`。
- `relation_role`：关系角色，如 ownership、contractual、governance。
- `control_type`：兼容字段，`relation_type` 缺失时可用于推断。
- `holding_ratio`：持股比例。
- `voting_ratio`：表决权比例。
- `economic_ratio`：经济收益比例。
- `effective_control_ratio`：有效控制比例。
- `is_direct`：是否直接关系边。当前控制推断只读取直接边。
- `is_current`：当前是否有效。
- `effective_date` / `expiry_date`：关系生效和失效日期。
- `control_basis`、`agreement_scope`、`board_seats`、`nomination_rights`：语义控制证据。
- `relation_metadata`：JSON 扩展信息，如总董事席位、有效表决权、受益所有人确认等。
- `confidence_level`：证据置信度。
- `is_beneficial_control`：是否受益控制。
- `look_through_allowed`：是否允许向上穿透。
- `termination_signal`：终止或阻断信号。
- `source`、`remarks`：来源和备注。

表间关系：

- 连接两个 `shareholder_entities`。
- 被 `relationship_sources.structure_id` 引用。
- 被 `shareholder_structure_history.structure_id` 引用。

读写角色：输入表。算法读取满足 `is_current = 1`、`is_direct = 1`、日期有效的关系边。

### `relationship_sources`

业务作用：保存关系边的证据来源。

核心字段：

- `structure_id`：关联的结构边。
- `source_type`：来源类型，如 annual_report、filing、web、manual。
- `source_name`：来源名称。
- `source_url`：来源链接。
- `source_date`：来源日期。
- `excerpt`：证据摘录。
- `confidence_level`：来源置信度。

表间关系：

- 多条来源可关联一条 `shareholder_structures`。

读写角色：可选辅助输入表。当前核心算法不直接读取它打分，但对人工复核、论文证据和后续可信度增强有价值。

### `entity_aliases`

业务作用：保存主体别名。

核心字段：

- `entity_id`：关联主体。
- `alias_name`：别名。
- `alias_type`：别名类型，如 english、chinese、short_name、old_name。
- `is_primary`：是否主别名。

表间关系：

- 多条别名可关联一个 `shareholder_entities` 主体。

读写角色：可选辅助输入表。当前核心算法不直接读取，但有助于抓取、匹配和去重。

### `control_relationships`

业务作用：保存控制分析输出结果。

核心字段：

- `company_id`：目标公司。
- `controller_entity_id`：控制主体。
- `controller_name` / `controller_type`：控制主体快照。
- `control_type`：控制类型，如 equity_control、agreement_control、mixed_control、joint_control。
- `control_ratio`：控制比例或控制得分百分比。
- `control_path`：控制路径 JSON。
- `is_actual_controller`：旧兼容字段，v2 语义中对齐 ultimate controller。
- `control_tier`：direct、intermediate、ultimate、candidate。
- `is_direct_controller` / `is_intermediate_controller` / `is_ultimate_controller`：层级标记。
- `promotion_source_entity_id` / `promotion_reason`：从下层主体上卷到上层主体的来源和原因。
- `control_chain_depth`：控制链深度。
- `is_terminal_inference`：是否属于终局推断链条。
- `terminal_failure_reason`：未能确认终局的原因。
- `immediate_control_ratio`：直接层控制比例。
- `aggregated_control_score`：聚合控制得分。
- `terminal_control_score`：终局控制得分。
- `inference_run_id`：关联推断运行。
- `basis`：结果依据 JSON。
- `control_mode`：numeric、semantic、mixed。
- `semantic_flags`：语义标签 JSON。
- `review_status`：复核状态。

表间关系：

- 引用 `companies`、`shareholder_entities` 和 `control_inference_runs`。

读写角色：算法输出表。不要作为基础输入导出给 GPT。

### `country_attributions`

业务作用：保存国家归属结果。

核心字段：

- `company_id`：目标公司。
- `incorporation_country` / `listing_country`：公司国家字段快照。
- `actual_control_country`：实际控制国家。
- `attribution_type`：归属类型，如 equity_control、mixed_control、fallback_incorporation。
- `actual_controller_entity_id`：终局实际控制主体。
- `direct_controller_entity_id`：直接控制主体。
- `attribution_layer`：归属层级，如 direct_controller_country、ultimate_controller_country。
- `country_inference_reason`：国家推断原因。
- `look_through_applied`：是否发生向上穿透。
- `basis`：归属依据 JSON。
- `is_manual`：是否人工记录。
- `source_mode`：control_chain_analysis、fallback_rule、manual_override、hybrid。
- `inference_run_id`：关联推断运行。

表间关系：

- 引用 `companies` 和 `control_inference_runs`。

读写角色：算法输出表或人工 override 表。不要作为基础输入模板。

### `control_inference_runs`

业务作用：记录一次控制推断运行。

核心字段：

- `company_id`
- `run_started_at` / `run_finished_at`
- `engine_version` / `engine_mode`
- `max_depth`
- `disclosure_threshold` / `significant_threshold` / `control_threshold`
- `terminal_identification_enabled`
- `look_through_policy`
- `result_status`
- `summary_json`
- `notes`

表间关系：

- 被 `control_relationships`、`country_attributions`、`control_inference_audit_log` 引用。

读写角色：过程留痕表。由算法运行创建和更新。

### `control_inference_audit_log`

业务作用：记录控制推断步骤审计。

核心字段：

- `inference_run_id`
- `company_id`
- `step_no`
- `from_entity_id` / `to_entity_id`
- `action_type`
- `action_reason`
- `score_before` / `score_after`
- `details_json`
- `created_at`

表间关系：

- 依附于 `control_inference_runs`。

读写角色：过程留痕表。用于解释和审计，不属于输入数据。

### `shareholder_structure_history`

业务作用：保存关系边的变更历史。

核心字段：

- `structure_id`
- `change_type`
- `old_value`
- `new_value`
- `change_reason`
- `changed_by`
- `created_at`

表间关系：

- 依附于 `shareholder_structures`。

读写角色：过程留痕表。由 CRUD 或导入整理流程写入。

### `business_segments` 和 `business_segment_classifications`

业务作用：支持行业分析模块。

`business_segments` 保存公司业务分部事实；`business_segment_classifications` 保存业务分部行业分类结果。

读写角色：行业分析相关，不属于当前控制链 CSV 必要输入。

### `annotation_logs`

业务作用：保存人工标注、修订和原因。

读写角色：通用操作留痕，不属于控制链输入。

## 4. 表间关系说明

主要关系如下：

- `companies.id` -> `shareholder_entities.company_id`
- `shareholder_entities.id` -> `shareholder_structures.from_entity_id`
- `shareholder_entities.id` -> `shareholder_structures.to_entity_id`
- `shareholder_structures.id` -> `relationship_sources.structure_id`
- `shareholder_structures.id` -> `shareholder_structure_history.structure_id`
- `shareholder_entities.id` -> `entity_aliases.entity_id`
- `companies.id` -> `control_relationships.company_id`
- `shareholder_entities.id` -> `control_relationships.controller_entity_id`
- `companies.id` -> `country_attributions.company_id`
- `control_inference_runs.id` -> `control_relationships.inference_run_id`
- `control_inference_runs.id` -> `country_attributions.inference_run_id`
- `control_inference_runs.id` -> `control_inference_audit_log.inference_run_id`
- `companies.id` -> `business_segments.company_id`
- `business_segments.id` -> `business_segment_classifications.business_segment_id`

控制图的核心是 `shareholder_entities` 和 `shareholder_structures`：节点表示主体，边表示控制关系。

## 5. 输入、输出、留痕的数据流

### 输入进入分析

1. 上层以 `company_id` 请求分析。
2. 系统读取 `companies`，确认目标公司存在。
3. 系统通过 `shareholder_entities.company_id = companies.id` 找到目标公司的实体节点。
4. 系统读取 `shareholder_entities` 构建节点表。
5. 系统读取 `shareholder_structures` 中满足条件的边：
   - `is_current = 1`
   - `is_direct = 1`
   - `effective_date` 为空或不晚于分析日
   - `expiry_date` 为空或不早于分析日
6. 每条边根据 `relation_type`、比例字段、语义文本、置信度和阻断字段转换成控制因子。

### 结果写回

1. 算法搜索从目标公司向上的控制路径。
2. 算法聚合同一候选主体的多条路径得分。
3. 算法识别 direct controller、intermediate controller、ultimate controller、joint control、leading candidate 或 fallback。
4. 结果写入 `control_relationships`。
5. 国家归属写入 `country_attributions`。

### 过程留痕

1. 一次 refresh 可创建 `control_inference_runs`。
2. 关键步骤可写入 `control_inference_audit_log`。
3. 结构边变更写入 `shareholder_structure_history`。
4. 人工修订写入 `annotation_logs`。

## 6. direct controller / ultimate controller 字段设计意义

### 主体层字段

| 字段 | 设计意义 |
| --- | --- |
| `entity_subtype` | 区分 operating company、holding company、SPV、shell company、family vehicle 等，辅助上卷判断 |
| `ultimate_owner_hint` | 数据源明确披露终局所有人时，提示算法在该主体停止 |
| `look_through_priority` | 为后续更细粒度穿透策略预留 |
| `controller_class` | 区分 natural_person、state、corporate_group、fund_complex 等终局类别 |
| `beneficial_owner_disclosed` | 代持和受益所有人场景中判断是否继续穿透 |

### 关系边字段

| 字段 | 设计意义 |
| --- | --- |
| `voting_ratio` | 处理表决权委托、同股不同权和投票权控制 |
| `economic_ratio` | 处理收益权、VIE 经济利益和可变回报 |
| `effective_control_ratio` | 表达最终可用于控制判断的比例 |
| `is_beneficial_control` | 标记受益控制事实 |
| `look_through_allowed` | 控制某条边是否允许继续向上穿透 |
| `termination_signal` | 表达 joint、unknown beneficial owner、protective rights 等阻断信号 |
| `control_basis` / `agreement_scope` / `nomination_rights` | 为协议、董事会、VIE、表决权等提供文本证据 |
| `relation_metadata` | 承载总董事席位、有效表决权、受益人确认等扩展结构化信息 |
| `confidence_level` | 将证据质量记录到分析结果解释中 |

### 结果层字段

| 字段 | 设计意义 |
| --- | --- |
| `control_tier` | 明确 direct、intermediate、ultimate、candidate 层级 |
| `is_direct_controller` | 标记直接控制人 |
| `is_intermediate_controller` | 标记上卷路径中的中间控制主体 |
| `is_ultimate_controller` | 标记最终实际控制人 |
| `promotion_source_entity_id` | 记录从哪个下层主体继续向上穿透 |
| `promotion_reason` | 记录上卷原因 |
| `control_chain_depth` | 记录控制链深度 |
| `terminal_failure_reason` | 记录无法终局确认的原因 |
| `aggregated_control_score` | 记录聚合后的候选控制得分 |
| `terminal_control_score` | 记录终局控制得分 |

### 国家归属字段

| 字段 | 设计意义 |
| --- | --- |
| `actual_controller_entity_id` | 国家归属对应的终局实际控制主体 |
| `direct_controller_entity_id` | 直接控制主体 |
| `attribution_layer` | 说明国家来自直接控制人、终局控制人、注册地 fallback 或共同控制不确定 |
| `country_inference_reason` | 记录国家推断理由 |
| `look_through_applied` | 标记是否发生向上穿透 |
| `source_mode` | 区分控制链分析、fallback、人工覆盖和混合来源 |

## 7. 现实对接中必须有的字段

最小可落地必须字段：

- `companies.id`
- `companies.name`
- `companies.incorporation_country`
- `shareholder_entities.id`
- `shareholder_entities.entity_name`
- `shareholder_entities.entity_type`
- 目标公司实体的 `shareholder_entities.company_id`
- `shareholder_structures.id`
- `shareholder_structures.from_entity_id`
- `shareholder_structures.to_entity_id`
- `shareholder_structures.is_direct`
- `shareholder_structures.is_current`
- 股权边的 `shareholder_structures.holding_ratio`

强烈建议字段：

- `companies.stock_code`
- `companies.listing_country`
- `shareholder_entities.country`
- `shareholder_entities.entity_subtype`
- `shareholder_entities.controller_class`
- `shareholder_structures.relation_type`
- `shareholder_structures.control_type`
- `shareholder_structures.voting_ratio`
- `shareholder_structures.effective_control_ratio`
- `shareholder_structures.effective_date`
- `shareholder_structures.expiry_date`
- `shareholder_structures.confidence_level`

复杂控制场景建议字段：

- `shareholder_structures.control_basis`
- `shareholder_structures.agreement_scope`
- `shareholder_structures.board_seats`
- `shareholder_structures.nomination_rights`
- `shareholder_structures.relation_metadata`
- `shareholder_structures.is_beneficial_control`
- `shareholder_structures.look_through_allowed`
- `shareholder_structures.termination_signal`
- `shareholder_entities.ultimate_owner_hint`
- `shareholder_entities.beneficial_owner_disclosed`

## 8. 可为空字段和降级判断

很多字段允许为空，是为了适配现实抓取数据不完整的情况。当前算法按字段完整程度降级：

| 缺失情况 | 降级行为 |
| --- | --- |
| 目标公司没有映射实体 | 无法从公司进入控制图，分析失败或返回缺失映射 |
| 没有有效结构边 | 无法识别控制人，国家归属 fallback 到注册地 |
| 股权边没有 `holding_ratio` 或 `effective_control_ratio` | 该股权边无法形成有效数值控制因子 |
| `relation_type` 缺失 | 尝试从 `control_type`、`holding_ratio`、`remarks` 推断 |
| 非股权边缺少语义证据 | 得分偏弱，可能标记 `needs_review` |
| `country` 缺失 | 尝试取该主体映射公司的 `incorporation_country`，再 fallback 到目标公司注册地 |
| `effective_date` / `expiry_date` 为空 | 视为无日期限制 |
| `is_current = 0` | 该边被过滤 |
| `is_direct = 0` | 当前控制推断不读取该边 |
| nominee 未披露受益所有人 | 可能阻断为 `nominee_without_disclosure` |
| joint control 信号明确 | 不输出唯一 ultimate controller，国家可能为 `undetermined` |

## 9. 论文/系统说明可用总结

当前数据库采用“公司主数据、控制主体节点、控制关系边、算法结果、过程留痕”的分层设计。输入层通过 `companies`、`shareholder_entities` 和 `shareholder_structures` 将企业控制结构抽象为图模型，其中主体表表达公司、自然人、机构、基金和政府等节点，结构表表达股权、协议、董事会、表决权、代持和 VIE 等边。该设计既支持传统股权穿透，也支持复杂语义控制关系的表达。

输出层通过 `control_relationships` 和 `country_attributions` 分别保存控制链识别结果和国家归属结果，并通过 direct、intermediate、ultimate 等层级字段区分直接控制人和最终实际控制人。过程留痕层通过运行记录和审计日志保存分析参数、阈值、上卷、阻断和终局确认过程，为结果解释、人工复核和论文复现提供依据。

整体上，该数据库设计兼顾最小落地和增强扩展：当数据只有基础持股比例时，可以完成基础股权穿透和注册地 fallback；当数据补充了协议、董事会、VIE、代持、受益所有人和终局主体特征后，可以进一步支持 mixed control、joint control、nominee、SPV、holding company 和 ultimate controller 的细粒度识别。
