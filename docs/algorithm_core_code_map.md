# Ultimate Controller / Country Attribution 核心代码导览

更新日期：2026-04-19

本文档基于当前仓库代码、SQLAlchemy 模型、Pydantic schema、API、测试和脚本整理。旧文档可作为背景资料，但当旧文档与当前代码不一致时，以本文档引用的当前代码路径和函数为准。

## 1. 文档目标

这份文档面向后续 Deep Research、算法优化分析、新对话承接、前后端联调排查和论文写作。它不修改算法，也不修改数据库 schema，而是回答几个代码层面的核心问题：

- 从一个 `company_id` 出发，当前 ultimate controller / country attribution 主流程实际调用哪些代码。
- 哪些文件是真正的算法主干，哪些只是 API、summary、可视化或历史兼容层。
- 哪些函数最适合用来研究 actual controller、ultimate controller、fallback、promotion、semantic evidence、public-float-like 等争议问题。
- 前端展示和论文描述中看到的字段，分别来自哪些表、schema、API 和 write-back 逻辑。

## 2. 当前算法主链路总览

当前主版本以 `backend.analysis.ownership_penetration.refresh_company_control_analysis()` 作为刷新入口，默认使用统一控制推断引擎。代码中仍保留 `CONTROL_INFERENCE_ENGINE=legacy` 的历史路径，但默认主流程是 unified engine，不应把 legacy ownership-only 路径当作当前算法主干。

主链路可以概括为：

1. API 或脚本传入 `company_id`。
2. `ownership_penetration.refresh_company_control_analysis()` 找到目标公司和目标 `shareholder_entities`。
3. `control_inference.build_control_context()` 从 `shareholder_structures`、`shareholder_entities`、`relationship_sources` 构建控制图上下文。
4. `control_inference.infer_controllers()` 对目标实体生成候选控制人，聚合 equity、voting_right、board_control、agreement、VIE、nominee、trust 等语义证据。
5. 推断结果区分 direct controller、leading candidate、actual controller、ultimate controller、joint block、fallback、terminal failure 等状态。
6. `ownership_penetration._apply_unified_company_analysis_records()` 将候选和最终结果写回：
   - `control_relationships`
   - `country_attributions`
   - `control_inference_runs`
   - `control_inference_audit_log`
7. API 读取持久化结果，供前端和 summary 使用：
   - 控制链：`backend/api/analysis.py`、`backend/api/company.py`
   - 国家归属：`backend/analysis/country_attribution_analysis.py`
   - 一屏汇总：`backend/analysis/industry_analysis.py.get_company_analysis_summary()`

特别注意：`country_attribution_analysis.py` 不是独立重新计算国家归属规则的核心引擎，它主要包装控制链刷新/读取，并读取最新 `country_attributions` 记录。国家归属类型、归属国家和 basis 的核心写入逻辑在 unified inference write-back 过程中完成。

## 3. 核心文件清单

### 3.1 真正的主干核心文件

| 文件 | 主流程位置 | 主要职责 | 深度研究最该看什么 |
|---|---|---|---|
| `backend/analysis/control_inference.py` | 统一控制推断核心 | 构建上下文、边评分、路径收集、候选排序、actual gate、promotion、joint/fallback/country attribution 类型判断 | `build_control_context()`、`edge_to_factor()`、`infer_controllers()`、semantic evidence scoring、block reason、promotion、country attribution resolver |
| `backend/analysis/ownership_penetration.py` | 刷新入口与写回层 | 选择 unified/legacy 引擎、开启 inference run、调用推断、删除旧自动结果、写入 `control_relationships` 和 `country_attributions`、提供 read-side control-chain 数据 | `refresh_company_control_analysis()`、`_apply_unified_company_analysis_records()`、`get_company_control_chain_data()` |
| `backend/analysis/control_chain.py` | 控制链分析包装层 | 为 API 提供 `refresh` 开关和统一返回结构；refresh 时委托 `ownership_penetration` | `analyze_control_chain_with_options()`、`analyze_control_chain()` |
| `backend/analysis/country_attribution_analysis.py` | 国家归属读取/包装层 | 触发或复用控制链结果，读取最新 `country_attributions` 并合并 control-chain basis | `analyze_country_attribution_with_options()` |
| `backend/analysis/ownership_graph.py` | 关系图/上下游图数据 | 构建前端 relationship graph、特殊控制关系摘要、路径上下文 | `get_company_relationship_graph_data()`、`get_company_special_control_relations_summary()` |
| `backend/analysis/industry_analysis.py` | 一屏 summary 聚合层 | 不是控制推断核心，但当前前端推荐入口会聚合公司、控制链、国家归属和产业研究 | `get_company_analysis_summary()` |

