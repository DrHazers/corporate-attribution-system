# 当前数据库结构与数据分层说明

本文档基于当前仓库中的真实实现整理，主要核对范围包括：

- `backend/models/`
- `backend/schemas/`
- `backend/crud/`
- `backend/api/`
- `backend/analysis/`
- `backend/database.py`
- `backend/database_config.py`
- `scripts/upgrade_db_to_v2.py`
- `scripts/verify_db_v2.py`
- `scripts/import_raw_dataset.py`
- `docs/database_full_field_reference.md`
- `docs/full_database_design_v2.md`
- `docs/industry_analysis_database_structure.md`

若历史文档、设计设想与当前代码不一致，应以当前代码为准。

## 1. 当前数据库总体设计思想

### 1.1 当前是否采用分层方式

从当前模型、分析写回逻辑和前端读取方式看，当前数据库设计确实可以概括为四层：

- 基础事实层
- 算法结果层
- 产业分析扩展层
- 人工征订 / 留痕层

对应关系大致如下：

- 基础事实层：`companies`、`shareholder_entities`、`shareholder_structures`、`relationship_sources`、`entity_aliases`
- 算法结果层：`control_relationships`、`country_attributions`
- 产业分析扩展层：`business_segments`、`business_segment_classifications`
- 人工征订 / 留痕层：`annotation_logs`、`manual_control_overrides`

同时，当前还存在两个“运行审计层”表：

- `control_inference_runs`
- `control_inference_audit_log`

它们不属于基础事实，也不属于最终业务主结果，更接近算法运行留痕。

### 1.2 各层解决什么问题

- 基础事实层解决“企业是谁、控制关系原始事实是什么、业务线原始事实是什么”的问题。
- 算法结果层解决“基于事实推断出的控制关系和国别归属是什么”的问题。
- 产业分析扩展层解决“业务线被映射成什么产业分类”的问题。
- 人工征订 / 留痕层解决“人工是否确认、改动了什么、为什么改”的问题。

### 1.3 为什么不把原始事实、算法结果和人工修订混在一张表

当前代码体现出的设计理由主要有三点。

- 原始事实与算法结果的来源不同。  
  `shareholder_structures`、`business_segments` 是输入事实，`control_relationships`、`country_attributions`、`business_segment_classifications` 是计算或映射结果。

- 自动结果可能会被 refresh / recompute 覆盖。  
  例如 `backend/analysis/ownership_penetration.py` 中的 `_apply_unified_company_analysis_records()` 会删除旧自动结果并重写。如果把输入事实和输出结果混在同表，会让数据语义混乱。

- 人工修订需要留痕且不能污染原始事实。  
  例如 `backend/analysis/manual_control_override.py` 和 `backend/crud/annotation_log.py` 都体现出当前系统希望把人工确认、覆盖、恢复动作与自动结果分离。

因此论文里更适合表述为：

- 系统采用“事实输入与分析结果分离、自动结果与人工修订分离”的数据库设计思路。

## 2. 当前核心数据表清单

### 2.1 用户要求覆盖的核心表

- `companies`
- `shareholder_entities`
- `shareholder_structures`
- `relationship_sources`
- `entity_aliases`
- `shareholder_structure_history`
- `control_relationships`
- `country_attributions`
- `business_segments`
- `business_segment_classifications`
- `annotation_logs`

### 2.2 当前还存在且与主业务直接相关的补充表

- `control_inference_runs`
- `control_inference_audit_log`
- `manual_control_overrides`

这三张表在当前仓库中都已被实际使用，不应忽略。

## 3. 每张表的详细说明

### 3.1 `companies`

定位与用途：

- 公司主表，控制分析和产业分析共同的入口表。

主要字段：

- `id`：主键
- `name`：公司名称
- `stock_code`：唯一股票代码/公司代码
- `incorporation_country`：注册地
- `listing_country`：上市地
- `headquarters`：总部所在地
- `description`：公司简介

关联关系：

- 主键：`id`
- 与 `shareholder_entities.company_id` 一对多
- 与 `control_relationships.company_id` 一对多
- 与 `country_attributions.company_id` 一对多
- 与 `control_inference_runs.company_id` 一对多
- 与 `business_segments.company_id` 一对多

