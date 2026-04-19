# 原始库副本数据库对接说明文档

本文面向同组同学、数据抓取同学和网页端 GPT 测试数据生成。当前轮次只承认 `company_test_analysis_industry.db` 为原始有效数据源，但不直接读取它导出；所有 CSV 均来自它的副本：

- 实际导出数据库：`company_test_analysis_industry_export_source.db`
- CSV 导出目录：`exports/db_handoff_from_original/`
- CSV 编码：`utf-8-sig`

本轮不再基于 `company_test_analysis_industry_v2.db` 的内容做任何导出判断。

## 1. 当前副本表分类

| 分类 | 表 | 当前行数 | 是否导出为输入 CSV | 说明 |
| --- | --- | ---: | --- | --- |
| 基础输入表 | `companies` | 10000 | 是 | 公司主表，控制分析入口和国家 fallback 来源 |
| 基础输入表 | `shareholder_entities` | 26000 | 是 | 控制图节点，表示公司、自然人、机构、基金、政府等主体 |
| 基础输入表 | `shareholder_structures` | 105000 | 是 | 控制图边，表示股权、协议、董事会、表决权、代持、VIE 等关系 |
| 可选辅助表 | `relationship_sources` | 25016 | 是 | 关系边证据来源，当前不直接打分，但对对接和复核有价值 |
| 可选辅助表 | `entity_aliases` | 50000 | 是 | 主体别名，当前不直接打分，但对实体匹配和展示有价值 |
| 算法输出表 | `control_relationships` | 18971 | 否 | 控制人、控制路径、控制得分等算法结果 |
| 算法输出表 | `country_attributions` | 10000 | 否 | 实际控制国家和归属类型结果 |
| 过程留痕表 | `control_inference_runs` | 0 | 否 | 每次推断运行参数和摘要 |
| 过程留痕表 | `control_inference_audit_log` | 0 | 否 | 推断步骤审计日志 |
| 过程留痕表 | `shareholder_structure_history` | 12000 | 否 | 结构边变更历史 |
| 行业模块输入/结果 | `business_segments` / `business_segment_classifications` | 21282 / 26787 | 否 | 行业分析模块数据，不属于控制链必要输入 |
| 通用留痕表 | `annotation_logs` | 6941 | 否 | 人工标注和修订日志 |

## 2. 本轮导出文件

### 完整输入表导出版

路径：`exports/db_handoff_from_original/current_full_tables/`

| 文件 | 行数 | 用途 |
| --- | ---: | --- |
| `companies.csv` | 10000 | 公司基础信息完整导出 |
| `shareholder_entities.csv` | 26000 | 股东、公司、自然人、机构等主体完整导出 |
| `shareholder_structures.csv` | 105000 | 股权和控制关系边完整导出 |
| `relationship_sources.csv` | 25016 | 关系边证据来源完整导出 |
| `entity_aliases.csv` | 50000 | 主体别名完整导出 |

### 推荐输入模板版

路径：`exports/db_handoff_from_original/recommended_input_templates/`

| 文件 | 行数 | 用途 |
| --- | ---: | --- |
| `companies_input_template.csv` | 10000 | 传给网页端 GPT 的公司表推荐模板 |
| `shareholder_entities_input_template.csv` | 26000 | 传给网页端 GPT 的主体表推荐模板 |
| `shareholder_structures_input_template.csv` | 105000 | 传给网页端 GPT 的关系边推荐模板 |
| `relationship_sources_input_template.csv` | 25016 | 可选证据来源模板 |
| `entity_aliases_input_template.csv` | 50000 | 可选别名模板 |

推荐模板版不包含 `created_at / updated_at` 等系统维护字段，也不包含 `control_relationships` 或 `country_attributions` 这类算法输出字段。

## 3. 每张表用途说明

`companies` 是目标公司主表。当前控制分析以 `company_id` 为入口；当无法识别唯一实际控制人时，国家归属会 fallback 到 `incorporation_country`。

