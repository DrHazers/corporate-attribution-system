# 数据库对接说明文档

本文面向同组同学、数据抓取同学和网页端 GPT 测试数据生成场景，说明当前控制分析算法真正需要哪些输入数据，以及哪些表不能混作原始输入。

本轮导出默认读取：

- `ultimate_controller_enhanced_dataset_working.db`
- 导出目录：`exports/db_handoff/`
- 编码：`utf-8-sig`，便于 Excel 直接打开

> Update 2026-04-20
>
> Current export default now follows the application working database:
> `ultimate_controller_enhanced_dataset_working.db`
>
> Snapshot counts:
> `companies=10030`, `shareholder_entities=27176`, `shareholder_structures=104112`,
> `control_relationships=19138`, `country_attributions=10047`,
> `control_inference_runs=10030`, `control_inference_audit_log=23167`

当前 v2 库的实际数据量如下：

| 表 | 当前行数 | 对接含义 |
| --- | ---: | --- |
| `companies` | 1 | 有 1 条公司主数据 |
| `shareholder_entities` | 1 | 有 1 条目标公司映射实体 |
| `shareholder_structures` | 0 | 当前 v2 库没有股权/控制边，算法无法仅凭输入表推导真实控制链 |
| `relationship_sources` | 0 | 当前无证据来源行 |
| `entity_aliases` | 0 | 当前无别名行 |
| `control_relationships` | 1 | 已有一条算法/人工结果，不应混入输入模板 |
| `country_attributions` | 1 | 已有一条国家归属结果，不应混入输入模板 |
| `control_inference_runs` | 0 | 当前无运行记录 |
| `control_inference_audit_log` | 0 | 当前无审计步骤记录 |

同目录的旧库 `company_test_analysis_industry.db` 和 `company_test_analysis_industry_v2.db` 仍可作为历史来源或对比样本，但本轮脚本默认优先使用 `ultimate_controller_enhanced_dataset_working.db`。后续如需切换到同结构的新工作库，优先配置 `CORP_DEFAULT_DATABASE_PATH` 或 `CORP_DEFAULT_DATABASE_NAME`。

## 1. 导出文件

### 完整表导出版

路径：`exports/db_handoff/current_full_tables/`

这些 CSV 保留当前表的全部字段和当前数据内容：

| 文件 | 用途 |
| --- | --- |
| `companies.csv` | 公司基础信息完整导出 |
| `shareholder_entities.csv` | 股东/公司/自然人/机构主体完整导出 |
| `shareholder_structures.csv` | 股权、协议、董事会、VIE、代持等关系边完整导出 |
| `relationship_sources.csv` | 关系边证据来源完整导出，当前为空表但保留 header |
| `entity_aliases.csv` | 主体别名完整导出，当前为空表但保留 header |

### 对接推荐模板版

路径：`exports/db_handoff/recommended_input_templates/`

这些 CSV 是推荐传给网页端 GPT 扩展测试数据的版本，保留算法最有价值的输入字段，去掉 `created_at / updated_at` 等系统维护字段：

| 文件 | 用途 |
| --- | --- |
| `companies_input_template.csv` | 推荐公司主表输入模板 |
| `shareholder_entities_input_template.csv` | 推荐主体节点输入模板 |
| `shareholder_structures_input_template.csv` | 推荐控制关系边输入模板 |
| `relationship_sources_input_template.csv` | 可选证据来源模板 |
| `entity_aliases_input_template.csv` | 可选别名模板 |

### 输出表 header 参考

路径：`exports/db_handoff/output_table_headers/`

这些文件只有 header，用于说明结构，不应作为基础输入数据提供给 GPT：

| 文件 | 用途 |
| --- | --- |
| `control_relationships_headers.csv` | 控制关系结果表字段参考 |
| `country_attributions_headers.csv` | 国家归属结果表字段参考 |
| `control_inference_runs_headers.csv` | 控制推断运行记录字段参考 |
| `control_inference_audit_log_headers.csv` | 控制推断审计步骤字段参考 |

## 2. 表分类

