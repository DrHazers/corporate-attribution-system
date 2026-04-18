# Ultimate Controller 算法通俗说明

## 先说这份文档是干什么的

这不是论文版，也不是对外汇报版。

这份文档是给项目内部自己看的，目标只有一个：

> 把当前已经基本冻结的 ultimate controller 主版本算法，用“能看懂、能复核、能对照代码和数据库”的方式讲清楚。

所以这份文档会尽量做到三件事：

1. 先讲算法到底想解决什么问题；
2. 再讲数据库里哪些输入字段真的在影响判断；
3. 最后用真实样本把“为什么识别出来 / 为什么被阻断”讲透。

当前说明主要对应这两块代码：

- `backend/analysis/control_inference.py`
- `backend/analysis/ownership_penetration.py`

同时结合了当前冻结主版本的验证结果：

- 小规模测试库关键样本回归通过；
- 增强验证库 `10030` 全量 refresh 可跑通；
- `235` 个重点目标回归当前全绿。

---

## 第 1 部分：算法总体目标

### 1.1 这套算法到底想解决什么问题

这套算法要解决的，不是“股东表里谁名字排第一”，而是：

> 对某一家公司，系统应该给出谁是**直接控制人**，谁是**最终/实际控制人**，以及在什么情况下应该保守地不下结论。

这里的“控制”不是单一概念。现实里一家公司可能出现这些情况：

- 某个主体直接持股超过 50%，一眼看上去就像控制人；
- 某个主体本身只是一个 holding company，它背后还有更上层的 parent；
- 某个人不一定持股最多，但通过董事会任命权、协议控制、VIE、投票权委托等方式在控制公司；
- 表面上看有一个大股东，但其实背后是 nominee，真正受益人没有披露；
- 上层是两个并列主体共同控制，这时候算法不应该硬给一个唯一的 actual controller。

所以算法做的事情，本质上是：

- 从公司出发建立一个“控制图”；
- 计算每条边的控制强度和可信度；
- 先判断谁是 direct controller；
- 再判断要不要继续向上 rollup 成 ultimate / actual controller；
- 如果证据不够、存在结构性阻断、或竞争太接近，就停下来，用 leading candidate 或 fallback 表示“目前只能保守到这里”。

### 1.2 为什么不能只看“谁持股最多”

因为“持股最多”在很多情况下并不等于“实际控制”。

举几个项目里真实会遇到的情况：

- **holding company 中间层**：一个控股平台直接持有 58%，但它本身又被上层母集团 82% 控制。只看目标公司的直接持股，你会停在中间层；但项目算法要继续向上看。
- **board control / voting right**：一个主体可能股权不高，但能任命多数董事、控制预算和重大事项。
- **VIE / agreement**：控制不一定来自股权，也可能来自协议安排、独家经营权、投票代理、收益权和 relevant activities 的控制。
- **nominee / beneficial owner unknown**：表面持股人可能只是代持载体，如果真正受益人不清楚，算法宁愿保守，也不会直接把 nominee 当成 actual controller。
- **joint control / close competition**：可能出现两个上层主体都很强，这时候“谁排第一”不能直接当作结论。

所以这套算法不是“排序器”，而是“带阻断规则的控制权推理器”。

### 1.3 为什么要区分 direct controller 和 ultimate / actual controller

这两个概念在项目里是故意分开的。

**direct controller** 解决的是：

- 眼前这一层，直接控制公司的人/主体是谁？

**ultimate / actual controller** 解决的是：

- 如果继续沿着控制链往上看，最应该作为终局控制人的主体是谁？

这两个值有时候相同，有时候不同：

- `2001` 这种普通股权控制，direct = ultimate；
- `2004` 这种 holding company 场景，direct 是中间层，ultimate 是上层 parent；
- `2023` / `2024` 这种 mixed / VIE 场景，direct 是控制平台/WFOE，ultimate 是背后的人；
- `2007` 这种 joint control 场景，direct 可以成立，但 ultimate 不应该强行给出。

### 1.4 为什么有时不会直接给 actual controller，而只保留 leading candidate 或 fallback

因为这套算法不是“强行猜一个”，而是“只在证据够的时候输出 actual controller”。

当前主版本里，常见的停下原因有：

- `joint_control`：不是一个人控制，而是共同控制；
- `beneficial_owner_unknown`：真正受益控制人没披露；
- `nominee_without_disclosure`：名义持有人不能被直接当成 actual controller；
- `low_confidence_evidence_weak`：虽然看起来像控制，但证据可靠性太低；
- `insufficient_evidence`：整体证据不够；
- `close_competition`：两个强候选人太接近，强行给一个会过于激进。

这时候系统会保留：

- `leading_candidate`：目前最像控制人的那个候选；
- 或者直接回落到 `fallback_incorporation`：只给出注册地归属，不给唯一 actual controller。

这正是当前主版本比较重要的一点：**宁可保守，也不乱认。**

---

## 第 2 部分：数据库输入表与关键字段

当前主版本算法主要依赖三张输入表：

- `companies`
- `shareholder_entities`
- `shareholder_structures`

辅助表如果有，也会帮助算法解释得更完整：

- `relationship_sources`
- `entity_aliases`

### 2.1 `companies`：算法处理的起点

这张表最重要的不是“公司名字”，而是“算法从哪个公司开始分析”。

关键字段：

