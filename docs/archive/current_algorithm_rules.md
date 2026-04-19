# 当前算法规则说明文档

本文档基于当前仓库中的真实代码整理，目标是忠实还原“企业控制链 / 实际控制人识别 / 国别归属分析”当前到底如何工作。

本文不讨论未来方案，不做优化建议，只回答“现在代码实际上在做什么”。

## 1. 当前算法总体概述

当前仓库里并不是只有一套算法，而是同时存在两套分析逻辑：

| 逻辑 | 主要文件 | 当前状态 | 说明 |
| --- | --- | --- | --- |
| 旧版股权穿透逻辑 | `backend/analysis/ownership_penetration.py` 中 `build_ownership_analysis_context / _collect_candidate_paths / _prepare_candidate_results` | 仍保留 | 只处理股权边，本质是多层股权穿透 |
| 新版统一控制推断逻辑 | `backend/analysis/control_inference.py` | 默认启用 | 同时处理股权边和语义控制边，是当前默认运行时主引擎 |

当前默认运行时行为：

- `refresh_company_control_analysis()` 默认优先走新版统一控制推断引擎
- 只有当环境变量 `CONTROL_INFERENCE_ENGINE=legacy`，或者新版失败且允许回退时，才会走旧版股权逻辑

对应代码：

- 默认启用新版：`backend/analysis/ownership_penetration.py` 中 `_use_unified_control_engine()`
- 失败时是否允许回退：`backend/analysis/ownership_penetration.py` 中 `_allow_legacy_fallback()`

一句话概括当前默认运行时版本：

> 当前系统默认已经不是“只看直接股东”的分析器，而是“多层股权 + 协议/董事会/表决权/代持/VIE 语义边混合判别器”。

但需要特别强调两个现实边界：

1. 旧版股权逻辑还在仓库里，且部分批处理工具仍直接调用旧版逻辑  
2. 读接口很多时候只是“读取已写回数据库的结果”，不是每次现场实时重算

## 2. 调用链总览

### 2.1 核心算法入口

主要入口函数如下：

| 入口函数 | 文件 | 作用 |
| --- | --- | --- |
| `refresh_company_control_analysis()` | `backend/analysis/ownership_penetration.py` | 真正执行控制链分析、实际控制人识别、国别归属写回 |
| `analyze_control_chain_with_options()` | `backend/analysis/control_chain.py` | 对外控制链读取入口，可选 `refresh=True` |
| `analyze_country_attribution_with_options()` | `backend/analysis/country_attribution_analysis.py` | 对外国别归属读取入口，可选 `refresh=True` |
| `infer_controllers()` | `backend/analysis/control_inference.py` | 新版统一推断核心函数 |
| `_prepare_candidate_results()` | `backend/analysis/ownership_penetration.py` | 旧版股权穿透核心函数 |

### 2.2 从 `company_id` 到输出结果的主调用链

当前仓库真正以 `company_id` 作为算法输入。  
没有单独实现“直接以 `company_name` 调算法”的主入口；如果上层传入公司名，需要先自行查 `companies` 表拿到 `company_id`。

#### 路径 1：只读控制链结果

调用链：

1. `GET /analysis/control-chain/{company_id}`  
2. `backend/api/analysis.py -> get_control_chain_analysis()`  
3. `backend/analysis/control_chain.py -> analyze_control_chain_with_options()`  
4. 如果 `refresh=True` 且存在映射实体，则调用 `refresh_company_control_analysis()`  
5. 否则直接调用 `get_company_control_chain_data()` 读取结果表  
6. 返回 `actual_controller + control_relationships`

#### 路径 2：只读国别归属结果

调用链：

1. `GET /analysis/country-attribution/{company_id}`  
2. `backend/api/analysis.py -> get_country_attribution_analysis()`  
3. `backend/analysis/country_attribution_analysis.py -> analyze_country_attribution_with_options()`  
4. 其内部先调用 `analyze_control_chain_with_options()`  
5. 再读取 `country_attributions` 最新一条记录  
6. 返回 `country_attribution + control_chain_basis`

#### 路径 3：显式重算

调用链：

1. `POST /companies/{company_id}/analysis/refresh`  
2. `backend/api/company.py -> refresh_company_analysis_endpoint()`  
3. `backend/api/company.py -> refresh_company_analysis_or_400()`  
4. `backend/analysis/ownership_penetration.py -> refresh_company_control_analysis()`  
5. 默认走新版：
6. `build_control_context()`  
7. `infer_controllers()`  
8. `_apply_unified_company_analysis_records()`  
9. 写回 `control_relationships / country_attributions`