| 分类 | 表 | 是否给数据抓取同学准备 | 是否给网页端 GPT 作为原始输入 |
| --- | --- | --- | --- |
| 基础输入表 | `companies` | 是 | 是 |
| 基础输入表 | `shareholder_entities` | 是 | 是 |
| 基础输入表 | `shareholder_structures` | 是 | 是 |
| 可选辅助表 | `relationship_sources` | 建议有来源时提供 | 可选 |
| 可选辅助表 | `entity_aliases` | 建议有别名时提供 | 可选 |
| 算法输出表 | `control_relationships` | 不应由抓取同学作为事实输入批量填写 | 否，只能看 header 或样例 |
| 算法输出表 | `country_attributions` | 不应由抓取同学作为事实输入批量填写 | 否，只能看 header 或样例 |
| 过程留痕表 | `control_inference_runs` | 否 | 否 |
| 过程留痕表 | `control_inference_audit_log` | 否 | 否 |
| 过程留痕表 | `shareholder_structure_history` | 一般由系统写入 | 否 |
| 行业分析表 | `business_segments` / `business_segment_classifications` | 行业模块使用 | 不属于控制链必要输入 |
| 操作留痕表 | `annotation_logs` | 系统操作记录 | 否 |

## 3. 每张表的用途

`companies` 是目标公司主表。当前控制算法以 `company_id` 为入口，国家归属 fallback 会使用 `companies.incorporation_country`。

`shareholder_entities` 是控制图中的节点表。每个待分析公司必须在这里有一条 `company_id = companies.id` 的映射实体，否则算法无法从公司进入控制图。

`shareholder_structures` 是控制图中的边表。当前算法只加载 `is_current = 1`、`is_direct = 1` 且日期有效的边，并把这些边转换成股权或语义控制因子。

`relationship_sources` 是关系边证据来源表。当前核心打分不直接读取它，但它能帮助人工复核、论文说明和后续可信度扩展。

`entity_aliases` 是主体别名表。当前核心算法不依赖它，但对抓取、实体匹配、展示和去重有帮助。

`control_relationships` 是控制分析结果表，保存 direct controller、intermediate controller、ultimate controller、候选控制人、控制路径和得分。它是算法写回结果，不是原始事实输入。

`country_attributions` 是国家归属结果表，保存实际控制国家、归属类型、归属层级和依据。它同样是算法写回结果，不是基础输入。

`control_inference_runs` 记录每次刷新分析的运行参数、阈值、模式和结果摘要。

`control_inference_audit_log` 记录推断过程中的关键动作，例如候选人选择、向上穿透、阻断、终局确认和共同控制识别。

## 4. 字段分级说明

字段等级分为：

- 必须字段：缺失后算法很难正常运行，或 CSV 对接无法表达关系。
- 条件必须字段：在某类关系中必须提供，例如股权边需要 `holding_ratio`，董事会控制需要席位或文本证据。
- 建议字段：明显提升 ultimate controller、joint control、nominee、VIE 等判断质量。
- 可选字段：增强解释性、展示、证据、后续扩展。
- 系统字段：主要由数据库或算法写入，不建议作为 GPT 造数重点。

### `companies`

| 字段 | 含义 | 等级 | 允许为空 | 样例 | 对算法的影响 |
| --- | --- | --- | --- | --- | --- |
| `id` | 公司主键 | 必须 | 否 | `1` | `company_id` 分析入口和外键关联 |
| `name` | 公司名称 | 必须 | 否 | `腾讯控股有限公司` | 展示、人工识别、对接说明 |
| `stock_code` | 股票代码或内部代码 | 建议 | 否 | `0700.HK` | 当前不打分，但便于去重和抓取对齐 |
| `incorporation_country` | 注册地国家/地区 | 必须 | 否 | `China` | 无控制人或控制人国家缺失时的 fallback 国家 |
| `listing_country` | 上市地国家/地区 | 建议 | 否 | `Hong Kong` | 当前主要复制到结果表，不直接参与 fallback |
| `headquarters` | 总部所在地 | 可选 | 否 | `Shenzhen` | 当前不参与控制判断，可用于说明 |
| `description` | 公司描述 | 可选 | 是 | `互联网与金融科技企业` | 当前不参与控制判断 |

### `shareholder_entities`