### 3.2 重要辅助文件

| 文件 | 类型 | 作用 |
|---|---|---|
| `backend/models/shareholder.py` | 输入模型 | 定义 `shareholder_entities`、`shareholder_structures`、`relationship_sources`、`entity_aliases` 等控制图输入表 |
| `backend/models/control_relationship.py` | 输出模型 | 存储候选控制关系、direct/actual/ultimate 标记、promotion、terminal failure、semantic flags、basis |
| `backend/models/country_attribution.py` | 输出模型 | 存储最终国家归属、归属层级、推断原因、look-through 标记和 basis |
| `backend/models/control_inference_run.py` | 运行记录 | 存储每次推断运行、状态、引擎版本、输入/输出摘要 |
| `backend/models/control_inference_audit_log.py` | 审计留痕 | 存储候选选择、阻断、promotion、fallback 等过程记录 |
| `backend/schemas/control_relationship.py` | API schema | 暴露控制候选、direct/actual/ultimate、promotion、terminal failure、basis、semantic flags |
| `backend/schemas/country_attribution.py` | API schema | 暴露国家归属、归属类型、归属层级、controller ids、look-through、basis |
| `backend/schemas/industry_analysis.py` | Summary schema | 暴露公司一屏汇总中的控制链、国家归属和产业分析结构 |
| `backend/api/analysis.py` | API | `/analysis/control-chain/{company_id}`、`/analysis/country-attribution/{company_id}`、上游股东图 |
| `backend/api/company.py` | API | 公司维度的 control-chain、actual-controller、country-attribution、refresh、relationship-graph |
| `backend/api/industry_analysis.py` | API | `/companies/{company_id}/analysis/summary`，前端推荐的一屏汇总入口 |
| `backend/api/control_relationship.py` | API | 控制关系 CRUD/查询入口，偏结果表维护 |
| `backend/api/country_attribution.py` | API | 国家归属结果 CRUD/查询入口 |
| `backend/shareholder_relations.py` | 工具层 | 股东关系解析、导入或辅助关系处理，属于输入关系生态的一部分 |

### 3.3 前端消费与可视化文件

| 文件 | 作用 | 研究价值 |
|---|---|---|
| `frontend/src/api/analysis.js` | 前端请求 summary、industry analysis、control chain | 确认前端实际调用哪些 API |
| `frontend/src/views/CompanyAnalysisView.vue` | 公司分析主页面 | 确认 summary 缺字段时是否追加请求 control-chain |
| `frontend/src/components/company/ControlSummaryCard.vue` | 控制摘要卡片 | 确认 actual/direct/leading candidate 的展示逻辑 |
| `frontend/src/components/company/ControlRelationsTable.vue` | 控制关系表格 | 确认 `promotion_reason`、`terminal_failure_reason`、semantic fields 的表格展示 |
| `frontend/src/components/company/ControlStructureDiagram.vue` | 当前控制结构图 | 排查前端为什么画成某种控制链形态 |
| `frontend/src/utils/controlStructureAdapter.js` | 当前控制结构适配器 | 将后端 control-chain summary 转成图形节点/边 |
| `frontend/src/utils/graphAdapter.js` | relationship graph 适配器 | 排查股权图和关系图的节点边转换 |
| `frontend/src/components/visualization/LegacyControlChainDiagram.vue` | 旧展示组件 | 当前仍存在但不应作为新主链路理解入口 |
| `frontend/src/utils/legacyControlChainAdapter.js` | 旧适配器 | 历史兼容/旧展示逻辑，研究时要和当前结构图区分 |
| `backend/visualization/control_graph.py` | 后端 HTML 可视化 | 构建控制图上下文、highlight、summary card，适合做论文图或样本排查 |
| `scripts/build_demo_visualizations.py` | 可视化脚本 | 批量生成典型样本图，用于汇报或论文图例 |

### 3.4 测试、脚本和文档支撑文件