如果新版失败且允许回退，则调用：

1. `build_ownership_analysis_context()`  
2. `_prepare_candidate_results()`  
3. `_apply_company_analysis_records()`

### 2.3 读接口与写接口的区别

当前系统的一个非常重要的现实特征是：

- `/analysis/...` 和 `/companies/{id}/control-chain` 这类 GET 接口默认不重算
- 它们主要是读取数据库中已经存在的 `control_relationships / country_attributions`
- 只有显式 `refresh=true` 或显式调用 refresh 接口时，才会触发重算

这点在 `tests/test_control_chain_generation_api.py` 中有明确断言。

### 2.4 可视化调用链

控制链图不是算法入口，而是结果展示层：

1. `backend/visualization/control_graph.py -> build_control_graph_with_session()`  
2. `_build_analysis_context()`  
3. `analyze_control_chain_with_options(refresh=False)`  
4. `analyze_country_attribution_with_options(refresh=False)`  
5. 再结合 `shareholder_structures` 当前边，生成 NetworkX / PyVis HTML

也就是说：

- 图默认读取预计算结果
- 图本身不负责判别 actual controller
- 图只是把结果高亮出来

## 3. 数据依赖与关键字段

### 3.1 核心依赖表

| 表 | 作用 | 是否直接参与判别 |
| --- | --- | --- |
| `companies` | 公司主表 | 是 |
| `shareholder_entities` | 图中的主体节点 | 是 |
| `shareholder_structures` | 股权/控制边 | 是 |
| `control_relationships` | 分析结果表 | 是，读接口直接依赖 |
| `country_attributions` | 国别归属结果表 | 是，读接口直接依赖 |
| `relationship_sources` | 来源证据 | 否，目前不参与打分 |
| `entity_aliases` | 别名 | 否，目前不参与打分 |
| `shareholder_structure_history` | 结构变更历史 | 否，目前不参与打分 |

### 3.2 `companies` 中真正影响结果的字段

| 字段 | 当前作用 |
| --- | --- |
| `id` | 主键，算法输入 |
| `incorporation_country` | 无实控人时 fallback 归属国家；控制人国家缺失时也会作为后备 |
| `listing_country` | 只会被复制写入结果表，目前不参与归属判定 |
| `name` | 展示用，不参与打分 |
| `stock_code` | 不参与打分 |
| `headquarters` | 当前未参与归属判定 |
| `description` | 当前未参与判定 |

结论：

- 当前国别归属 fallback 只真正用到了 `incorporation_country`
- `listing_country` 和 `headquarters` 目前没有进入决策链

### 3.3 `shareholder_entities` 中真正影响结果的字段

| 字段 | 当前作用 |
| --- | --- |
| `id` | 图节点主键 |
| `company_id` | 用来把 `companies` 映射到目标实体；没有它就无法从公司进入控制图 |
| `country` | 实际控制人国家优先取这个字段 |
| `entity_type` | 会写回 `controller_type`，但不直接参与控制得分 |
| `entity_name` | 展示、路径、证据摘要 |
| `identifier_code` | 未参与判别 |
| `is_listed` | 未参与判别 |
| `notes` | 未参与判别 |

特别重要：

- 每个待分析公司必须能在 `shareholder_entities` 里找到一条 `company_id = companies.id` 的映射实体
- 没有映射实体时，重算会报错或被 API 拒绝

这点在 `tests/test_entity_mapping.py` 和 `backend/crud/shareholder.py -> get_entity_by_company_id()` 中有体现。

### 3.4 `shareholder_structures` 中真正影响结果的字段

#### 当前新版统一引擎真正使用的字段