字段类型划分：

- 基础输入字段：`name`、`stock_code`、`incorporation_country`、`listing_country`、`headquarters`
- 展示/说明字段：`description`
- 当前算法直接使用字段：`incorporation_country`

当前存在但主算法未高频使用的字段：

- `listing_country`
- `headquarters`
- `description`

其中 `listing_country` 和 `headquarters` 当前主要用于展示或结果快照，不是 unified 控制国别判定主规则。

对应实现文件：

- `backend/models/company.py`
- `backend/crud/company.py`
- `backend/api/company.py`

### 3.2 `shareholder_entities`

定位与用途：

- 控制网络中的节点表，统一表示公司、自然人、机构、基金、政府等主体。

主要字段：

- `id`
- `entity_name`
- `entity_type`
- `country`
- `company_id`
- `identifier_code`
- `is_listed`
- `entity_subtype`
- `ultimate_owner_hint`
- `look_through_priority`
- `controller_class`
- `beneficial_owner_disclosed`
- `notes`
- `created_at`
- `updated_at`

关联关系：

- 主键：`id`
- 外键：`company_id -> companies.id`
- 被 `shareholder_structures.from_entity_id`、`shareholder_structures.to_entity_id` 引用
- 被 `control_relationships.controller_entity_id`、`promotion_source_entity_id` 引用
- 被 `entity_aliases.entity_id` 引用

字段类型划分：

- 基础输入字段：`entity_name`、`entity_type`、`country`、`company_id`
- 算法增强输入字段：`entity_subtype`、`ultimate_owner_hint`、`look_through_priority`、`controller_class`、`beneficial_owner_disclosed`
- 展示/辅助字段：`identifier_code`、`is_listed`、`notes`

当前真实使用情况：

- `company_id` 是公司进入控制图的映射关键字段，`backend/crud/shareholder.py:get_entity_by_company_id()` 会用它找到目标公司对应实体。
- `country`、`company_id` 和映射公司注册地共同参与控制主体国别解析。
- `entity_subtype`、`controller_class`、`ultimate_owner_hint`、`beneficial_owner_disclosed` 当前 unified 算法会实际读取。

当前存在但算法或接口暂未高频使用的字段：

- `identifier_code`
- `is_listed`
- `notes`

对应实现文件：

- `backend/models/shareholder.py`
- `backend/schemas/shareholder.py`
- `backend/crud/shareholder.py`

### 3.3 `shareholder_structures`

定位与用途：

- 控制网络的边表，是控制分析的核心事实输入。

主要字段：

- `id`
- `from_entity_id`
- `to_entity_id`
- `holding_ratio`
- `voting_ratio`
- `economic_ratio`
- `is_direct`
- `control_type`
- `relation_type`
- `has_numeric_ratio`
- `is_beneficial_control`
- `look_through_allowed`
- `termination_signal`
- `effective_control_ratio`
- `relation_role`
- `control_basis`
- `board_seats`
- `nomination_rights`
- `agreement_scope`
- `relation_metadata`
- `relation_priority`
- `confidence_level`
- `reporting_period`
- `effective_date`
- `expiry_date`
- `is_current`
- `source`
- `remarks`

关联关系：

- 主键：`id`
- 外键：`from_entity_id -> shareholder_entities.id`
- 外键：`to_entity_id -> shareholder_entities.id`
- 与 `relationship_sources.structure_id` 一对多
- 与 `shareholder_structure_history.structure_id` 一对多

字段类型划分：

- 基础输入字段：`from_entity_id`、`to_entity_id`、`is_direct`、`is_current`
- 股权数值输入字段：`holding_ratio`、`effective_control_ratio`
- 非股权控制输入字段：`relation_type`、`voting_ratio`、`economic_ratio`、`control_basis`、`board_seats`、`nomination_rights`、`agreement_scope`、`relation_metadata`
- 算法辅助字段：`look_through_allowed`、`termination_signal`、`relation_priority`、`confidence_level`
- 展示/导入字段：`reporting_period`、`source`、`remarks`

当前真实使用情况：

