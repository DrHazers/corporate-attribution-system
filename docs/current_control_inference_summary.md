# 当前项目中的股权穿刺与实际控制人判定说明

本文档以当前代码实现为准，主要对应以下代码入口：

- `backend/analysis/control_inference.py`
- `backend/analysis/ownership_penetration.py`
- `backend/analysis/control_chain.py`

如果历史文档与本文不一致，以当前实现为准。尤其需要注意：当前默认 `disclosure_threshold` 已经与 `significant_threshold` 对齐为 `20%`，不再是旧口径中的 `25%`。

## 1. 先说结论：当前项目默认算法是什么

当前项目运行时默认使用的，并不是“只看股权比例连乘”的老版股权穿透，而是一个统一的控制推断引擎 `unified control inference`。

它的核心思想是：

1. 先把公司映射成股东图谱里的目标实体。
2. 从目标公司向上追溯所有可能的控制路径。
3. 对每一条路径同时计算：
   - 数值控制强度
   - 语义控制强度
   - 证据置信度
4. 再把同一个上游主体的多条路径合并，形成“控制候选人”。
5. 按阈值和竞争关系判断：
   - 是否能认定为实际控制人
   - 是否只能认定为共同控制
   - 是否只能给出 leading candidate
   - 是否根本没有明显控制信号

所以，项目里的“股权穿刺”现在已经扩展成“控制链分析”：
它不仅看股权，还会纳入协议控制、董事会控制、表决权安排、代持、VIE 等语义型控制关系。

## 2. 默认入口和运行方式

单家公司重算入口仍然在 `backend/analysis/ownership_penetration.py`：

- `refresh_company_control_analysis()`

但这个入口默认会走 unified 引擎：

- `_use_unified_control_engine()` 的默认返回逻辑是“不是 legacy 就用 unified”
- `_allow_legacy_fallback()` 当前直接返回 `False`

也就是说，当前默认主链路是：

1. `build_control_context()`
2. `infer_controllers()`
3. 将结果写回 `control_relationships` 和 `country_attributions`
4. 前端/接口再读取写回后的结果进行展示

只有显式把环境变量 `CONTROL_INFERENCE_ENGINE=legacy` 时，才会走旧版纯股权穿透逻辑。

## 3. 算法输入范围：系统实际会分析哪些边

统一控制推断引擎在构造上下文时，只会读取满足以下条件的 `shareholder_structures`：

- `is_current = 1`
- `is_direct = 1`
- `effective_date <= as_of` 或为空
- `expiry_date >= as_of` 或为空

这意味着系统默认只分析“当前有效、直接记录、时点有效”的控制边。

当前支持的关系类型包括：

- `equity`
- `agreement`
- `board_control`
- `voting_right`
- `nominee`
- `vie`

## 4. 每条边是怎么评分的

### 4.1 股权边

如果一条边是 `equity`，算法直接把持股比例归一化到 `0~1`，作为这条边的 `numeric_factor`。

例如：

- 60% 持股，对应 `numeric_factor = 0.6`
- 25% 持股，对应 `numeric_factor = 0.25`

股权边的 `semantic_factor` 默认是 `1`。

### 4.2 语义型控制边

如果是 `agreement`、`board_control`、`voting_right`、`nominee`、`vie`，算法会从以下信息里抽取控制强度：

- `control_basis`
- `agreement_scope`
- `nomination_rights`
- `remarks`
- `relation_metadata`
- `board_seats`

系统会根据关键词和结构化字段给出一个 `semantic_factor`，典型规则包括：

- 出现 joint control 相关措辞时，标记 `joint_control_candidate`
- 出现 protective rights / veto 之类保护性权利时，显著压低控制强度
- 出现“控制 relevant activities”“多数董事任命权”“super voting”等强控制信号时，提高语义控制分
- nominee / VIE 会综合“是否披露真实受益人”“是否同时具备权力和经济利益”等信号判断

可以把这一层理解成：算法在把“文本和元数据中的控制事实”转换成一个保守的语义控制分值。

### 4.3 置信度

每条边还有一个 `confidence_weight`，来源于 `confidence_level`：

- `high -> 0.9`
- `medium -> 0.7`
- `low -> 0.4`
- `unknown -> 0.6`

这个值不会直接充当控制分数，但会参与候选人排序和证据表达。

## 5. 股权穿刺 / 控制链是怎么向上追溯的

路径搜索函数是 `collect_control_paths()`。

它会从目标公司对应的实体开始，沿着“谁控制了当前节点”这条方向向上做 DFS，核心规则是：

1. 最多向上搜索 `10` 层
2. 用 `visited_entity_ids` 防止环路
3. 每扩展一条边，就把整条路径的三个量连乘：
   - `numeric_prod`
   - `semantic_prod`
   - `conf_prod`
4. 路径最终分数定义为：

`path_score = numeric_prod * semantic_prod`

5. 如果路径分数低于 `0.0001`，就直接剪枝

也就是说，当前项目的“穿刺”不是简单把所有边都当股权比例连乘，而是：

- 股权控制靠 `numeric_prod`
- 语义控制靠 `semantic_prod`
- 两者共同决定路径强度

## 6. 多条路径如何汇总成“控制候选人”

同一个上游主体可能通过多条路径影响目标公司。系统会把这些路径按上游实体分组，形成候选人，然后做聚合。

当前默认聚合器是：

- `sum_cap`

它的含义是：

1. 把同一主体的多条路径分数相加
2. 总分最高不超过 `1.0`

候选人最终会得到这些关键字段：

- `total_score`：总控制得分
- `total_confidence`：按路径分数加权后的总体置信度
- `control_mode`：`numeric` / `semantic` / `mixed`
- `semantic_flags`
- `top_paths`

## 7. 控制强度如何分层

