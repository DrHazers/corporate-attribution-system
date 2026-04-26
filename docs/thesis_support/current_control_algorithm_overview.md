# 当前股权穿透与控制关系分析算法说明

本文档仅依据当前仓库代码整理，目标是为本科毕业论文提供“当前真实实现”的说明依据。若历史文档、设计稿或前端文案与本文不一致，应以当前代码为准。本文重点对应以下代码：

- `backend/analysis/ownership_penetration.py`
- `backend/analysis/control_inference.py`
- `backend/analysis/control_chain.py`
- `backend/analysis/country_attribution_analysis.py`
- `backend/analysis/manual_control_override.py`
- `backend/analysis/ownership_graph.py`
- `backend/tasks/recompute_analysis_results.py`
- `backend/api/analysis.py`
- `backend/api/company.py`

## 1. 总体目标、输入与输出

当前控制分析模块的目标不是单纯做“股权比例连乘”的传统穿透，而是围绕一个目标公司识别：

- 直接控制人（direct controller）
- 实际控制人/最终控制人（actual controller / ultimate controller）
- 领先候选控制人（leading candidate）
- 实际控制国别（actual control country）

输入的核心事实来源是：

- `companies`
- `shareholder_entities`
- `shareholder_structures`
- `relationship_sources`（主要用于关系可信度与来源信息）

输出主要写入：

- `control_relationships`
- `country_attributions`
- `control_inference_runs`
- `control_inference_audit_log`

其中 `control_relationships` 存候选控制关系、控制层级和依据，`country_attributions` 存最终国别归属结果。

## 2. 核心调用链

### 2.1 单公司刷新主链

当前后端单公司刷新入口在 `backend/analysis/ownership_penetration.py` 的 `refresh_company_control_analysis()`。

典型调用链为：

1. API 入口触发刷新  
   典型接口包括：
   - `POST /companies/{company_id}/analysis/refresh`（`backend/api/company.py`）
   - `GET /analysis/control-chain/{company_id}?refresh=true`（`backend/api/analysis.py`）
   - `GET /analysis/country-attribution/{company_id}?refresh=true`
2. `refresh_company_control_analysis()` 选择算法路径
3. 默认进入 `_refresh_company_control_analysis_with_unified_context()`
4. `build_control_context()` 从 `shareholder_structures`、`shareholder_entities` 等构造控制图上下文
5. `infer_controllers()` 计算 direct / actual / leading candidate / country attribution basis
6. `_apply_unified_company_analysis_records()` 清理旧自动结果并写回结果表
7. 读接口再从结果表读取，并按 `result_layer` 决定是否叠加人工覆盖结果

### 2.2 读接口链路

- `backend/analysis/control_chain.py` 的 `analyze_control_chain_with_options()` 负责控制链读取
- `backend/analysis/country_attribution_analysis.py` 的 `analyze_country_attribution_with_options()` 负责国别归属读取

这两者都支持：

- `refresh=False`：直接读已落库结果
- `refresh=True`：先触发刷新再读
- `result_layer="auto"`：读自动分析结果层
- `result_layer="current"`：读当前有效结果层，可能叠加人工覆盖

当前有效结果层由 `backend/analysis/manual_control_override.py` 中的：

- `get_current_effective_control_chain_data()`
- `get_current_effective_country_attribution_data()`

负责组装。

### 2.3 批处理和脚本链路

批量重算入口主要包括：

- `backend/tasks/recompute_analysis_results.py`
- `scripts/run_refresh_on_test_db.py`
- `scripts/run_refresh_on_enhanced_working_db.py`
- `scripts/run_large_control_validation.py`

这些工具会基于数据库批量刷新自动分析结果，并生成 JSON / Markdown / HTML 验证材料。它们不是新的算法实现，而是对已有算法的批处理或验证包装。

## 3. 当前实际使用的是哪套算法

### 3.1 当前默认主算法：unified control inference