- `backend/analysis/control_inference.py:build_control_context()` 会读取当前有效、直接关系边。
- `relation_type` 是 unified 选择规则分支的关键字段。
- `holding_ratio`、`voting_ratio`、`economic_ratio`、`effective_control_ratio` 参与数值控制强度计算。
- `control_basis`、`agreement_scope`、`nomination_rights`、`relation_metadata` 参与语义评分。
- `effective_date`、`expiry_date`、`is_current` 参与有效边过滤。

当前存在但算法或接口未高频使用的字段：

- `reporting_period`
- `source`

它们主要更偏导入/说明/展示用途。

`control_type` 与 `relation_type` 的关系：

- 当前 `relation_type` 才是统一算法的规范关系类型字段。
- `control_type` 更偏历史兼容字段，`backend/database.py:_backfill_shareholder_structures()` 也会利用它回填 `relation_type`。

对应实现文件：

- `backend/models/shareholder.py`
- `backend/schemas/shareholder.py`
- `backend/crud/shareholder.py`
- `backend/analysis/control_inference.py`
- `backend/database.py`

### 3.4 `relationship_sources`

定位与用途：

- 为单条股东关系边提供来源、链接、摘录和来源置信度。

主要字段：

- `id`
- `structure_id`
- `source_type`
- `source_name`
- `source_url`
- `source_date`
- `excerpt`
- `confidence_level`

关联关系：

- 主键：`id`
- 外键：`structure_id -> shareholder_structures.id`

字段类型划分：

- 基础输入/证据输入字段：`source_type`、`source_name`、`source_url`、`source_date`、`excerpt`、`confidence_level`

当前真实使用情况：

- 当前 unified 控制推断会读取 `relationship_sources`，将其纳入关系可靠性与证据摘要。
- `backend/analysis/control_inference.py` 中会把 source payload 合并到边级证据中，并用于 reliability 调整。

当前存在但未成为独立主判定规则的字段：

- `source_url`
- `source_name`
- `excerpt`

这些字段更多是证据增强和展示，不会单独决定控制结果。

对应实现文件：

- `backend/models/shareholder.py`
- `backend/schemas/shareholder.py`
- `backend/crud/shareholder.py`
- `backend/api/relationship_support.py`
- `backend/analysis/control_inference.py`

### 3.5 `entity_aliases`

定位与用途：

- 记录主体别名，如英文名、中文名、简称、旧名、ticker 名称。

主要字段：

- `id`
- `entity_id`
- `alias_name`
- `alias_type`
- `is_primary`
- `created_at`
- `updated_at`

关联关系：

- 主键：`id`
- 外键：`entity_id -> shareholder_entities.id`

字段类型划分：

- 基础辅助输入字段：`alias_name`、`alias_type`、`is_primary`

当前真实使用情况：

- 有正式 CRUD 和 API 支持。
- 在导入、实体管理、辅助匹配、展示层面有用。

当前存在但控制算法/产业接口暂未实际高频使用：

- `entity_aliases` 当前并不是 unified 控制分析和正式产业分析的主输入表。

也就是说，这张表真实存在、可维护，但当前更偏辅助数据层。

对应实现文件：

- `backend/models/shareholder.py`
- `backend/schemas/shareholder.py`
- `backend/crud/shareholder.py`
- `backend/api/relationship_support.py`

### 3.6 `shareholder_structure_history`

定位与用途：

- 记录股东关系边的变更历史。

主要字段：

- `id`
- `structure_id`
- `change_type`
- `old_value`
- `new_value`
- `change_reason`
- `changed_by`
- `created_at`

关联关系：

- 主键：`id`
- 外键：`structure_id -> shareholder_structures.id`

字段类型划分：

- 留痕字段：全部字段都属于过程留痕，不是控制算法事实输入

当前真实使用情况：

- `backend/crud/shareholder.py` 中创建和更新 `shareholder_structures` 时会自动写入 `insert` / `update` 历史。
- `backend/api/relationship_support.py` 允许读取和手工创建历史记录。

当前边界与不足：

- schema 中允许 `delete`、`normalize`、`manual_fix`、`import` 等 `change_type`
- 但当前默认 CRUD 自动写历史主要只覆盖 `insert` 和 `update`
- `delete_shareholder_structure()` 当前不会自动补一条删除历史