| 字段 | 是否参与判别 | 用途 |
| --- | --- | --- |
| `from_entity_id` | 是 | 上游节点 |
| `to_entity_id` | 是 | 下游节点 |
| `holding_ratio` | 是 | 股权边数值因子 |
| `is_direct` | 是 | 新旧两套分析引擎都只吃直接边 |
| `is_current` | 是 | 过滤失效边 |
| `effective_date` | 是 | 时间有效性过滤 |
| `expiry_date` | 是 | 时间有效性过滤 |
| `relation_type` | 是 | 决定按股权还是按语义控制处理 |
| `control_type` | 是 | 当 `relation_type` 缺失时用于推断关系类型 |
| `relation_metadata` | 是 | 提供 `voting_ratio / effective_voting_ratio / total_board_seats / legacy_ratio_proxy` 等 |
| `control_basis` | 是 | 协议、董事会、VIE、代持等文本证据 |
| `agreement_scope` | 是 | 协议/VIE/表决权文本证据 |
| `board_seats` | 是 | 董事会控制因子 |
| `nomination_rights` | 是 | 董事会控制文本证据 |
| `confidence_level` | 是 | 转换成 `confidence_weight` |
| `relation_priority` | 是 | 影响边遍历优先级 |
| `remarks` | 是 | 关系类型补推断、文本证据、兼容旧数据 |

#### 当前新版统一引擎读取但不实质参与打分的字段

| 字段 | 当前状态 |
| --- | --- |
| `has_numeric_ratio` | 查询时会取出，但新版打分并不依赖它 |
| `relation_role` | 用于输出和展示，不直接决定得分 |
| `reporting_period` | 当前不参与判别 |
| `source` | 当前不参与判别 |

#### 当前旧版股权引擎真正使用的字段

旧版逻辑只会使用：

- `from_entity_id`
- `to_entity_id`
- `holding_ratio`
- `is_direct`
- `is_current`
- `effective_date`
- `expiry_date`
- `relation_type / control_type / holding_ratio`  
  这里只用于判断“这是不是股权边”

旧版逻辑不会使用：

- `control_basis`
- `agreement_scope`
- `board_seats`
- `nomination_rights`
- `relation_metadata`
- `confidence_level`

### 3.5 `control_relationships` 和 `country_attributions` 对最终读结果的影响

读接口不是重新计算，而是直接读取这两张表，所以它们本身也会影响“最终看到的结果”。

#### `control_relationships`

真正参与读接口输出的字段：

- `company_id`
- `controller_entity_id`
- `controller_name`
- `controller_type`
- `control_type`
- `control_ratio`
- `control_path`
- `is_actual_controller`
- `basis`
- `control_mode`
- `semantic_flags`
- `review_status`

`analyze_control_chain_with_options()` 中的 `actual_controller` 是通过：

- 读取所有 `control_relationships`
- 找到第一条 `is_actual_controller = True` 的记录

来得到的。

#### `country_attributions`

真正参与读接口输出的字段：

- `company_id`
- `actual_control_country`
- `attribution_type`
- `basis`
- `source_mode`
- `is_manual`

`analyze_country_attribution_with_options()` 会按 `id desc` 读取最新一条记录。

这意味着：

- 如果有人手工插入了一条更新的 `country_attributions`
- 读接口会优先返回这条最新记录
- 并不会重新校验它是否和当前控制链一致

### 3.6 输入归一化与启动期 backfill

当前代码在两个地方会自动修正旧数据：

#### 创建/更新 `shareholder_structures` 时

`backend/shareholder_relations.py -> prepare_shareholder_structure_values()`

会自动做这些事：

- 如果 `relation_type` 缺失，则优先从 `relation_type -> remarks -> control_type -> holding_ratio` 推断
- 如果 `holding_ratio` 存在，则可自动推成 `equity`
- 自动补 `has_numeric_ratio`
- 自动补 `relation_role`
- 非股权边如果 `control_basis` 缺失，会用 `remarks` 回填
- `board_control` 边如果 `nomination_rights` 缺失，会用 `remarks` 回填
- `agreement / vie / voting_right` 边如果 `agreement_scope` 缺失，会用 `remarks` 回填
- `confidence_level` 缺失会默认成 `unknown`

#### 应用启动时

`backend/main.py -> on_startup() -> backend/database.py -> init_db() -> ensure_sqlite_schema()`

会自动：

- 给老库补列
- 给老数据回填 `relation_type / has_numeric_ratio / relation_role / control_basis / nomination_rights / agreement_scope / confidence_level`
- 给 `control_relationships` 回填 `control_mode / review_status`
- 给 `country_attributions` 回填 `source_mode`

这意味着旧数据库即使不是完全新结构，也会在启动时被“尽量修补到当前算法能读”的状态。

## 4. 股权穿透规则

### 4.1 是否支持多层穿透

支持。

默认深度：

- 新版统一引擎：`max_depth = 10`
- 旧版股权引擎：`max_depth = 10`

