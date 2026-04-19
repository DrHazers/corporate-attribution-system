# 前端展示层与主版本后端输出语义差距审计

日期：2026-04-18

## 1. 审计目标与结论

当前后端已经进入主版本冻结口径：统一控制推断负责区分 direct controller、ultimate / actual controller、leading candidate、promotion / look-through、共同控制与各类保守阻断。前端下一阶段不应继续把控制分析结果理解成“一个实际控制人 + 一个国家 + 一张简单链路图”，而应把它作为一个研究解释型结论来展示。

本次审计结论如下：

1. `/companies/{company_id}/analysis/summary` 已经是首屏最合适的主入口，后端已提供 direct / actual / leading、归属层级、失败原因、promotion reason、control mode、score 等字段。
2. 当前前端主页面已经消费 summary、control relationships、country attribution 和 relationship graph，但首屏摘要仍以 `display_controller` 为中心，容易把 actual controller 与 leading candidate 混在一个“控制主体”槽位里。
3. 控制结构图已经有一版重建组件，能表达 actual / leading 的顶部主轴，但 adapter 仍主要围绕 `actualController` / `focused` 两类角色，尚未系统表达 direct、ultimate、joint participant、nominee、trust、SPV、holding company 等后端语义。
4. 控制关系表已展示 controller、control_type、control_ratio、control_path、is_actual_controller、basis，但尚未把 `control_tier`、`is_direct_controller`、`is_ultimate_controller`、`control_mode`、`aggregated_control_score`、`terminal_control_score`、`promotion_reason`、`terminal_failure_reason` 作为一等字段展示。
5. 后端字段命名整体可用，但前端文案和若干 fallback 逻辑仍带有旧版 actual-controller-only 思维，需要先改摘要卡，再逐步增强图和表。

## 2. 当前前端分析展示入口

### 2.1 页面与 API 消费点

主页面：

- `frontend/src/views/CompanyAnalysisView.vue`
  - 首屏调用 `fetchCompanyAnalysisSummary(companyId)`。
  - 若 `summary.control_analysis.control_relationships` 不存在，再 fallback 调 `fetchCompanyControlChain(companyId)`。
  - 若 `summary.industry_analysis.segments` 不存在，再 fallback 调 `fetchCompanyIndustryAnalysis(companyId)`。
  - 单独调用 `fetchCompanyRelationshipGraph(companyId)` 给控制结构图。

API 封装：

- `frontend/src/api/analysis.js`
  - `GET /companies/{company_id}/analysis/summary`
  - `GET /companies/{company_id}/industry-analysis`
  - `GET /companies/{company_id}/control-chain`
- `frontend/src/api/company.js`
  - `GET /companies/{company_id}`
  - `GET /companies/{company_id}/relationship-graph`

结论：调用顺序与 `docs/frontend_api_handoff.md` 大体一致，首屏主入口正确；差距主要在展示层和 adapter 层。

### 2.2 展示组件

公司总览：

- `frontend/src/components/CompanyOverviewCard.vue`
  - 当前展示 `display_controller || actual_controller`。
  - 若 `display_controller_role === leading_candidate`，文案显示“重点控制候选”。
  - 仍只有一个“控制主体”字段，没有 direct / ultimate / leading 分列。

分析摘要与图容器：

- `frontend/src/components/ControlSummaryCard.vue`
  - 当前摘要卡展示 display controller、控制主体类型、控制类型、控制比例、控制关系数量、实际控制地、归属类型、识别状态。
  - 仍缺少 `direct_controller`、`actual_controller`、`leading_candidate` 同屏区分。
  - 尚未展示 `attribution_layer`、`look_through_applied`、`promotion_reason`、`terminal_failure_reason`、fallback 说明。

控制结构图：

- `frontend/src/components/ControlStructureDiagram.vue`
  - 当前能在顶部主轴切换“实际控制人”或“重点控制候选”。
  - 文案中仍有一些 legacy 静态句式，虽被隐藏或补充文案覆盖，但维护上容易混淆。
  - 节点角色仍主要是 target / actualSummary / direct / focused / intermediate / support。

控制结构图 adapter：