因此论文中应写成“部分实现关系变更留痕”，而不是“已形成完整变更审计链”。

对应实现文件：

- `backend/models/shareholder.py`
- `backend/schemas/shareholder.py`
- `backend/crud/shareholder.py`
- `backend/api/relationship_support.py`

### 3.7 `control_relationships`

定位与用途：

- 保存控制分析输出结果，包括候选控制人、直接控制人、最终控制人及其路径依据。

主要字段：

- `id`
- `company_id`
- `controller_entity_id`
- `controller_name`
- `controller_type`
- `control_type`
- `control_ratio`
- `control_path`
- `is_actual_controller`
- `control_tier`
- `is_direct_controller`
- `is_intermediate_controller`
- `is_ultimate_controller`
- `promotion_source_entity_id`
- `promotion_reason`
- `control_chain_depth`
- `is_terminal_inference`
- `terminal_failure_reason`
- `immediate_control_ratio`
- `aggregated_control_score`
- `terminal_control_score`
- `inference_run_id`
- `basis`
- `notes`
- `control_mode`
- `semantic_flags`
- `review_status`

关联关系：

- 主键：`id`
- 外键：`company_id -> companies.id`
- 外键：`controller_entity_id -> shareholder_entities.id`
- 外键：`promotion_source_entity_id -> shareholder_entities.id`
- 外键：`inference_run_id -> control_inference_runs.id`

字段类型划分：

- 算法输出字段：绝大多数核心字段都属于算法输出
- 人工/审核相关字段：`review_status`、`notes`
- 展示字段：`controller_name`、`control_path`、`basis`

当前真实使用情况：

- unified 刷新会删除旧自动结果并重写该表。
- `control_path`、`basis` 是前端解释和论文举例的重要依据。
- `control_tier`、`is_direct_controller`、`is_ultimate_controller` 用于区分 direct / ultimate / candidate。

当前存在但不应当视作基础输入的字段：

- 本表所有控制判定相关字段都不应被当作原始事实输入。

当前存在但使用范围相对有限的字段：

- `terminal_failure_reason`
- `promotion_reason`
- `immediate_control_ratio`

这些字段主要服务于统一推断解释和前端展示，并非每条结果都有值。

对应实现文件：

- `backend/models/control_relationship.py`
- `backend/schemas/control_relationship.py`
- `backend/crud/control_relationship.py`
- `backend/analysis/ownership_penetration.py`
- `backend/analysis/manual_control_override.py`

### 3.8 `country_attributions`

定位与用途：

- 保存企业实际控制国别归属结果。

主要字段：

- `id`
- `company_id`
- `incorporation_country`
- `listing_country`
- `actual_control_country`
- `attribution_type`
- `actual_controller_entity_id`
- `direct_controller_entity_id`
- `attribution_layer`
- `country_inference_reason`
- `look_through_applied`
- `inference_run_id`
- `basis`
- `is_manual`
- `notes`
- `source_mode`

关联关系：

- 主键：`id`
- 外键：`company_id -> companies.id`
- 外键：`inference_run_id -> control_inference_runs.id`

需要特别说明：

- `actual_controller_entity_id`
- `direct_controller_entity_id`

当前在 ORM 中只是带索引整数列，不是数据库外键；业务含义上它们指向 `shareholder_entities.id`。

字段类型划分：

- 算法输出字段：`actual_control_country`、`attribution_type`、`attribution_layer`、`country_inference_reason`、`look_through_applied`
- 基础快照字段：`incorporation_country`、`listing_country`
- 人工相关字段：`is_manual`、`notes`、`source_mode`

当前真实使用情况：

- unified 自动分析写入时会设置 `is_manual=False`
- 手工覆盖时可能生成人工有效国别结果
- 读接口会根据 `result_layer` 选择自动结果或当前有效结果

当前存在但算法主链未真正用于决策的字段：

- `listing_country` 当前主要是快照与展示字段，不是 unified 后端主回退规则

对应实现文件：

- `backend/models/country_attribution.py`
- `backend/schemas/country_attribution.py`
- `backend/crud/country_attribution.py`
- `backend/analysis/ownership_penetration.py`
- `backend/analysis/country_attribution_analysis.py`
- `backend/analysis/manual_control_override.py`