当前默认主算法是 `backend/analysis/control_inference.py` 中的统一控制推断逻辑。

其默认性体现在：

- `ownership_penetration._use_unified_control_engine()`：只要环境变量 `CONTROL_INFERENCE_ENGINE` 不是 `"legacy"`，就使用 unified
- `_allow_legacy_fallback()` 当前直接返回 `False`

因此当前运行时的真实默认行为是：

- 默认使用 unified
- 当前未启用“unified 失败后自动回退 legacy”的运行时回退机制

### 3.2 legacy 逻辑仍然存在，但不是默认主链

仓库中仍保留旧版股权穿透逻辑，主要在 `backend/analysis/ownership_penetration.py` 内部旧分支中。

其特点是：

- 以股权比例为主
- 使用 DFS 搜索上游股权路径
- 主要看 `holding_ratio`
- 不纳入当前 unified 中那套语义型控制证据模型

### 3.3 两套逻辑的主要差异

`legacy` 与 `unified` 的主要差异如下：

- `legacy` 以股权边为主，`unified` 同时支持 `equity`、`agreement`、`board_control`、`voting_right`、`nominee`、`vie`
- `legacy` 主要做比例连乘，`unified` 对每条边构造数值因子、语义因子和可信度因子
- `legacy` 输出相对简单，`unified` 能区分 direct / actual / ultimate / leading candidate / joint control / fallback
- `unified` 会写入 `control_inference_runs` 与 `control_inference_audit_log`，保留更完整的推断痕迹

### 3.4 当前实际使用边界

当前代码中的真实边界是：

- 单公司刷新默认走 unified
- 批量重算工具也支持 unified 和 legacy 两种模式
- `backend/tasks/recompute_analysis_results.py` 仍保留显式指定 legacy 的能力
- 因此论文中可以说“系统当前默认主算法为 unified，旧版 legacy 逻辑作为兼容/对照路径保留”，但不能说“仓库中只有一套算法”

## 4. 参与算法计算的核心表和关键字段

### 4.1 `companies`

与控制分析、国别归属直接相关的字段主要有：

- `id`
- `name`
- `stock_code`
- `incorporation_country`
- `listing_country`
- `headquarters`
- `description`

其中：

- `incorporation_country` 是当前后端明确使用的兜底国别来源
- `listing_country`、`headquarters` 当前更多是存储与展示字段，不是 unified 国别判定主规则的一部分

### 4.2 `shareholder_entities`

当前 unified 算法会实际读取和利用的字段包括：

- `id`
- `entity_name`
- `entity_type`
- `country`
- `company_id`
- `entity_subtype`
- `ultimate_owner_hint`
- `look_through_priority`
- `controller_class`
- `beneficial_owner_disclosed`
- `notes`

这些字段用于：

- 实体基本身份识别
- 是否适合继续向上穿透
- 是否提示 ultimate owner
- 是否属于 holding vehicle、family trust、state、fund complex 等特定主体类型
- 是否已披露受益所有人

### 4.3 `shareholder_structures`

这是控制图的核心边表。当前 unified 实际用到的关键字段包括：

- `from_entity_id`
- `to_entity_id`
- `holding_ratio`
- `voting_ratio`
- `economic_ratio`
- `effective_control_ratio`
- `relation_type`
- `control_type`
- `has_numeric_ratio`
- `is_beneficial_control`
- `look_through_allowed`
- `termination_signal`
- `relation_role`
- `control_basis`
- `board_seats`
- `nomination_rights`
- `agreement_scope`
- `relation_metadata`
- `relation_priority`
- `confidence_level`
- `effective_date`
- `expiry_date`
- `is_current`
- `is_direct`
- `remarks`

### 4.4 `control_relationships`

当前 unified 写回时使用的字段比旧版更丰富，核心包括：

- `company_id`
- `controller_entity_id`
- `controller_name`
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
- `control_mode`
- `semantic_flags`
- `review_status`
- `notes`

