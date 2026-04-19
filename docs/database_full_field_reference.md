# 数据库完整字段说明与模块边界参考

本文档是当前仓库的数据库字典、模块边界说明和协作 handoff 文档。它以当前代码为准，核对了 `backend/models/`、`backend/schemas/`、`backend/api/`、`backend/crud/`、`backend/analysis/`、`backend/tasks/`、`scripts/`、前端消费代码以及既有数据库说明文档。

如果旧文档、历史 handoff 或原始数据导入说明与本文档不一致，以本文档和当前代码为准。旧文档仍可作为历史背景，但不应替代本文件做字段对接。

生成日期：2026-04-19  
当前默认 SQLite 文件：`company_test_analysis_industry_v2.db`  
当前 SQLAlchemy 主表数量：13 张

## 1. 核对范围与结论

本次核对的主要代码入口如下：

| 范围 | 代码位置 | 本文档使用方式 |
| --- | --- | --- |
| SQLAlchemy 模型 | `backend/models/` | 作为表、字段、类型、主外键、索引、可空性的第一依据 |
| Pydantic Schema | `backend/schemas/` | 判断哪些字段可通过 API 创建、更新、读取 |
| API 路由 | `backend/api/` | 判断前端和外部协作真实消费哪些字段 |
| CRUD | `backend/crud/` | 判断字段写入、更新、留痕、副作用 |
| 控制分析逻辑 | `backend/analysis/control_inference.py`、`backend/analysis/ownership_penetration.py`、`backend/analysis/ownership_graph.py` | 判断股权控制算法真实读取哪些输入字段、写回哪些输出字段 |
| 产业研究逻辑 | `backend/analysis/industry_analysis.py` | 判断产业研究模块读取、聚合、质检、对比哪些字段 |
| 导入/升级/重算脚本 | `scripts/`、`backend/tasks/recompute_analysis_results.py` | 判断历史数据、CSV 对接和升级兼容边界 |
| 前端消费 | `frontend/src/api/`、`frontend/src/components/`、`frontend/src/views/` | 判断字段是否进入当前展示页面 |
| 既有文档 | `docs/database_handoff_guide.md`、`docs/full_database_design_v2.md`、`docs/industry_analysis_database_structure.md`、`docs/semantic_control_evidence_model_v1.md` | 作为背景参考，发现差异时以代码为准 |

实际数据库文件核对结果：

| 数据库文件 | 表情况 | 说明 |
| --- | --- | --- |
| `company_test_analysis_industry_v2.db` | 13 张表齐全。当前数据较少：公司 1 行、主体 1 行、关系边 0 行、控制结果 1 行、国别结果 1 行、产业表为空 | 当前默认库更像结构和演示壳，不代表满量样本 |
| `company_test_analysis_industry.db` | 13 张表齐全，且有满量样本：公司 10000 行、关系边 105000 行、产业业务线 21282 行、产业分类 26787 行 | 更能反映当前完整数据设计的使用方式 |
| `company_test_analysis.db` | 只有 6 张原始输入/辅助表，且 `shareholder_entities`、`shareholder_structures` 是旧字段子集 | 历史原始导入库，不具备 v2 输出表和产业表 |

## 2. 数据库整体分层

| 分层 | 表 | 业务含义 | 输入/输出属性 |
| --- | --- | --- | --- |
| 基础主数据 | `companies` | 公司主表，控制分析和产业研究共用入口 | 基础输入 |
| 控制图节点 | `shareholder_entities` | 公司、自然人、机构、基金、政府等主体节点 | 股权分析输入，部分字段为控制推断增强输入 |
| 控制图边 | `shareholder_structures` | 股权、协议、董事会、表决权、代持、VIE 等关系边 | 股权分析核心输入 |
| 关系证据 | `relationship_sources` | 关系边来源、链接、摘录、来源置信度 | 股权分析增强输入，证据留痕 |
| 实体别名 | `entity_aliases` | 主体中英文名、简称、旧名、股票简称等 | 通用辅助输入 |
| 关系变更历史 | `shareholder_structure_history` | 关系边创建、更新、归一化、人工修订历史 | 过程留痕 |
| 控制结果 | `control_relationships` | direct、intermediate、ultimate、candidate 控制关系输出 | 股权分析输出 |
| 国别归属结果 | `country_attributions` | 实际控制国家、归属类型、归属层级输出 | 国别归属输出 |
| 推断运行记录 | `control_inference_runs` | 单次控制推断参数、阈值、状态、摘要 | 运行留痕 |
| 推断审计日志 | `control_inference_audit_log` | 控制推断步骤、上卷、阻断、终局确认等动作 | 审计留痕 |
| 产业业务事实 | `business_segments` | 主营业务、业务线、收入/利润占比、报告期 | 产业研究输入 |
| 产业分类结果 | `business_segment_classifications` | 业务线到 GICS 等分类体系的映射 | 产业研究结果/人工修订对象 |
| 通用人工标注 | `annotation_logs` | 业务线和分类的人工创建、更新、确认、覆盖、删除留痕 | 人工标注/修订留痕 |

## 3. 股权分析与产业研究边界

### 3.1 表级归属

| 表 | 归属判断 | 原因 |
| --- | --- | --- |
| `companies` | 两者共用基础数据 | 控制分析用 `company_id` 进入控制图并在 fallback 时用注册地；产业研究用 `company_id` 聚合业务线 |
| `shareholder_entities` | 仅股权分析，兼具基础主体主数据属性 | 当前产业研究不读取主体节点；控制分析依赖主体类型、国家、公司映射、终局主体字段 |
| `shareholder_structures` | 仅股权分析 | 控制图边，是控制推断最核心输入 |
| `relationship_sources` | 仅股权分析增强输入 | 当前 unified 控制引擎读取来源存在性、摘录、来源置信度并影响 reliability |
| `entity_aliases` | 通用辅助数据，当前主要服务股权数据整理 | 当前控制算法和产业研究主流程均不直接依赖，但对实体匹配、抓取、展示有价值 |
| `shareholder_structure_history` | 输出/留痕，不属于原始事实输入 | 通过结构边 CRUD 自动写入 insert/update 历史，也可手工补充 |
| `control_relationships` | 股权分析输出 | 保存控制候选、实际控制人、控制路径、得分、层级 |
| `country_attributions` | 国别归属输出 | 根据控制链或 fallback 写回实际控制国家，不是原始注册地输入 |
| `control_inference_runs` | 股权分析运行留痕 | 记录单次 refresh 参数和结果摘要 |
| `control_inference_audit_log` | 股权分析审计留痕 | 记录推断过程动作和阻断原因 |
| `business_segments` | 仅产业研究 | 控制链不依赖业务线；产业研究主流程核心输入 |
| `business_segment_classifications` | 仅产业研究 | 控制链不依赖产业分类；产业分析聚合、质检、历史对比核心表 |
| `annotation_logs` | 当前主要服务产业研究人工修订 | 通用设计，但当前代码只围绕业务线和分类写入、读取 |

### 3.2 字段级标记说明

字段明细表中的“股权核心”和“产业核心”按以下含义判断：

| 标记 | 含义 |
| --- | --- |
| 是 | 当前主流程直接依赖，缺失会影响主链路 |
| 增强 | 当前主流程会读取或输出，但缺失时可降级 |
| 输出 | 由算法、接口或系统写回，不是原始输入 |
| 前端 | 主要服务当前页面展示或图渲染 |
| 否 | 当前主流程不直接依赖 |
| 预留 | 代码有字段或枚举，但当前影响较弱，主要为后续扩展 |
| 留痕 | 用于审计、变更历史或人工修订记录 |

## 4. 表关系总览

```text
companies.id
  -> shareholder_entities.company_id
  -> control_relationships.company_id
  -> country_attributions.company_id
  -> control_inference_runs.company_id
  -> control_inference_audit_log.company_id
  -> business_segments.company_id

shareholder_entities.id
  -> shareholder_structures.from_entity_id
  -> shareholder_structures.to_entity_id
  -> control_relationships.controller_entity_id
  -> control_relationships.promotion_source_entity_id
  -> entity_aliases.entity_id

shareholder_structures.id
  -> relationship_sources.structure_id
  -> shareholder_structure_history.structure_id

control_inference_runs.id
  -> control_relationships.inference_run_id
  -> country_attributions.inference_run_id
  -> control_inference_audit_log.inference_run_id

business_segments.id
  -> business_segment_classifications.business_segment_id

annotation_logs.target_type + annotation_logs.target_id
  -> weak reference to business_segments.id or business_segment_classifications.id
```

注意：`country_attributions.actual_controller_entity_id` 和 `country_attributions.direct_controller_entity_id` 在 SQLAlchemy 模型中只是带索引的整数，不是数据库外键。业务上它们指向 `shareholder_entities.id`，但数据库层当前没有强约束。

## 5. 字段分级规则

本文档使用以下字段分级：

| 分级 | 判断标准 |
| --- | --- |
| 核心必需字段 | 表达主业务实体、关系或算法入口，缺失后主流程不能正常运行 |
| 条件必需字段 | 特定关系类型或场景下必需，例如股权边需要比例，董事会控制需要席位或证据文本 |
| 建议字段 | 不阻断主流程，但会显著提升推断、展示、追溯或质量检查 |
| 可选字段 | 当前主流程弱依赖或不依赖，主要用于展示、去重、扩展 |
| 系统维护字段 | 主键、时间戳、运行状态、自动写回字段等 |
| 算法输出字段 | 由控制推断、国别归属或产业聚合写回/返回 |
| 历史兼容/预留字段 | 为旧数据、旧算法、未来扩展保留，当前主流程影响有限 |