| 字段 | 作用 |
| --- | --- |
| `id` | 算法入口。`refresh_company_control_analysis(company_id)` 就是从这里起跑。 |
| `name` | 用于结果输出、样本解释、前端展示。 |
| `incorporation_country` | 当没有唯一 actual controller 时，算法会 fallback 到这里。 |
| `listing_country` | 跟归属判断有关，但当前主版本里它更多是结果附带信息，不是主判定核心。 |
| `description` | 目前不是主判定字段，但在某些总结/展示逻辑里可作辅助上下文。 |

`incorporation_country` 特别重要，因为：

- 如果没有识别出唯一控制人；
- 或者控制链被保守规则挡住；
- 系统最终仍然要给一个 `actual_control_country`；

这时候就会回退到公司注册地，也就是 `fallback_incorporation`。

### 2.2 `shareholder_entities`：图里的“节点”

这张表存的是所有可能出现在控制链里的主体，包括：

- 公司
- 自然人
- 机构
- 基金
- 政府
- 其他特殊主体

关键字段不是为了“存资料”，而是为了告诉算法“这个节点更像终点还是中间层”。

| 字段 | 作用 |
| --- | --- |
| `id` | 节点主键，所有控制路径最后都落在某个 entity 上。 |
| `entity_name` | 输出 direct / ultimate controller 名称，也参与 trust 等轻量文本判断。 |
| `entity_type` | 区分 `company/person/fund/government/...`，影响终局停留判断。 |
| `country` | 如果识别出 controller，这通常是 actual control country 的直接来源。 |
| `company_id` | 把实体映射回 `companies`。这是“从公司找到控制图入口”的关键。 |
| `entity_subtype` | 区分 `holding_company`、`spv`、`wfoe`、`family_trust` 等，直接影响是否 look-through。 |
| `ultimate_owner_hint` | 很强的上卷信号，表示这个实体更像终局层。 |
| `look_through_priority` | 当前主版本不是绝对核心，但能表达实体的穿透倾向。 |
| `controller_class` | 区分 `natural_person`、`state`、`family`、`corporate_group` 等，影响终局判断。 |
| `beneficial_owner_disclosed` | 对 nominee、trust、rollup 都很关键，表示上层受益控制信息是否清楚。 |
| `notes` | 不直接决定结论，但会在某些 trust / 样本解释里提供辅助线索。 |

几个字段的直观理解：

#### `entity_type`

它告诉算法这个实体“像什么”。

比如：

- `person` 往往更像终局控制人；
- `government` 也常常是终局层；
- `company` 可能只是中间壳；
- `fund` 不一定能直接当成最终控制人，要结合上层和披露判断。

#### `entity_subtype`

这是当前主版本里非常有用的“结构提示”。

例如：

- `holding_company`
- `spv`
- `investment_vehicle`
- `control_platform`
- `sponsor_vehicle`
- `wfoe`

这些 subtype 会让算法更倾向于认为它们是“中间层”，从而继续 look-through。

相反，如果是：

- `family_trust`
- `government_agency`
- `founder_vehicle`

算法会更倾向于把它们当作终局层或至少更接近终局层。

#### `controller_class`

这个字段更像是“控制身份标签”。

比如：

- `natural_person`
- `state`
- `family`
- `corporate_group`
- `institutional`

它不会单独决定结论，但会影响：

- 这个主体是不是适合成为 ultimate controller；
- trust / family / state 类场景的终局偏好；
- 某些 promotion reason 的解释。

#### `beneficial_owner_disclosed`

这个字段在当前主版本里很重要，因为它决定算法是否敢继续往上认人。

典型场景：

- 一个 holding company 直接控股目标公司；
- 如果它上层 parent 也很强，但 `beneficial_owner_disclosed = 0`，算法会更保守；
- 如果上层受益控制关系清楚，算法更容易 rollup；
- 在 nominee / trust 场景里，这个字段尤其关键。

### 2.3 `shareholder_structures`：图里的“边”

这张表是整个算法最核心的输入，因为它描述的是：

> 谁通过什么关系，对谁形成控制或影响。

可以把它理解成“控制图里的边表”。

关键字段很多，但不是每个都同样重要。当前主版本里真正影响判断的，主要是下面这些：

| 字段 | 作用 |
| --- | --- |
| `from_entity_id` | 控制方向的起点，谁在上游。 |
| `to_entity_id` | 被控制的一方，谁在下游。 |
| `relation_type` | 这条边是什么类型：`equity/agreement/board_control/voting_right/nominee/vie` 等。 |
| `holding_ratio` | 股权比例，普通 equity 场景的主输入。 |
| `voting_ratio` | 投票控制比例，在 voting_right / board / VIE 场景里很重要。 |
| `economic_ratio` | 经济利益比例，尤其是 VIE / agreement 场景有意义。 |
| `effective_control_ratio` | 当前算法最偏好的数值控制比例，很多时候比单纯 `holding_ratio` 更直接。 |
| `control_basis` | 文本证据，说明控制依据是什么。 |
| `agreement_scope` | 协议控制的范围，帮助判断是不是在控制“relevant activities”。 |
| `board_seats` | 董事席位数，`board_control` 的核心输入之一。 |
| `nomination_rights` | 任命董事或管理层的权利说明。 |
| `relation_metadata` | 结构化补充字段，常常塞一些 ratio、披露、阻断信号。 |
| `confidence_level` | `high/medium/unknown/low`，是 reliability 的起点。 |
| `look_through_allowed` | 这条边允许不允许继续向上穿透。 |
| `termination_signal` | 如果这里已经明确要求停下，算法会停止继续 promotion。 |
| `is_direct` | 当前主版本只读取直接边。 |
| `is_current` | 只读取当前有效的边。 |
| `effective_date` / `expiry_date` | 只用当前时点有效的关系。 |
| `is_beneficial_control` | 表示这条控制关系是否涉及受益控制披露。 |
| `remarks` | 备注文本，会被 evidence scoring 和样本解释读取。 |