### 4.2 路径是怎么找的

#### 新版统一引擎

文件：

- `backend/analysis/control_inference.py -> collect_control_paths()`

方法：

- 从目标实体开始
- 沿 `incoming_factor_map` 向上 DFS
- 每走一条边，把边对应的 `numeric_factor / semantic_factor / confidence_weight` 乘入路径状态
- 用 `visited_entity_ids` 去环

#### 旧版股权引擎

文件：

- `backend/analysis/ownership_penetration.py -> _collect_candidate_paths()`

方法：

- 从目标实体开始
- 沿 `incoming_map` 向上 DFS
- 每条边只按 `holding_ratio` 连乘
- 用 `visited_entity_ids` 去环

### 4.3 单条股权路径的比例怎么计算

#### 旧版

路径比例：

- `当前路径比例 = 上一路径比例 × 当前边 holding_ratio / 100`

例如：

- A -> B = 80%
- B -> C = 40%

则 A 对 C 的单条路径比例 = `0.8 × 0.4 = 0.32 = 32%`

#### 新版

股权边会被转成：

- `numeric_factor = holding_ratio`
- `semantic_factor = 1`

如果路径全是股权边：

- `path_score = numeric_prod × semantic_prod = numeric_prod`

所以在纯股权场景下，新版和旧版的股权路径分数本质一致。

### 4.4 多条路径如何合并

#### 旧版

- 同一候选控制人如果有多条路径，路径比例直接求和
- 最后总比例封顶到 `100%`

#### 新版

- 同一候选控制人如果有多条路径，先求每条路径的 `path_score`
- 再调用聚合器
- 当前实际写回流程固定使用 `sum_cap`
- `sum_cap` 的含义是：路径分数求和后封顶到 `1.0`

代码：

- 聚合器定义：`backend/analysis/control_inference.py -> aggregate_scores_sum_cap()`
- 当前 refresh 硬编码使用：`backend/analysis/ownership_penetration.py -> _refresh_company_control_analysis_with_unified_context()`

仓库里虽然还提供了 `noisy_or` 聚合器，但当前正常 refresh 流程没有使用它。

### 4.5 有哪些有效边过滤条件

新旧两套分析引擎都会过滤：

- `is_current = 1`
- `is_direct = 1`
- `effective_date <= as_of`
- `expiry_date >= as_of`

这点在：

- `backend/analysis/control_inference.py -> build_control_context()`
- `backend/analysis/ownership_penetration.py -> _load_eligible_edges()`

都有体现。

### 4.6 剪枝、去环、去重

#### 去环

支持，通过 `visited_entity_ids` 完成。

#### 最大深度

支持，默认 10 层。

#### 剪枝

支持。

旧版：

- 如果当前路径比例 `< min_path_ratio_pct`，直接剪枝
- 默认 `min_path_ratio_pct = 0.01`

新版：

- 如果当前 `path_score < min_path_score`，直接剪枝
- 默认 `min_path_score = 0.0001`
- 对应百分比也是 `0.01%`

#### 去重

没有单独的“路径去重”结构。

当前实现更接近：

- 通过 DFS + 去环来避免明显重复循环
- 同一候选人的多条合法路径全部保留
- 聚合时统一累计

### 4.7 哪些情况会直接跳过某条边

#### 旧版会跳过

- 非股权边
- `holding_ratio <= 0`
- 无效日期边
- `is_direct = 0`
- `is_current = 0`

#### 新版会跳过

- `relation_type` 不在支持集合里
- 股权边但 `holding_ratio <= 0`
- 路径分数过低
- 会造成环路的边
- 无效日期边
- `is_direct = 0`
- `is_current = 0`

## 5. 非股权控制规则

### 5.1 当前被识别为非股权控制的类型

新版统一引擎支持这些非股权关系：

- `agreement`
- `board_control`
- `voting_right`
- `nominee`
- `vie`

代码位置：

- `backend/analysis/control_inference.py -> SUPPORTED_RELATION_TYPES`

### 5.2 这些控制关系是“真参与计算”还是“只做说明”

它们在新版统一引擎里是真参与计算的，不只是说明信息。

参与方式是：

- 每条非股权边被转换为一个 `semantic_factor`
- 路径总分 = `numeric_prod × semantic_prod`
- 候选人总分再按多路径聚合

也就是说：

- 它不是“强制直接判定”
- 也不是“仅展示标签”
- 而是作为路径得分中的语义因子参与乘法和阈值比较