- `frontend/src/utils/controlStructureAdapter.js`
  - 当前会用 `actual_controller || focusedRelationship` 生成 summary controller。
  - `directUpstreamIds` 来自 relationship graph 中指向 target 的边，而不是优先来自 `control_analysis.direct_controller`。
  - 尚未显式把 `control_tier`、`is_direct_controller`、`is_ultimate_controller`、`promotion_reason`、`terminal_failure_reason` 带入节点角色与 tooltip。

ECharts 关系图：

- `frontend/src/components/RelationshipGraphCard.vue`
- `frontend/src/utils/graphAdapter.js`
  - 已支持 target、focused、actualController 角色和 edge type 颜色。
  - 未在主页面使用；当前 `ControlSummaryCard` 使用的是 `ControlStructureDiagram`。
  - 角色表缺少 direct controller、ultimate controller、leading candidate、joint participant、nominee、trust / SPV / holding company。

控制关系表：

- `frontend/src/components/ControlRelationsTable.vue`
  - 已展示 controller、entity type、control_type、control_ratio、control_path、is_actual_controller、basis。
  - 已能标记 `is_leading_candidate` 和 joint-control-like status。
  - 排序仍按 actual controller 优先，再按 control_ratio；未按 direct / ultimate / candidate 层级排序。
  - 未展示主版本后端新增字段。

历史/备用图：

- `frontend/src/components/LegacyControlChainDiagram.vue`
- `frontend/src/utils/legacyControlChainAdapter.js`
- `frontend/src/utils/legacyControlChainLayout.js`
  - 文件名和实现均是 adaptive / legacy 图方案。
  - 当前未在主页面直接使用，但若未来启用，需要同步升级字段语义。

## 3. 当前后端实际可提供字段

### 3.1 首屏 summary payload

主入口：`GET /companies/{company_id}/analysis/summary`

实现来源：

- `backend/api/industry_analysis.py`
- `backend/analysis/industry_analysis.py::get_company_analysis_summary`
- `backend/schemas/industry_analysis.py::CompanyAnalysisSummaryRead`

顶层结构：

- `company`
- `control_analysis`
- `country_attribution`
- `industry_analysis`

`control_analysis` 当前可用字段：

- `company_id`
- `controller_count`
- `direct_controller`
- `actual_controller`
- `leading_candidate`
- `focused_candidate`
- `display_controller`
- `display_controller_role`
- `identification_status`
- `controller_status`
- `control_relationships`

`control_relationships[]` / controller summary 当前可用字段：

- `id`
- `company_id`
- `controller_entity_id`
- `controller_name`
- `controller_type`
- `control_type`
- `control_ratio`
- `control_path`
- `is_actual_controller`
- `whether_actual_controller`
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
- `controller_status`
- `selection_reason`
- `is_leading_candidate`
- `review_status`
- `created_at`
- `updated_at`

`country_attribution` 当前可用字段：

- `company_id`
- `actual_control_country`
- `attribution_type`
- `actual_controller_entity_id`
- `direct_controller_entity_id`
- `attribution_layer`
- `country_inference_reason`
- `look_through_applied`
- `basis`
- `source_mode`
- `message`

### 3.2 关系图 payload

入口：`GET /companies/{company_id}/relationship-graph`

实现来源：

- `backend/api/company.py`
- `backend/schemas/company.py::CompanyRelationshipGraphRead`

节点字段：

- `id`
- `entity_id`
- `entity_name`
- `name`
- `entity_type`
- `country`
- `company_id`
- `identifier_code`
- `is_listed`
- `notes`
- `is_root`

边字段：

- `id`
- `structure_id`
- `from_entity_id`
- `from_entity_name`
- `to_entity_id`
- `to_entity_name`
- `holding_ratio`
- `is_direct`
- `control_type`
- `relation_type`
- `has_numeric_ratio`
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

注意：关系图节点当前没有直接暴露 `entity_subtype`、`controller_class`、`beneficial_owner_disclosed`，因此 trust / SPV / holding company 角色只能从名称、notes 或控制分析结果间接推断。若要图层准确表达这些角色，后续需要后端补字段或图 adapter 保守降级。