### 4.5 `country_attributions`

核心字段包括：

- `company_id`
- `incorporation_country`
- `listing_country`
- `actual_control_country`
- `actual_controller_entity_id`
- `direct_controller_entity_id`
- `attribution_type`
- `attribution_layer`
- `country_inference_reason`
- `look_through_applied`
- `inference_run_id`
- `basis`
- `source_mode`
- `is_manual`
- `notes`

## 5. 股权穿透与多层路径搜索规则

### 5.1 当前 unified 图搜索的基本边过滤

`build_control_context()` 构图时，当前会把满足以下条件的关系作为可分析边纳入：

- `is_current = 1`
- `is_direct = 1`
- 在当前时间点 `effective_date` / `expiry_date` 有效
- `relation_type` 属于当前支持集合

当前支持的关系类型常量位于 `control_inference.py` 的 `SUPPORTED_RELATION_TYPES`，包括：

- `equity`
- `agreement`
- `board_control`
- `voting_right`
- `nominee`
- `vie`

这里要注意：虽然只读取“直接边”，但 unified 会在这些直接边构成的图上继续向上递归搜索，因此仍然能形成多层控制路径。

### 5.2 路径搜索方式

当前 unified 使用 `collect_control_paths()` 做深度优先搜索。

真实实现特点为：

- 搜索方向是“从目标公司实体向上找谁控制了它”
- 使用 DFS 递归/栈式扩展路径
- 默认最大深度是 `DEFAULT_MAX_DEPTH = 10`
- 使用已访问实体集合避免环路
- 最小路径分值阈值为 `DEFAULT_MIN_PATH_SCORE = 0.0001`

这意味着：

- 代码支持多层穿透
- 代码支持去环
- 代码会对极弱路径剪枝

### 5.3 路径分值计算

当前 unified 的路径分值不是简单的股权比例连乘，而是：

- `numeric_prod`：路径上数值型控制因子的累乘
- `semantic_prod`：路径上语义型控制因子的累乘
- `path_score = numeric_prod * semantic_prod`

可信度 `confidence_prod` 会单独记录，用于排序和解释，但不是唯一的控制强度值。

### 5.4 单边因子构造

当前代码由 `edge_to_factor()` 为每条边构造控制因子。

对不同边：

- `equity` 边主要来自 `holding_ratio` / `effective_control_ratio` 等数值字段
- `voting_right` 可能使用 `voting_ratio`
- `board_control` 可结合 `board_seats` 和 `relation_metadata.total_board_seats`
- `agreement`、`nominee`、`vie` 会结合 `agreement_scope`、`control_basis`、`nomination_rights`、`relation_metadata`、`remarks` 等语义信息评分

因此论文中更准确的表述应是：

- 当前系统对股权边使用比例型数值控制强度
- 对非股权边使用规则化语义证据模型
- 两者可以混合形成同一控制路径

### 5.5 多路径聚合

同一上游主体可能通过多条路径影响目标公司。当前 unified 会将同一 `controller_entity_id` 下的多条路径聚合成一个候选控制人。

默认聚合器是：

- `DEFAULT_AGGREGATOR = "sum_cap"`

含义是：

- 将同一主体的多条路径分值相加
- 总分上限封顶为 `1.0`

代码中还存在 `noisy_or` 聚合器实现，但当前默认并不用它。

## 6. 实际控制人识别规则

### 6.1 候选控制人形成与披露阈值

路径聚合后会形成控制候选人。当前默认阈值为：

- 控制阈值 `DEFAULT_CONTROL_THRESHOLD = 0.5`
- 显著影响阈值 `DEFAULT_SIGNIFICANT_THRESHOLD = 0.2`
- 披露阈值 `DEFAULT_DISCLOSURE_THRESHOLD = 0.2`

因此当前默认口径是：