### 3.9 `business_segments`

定位与用途：

- 企业业务线事实表，是产业分析正式输入。

主要字段：

- `id`
- `company_id`
- `segment_name`
- `segment_alias`
- `segment_type`
- `revenue_ratio`
- `profit_ratio`
- `description`
- `currency`
- `source`
- `reporting_period`
- `is_current`
- `confidence`
- `created_at`
- `updated_at`

关联关系：

- 主键：`id`
- 外键：`company_id -> companies.id`
- 与 `business_segment_classifications.business_segment_id` 一对多

字段类型划分：

- 基础输入字段：几乎所有业务语义字段都属于事实输入
- 展示字段：`description`、`currency`、`source`

当前真实使用情况：

- 正式产业分析聚合从本表读取业务线事实。
- `segment_type` 当前支持 `primary`、`secondary`、`emerging`、`other`。

当前存在但不是分类输出字段：

- `business_segments` 不是自动分类结果表，不能在论文中写成“业务线算法输出表”。

对应实现文件：

- `backend/models/business_segment.py`
- `backend/schemas/business_segment.py`
- `backend/crud/business_segment.py`
- `backend/analysis/industry_analysis.py`

### 3.10 `business_segment_classifications`

定位与用途：

- 保存业务线映射到产业分类体系后的结果。

主要字段：

- `id`
- `business_segment_id`
- `standard_system`
- `level_1`
- `level_2`
- `level_3`
- `level_4`
- `is_primary`
- `mapping_basis`
- `review_status`
- `classifier_type`
- `confidence`
- `review_reason`
- `created_at`
- `updated_at`

关联关系：

- 主键：`id`
- 外键：`business_segment_id -> business_segments.id`

字段类型划分：

- 分类结果字段：`standard_system`、`level_1`~`level_4`、`is_primary`
- 人工/审核字段：`review_status`、`classifier_type`、`review_reason`
- 解释字段：`mapping_basis`
- 置信度字段：`confidence`

当前真实使用情况：

- 既可由规则刷新生成，也可由 LLM 建议确认写入，也可经人工 CRUD 修改。
- 当前默认正式分类体系为 `GICS`。

当前存在但不宜误写为“机器学习结果”的字段：

- `classifier_type`
- `review_status`

它们反映结果来源与审核状态，不代表系统已具备训练型自动分类模型。

对应实现文件：

- `backend/models/business_segment_classification.py`
- `backend/schemas/business_segment_classification.py`
- `backend/crud/business_segment_classification.py`
- `backend/analysis/industry_classification.py`
- `backend/analysis/industry_analysis.py`

### 3.11 `annotation_logs`

定位与用途：

- 通用人工修订留痕表，当前主要用于业务线和分类结果的人工操作记录。

主要字段：

- `id`
- `target_type`
- `target_id`
- `action_type`
- `old_value`
- `new_value`
- `reason`
- `operator`
- `created_at`

关联关系：

- 主键：`id`
- 当前没有数据库级外键到业务线或分类表
- 是通过 `target_type + target_id` 做弱关联

字段类型划分：

- 留痕字段：全部字段都属于留痕和审计

当前真实使用情况：

- `business_segment` 和 `business_segment_classification` 的创建、更新、删除会写入本表。
- `old_value` / `new_value` 保存序列化快照。

当前边界：

- 当前主用在产业分析侧
- 不应写成“全系统所有人工修订都统一进 annotation_logs”，因为控制结果人工覆盖当前还有 `manual_control_overrides` 这套独立实现

对应实现文件：

- `backend/models/annotation_log.py`
- `backend/crud/annotation_log.py`
- `backend/crud/business_segment.py`
- `backend/crud/business_segment_classification.py`
- `backend/api/industry_analysis.py`

### 3.12 `control_inference_runs`

定位与用途：

- 单次控制推断运行摘要表。

主要字段：

- `company_id`
- `run_started_at`
- `run_finished_at`
- `engine_version`
- `engine_mode`
- `max_depth`
- `disclosure_threshold`
- `significant_threshold`
- `control_threshold`
- `terminal_identification_enabled`
- `look_through_policy`
- `result_status`
- `summary_json`
- `notes`