| 文件 | 类型 | 用途 |
|---|---|---|
| `tests/test_ultimate_controller_dataset_regression.py` | 回归测试 | 小型标准样本集，覆盖 direct=ultimate、rollup、joint、nominee、fallback、board_control、VIE 等 |
| `tests/test_extended_semantic_controls.py` | 回归测试 | 语义控制扩展样本，覆盖 voting_right、nominee、VIE、protective rights |
| `tests/test_mixed_and_non_equity_threshold_tuning.py` | 回归测试 | mixed control、agreement、voting proxy、低置信阻断 |
| `tests/test_rollup_success_promotion_tuning.py` | 回归测试 | rollup/promotion 调参重点 |
| `tests/test_trust_control_rules.py` | 回归测试 | trust vehicle、family trust、nominee trust |
| `tests/test_semantic_control_evidence_model.py` | 回归测试 | semantic evidence 分层模型，适合研究证据强弱 |
| `tests/test_mixed_control_paths.py` | 回归测试 | 混合路径、环路剪枝、joint/protective fallback |
| `tests/control_inference_test_utils.py` | 测试工具 | 构造临时 DB、刷新并读取控制/归属结果 |
| `scripts/run_refresh_on_test_db.py` | 脚本 | 刷新小型测试 DB，输出 JSON 摘要 |
| `scripts/run_large_control_validation.py` | 脚本 | 大库分层抽样验证，找代表样本和异常分布 |
| `scripts/run_refresh_on_enhanced_working_db.py` | 脚本 | 刷新增强工作库 |
| `scripts/summarize_enhanced_working_results.py` | 脚本 | 汇总增强工作库结果分布和样本验证类别 |
| `scripts/build_enhanced_target_regression_table.py` | 脚本 | 构建增强目标回归表，适合整理论文或 Deep Research 样本 |
| `docs/current_control_inference_summary.md` | 文档 | 当前控制推断概览，需与代码交叉核对 |
| `docs/ultimate_controller_algorithm_explained.md` | 文档 | 算法解释材料，适合论文叙述参考 |
| `docs/semantic_control_evidence_model_v1.md` | 文档 | 语义控制证据模型说明 |
| `docs/ultimate_controller_rules_v2.md` | 文档 | 规则口径说明，部分内容可能落后于代码 |

## 4. 调用关系与阅读顺序建议

### 4.1 理解 actual controller 如何得出

建议阅读顺序：

1. `backend/analysis/ownership_penetration.py`
   - 先看 `refresh_company_control_analysis()`，确认当前 refresh 入口和 unified engine 分支。
   - 再看 `_apply_unified_company_analysis_records()`，理解最终字段如何写入数据库。
2. `backend/analysis/control_inference.py`
   - `build_control_context()`：理解目标公司如何进入控制图。
   - `edge_to_factor()`：理解一条 `shareholder_structures` 边如何变成可评分控制因子。
   - `_score_semantic_evidence()` 及相关 scoring 函数：理解非股权语义证据如何加权。
   - `collect_control_paths()`：理解路径如何搜索、剪枝和累计。
   - `_build_candidates_for_target_entity()`：理解候选控制人如何产生。
   - `infer_controllers()`：理解 direct、actual、ultimate、fallback 的总控逻辑。
3. `backend/models/control_relationship.py`
   - 对照最终写入字段，确认代码里的候选状态如何落库。
4. `backend/schemas/control_relationship.py`
   - 确认哪些字段被 API 暴露给前端或外部调用方。

### 4.2 理解为什么某个样本 fallback

优先看这些位置：

- `control_inference._controller_block_reason()`
- `control_inference._actual_control_evidence_block_reason()`
- `control_inference._promotion_block_reason()`
- `control_inference._is_close_competition()`
- `control_inference._resolve_controller_status()`
- `control_inference._build_unified_basis_payload()`
- `ownership_penetration._apply_unified_company_analysis_records()`
- `control_relationships.terminal_failure_reason`
- `country_attributions.attribution_type`
- `country_attributions.attribution_layer`
- `country_attributions.country_inference_reason`
- `country_attributions.basis`

排查时不要只看 `country_attributions.actual_control_country`。很多 fallback 的关键证据在 `control_relationships` 的候选行和 basis payload 里。

### 4.3 理解前端为什么显示成这样

建议阅读顺序：