- 候选总分低于 20% 的主体通常不会作为主要输出候选展示
- 50% 及以上是严格控制判定的重要门槛

### 6.2 direct controller 与 actual controller

`infer_controllers()` 当前会区分：

- `direct_controller_entity_id`
- `actual_controller_entity_id`
- `leading_candidate_entity_id`

其中：

- direct controller 更接近“当前结构上直接形成控制的主体”
- actual controller 是综合路径、竞争情况、joint control、promotion 等后得到的最终控制主体
- 若无法形成唯一 actual controller，系统仍可能保留 leading candidate

### 6.3 ultimate controller / rollup / promotion

当前 unified 明确支持“从直接控制人继续向上推到最终控制人”的 rollup / promotion 逻辑。

相关特征包括：

- 对 holding vehicle、trust vehicle 等中间层主体可继续向上看
- `look_through_priority`
- `ultimate_owner_hint`
- `controller_class`
- `beneficial_owner_disclosed`
- `look_through_allowed`
- `termination_signal`

都可能影响是否继续 promotion。

写回后会在 `control_relationships` 中反映为：

- `is_direct_controller`
- `is_intermediate_controller`
- `is_ultimate_controller`
- `promotion_source_entity_id`
- `promotion_reason`
- `terminal_failure_reason`

从测试 `tests/test_terminal_controller_v2.py`、`tests/test_trust_control_rules.py` 可见，当前代码确实支持：

- direct controller 与 ultimate controller 分层
- trust vehicle look-through
- disclosed family trust 保守终止
- nominee / undisclosed vehicle 阻断 promotion

### 6.4 joint control

当前 unified 明确支持 joint control 的识别。

表现为：

- 语义规则中存在 joint control 信号
- `_joint_control_entity_ids()` 会识别联合控制情形
- 若属于联合控制，系统通常不会强行选出唯一 actual controller

当前后端在此场景下的典型结果是：

- `actual_controller_entity_id = None`
- `attribution_type = "joint_control"`
- `actual_control_country = "undetermined"`
- `attribution_layer = "joint_control_undetermined"`

### 6.5 nominee、beneficial owner unknown、disclosure 处理

当前代码对 nominee、beneficial owner、disclosure 相关情形是“部分支持”，更准确地说是：

- 支持把 nominee / trust / beneficial owner disclosure 作为控制推断证据
- 支持把“未披露受益所有人”作为阻断或降权因素
- 支持在有明确披露时继续向上穿透

但当前未实现的是：

- 仅凭模糊文本自动稳定恢复隐藏受益所有人的完整识别机制
- 一个单独命名为 “beneficial_owner_unknown” 的正式国别归属类型

也就是说，这类信息当前主要用于：

- 阻断 promotion
- 降低控制可信度
- 解释为什么系统没有继续上推

而不是保证一定识别出真正受益人。

### 6.6 fallback_incorporation

当系统无法形成足够强的实际控制结论时，当前后端明确支持：

- `fallback_incorporation`

即回落到目标公司注册地作为控制国别。

这是后端当前真实存在且明确落库的 fallback 类型。

## 7. 非股权控制关系的处理规则

当前 unified 中，非股权控制关系不是“只做展示”，而是实质参与控制推断。

### 7.1 `agreement`

会结合：

- `agreement_scope`
- `control_basis`
- `remarks`
- `relation_metadata`

进行语义评分。若是“exclusive service agreement”“control over relevant activities”等强控制表述，可以形成语义型控制结果。

### 7.2 `board_control`

会结合：

- `board_seats`
- `nomination_rights`
- `relation_metadata`

评估董事会控制。测试中存在基于董事席位比例形成 `board_control` 结果的样例。

### 7.3 `voting_right`

会结合投票权安排参与控制推断。它可用于：

- 直接形成控制候选
- 作为 promotion 到上层主体的依据之一

### 7.4 `vie`