### 3.3 语义变化与旧字段风险

以下字段不能再按旧逻辑展示：

- `actual_control_country`：不一定表示已经识别出 actual controller；当 `attribution_type = fallback_incorporation` 时，它是注册地兜底。
- `display_controller`：只是 UI 友好的展示主体，可能是 actual controller，也可能是 leading candidate；不能直接命名为“实际控制人”。
- `control_type`：现在包括 `equity_control`、`agreement_control`、`board_control`、`mixed_control`、`joint_control`、`significant_influence`，不是旧版 direct / indirect 层级。
- `control_ratio`：更接近候选人的综合控制分或控制比例展示值，不应被简单理解为直接持股比例。
- `control_relationships`：是算法输出的候选控制关系结果，不是底层事实输入表；不能拿它反推完整原始股权网络。
- `is_actual_controller` 与 `is_ultimate_controller`：当前基本同向，但语义上应保留 ultimate / actual 口径，不能用 “actual-only” 展示替代 direct / ultimate 层级。

## 4. 字段契合差距清单

### 4.1 前端已消费且语义基本正确

| 字段 | 前端位置 | 判断 |
| --- | --- | --- |
| `company.name/id/stock_code/incorporation_country/listing_country` | `CompanyOverviewCard`、`CompanyAnalysisView` | 基础展示正确。 |
| `country_attribution.actual_control_country` | `CompanyOverviewCard`、`ControlSummaryCard` | 值读取正确，但 fallback 语义解释不足。 |
| `country_attribution.attribution_type` | `ControlSummaryCard`、图 adapter | 读取正确，label 覆盖部分值。 |
| `control_analysis.controller_count` | `ControlSummaryCard` | 基本正确。 |
| `control_relationships[].controller_name/controller_type/control_type/control_ratio/control_path/basis` | `ControlRelationsTable` | 基础展示可用。 |
| `control_relationships[].is_actual_controller` | `ControlRelationsTable`、adapter | 可识别 actual 行，但需要补充 direct / ultimate。 |
| `control_relationships[].is_leading_candidate` | `ControlRelationsTable` | 可显示 leading candidate badge。 |
| `relationship_graph.nodes/edges` | `ControlStructureDiagram` adapter | 可渲染结构，但角色语义不足。 |

### 4.2 前端已消费但语义过时或展示不完整

| 字段/逻辑 | 问题 | 风险 |
| --- | --- | --- |
| `display_controller` | 多处把它作为首要控制主体展示。 | leading candidate 可能被弱化为“控制主体”，用户误认为已识别 actual controller。 |
| `display_controller_role` | 只在文案上切换 actual / leading。 | 没有同时展示 direct / actual / leading 的差异。 |
| `actual_control_country` | 只显示“实际控制地”。 | fallback 时会误导为“从 actual controller 推导出的国家”。 |
| `control_type` | 前端标签把它当“控制类型”展示。 | 未区分 control mode、attribution type、control tier，用户看不到 direct / ultimate / promotion 层次。 |
| `basis` | 表格只解析 classification、control_mode、aggregator、path_count、as_of。 | `evidence_summary`、`selection_reason`、`terminal_failure_reason`、`promotion_path_entity_ids` 等解释信息没有释放。 |
| `identification_status/controller_status` | 摘要只显示状态标签。 | joint / leading / no signal 的原因没有和 failure reason 结合。 |
| 图 adapter 的 `focused` | actual 不存在时取第一条 relationship。 | 若排序或 fallback 改变，可能把普通候选误当主轴主体。 |

### 4.3 后端已提供但前端尚未消费

高优先字段：

- `control_analysis.direct_controller`
- `control_analysis.actual_controller`
- `control_analysis.leading_candidate`
- `country_attribution.actual_controller_entity_id`
- `country_attribution.direct_controller_entity_id`
- `country_attribution.attribution_layer`
- `country_attribution.country_inference_reason`
- `country_attribution.look_through_applied`
- `country_attribution.source_mode`
- `country_attribution.basis.terminal_failure_reason`
- `country_attribution.basis.joint_controller_entity_ids`
- `country_attribution.basis.leading_candidate_entity_id`
- `country_attribution.basis.leading_candidate_classification`
- `country_attribution.basis.promotion_reason_by_entity_id`