## 6. 逐表字段说明

### 6.1 `companies`

表作用：公司主表，是系统中所有公司级分析的共同入口。股权控制分析以 `companies.id` 作为请求入口，再通过 `shareholder_entities.company_id` 找到控制图中的目标实体；产业研究模块也以 `company_id` 读取业务线和产业分类。

模块分类：基础主数据表，两者共用。  
输入/输出属性：基础输入。  
主流程使用：股权分析、国别归属、产业研究、前端公司页均使用。  
前端消费：`CompanyRead`、`CompanyAnalysisSummaryRead`、关系图 target company。

字段分级：

- 核心必需字段：`id`、`name`、`stock_code`、`incorporation_country`、`listing_country`、`headquarters`
- 建议字段：`description`
- 系统维护字段：无显式时间戳字段

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 公司主键 | 否 | PK、index | 所有公司级分析入口和外键目标 | 是 | 是 | 前端搜索当前使用 `company_id` |
| `name` | String(255) | 公司名称 | 否 | index | 展示、导入、论文说明、图谱目标公司名称 | 增强 | 增强 | 不参与控制打分 |
| `stock_code` | String(50) | 股票代码或内部公司代码 | 否 | unique、index | 去重、导入校验、公司识别 | 增强 | 增强 | API 创建/更新会校验唯一 |
| `incorporation_country` | String(100) | 注册地国家/地区 | 否 | 无 | 国别归属 fallback；写入国别结果快照 | 是 | 否 | 无控制人时 `actual_control_country` 可 fallback 到该字段 |
| `listing_country` | String(100) | 上市地国家/地区 | 否 | 无 | 公司基础展示；写入国别结果快照 | 增强 | 否 | 当前控制算法不以它作为归属优先来源 |
| `headquarters` | String(255) | 总部所在地 | 否 | 无 | 公司概览和业务说明 | 否 | 增强 | 当前算法不读取 |
| `description` | Text | 公司描述 | 是 | 无 | 展示、协作说明、后续文本扩展 | 否 | 增强 | 可为空 |

当前实际使用情况：

- 当前主流程真实使用，是股权控制和产业研究的共同公司级入口。
- 控制分析刷新前会先校验公司是否存在。
- `incorporation_country` 是国别 fallback 的核心字段。
- 前端综合页读取并展示公司基础信息。

与其他表关系：

- 一对多：`companies.id` -> `shareholder_entities.company_id`
- 一对多：`companies.id` -> `control_relationships.company_id`
- 一对多：`companies.id` -> `country_attributions.company_id`
- 一对多：`companies.id` -> `control_inference_runs.company_id`
- 一对多：`companies.id` -> `business_segments.company_id`

### 6.2 `shareholder_entities`

表作用：控制图节点表，统一表达公司、自然人、机构、基金、政府和其他主体。每家待分析公司必须至少有一条 `company_id = companies.id` 的映射实体，否则控制分析无法从公司进入控制图。

模块分类：股权分析输入表，兼具主体主数据属性。  
输入/输出属性：基础输入和增强输入。  
主流程使用：控制图构建、国家归属、终局控制人判断、前端关系图。  
前端消费：关系图节点、上游股东接口、控制结果中的 controller 快照。

字段分级：

- 核心必需字段：`id`、`entity_name`、`entity_type`
- 条件必需字段：`company_id`，目标公司映射实体必须有；上游主体可为空
- 建议字段：`country`、`entity_subtype`、`controller_class`、`beneficial_owner_disclosed`、`ultimate_owner_hint`
- 可选字段：`identifier_code`、`is_listed`、`notes`
- 预留字段：`look_through_priority`
- 系统维护字段：`created_at`、`updated_at`

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 主体主键 | 否 | PK、index | 作为控制图节点 ID | 是 | 否 | 被关系边、别名、控制结果引用 |
| `entity_name` | String(255) | 主体标准名称 | 否 | index | 图节点展示、控制人名称快照、路径输出 | 是 | 否 | 控制结果也会复制为 `controller_name` |
| `entity_type` | Enum/String | 主体类型：`company`、`person`、`institution`、`fund`、`government`、`other` | 否 | index | 终局主体判断、展示、控制人类型快照 | 是 | 否 | 自然人、政府更容易被视作终局主体 |
| `country` | String(100) | 主体国家/地区 | 是 | 无 | 控制人国家优先来源 | 是 | 否 | 缺失时若映射公司存在，则取映射公司注册地 |
| `company_id` | Integer | 若该主体对应公司主表，则引用公司 ID | 是 | FK -> `companies.id`、index | 公司进入控制图的映射点；上游公司国家补全 | 是 | 否 | 目标公司必须有映射实体 |
| `identifier_code` | String(100) | 注册号、统一信用代码、LEI、股票代码等识别码 | 是 | 无 | 去重、导入、人工核验 | 增强 | 否 | 当前算法不打分 |
| `is_listed` | Boolean | 是否上市主体 | 是 | 无 | 展示和主体属性说明 | 否 | 否 | 当前算法不直接读取 |
| `entity_subtype` | String(50) | 主体子类型，如 `holding_company`、`spv`、`shell_company`、`state_owned_vehicle`、`trust` | 是 | index | 判断是否中间持股平台、信托、终局实体 | 增强 | 否 | `prepare_shareholder_entity_values` 会默认补 `unknown` |
| `ultimate_owner_hint` | Boolean | 是否提示为终局所有人 | 否 | default 0 | 终局停步、上卷原因判断 | 增强 | 否 | 当前 unified 引擎读取 |
| `look_through_priority` | Integer | 穿透优先级 | 否 | default 0 | 预留给更细的穿透排序策略 | 预留 | 否 | 当前控制推断主逻辑影响弱 |
| `controller_class` | String(50) | 控制人类别，如 `natural_person`、`corporate_group`、`state`、`fund_complex`、`trust_structure` | 是 | index | 终局控制人分类、信托/国家/自然人判断 | 增强 | 否 | `natural_person`、`state` 是终局类别 |
| `beneficial_owner_disclosed` | Boolean | 是否已披露受益所有人 | 否 | default 0 | nominee、trust、beneficial owner 场景的穿透判断 | 增强 | 否 | 当前 unified 引擎读取 |
| `notes` | Text | 主体备注 | 是 | 无 | 人工说明、展示、后续文本扩展 | 否 | 否 | 当前控制推断不直接使用 |
| `created_at` | DateTime | 创建时间 | 否 | server default now | 系统维护 | 否 | 否 | API 读取返回 |
| `updated_at` | DateTime | 更新时间 | 否 | server default now、onupdate | 系统维护 | 否 | 否 | API 读取返回 |

当前实际使用情况：

- 当前股权主流程真实使用，是控制图节点层。
- `company_id` 是从公司进入控制图的入口。
- `country`、`company_id`、`company.incorporation_country` 共同决定控制人国家。
- `entity_subtype`、`controller_class`、`ultimate_owner_hint`、`beneficial_owner_disclosed` 是 v2/unified 终局控制推断的重要增强字段。
- 当前产业研究主流程不读取该表。

与其他表关系：

- 多对一：`shareholder_entities.company_id` -> `companies.id`
- 一对多：`shareholder_entities.id` -> `shareholder_structures.from_entity_id`
- 一对多：`shareholder_entities.id` -> `shareholder_structures.to_entity_id`
- 一对多：`shareholder_entities.id` -> `entity_aliases.entity_id`
- 一对多：`shareholder_entities.id` -> `control_relationships.controller_entity_id`
- 一对多：`shareholder_entities.id` -> `control_relationships.promotion_source_entity_id`

### 6.3 `shareholder_structures`

表作用：控制图边表，是股权控制分析最核心的事实输入。它不仅表达传统持股关系，也表达协议控制、董事会控制、表决权控制、代持、VIE 等语义控制关系。

模块分类：股权分析核心输入表。  
输入/输出属性：原始事实输入，部分字段由导入/CRUD 归一化补全。  
主流程使用：控制图构建、控制路径搜索、语义证据评分、关系图展示。  
前端消费：关系图边、上游股东接口、控制结构图辅助信息。

字段分级：