### 2.4 这些字段到底是怎么影响判断的

#### `relation_type`

这个字段决定“算法用哪套逻辑看这条边”。

当前主版本支持的主类型包括：

- `equity`
- `agreement`
- `board_control`
- `voting_right`
- `nominee`
- `vie`

简单理解：

- `equity`：主要靠比例；
- `board_control`：主要看董事会控制权；
- `voting_right`：主要看投票权；
- `agreement`：主要看协议文本能不能形成实际控制；
- `vie`：看 power + economics + exclusivity 的组合；
- `nominee`：要特别看受益人披露，不然会触发阻断。

#### `effective_control_ratio`

当前主版本会优先用这类“有效控制比例”，而不是机械地只看 `holding_ratio`。

这很重要，因为有些边不是纯股权边：

- `voting_right` 可能有单独的表决权比例；
- `vie` 可能同时有投票和经济收益；
- 有些文本或 metadata 里会提示一个更接近实际控制的 ratio。

#### `confidence_level`

这是 reliability integration 的起点。

当前主版本里它会先映射成基础可信度：

- `high -> 0.90`
- `medium -> 0.70`
- `unknown -> 0.60`
- `low -> 0.40`

然后再结合：

- metadata 是否丰富；
- control_basis 是否清楚；
- agreement_scope 是否清楚；
- source 是否存在；
- beneficial owner 是否披露；
- 是否存在 nominee / unknown / protective rights / evidence insufficient 等风险；

最后形成这条边的 `reliability_score`。

#### `look_through_allowed` 和 `termination_signal`

这两个字段像“刹车”。

- `look_through_allowed = false`：即使这条边看起来很强，也不能继续往上穿透；
- `termination_signal`：如果明确写了阻断原因，比如受益人未知，算法会优先停下来。

#### `relationship_sources` 和 `entity_aliases`

这两张辅助表不是每次都必须有，但有的话会提升解释力。

`relationship_sources` 的作用：

- 给边补充来源、来源时间、摘录、来源 confidence；
- reliability integration 会把它们当成“证据质量增强项”。

`entity_aliases` 的作用：

- 帮助实体名称统一、展示更友好；
- 对当前主版本主判断不是核心，但对实际工程里的清洗和解释是有帮助的。

---

## 第 3 部分：算法整体流程（一步步讲）

这一部分按“从输入到输出”的顺序说。

### Step 1：从公司找到控制图入口

算法入口是 `company_id`，但真正参与图搜索的入口不是 `companies` 本身，而是：

> `shareholder_entities` 里那个 `company_id = 当前公司 id` 的映射实体。

在代码里，这一步体现在：

- `build_control_context(...)`
- `_resolve_company_and_target_entity(...)`

为什么必须有这个映射实体？

因为控制图里的节点统一都是 `shareholder_entities`。

也就是说，算法不是“公司表里直接互相连线”，而是：

- 先把目标公司映射成一个 entity 节点；
- 再从这个节点往上找所有 incoming 控制边；
- 然后沿着这些边向上追溯。

如果公司在 `shareholder_entities` 里没有映射实体，算法就没法建图，也没法推 direct / ultimate controller。

### Step 2：读取直接边，构建控制图

当前主版本不会读取所有历史关系，而是只读取“当前有效的直接边”。

在 `build_control_context(...)` 里，核心筛选条件是：

- `is_current = 1`
- `is_direct = 1`
- `effective_date <= as_of`
- `expiry_date >= as_of`

这意味着：

- 历史边不会混进来；
- 间接边不会提前存成结果再被重复当输入；
- 只看当前这个时点有效的控制结构。

然后，每条 `shareholder_structures` 记录会被转成一个 `EdgeFactor`，其中会带上：

- numeric factor
- semantic factor
- reliability score
- relation_type
- flags
- evidence summary

你可以把 `EdgeFactor` 理解成：

> 一条“已经被算法翻译过”的控制边。

### Step 3：计算每条边的控制强度

这是当前主版本最核心的部分之一。

#### 3.1 equity 边怎么处理

`equity` 相对简单：

- 主要看 `holding_ratio` / `effective_control_ratio`；
- semantic factor 通常接近 1；
- reliability 更多由 `confidence_level`、metadata、source 等决定；
- 最终这条边的控制力度大体就是“比例 * 可信度背景”。

所以像 `2001` 这种 `0.65` 的普通股权边，算法很容易认出 direct controller。

#### 3.2 agreement / voting_right / board_control / nominee / vie 怎么处理

这些不是单纯看比例，而是走语义控制评分。

当前主版本里，语义控制是通过 `semantic control evidence model` 做的。它不是机器学习模型，而是规则化评分层。

简单说，这一层在做的事是：

> 把“协议控制、投票权控制、董事会控制、nominee、VIE”这些复杂关系，拆成几种可解释的信号，再合成为一条边的 `semantic_strength`。

### Step 3.3 五个维度分别是什么意思

#### A. Power

通俗理解：

> 谁能拍板决策。

它会看这些东西：

- `voting_ratio`
- `effective_voting_ratio`
- `board_seats`
- `appoint majority directors`
- `right to nominate majority`
- `power of attorney`
- `control relevant activities`
- `de facto control`

比如：

- `board_control` 场景里，如果有 `4/7` 董事席位，power 会很强；
- `voting_right` 场景里，如果文本出现 `full voting control`、`controlling voting rights`，power 会被明显抬高；
- `VIE` 场景里，如果文本写了 `control relevant activities`，也会被视为强 power 信号。