`shareholder_entities` 是控制图节点表。每个待分析公司必须在该表中有一条 `company_id = companies.id` 的映射实体，否则算法无法从公司进入控制图。

`shareholder_structures` 是控制图边表。算法读取当前有效、直接、日期有效的边，并将其转换为股权控制或语义控制因子。

`relationship_sources` 是证据来源表。当前核心控制推断不直接读取该表打分，但它能支持人工核验、同学抓取说明和后续可信度扩展。

`entity_aliases` 是主体别名表。当前核心控制推断不直接读取该表，但它能帮助实体匹配、去重、展示和抓取。

`control_relationships` 是算法输出表，保存控制人候选、direct/intermediate/ultimate 层级、控制路径、得分和依据。

`country_attributions` 是算法输出表，保存实际控制国家、归属类型、归属层级和依据。

`control_inference_runs` 和 `control_inference_audit_log` 是过程留痕表，记录推断运行参数和步骤级审计信息。

## 4. 输入字段说明与分级

字段等级定义：

- 必须：缺失后算法无法正常进入分析，或无法表达基本控制图。
- 条件必须：在某类关系中必须提供。例如股权边必须有 `holding_ratio`，董事会控制最好有席位或文本证据。
- 建议：明显提升 direct controller、ultimate controller、joint control、nominee、VIE 等判断能力。
- 可选：主要增强解释性、展示、来源追溯或后续扩展。
- 系统：由数据库或系统维护，不建议作为 GPT 造数重点。

### `companies`

| 字段 | 含义 | 算法必须 | 允许为空 | 推荐样例 | 对算法的影响 |
| --- | --- | --- | --- | --- | --- |
| `id` | 公司主键 | 是 | 否 | `1` | 分析入口和外键关联 |
| `name` | 公司名称 | 是 | 否 | `Demo Holdings Ltd.` | 展示、搜索和人工识别 |
| `stock_code` | 股票代码或内部代码 | 否，建议 | 否 | `000001.SZ` | 当前不打分，便于去重 |
| `incorporation_country` | 注册地 | 是 | 否 | `China` | 控制人缺失时 fallback 国家 |
| `listing_country` | 上市地 | 否，建议 | 否 | `Hong Kong` | 当前主要写入结果表，不直接判定 |
| `headquarters` | 总部 | 否，可选 | 否 | `Shenzhen` | 当前不参与判定 |
| `description` | 描述 | 否，可选 | 是 | `Technology group` | 当前不参与判定 |

字段分级：

- 必须：`id`、`name`、`incorporation_country`
- 建议：`stock_code`、`listing_country`
- 可选：`headquarters`、`description`

### `shareholder_entities`

| 字段 | 含义 | 算法必须 | 允许为空 | 推荐样例 | 对算法的影响 |
| --- | --- | --- | --- | --- | --- |
| `id` | 主体主键 | 是 | 否 | `1001` | 关系边连接依赖 |
| `entity_name` | 主体名称 | 是 | 否 | `Founder Holding Ltd.` | 路径、结果、展示 |
| `entity_type` | 主体类型 | 是 | 否 | `company` / `person` | 自然人、政府更容易成为终局主体 |
| `country` | 主体国家 | 否，建议 | 是 | `China` | 控制人国家优先来源 |
| `company_id` | 映射公司 ID | 目标公司必需 | 是 | `1` | 目标公司没有映射实体则无法分析 |
| `identifier_code` | 注册号/统一代码/LEI | 否，可选 | 是 | `914403...` | 当前不打分，便于去重 |
| `is_listed` | 是否上市 | 否，可选 | 是 | `1` | 当前不打分 |
| `entity_subtype` | 主体子类型 | 否，建议 | 是 | `holding_company` / `spv` | 影响是否继续穿透或终止 |
| `ultimate_owner_hint` | 终局所有人提示 | 否，建议 | 否 | `1` | 为真时倾向停止上卷 |
| `look_through_priority` | 穿透优先级 | 否，可选 | 否 | `1` | 当前影响弱，预留扩展 |
| `controller_class` | 控制人类别 | 否，建议 | 是 | `natural_person` / `state` | 自然人、国家类别触发终局倾向 |
| `beneficial_owner_disclosed` | 是否披露受益所有人 | 否，建议 | 否 | `1` | nominee 场景影响是否阻断上卷 |
| `notes` | 备注 | 否，可选 | 是 | `Founder family vehicle` | 解释性字段 |
| `created_at` / `updated_at` | 创建/更新时间 | 否，系统 | 否 | 自动生成 | 不建议由抓取同学提供 |