1. `backend/analysis/industry_analysis.py.get_company_analysis_summary()`
2. `backend/schemas/industry_analysis.py`
3. `frontend/src/api/analysis.js`
4. `frontend/src/views/CompanyAnalysisView.vue`
5. `frontend/src/components/company/ControlSummaryCard.vue`
6. `frontend/src/components/company/ControlRelationsTable.vue`
7. `frontend/src/components/company/ControlStructureDiagram.vue`
8. `frontend/src/utils/controlStructureAdapter.js`

当前前端一屏分析主要从 summary 入口消费结果。如果 summary 返回的 `control_analysis.control_relationships` 不完整，页面逻辑会追加请求 control-chain。因此同一页面可能同时受 summary API 和 control-chain API 影响。

### 4.4 理解 public float、board_control、agreement、voting_right、VIE 问题

优先看：

- `control_inference.edge_to_factor()`
- `_score_power_signals()`
- `_score_economic_signals()`
- `_score_exclusivity_signals()`
- `_score_disclosure_signals()`
- `_score_reliability_signals()`
- `_score_semantic_evidence()`
- `_combine_semantic_evidence_score()`
- `_build_candidates_for_target_entity()`
- `_actual_control_evidence_block_reason()`
- `_promotion_block_reason()`
- `_promotable_rollup_company_candidate()`

然后结合这些测试：

- `tests/test_extended_semantic_controls.py`
- `tests/test_mixed_and_non_equity_threshold_tuning.py`
- `tests/test_semantic_control_evidence_model.py`
- `tests/test_mixed_control_paths.py`

## 5. 重点函数索引