- 核心必需字段：`id`、`from_entity_id`、`to_entity_id`、`is_direct`、`is_current`
- 条件必需字段：股权边需要 `holding_ratio` 或 `effective_control_ratio`；董事会/协议/VIE/表决权/代持边需要 `relation_type` 和足够证据字段
- 建议字段：`relation_type`、`voting_ratio`、`economic_ratio`、`effective_control_ratio`、`control_basis`、`board_seats`、`nomination_rights`、`agreement_scope`、`relation_metadata`、`confidence_level`、`look_through_allowed`、`termination_signal`
- 可选字段：`reporting_period`、`source`、`remarks`、`relation_role`
- 预留/兼容字段：`control_type`、`has_numeric_ratio`
- 系统维护字段：`created_at`、`updated_at`

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 关系边主键 | 否 | PK、index | 控制路径、证据来源、历史记录引用 | 是 | 否 | `control_path` 中保存 edge id |
| `from_entity_id` | Integer | 上游持股/控制主体 | 否 | FK -> `shareholder_entities.id`、index | 控制图边起点 | 是 | 否 | 必须存在 |
| `to_entity_id` | Integer | 下游被持股/被控制主体 | 否 | FK -> `shareholder_entities.id`、index | 控制图边终点 | 是 | 否 | 目标公司映射实体常作为起始分析点 |
| `holding_ratio` | Numeric(7,4) | 名义持股比例，通常按 0-100 百分比存储 | 是 | 无 | 股权边数值因子 | 条件必需 | 否 | 股权控制最常用比例；旧导入可能存在 0-1 比例，重算脚本会检测 |
| `voting_ratio` | Numeric(10,4) | 表决权比例 | 是 | 无 | 表决权控制、同股不同权、语义元数据补充 | 增强 | 否 | unified 引擎会读入 metadata |
| `economic_ratio` | Numeric(10,4) | 经济收益或可变回报比例 | 是 | 无 | VIE、收益权、经济利益信号 | 增强 | 否 | unified 引擎会读入 metadata |
| `is_direct` | Boolean | 是否直接关系边 | 否 | default true | 当前控制推断只加载直接边 | 是 | 否 | `is_direct = 0` 当前会被过滤 |
| `control_type` | String(30) | 旧版控制类型兼容字段 | 是 | 无 | `relation_type` 缺失时推断关系类型 | 历史兼容 | 否 | CRUD 会尝试规范化 |
| `relation_type` | String(30) | 标准关系类型：`equity`、`agreement`、`board_control`、`voting_right`、`nominee`、`vie`、`other` | 是 | index | 决定股权还是语义控制边 | 是 | 否 | 为空时会从 `control_type`、`holding_ratio`、`remarks` 推断 |
| `has_numeric_ratio` | Boolean | 是否有数值比例 | 否 | default 0 | 展示、兼容、查询过滤 | 预留 | 否 | 当前 `prepare_shareholder_structure_values` 会根据关系类型和持股比例重算 |
| `is_beneficial_control` | Boolean | 是否代表受益控制或受益人已确认 | 否 | default 0 | nominee/beneficial owner 语义判断 | 增强 | 否 | 会填入 metadata 的 `beneficial_owner_disclosed` 默认来源 |
| `look_through_allowed` | Boolean | 是否允许继续向上穿透 | 否 | default 1 | 阻断或允许 ultimate controller 上卷 | 增强 | 否 | 为假时可能产生 `look_through_not_allowed` 阻断 |
| `termination_signal` | String(50) | 终止或阻断信号，如 `ultimate_disclosed`、`joint_control`、`beneficial_owner_unknown`、`nominee_without_disclosure`、`protective_right_only` | 是 | index | 上卷阻断、终局确认、共同控制判断 | 增强 | 否 | 默认为 `none` |
| `effective_control_ratio` | Numeric(10,4) | 有效控制比例 | 是 | 无 | 股权边优先使用的数值因子 | 增强 | 否 | 若存在，优先于 `holding_ratio` |
| `relation_role` | String(30) | 关系角色：`ownership`、`control`、`governance`、`nominee`、`contractual`、`other` | 是 | 无 | 输出解释、图展示、路径证据 | 增强 | 否 | 可由 `relation_type` 自动推断 |
| `control_basis` | Text | 控制依据文本 | 是 | 无 | 语义控制证据评分 | 条件必需 | 否 | 非股权边非常重要 |
| `board_seats` | Integer | 可任命或控制的董事席位数 | 是 | 无 | 董事会控制 power score | 条件必需 | 否 | 总席位常放在 `relation_metadata.total_board_seats` |
| `nomination_rights` | Text | 董事提名/任命权说明 | 是 | 无 | 董事会控制文本证据 | 增强 | 否 | 也会提高 reliability |
| `agreement_scope` | Text | 协议、VIE、表决权安排范围 | 是 | 无 | 协议控制/VIE/表决权控制文本证据 | 条件必需 | 否 | 强语义边核心字段 |
| `relation_metadata` | Text | JSON 扩展元数据 | 是 | 无 | 结构化补充，如 `total_board_seats`、`effective_voting_ratio`、`beneficial_owner_unknown`、`benefit_capture` | 增强 | 否 | unified 引擎会解析 |
| `relation_priority` | Integer | 边排序优先级 | 是 | 无 | 同一目标多条边时排序 | 增强 | 否 | 缺失时按关系类型默认优先级 |
| `confidence_level` | String(20) | 关系证据置信度：`high`、`medium`、`low`、`unknown` | 是 | index | reliability 基础分 | 增强 | 否 | high 0.9、medium 0.7、unknown 0.6、low 0.4 |
| `reporting_period` | String(20) | 报告期 | 是 | 无 | 展示、导入、历史说明 | 前端 | 否 | 当前控制推断不按该字段过滤 |
| `effective_date` | Date | 生效日期 | 是 | 无 | 当前有效边过滤 | 增强 | 否 | 晚于分析日会被过滤 |
| `expiry_date` | Date | 失效日期 | 是 | 无 | 当前有效边过滤 | 增强 | 否 | 早于分析日会被过滤 |
| `is_current` | Boolean | 是否当前有效 | 否 | default true | 当前有效边过滤 | 是 | 否 | 为 false 时不进入控制推断 |
| `source` | String(255) | 简要来源说明 | 是 | 无 | 关系图展示、reliability source presence 信号 | 增强 | 否 | 与 `relationship_sources` 不同，是边上的简要来源 |
| `remarks` | Text | 备注、兼容文本、证据补充 | 是 | 无 | 关系类型补推断、语义文本证据 | 增强 | 否 | 旧数据可含 `original_control_type=...` |
| `created_at` | DateTime | 创建时间 | 否 | server default now | 系统维护 | 否 | 否 | API 返回 |
| `updated_at` | DateTime | 更新时间 | 否 | server default now、onupdate | 系统维护 | 否 | 否 | API 返回 |

当前实际使用情况：

- 当前股权控制主流程最核心输入。
- `control_inference.build_control_context()` 读取 `is_current = 1`、`is_direct = 1`、日期有效的边。
- `edge_to_factor()` 会将每条边转换为 `numeric_factor`、`semantic_factor`、`reliability_score`、`priority`、`look_through_allowed`、`termination_signal` 等控制因子。
- `ownership_graph` 和前端关系图会序列化当前有效边，并把语义字段一起返回。
- 当前产业研究不读取该表。

与其他表关系：

- 多对一：`from_entity_id`、`to_entity_id` -> `shareholder_entities.id`
- 一对多：`shareholder_structures.id` -> `relationship_sources.structure_id`
- 一对多：`shareholder_structures.id` -> `shareholder_structure_history.structure_id`

### 6.4 `relationship_sources`

表作用：关系边证据来源表，用于保存年报、公告、备案、网页、人工整理等来源信息。当前代码已经不只是“人工复核辅助”：unified 控制引擎会读取该表并根据来源存在性、摘录、链接/名称、来源置信度调整边的 reliability。

模块分类：股权分析增强输入表，证据留痕表。  
输入/输出属性：可选输入和证据辅助。  
主流程使用：控制推断增强、人工复核、论文证据说明。  
前端消费：当前关系支持 API 可读取；关系图主接口暂不逐条暴露完整来源列表。

字段分级：

- 核心必需字段：`id`、`structure_id`
- 建议字段：`source_type`、`source_name`、`source_url`、`excerpt`、`confidence_level`
- 可选字段：`source_date`
- 系统维护字段：`created_at`、`updated_at`

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 来源记录主键 | 否 | PK、index | API CRUD、引用 | 增强 | 否 | 可多条来源对应一条关系边 |
| `structure_id` | Integer | 对应关系边 ID | 否 | FK -> `shareholder_structures.id`、index | 将来源绑定到控制关系边 | 增强 | 否 | 无关联边则来源无业务意义 |
| `source_type` | String(30) | 来源类型，如 `annual_report`、`filing`、`manual`、`synthetic`、`web`、`other` | 是 | 无 | 来源分层、复核 | 增强 | 否 | Schema 会规范化枚举 |
| `source_name` | String(255) | 来源名称 | 是 | 无 | reliability source reference、人工复核 | 增强 | 否 | 存在时会给 reliability 轻微正向信号 |
| `source_url` | String(500) | 来源链接 | 是 | 无 | reliability source reference、复核 | 增强 | 否 | 存在时会给 reliability 轻微正向信号 |
| `source_date` | Date | 来源日期 | 是 | 无 | 时效说明 | 增强 | 否 | 当前推断不按该日期过滤 |
| `excerpt` | Text | 来源摘录 | 是 | 无 | 证据说明和 reliability 增强 | 增强 | 否 | 摘录存在时 reliability 有正向调整 |
| `confidence_level` | String(20) | 来源级置信度 | 是 | 无 | reliability 增强/扣减 | 增强 | 否 | high 有正向调整，low 有负向调整 |
| `created_at` | DateTime | 创建时间 | 否 | server default now | 系统维护 | 否 | 否 | API 返回 |
| `updated_at` | DateTime | 更新时间 | 否 | server default now、onupdate | 系统维护 | 否 | 否 | API 返回 |

当前实际使用情况：