#### B. Economics

通俗理解：

> 谁真正吃到收益、承担风险。

它会看：

- `economic_ratio`
- `benefit_capture`
- `variable returns`
- `economic benefits`
- `substantially all benefits`
- `equity pledge`

这在 VIE / agreement 特别重要。

因为光有“拍板权”还不够，算法还想知道这个主体是不是也真的绑定了经济利益。

#### C. Exclusivity / Irrevocability

通俗理解：

> 这套安排是不是排他的、是不是不容易被撤销。

它会看：

- `exclusive business cooperation`
- `exclusive option`
- `exclusive service agreement`
- `irrevocable voting proxy`
- `irrevocable power of attorney`
- `long-term non-revocable`

为什么这一维重要？

因为很多 agreement / VIE 场景里，真正强的控制不是一句“有协议”，而是：

- 这个协议是否排他；
- 这个委托是否不可撤销；
- 它是不是长期绑定。

#### D. Disclosure

通俗理解：

> 背后的真实受益控制人有没有讲清楚。

它会看：

- `beneficial_owner_disclosed`
- `beneficial_owner_confirmed`
- `beneficiary_controls`
- `beneficial_owner_controls`
- nominee 文本
- beneficial owner unknown 标记

这一维在 nominee / trust 特别关键。

因为当前主版本的态度是：

- 如果披露清楚，可以继续判断；
- 如果表面有 nominee，但受益人不清楚，就宁可阻断。

#### E. Reliability

通俗理解：

> 这条边不是“像不像控制”，而是“这条证据靠不靠谱”。

当前主版本里，reliability 从 `confidence_level` 起步，再加减分。

会影响 reliability 的东西包括：

- `confidence_level`
- relation metadata 是否存在且丰富
- `control_basis` 是否清楚
- `agreement_scope` 是否清楚
- `nomination_rights` 是否清楚
- 文本是否足够丰富
- `relationship_sources` 是否存在
- nominee / unknown / protective rights / evidence insufficient 等风险

所以同样是 `0.51` 的股权边：

- 如果 `confidence_level = high`，更可能通过；
- 如果 `confidence_level = low`，而且没什么别的支撑，就可能被 `low_confidence_evidence_weak` 挡住。

### Step 4：边 -> 路径 -> 候选人

这一步非常关键，因为算法不是只看单边，而是会把边向上拼成路径。

#### 4.1 path score 是什么

一条 path 可以理解成：

> 从某个上游主体，一路走到目标公司的一条控制链。

例如：

- `Continental Power Group -> Nova Grid Holdings -> Nova Grid Systems`

当前主版本里，path score 大体是：

- 路径上各边 numeric factor 的连乘；
- 再乘上各边 semantic factor 的连乘。

可以把它理解成：

> 这条整条控制路径最终还能剩下多少“控制强度”。

#### 4.2 path confidence 是什么

path confidence 不是控制强度，而是：

> 我对这条路径可信不可信的整体把握。

当前主版本里，它是各边 reliability 的乘积。

所以：

- 一条很长的链，只要中间有一条边不太可靠，整条路径 confidence 就会被拖下来；
- 这正好符合“控制链越长，不确定性越大”的直觉。

#### 4.3 candidate score 是什么

同一个上游主体，可能通过多条路径控制目标公司。

比如：

- 一条股权路径；
- 一条投票权路径；
- 一条协议控制路径。

算法会把这些 path 汇总到同一个候选人（candidate）上，再聚合成：

- `candidate total_score`
- `candidate total_confidence`
- `candidate control_mode`

当前默认聚合方式是 `sum_cap`，也就是：

- 多条路径可以叠加；
- 但总分封顶在 1。

#### 4.4 candidate confidence 是什么

这一步是 reliability integration 真正落到候选人层的地方。

当前主版本里：

- 先按 path score 对 path confidence 做加权平均；
- 如果一个候选人有多条“都比较像样”的路径，还会给一个小的 corroboration boost。

通俗理解就是：

- 一条孤零零但证据薄的路径，不太可信；
- 多条独立路径都指向同一个候选人，会更可信；
- 但这个 boost 是有限的，不会因为“路径多”就硬把一个弱候选人抬成强控制人。

### Step 5：识别 direct controller

当前主版本里，direct controller 不是“总分最高的人”，而是更严格：

1. 这个候选人必须是 `min_depth = 1`，也就是直接作用在目标公司的那一层；
2. 它的 `control_level` 必须到 `control`；
3. 不能是 direct layer joint control；
4. 不能命中硬阻断，如：
   - `beneficial_owner_unknown`
   - `nominee_without_disclosure`
   - `protective_right_only`
   - `evidence_insufficient`
   - `low_confidence_evidence_weak`

所以“排第一”不等于 direct controller。

举个直观例子：

- `2012` 里领先候选确实是 `Vertex Industrial Sponsor Pte. Ltd.`；
- 但它只有 51%，而且 `confidence_level = low`；
- 算法最后把它保留成 leading candidate，没有直接落成 direct controller。

### Step 6：判断是否继续上卷到 ultimate controller

这是 current mainline 里另一个核心：promotion / rollup。

如果 direct controller 已经成立，算法接下来要问：

> 这个 direct controller 本身是不是终点？还是只是中间层？

#### 6.1 什么情况下继续上卷

典型触发场景：

- 当前 direct controller 是 `holding_company` / `spv` / `control_platform` / `wfoe` 等中间层；
- 它上面还有明显更强的 parent；
- 上游 parent 对当前 direct controller 也形成控制；
- 上游候选人在目标公司层面的间接控制分数达到要求；
- confidence 也够；
- 没有命中阻断。