### 5.3 各类非股权控制的当前处理方式

#### `board_control`

规则：

- 如果 `board_seats` 和董事会总席位都能拿到，则直接按席位比计算
- 如果只能看见“可提名多数董事”这类关键词，则保守给 `0.55`
- 如果只有席位数、没有总席位，则保守估算且封顶 `< 0.49`
- 否则默认 `0.35`
- 大多数不完全信息场景会打 `needs_review`

#### `agreement`

规则：

- 默认起点分值 `0.15`
- 如果是保护性权利，降到 `0.05`
- 如果有 joint control 关键词，至少 `0.50`
- 如果出现强控制关键词，或同时出现 power + economics 关键词，可直接抬到 `1.0`
- 如果 `relation_metadata` 中有 `voting_ratio`，会取较大值
- 如果文本里能抽出比例，也会取较大值
- 如果只有弱证据，则保留为较低分并打 `needs_review`

#### `voting_right`

规则：

- 默认起点分值 `0.18`
- 如果是保护性表决权，直接降到 `0.05`
- 若有效表决权比例 `>= 50%`，直接按比例
- 若低于 50%，会做一个放大但保守封顶
- `super-voting / founder block / acting in concert` 等强关键词会进一步抬高
- `full voting control / controlling voting rights` 可直接拉到 `1.0`

注意：

- 输出分类里没有单独的 `voting_right_control`
- 当前会被归入 `agreement_control` 或 `mixed_control`，具体看路径模式
- `voting_right` 更像是语义标签和打分来源，而不是最终单独类型

#### `nominee`

规则：

- 默认会带上 `beneficial_owner_candidate`
- 如果 `beneficial_owner_disclosed + explicit control` 同时成立，可到 `0.85`
- 只有披露或只有强控制表述时，中高分
- 只有 nominee/custodian 指示而无强证据时，分值较低并打 `needs_review`

注意：

- 输出分类里也没有单独的 `nominee_control`
- 最终仍会归入 `agreement_control / mixed_control / significant_influence`

#### `vie`

规则：

- 如果同时出现 power 权利和 economic benefits，分值 `0.90`
- 只有 power 或只有 economics，则 `0.45 + needs_review`
- 只有非常弱的 proxy 信息，则按 `legacy_ratio_proxy` 给低分
- 保护性权利降到 `0.08`

同样：

- 输出分类没有单独 `vie_control`
- 会归到 `agreement_control / mixed_control / significant_influence`

### 5.4 哪些部分只是“已建模，但未真正参与最终分类”

以下内容虽然进入了语义打分，但在最终输出分类上没有单独类型：

- `voting_right`
- `nominee`
- `vie`

它们会体现在：

- `semantic_flags`
- `control_path.edges[].relation_type`
- `basis.evidence_summary`

但最终 `control_type / attribution_type` 通常会被折叠成：

- `agreement_control`
- `mixed_control`
- `significant_influence`
- `joint_control`

## 6. 实际控制人判别规则

### 6.1 当前默认运行时是谁会被认定为 `actual controller`

#### 新版统一引擎

步骤如下：

1. 找到所有上游候选人及其路径
2. 聚合每个候选人的总分
3. 先过滤掉低于 `disclosure_threshold` 的候选人
4. 对剩余候选人判定 `control_level`
5. 只从 `control / joint_control` 候选里挑实际控制结果

默认阈值：

- `control_threshold = 0.5`
- `significant_threshold = 0.2`
- `disclosure_threshold = 0.25`

注意一个现实细节：

- 因为默认 `disclosure_threshold = 0.25`
- 所以虽然代码里有 `significant_threshold = 0.2`
- 但在默认 refresh 流程里，`20%-25%` 的候选人其实会先被过滤掉，不会落库

### 6.2 `control_level` 的判定

当前规则：

- 如果有 `joint_control_candidate` 且总分 `>= 0.2`，判为 `joint_control`
- 否则总分 `>= 0.5`，判为 `control`
- 否则总分 `>= 0.2`，判为 `significant_influence`
- 否则为 `weak_link`

### 6.3 实际控制人如何选出

#### 新版统一引擎

当前实现不是递归地“先找 A 的实控人，再替换掉 A”，而是：

- 把所有上游实体都当作“对目标公司直接打分的候选人”
- 谁对目标公司的总控制分数最高且达到 `control`，谁就是 winner

