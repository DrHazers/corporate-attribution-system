# 完整数据库设计说明 V2

本文面向项目维护、论文写作、系统设计说明和后续开发，概括当前 v2 数据库的设计目标、表结构职责、数据流和控制推断字段的意义。

## 1. v2 数据库整体设计目标

v2 升级不是推翻原有输入层，而是在保留 `companies`、`shareholder_entities`、`shareholder_structures` 三张基础事实表的前提下，增强控制分析的表达能力和留痕能力。

核心目标包括：

1. 区分 direct controller 和 ultimate controller  
   旧结构更像“最强控制候选人”结果，v2 增加 `control_tier`、`is_direct_controller`、`is_intermediate_controller`、`is_ultimate_controller` 等字段，能够明确控制层级。

2. 支持终局上卷  
   v2 在主体和关系边上增加 `entity_subtype`、`ultimate_owner_hint`、`controller_class`、`beneficial_owner_disclosed`、`look_through_allowed`、`termination_signal` 等字段，用于判断何时继续穿透、何时停止、何时阻断。

3. 支持股权和语义控制混合分析  
   `shareholder_structures` 不再只表达持股比例，还能表达协议控制、董事会控制、表决权控制、代持、VIE 等关系。

4. 支持控制分析留痕  
   `control_inference_runs` 记录一次分析的参数和结果摘要；`control_inference_audit_log` 记录候选选择、上卷、阻断、终局确认、共同控制识别等关键步骤。

5. 支持国家归属层级化  
   `country_attributions` 增加 `actual_controller_entity_id`、`direct_controller_entity_id`、`attribution_layer`、`country_inference_reason`、`look_through_applied`，把国家归属和控制层级绑定起来。

6. 兼容现实数据不完整  
   很多增强字段允许为空，由算法按默认值、回填规则或 fallback 规则降级处理，便于先落地最小版本，再逐步补充证据。

## 2. 数据库整体分层

| 层级 | 表 | 主要角色 |
| --- | --- | --- |
| 公司主数据层 | `companies` | 分析入口、公司基础信息、国家归属 fallback |
| 控制图节点层 | `shareholder_entities` | 公司、自然人、机构、基金、政府等主体节点 |
| 控制图边层 | `shareholder_structures` | 股权边和语义控制边 |
| 证据辅助层 | `relationship_sources` | 控制关系的来源、链接、摘录和置信度 |
| 实体匹配辅助层 | `entity_aliases` | 主体别名、旧名、简称、中英文名 |
| 结构变更留痕层 | `shareholder_structure_history` | 关系边创建、更新、删除、归一化记录 |
| 控制结果层 | `control_relationships` | direct/intermediate/ultimate/candidate 控制关系结果 |
| 国家归属结果层 | `country_attributions` | 实际控制国家和归属类型结果 |
| 推断运行层 | `control_inference_runs` | 每次控制推断的运行参数、阈值、状态和摘要 |
| 推断审计层 | `control_inference_audit_log` | 控制推断过程关键动作 |
| 行业分析输入层 | `business_segments` | 业务分部事实数据 |
| 行业分类结果层 | `business_segment_classifications` | 业务分部行业分类 |
| 通用人工操作留痕层 | `annotation_logs` | 人工修订、标注和理由记录 |

## 3. 各表完整设计说明

### `companies`

业务作用：公司主表，是控制分析和行业分析的共同入口。

核心字段：

- `id`：公司主键。
- `name`：公司名称。
- `stock_code`：股票代码或内部代码。
- `incorporation_country`：注册地，当前国家归属 fallback 的核心字段。
- `listing_country`：上市地，当前主要复制到国家归属结果。
- `headquarters`：总部所在地。
- `description`：公司描述。

关系：被 `shareholder_entities.company_id` 映射为控制图中的目标实体；被 `control_relationships`、`country_attributions`、`control_inference_runs`、`business_segments` 引用。

读写角色：输入表。算法读取，不主动生成公司基础事实。