控制关系明细字段：

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
- `control_mode`
- `semantic_flags`
- `selection_reason`
- `review_status`

图角色字段缺口：

- 后端关系图 payload 未直接提供 `entity_subtype`、`controller_class`、`beneficial_owner_disclosed`。
- 前端若要准确标注 nominee / trust vehicle / SPV / holding company，建议后端在 `RelationshipGraphNodeRead` 增补这些字段，或者前端仅在 summary/control_relationships 明确出现时标注。

## 5. 组件过时清单

### 5.1 仍偏 actual-controller-only 的组件

- `ControlSummaryCard.vue`
  - 当前最明显。它以 `display_controller || actual_controller` 为中心，只有一个 controller name。
  - 需要改成 direct / ultimate actual / leading candidate 三段式摘要。

- `CompanyOverviewCard.vue`
  - 总览只有一个“控制主体”字段。
  - 建议短期保留兼容，但字段名改成“主要展示主体”或新增“识别状态/归属层级”避免误导。

- `LegacyControlChainDiagram.vue`
  - 文件名和 legend 仍是 actual controller 优先。
  - 当前未主用，后置处理。

### 5.2 只适合旧 control_relationships 单层表视角的组件

- `ControlRelationsTable.vue`
  - 当前表结构更像候选结果列表，不像 direct / intermediate / ultimate / candidate 分层解释表。
  - 缺少 control tier、score、terminal reason、promotion reason，无法解释“为什么没有 actual controller”。

### 5.3 可能导致 direct / ultimate / leading 混淆的 adapter

- `controlStructureAdapter.js`
  - `summaryControllerId = actualControllerId || focusedControllerId || keyPath.nodeIds[0]`。
  - 当 actual 为空时，focused 可能来自 leading，也可能来自 relationships[0]；需要显式优先 `leading_candidate`。
  - direct controller 当前更多来自 graph incoming edge，不是 `control_analysis.direct_controller`。

- `graphAdapter.js`
  - `pickFocusedRelationship()` 在没有 actual 时直接取第一条 relationship。
  - legend 只有 target / focused / actual controller。
  - 需要显式区分 direct、ultimate、leading、joint participant。

### 5.4 会误导用户的字段命名或文案

- “实际控制地”：fallback 场景应显示“归属国家/地区”或附带 fallback 说明。
- “控制主体”：在 leading candidate only 场景不够准确。
- “实际控制人”：不能从 `display_controller` 推导，只能来自 `actual_controller` 或 `is_actual_controller/is_ultimate_controller`。
- “控制比例”：对 mixed / semantic 控制应说明是综合控制分或推断分，不是总是持股比例。
- 图中“实际控制人位于顶部主轴”的静态文案应继续弱化或替换为按状态生成的文案。

## 6. 前端改造优先级路线图

### P1：分析摘要卡片

目标：首屏先准确表达主版本控制结论。

建议改造：

- 分列展示 `Direct Controller`、`Ultimate / Actual Controller`、`Leading Candidate`。
- 展示 `Actual Control Country`，并配合 `attribution_layer` 与 `attribution_type` 解释来源。
- 展示 `Control Mode / Control Type`，优先从 actual controller，其次 direct controller，其次 leading candidate 取值。
- 展示 `promotion_reason`、`terminal_failure_reason`、`look_through_applied`。
- 当 `attribution_type = fallback_incorporation` 且无 actual controller 时，明确显示：未识别出唯一实际控制人，当前按公司注册地兜底。
- 当 `controller_status = joint_control_identified` 或 `terminal_failure_reason = joint_control` 时，明确显示共同控制阻断。

优先原因：

- 摘要卡是用户首屏理解结论的入口。
- 改动范围小，不需要重画图。
- 可以立即避免 leading candidate 被误读成 actual controller。

### P2：链路图增强

目标：图不只是画路径，而是表达判定层次。

建议改造：