如果存在 joint control 候选：

- 不会选唯一 actual controller
- `actual_controller_entity_id = None`
- `actual_control_country = undetermined`
- `attribution_type = joint_control`

如果存在普通 control 候选且没有 joint：

- 取排序后的第一个 control 候选为 actual controller

排序规则大致是：

- `control` 候选优先
- 然后按总分降序
- 然后按总置信度降序
- 然后按 `controller_entity_id`

### 6.4 如果股权和协议冲突，当前倾向选谁

当前没有写死“股权优先”或“协议优先”。

默认规则是：

- 谁的总控制分数更高，谁赢
- 纯股权候选、纯协议候选、董事会候选、混合候选都在同一候选池里比较

所以：

- 强协议控制可以战胜弱股权
- 强董事会控制可以战胜弱股权
- 混合路径也可能战胜单一路径

这是分数驱动，不是类型硬编码优先。

### 6.5 如果没有明确控制人怎么办

当前 fallback 是：

- `actual_controller_entity_id = None`
- `actual_control_country = company.incorporation_country`
- `attribution_type = fallback_incorporation`

### 6.6 是否支持多个实际控制人

自动算法层面：

- 不支持输出多个 `is_actual_controller = True` 的实体
- `joint_control` 场景下反而是不输出唯一 actual controller

读接口层面：

- `GET /companies/{id}/actual-controller` 会返回所有 `is_actual_controller = True` 的行
- 如果有人手工写入多条 `is_actual_controller = True`，这个接口可以返回多条
- 但 `analyze_control_chain_with_options()` 里的 `actual_controller` 便利字段只会取第一条

也就是说：

- 自动算法：单一 actual controller 或无唯一 actual controller
- 手工数据：理论上可以出现多条 actual rows

## 7. 国别归属判别规则

### 7.1 当前国别归属的主规则

#### 新版统一引擎

优先顺序如下：

1. 如果是 `joint_control`
   - `actual_control_country = undetermined`
   - `attribution_type = joint_control`
2. 如果有唯一 actual controller
   - 先取 `controller_entity.country`
   - 如果没有，再看该实体映射公司 `company.incorporation_country`
   - 如果还没有，再 fallback 到目标公司 `incorporation_country`
3. 如果没有控制人
   - 直接 fallback 到目标公司 `incorporation_country`

### 7.2 当前没有实现的 fallback

当前没有按以下顺序做 fallback：

- 上市地优先
- 总部地优先
- 注册地、上市地、总部地综合加权

现实上目前只真正用：

- `controller_entity.country`
- `controller_entity.company.incorporation_country`
- `company.incorporation_country`

### 7.3 `attribution_type` 如何赋值

#### 新版统一引擎

规则：

- `joint_control` -> `joint_control`
- 纯 numeric -> `equity_control`
- mixed -> `mixed_control`
- 纯 semantic 且语义标记里含 `board_control` -> `board_control`
- 其他纯 semantic -> `agreement_control`
- 没有控制人 -> `fallback_incorporation`

#### 旧版股权引擎

只有：

- `equity_control`
- `fallback_incorporation`

### 7.4 `basis` 里目前实际记录了什么

#### 新版统一引擎

当前 `country_attributions.basis` 会记录：

- `analysis = unified_control_inference_v1`
- `aggregator`
- `as_of`
- `classification / attribution_type`
- `actual_control_country`
- `actual_controller_entity_id`
- `joint_controller_entity_ids`
- `semantic_flags`
- `top_paths`
- `evidence_summary`
- `total_confidence`
- `total_score / total_score_pct`
- `top_candidates`

#### 旧版股权引擎

`basis` 只会有较简化的信息：

- `analysis = ownership_penetration`
- `aggregator`
- `as_of`
- `classification / attribution_type`
- `actual_control_country`
- `actual_controller_entity_id`
- `top_paths`
- `total_score / total_score_pct`

### 7.5 国别结果读取层的现实行为

`analyze_country_attribution_with_options()` 并不会自己重跑逻辑去验证 `country_attributions` 对不对，它只是：

1. 先读控制链结果
2. 再拿 `country_attributions` 最新一条
3. 拼成输出

这意味着：

- 如果数据库里已有人工修改过的 `country_attributions`
- 读接口会直接返回该记录

## 8. 结果输出与回写机制

### 8.1 控制链结果最终返回什么结构

#### `get_company_control_chain_data()`