### `shareholder_entities`

业务作用：控制图节点表，统一表达公司、自然人、机构、基金、政府和其他主体。

核心字段：

- `id`：主体主键。
- `entity_name`：主体名称。
- `entity_type`：主体类型。
- `country`：主体国家，优先用于控制人国家归属。
- `company_id`：可选公司映射。目标公司必须有一条映射实体。
- `entity_subtype`：主体子类型，如 holding company、SPV、family vehicle。
- `ultimate_owner_hint`：提示该主体为终局所有人。
- `look_through_priority`：穿透优先级预留字段。
- `controller_class`：控制人类别，如 natural_person、state。
- `beneficial_owner_disclosed`：是否披露受益所有人。

关系：通过 `shareholder_structures.from_entity_id` 和 `shareholder_structures.to_entity_id` 参与控制图；可被 `control_relationships.controller_entity_id` 引用。

读写角色：输入表。算法读取主体类型、国家、公司映射和终局相关字段。

### `shareholder_structures`

业务作用：控制图边表，表达主体之间的股权、表决权、协议、董事会、VIE、代持等关系。

核心字段：

- `from_entity_id` / `to_entity_id`：边的上游和下游主体。
- `holding_ratio`：持股比例。
- `voting_ratio`：表决权比例。
- `economic_ratio`：经济收益比例。
- `is_direct`：是否直接边。当前分析只读取直接边。
- `relation_type`：标准关系类型。
- `control_type`：兼容旧字段，`relation_type` 缺失时用于推断。
- `effective_control_ratio`：有效控制比例，优先于 `holding_ratio` 用于股权打分。
- `is_beneficial_control`：是否代表受益控制。
- `look_through_allowed`：是否允许继续向上穿透。
- `termination_signal`：上卷阻断或终局信号。
- `control_basis`、`agreement_scope`、`nomination_rights`、`board_seats`：语义控制证据。
- `relation_metadata`：JSON 扩展信息，如总董事席位、有效表决权、受益人披露。
- `confidence_level`：证据置信度。
- `effective_date` / `expiry_date` / `is_current`：有效性过滤字段。

关系：连接两个 `shareholder_entities`；被 `relationship_sources.structure_id` 和 `shareholder_structure_history.structure_id` 引用。

读写角色：输入表。算法读取当前有效、直接、日期有效的边，并转换成控制因子。

### `relationship_sources`

业务作用：控制关系证据来源表，保存年报、公告、网页、人工整理等来源信息。

核心字段：

- `structure_id`：对应的 `shareholder_structures.id`。
- `source_type`：来源类型。
- `source_name`：来源名称。
- `source_url`：来源链接。
- `source_date`：来源日期。
- `excerpt`：证据摘录。
- `confidence_level`：来源置信度。

关系：多条来源可对应一条结构边。

读写角色：可选辅助输入表。当前核心算法不直接参与打分，但对人工复核和论文说明有价值。

### `entity_aliases`

业务作用：主体别名表，用于实体匹配、展示和去重。

核心字段：

- `entity_id`：对应的 `shareholder_entities.id`。
- `alias_name`：别名。
- `alias_type`：别名类型，如 english、chinese、short_name、old_name。
- `is_primary`：是否主别名。

关系：多条别名可对应一个主体。

读写角色：可选辅助输入表。当前核心算法不直接读取。

### `shareholder_structure_history`

业务作用：关系边变更历史表，记录插入、更新、删除、归一化、人工修订等动作。

核心字段：

- `structure_id`：对应结构边。
- `change_type`：变更类型。
- `old_value` / `new_value`：变更前后快照。
- `change_reason`：变更原因。
- `changed_by`：操作者。

关系：依附于 `shareholder_structures`。

读写角色：过程留痕表。通过 CRUD 创建或更新结构边时写入，不属于算法基础输入。

### `control_relationships`

业务作用：控制关系结果表，承载控制人候选、直接控制人、中间控制人和最终实际控制人。

核心字段：