字段分级：

- 必须：`id`、`entity_name`、`entity_type`
- 条件必须：目标公司实体的 `company_id`
- 建议：`country`、`entity_subtype`、`ultimate_owner_hint`、`controller_class`、`beneficial_owner_disclosed`
- 可选：`identifier_code`、`is_listed`、`look_through_priority`、`notes`
- 系统：`created_at`、`updated_at`

### `shareholder_structures`

| 字段 | 含义 | 算法必须 | 允许为空 | 推荐样例 | 对算法的影响 |
| --- | --- | --- | --- | --- | --- |
| `id` | 关系边主键 | 是 | 否 | `5001` | 控制路径和证据来源引用 |
| `from_entity_id` | 上游主体 | 是 | 否 | `1001` | 控制图边起点 |
| `to_entity_id` | 下游主体 | 是 | 否 | `1` | 控制图边终点 |
| `relation_type` | 标准关系类型 | 是，建议明确 | 是 | `equity` / `agreement` / `vie` | 决定股权或语义控制处理方式 |
| `relation_role` | 关系角色 | 否，可选 | 是 | `ownership` | 展示和解释 |
| `control_type` | 兼容控制类型 | 否，建议 | 是 | `equity` | `relation_type` 缺失时用于推断 |
| `holding_ratio` | 持股比例 | 股权边必需 | 是 | `55.0000` | 股权边核心数值因子 |
| `has_numeric_ratio` | 是否有数值比例 | 否，可选 | 否 | `1` | 可自动推断，当前非核心 |
| `is_direct` | 是否直接边 | 是 | 否 | `1` | 当前算法只读取 `is_direct = 1` |
| `control_basis` | 控制依据文本 | 非股权建议/条件必须 | 是 | `right to appoint majority directors` | 语义控制核心证据 |
| `agreement_scope` | 协议/VIE/表决权范围 | 协议类建议/条件必须 | 是 | `exclusive service agreement` | agreement/vie/voting_right 证据 |
| `board_seats` | 董事席位 | 董事会控制建议/条件必须 | 是 | `4` | 董事会控制打分 |
| `nomination_rights` | 董事提名权 | 董事会控制建议 | 是 | `appoint 4 of 7 directors` | 董事会控制文本证据 |
| `relation_priority` | 边优先级 | 否，可选 | 是 | `20` | 影响边排序 |
| `confidence_level` | 置信度 | 否，建议 | 是 | `high` | 转成置信权重 |
| `reporting_period` | 报告期 | 否，可选 | 是 | `2024A` | 当前不直接判定 |
| `effective_date` | 生效日 | 否，建议 | 是 | `2024-01-01` | 日期晚于分析日会被过滤 |
| `expiry_date` | 失效日 | 否，建议 | 是 | `2026-12-31` | 日期早于分析日会被过滤 |
| `is_current` | 当前是否有效 | 是 | 否 | `1` | 为 `0` 时算法忽略 |
| `relation_metadata` | JSON 扩展信息 | 否，建议 | 是 | `{"total_board_seats":7}` | 提供总席位、有效表决权、受益人信息 |
| `source` | 简要来源 | 否，可选 | 是 | `annual_report_2024` | 追溯用 |
| `remarks` | 备注/兼容文本 | 否，建议 | 是 | `joint control by unanimous consent` | 可用于关系类型和关键词推断 |
| `voting_ratio` | 表决权比例 | 否，建议 | 是 | `65.0000` | 表决权和协议控制辅助 |
| `economic_ratio` | 经济收益比例 | 否，可选 | 是 | `40.0000` | VIE 和收益权解释 |
| `is_beneficial_control` | 是否受益控制 | 否，建议 | 否 | `1` | nominee/beneficial owner 场景 |
| `look_through_allowed` | 是否允许继续穿透 | 否，建议 | 否 | `1` | 为 `0` 时阻断上卷 |
| `termination_signal` | 终止/阻断信号 | 否，建议 | 是 | `beneficial_owner_unknown` | 可直接阻断或标记 joint/protective 等 |
| `effective_control_ratio` | 有效控制比例 | 否，建议 | 是 | `70.0000` | 股权边优先替代 `holding_ratio` |
| `created_at` / `updated_at` | 创建/更新时间 | 否，系统 | 否 | 自动生成 | 不建议由抓取同学提供 |