| 字段 | 含义 | 等级 | 允许为空 | 样例 | 对算法的影响 |
| --- | --- | --- | --- | --- | --- |
| `id` | 主体主键 | 必须 | 否 | `1001` | 关系边 `from_entity_id / to_entity_id` 依赖它 |
| `entity_name` | 主体名称 | 必须 | 否 | `Founder Holding Ltd.` | 控制路径、输出结果、人工核验 |
| `entity_type` | 主体类型 | 必须 | 否 | `company` / `person` / `government` | 自然人和政府更容易被视作终局主体 |
| `country` | 主体国家/地区 | 建议 | 是 | `China` | 控制人国家优先取该字段 |
| `company_id` | 映射到公司主表的 ID | 条件必须 | 是 | `1` | 目标公司必须有映射实体；上游公司有映射时可继续取其注册地 |
| `identifier_code` | 统一社会信用代码、注册号、LEI 等 | 可选 | 是 | `91440300...` | 当前不打分，帮助去重和溯源 |
| `is_listed` | 是否上市 | 可选 | 是 | `1` | 当前不打分，可用于解释主体属性 |
| `entity_subtype` | 主体子类型 | 建议 | 是 | `holding_company` / `spv` / `family_vehicle` | 帮助判断是否应继续向上穿透或终止 |
| `ultimate_owner_hint` | 是否提示为终局所有人 | 建议 | 否，默认 `0` | `1` | 为真时算法倾向在该主体终止上卷 |
| `look_through_priority` | 穿透优先级 | 可选 | 否，默认 `0` | `1` | 当前影响较弱，可为后续规则扩展准备 |
| `controller_class` | 控制人类别 | 建议 | 是 | `natural_person` / `state` | `natural_person`、`state` 会触发终局停止倾向 |
| `beneficial_owner_disclosed` | 是否已披露受益所有人 | 建议 | 否，默认 `0` | `1` | nominee/beneficial owner 场景中会影响是否阻断上卷 |
| `notes` | 备注 | 可选 | 是 | `Founder family vehicle` | 当前不直接打分 |
| `created_at` | 创建时间 | 系统字段 | 否 | `2026-04-17 10:00:00` | 不建议由 GPT 生成 |
| `updated_at` | 更新时间 | 系统字段 | 否 | `2026-04-17 10:00:00` | 不建议由 GPT 生成 |

### `shareholder_structures`

| 字段 | 含义 | 等级 | 允许为空 | 样例 | 对算法的影响 |
| --- | --- | --- | --- | --- | --- |
| `id` | 关系边主键 | 必须 | 否 | `5001` | 控制路径、证据来源、审计输出会引用 |
| `from_entity_id` | 上游控制/持股主体 | 必须 | 否 | `1001` | 控制图边的起点 |
| `to_entity_id` | 下游被控制/被持股主体 | 必须 | 否 | `1` | 控制图边的终点 |
| `holding_ratio` | 持股比例，0-100 | 条件必须 | 是 | `55.0000` | 股权边的核心数值因子 |
| `voting_ratio` | 表决权比例，0-100 | 建议 | 是 | `65.0000` | 表决权控制、协议控制会读取或写入元数据 |
| `economic_ratio` | 经济收益比例，0-100 | 可选 | 是 | `40.0000` | VIE、收益权说明和后续扩展 |
| `is_direct` | 是否直接关系边 | 必须 | 否 | `1` | 当前算法只加载 `is_direct = 1` 的边 |
| `control_type` | 控制类型兼容字段 | 建议 | 是 | `equity` / `agreement` | `relation_type` 缺失时用于推断关系类型 |
| `relation_type` | 标准关系类型 | 必须 | 是 | `equity` / `board_control` / `vie` | 决定按股权还是语义控制处理 |
| `has_numeric_ratio` | 是否有数值比例 | 可选 | 否，默认 `0` | `1` | 当前可自动推断，更多用于展示和兼容 |
| `is_beneficial_control` | 是否代表受益控制 | 建议 | 否，默认 `0` | `1` | nominee 场景中帮助确认受益控制 |
| `look_through_allowed` | 是否允许继续上穿 | 建议 | 否，默认 `1` | `0` | 为假时会阻断 ultimate controller 上卷 |
| `termination_signal` | 终止/阻断信号 | 建议 | 是 | `beneficial_owner_unknown` | 可直接阻断或标记 joint/protective/unknown 等场景 |
| `effective_control_ratio` | 有效控制比例，0-100 | 建议 | 是 | `70.0000` | 股权边优先用它替代 `holding_ratio` 打分 |
| `relation_role` | 关系角色 | 可选 | 是 | `ownership` / `contractual` | 主要用于输出、展示和解释 |
| `control_basis` | 控制依据文本 | 条件必须 | 是 | `right to appoint majority of directors` | 非股权语义控制的核心证据文本 |
| `board_seats` | 可任命或控制董事席位数 | 条件必须 | 是 | `4` | 董事会控制因子，最好配合总席位元数据 |
| `nomination_rights` | 董事提名权说明 | 建议 | 是 | `appoint 4 of 7 directors` | 董事会控制文本证据 |
| `agreement_scope` | 协议/VIE/表决权范围 | 建议 | 是 | `exclusive service agreement and voting proxy` | agreement、vie、voting_right 的主要语义证据 |
| `relation_metadata` | JSON 扩展信息 | 建议 | 是 | `{"total_board_seats":7}` | 可提供总席位、effective_voting_ratio、beneficiary_controls 等 |
| `relation_priority` | 边遍历优先级 | 可选 | 是 | `20` | 影响边排序，缺失时按关系类型默认优先级 |
| `confidence_level` | 证据置信度 | 建议 | 是 | `high` / `medium` / `low` | 转换为 `confidence_weight`，影响候选人置信度 |
| `reporting_period` | 报告期 | 可选 | 是 | `2024A` | 当前不直接参与控制判断 |
| `effective_date` | 生效日期 | 建议 | 是 | `2024-01-01` | 日期晚于分析日会被过滤 |
| `expiry_date` | 失效日期 | 建议 | 是 | `2026-12-31` | 日期早于分析日会被过滤 |
| `is_current` | 是否当前有效 | 必须 | 否 | `1` | 为 `0` 时算法直接忽略 |
| `source` | 简要来源 | 可选 | 是 | `annual_report_2024` | 当前不打分，但便于追溯 |
| `remarks` | 备注和兼容文本 | 建议 | 是 | `joint control by unanimous consent` | 可用于关系类型补推断和语义关键词识别 |
| `created_at` | 创建时间 | 系统字段 | 否 | `2026-04-17 10:00:00` | 不建议由 GPT 生成 |
| `updated_at` | 更新时间 | 系统字段 | 否 | `2026-04-17 10:00:00` | 不建议由 GPT 生成 |