#### 6.2 promotion reason 常见有哪些

当前主版本里，比较常见的上卷理由包括：

- `beneficial_owner_priority`
- `disclosed_ultimate_parent`
- `look_through_holding_vehicle`
- `trust_vehicle_lookthrough`
- `controls_direct_controller`

这几个 reason 很有用，因为它们直接告诉你：

- 算法为什么没有停在 direct controller；
- 它是基于受益人披露、holdco look-through，还是 trust vehicle 小规则继续向上走的。

#### 6.3 什么情况下不会继续上卷

常见停下原因：

- 当前实体本身更像终局层；
- 上游 parent 对目标公司的间接控制分数不够；
- 上游 parent 自身只到 significant influence，不到 control；
- 上游存在 joint control；
- nominee / beneficial owner unknown / low confidence / protective rights 等阻断；
- `look_through_allowed = false`；
- `termination_signal` 提前要求停下。

#### 6.4 trust vehicle look-through 现在怎么做

当前主版本里的 trust 规则是“小规则”，不是大规模 trust framework。

它大致做了两件事：

1. **终局 trust 倾向**  
   如果一个 trust 明显是终局安排，比如 `family_trust`，而且受益关系披露清楚，它可以作为终局层停下。

2. **trust vehicle 中间层倾向**  
   如果一个 trust 更像 holding / vehicle，而上游又有清楚的终局父层信号（比如 state / disclosed parent），算法允许继续 look-through。

所以这一步不是“名字里有 trust 就继续往上”，也不是“名字里有 trust 就直接认成终局”，而是：

> trust 只是一个结构提示，最终还要看披露、上游控制和整体链条。

### Step 7：阻断规则

这一部分非常重要，因为当前主版本的稳定性，很大程度就来自这些阻断规则。

#### `joint_control`

含义：

- 不止一个主体在控制；
- 当前不应该给唯一 actual controller。

典型情况：

- 两个上游 parent 各持 50% 控制中间 holding company；
- 两个都够强；
- 算法不会随便挑一个，而是返回 `joint_control_undetermined`。

#### `nominee_without_disclosure`

含义：

- 看到 nominee 关系了；
- 但受益控制人没有披露清楚。

当前主版本态度很明确：

- nominee 可以作为风险信号；
- 但不能直接把 nominee 自己当成 actual controller。

#### `beneficial_owner_unknown`

含义：

- 系统明确知道“真正控制人不清楚”；
- 这时候要阻断，而不是继续猜。

#### `low_confidence_evidence_weak`

含义：

- 候选人表面上刚过控制阈值；
- 但 confidence 太低；
- 再加上它是 semantic / mixed / barely control 等边缘情况；
- 所以宁可只留 leading candidate。

#### `insufficient_evidence`

含义：

- 整体证据就不够强；
- 不一定是某条硬阻断，但不足以下 actual controller 结论。

#### `close_competition`

含义：

- 领先者和第二名太接近；
- 这时候“排第一”不等于“足够稳”。

#### `look_through_not_allowed`

含义：

- 这条边本身不允许继续穿透；
- 即使上面可能还有链，也要停下。

#### `protective_right_only`

含义：

- 只有保护性权利；
- 这种权利可以限制别人，但不等于自己已经控制公司。

### Step 8：写回结果

算法最后不是只在内存里出一个结果，而是会写回两类核心输出：

- `control_relationships`
- `country_attributions`

#### 8.1 `control_relationships` 里写什么

这张表存的是“候选控制人层面的分析结果”。

典型字段包括：

- `controller_entity_id`
- `controller_name`
- `control_type`
- `control_ratio`
- `control_path`
- `is_direct_controller`
- `is_actual_controller`
- `is_ultimate_controller`
- `promotion_reason`
- `control_chain_depth`
- `terminal_failure_reason`
- `control_mode`
- `semantic_flags`
- `basis`

可以把它理解成：

> 这张表是“候选人列表 + 每个候选人为什么被判成这样”的明细表。

#### 8.2 `country_attributions` 里写什么

这张表存的是“最后给公司的归属结论”。

典型字段包括：

- `actual_control_country`
- `attribution_type`
- `actual_controller_entity_id`
- `direct_controller_entity_id`
- `attribution_layer`
- `country_inference_reason`
- `look_through_applied`
- `basis`

这张表更像：

> 给这家公司最后落地的一条总结结果。

#### 8.3 为什么要区分 `attribution_layer`

因为“这个国家归属是怎么来的”很重要。

常见值有：

- `direct_controller_country`
- `ultimate_controller_country`
- `joint_control_undetermined`
- `fallback_incorporation`

这能区分几种完全不同的情况：

- 直接控制人就是终局；
- 经过 rollup 才到了上层；
- 没法给唯一控制人；
- 根本没有足够控制链，只能 fallback 到注册地。

#### 8.4 为什么同时要有 `direct_controller_entity_id` 和 `actual_controller_entity_id`

因为它们本来就在回答不同问题。

举例：

- `2004`：direct 是 `Nova Grid Holdings Ltd.`，actual 是 `Continental Power Group`；
- `2007`：direct 是 `Lakeshore Holdings Ltd.`，但 actual 是空，因为上层 joint control；
- `2001`：两者相同；
- `2021`：两者都空，只剩 fallback。

这两个字段同时保留，才能把“看见眼前控股平台”和“最终该把谁算作实际控制人”区分开。

---

## 第 4 部分：结合真实样本举例说明

下面不讲抽象概念，直接看已经验证过的真实样本。