- `company_id`：目标公司。
- `controller_entity_id`：控制主体。
- `controller_name` / `controller_type`：控制主体快照。
- `control_type`：控制类型，如 equity_control、agreement_control、mixed_control、joint_control。
- `control_ratio`：控制比例或控制得分的百分比表达。
- `control_path`：控制路径 JSON。
- `is_actual_controller`：旧兼容字段，v2 中与 ultimate controller 语义对齐。
- `control_tier`：direct、intermediate、ultimate、candidate。
- `is_direct_controller` / `is_intermediate_controller` / `is_ultimate_controller`：层级布尔标记。
- `promotion_source_entity_id` / `promotion_reason`：从下层主体上卷到上层主体的来源和原因。
- `control_chain_depth`：路径深度。
- `is_terminal_inference`：是否属于终局推断链条。
- `terminal_failure_reason`：未能终局确认的原因。
- `immediate_control_ratio`：直接层控制比例。
- `aggregated_control_score`：聚合控制得分。
- `terminal_control_score`：终局控制得分。
- `inference_run_id`：关联推断运行。
- `basis`：结果依据 JSON。
- `control_mode`：numeric、semantic、mixed。
- `semantic_flags`：语义标签 JSON。
- `review_status`：auto、needs_review、manual_confirmed 等。

关系：引用 `companies`、`shareholder_entities`、`control_inference_runs`。

读写角色：算法输出表。刷新分析时自动删除该公司旧的 `AUTO:%` 结果并写入新结果。

### `country_attributions`

业务作用：国家归属结果表，保存实际控制国家、归属类型和归属层级。

核心字段：

- `company_id`：目标公司。
- `incorporation_country` / `listing_country`：公司国家基础字段快照。
- `actual_control_country`：实际控制国家。
- `attribution_type`：归属类型，如 equity_control、mixed_control、fallback_incorporation。
- `actual_controller_entity_id`：最终实际控制人主体。
- `direct_controller_entity_id`：直接控制人主体。
- `attribution_layer`：direct_controller_country、ultimate_controller_country、fallback_incorporation、joint_control_undetermined。
- `country_inference_reason`：国家推断原因。
- `look_through_applied`：是否发生向上穿透。
- `inference_run_id`：关联推断运行。
- `basis`：归属依据 JSON。
- `is_manual`：是否人工记录。
- `source_mode`：control_chain_analysis、fallback_rule、manual_override、hybrid。

关系：引用 `companies` 和 `control_inference_runs`。

读写角色：算法输出表，也支持人工 override。读取接口默认取该公司最新一条记录。

### `control_inference_runs`

业务作用：控制推断运行记录表，记录一次 refresh 的参数、阈值、模式和结果状态。

核心字段：

- `company_id`：目标公司。
- `run_started_at` / `run_finished_at`：运行时间。
- `engine_version` / `engine_mode`：推断引擎版本和模式。
- `max_depth`：最大穿透深度。
- `disclosure_threshold` / `significant_threshold` / `control_threshold`：候选披露、重大影响和控制阈值。
- `terminal_identification_enabled`：是否启用终局识别。
- `look_through_policy`：穿透策略说明。
- `result_status`：running、success、failed 等状态。
- `summary_json`：结果摘要。
- `notes`：备注。

关系：被 `control_relationships`、`country_attributions`、`control_inference_audit_log` 引用。

读写角色：过程留痕表。由算法运行时创建和更新。

### `control_inference_audit_log`

业务作用：控制推断审计表，记录算法关键判断动作。

核心字段：

- `inference_run_id`：对应运行。
- `company_id`：目标公司。
- `step_no`：步骤序号。
- `from_entity_id` / `to_entity_id`：动作涉及主体。
- `action_type`：动作类型，如 candidate_selected、promotion_to_parent、promotion_blocked、terminal_confirmed、joint_control_detected。
- `action_reason`：动作原因。
- `score_before` / `score_after`：动作前后得分。
- `details_json`：扩展细节。