- 通过 `/shareholder-structures/{structure_id}/sources` 系列 API 创建、读取、更新、删除。
- 当前 unified 引擎在构建控制上下文时会按 `structure_id` 读取所有来源。
- 旧文档中“当前核心打分不直接读取该表”的说法已过时，应以当前代码为准。

与其他表关系：

- 多对一：`relationship_sources.structure_id` -> `shareholder_structures.id`

### 6.5 `entity_aliases`

表作用：主体别名表，用于保存英文名、中文名、简称、旧名、股票简称等。它主要服务数据抓取、实体匹配、去重和展示。

模块分类：通用辅助表，当前主要服务股权数据整理。  
输入/输出属性：可选辅助输入。  
主流程使用：当前控制推断和产业研究均不直接读取。  
前端消费：有 API CRUD，当前综合页不作为核心展示。

字段分级：

- 核心必需字段：`id`、`entity_id`、`alias_name`
- 建议字段：`alias_type`、`is_primary`
- 系统维护字段：`created_at`、`updated_at`

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 别名记录主键 | 否 | PK、index | API CRUD | 否 | 否 | 可选辅助 |
| `entity_id` | Integer | 对应主体 ID | 否 | FK -> `shareholder_entities.id`、index | 将别名绑定到主体 | 增强 | 否 | 无主体则别名无意义 |
| `alias_name` | String(255) | 别名文本 | 否 | 无 | 实体匹配、去重、展示 | 增强 | 否 | 当前算法不读取 |
| `alias_type` | String(30) | 别名类型：`english`、`chinese`、`short_name`、`old_name`、`ticker_name`、`other` | 是 | 无 | 区分来源和展示语义 | 增强 | 否 | Schema 会规范化 |
| `is_primary` | Boolean | 是否主别名 | 否 | default 0 | 别名优先展示 | 增强 | 否 | 设为 true 时 CRUD 会清除同主体其他 primary |
| `created_at` | DateTime | 创建时间 | 否 | server default now | 系统维护 | 否 | 否 | API 返回 |
| `updated_at` | DateTime | 更新时间 | 否 | server default now、onupdate | 系统维护 | 否 | 否 | API 返回 |

当前实际使用情况：

- 通过 `/entities/{entity_id}/aliases` 系列 API 使用。
- 当前控制推断不通过别名匹配实体，实体匹配应在导入或数据准备阶段完成。
- 产业研究不读取该表。

与其他表关系：

- 多对一：`entity_aliases.entity_id` -> `shareholder_entities.id`

### 6.6 `shareholder_structure_history`

表作用：关系边变更历史表，用于记录关系边创建、更新、删除、归一化、人工修订、导入等动作的前后快照和原因。

模块分类：过程留痕表，人工修订/审计辅助。  
输入/输出属性：留痕，不属于控制算法原始输入。  
主流程使用：CRUD 创建/更新结构边时写入 insert/update 历史；API 也允许手工追加历史记录。  
前端消费：当前综合页不消费，关系支持 API 可读取。

字段分级：

- 核心必需字段：`id`、`structure_id`、`change_type`
- 建议字段：`old_value`、`new_value`、`change_reason`、`changed_by`
- 系统维护字段：`created_at`

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 历史记录主键 | 否 | PK、index | API 读取、审计引用 | 留痕 | 否 | 系统生成或手工追加 |
| `structure_id` | Integer | 对应关系边 ID | 否 | FK -> `shareholder_structures.id`、index | 将变更绑定到关系边 | 留痕 | 否 | 关系边删除时 ORM cascade 会删除历史 |
| `change_type` | String(30) | 变更类型：`insert`、`update`、`delete`、`normalize`、`manual_fix`、`import` | 否 | 无 | 区分变更场景 | 留痕 | 否 | Schema 会校验枚举 |
| `old_value` | Text | 变更前快照，通常是 JSON 文本 | 是 | 无 | 审计、回溯 | 留痕 | 否 | CRUD update 会写 |
| `new_value` | Text | 变更后快照，通常是 JSON 文本 | 是 | 无 | 审计、回溯 | 留痕 | 否 | CRUD create/update 会写 |
| `change_reason` | Text | 变更原因 | 是 | 无 | 人工说明、导入说明 | 留痕 | 否 | create 默认 `api_create`，update 默认 `api_update` |
| `changed_by` | String(100) | 操作者 | 是 | 无 | 审计追责 | 留痕 | 否 | 默认 `api` 或 `system` |
| `created_at` | DateTime | 创建时间 | 否 | server default now | 系统维护 | 留痕 | 否 | 无 `updated_at` |

当前实际使用情况：

- `create_shareholder_structure()` 会写 insert 历史。
- `update_shareholder_structure()` 在字段有变化时写 update 历史。
- `delete_shareholder_structure()` 当前不主动写 delete 历史，而是直接删除关系边，历史会随关系边 cascade 删除。这一点如果要做审计闭环，后续应统一。
- 控制算法不读取该表。

与其他表关系：

- 多对一：`shareholder_structure_history.structure_id` -> `shareholder_structures.id`

### 6.7 `control_relationships`

表作用：控制关系输出表，保存控制推断得到的候选控制人、直接控制人、中间控制人、最终实际控制人、控制路径、得分、控制模式和复核状态。它不是原始事实输入。

模块分类：股权分析输出表。  
输入/输出属性：算法输出，可支持人工覆盖或手工 CRUD，但不应作为基础事实批量造数。  
主流程使用：控制链读取接口、前端控制摘要、关系图补充实际控制人、国别归属说明。  
前端消费：当前综合页大量消费该表序列化后的字段。

字段分级：

- 算法输出核心字段：`company_id`、`controller_entity_id`、`controller_name`、`controller_type`、`control_type`、`control_ratio`、`control_path`、`is_actual_controller`、`control_tier`、`is_direct_controller`、`is_intermediate_controller`、`is_ultimate_controller`、`basis`、`control_mode`、`semantic_flags`、`review_status`
- 终局上卷增强字段：`promotion_source_entity_id`、`promotion_reason`、`control_chain_depth`、`is_terminal_inference`、`terminal_failure_reason`、`immediate_control_ratio`、`aggregated_control_score`、`terminal_control_score`
- 运行追踪字段：`inference_run_id`、`notes`
- 系统维护字段：`id`、`created_at`、`updated_at`

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 控制关系结果主键 | 否 | PK、index | 结果引用、前端 key | 输出 | 否 | 自动生成 |
| `company_id` | Integer | 目标公司 ID | 否 | FK -> `companies.id`、index | 读取公司控制结果 | 输出 | 否 | 查询按公司过滤 |
| `controller_entity_id` | Integer | 控制主体 ID | 是 | FK -> `shareholder_entities.id`、index | 关联控制图主体 | 输出 | 否 | 某些手工结果可能为空 |
| `controller_name` | String(255) | 控制主体名称快照 | 否 | 无 | 前端展示、结果快照 | 输出 | 否 | 算法从 `shareholder_entities.entity_name` 复制 |
| `controller_type` | String(50) | 控制主体类型快照 | 否 | 无 | 前端展示、论文解释 | 输出 | 否 | 算法从 `entity_type` 复制 |
| `control_type` | String(50) | 控制结论类型，如 `equity_control`、`agreement_control`、`board_control`、`mixed_control`、`joint_control`、`significant_influence` | 否 | 无 | 控制结果分类 | 输出 | 否 | 读取层会兼容 canonicalize 旧名称 |
| `control_ratio` | Numeric(7,4) | 控制比例或控制得分的百分比表达 | 是 | 无 | 排序、前端展示、结果解释 | 输出 | 否 | unified 写入 `unit_to_pct(total_score)` |
| `control_path` | Text | 控制路径 JSON | 是 | 无 | 前端控制链/图展示、论文路径说明 | 输出 | 否 | 包含 path entity ids、edge ids、path score、edge evidence |
| `is_actual_controller` | Boolean | 是否实际控制人 | 否 | default 0 | 兼容旧字段和实际控制人判断 | 输出 | 否 | v2 中与 ultimate controller 语义对齐 |
| `control_tier` | String(20) | 控制层级：`direct`、`intermediate`、`ultimate`、`candidate` | 是 | index | 区分直接、中间、最终、候选 | 输出 | 否 | 前端和论文都很重要 |
| `is_direct_controller` | Boolean | 是否直接控制人 | 否 | default 0 | 控制摘要、国别直接层判断 | 输出 | 否 | unified 写入 |
| `is_intermediate_controller` | Boolean | 是否中间控制人 | 否 | default 0 | 上卷路径解释 | 输出 | 否 | unified 写入 |
| `is_ultimate_controller` | Boolean | 是否最终实际控制人 | 否 | default 0 | 选取 actual controller | 输出 | 否 | 前端优先使用 |
| `promotion_source_entity_id` | Integer | 从哪个下层主体上卷而来 | 是 | FK -> `shareholder_entities.id`、index | 终局上卷链路解释 | 输出 | 否 | 对 ultimate controller 解释很重要 |
| `promotion_reason` | String(100) | 上卷原因 | 是 | 无 | 解释为何继续穿透 | 输出 | 否 | 如 holding platform、beneficial owner disclosed 等 |
| `control_chain_depth` | Integer | 控制链深度 | 是 | 无 | 路径复杂度说明 | 输出 | 否 | 来自候选最小路径深度 |
| `is_terminal_inference` | Boolean | 是否属于终局推断链条 | 否 | default 0 | 标记 direct/intermediate/ultimate 链条节点 | 输出 | 否 | 前端可用于强调主链 |
| `terminal_failure_reason` | String(100) | 未能形成唯一终局控制人的原因 | 是 | 无 | 失败解释、needs review | 输出 | 否 | 如 joint control、close competition、insufficient evidence |
| `immediate_control_ratio` | Numeric(10,4) | 直接层控制比例 | 是 | 无 | 解释上层即时控制强度 | 输出 | 否 | 前端表格会展示 |
| `aggregated_control_score` | Numeric(10,6) | 聚合控制得分，0-1 | 是 | 无 | 计算与复盘 | 输出 | 否 | 比 `control_ratio` 更适合算法复核 |
| `terminal_control_score` | Numeric(10,6) | 终局控制得分，0-1 | 是 | 无 | 终局链解释 | 输出 | 否 | 可能等于候选总分或上卷终局分 |
| `inference_run_id` | Integer | 关联推断运行 ID | 是 | FK -> `control_inference_runs.id`、index | 追溯本结果来自哪次 refresh | 输出/留痕 | 否 | 部分离线 recompute 脚本可能不写该字段 |
| `basis` | Text | 结果依据 JSON | 是 | 无 | 前端解释、论文证据、路径归一化 | 输出 | 否 | 包含 classification、top_paths、evidence_summary、controller_status 等 |
| `notes` | Text | 备注 | 是 | 无 | 标记自动/手工/重算来源 | 输出/留痕 | 否 | 自动刷新结果通常是 `AUTO:...`；刷新会删除旧 `AUTO:%` 结果 |
| `control_mode` | String(20) | 控制模式：`numeric`、`semantic`、`mixed` | 是 | index | 区分股权数值、语义控制、混合控制 | 输出 | 否 | 当前 unified 核心字段 |
| `semantic_flags` | Text | 语义标签 JSON 列表 | 是 | 无 | 展示语义信号、触发 review | 输出 | 否 | 包含 `needs_review` 时 review_status 常为 needs_review |
| `review_status` | String(30) | 复核状态：`auto`、`manual_confirmed`、`manual_rejected`、`needs_review` | 是 | index | 人工复核工作流 | 输出/人工 | 否 | API 可手工更新 |
| `created_at` | DateTime | 创建时间 | 否 | server default now | 系统维护 | 留痕 | 否 | API 返回 |
| `updated_at` | DateTime | 更新时间 | 否 | server default now、onupdate | 系统维护 | 留痕 | 否 | API 返回 |