### 4.1 `2001`：direct = ultimate 的标准股权场景

**输入结构大概是什么**

- `Zenith Founder Holdings Ltd.` 直接持有目标公司 `65%`；
- 其他股东只有 `18% / 12% / 5%` 的中小持股；
- 没有复杂上层链，也没有协议控制、joint control、nominee 风险。

**算法怎么判断**

1. equity 边直接给出很高的 numeric control；
2. 候选人 `Zenith Founder Holdings Ltd.` 在 direct layer 就达到 `control`；
3. 它没有命中任何阻断；
4. 因为没有必要继续上卷，所以直接停在这一层。

**结果**

- direct controller：`Zenith Founder Holdings Ltd.`
- ultimate / actual controller：`Zenith Founder Holdings Ltd.`
- attribution layer：`direct_controller_country`

**它说明的规则**

- 普通强股权控制下，算法会稳定输出 `direct = ultimate`；
- 这也是最简单、最“像常识”的场景。

### 4.2 `2004`：上卷成功的标准 holding-company 场景

**输入结构大概是什么**

- 目标公司 `Nova Grid Systems Ltd.` 被 `Nova Grid Holdings Ltd.` 直接持有 `70%`；
- 这个 holding company 又被 `Continental Power Group` 持有 `90%`；
- holding company 本身 `beneficial_owner_disclosed = 1`。

**算法怎么判断**

1. 第一层先把 `Nova Grid Holdings Ltd.` 识别为 direct controller；
2. 发现它是 `holding_company`，更像中间层；
3. 再往上一层看，`Continental Power Group -> Nova Grid Holdings` 的边也足够强；
4. promotion reason 是 `disclosed_ultimate_parent`；
5. 所以 actual controller 上卷到上层集团。

**结果**

- direct controller：`Nova Grid Holdings Ltd.`
- ultimate / actual controller：`Continental Power Group`
- attribution layer：`ultimate_controller_country`

**它说明的规则**

- direct controller 成立，不代表算法就停下；
- `holding_company + 强上游 parent + 披露清楚` 是典型 rollup 成功场景。

### 4.3 `2007`：joint control 阻断

**输入结构大概是什么**

- 目标公司先被 `Lakeshore Holdings Ltd.` 直接控股 `70%`；
- 但 `Lakeshore Holdings Ltd.` 上面有两个父层：
  - `Red Cedar Capital` 持有 `50%`
  - `Maple Bridge Capital` 持有 `50%`

**算法怎么判断**

1. direct layer 上，`Lakeshore Holdings Ltd.` 可以成立；
2. promotion 时继续往上看；
3. 上层两个 parent 对 direct controller 的控制完全并列；
4. 这不是“一个赢”，而是“共同控制”。

**结果**

- direct controller：`Lakeshore Holdings Ltd.`
- ultimate / actual controller：空
- attribution layer：`joint_control_undetermined`
- terminal failure reason：`joint_control`

**它说明的规则**

- 当前主版本不会在 joint control 时硬挑一个 actual controller；
- direct 可以存在，但 ultimate 可以为空。

### 4.4 `2012`：low confidence，保守处理

**输入结构大概是什么**

- `Vertex Industrial Sponsor Pte. Ltd.` 直接持股 `51%`；
- 看起来刚好过控制线；
- 但这条边 `confidence_level = low`。

**算法怎么判断**

1. numeric 上它看起来像控制；
2. 但 candidate 只是在控制阈值附近；
3. reliability 太低；
4. 命中 `low_confidence_evidence_weak`；
5. 所以不直接输出 direct / actual controller，只保留 leading candidate。

**结果**

- direct controller：空
- actual controller：空
- leading candidate：`Vertex Industrial Sponsor Pte. Ltd.`
- attribution layer：`fallback_incorporation`
- terminal failure reason：`low_confidence_evidence_weak`

**它说明的规则**

- 当前主版本不是“51% 一定认”；
- 如果证据可靠性不够，会故意保守。

### 4.5 `2016`：nominee / beneficial owner unknown 阻断

**输入结构大概是什么**

- `Clearwave Nominee Services Ltd.` 对目标公司有一条 nominee 边；
- `effective_control_ratio = 55%`；
- 但 `look_through_allowed = 0`；
- `termination_signal = beneficial_owner_unknown`；
- `control_basis = registered nominee account`。

**算法怎么判断**

1. nominee 边本身会先进入 semantic scoring；
2. 但 disclosure 这一维发现真正受益控制人不清楚；
3. 同时 `termination_signal` 也明确要求停下；
4. 因此不允许继续把 nominee 当作 actual controller，也不能往上穿透。

**结果**

- direct controller：空
- actual controller：空
- leading candidate：`Clearwave Nominee Services Ltd.`
- attribution layer：`fallback_incorporation`
- terminal failure reason：`beneficial_owner_unknown`

**它说明的规则**

- nominee 不是不能进入算法；
- 但在当前主版本里，nominee 没有受益人披露就会被硬阻断。

### 4.6 `2021`：fallback 的典型场景

**输入结构大概是什么**

- 公司股东比较分散；
- 最大几个股东只有 `18% / 16% / 15% / 11% / 9%`；
- 没有明显协议控制、board control、VIE、受益人优先线索。

**算法怎么判断**

1. 会正常生成一批候选人；
2. 但没有任何候选人达到稳定控制；
3. 也不存在足够强的 semantic control 路径；
4. 所以既没有 direct controller，也没有 actual controller。

**结果**

- direct controller：空
- actual controller：空
- attribution type：`fallback_incorporation`
- actual control country：`Canada`

**它说明的规则**