### `relationship_sources`

| 字段 | 含义 | 等级 | 允许为空 | 样例 | 对算法的影响 |
| --- | --- | --- | --- | --- | --- |
| `id` | 来源记录主键 | 可选 | 否 | `1` | 便于引用 |
| `structure_id` | 对应关系边 ID | 条件必须 | 否 | `5001` | 没有关联边则来源无意义 |
| `source_type` | 来源类型 | 建议 | 是 | `annual_report` / `filing` / `web` | 当前不打分，便于证据分层 |
| `source_name` | 来源名称 | 建议 | 是 | `2024 Annual Report` | 便于复核 |
| `source_url` | 来源链接 | 可选 | 是 | `https://...` | 便于复核 |
| `source_date` | 来源日期 | 可选 | 是 | `2025-03-31` | 便于判断时效 |
| `excerpt` | 证据摘录 | 建议 | 是 | `The founder controls voting rights...` | 后续可用于解释和 LLM 复核 |
| `confidence_level` | 来源置信度 | 建议 | 是 | `high` | 当前核心算法不读取，后续可并入置信度 |
| `created_at` | 创建时间 | 系统字段 | 否 | `2026-04-17 10:00:00` | 不建议由 GPT 生成 |
| `updated_at` | 更新时间 | 系统字段 | 否 | `2026-04-17 10:00:00` | 不建议由 GPT 生成 |

### `entity_aliases`

| 字段 | 含义 | 等级 | 允许为空 | 样例 | 对算法的影响 |
| --- | --- | --- | --- | --- | --- |
| `id` | 别名记录主键 | 可选 | 否 | `1` | 便于引用 |
| `entity_id` | 对应主体 ID | 条件必须 | 否 | `1001` | 没有关联主体则别名无意义 |
| `alias_name` | 别名 | 建议 | 否 | `Tencent Holdings` | 当前不打分，帮助抓取、匹配和去重 |
| `alias_type` | 别名类型 | 可选 | 是 | `english` / `short_name` | 便于展示和实体匹配 |
| `is_primary` | 是否主别名 | 可选 | 否，默认 `0` | `1` | 当前不打分 |
| `created_at` | 创建时间 | 系统字段 | 否 | `2026-04-17 10:00:00` | 不建议由 GPT 生成 |
| `updated_at` | 更新时间 | 系统字段 | 否 | `2026-04-17 10:00:00` | 不建议由 GPT 生成 |

## 5. 输入事实字段和算法写回字段不要混淆

抓取同学应主要提供这些输入事实字段：