当前 unified 明确把 VIE 作为支持的关系类型之一，并把其权力、收益、排他性等信号纳入语义评分。

### 7.5 `nominee`

当前 nominee 不只是标签，确实参与控制推断，但其作用高度依赖是否有受益所有人披露、look-through 证据是否充分。很多情况下 nominee 更容易触发保守阻断，而不是直接确认 ultimate controller。

### 7.6 protective rights

当前系统会识别“仅保护性权利”的场景，并保守处理。测试 `tests/test_mixed_control_paths.py` 中，protective rights 仅作为协议性保护时不会形成控制结果，最终会回落到 `fallback_incorporation`。

## 8. 国别归属判定规则

### 8.1 当前真实主规则

国别归属当前不是独立大算法，而是 unified 控制推断结果的延伸。

基本顺序是：

1. 若识别出 actual controller，则优先取 actual controller 的国别
2. 若 actual controller 不成立但 direct controller 成立，则可退到 direct controller 国别
3. 若属于 joint control，则给出 `undetermined`
4. 若无有效控制主体，则回落到目标公司 `incorporation_country`

### 8.2 controller 国别从哪里取

`control_inference._resolve_controller_country()` 当前的真实取值顺序是：

1. `ShareholderEntity.country`
2. 若该实体映射到 `entity.company`，则读取其对应公司 `incorporation_country`

因此：

- 当前确实会用控制主体实体国别
- 若实体本身没有 `country`，会尝试用其映射公司的注册地

### 8.3 `listing_country` 与 `headquarters` 是否参与决策

当前 unified 后端主规则中：

- `listing_country` 当前未作为正式 fallback 决策主规则使用
- `headquarters` 当前未作为正式 fallback 决策主规则使用

它们在模型、接口和前端展示中存在，但不等于后端当前真的按它们判定国别。

因此论文中不能写成：

- “系统会按注册地、上市地、总部地多级自动回退”

更准确的写法是：

- “当前后端已明确实现的兜底规则是回落至注册地；上市地和总部地目前主要是存储/展示字段，未构成 unified 主判定链”

## 9. 结果如何写入 `control_relationships` 和 `country_attributions`

### 9.1 自动结果清理与重写

`_apply_unified_company_analysis_records()` 当前会先清理该公司旧的自动生成结果，清理依据主要是：

- `notes` 以 `AUTO:` 开头的自动结果行

这意味着：

- 自动结果会被本次刷新覆盖
- 人工结果不会按同一规则被直接清掉

### 9.2 `control_relationships` 写回方式

当前会把候选控制人及最终判定层次写入 `control_relationships`。

写回内容通常包括：

- 控制人身份
- 控制类型 `control_type`
- 控制模式 `control_mode`
- 聚合控制比例/分值 `control_ratio`
- 路径明细 `control_path`
- `basis` JSON
- 是否为 direct / actual / ultimate
- promotion 来源和原因
- terminal failure reason
- `review_status = "auto"`
- `notes = "AUTO: generated by ownership penetration"`

### 9.3 `country_attributions` 写回方式

当前每次 unified 自动推断会写入一条自动国别归属记录，包含：

- `actual_control_country`
- `actual_controller_entity_id`
- `direct_controller_entity_id`
- `attribution_type`
- `attribution_layer`
- `country_inference_reason`
- `look_through_applied`
- `basis`
- `source_mode`
- `inference_run_id`
- `is_manual = False`

### 9.4 运行审计

当前 unified 还会写入：

- `control_inference_runs`
- `control_inference_audit_log`

其中 run 级摘要和 step 级日志可用于解释：

- 为什么发生 promotion
- 为什么某个候选被阻断
- 为什么最终选择 direct / actual / fallback

## 10. 当前算法边界、限制与已知不一致点

### 10.1 读接口默认不是实时重算

当前 `GET /analysis/control-chain/{company_id}`、`GET /analysis/country-attribution/{company_id}` 默认只是读库。