当前实际使用情况：

- 当前主流程真实使用，是股权分析最核心结果表。
- `refresh_company_control_analysis()` 会删除同公司旧的 `notes LIKE 'AUTO:%'` 自动结果，再写入新结果。
- 控制链读取接口默认读取该表，不会每次自动重算，除非显式传 `refresh=true` 或调用 refresh endpoint。
- 前端综合页通过 `/companies/{company_id}/analysis/summary` 和 `/companies/{company_id}/control-chain` 消费。
- 当前产业研究不读取该表。

与其他表关系：

- 多对一：`company_id` -> `companies.id`
- 多对一：`controller_entity_id` -> `shareholder_entities.id`
- 多对一：`promotion_source_entity_id` -> `shareholder_entities.id`
- 多对一：`inference_run_id` -> `control_inference_runs.id`

### 6.8 `country_attributions`

表作用：国别归属结果表，保存每家公司最终的实际控制国家、归属类型、归属层级、控制人主体和推断依据。它是控制分析之后的输出，不应被误认为公司原始注册地或上市地。

模块分类：国别归属输出表，股权控制输出的下游结果。  
输入/输出属性：算法输出，也支持人工 override。  
主流程使用：国别归属接口、公司综合页、控制摘要。  
前端消费：当前综合页和控制摘要消费。

字段分级：

- 算法输出核心字段：`company_id`、`incorporation_country`、`listing_country`、`actual_control_country`、`attribution_type`、`actual_controller_entity_id`、`direct_controller_entity_id`、`attribution_layer`、`country_inference_reason`、`look_through_applied`、`basis`、`source_mode`
- 人工修订字段：`is_manual`、`notes`
- 运行追踪字段：`inference_run_id`
- 系统维护字段：`id`、`created_at`、`updated_at`

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 国别归属结果主键 | 否 | PK、index | 结果引用 | 输出 | 否 | 自动生成 |
| `company_id` | Integer | 目标公司 ID | 否 | FK -> `companies.id`、index | 查询公司国别结果 | 输出 | 否 | 读取接口默认取同公司最新一条 |
| `incorporation_country` | String(100) | 公司注册地快照 | 否 | 无 | fallback 依据和结果快照 | 输出 | 否 | 从 `companies` 复制 |
| `listing_country` | String(100) | 公司上市地快照 | 否 | 无 | 结果快照、展示 | 输出 | 否 | 从 `companies` 复制 |
| `actual_control_country` | String(100) | 实际控制国家/地区 | 否 | 无 | 国别归属最终结果 | 输出 | 否 | 可为 `undetermined` |
| `attribution_type` | String(50) | 归属类型，如 `equity_control`、`agreement_control`、`board_control`、`mixed_control`、`joint_control`、`fallback_incorporation` | 否 | 无 | 国别结果分类 | 输出 | 否 | 读取层会兼容旧名称 |
| `actual_controller_entity_id` | Integer | 最终实际控制人主体 ID | 是 | index | 绑定 ultimate controller | 输出 | 否 | 业务上指向 `shareholder_entities.id`，但模型未设 FK |
| `direct_controller_entity_id` | Integer | 直接控制人主体 ID | 是 | index | 区分直接层和终局层 | 输出 | 否 | 业务上指向 `shareholder_entities.id`，但模型未设 FK |
| `attribution_layer` | String(50) | 归属层级：`direct_controller_country`、`ultimate_controller_country`、`fallback_incorporation`、`joint_control_undetermined` | 是 | index | 解释国家来源 | 输出 | 否 | 前端控制摘要会展示 |
| `country_inference_reason` | String(100) | 国家推断原因 | 是 | 无 | 解释是来自直接控制人、终局控制人、fallback、共同控制等 | 输出 | 否 | 论文和协作说明常用 |
| `look_through_applied` | Boolean | 是否发生向上穿透 | 否 | default 0 | 区分 direct vs ultimate 归属 | 输出 | 否 | 当前 unified 写入 |
| `inference_run_id` | Integer | 关联推断运行 ID | 是 | FK -> `control_inference_runs.id`、index | 追溯本结果来自哪次 refresh | 输出/留痕 | 否 | 部分离线 recompute 可能为空 |
| `basis` | Text | 国别归属依据 JSON | 是 | 无 | 前端解释、论文证据、top candidates | 输出 | 否 | 包含 leading_candidate、direct_controller、top_candidates 等 |
| `is_manual` | Boolean | 是否人工记录/人工覆盖 | 否 | default true | 区分自动结果和人工 override | 输出/人工 | 否 | 算法自动写入时为 false |
| `notes` | Text | 备注 | 是 | 无 | 自动/手工/重算来源说明 | 输出/留痕 | 否 | 自动刷新结果通常是 `AUTO:...` |
| `source_mode` | String(30) | 来源模式：`control_chain_analysis`、`fallback_rule`、`manual_override`、`hybrid` | 是 | index | 区分控制链、fallback、人工、混合来源 | 输出 | 否 | `prepare_country_attribution_values` 可推断 |
| `created_at` | DateTime | 创建时间 | 否 | server default now | 系统维护 | 留痕 | 否 | API 返回 |
| `updated_at` | DateTime | 更新时间 | 否 | server default now、onupdate | 系统维护 | 留痕 | 否 | API 返回 |

当前实际使用情况：

- 当前主流程真实使用，是国家归属读取接口的数据源。
- 控制刷新会删除同公司旧的 `AUTO:%` 国别结果并写入新结果。
- 当没有唯一控制人时，可能 fallback 到 `companies.incorporation_country`。
- 共同控制时，`actual_control_country` 可能为 `undetermined`，`attribution_layer` 可能为 `joint_control_undetermined`。
- 当前产业研究不读取该表。

与其他表关系：

- 多对一：`company_id` -> `companies.id`
- 多对一：`inference_run_id` -> `control_inference_runs.id`
- 业务弱关联：`actual_controller_entity_id`、`direct_controller_entity_id` -> `shareholder_entities.id`

### 6.9 `control_inference_runs`

表作用：控制推断运行记录表，记录一次 refresh 的运行参数、阈值、引擎版本、运行状态和结果摘要。它把“结果是怎么来的”提升到可追溯层。

模块分类：股权分析运行留痕表。  
输入/输出属性：系统生成的运行记录，不属于原始输入。  
主流程使用：unified refresh 会创建并最终更新该表。  
前端消费：当前综合页不直接展示运行记录，但结果表通过 `inference_run_id` 可追溯。

字段分级：