实际意义：

- 记录每次 unified/legacy 重算的参数和概要结果
- 是运行审计，不是基础事实

对应实现文件：

- `backend/models/control_inference_run.py`
- `backend/analysis/ownership_penetration.py`

### 3.13 `control_inference_audit_log`

定位与用途：

- 单次控制推断的步骤级审计日志。

主要字段：

- `inference_run_id`
- `company_id`
- `step_no`
- `from_entity_id`
- `to_entity_id`
- `action_type`
- `action_reason`
- `score_before`
- `score_after`
- `details_json`

实际意义：

- 用于记录 promotion、block、terminal confirm 等过程动作
- 不是正式业务结果表

对应实现文件：

- `backend/models/control_inference_audit_log.py`
- `backend/analysis/ownership_penetration.py`

### 3.14 `manual_control_overrides`

定位与用途：

- 控制结果人工征订/确认/恢复专用表。

主要字段：

- `company_id`
- `action_type`
- `source_type`
- `actual_controller_entity_id`
- `actual_controller_name`
- `actual_control_country`
- `attribution_type`
- `manual_control_ratio`
- `manual_control_path`
- `manual_paths`
- `manual_decision_reason`
- `reason`
- `evidence`
- `operator`
- `is_current_effective`
- `automatic_control_snapshot`
- `automatic_country_snapshot`
- `manual_result_snapshot`
- `control_relationship_id`
- `country_attribution_id`

实际意义：

- 保存人工覆盖与自动结果快照
- 支撑 `current` 结果层

对应实现文件：

- `backend/models/manual_control_override.py`
- `backend/analysis/manual_control_override.py`

## 4. 表之间的关系

### 4.1 `companies` 与 `shareholder_entities`

- 一家公司通常需要至少一个映射实体，依靠 `shareholder_entities.company_id = companies.id`
- 控制分析不是直接对 `companies` 做图搜索，而是先通过这个映射进入控制图

### 4.2 `shareholder_entities` 与 `shareholder_structures`

- `shareholder_entities` 是节点
- `shareholder_structures` 是边
- `from_entity_id -> to_entity_id` 形成有向控制网络

### 4.3 `shareholder_structures` 与 `relationship_sources`、`shareholder_structure_history`

- 一条结构边可有多条 `relationship_sources`
- 一条结构边可有多条 `shareholder_structure_history`
- 前者记录证据来源，后者记录结构边变更历史

### 4.4 `companies` 与 `control_relationships`、`country_attributions`

- `control_relationships.company_id` 记录该公司的控制分析输出
- `country_attributions.company_id` 记录该公司的国别归属输出

### 4.5 `companies` 与 `business_segments`

- 一家公司可对应多条业务线
- 通过 `business_segments.company_id` 关联

### 4.6 `business_segments` 与 `business_segment_classifications`

- 一条业务线可有一条或多条分类映射结果
- 通过 `business_segment_classifications.business_segment_id` 关联

### 4.7 `annotation_logs` 如何记录人工修订

- 通过 `target_type + target_id` 记录对业务线或分类映射的操作
- `old_value`、`new_value` 存储序列化快照
- `reason`、`operator` 记录修订原因和操作者

## 5. 控制分析相关数据流

### 5.1 哪些表作为输入

当前控制链分析输入表主要是：

- `companies`
- `shareholder_entities`
- `shareholder_structures`
- `relationship_sources`

辅助表包括：

- `entity_aliases`：当前主要辅助管理，不是算法主输入
- `shareholder_structure_history`：留痕，不是算法主输入

### 5.2 结果写回哪些表

当前控制分析结果主要写回：

- `control_relationships`
- `country_attributions`

同时写入运行留痕：

- `control_inference_runs`
- `control_inference_audit_log`

### 5.3 为什么 `control_relationships` 和 `country_attributions` 不应由基础数据提供方手工填写

因为这两张表在当前设计中是：

- 基于原始事实计算得到的结果层
- 可能被 refresh / recompute 重写
- 与当前算法阈值、路径聚合、promotion 逻辑直接相关

如果由基础事实提供方手工填写，会混淆：