关系：依附于 `control_inference_runs`，也引用 `companies`。

读写角色：过程留痕表。便于审计、解释和论文展示。

### `business_segments`

业务作用：行业分析模块的业务分部事实表。

核心字段：

- `company_id`：目标公司。
- `segment_name`：业务分部名称。
- `segment_type`：业务类型。
- `revenue_ratio` / `profit_ratio`：收入或利润占比。
- `description`：业务描述。
- `reporting_period`：报告期。
- `is_current`：是否当前有效。
- `confidence`：置信度。

关系：引用 `companies`，被 `business_segment_classifications` 引用。

读写角色：行业模块输入表，不属于 ultimate controller 必要输入。

### `business_segment_classifications`

业务作用：业务分部行业分类结果表。

核心字段：

- `business_segment_id`：业务分部。
- `standard_system`：分类体系，如 GICS。
- `level_1` 到 `level_4`：多级行业分类。
- `is_primary`：是否主分类。
- `mapping_basis`：分类依据。
- `review_status`：复核状态。

关系：引用 `business_segments`。

读写角色：行业模块输出或人工分类结果表，不参与控制链算法。

### `annotation_logs`

业务作用：通用人工操作留痕表，记录人工标注、修订和理由。

核心字段：

- `target_type` / `target_id`：目标对象。
- `action_type`：动作类型。
- `old_value` / `new_value`：变更前后内容。
- `reason`：原因。
- `operator`：操作者。

关系：弱关联到业务对象。

读写角色：人工操作留痕表，不作为算法输入。

## 4. 数据流说明

### 4.1 原始输入进入分析模块

1. 上层以 `company_id` 请求分析。
2. 系统读取 `companies`，确认目标公司存在。
3. 系统通过 `shareholder_entities.company_id = companies.id` 找到目标公司的控制图实体。
4. 系统读取所有主体节点 `shareholder_entities`。
5. 系统读取 `shareholder_structures` 中满足以下条件的边：
   - `is_current = 1`
   - `is_direct = 1`
   - `effective_date` 为空或不晚于分析日
   - `expiry_date` 为空或不早于分析日
6. 每条边通过 `edge_to_factor()` 转换为控制因子，包括数值因子、语义因子、置信度、优先级、阻断信号和证据。

### 4.2 分析结果写入输出表

1. `infer_controllers()` 从目标实体向上搜索控制路径。
2. 算法聚合同一候选主体的多条路径得分。
3. 算法识别 direct controller、ultimate controller、joint control、leading candidate 或 fallback。
4. `refresh_company_control_analysis()` 创建一条 `control_inference_runs`。
5. 系统删除该公司旧的自动结果，即 `notes LIKE 'AUTO:%'` 的 `control_relationships` 和 `country_attributions`。
6. 系统写入新的 `control_relationships` 和 `country_attributions`。
7. 系统写入 `control_inference_audit_log`。
8. 系统更新 `control_inference_runs.result_status` 和 `summary_json`。

### 4.3 读取接口如何返回结果

控制链读取接口默认读取 `control_relationships`，并从中挑选 actual controller、direct controller 和 leading candidate。

国家归属读取接口默认读取 `country_attributions` 最新一条记录，并结合控制链结果返回。

这意味着读取接口默认信任结果表，不会每次自动重算。需要刷新时，应显式调用 refresh 接口或传入 refresh 选项。

## 5. direct controller / ultimate controller 字段设计意义

### `shareholder_entities` 新增字段

| 字段 | 设计意义 |
| --- | --- |
| `entity_subtype` | 识别 holding company、SPV、shell company、family vehicle 等，帮助判断是否继续穿透 |
| `ultimate_owner_hint` | 当数据源明确披露终局所有人时，为算法提供终止上卷提示 |
| `look_through_priority` | 预留给更细的穿透优先级策略 |
| `controller_class` | 将自然人、国家、基金、信托、公司集团区分开，辅助终局判断 |
| `beneficial_owner_disclosed` | 在代持和受益所有人场景中，判断是否可以继续上卷 |