- 运行核心字段：`id`、`company_id`、`run_started_at`、`run_finished_at`、`engine_version`、`engine_mode`、`result_status`
- 参数字段：`max_depth`、`disclosure_threshold`、`significant_threshold`、`control_threshold`、`terminal_identification_enabled`、`look_through_policy`
- 摘要字段：`summary_json`、`notes`

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 运行记录主键 | 否 | PK、index | 关联结果和审计日志 | 留痕 | 否 | 自动生成 |
| `company_id` | Integer | 目标公司 ID | 否 | FK -> `companies.id`、index | 运行归属公司 | 留痕 | 否 | refresh 时写入 |
| `run_started_at` | DateTime | 运行开始时间 | 是 | 无 | 运行耗时和审计 | 留痕 | 否 | 当前 `_now_utc()` 写入 |
| `run_finished_at` | DateTime | 运行结束时间 | 是 | 无 | 运行耗时和状态闭环 | 留痕 | 否 | finalize 时写入 |
| `engine_version` | String(50) | 引擎版本 | 是 | 无 | 结果可复现 | 留痕 | 否 | 当前写 `unified_terminal_v2` |
| `engine_mode` | String(50) | 引擎模式 | 是 | index | 区分 unified、legacy 等模式 | 留痕 | 否 | 当前写 `unified_terminal` |
| `max_depth` | Integer | 最大穿透深度 | 是 | 无 | 控制路径搜索参数 | 留痕 | 否 | 默认来自 `DEFAULT_MAX_DEPTH` |
| `disclosure_threshold` | Numeric(10,4) | 披露/候选阈值，0-1 | 是 | 无 | 推断参数 | 留痕 | 否 | 由百分比阈值转换 |
| `significant_threshold` | Numeric(10,4) | 重大影响阈值，0-1 | 是 | 无 | 推断参数 | 留痕 | 否 | 当前默认 0.2 |
| `control_threshold` | Numeric(10,4) | 控制阈值，0-1 | 是 | 无 | 推断参数 | 留痕 | 否 | 当前默认 0.5 |
| `terminal_identification_enabled` | Boolean | 是否启用终局识别 | 否 | default true | 推断参数说明 | 留痕 | 否 | 当前 refresh 写 true |
| `look_through_policy` | String(100) | 穿透策略说明 | 是 | 无 | 解释上卷策略 | 留痕 | 否 | 当前写 `promote_unique_control_parents` |
| `result_status` | String(30) | 运行状态，如 `running`、`success`、`failed` | 是 | index | 状态追踪 | 留痕 | 否 | 当前成功 finalize 为 `success` |
| `summary_json` | Text | 运行结果摘要 JSON | 是 | 无 | 快速复盘、审计 | 留痕 | 否 | 包含候选摘要和 audit_event_count |
| `notes` | Text | 备注 | 是 | 无 | 运行说明 | 留痕 | 否 | 当前写 `AUTO: unified terminal control inference` |

当前实际使用情况：

- 单公司 refresh 和批量 refresh 的 unified 路径会创建该表记录。
- 历史/离线重算脚本 `backend/tasks/recompute_analysis_results.py` 可通过 `notes` 标记 run_id，但不一定创建 `control_inference_runs`。
- 当前前端不直接读取该表，后续可用于“算法运行历史”页面或论文实验复现。

与其他表关系：

- 多对一：`company_id` -> `companies.id`
- 一对多：`control_inference_runs.id` -> `control_relationships.inference_run_id`
- 一对多：`control_inference_runs.id` -> `country_attributions.inference_run_id`
- 一对多：`control_inference_runs.id` -> `control_inference_audit_log.inference_run_id`

### 6.10 `control_inference_audit_log`

表作用：控制推断审计日志表，记录一次运行中的关键动作，例如候选选择、向上穿透、阻断、终局确认、共同控制识别等。它是可解释性和论文复盘的重要过程证据。

模块分类：股权分析审计留痕表。  
输入/输出属性：系统生成的过程日志，不属于原始输入。  
主流程使用：unified refresh 根据 `result.audit_events` 写入。  
前端消费：当前综合页不直接展示。

字段分级：

- 审计核心字段：`id`、`inference_run_id`、`company_id`、`step_no`、`action_type`
- 解释字段：`from_entity_id`、`to_entity_id`、`action_reason`、`score_before`、`score_after`、`details_json`
- 系统维护字段：`created_at`

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 审计记录主键 | 否 | PK、index | 日志引用 | 留痕 | 否 | 自动生成 |
| `inference_run_id` | Integer | 所属推断运行 ID | 否 | FK -> `control_inference_runs.id`、index | 将步骤绑定到一次运行 | 留痕 | 否 | 必填 |
| `company_id` | Integer | 目标公司 ID | 否 | FK -> `companies.id`、index | 日志归属公司 | 留痕 | 否 | 便于按公司查询 |
| `step_no` | Integer | 步骤序号 | 否 | 无 | 保持推断步骤顺序 | 留痕 | 否 | 写入时从 1 开始 |
| `from_entity_id` | Integer | 动作涉及的上游/来源主体 | 是 | index | 上卷、阻断、确认动作解释 | 留痕 | 否 | 模型未设 FK |
| `to_entity_id` | Integer | 动作涉及的下游/目标主体 | 是 | index | 上卷、阻断、确认动作解释 | 留痕 | 否 | 模型未设 FK |
| `action_type` | String(50) | 动作类型 | 否 | index | 分类审计事件 | 留痕 | 否 | 如 `direct_controller_selected`、`promotion_to_parent`、`promotion_blocked`、`terminal_confirmed`、`joint_control_detected` |
| `action_reason` | String(100) | 动作原因 | 是 | 无 | 解释为什么执行该动作 | 留痕 | 否 | 如 `close_competition`、`look_through_not_allowed` |
| `score_before` | Numeric(10,6) | 动作前得分 | 是 | 无 | 得分变化复盘 | 留痕 | 否 | 0-1 |
| `score_after` | Numeric(10,6) | 动作后得分 | 是 | 无 | 得分变化复盘 | 留痕 | 否 | 0-1 |
| `details_json` | Text | 动作细节 JSON | 是 | 无 | 扩展审计信息 | 留痕 | 否 | 存 runner_up、parent score 等 |
| `created_at` | DateTime | 创建时间 | 否 | server default now | 系统维护 | 留痕 | 否 | 当前写入时也显式传 `_now_utc()` |

当前实际使用情况：

- unified 控制刷新在结果写入后追加审计事件。
- 当前默认 v2 库中可能为空，因为现有输出不一定由最新 refresh 生成。
- 适合后续做“算法解释/审计轨迹”页面。

与其他表关系：

- 多对一：`inference_run_id` -> `control_inference_runs.id`
- 多对一：`company_id` -> `companies.id`
- 业务弱关联：`from_entity_id`、`to_entity_id` -> `shareholder_entities.id`

### 6.11 `business_segments`

表作用：产业研究模块的业务分部事实表，记录公司主营业务线、业务类型、收入占比、利润占比、描述、来源、报告期和置信度。

模块分类：产业研究输入表。  
输入/输出属性：产业研究基础事实输入。  
主流程使用：产业分析摘要、业务结构标志、数据完整性、质量检查、报告期历史对比。  
前端消费：当前综合页的 IndustrySummaryCard 和 BusinessSegmentsTable。

字段分级：

- 核心必需字段：`id`、`company_id`、`segment_name`、`segment_type`、`is_current`
- 建议字段：`revenue_ratio`、`profit_ratio`、`description`、`source`、`reporting_period`、`confidence`
- 系统维护字段：`created_at`、`updated_at`

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 业务分部主键 | 否 | PK、index | 分类表和标注日志引用 | 否 | 是 | 自动或导入指定 |
| `company_id` | Integer | 公司 ID | 否 | FK -> `companies.id`、index | 按公司聚合业务线 | 否 | 是 | 产业接口核心查询条件 |
| `segment_name` | String(255) | 业务线/主营分部名称 | 否 | 无 | 展示、去重、历史对比匹配 | 否 | 是 | 空白会被 schema 拒绝 |
| `segment_type` | String(30) | 业务线类型：`primary`、`secondary`、`emerging`、`other` | 否 | 无 | 主营/次要/新兴/其他分组 | 否 | 是 | 产业摘要核心字段 |
| `revenue_ratio` | Numeric(7,4) | 收入占比，0-100 | 是 | 无 | 完整性、展示、业务结构解释 | 否 | 增强 | schema 校验 0-100 |
| `profit_ratio` | Numeric(7,4) | 利润占比，0-100 | 是 | 无 | 展示、业务结构解释 | 否 | 增强 | schema 校验 0-100 |
| `description` | Text | 业务描述 | 是 | 无 | 业务说明、后续分类依据 | 否 | 增强 | 当前聚合不做 NLP |
| `source` | String(255) | 来源说明 | 是 | 无 | 数据追溯 | 否 | 增强 | 可填年报、官网、手工 |
| `reporting_period` | String(20) | 报告期 | 是 | 无 | 报告期筛选、历史对比、默认期选择 | 否 | 是 | 支持年、半年、季度、日期等文本排序 |
| `is_current` | Boolean | 是否当前有效 | 否 | default 1 | 默认过滤非当前业务线 | 否 | 是 | 默认产业分析只取当前或有效候选 |
| `confidence` | Numeric(5,4) | 业务事实置信度，0-1 | 是 | 无 | 展示和质量提示扩展 | 否 | 增强 | schema 校验 0-1 |
| `created_at` | DateTime | 创建时间 | 否 | server default now | 系统维护 | 否 | 留痕 | API 返回 |
| `updated_at` | DateTime | 更新时间 | 否 | server default now、onupdate | 系统维护 | 否 | 留痕 | API 返回 |

当前实际使用情况：