- 原始事实
- 自动推断结论
- 人工修订结论

这会破坏当前分层设计。

### 5.4 refresh / recompute 后如何变化

当前 unified 刷新时：

- 旧自动 `control_relationships` 会被删除
- 旧自动 `country_attributions` 会被删除
- 新的自动结果重新写入
- 新 run 和 audit log 会追加写入

相关逻辑位于：

- `backend/analysis/ownership_penetration.py`
- `backend/tasks/recompute_analysis_results.py`

### 5.5 当前是否保留历史结果

需要区分两类“历史”。

- 正式结果表层面：  
  当前没有单独的完整版本化历史结果表。旧自动结果通常会在重算时被删掉并替换。

- 运行审计层面：  
  当前保留 `control_inference_runs` 和 `control_inference_audit_log`，因此“每次运行的摘要和步骤痕迹”部分保留。

此外：

- `manual_control_overrides` 会保留人工覆盖快照

但这不等于自动结果有完整版本仓库。

## 6. 产业分析相关数据流

### 6.1 `business_segments` 是事实输入还是算法结果

- 当前 `business_segments` 是业务线事实输入表，不是算法结果表。

### 6.2 `business_segment_classifications` 是什么

- 当前 `business_segment_classifications` 是业务线分类映射结果表
- 其中既可以是规则刷新生成的自动结果，也可以是 LLM 建议确认后的正式结果，也可以是人工调整后的结果

因此更准确的表述是：

- 它是“分类结果层”，而不是单一的“自动分类结果表”

### 6.3 `annotation_logs` 如何体现人工确认、调整和修订

- 业务线 CRUD 会写 `annotation_logs`
- 分类 CRUD 会写 `annotation_logs`
- 记录 action type、前后快照、原因、操作者

因此当前产业分析侧确实有留痕闭环。

### 6.4 产业分析接口如何聚合展示

当前主要由以下逻辑聚合：

- `backend/analysis/industry_analysis.py`

主要读取：

- `business_segments`
- `business_segment_classifications`

并生成：

- 当前报告期业务线结构
- 主分类标签
- 数据完整性标记
- 质量警告
- 历史期间对比结果

接口入口主要在：

- `backend/api/industry_analysis.py`

## 7. 数据库设计的论文表达建议

### 7.1 应重点强调什么

建议重点强调：

- 事实层与结果层分离
- 控制分析结果与人工修订分离
- 业务线事实、分类结果和留痕分离
- 同一数据库同时服务控制归属分析和产业结构征订

### 7.2 哪些表适合放入 ER 图

建议论文 ER 图至少包含：

- `companies`
- `shareholder_entities`
- `shareholder_structures`
- `relationship_sources`
- `control_relationships`
- `country_attributions`
- `business_segments`
- `business_segment_classifications`
- `annotation_logs`

若篇幅允许，可再加入：

- `control_inference_runs`
- `manual_control_overrides`

### 7.3 哪些字段适合在论文中详细解释

建议重点解释：

- `shareholder_entities.company_id`
- `shareholder_structures.relation_type`
- `shareholder_structures.holding_ratio`
- `shareholder_structures.effective_control_ratio`
- `shareholder_structures.control_basis`
- `shareholder_structures.look_through_allowed`
- `shareholder_structures.termination_signal`
- `control_relationships.control_tier`
- `control_relationships.control_mode`
- `control_relationships.basis`
- `country_attributions.attribution_type`
- `country_attributions.attribution_layer`
- `business_segments.segment_type`
- `business_segment_classifications.standard_system`
- `business_segment_classifications.level_1 ~ level_4`
- `business_segment_classifications.review_status`
- `annotation_logs.action_type`

### 7.4 哪些工程兼容字段不宜展开过多

不建议在论文主体中展开过多：

- `control_type` 这类历史兼容字段
- `look_through_priority` 这类当前使用相对较弱的预留/增强字段
- `identifier_code`、`is_listed` 这类辅助管理字段
- 大量时间戳和索引实现细节

### 7.5 如何避免写成简单字段罗列

建议按“问题 -> 分层 -> 关系 -> 数据流 -> 结果层 -> 留痕层”的顺序写，而不是逐字段堆表。

可采用的写法是：