字段分级：

- 必须：`id`、`from_entity_id`、`to_entity_id`、`is_direct`、`is_current`
- 条件必须：股权边的 `holding_ratio`；非股权边的 `relation_type` 和相应证据字段
- 建议：`relation_type`、`control_type`、`voting_ratio`、`effective_control_ratio`、`control_basis`、`agreement_scope`、`board_seats`、`nomination_rights`、`relation_metadata`、`confidence_level`、`effective_date`、`expiry_date`、`is_beneficial_control`、`look_through_allowed`、`termination_signal`、`remarks`
- 可选：`relation_role`、`has_numeric_ratio`、`economic_ratio`、`relation_priority`、`reporting_period`、`source`
- 系统：`created_at`、`updated_at`

### `relationship_sources`

| 字段 | 含义 | 算法必须 | 允许为空 | 推荐样例 | 对算法的影响 |
| --- | --- | --- | --- | --- | --- |
| `id` | 来源主键 | 否，可选 | 否 | `1` | 来源记录标识 |
| `structure_id` | 对应关系边 | 有来源时必需 | 否 | `5001` | 关联到 `shareholder_structures` |
| `source_type` | 来源类型 | 否，建议 | 是 | `annual_report` | 复核和证据分类 |
| `source_name` | 来源名称 | 否，建议 | 是 | `2024 Annual Report` | 复核用 |
| `source_url` | 来源链接 | 否，可选 | 是 | `https://...` | 复核用 |
| `source_date` | 来源日期 | 否，可选 | 是 | `2025-03-31` | 时效判断 |
| `excerpt` | 证据摘录 | 否，建议 | 是 | `The founder controls voting rights...` | 后续解释和 LLM 复核 |
| `confidence_level` | 来源置信度 | 否，建议 | 是 | `high` | 当前不直接打分 |
| `created_at` / `updated_at` | 创建/更新时间 | 否，系统 | 否 | 自动生成 | 不建议由抓取同学提供 |

### `entity_aliases`

| 字段 | 含义 | 算法必须 | 允许为空 | 推荐样例 | 对算法的影响 |
| --- | --- | --- | --- | --- | --- |
| `id` | 别名主键 | 否，可选 | 否 | `1` | 别名记录标识 |
| `entity_id` | 对应主体 | 有别名时必需 | 否 | `1001` | 关联到 `shareholder_entities` |
| `alias_name` | 别名 | 否，建议 | 否 | `Tencent Holdings` | 实体匹配和展示 |
| `alias_type` | 别名类型 | 否，可选 | 是 | `english` / `short_name` | 展示和匹配 |
| `is_primary` | 是否主别名 | 否，可选 | 否 | `1` | 当前不打分 |
| `created_at` / `updated_at` | 创建/更新时间 | 否，系统 | 否 | 自动生成 | 不建议由抓取同学提供 |

## 5. 抓取同学提供字段 vs 算法写回字段