- `companies`：公司名称、代码、注册地、上市地、总部、描述。
- `shareholder_entities`：主体名称、类型、国家、公司映射、主体子类型、终局提示、受益所有人披露状态。
- `shareholder_structures`：上游主体、下游主体、持股比例、表决权比例、关系类型、是否当前有效、日期、控制依据、协议范围、董事席位、置信度、来源说明。
- `relationship_sources`：年报、公告、网页、人工整理等证据来源。
- `entity_aliases`：中英文名、简称、旧名、股票简称等别名。

算法或系统写回这些字段和表：

- `control_relationships`：控制人候选、direct/intermediate/ultimate 标记、控制路径、控制得分、语义标签、review 状态。
- `country_attributions`：实际控制国家、归属类型、归属层级、是否向上穿透、国家推断原因。
- `control_inference_runs`：每次推断的参数、阈值、状态、摘要。
- `control_inference_audit_log`：推断步骤和阻断原因。
- `shareholder_structure_history`：通过 API 创建或更新结构边时的变更记录。

除非是人工 override 或结果校验样例，不建议让 GPT 生成 `control_relationships` 和 `country_attributions` 的数据行。否则会把“输入事实”和“算法结论”混在一起，后续很难判断结果到底是算出来的还是预填的。

## 6. 最小可运行输入集

如果只准备一版基础测试数据，至少提供：

1. `companies`
   - `id`
   - `name`
   - `stock_code`
   - `incorporation_country`
   - `listing_country`
   - `headquarters`

2. `shareholder_entities`
   - 每个待分析公司一条目标实体：`company_id = companies.id`
   - 所有上游股东或控制主体：`id`、`entity_name`、`entity_type`、`country`

3. `shareholder_structures`
   - `id`
   - `from_entity_id`
   - `to_entity_id`
   - `relation_type = equity`
   - `holding_ratio`
   - `is_direct = 1`
   - `is_current = 1`
   - `effective_date / expiry_date` 可为空，表示不限制日期

有了这三张表，算法可以完成基础股权穿透、direct controller、ultimate controller 和 fallback 国家归属判断。

## 7. 增强版输入集

为了让算法更好地区分复杂场景，建议补充：

| 场景 | 建议补充字段 |
| --- | --- |
| direct controller | `holding_ratio`、`effective_control_ratio`、`voting_ratio`、`confidence_level` |
| ultimate controller | 上游多层 `shareholder_structures`、`entity_subtype`、`controller_class`、`ultimate_owner_hint`、`look_through_allowed` |
| joint control | `relation_type`、`control_basis`、`agreement_scope`、`remarks` 中明确 joint/unanimous/acting in concert 等证据 |
| fallback | 缺少有效控制边时确保 `companies.incorporation_country` 准确 |
| nominee / beneficial owner | `relation_type = nominee`、`is_beneficial_control`、`beneficial_owner_disclosed`、`termination_signal`、`relation_metadata` |
| SPV / holding company | `entity_subtype = spv / holding_company / shell_company`、上游控制边、`look_through_allowed` |
| 董事会控制 | `relation_type = board_control`、`board_seats`、`nomination_rights`、`relation_metadata.total_board_seats` |
| VIE / 协议控制 | `relation_type = vie / agreement`、`agreement_scope`、`control_basis`、`economic_ratio`、`relation_metadata` |
| 表决权控制 | `relation_type = voting_right`、`voting_ratio`、`agreement_scope`、`relation_metadata.effective_voting_ratio` |

## 8. 推荐给网页端 GPT 的文件组合

优先传这三份核心模板：

- `exports/db_handoff/recommended_input_templates/companies_input_template.csv`
- `exports/db_handoff/recommended_input_templates/shareholder_entities_input_template.csv`
- `exports/db_handoff/recommended_input_templates/shareholder_structures_input_template.csv`

如果要让 GPT 同时生成证据和别名，再加：

- `exports/db_handoff/recommended_input_templates/relationship_sources_input_template.csv`
- `exports/db_handoff/recommended_input_templates/entity_aliases_input_template.csv`

不要把以下文件作为原始输入数据传给 GPT：

- `exports/db_handoff/output_table_headers/control_relationships_headers.csv`
- `exports/db_handoff/output_table_headers/country_attributions_headers.csv`
- `exports/db_handoff/output_table_headers/control_inference_runs_headers.csv`
- `exports/db_handoff/output_table_headers/control_inference_audit_log_headers.csv`

这些只能作为“算法输出长什么样”的字段参考。