只有：

- `refresh=true`
- 或显式刷新接口

才会触发重新计算。

因此论文中不能写成“前端每次打开页面都实时跑算法”。

### 10.2 图展示使用的边集不等于算法最终采纳边集

`backend/analysis/ownership_graph.py` 构造前端关系图时，会遍历当前直接关系图，主要用于展示结构。

这与 unified 最终用于 actual controller 判定并写入 `control_relationships.basis` / `control_path` 的“关键证据路径”不是完全同一集合。

因此：

- 前端图展示更接近“当前上游关系图”
- 算法结论更接近“经过过滤、评分、聚合后的控制证据结果”

二者不能简单视为完全一一对应。

### 10.3 `current` 与 `auto` 两层结果并存

当前系统存在：

- 自动分析层 `auto`
- 叠加人工覆盖后的当前有效层 `current`

前端默认更偏向读 `current`。因此如果论文描述页面展示结果，必须说明：

- 页面看到的结果不一定就是原始自动推断结果
- 可能是 `manual_control_override.py` 叠加后的当前有效结果

### 10.4 批处理工具仍保留 legacy 模式

虽然默认主算法是 unified，但批处理任务 `backend/tasks/recompute_analysis_results.py` 仍支持显式选择 legacy。

因此仓库中“批量工具仍可调用旧逻辑”这一点是真实存在的。

### 10.5 前端标签与后端真实返回值存在轻微不一致

`frontend/src/components/ControlSummaryCard.vue` 中存在：

- `fallback_listing`
- `fallback_headquarters`

等前端标签映射。

但当前后端 schema 和 unified 写回中，明确存在并稳定使用的是：

- `fallback_incorporation`

因此这两类前端标签当前更像预留显示分支，不能据此前推为后端已实现上市地/总部地回退逻辑。

### 10.6 beneficial owner / nominee / trust 属于“部分支持”

当前代码确实处理这些情形，但很多地方是：

- 用于阻断
- 用于降权
- 用于是否允许继续上推

而不是保证一定能自动还原最深层自然人受益人。

因此在论文里宜写成“部分支持复杂受益所有人/代持/信托场景的保守识别与穿透”，不宜写成“已完全解决复杂隐性控制识别”。

## 11. 适合论文写作的表述建议

### 11.1 可以作为重点强调的内容

- 当前系统已从单纯股权穿透扩展为统一控制链推断
- 算法支持股权关系与协议控制、董事会控制、投票权安排、VIE、nominee 等多类控制信号的混合分析
- 算法支持多层路径搜索、去环、路径聚合、direct/actual/ultimate 分层和审计留痕
- 国别归属与控制链分析结果联动，能输出控制主体国别与注册地兜底结果
- 系统存在自动结果层与人工覆盖层，适合研究型“算法 + 人工征订”场景

### 11.2 不宜夸大的内容

- 不能写成“只有一套算法”，因为仓库中仍保留 legacy
- 不能写成“所有读接口实时重算”
- 不能写成“图展示与算法证据完全一致”
- 不能写成“已完整实现按上市地、总部地自动回退国别”
- 不能写成“已完全自动识别所有复杂受益所有人/信托/代持结构”

### 11.3 可直接用于论文的简短总结

可表述为：

> 当前项目的控制分析模块采用以 unified control inference 为主的多源控制推断方案。系统以公司、股东实体与股东关系为基础，沿上游关系图进行多层路径搜索，并对股权比例、投票权、协议安排、董事会控制、VIE、nominee 等控制信号进行统一评分与聚合，从而识别直接控制人、实际控制人及其控制国别。系统同时保留旧版股权穿透逻辑作为兼容路径，但当前默认运行链路已以 unified 算法为主。该实现适合在论文中表述为“面向复杂控制关系的统一控制链分析与国别归属判定”，但不宜夸大为“完全自动解决所有隐性控制识别问题”。