- 节点角色新增 direct controller、ultimate / actual controller、leading candidate、joint participant。
- 根据 `control_tier`、`is_direct_controller`、`is_ultimate_controller`、`is_leading_candidate` 设置节点样式。
- 根据 `promotion_reason` 与 `look_through_applied` 高亮 promotion / rollup 路径。
- 边类型继续区分 `equity`、`agreement`、`board_control`、`voting_right`、`vie`、`nominee`。
- 对失败状态添加图上说明：joint / nominee / beneficial owner unknown / weak evidence / fallback。
- 若要准确标注 trust / SPV / holding company，建议后端补充 `entity_subtype` 到 relationship graph node。

优先原因：

- 图是解释控制链最直观的部分，但改动复杂度明显高于摘要卡。
- 需要 adapter 与布局协同，适合在 P1 稳定后做。

### P3：控制关系表升级

目标：把候选控制关系表升级成“控制判定明细表”。

建议新增列或折叠详情：

- `control_tier`
- `is_direct_controller`
- `is_ultimate_controller`
- `control_mode`
- `control_type`
- `aggregated_control_score`
- `terminal_control_score`
- `promotion_reason`
- `terminal_failure_reason`
- `semantic_flags`
- `selection_reason`

排序建议：

1. actual / ultimate
2. direct
3. leading candidate
4. intermediate
5. candidate
6. supporting rows by score

优先原因：

- 表是复核入口，适合承接摘要卡未完全展示的解释细节。
- 字段多，需控制可读性，避免首屏过载。

### P4：运行与审计信息

目标：给研究和调试人员追溯推断过程。

可后置展示：

- `inference_run_id`
- `control_inference_runs`
- `control_inference_audit_log`
- evidence breakdown
- reliability breakdown

优先原因：

- 当前首屏缺口不在审计日志。
- 该部分适合做折叠面板或调试 tab，避免喧宾夺主。

## 7. 字段命名与接口补充问题清单

以下问题不建议前端私自臆测，应作为接口/字段层面的明确议题：

1. `relationship-graph.nodes` 缺少 `entity_subtype`、`controller_class`、`beneficial_owner_disclosed`，导致前端无法稳定标注 trust vehicle、SPV、holding company、nominee vehicle。
2. `display_controller` 是便利字段，但语义上可能是 actual 或 leading。前端必须始终配合 `display_controller_role`，不应单独使用。
3. `country_attribution.actual_control_country` 名称在 fallback 场景略有误导。前端可用“归属国家/地区”做 UI 文案，并在说明里保留后端字段名。
4. `control_ratio` 对 semantic / mixed 控制不总是直接股权比例。前端应在文案中称为“控制比例/综合控制分”，或结合 `control_mode` 分别显示。
5. `joint_controller_entity_ids` 当前在 `country_attribution.basis` 中，不在 top-level summary。若图层要稳定标注 joint participants，建议后端提升为结构化字段。
6. `terminal_failure_reason` 同时可能出现在 relationship 行和 country basis 中。摘要卡应优先使用 actual/leading/focused controller 行，其次使用 `country_attribution.basis.terminal_failure_reason`。

## 8. 建议第一批实现边界

第一批只改摘要卡，暂不大改图和表。

推荐新增展示字段：

- Direct Controller：`control_analysis.direct_controller`
- Ultimate / Actual Controller：`control_analysis.actual_controller`
- Leading Candidate：`control_analysis.leading_candidate`
- Actual Control Country：`country_attribution.actual_control_country`
- Attribution Layer：`country_attribution.attribution_layer`
- Attribution Type：`country_attribution.attribution_type`
- Control Mode / Control Type：从 actual -> direct -> leading 依次取
- Promotion Reason：优先 actual，其次 direct / leading
- Terminal Failure Reason：优先 leading / direct / actual，其次 `country_attribution.basis`
- Look-through Applied：`country_attribution.look_through_applied`
- Fallback Explanation：`attribution_type = fallback_incorporation` 且 `actual_controller` 为空时显示

保留兼容：

- 继续接收 `display_controller`，但只作为“展示主体 fallback”，不再作为实际控制人的唯一来源。
- 继续兼容 `control_relationships` 不在 summary 中时调用 `/control-chain` 的逻辑。
- 不改变后端接口和图布局。