返回：

- `company_id`
- `controller_count`
- `control_relationships`

每条 `control_relationships` 包含：

- `controller_name / controller_type`
- `control_type`
- `control_ratio`
- `control_path`
- `is_actual_controller`
- `basis`
- `control_mode`
- `semantic_flags`
- `review_status`

#### `analyze_control_chain_with_options()`

在上面的基础上额外补：

- `actual_controller`

这个字段只是一个便利字段，不是单独重新计算。

### 8.2 会不会写入结果表

会。

真正重算入口 `refresh_company_control_analysis()` 会写入：

- `control_relationships`
- `country_attributions`

### 8.3 写回时写哪些字段

#### `control_relationships`

统一引擎写入：

- `company_id`
- `controller_entity_id`
- `controller_name`
- `controller_type`
- `control_type`
- `control_ratio`
- `control_path`
- `is_actual_controller`
- `basis`
- `notes = AUTO: generated by ownership penetration`
- `control_mode`
- `semantic_flags`
- `review_status`

#### `country_attributions`

统一引擎写入：

- `company_id`
- `incorporation_country`
- `listing_country`
- `actual_control_country`
- `attribution_type`
- `basis`
- `is_manual = False`
- `notes = AUTO: generated by ownership penetration`
- `source_mode`

### 8.4 是否支持覆盖更新

支持，但方式是“删旧自动结果，再插新结果”。

普通 refresh 的删除规则：

- 删除该公司下 `notes LIKE 'AUTO:%'` 的旧 `control_relationships`
- 删除该公司下 `notes LIKE 'AUTO:%'` 的旧 `country_attributions`

然后重新插入新结果。

这意味着：

- 自动结果是覆盖式更新
- 不是增量 merge

### 8.5 是否支持历史留痕

#### 对 `shareholder_structures`

支持。

- 创建/更新结构边时，会写 `shareholder_structure_history`

#### 对分析结果表

普通 refresh 不支持真正的历史版本留痕。

当前只有：

- `created_at / updated_at`
- `notes`
- `basis`

旧自动结果会被删掉，不会单独保留历史记录表。

### 8.6 批量重算任务的特殊留痕

`backend/tasks/recompute_analysis_results.py` 是一个单独的批处理工具，它和普通 refresh 不一样。

它会：

- 先做数据库备份
- 区分 auto/manual/uncertain 结果
- 只删除 auto 结果
- 对 manual 或 uncertain 结果所在公司跳过写回
- 写带 `recompute_run=...` 的 notes 和 audit basis
- 生成 markdown 报告

但是要特别注意：

这个批处理工具当前调用的是旧版股权逻辑：

- `build_ownership_analysis_context()`
- `_prepare_candidate_results()`

而不是新版统一控制推断逻辑。

这是当前仓库一个非常明确的“逻辑不统一点”。

### 8.7 可视化层对结果的使用方式

`backend/visualization/control_graph.py` 的行为是：

- 调用 `analyze_control_chain_with_options(refresh=False)`
- 调用 `analyze_country_attribution_with_options(refresh=False)`
- 再去数据库里加载当前上游边来画图

重点：

- 图层默认不重算
- 图层只是读取已有结果并高亮

另外还有一个很重要的现实差异：

- 分析引擎会过滤 `is_direct = 1`
- `control_graph.py` 和 `ownership_graph.py` 当前图构建层只按 `is_current + 日期有效` 过滤，并没有强制过滤 `is_direct`

也就是说：

- 算法层看到的边集，和图层可能并不完全一致
- 如果库里存在 `is_direct = 0` 的边，图层有可能画出来，但算法不会拿它做控制判断

## 9. 当前实现边界与未完成部分

### 9.1 已真正实现并生效的规则

当前默认运行时已经真正实现并生效的能力：

- 多层股权穿透
- 多条路径累计后再判断控制
- 日期有效性过滤
- 去环和最大深度限制
- 协议控制、董事会控制、表决权控制、代持、VIE 的语义打分
- mixed control 判定
- joint control 判定
- actual controller 识别
- 国别归属输出
- 结果写回 `control_relationships / country_attributions`
- 基于预计算结果生成控制链图

### 9.2 已有表结构但还没真正用起来的部分

这些字段或表当前更多是“存着”，没有进入核心判别：