抓取同学应提供事实输入：

- `companies`：公司名称、代码、注册地、上市地、总部、描述。
- `shareholder_entities`：主体名称、主体类型、国家、公司映射、主体子类型、终局提示、受益所有人披露状态。
- `shareholder_structures`：上游主体、下游主体、关系类型、持股/表决权/有效控制比例、是否当前有效、日期、协议/董事会/VIE/代持证据、置信度、来源说明。
- `relationship_sources`：来源类型、来源名称、链接、日期、摘录、置信度。
- `entity_aliases`：中英文名、简称、旧名、股票简称等别名。

算法或系统写回：

- `control_relationships`：控制人候选、direct/intermediate/ultimate 标记、控制路径、控制得分、语义标签、复核状态。
- `country_attributions`：实际控制国家、归属类型、归属层级、国家推断原因。
- `control_inference_runs`：运行参数、阈值、状态和摘要。
- `control_inference_audit_log`：候选选择、上卷、阻断、终局确认、共同控制等步骤日志。
- `shareholder_structure_history`：结构边变更历史。
- `annotation_logs`：人工标注和修订记录。

不要把 `control_relationships` 或 `country_attributions` 当作 GPT 的原始输入模板，否则会混淆“事实数据”和“算法结论”。

## 6. 最小可运行输入集

最小版本只需要三张基础输入表：

1. `companies`
   - `id`
   - `name`
   - `incorporation_country`
   - 建议同时提供 `stock_code`、`listing_country`

2. `shareholder_entities`
   - 所有主体的 `id`、`entity_name`、`entity_type`
   - 目标公司实体必须提供 `company_id = companies.id`
   - 建议提供控制主体的 `country`

3. `shareholder_structures`
   - `id`
   - `from_entity_id`
   - `to_entity_id`
   - `relation_type = equity`
   - `holding_ratio`
   - `is_direct = 1`
   - `is_current = 1`
   - 日期字段可为空，表示不限制日期

这套数据可以支持基础股权穿透、direct controller、ultimate controller 和注册地 fallback。

## 7. 增强版输入集

| 分析目标 | 建议补充 |
| --- | --- |
| 更准的 direct controller | `holding_ratio`、`effective_control_ratio`、`voting_ratio`、`confidence_level` |
| 更准的 ultimate controller | 多层 `shareholder_structures`、`entity_subtype`、`controller_class`、`ultimate_owner_hint`、`look_through_allowed` |
| joint control | 在 `control_basis`、`agreement_scope`、`remarks` 中写明 joint/unanimous/acting in concert 等证据 |
| nominee / beneficial owner | `relation_type = nominee`、`is_beneficial_control`、`beneficial_owner_disclosed`、`termination_signal`、`relation_metadata` |
| SPV / holding company | `entity_subtype = spv / holding_company / shell_company`、上游控制边、`look_through_allowed` |
| 董事会控制 | `relation_type = board_control`、`board_seats`、`nomination_rights`、`relation_metadata.total_board_seats` |
| VIE / 协议控制 | `relation_type = vie / agreement`、`agreement_scope`、`control_basis`、`economic_ratio`、`relation_metadata` |
| 表决权控制 | `relation_type = voting_right`、`voting_ratio`、`agreement_scope`、`relation_metadata.effective_voting_ratio` |
| fallback 场景 | 保证 `companies.incorporation_country` 准确 |

## 8. 推荐传给网页端 GPT 的文件

核心三份：

- `exports/db_handoff_from_original/recommended_input_templates/companies_input_template.csv`
- `exports/db_handoff_from_original/recommended_input_templates/shareholder_entities_input_template.csv`
- `exports/db_handoff_from_original/recommended_input_templates/shareholder_structures_input_template.csv`

可选两份：

- `exports/db_handoff_from_original/recommended_input_templates/relationship_sources_input_template.csv`
- `exports/db_handoff_from_original/recommended_input_templates/entity_aliases_input_template.csv`