### `shareholder_structures` 新增字段

| 字段 | 设计意义 |
| --- | --- |
| `voting_ratio` | 处理同股不同权、投票权委托、表决权控制 |
| `economic_ratio` | 处理收益权、VIE 经济利益、可变回报 |
| `is_beneficial_control` | 标记受益控制事实 |
| `look_through_allowed` | 明确某条边是否允许向上穿透 |
| `termination_signal` | 明确阻断原因，如 joint_control、beneficial_owner_unknown、protective_right_only |
| `effective_control_ratio` | 表达最终可用于控制判断的比例，避免只依赖名义持股 |
| `relation_type` | 将股权、协议、董事会、表决权、代持、VIE 标准化 |
| `control_basis` / `agreement_scope` / `nomination_rights` | 为语义控制提供文本证据 |
| `relation_metadata` | 承载总董事席位、有效表决权、受益人披露等结构化补充信息 |
| `confidence_level` | 将证据质量纳入候选结果解释 |

### `control_relationships` 层级字段

| 字段 | 设计意义 |
| --- | --- |
| `control_tier` | 明确 direct、intermediate、ultimate、candidate |
| `is_direct_controller` | 标记直接控制人 |
| `is_intermediate_controller` | 标记上卷路径中的中间控制人 |
| `is_ultimate_controller` | 标记最终实际控制人 |
| `promotion_source_entity_id` | 记录从哪个下层主体继续向上卷 |
| `promotion_reason` | 记录上卷原因 |
| `control_chain_depth` | 记录控制链深度 |
| `is_terminal_inference` | 标记是否属于终局推断链条 |
| `terminal_failure_reason` | 记录未能确认终局的原因 |
| `immediate_control_ratio` | 直接层控制比例 |
| `aggregated_control_score` | 聚合后的候选得分 |
| `terminal_control_score` | 终局层得分 |

### `country_attributions` 归属层级字段

| 字段 | 设计意义 |
| --- | --- |
| `actual_controller_entity_id` | 国家归属对应的终局控制主体 |
| `direct_controller_entity_id` | 直接控制主体 |
| `attribution_layer` | 说明国家来自直接控制人、终局控制人、注册地 fallback 或共同控制不确定 |
| `country_inference_reason` | 说明国家推断原因 |
| `look_through_applied` | 说明是否发生了穿透上卷 |
| `source_mode` | 区分控制链分析、fallback、人工覆盖和混合来源 |

### `control_inference_runs` 和 `control_inference_audit_log`

这两张表把“结论”拆成“运行参数”和“过程动作”。论文和系统说明中可以用它们证明：

- 分析不是黑箱写死字段，而是有运行参数、阈值和模式。
- 每次上卷、阻断、终局确认都有动作记录。
- 未来可以复盘某一次结果来自哪次运行、经过哪些判断。

## 6. 最小落地版和增强版

### 最小落地版

最小落地只需要：

- `companies`
- `shareholder_entities`
- `shareholder_structures`

最小字段包括：

- 公司：`id`、`name`、`stock_code`、`incorporation_country`、`listing_country`、`headquarters`
- 主体：`id`、`entity_name`、`entity_type`、`country`、目标公司的 `company_id`
- 关系边：`id`、`from_entity_id`、`to_entity_id`、`relation_type`、`holding_ratio`、`is_direct`、`is_current`

在这个版本里，系统可以完成基础股权穿透、控制人识别和注册地 fallback。

### 增强版

增强版逐步补充：

- 表决权和有效控制比例：`voting_ratio`、`effective_control_ratio`
- 语义控制证据：`control_basis`、`agreement_scope`、`board_seats`、`nomination_rights`
- 终局主体特征：`entity_subtype`、`controller_class`、`ultimate_owner_hint`
- 上卷策略：`look_through_allowed`、`termination_signal`
- 受益所有人信息：`is_beneficial_control`、`beneficial_owner_disclosed`
- 证据质量：`confidence_level`、`relationship_sources`
- 实体匹配：`entity_aliases`