候选人的 `control_level` 由 `_classify_control_level()` 判定，当前规则是：

1. 如果带有 `joint_control_candidate` 且总分 `>= 20%`，记为 `joint_control`
2. 否则如果总分 `>= 50%`，记为 `control`
3. 否则如果总分 `>= 20%`，记为 `significant_influence`
4. 否则记为 `weak_link`

这里的关键阈值是：

- `control_threshold = 50%`
- `significant_threshold = 20%`
- `disclosure_threshold = 20%`

其中 `disclosure_threshold` 表示：低于这个阈值的候选人，默认连结果集都不会进入。

## 8. 实际控制人到底是怎么判定出来的

这是最关键的一段。

`infer_controllers()` 的判定顺序可以概括为：

### 8.1 先产生候选人列表

所有路径汇总后，先筛出达到 `disclosure_threshold` 的候选人，再按以下顺序排序：

1. 优先普通 `control`
2. 再看 `joint_control`
3. 再看 `total_score` 高低
4. 再看 `total_confidence` 高低
5. 最后按实体 ID 稳定排序

### 8.2 然后区分三种情况

#### 情况 A：存在 joint control 候选人

如果控制候选人里存在 `joint_control`：

- `actual_controller_entity_id = None`
- `actual_control_country = "undetermined"`
- `attribution_type = "joint_control"`

也就是说，当前实现里“共同控制”不会再强行挑一个单一实控人。

#### 情况 B：存在普通 control 候选人

如果没有共同控制，但有普通 `control` 候选人：

- 取排序后的第一名作为 `actual_controller_entity_id`
- 它就是当前系统认定的实际控制人

这类情况最典型的就是：

- 直接或穿透后控制分数达到 50% 以上
- 且不存在优先级更高的共同控制判定

#### 情况 C：没有任何满足 control 的唯一赢家

如果候选人里没有能进入“实际控制人”判定的唯一控制者：

- `actual_controller_entity_id` 为空
- 系统仍可能保留一个 `leading_candidate_entity_id`

这时系统不会说“已经识别出实际控制人”，而是只保留“当前最领先的控制候选人”。

## 9. 没有实控人时，leading candidate 是怎么来的

只要候选人列表非空，系统就会把排序第一名记为 `leading_candidate_entity_id`。

随后用 `_classify_leading_candidate_signal()` 给它一个语义标签，当前包括：

- `absolute_control`
- `joint_control`
- `relative_control_candidate`
- `significant_influence_close_competition`
- `significant_influence_candidate`

这里的意思是：

- 有些公司虽然不能严谨认定“实际控制人”
- 但系统仍能指出“谁是目前最强的候选者”
- 同时说明它是强领先、相对控制、还是接近竞争状态

这也是为什么前端展示层必须把“actual controller”和“leading candidate”区分开，二者不是一回事。

## 10. 项目里“实际控制人”判断的答辩口径

如果你要用比较顺的中文解释，可以直接这么说：

> 我们当前不是只做传统股权穿透，而是做统一控制链推断。系统先从目标公司向上搜索所有有效控制路径，对每条路径同时计算股权数值强度和语义控制强度，再把同一上游主体的多条路径合并成候选人。如果某个候选人的综合控制分达到严格控制阈值，并且不存在共同控制冲突，就认定为实际控制人；如果只能说明某个主体最有可能控制，但证据还不足以形成唯一实控结论，就只标记为 leading candidate，而不会冒充成实际控制人。

再短一点的版本是：

> 实际控制人的判定不是看单条股权链，而是看所有有效控制路径汇总后的综合控制分，并结合共同控制、接近竞争和语义控制证据做最终判断。

## 11. 国家归属是怎么跟着实控人走的

当系统识别出实际控制人后，会进一步确定 `actual_control_country`：

1. 优先取控制主体实体本身的 `country`
2. 如果没有，就取该主体映射公司的 `incorporation_country`
3. 如果还没有，再回退到目标公司的 `incorporation_country`

如果是共同控制，则国家归属会记为：

- `undetermined`

如果根本没有满足阈值的控制候选人，则回退为：

- `fallback_incorporation`

## 12. 与旧版纯股权穿透逻辑的关系

项目里仍然保留了 legacy 逻辑，但它不是默认主路径。

旧版逻辑的特点是：

- 主要只看股权边
- 通过股权比例沿路径连乘
- 再根据比例大小判断主导候选人

而当前默认的 unified 逻辑比它多了三层能力：

1. 不只看股权，也看协议、表决权、董事会、代持、VIE
2. 不只看单条路径，也聚合同一主体的多条路径
3. 不只输出“有没有实控人”，还区分 leading candidate、joint control、no meaningful signal

所以现在更准确的表述应该是：

- “项目包含历史上的股权穿刺逻辑”
- “但当前运行时默认算法已经升级为统一控制链推断”

## 13. 当前实现里最值得记住的几个参数

当前默认常量如下：

- 最大搜索深度：`10`
- 最小路径分数：`0.0001`
- 严格控制阈值：`50%`
- 显著影响阈值：`20%`
- 结果披露阈值：`20%`
- 相对控制候选阈值：`35%`
- 相对控制领先差值阈值：`8%`
- 相对控制领先倍数阈值：`1.2`
- 接近竞争差值阈值：`5%`
- 接近竞争倍数阈值：`1.1`
- 聚合方式：`sum_cap`

## 14. 一句话总结

当前项目中“股权穿刺”的本质已经不是单纯的股权比例层层相乘，而是：

> 在有效控制图谱上，综合股权强度、协议/表决权/董事会等语义控制信号，以及多路径聚合结果，去判定是否存在唯一实际控制人；若不能唯一认定，则退化为共同控制、leading candidate 或无明显控制信号。