- 当前主版本不会为了“必须给答案”而强认控制人；
- 分散持股下，fallback 是合理结论。

### 4.7 `2023`：board_control / mixed_control

**输入结构大概是什么**

- `Signal Industrial Control Platform Ltd.` 对目标公司有一条 `board_control` 边；
- 这条边包含：
  - `voting_ratio = 57.1%`
  - `board_seats = 4`
  - `appoint 4 of 7 directors`
  - `board appointment and strategic budget approval`
- 这个控制平台上层由 `Mr. Zhao Ming` 持有 `88%`，且 `ultimate_owner_hint = 1`。

**算法怎么判断**

1. `board_control` 边在 power 维度很强，因为它直接碰到董事会多数席位；
2. 这让 `Signal Industrial Control Platform Ltd.` 成为 direct controller；
3. 然后算法发现它是 `holding_company` 类型的平台节点；
4. 上层 `Mr. Zhao Ming` 对平台持股 `88%`，而且有 `ultimate_owner_hint`；
5. 所以继续上卷，promotion reason 是 `beneficial_owner_priority`。

**结果**

- direct controller：`Signal Industrial Control Platform Ltd.`
- ultimate / actual controller：`Mr. Zhao Ming`
- attribution type：`mixed_control`

**它说明的规则**

- 不是只有 equity 才能识别控制；
- 董事会控制 + 上层受益人清晰时，算法会走 mixed-control + promotion。

### 4.8 `2024`：VIE 强控制上卷

**输入结构大概是什么**

- `Jade River WFOE Co., Ltd.` 对目标公司有一条 `vie` 边；
- 这条边包含：
  - `voting_ratio = 62%`
  - `economic_ratio = 95%`
  - `exclusive business cooperation`
  - `equity pledge`
  - `exclusive option`
  - `voting proxy`
- 上层 `Ms. Chen Rui` 持有 WFOE `90%`，且 `ultimate_owner_hint = 1`。

**算法怎么判断**

1. `vie` 边不是只看一个 ratio，而是看 power + economics + exclusivity 的组合；
2. 这条边的文本和比例都很强，所以 semantic strength 很高；
3. `Jade River WFOE Co., Ltd.` 成为 direct controller；
4. 再往上看，`Ms. Chen Rui` 对 WFOE 的控制明确且披露清楚；
5. promotion reason 也是 `beneficial_owner_priority`。

**结果**

- direct controller：`Jade River WFOE Co., Ltd.`
- ultimate / actual controller：`Ms. Chen Rui`
- attribution type：`mixed_control`

**它说明的规则**

- 当前主版本已经能把 VIE 当作实质控制关系来识别；
- 只要 semantic evidence 和 reliability 足够，就不会卡在“不是股权所以不给控制”。

### 4.9 `1112 / 4099`：trust 小规则实际改善的样本

这两个样本很像，可以一起看。

#### `1112 Apex Advanced Materials Corporation`

- direct controller：`Crescent Trust Group Inc.`
- ultimate controller：`USA State Capital Holdings 37`
- promotion reason：`trust_vehicle_lookthrough`

#### `4099 Atlantic Media Holdings Inc.`

- direct controller：`Crescent Trust Group Inc.`
- ultimate controller：`USA State Capital Holdings 37`
- promotion reason：`trust_vehicle_lookthrough`

**输入结构大概是什么**

- 目标公司先被 `Crescent Trust Group Inc.` 直接控制；
- 这层 trust 实体本身不是 family trust，也不是明确终局主体；
- 它上面还有 `USA State Capital Holdings 37` 持股 `72.11%`；
- 上层是 state 类终局信号。

**算法怎么判断**

1. 先把 `Crescent Trust Group Inc.` 识别为 direct controller；
2. 然后算法判断这个 trust 更像“中间层 trust vehicle”，不是终局；
3. 上层 parent 又是明显更强的终局信号；
4. 所以按照 trust 小规则继续 look-through。

**它说明的规则**

- 当前主版本不是“名字带 trust 就停”；
- 也不是“名字带 trust 就乱上卷”；
- 它只在**像 trust vehicle、且上层终局信号明确**时继续向上。

### 4.10 rollup_success 这 6 个样本：这轮为什么能上卷成功

这组样本的共同特点非常明显：

- 目标公司都有一个 `58%~60%` 左右的 direct holding company；
- 这个 direct controller 都是：
  - `holding_company`
  - `beneficial_owner_disclosed = 1`
  - `confidence_level = high`
- 它们上层还有一个 `82%~85%` 左右的 parent / fund / group；
- 上层 parent 也有明确的终局信号或披露线索。

| company_id | 公司 | direct controller | ultimate controller | promotion reason |
| --- | --- | --- | --- | --- |
| 843 | Pacific Platform Integrated Group Inc. | Pacific Platform Holdings Ltd. | Pacific Platform Parent Group | `disclosed_ultimate_parent` |
| 1911 | Taishan Health Technology Group Co., Ltd. | Taishan Health Holdings Ltd. | Taishan Health Parent Group | `disclosed_ultimate_parent` |
| 3751 | Orchid Network Ltd. | Orchid Network Holdings Ltd. | Orchid Network Growth Fund II | `beneficial_owner_priority` |
| 9035 | Pacific Water International Group Inc. | Pacific Water Holdings Ltd. | Pacific Water Parent Group | `disclosed_ultimate_parent` |
| 9175 | Seoul Foods International Co., Ltd. | Seoul Foods Holdings Ltd. | Seoul Foods Growth Fund II | `beneficial_owner_priority` |
| 10004 | Helix Industrial Motion Co. 1 | Helix Industrial Holdings Ltd. | Helix Industrial Growth Fund II | `beneficial_owner_priority` |