- 当前产业研究主流程真实使用，是产业模块的事实输入表。
- `/companies/{company_id}/industry-analysis` 会按公司读取所有业务线，并根据报告期和 `is_current` 选择有效快照。
- `get_company_industry_analysis_quality()` 会检查是否有 primary segment、是否缺分类、是否重名。
- 创建、更新、删除该表记录时会写 `annotation_logs`。
- 控制链算法不读取该表。

与其他表关系：

- 多对一：`business_segments.company_id` -> `companies.id`
- 一对多：`business_segments.id` -> `business_segment_classifications.business_segment_id`
- 弱关联：`annotation_logs.target_type = 'business_segment'` 且 `target_id = business_segments.id`

### 6.12 `business_segment_classifications`

表作用：业务分部行业分类表，记录业务线到标准行业分类体系的映射。当前默认体系为 GICS，支持四级分类、主分类标记、映射依据和复核状态。

模块分类：产业研究结果表和人工修订对象。  
输入/输出属性：可以是算法/人工分类结果，也可以导入为产业研究基础数据。  
主流程使用：产业标签聚合、主营行业识别、手工调整判断、质量检查、历史对比。  
前端消费：业务线表、产业摘要中的行业标签。

字段分级：

- 核心必需字段：`id`、`business_segment_id`、`standard_system`、`is_primary`
- 建议字段：`level_1`、`level_2`、`level_3`、`level_4`、`mapping_basis`、`review_status`
- 系统维护字段：`created_at`、`updated_at`

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 分类记录主键 | 否 | PK、index | API、前端 key、标注日志引用 | 否 | 是 | 自动或导入指定 |
| `business_segment_id` | Integer | 对应业务线 ID | 否 | FK -> `business_segments.id`、index | 将分类绑定到业务线 | 否 | 是 | 必填 |
| `standard_system` | String(50) | 分类体系名称 | 否 | default `GICS` | 区分分类体系 | 否 | 是 | Schema 会转大写，默认 GICS |
| `level_1` | String(255) | 一级行业分类 | 是 | 无 | 构造行业标签 | 否 | 是 | 可为空，但无层级会没有 label |
| `level_2` | String(255) | 二级行业分类 | 是 | 无 | 构造行业标签 | 否 | 增强 | 与 level_1 拼接 |
| `level_3` | String(255) | 三级行业分类 | 是 | 无 | 构造行业标签 | 否 | 增强 | 与前级拼接 |
| `level_4` | String(255) | 四级行业分类 | 是 | 无 | 构造行业标签 | 否 | 增强 | 与前级拼接 |
| `is_primary` | Boolean | 是否该业务线主分类 | 否 | default 0 | 主营行业识别 | 否 | 是 | 多个 primary 会触发质量警告 |
| `mapping_basis` | Text | 分类依据 | 是 | 无 | 人工说明、论文和复核 | 否 | 增强 | 可记录依据文本 |
| `review_status` | String(30) | 复核状态：`auto`、`manual_confirmed`、`manual_adjusted` | 是 | index | 判断是否存在人工调整 | 否 | 是 | `manual_confirmed`/`manual_adjusted` 会触发 has_manual_adjustment |
| `created_at` | DateTime | 创建时间 | 否 | server default now | 系统维护 | 否 | 留痕 | API 返回 |
| `updated_at` | DateTime | 更新时间 | 否 | server default now、onupdate | 系统维护 | 否 | 留痕 | API 返回 |

当前实际使用情况：

- 当前产业研究主流程真实使用。
- `build_industry_label_from_levels()` 用 `level_1` 到 `level_4` 拼接行业标签。
- `is_primary` 优先决定主营行业；如果没有 primary 分类，则 primary segment 的分类作为 fallback。
- 创建、更新、删除该表记录时会写 `annotation_logs`。
- 控制链算法不读取该表。

与其他表关系：

- 多对一：`business_segment_classifications.business_segment_id` -> `business_segments.id`
- 弱关联：`annotation_logs.target_type = 'business_segment_classification'` 且 `target_id = business_segment_classifications.id`

### 6.13 `annotation_logs`

表作用：通用人工标注和修订日志表。当前代码主要用于产业研究模块，记录业务分部和业务分部分类的创建、更新、删除、人工确认和人工覆盖。

模块分类：人工标注/修订/留痕表。  
输入/输出属性：过程留痕，不属于控制链或产业事实输入。  
主流程使用：产业 CRUD 自动写入，产业 annotation log API 读取。  
前端消费：当前综合页不直接展示日志，但 API 已支持查看单条业务线或分类的日志。

字段分级：

- 核心必需字段：`id`、`target_type`、`target_id`、`action_type`
- 建议字段：`old_value`、`new_value`、`reason`、`operator`
- 系统维护字段：`created_at`

字段明细：

| 字段名 | 类型 | 含义 | 允许为空 | 主键/外键/索引/唯一 | 当前主要用途 | 股权核心 | 产业核心 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `id` | Integer | 标注日志主键 | 否 | PK、index | 日志引用 | 否 | 留痕 | 自动或导入指定 |
| `target_type` | String(50) | 目标对象类型 | 否 | index、复合 index `ix_annotation_logs_target_lookup` | 区分业务线和分类 | 否 | 留痕 | 当前允许 `business_segment`、`business_segment_classification` |
| `target_id` | Integer | 目标对象 ID | 否 | index、复合 index | 定位被修改记录 | 否 | 留痕 | 弱关联，无数据库 FK |
| `action_type` | String(50) | 动作类型，如 `create`、`update`、`delete`、`confirm`、`manual_override` | 否 | index | 记录操作类型 | 否 | 留痕 | 分类更新会根据 review_status 映射 confirm/manual_override/update |
| `old_value` | Text | 操作前快照，通常 JSON | 是 | 无 | 回溯变更前内容 | 否 | 留痕 | `deserialize_model_snapshot()` 会尝试 JSON 解析 |
| `new_value` | Text | 操作后快照，通常 JSON | 是 | 无 | 回溯变更后内容 | 否 | 留痕 | 删除时为空 |
| `reason` | Text | 修改原因 | 是 | 无 | 人工说明 | 否 | 留痕 | API query 参数传入 |
| `operator` | String(100) | 操作者 | 是 | 无 | 审计追责 | 否 | 留痕 | API 默认 `api` |
| `created_at` | DateTime | 创建时间 | 否 | server default now | 系统维护 | 否 | 留痕 | 无 `updated_at` |

当前实际使用情况：

- `business_segments` 创建、更新、删除会写日志。
- `business_segment_classifications` 创建、更新、删除会写日志。
- 当前没有控制关系人工修订自动写入该表，控制关系复核主要落在 `control_relationships.review_status`。
- 设计上是通用日志，但当前实际边界主要在产业模块。

与其他表关系：

- 弱关联：`target_type='business_segment'`，`target_id` -> `business_segments.id`
- 弱关联：`target_type='business_segment_classification'`，`target_id` -> `business_segment_classifications.id`

## 7. 当前核心股权分析主链路

当前默认控制分析主链路是 unified control inference。只有显式设置 `CONTROL_INFERENCE_ENGINE=legacy` 时才走旧版纯股权穿透；默认不会隐式回退 legacy。

主链路如下：

1. API 以 `company_id` 为入口，例如 `/companies/{company_id}/analysis/refresh`、`/companies/{company_id}/control-chain?refresh=true`。
2. 后端读取 `companies`，确认公司存在。
3. 后端通过 `shareholder_entities.company_id = companies.id` 找到目标公司在控制图中的目标实体。没有该映射时，刷新会失败。
4. `build_control_context()` 读取所有主体和当前有效关系边：
   - `shareholder_structures.is_current = 1`
   - `shareholder_structures.is_direct = 1`
   - `effective_date` 为空或不晚于分析日
   - `expiry_date` 为空或不早于分析日
5. 对每条边执行 `edge_to_factor()`：
   - 股权边使用 `effective_control_ratio` 或 `holding_ratio` 形成数值因子。
   - 语义边使用 `control_basis`、`agreement_scope`、`nomination_rights`、`board_seats`、`relation_metadata`、`remarks` 等形成语义因子。
   - `confidence_level`、证据文本丰富度、`relationship_sources` 来源信息共同形成 reliability。
   - `look_through_allowed` 和 `termination_signal` 决定是否阻断继续上卷。
6. `infer_controllers()` 从目标实体向上搜索控制路径，聚合同一候选主体的多条路径，识别 direct controller、leading candidate、actual/ultimate controller、joint control 或 fallback。
7. 刷新逻辑创建 `control_inference_runs`，并在结果成功后写入：
   - `control_relationships`：候选控制人、直接控制人、中间控制人、最终控制人、路径和得分。
   - `country_attributions`：实际控制国家、归属类型、归属层级。
   - `control_inference_audit_log`：上卷、阻断、终局确认、共同控制等步骤。
8. 读取接口默认读取持久化结果表，不会每次自动重算。需要重算必须显式 refresh。

最小可运行股权输入集：

- `companies`：至少有 `id`、`name`、`stock_code`、`incorporation_country`、`listing_country`、`headquarters`
- `shareholder_entities`：目标公司映射实体和所有上游主体，至少有 `id`、`entity_name`、`entity_type`，目标实体必须有 `company_id`
- `shareholder_structures`：至少有 `id`、`from_entity_id`、`to_entity_id`、`relation_type='equity'`、`holding_ratio`、`is_direct=1`、`is_current=1`