- `companies.headquarters`
- `companies.description`
- `companies.stock_code`
- `shareholder_entities.identifier_code`
- `shareholder_entities.is_listed`
- `shareholder_entities.notes`
- `shareholder_structures.reporting_period`
- `shareholder_structures.source`
- `shareholder_structures.has_numeric_ratio`
- `relationship_sources`
- `entity_aliases`
- `shareholder_structure_history`

### 9.3 看起来像支持，但实际上只是部分支持或占位的部分

#### `company_name` 作为算法主入口

未实现。

当前核心分析都是围绕 `company_id`。

#### `listing_country / headquarters` 参与 fallback

未实现。

当前归属 fallback 实际上只用 `incorporation_country`。

#### `voting_right / nominee / vie` 作为独立最终分类

未实现。

它们参与打分，但最终分类会折叠进：

- `agreement_control`
- `mixed_control`
- `significant_influence`

#### 多实际控制人同时输出

自动逻辑未实现。

joint control 只会输出：

- 无唯一 actual controller
- `actual_control_country = undetermined`

### 9.4 当前仓库中的规则冲突点

#### 冲突点 1：默认运行时是新版统一引擎，但批量重算工具仍用旧版股权逻辑

表现：

- `refresh_company_control_analysis()` 默认走 `infer_controllers()`
- `backend/tasks/recompute_analysis_results.py` 仍调用 `_prepare_candidate_results()`

结果：

- 平时单公司 refresh 与批量 recompute 的判别口径不完全一致

#### 冲突点 2：分析层只吃直接边，但图层可能展示所有当前边

表现：

- 分析层：`is_direct = 1`
- 图层：当前实现未统一强制过滤 `is_direct`

结果：

- 图中链路可能比算法真正参与计算的边更多

#### 冲突点 3：API 读层默认信任结果表，而不重新验证

表现：

- `/analysis/control-chain` 默认只读 `control_relationships`
- `/analysis/country-attribution` 默认只读最新 `country_attributions`

结果：

- 如果数据库里存在人工写入或旧格式结果，读接口会直接返回它们
- 不保证一定是“刚算出来的”

#### 冲突点 4：结果类型在 schema 层不是强枚举

表现：

- `ControlRelationship.control_type` 在 schema 里是自由字符串
- `CountryAttribution.attribution_type` 在 schema 里也是自由字符串

结果：

- 手工 CRUD 可以写入 `direct / manual / mixed_test / legacy_auto_country` 等非标准值
- 读层只会对部分旧值做 canonicalize，不会全面校验

### 9.5 当前版本最准确的一句话总结

> 当前默认运行时最准确的定位是：一个“多层股权穿透 + 语义控制边混合判别”的控制链分析器，并且已经能输出实际控制人与国别归属；但仓库内仍并存旧版股权逻辑，部分批处理工具尚未统一到新版规则。

## 10. 一页式总结

### 10.1 当前算法最核心的判别标准

当前默认运行时的核心标准是：

- 沿股权边和语义控制边向上找路径
- 对每条路径计算控制分数
- 对同一候选人的多条路径做 `sum_cap` 聚合
- 总分 `>= 50%` 判为 `control`
- 总分 `>= 25%` 才会进入默认落库候选集
- 如果出现 joint control 语义，则优先转成 `joint_control`

### 10.2 当前算法更偏股权还是更偏协议

现实上：

- 默认仍然是“分数驱动”
- 不是单纯股权优先
- 也不是协议绝对优先

但从实现成熟度上看：

- 股权路径是最稳定、最直接、最完整的部分
- 非股权控制已经真实参与计算，但很多仍依赖关键词和启发式因子

所以可以说：

> 当前系统已经不是纯股权算法，但整体成熟度仍然是“股权规则最稳定，语义控制规则次之”。

### 10.3 当前是否足够支撑“输入公司 -> 展示股权链路图 -> 输出实际控制与国别归属”

答案是：

- 可以支撑

但要加一个现实前提：

- 最好走“先 refresh 写回结果，再读取结果表和 HTML 展示”的流程

在这个前提下，当前仓库已经具备：

- 输入 `company_id`
- 重算控制链
- 生成 `control_relationships`
- 生成 `country_attributions`
- 读取结果
- 生成控制链可视化 HTML

### 10.4 当前最需要警惕的三件事

1. 默认读接口并不自动重算，很多时候只是读库里旧结果  
2. 批量重算工具与默认运行时引擎并不完全一致  
3. 图层看到的边不一定等于分析层真正参与计算的边