| 函数 | 文件 | 功能说明 | 研究价值 | 适合回答的问题 |
|---|---|---|---|---|
| `refresh_company_control_analysis()` | `backend/analysis/ownership_penetration.py` | 控制分析 refresh 总入口 | 确认当前主流程、legacy/unified 分支和返回结构 | “company_id 进入算法后第一站在哪里？” |
| `_refresh_company_control_analysis_with_unified_context()` | `backend/analysis/ownership_penetration.py` | unified engine 执行包装 | 串联 context、inference、write-back | “统一引擎在哪里被调用？” |
| `_apply_unified_company_analysis_records()` | `backend/analysis/ownership_penetration.py` | 写回控制关系和国家归属 | 研究字段落库和 API 输出口径的关键 | “为什么数据库里这几个字段是这个值？” |
| `_start_inference_run()` / `_finalize_inference_run()` | `backend/analysis/ownership_penetration.py` | 记录推断运行 | 运行审计、批量验证和问题追踪 | “这次结果是哪次运行产生的？” |
| `_append_inference_audit_logs()` | `backend/analysis/ownership_penetration.py` | 写入审计日志 | 过程留痕和候选选择分析 | “候选为什么被选中或阻断？” |
| `build_control_context()` | `backend/analysis/control_inference.py` | 构建控制图上下文 | 输入图结构入口 | “哪些边和实体进入了本次推断？” |
| `edge_to_factor()` | `backend/analysis/control_inference.py` | 将结构边转换为控制因子 | 股权、投票权、协议、董事会、VIE 等证据入口 | “某条关系边为什么有这个 control_mode / score？” |
| `_score_semantic_evidence()` | `backend/analysis/control_inference.py` | 语义控制证据总评分 | 非股权控制研究核心 | “board_control/agreement/VIE 为什么强或弱？” |
| `_score_reliability_signals()` | `backend/analysis/control_inference.py` | 可信度和来源评分 | 研究 `relationship_sources` 对结果的影响 | “来源质量如何改变候选可信度？” |
| `_score_power_signals()` | `backend/analysis/control_inference.py` | 权力类语义评分 | 董事会、投票、任免权研究入口 | “治理权是否足以构成控制？” |
| `_score_economic_signals()` | `backend/analysis/control_inference.py` | 经济利益类评分 | VIE、收益权、经济暴露研究入口 | “经济利益是否支持实际控制？” |
| `_score_exclusivity_signals()` | `backend/analysis/control_inference.py` | 排他/锁定类评分 | 协议控制、独家安排研究入口 | “协议是否只是保护性条款？” |
| `_score_disclosure_signals()` | `backend/analysis/control_inference.py` | 披露类评分 | beneficial owner、nominee、ultimate owner hint | “是否有披露证据支持穿透？” |
| `_combine_semantic_evidence_score()` | `backend/analysis/control_inference.py` | 综合语义证据 | 调参和证据冲突研究 | “多个弱信号如何合成强/弱证据？” |
| `collect_control_paths()` | `backend/analysis/control_inference.py` | 收集控制路径 | 路径深度、环路、累计控制比例研究 | “控制路径为什么到这里停止？” |
| `_build_candidates_for_target_entity()` | `backend/analysis/control_inference.py` | 生成目标候选控制人 | 候选池、排序、直接候选入口 | “谁成为候选，谁没有进入候选？” |
| `_classify_control_level()` | `backend/analysis/control_inference.py` | 控制强度分类 | 区分 equity_control、significant_influence、mixed_control | “control_type 为什么这样分类？” |
| `_controller_sort_key()` | `backend/analysis/control_inference.py` | 候选排序 | close competition、public-float-like 争议入口 | “为什么 A 排在 B 前面？” |
| `_direct_candidate_sort_key()` | `backend/analysis/control_inference.py` | direct candidate 排序 | 直接控制人选择入口 | “直接控制人为什么是它？” |
| `_joint_control_entity_ids()` | `backend/analysis/control_inference.py` | joint control 识别 | 50/50、共同控制阻断 | “为什么没有单一 actual controller？” |
| `_controller_block_reason()` | `backend/analysis/control_inference.py` | 候选阻断原因 | fallback 和 terminal failure 分析 | “候选为什么被阻断？” |
| `_actual_control_evidence_block_reason()` | `backend/analysis/control_inference.py` | actual gate 阻断 | 低置信、证据弱、protective rights 研究入口 | “候选为什么没能成为 actual controller？” |
| `_promotion_block_reason()` | `backend/analysis/control_inference.py` | promotion 阻断 | rollup、holdco、trust、nominee 研究入口 | “为什么没有向上穿透？” |
| `_is_close_competition()` | `backend/analysis/control_inference.py` | 接近竞争判断 | 多候选、分散持股、public float 争议入口 | “是否存在难以明确的竞争候选？” |
| `_promotable_rollup_company_candidate()` | `backend/analysis/control_inference.py` | 可上推候选选择 | direct holdco 到 ultimate owner 的关键 | “直接控制人是否应该继续上推？” |
| `_promotion_reason_for_entity()` | `backend/analysis/control_inference.py` | promotion reason 生成 | 解释 `promotion_reason` 字段 | “为什么是 disclosed parent / beneficial owner priority？” |
| `_resolve_country_attribution_type()` | `backend/analysis/control_inference.py` | 归属类型解析 | 国家归属结果口径入口 | “为什么是 equity_control、mixed_control、fallback 或 joint_control？” |
| `_resolve_controller_country()` | `backend/analysis/control_inference.py` | 控制人国家解析 | 国家归属核心辅助 | “actual controller 的国家从哪里来？” |
| `_build_unified_basis_payload()` | `backend/analysis/control_inference.py` | 控制关系 basis | Deep Research 最重要解释字段之一 | “候选判断依据里有哪些证据？” |
| `_build_unified_country_basis_payload()` | `backend/analysis/control_inference.py` | 国家归属 basis | 国家归属解释字段 | “国家归属为什么是这个国家？” |
| `get_company_control_chain_data()` | `backend/analysis/ownership_penetration.py` | 读取控制链结果 | API/前端结果来源 | “前端看到的控制链来自哪里？” |
| `_normalize_country_basis_payload()` | `backend/analysis/ownership_penetration.py` | 归一化国家归属 basis | API 输出一致性 | “basis 字段为什么被改写/补齐？” |
| `analyze_country_attribution_with_options()` | `backend/analysis/country_attribution_analysis.py` | 国家归属分析包装 | refresh/read 行为和返回结构 | “国家归属 API 是怎么算还是读？” |
| `get_company_analysis_summary()` | `backend/analysis/industry_analysis.py` | 汇总公司、控制、国家、产业 | 前端一屏入口 | “页面 summary 为什么缺/有某个字段？” |

## 6. 当前实现中最值得深度研究关注的薄弱点入口

以下是代码结构层面的研究入口定位，不代表需要立即改代码。

### 6.1 Semantic evidence vs high-equity competition

相关入口：

- `_score_semantic_evidence()`
- `_combine_semantic_evidence_score()`
- `_controller_sort_key()`
- `_actual_control_evidence_block_reason()`
- `_is_close_competition()`