1. 先说明为什么需要事实层与结果层分离
2. 再说明控制网络如何由节点和边构成
3. 再说明控制结果和国别结果为什么单独落表
4. 最后说明业务线、分类结果和人工留痕如何构成产业分析子系统

## 8. 当前数据库设计的边界与不足

### 8.1 当前是否仍以 SQLite 为主，是否支持 PostgreSQL

- 当前默认主路径仍以 SQLite 为主
- `backend/database_config.py` 默认返回 SQLite 文件路径
- `backend/database.py` 的兼容补列和 backfill 逻辑明显以 SQLite 为中心
- 依赖中包含 `psycopg2-binary`，说明从连接能力上可支持 PostgreSQL URL

但更准确的说法应是：

- 当前仓库默认运行、升级和验证流程主要围绕 SQLite 设计，PostgreSQL 支持更多停留在可连接层面，而非完整迁移实践主路径

### 8.2 是否有正式 migration 工具

- 当前仓库中没有正式 Alembic 迁移目录和迁移版本链
- 没有看到当前实际使用的正式 migration framework
- 当前数据库演进主要依赖：
  - `Base.metadata.create_all`
  - `backend/database.py:ensure_sqlite_schema()`
  - `scripts/upgrade_db_to_v2.py`
  - `scripts/verify_db_v2.py`

因此更准确的表述是：

- 当前采用代码内补列/backfill 和脚本式升级，而不是正式 migration 工具链

### 8.3 自动结果是否有完整历史版本表

- 当前没有专门的“控制结果历史版本表”或“国别结果历史版本表”
- 自动结果表会被重算覆盖
- 仅通过 `control_inference_runs`、`control_inference_audit_log`、`manual_control_overrides` 部分保留摘要和快照

### 8.4 是否支持大规模图数据库能力

- 当前不支持图数据库主架构
- 当前实现是关系型数据库存储 + 后端内存图分析
- 图遍历与推断逻辑主要在 Python 代码中完成

### 8.5 哪些字段为未来扩展预留，哪些已真实参与业务逻辑

当前已真实参与业务逻辑的字段包括：

- `shareholder_structures.relation_type`
- `holding_ratio` / `effective_control_ratio`
- `control_basis`
- `agreement_scope`
- `relation_metadata`
- `confidence_level`
- `look_through_allowed`
- `termination_signal`
- `shareholder_entities.entity_subtype`
- `controller_class`
- `beneficial_owner_disclosed`
- `control_relationships.control_tier`
- `control_relationships.control_mode`
- `country_attributions.attribution_layer`
- `business_segments.segment_type`
- `business_segment_classifications.review_status`
- `classifier_type`

当前更偏预留、兼容或弱使用的字段包括：

- `shareholder_structures.control_type`
- `shareholder_structures.has_numeric_ratio`
- `shareholder_entities.identifier_code`
- `shareholder_entities.is_listed`
- `shareholder_entities.look_through_priority`
- `companies.headquarters` 在控制算法中的使用
- `companies.listing_country` 在 unified 国别回退中的使用

## 9. 论文数据库设计章节可用小结

当前项目的数据库设计体现出较清晰的分层思想：以 `companies`、`shareholder_entities`、`shareholder_structures` 等表保存企业与控制关系的基础事实，以 `control_relationships`、`country_attributions` 保存控制分析和国别归属结果，以 `business_segments`、`business_segment_classifications` 组织业务线与产业分类，以 `annotation_logs`、`manual_control_overrides` 保留人工修订和确认痕迹。这种设计避免了原始事实、自动推断结论与人工修正结果混杂在同一张表中，有利于区分数据来源、支持 refresh/recompute 覆盖自动结果，并保留必要的人工审计链。当前系统仍以 SQLite 为默认运行环境，数据库演进主要依赖 `create_all`、`ensure_sqlite_schema()` 和脚本式升级校验，而非正式 migration 框架；同时，系统尚未采用图数据库，也没有完整的自动结果版本历史表。整体来看，该数据库更适合在论文中表述为“面向企业控制归属分析与业务结构征订的分层关系型数据模型”，重点应放在数据分层、表间关系和分析数据流，而不是简单罗列字段。