增强版能更好地区分 direct controller、ultimate controller、joint control、fallback、nominee、SPV、holding company、beneficial owner、VIE 和董事会控制等场景。

### 为什么很多字段允许为空

现实抓取数据经常不完整，尤其是协议范围、董事会席位、受益所有人和 VIE 信息。因此 v2 把很多增强字段设计为可空，让系统支持分阶段落地：

- 有持股比例时先做基础股权穿透。
- 有语义证据时再做协议、董事会、VIE、代持等增强判断。
- 没有明确控制人时 fallback 到注册地。
- 缺少置信度时默认 `unknown`。
- 缺少日期时视为无日期限制。
- 缺少 `relation_type` 时尝试从 `control_type`、`holding_ratio`、`remarks` 推断。

### 当前算法的降级判断

| 数据缺失情况 | 当前行为 |
| --- | --- |
| 目标公司没有 `shareholder_entities.company_id` 映射 | 无法进入控制图，刷新分析会失败 |
| 没有有效 `shareholder_structures` 边 | 无法识别控制人，国家归属 fallback 到公司注册地 |
| 股权边缺少比例 | 该股权边无法形成有效控制因子 |
| 非股权边缺少证据文本 | 语义得分偏弱，可能进入 `needs_review` |
| `country` 缺失 | 控制人国家尝试取其映射公司注册地，再 fallback 到目标公司注册地 |
| `is_current = 0` 或日期失效 | 该边被过滤 |
| `is_direct = 0` | 当前控制推断不读取该边 |
| nominee 未披露受益所有人 | 可能被 `nominee_without_disclosure` 阻断 |
| joint control 信号明确 | 不输出唯一 ultimate controller，国家归属可能为 `undetermined` |

## 7. 当前 v2 数据状态说明

本轮实际读取的 `company_test_analysis_industry_v2.db` 已具备 v2 schema，但当前数据量很小：

- `companies`：1 行
- `shareholder_entities`：1 行
- `shareholder_structures`：0 行
- `control_relationships`：1 行
- `country_attributions`：1 行

因此，本轮导出的推荐模板适合做“字段结构对接”和“GPT 生成测试数据模板”，但不能代表完整样本库。如果要用旧行业数据生成满量 v2 数据，应先确认 `company_test_analysis_industry.db` 到 `company_test_analysis_industry_v2.db` 的升级和复制状态。

## 8. 论文可用数据库设计总结

本系统的 v2 数据库采用“事实输入、算法输出、过程留痕”分层设计。输入层以公司主表、主体节点表和控制关系边表为基础，将公司、自然人、机构、政府等控制主体统一抽象为节点，将股权、协议、董事会、表决权、代持和 VIE 等控制事实统一抽象为边。该设计既保留了传统股权穿透所需的持股比例和层级结构，又通过关系类型、语义证据、有效控制比例、受益所有人披露和穿透阻断信号等字段，扩展了对复杂控制安排的表达能力。

结果层将控制关系和国家归属拆分为两类输出表。`control_relationships` 记录候选控制主体、直接控制人、中间控制人和最终实际控制人的层级化结果，`country_attributions` 记录实际控制国家、归属类型和归属层级。两者通过 `inference_run_id` 与运行记录关联，使每次结果都可以追溯到具体分析参数和推断过程。

过程留痕层由 `control_inference_runs` 和 `control_inference_audit_log` 组成，分别记录运行级信息和步骤级审计信息。这种设计增强了控制识别结果的可解释性，也为后续人工复核、论文实验复现和系统迭代提供依据。

总体而言，v2 数据库在工程上兼顾了最小可落地性和复杂场景扩展性：在输入数据不足时可以退化为基础股权穿透和注册地 fallback；在数据较完整时可以支持 direct controller、ultimate controller、joint control、nominee、SPV、holding company、beneficial owner、VIE 和董事会控制等更细粒度的控制识别。