增强输入最值得补：

- 终局主体：`entity_subtype`、`controller_class`、`ultimate_owner_hint`、`beneficial_owner_disclosed`
- 上卷策略：`look_through_allowed`、`termination_signal`
- 语义控制：`relation_type`、`control_basis`、`agreement_scope`、`board_seats`、`nomination_rights`、`relation_metadata`
- 证据质量：`confidence_level`、`relationship_sources.excerpt`、`relationship_sources.source_url`、`relationship_sources.confidence_level`

## 8. 当前核心产业研究主链路

产业研究模块不依赖控制链必要输入，也不读取 `shareholder_structures`。它以 `companies` 为入口，以业务线和业务线分类为核心。

主链路如下：

1. API 以 `company_id` 为入口，例如 `/companies/{company_id}/industry-analysis`、`/companies/{company_id}/analysis/summary`。
2. 后端读取 `business_segments`，按公司聚合所有业务线。
3. 若请求指定 `reporting_period`，则选取该报告期业务线；否则优先选择当前有效业务线所在的最新报告期。
4. 后端加载每条业务线的 `business_segment_classifications`。
5. 产业分析输出：
   - 按 `segment_type` 分成 primary、secondary、emerging、other。
   - 由 `level_1` 到 `level_4` 拼接 industry label。
   - 由 `is_primary` 分类优先判断主营行业；如果没有，则用 primary segment 的分类作为 fallback。
   - 根据 `review_status` 判断是否存在人工调整。
   - 根据 `is_current`、`reporting_period` 生成历史对比和默认快照。
6. 创建、更新、删除业务线和分类时，系统写 `annotation_logs`，保存 old/new snapshot、原因和操作者。

最小可运行产业输入集：

- `companies`：公司主数据
- `business_segments`：每家公司至少一条 `segment_type='primary'` 的当前有效业务线
- `business_segment_classifications`：建议每条 primary 业务线至少一条分类，且最好有 `level_1`

产业研究中“原始事实”和“分类结果”的边界：

- 原始事实：`business_segments.segment_name`、`segment_type`、`revenue_ratio`、`profit_ratio`、`description`、`source`、`reporting_period`
- 分类结果：`business_segment_classifications.standard_system`、`level_1` 到 `level_4`、`is_primary`、`mapping_basis`、`review_status`
- 人工留痕：`annotation_logs`

## 9. 最容易混淆的点

### 9.1 原始输入 vs 算法输出

原始输入主要是：

- `companies`
- `shareholder_entities`
- `shareholder_structures`
- `relationship_sources`
- `entity_aliases`
- `business_segments`

算法或系统输出主要是：

- `control_relationships`
- `country_attributions`
- `control_inference_runs`
- `control_inference_audit_log`
- `shareholder_structure_history`
- `annotation_logs`

不要把 `control_relationships` 和 `country_attributions` 批量当作原始事实提供给数据抓取或测试数据生成，否则会混淆“输入事实”和“算法结论”。

### 9.2 股权分析 vs 产业研究

股权分析主链路依赖控制图：

- `shareholder_entities`
- `shareholder_structures`
- `relationship_sources`

产业研究主链路依赖业务结构：

- `business_segments`
- `business_segment_classifications`
- `annotation_logs`

`business_segments` 系列表不属于控制链必要输入，缺失不会阻止 ultimate controller 推断；`shareholder_structures` 缺失会阻止控制图分析，但不会影响产业业务线聚合。

### 9.3 公司主表 vs 主体表

`companies` 是公司主数据表，代表“要分析的公司记录”。  
`shareholder_entities` 是控制图节点表，代表“图中的主体节点”。

每家待分析公司必须在 `shareholder_entities` 中有一条映射实体，依靠 `shareholder_entities.company_id = companies.id` 进入控制图。上游股东如果也是公司，也可以映射到 `companies`，但不是必须。

### 9.4 控制关系结果 vs 原始关系边

`shareholder_structures` 是原始关系边，例如 A 持有 B 60%、C 有权任命 D 董事会多数席位。  
`control_relationships` 是算法输出，例如 A 是直接控制人、C 是 ultimate controller、某主体只是 leading candidate。

原始边可以有很多条，控制结果是算法聚合路径后对候选主体做出的结论。

### 9.5 国家归属结果 vs 注册地/上市地

`companies.incorporation_country` 是公司注册地。  
`companies.listing_country` 是上市地。  
`country_attributions.actual_control_country` 是算法或人工归属后的实际控制国家。

实际控制国家可能来自 ultimate controller 的 `shareholder_entities.country`，也可能来自映射公司的注册地，或者 fallback 到目标公司的注册地。它不等同于原始注册地。

### 9.6 `relationship_sources` 的当前作用

旧文档可能说 `relationship_sources` 当前不参与核心打分。当前代码已改变：unified 控制推断会读取该表，来源存在、摘录存在、来源名称/URL 存在、高低来源置信度都会影响边的 reliability。

### 9.7 `annotation_logs` 的当前边界

`annotation_logs` 设计是通用人工留痕表，但当前实际代码只围绕产业研究的 `business_segments` 和 `business_segment_classifications` 自动写入。控制结果人工复核状态主要落在 `control_relationships.review_status`，不会自动写 `annotation_logs`。

## 10. 给协作者的最小阅读建议

前端同学重点看：

- `companies`
- `control_relationships`
- `country_attributions`
- `business_segments`
- `business_segment_classifications`
- 关系图字段：`shareholder_entities`、`shareholder_structures`

数据抓取同学重点看：

- `companies`
- `shareholder_entities`
- `shareholder_structures`
- `relationship_sources`
- `entity_aliases`
- 产业补数时再看 `business_segments`、`business_segment_classifications`

股权算法同学重点看：

- `shareholder_entities`
- `shareholder_structures`
- `relationship_sources`
- `control_relationships`
- `country_attributions`
- `control_inference_runs`
- `control_inference_audit_log`

产业研究同学重点看：

- `companies`
- `business_segments`
- `business_segment_classifications`
- `annotation_logs`

论文写作时最常引用：

- 输入建模：`companies`、`shareholder_entities`、`shareholder_structures`
- 复杂控制证据：`relation_type`、`control_basis`、`agreement_scope`、`board_seats`、`nomination_rights`、`relation_metadata`、`relationship_sources`
- 控制识别输出：`control_relationships.control_tier`、`is_ultimate_controller`、`control_path`、`aggregated_control_score`、`semantic_flags`
- 国别归属输出：`country_attributions.actual_control_country`、`attribution_type`、`attribution_layer`、`look_through_applied`
- 可解释性和复现：`control_inference_runs`、`control_inference_audit_log`
- 产业研究：`business_segments.segment_type`、`revenue_ratio`、`reporting_period`、`business_segment_classifications.level_1` 到 `level_4`、`is_primary`、`review_status`

## 11. 待清理 / 待统一

1. `country_attributions.actual_controller_entity_id` 和 `direct_controller_entity_id` 业务上指向 `shareholder_entities.id`，但模型没有设置数据库外键。后续若要加强一致性，可补外键或在文档/API 中明确弱关联。
2. `shareholder_structure_history` 当前 create/update 会自动写历史，但 delete 不会先写 delete 历史，且关系边删除会 cascade 删除历史记录。如果需要完整审计，应改为软删除或先写独立审计。
3. `look_through_priority` 字段存在并会被归一化，但当前 unified 推断主逻辑影响弱，属于预留扩展字段。
4. `control_type` 和 `relation_type` 存在历史兼容关系。当前应优先填写 `relation_type`，`control_type` 主要兼容旧数据。
5. `has_numeric_ratio` 当前会由准备函数根据 `relation_type` 和 `holding_ratio` 推断，人工填入值可能被覆盖。对接时不应把它当作权威输入。
6. `control_relationships.is_actual_controller` 与 v2 的 `is_ultimate_controller` 有语义重叠。当前读取层兼容两者，后续文档和前端应逐步以 `control_tier` 和 `is_ultimate_controller` 为主。
7. 离线 `backend/tasks/recompute_analysis_results.py` 与在线 refresh 写运行留痕的方式不完全一致。在线 refresh 会写 `control_inference_runs` 和 audit log，部分离线重算更依赖 `notes` 中的 run_id。
8. 当前默认 v2 数据库表结构完整但数据很少，满量样本主要在 `company_test_analysis_industry.db`。协作时应明确使用哪个数据库文件，避免把“默认库为空”误解为“模块未实现”。
9. 旧文档关于 `relationship_sources` 不参与打分的描述已过时。当前 unified 引擎会把来源信息纳入 reliability。
10. 前端文件中存在一些历史/legacy 命名，如 `legacyControlChainAdapter.js`，但当前后端默认是 unified 控制推断，不应把 legacy 视作主流程。

## 12. 维护建议

后续如果修改模型或新增表，建议同步更新本文档的四处内容：

1. 总览分层和表级归属。
2. 对应表的字段明细、字段分级、实际使用情况。
3. 股权分析或产业研究主链路。
4. 待清理/待统一小节。

新增字段时尤其要标明：

- 是原始事实、算法输出、人工修订还是过程留痕。
- 是否当前主流程真实读取。
- 是否暴露给 API 或前端。
- 是否参与股权分析、产业研究，还是两者都不直接使用。