**这组样本说明的规则**

- 当前主版本不会在 direct holding company 那一层过早停止；
- 只要 direct 层已经形成控制，而上层链条也足够强，就会继续上卷；
- `disclosed_ultimate_parent` 和 `beneficial_owner_priority` 是两条最常见的 rollup 成功路径。

---

## 第 5 部分：当前主版本已经能处理什么

当前冻结主版本已经比较稳定支持以下能力。

### 5.1 普通股权控制

- 能识别 direct equity control；
- 能区分 direct = ultimate 和 direct != ultimate；
- 能把强股权控制稳定写回到 `control_relationships` 和 `country_attributions`。

### 5.2 promotion / rollup

- 能从 direct controller 继续往上找 ultimate controller；
- 能处理 `holding_company`、`spv`、`control_platform`、`wfoe` 等中间层；
- 对典型 rollup-success 样本已经收口。

### 5.3 SPV / holding-company look-through

- 对“中间壳 + 强上层 parent”的场景已经比较稳定；
- 不会因为看到一层 holdco 就过早停住。

### 5.4 阻断逻辑

- `joint_control`
- `nominee_without_disclosure`
- `beneficial_owner_unknown`
- `low_confidence_evidence_weak`
- `insufficient_evidence`
- `close_competition`
- `look_through_not_allowed`
- `protective_right_only`

这些规则一起构成了当前主版本的“保守边界”。

### 5.5 统一语义控制识别

当前主版本已经能把这些关系放进统一框架里做判断：

- `agreement`
- `voting_right`
- `board_control`
- `nominee`
- `vie`

也就是说，现在系统不是只有 equity 才能识别控制，而是已经具备了一个相对完整的“语义控制”主干。

### 5.6 mixed-control / non-equity 收口

前面几轮调参之后，这部分已经从“容易偏保守”收敛到比较稳定的状态：

- mixed-control 不会轻易被压回 fallback；
- 强 non-equity 结构更容易穿过 actual gate；
- 同时 nominee / joint / low-confidence 这些保守逻辑没有被冲坏。

### 5.7 trust 小规则

当前主版本已经支持一个**小范围、可解释的 trust 增强**：

- 终局 trust 可以作为终点；
- trust vehicle 可以在证据足够时继续 look-through；
- name-only trust 不会被普遍放宽。

---

## 第 6 部分：当前主版本还没有深入处理什么

这一部分不是说算法“不行”，而是说：

> 当前主版本已经先把主干收口了，下面这些属于下一阶段增强项。

### 6.1 GP-LP / fund governance

现在基金、平台、growth fund 可以进入控制链，但更细的 GP-LP 权利结构还没有专门建模。

### 6.2 更复杂 trust hierarchy

当前 trust 只做了小规则：

- 终局 trust；
- trust vehicle 中间层。

但更复杂的多层 trust arrangement、trustee / beneficiary 多角色链条，主版本还没有深入做。

### 6.3 acting-in-concert

当前主版本能处理 joint control，但没有专门做“concert party / acting-in-concert”这一类协同行为规则。

### 6.4 state ownership 特化

现在 `state` 可以作为 controller_class 或终局信号使用，但还没有做更细的 state ownership 专项规则体系。

### 6.5 public float / dispersed ownership 更细口径

现在主版本对这类场景的处理思路是正确的：该保守时保守。  
但在解释层面、分类口径层面，还可以做得更细，比如：

- 更清楚地区分 public float；
- 更清楚地区分 dispersed ownership；
- 在前端或报告层给出更直观解释。

### 6.6 source quality / corroboration / path independence / time consistency

当前 reliability integration 已经把 source / metadata / text richness 放进去了，但还没做到特别细。

未来可以继续增强：

- 来源质量分级；
- 独立证据链之间的真正 path independence；
- 更细的 corroboration；
- 时间一致性和历史变化建模。

所以这些不是“当前算法不能用”，而是：

- 主版本先把 direct / ultimate / promotion / block 主干做稳；
- 更复杂的结构，放到下一阶段更合适。

---

## 第 7 部分：用一句话总结当前算法

如果只用一句话概括当前主版本，我会这么说：

> 当前 ultimate controller 算法本质上是在一个带语义控制、可靠性评分和阻断规则的控制图上，先找 direct controller，再判断是否可以安全地上卷到 ultimate / actual controller；它不是简单按持股排序，而是一套“只有证据够强才给唯一控制人、否则宁可保守”的最终实际控制人识别主版本。

---

## 最后补一句：最容易误解的几个点

如果你后面自己回看代码或结果，最容易误解的地方大概有这几个：

1. **leading candidate 不等于 actual controller**  
   leading candidate 只是“目前最像的候选人”，不是系统已经认可的最终控制人。

2. **direct controller 存在，不代表 actual controller 一定存在**  
   `2007` 就是典型：direct 可以成立，但因为上层 joint control，actual 仍然为空。

3. **actual_control_country 不一定意味着 actual controller 已被识别**  
   在 fallback 场景里，这个国家可能只是公司注册地，不是上层控制链推出来的。

4. **trust 规则现在只是小规则，不是 trust 全框架**  
   它只解决“明显终局 trust”和“明显 trust vehicle 中间层”这两类当前最值得处理的情况。

5. **当前主版本最重要的气质是“保守正确”，不是“尽量多认”**  
   所以很多你觉得“差不多像控制”的样本，如果 reliability 不够或结构不够清楚，系统会故意停在 leading candidate / fallback。