研究问题：当高持股候选与强语义控制候选并存时，当前排序、门槛和阻断逻辑是否能稳定选择真实 actual controller。

### 6.2 Public-float-like / dispersed ownership 候选处理

相关入口：

- `_controller_sort_key()`
- `_direct_candidate_sort_key()`
- `_controller_block_reason()`
- `_actual_control_evidence_block_reason()`
- `basis` 中的 top candidates 和 candidate status

研究问题：市场流通股、公众股、分散候选是否可能因比例或命名而被错误上位；当前代码是否有足够明确的 public float 识别与降权。

### 6.3 Actual gate 是否过严

相关入口：

- `_actual_control_evidence_block_reason()`
- `_score_reliability_signals()`
- `_score_disclosure_signals()`
- `_build_unified_basis_payload()`
- `control_relationships.terminal_failure_reason`

研究问题：低置信、来源弱、披露不足、protective rights 等是否导致强业务语义证据被过度阻断。

### 6.4 Promotion / rollup 对 governance-control 的适配

相关入口：

- `_promotable_rollup_company_candidate()`
- `_promotion_block_reason()`
- `_promotion_reason_for_entity()`
- `_resolve_country_attribution_type()`

研究问题：非股权强控制、董事会控制、协议控制、投票权控制、trust vehicle 是否应当像持股 holdco 一样上推，还是应保持直接控制人。

### 6.5 Nominee、beneficial owner、trust、joint control

相关入口：

- `_controller_block_reason()`
- `_promotion_block_reason()`
- `_joint_control_entity_ids()`
- `_resolve_controller_status()`
- `tests/test_trust_control_rules.py`
- `tests/test_ultimate_controller_dataset_regression.py`

研究问题：nominee 和 unknown beneficial owner 应该阻断到什么层级；family trust、state trust、nominee trust 的规则边界是否清晰；joint control 是否应该输出更多候选解释。

### 6.6 relationship_sources 对 reliability 的影响

相关入口：

- `_relationship_source_payloads()`
- `_load_relationship_source_map()`
- `_score_reliability_signals()`

研究问题：当前来源类型、文件日期、证据强度是否真正进入评分；未来如果接入更复杂 source reliability，应该从这里扩展。

## 7. 当前代码与旧材料容易不一致的点

1. 旧材料有时把 actual controller 和 ultimate controller 混用。当前代码和数据库同时保留 `is_actual_controller` 与 `is_ultimate_controller`，主流程解释应优先看 `is_actual_controller`，`is_ultimate_controller` 更多用于兼容和展示层。
2. 旧材料可能把 `relationship_sources` 当成纯辅助表。当前 unified engine 的 reliability scoring 已读取关系来源 payload，因此来源质量会影响证据强弱。
3. `country_attribution_analysis.py` 名字像分析核心，但当前实际是读取/包装层。国家归属核心推断和写回在 `control_inference.py` 与 `ownership_penetration.py` 中完成。
4. `ownership_penetration.py` 中保留 legacy engine，但默认主链路是 unified engine。做 Deep Research 时应优先研究 `control_inference.py`。
5. 前端存在 legacy control-chain diagram/adapters。排查当前主展示时，应优先看 `ControlStructureDiagram.vue` 和 `controlStructureAdapter.js`，再确认 legacy 是否仍被某个页面引用。
6. 部分历史脚本和文档可能存在编码或命名遗留，尤其是早期增强样本描述。研究样本导出已尽量改为稳定字段和说明，但 case ground truth 仍应回到测试、脚本和当前 DB 结果交叉验证。

## 8. 最小阅读建议

- 只想理解算法主干：`ownership_penetration.py` -> `control_inference.py` -> `control_relationship.py` -> `country_attribution.py`
- 只想排查某个公司为什么 fallback：`control_inference.py` 的 block reason 函数 -> `control_relationships.basis` -> `country_attributions.basis`
- 只想排查前端显示：`industry_analysis.py.get_company_analysis_summary()` -> `analysis.js` -> `CompanyAnalysisView.vue` -> `ControlSummaryCard.vue` / `ControlRelationsTable.vue`
- 只想写论文实现章节：先看本文档第 2、4、5 节，再结合 `docs/algorithm_typical_cases_guide.md` 的样本案例
- 只想做 Deep Research 提示词输入：重点复制第 2、4、5、6 节，并附上 `exports/research_samples/typical_control_cases.json`
