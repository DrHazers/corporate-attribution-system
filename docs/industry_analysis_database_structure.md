# Corporate Attribution System 数据库结构（含产业分析模块）

这份文档用于给网页端或外部 GPT 生成模拟数据、理解数据库表关系、补充产业分析模块数据。

当前系统是一个“基础事实表 + 算法结果表 + 产业分析扩展表”的结构：

- 基础事实表：企业、主体、股权关系及其辅助信息
- 算法结果表：`control_relationships`、`country_attributions`
- 产业分析模块表：`business_segments`、`business_segment_classifications`、`annotation_logs`

注意：

- 当前控制分析主链路已经存在，默认使用 unified 控制推断主链路
- `control_relationships` 和 `country_attributions` 是算法输出结果表，不是底层事实来源
- 产业分析 v1 当前不需要额外的“公司级产业结果表”，而是通过接口从 `business_segments + business_segment_classifications` 读时聚合


## 1. 当前数据库层级

### 1.1 基础事实层

- `companies`
- `shareholder_entities`
- `shareholder_structures`
- `relationship_sources`
- `entity_aliases`
- `shareholder_structure_history`

### 1.2 算法结果层

- `control_relationships`
- `country_attributions`

### 1.3 产业分析模块

- `business_segments`
- `business_segment_classifications`
- `annotation_logs`


## 2. 当前工作副本中的实际表状态

基于当前已经重算完成的分析副本数据库：

- `companies`: 有数据
- `shareholder_entities`: 有数据
- `shareholder_structures`: 有数据
- `relationship_sources`: 有数据
- `entity_aliases`: 有数据
- `shareholder_structure_history`: 有数据
- `control_relationships`: 有数据
- `country_attributions`: 有数据
- `business_segments`: 当前为空，适合让网页端 GPT 补模拟数据
- `business_segment_classifications`: 当前为空，适合让网页端 GPT 补模拟数据
- `annotation_logs`: 当前为空，可选补模拟数据

这意味着网页端如果要补产业分析，只需要新增：

- `business_segments`
- `business_segment_classifications`
- `annotation_logs`（可选）

而不需要重造：

- `control_relationships`
- `country_attributions`


## 3. 表关系总览

### 3.1 公司与股权分析

- `companies.id` -> `shareholder_entities.company_id`
- `shareholder_entities.id` -> `shareholder_structures.from_entity_id`
- `shareholder_entities.id` -> `shareholder_structures.to_entity_id`
- `shareholder_structures.id` -> `relationship_sources.structure_id`
- `shareholder_structures.id` -> `shareholder_structure_history.structure_id`
- `shareholder_entities.id` -> `entity_aliases.entity_id`
- `companies.id` -> `control_relationships.company_id`
- `shareholder_entities.id` -> `control_relationships.controller_entity_id`
- `companies.id` -> `country_attributions.company_id`

### 3.2 公司与产业分析

- `companies.id` -> `business_segments.company_id`
- `business_segments.id` -> `business_segment_classifications.business_segment_id`
- `annotation_logs` 使用 `(target_type, target_id)` 记录对业务线或分类映射的人工修订留痕


## 4. 各表详细结构

### 4.1 `companies`

用途：公司主表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | INTEGER | 是 | 主键 |
| name | VARCHAR(255) | 是 | 公司名称 |
| stock_code | VARCHAR(50) | 是 | 股票代码，唯一 |
| incorporation_country | VARCHAR(100) | 是 | 注册地 |
| listing_country | VARCHAR(100) | 是 | 上市地 |
| headquarters | VARCHAR(255) | 是 | 总部所在地 |
| description | TEXT | 否 | 公司描述 |

说明：

- `stock_code` 唯一
- 产业分析与控制分析都以 `company_id` 为核心入口


### 4.2 `shareholder_entities`

用途：控制网络中的主体节点表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | INTEGER | 是 | 主键 |
| entity_name | VARCHAR(255) | 是 | 主体名称 |
| entity_type | ENUM(TEXT) | 是 | 主体类型 |
| country | VARCHAR(100) | 否 | 主体国别 |
| company_id | INTEGER | 否 | 若该主体映射到公司，则引用 `companies.id` |
| identifier_code | VARCHAR(100) | 否 | 识别码 |
| is_listed | BOOLEAN | 否 | 是否上市主体 |
| notes | TEXT | 否 | 备注 |
| created_at | DATETIME | 是 | 创建时间 |
| updated_at | DATETIME | 是 | 更新时间 |

推荐枚举：

- `entity_type`:
  - `company`
  - `person`
  - `institution`
  - `fund`
  - `government`
  - `other`


### 4.3 `shareholder_structures`

用途：原始股权/控制关系事实表，是控制算法的核心输入

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | INTEGER | 是 | 主键 |
| from_entity_id | INTEGER | 是 | 上游主体 ID |
| to_entity_id | INTEGER | 是 | 下游主体 ID |
| holding_ratio | NUMERIC(7,4) | 否 | 持股比例 |
| is_direct | BOOLEAN | 是 | 是否直接关系 |
| control_type | VARCHAR(30) | 否 | 控制类型 |
| relation_type | VARCHAR(30) | 否 | 关系类型 |
| has_numeric_ratio | BOOLEAN | 是 | 是否有数值比例 |
| relation_role | VARCHAR(30) | 否 | 关系角色 |
| control_basis | TEXT | 否 | 控制依据 |
| board_seats | INTEGER | 否 | 董事席位数 |
| nomination_rights | TEXT | 否 | 提名权说明 |
| agreement_scope | TEXT | 否 | 协议控制范围 |
| relation_metadata | TEXT | 否 | 补充元数据，通常 JSON 字符串 |
| relation_priority | INTEGER | 否 | 关系优先级 |
| confidence_level | VARCHAR(20) | 否 | 置信度 |
| reporting_period | VARCHAR(20) | 否 | 报告期 |
| effective_date | DATE | 否 | 生效日期 |
| expiry_date | DATE | 否 | 失效日期 |
| is_current | BOOLEAN | 是 | 是否当前有效 |
| source | VARCHAR(255) | 否 | 来源说明 |
| remarks | TEXT | 否 | 备注 |
| created_at | DATETIME | 是 | 创建时间 |
| updated_at | DATETIME | 是 | 更新时间 |

推荐枚举：

- `relation_type`:
  - `equity`
  - `agreement`
  - `board_control`
  - `voting_right`
  - `nominee`
  - `vie`
  - `other`
- `relation_role`:
  - `ownership`
  - `control`
  - `governance`
  - `nominee`
  - `contractual`
  - `other`
- `confidence_level`:
  - `high`
  - `medium`
  - `low`
  - `unknown`


### 4.4 `relationship_sources`

用途：股权/控制关系的来源证据表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | INTEGER | 是 | 主键 |
| structure_id | INTEGER | 是 | 关联 `shareholder_structures.id` |
| source_type | VARCHAR(30) | 否 | 来源类型 |
| source_name | VARCHAR(255) | 否 | 来源名称 |
| source_url | VARCHAR(500) | 否 | 来源链接 |
| source_date | DATE | 否 | 来源日期 |
| excerpt | TEXT | 否 | 摘录 |
| confidence_level | VARCHAR(20) | 否 | 可信度 |
| created_at | DATETIME | 是 | 创建时间 |
| updated_at | DATETIME | 是 | 更新时间 |


### 4.5 `entity_aliases`

用途：主体别名表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | INTEGER | 是 | 主键 |
| entity_id | INTEGER | 是 | 关联 `shareholder_entities.id` |
| alias_name | VARCHAR(255) | 是 | 别名 |
| alias_type | VARCHAR(30) | 否 | 别名类型 |
| is_primary | BOOLEAN | 是 | 是否主别名 |
| created_at | DATETIME | 是 | 创建时间 |
| updated_at | DATETIME | 是 | 更新时间 |


### 4.6 `shareholder_structure_history`

用途：股权关系历史变更记录

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | INTEGER | 是 | 主键 |
| structure_id | INTEGER | 是 | 关联 `shareholder_structures.id` |
| change_type | VARCHAR(30) | 是 | 变更类型 |
| old_value | TEXT | 否 | 旧值，通常 JSON 字符串 |
| new_value | TEXT | 否 | 新值，通常 JSON 字符串 |
| change_reason | TEXT | 否 | 变更原因 |
| changed_by | VARCHAR(100) | 否 | 操作者 |
| created_at | DATETIME | 是 | 创建时间 |


### 4.7 `control_relationships`

用途：控制分析算法输出表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | INTEGER | 是 | 主键 |
| company_id | INTEGER | 是 | 关联 `companies.id` |
| controller_entity_id | INTEGER | 否 | 关联 `shareholder_entities.id` |
| controller_name | VARCHAR(255) | 是 | 控制方名称 |
| controller_type | VARCHAR(50) | 是 | 控制方类型 |
| control_type | VARCHAR(50) | 是 | 控制结论类型 |
| control_ratio | NUMERIC(7,4) | 否 | 控制强度/比例 |
| control_path | TEXT | 否 | 控制路径，通常为 JSON 文本 |
| is_actual_controller | BOOLEAN | 是 | 是否为实际控制人 |
| basis | TEXT | 否 | 判定依据，通常为 JSON 文本 |
| notes | TEXT | 否 | 备注 |
| control_mode | VARCHAR(20) | 否 | 控制模式 |
| semantic_flags | TEXT | 否 | 语义标签，通常为 JSON 文本 |
| review_status | VARCHAR(30) | 否 | 审核状态 |
| created_at | DATETIME | 是 | 创建时间 |
| updated_at | DATETIME | 是 | 更新时间 |

推荐枚举：

- `control_mode`:
  - `numeric`
  - `semantic`
  - `mixed`
- `review_status`:
  - `auto`
  - `manual_confirmed`
  - `manual_rejected`
  - `needs_review`


### 4.8 `country_attributions`

用途：国别归属算法输出表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | INTEGER | 是 | 主键 |
| company_id | INTEGER | 是 | 关联 `companies.id` |
| incorporation_country | VARCHAR(100) | 是 | 注册地 |
| listing_country | VARCHAR(100) | 是 | 上市地 |
| actual_control_country | VARCHAR(100) | 是 | 实际控制归属国 |
| attribution_type | VARCHAR(50) | 是 | 归属类型 |
| basis | TEXT | 否 | 判定依据，通常为 JSON 文本 |
| is_manual | BOOLEAN | 是 | 是否人工覆盖 |
| notes | TEXT | 否 | 备注 |
| source_mode | VARCHAR(30) | 否 | 来源模式 |
| created_at | DATETIME | 是 | 创建时间 |
| updated_at | DATETIME | 是 | 更新时间 |

推荐枚举：

- `source_mode`:
  - `control_chain_analysis`
  - `fallback_rule`
  - `manual_override`
  - `hybrid`


### 4.9 `business_segments`

用途：产业分析模块 v1 的业务线基础事实表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | INTEGER | 是 | 主键 |
| company_id | INTEGER | 是 | 关联 `companies.id` |
| segment_name | VARCHAR(255) | 是 | 业务线名称 |
| segment_type | VARCHAR(30) | 是 | 业务线类型 |
| revenue_ratio | NUMERIC(7,4) | 否 | 收入占比 |
| profit_ratio | NUMERIC(7,4) | 否 | 利润占比 |
| description | TEXT | 否 | 业务说明 |
| source | VARCHAR(255) | 否 | 来源说明 |
| reporting_period | VARCHAR(20) | 否 | 报告期 |
| is_current | BOOLEAN | 是 | 是否当前有效 |
| confidence | NUMERIC(5,4) | 否 | 可信度/置信度 |
| created_at | DATETIME | 是 | 创建时间 |
| updated_at | DATETIME | 是 | 更新时间 |

推荐枚举：

- `segment_type`:
  - `primary`
  - `secondary`
  - `emerging`
  - `other`

网页端生成建议：

- 每家公司生成 1 到 4 条业务线
- 至少 1 条 `primary`
- 可选 0 到 2 条 `secondary`
- 可选 0 到 1 条 `emerging`
- `is_current=true` 的数据会进入默认产业分析摘要


### 4.10 `business_segment_classifications`

用途：业务线映射到标准产业体系的结果表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | INTEGER | 是 | 主键 |
| business_segment_id | INTEGER | 是 | 关联 `business_segments.id` |
| standard_system | VARCHAR(50) | 是 | 分类体系名称 |
| level_1 | VARCHAR(255) | 否 | 一级分类 |
| level_2 | VARCHAR(255) | 否 | 二级分类 |
| level_3 | VARCHAR(255) | 否 | 三级分类 |
| level_4 | VARCHAR(255) | 否 | 四级分类 |
| is_primary | BOOLEAN | 是 | 是否该业务线主产业映射 |
| mapping_basis | TEXT | 否 | 映射依据 |
| review_status | VARCHAR(30) | 否 | 审核状态 |
| created_at | DATETIME | 是 | 创建时间 |
| updated_at | DATETIME | 是 | 更新时间 |

推荐枚举：

- `standard_system`:
  - `GICS`
- `review_status`:
  - `auto`
  - `manual_confirmed`
  - `manual_adjusted`

网页端生成建议：

- 每条业务线生成 1 到 2 条分类映射
- `primary` 业务线建议至少 1 条映射
- 若要触发 `has_manual_adjustment = true`，可在部分行使用：
  - `manual_confirmed`
  - `manual_adjusted`


### 4.11 `annotation_logs`

用途：产业分析模块的轻量留痕表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | INTEGER | 是 | 主键 |
| target_type | VARCHAR(50) | 是 | 目标类型 |
| target_id | INTEGER | 是 | 目标记录 ID |
| action_type | VARCHAR(50) | 是 | 动作类型 |
| old_value | TEXT | 否 | 旧值，通常 JSON 字符串 |
| new_value | TEXT | 否 | 新值，通常 JSON 字符串 |
| reason | TEXT | 否 | 修改原因 |
| operator | VARCHAR(100) | 否 | 操作者 |
| created_at | DATETIME | 是 | 创建时间 |

推荐枚举：

- `target_type`:
  - `business_segment`
  - `business_segment_classification`
- `action_type`:
  - `create`
  - `update`
  - `delete`
  - `manual_override`
  - `confirm`


## 5. 当前前端/网页端应该如何理解这些表

### 5.1 已有可直接使用的数据

这些表当前已经有实际内容，可直接用于网页端展示或给 GPT 作为上下文：

- `companies`
- `shareholder_entities`
- `shareholder_structures`
- `relationship_sources`
- `entity_aliases`
- `shareholder_structure_history`
- `control_relationships`
- `country_attributions`

### 5.2 需要网页端 GPT 生成的产业分析数据

当前建议网页端 GPT 只补这些表：

- `business_segments`
- `business_segment_classifications`
- `annotation_logs`（可选）

不建议让网页端 GPT 重写这些算法结果表：

- `control_relationships`
- `country_attributions`

因为这两张表已经由当前算法在分析副本里计算完成。


## 6. 推荐的产业分析建数顺序

如果网页端 GPT 要在当前已有数据库基础上补产业分析数据，建议顺序如下：

1. 读取 `companies`
2. 为每家公司生成 `business_segments`
3. 为每条业务线生成 `business_segment_classifications`
4. 若需要模拟人工调整，再补 `annotation_logs`


## 7. 推荐给网页端 GPT 的简化任务说明

可以直接把下面这段发给网页端：

```text
请基于现有 Corporate Attribution System 数据库生成产业分析模块的模拟数据。

现有数据库中已经有这些表并且已有数据：
- companies
- shareholder_entities
- shareholder_structures
- relationship_sources
- entity_aliases
- shareholder_structure_history
- control_relationships
- country_attributions

请不要重写或重造上面这些已有表的数据。

请只为以下 3 张表生成模拟数据：
- business_segments
- business_segment_classifications
- annotation_logs（可选）

外键要求：
- business_segments.company_id 必须引用 companies.id
- business_segment_classifications.business_segment_id 必须引用 business_segments.id
- annotation_logs.target_type 只能是 business_segment 或 business_segment_classification

业务规则：
- 每家公司生成 1 到 4 条业务线
- 每家公司至少 1 条 primary 业务线
- business_segments.segment_type 只能是 primary / secondary / emerging / other
- 每条业务线生成 1 到 2 条 GICS 分类映射
- business_segment_classifications.review_status 只能是 auto / manual_confirmed / manual_adjusted
- 部分分类映射要设置为 manual_adjusted，用于后续展示 has_manual_adjustment=true
- 数值字段保留 4 位小数

请输出为 SQLite 可执行 INSERT 语句，或输出为 CSV 文件内容。
```


## 8. 推荐行业与业务线命名风格

可优先覆盖这些方向：

- 云计算
- 工业软件
- 半导体
- 新能源
- 消费电子
- 电商平台
- 数字金融
- 医疗科技
- 智能制造
- 物流科技

业务线命名风格示例：

- Cloud Infrastructure
- Industrial Software
- AI Computing
- Power Battery
- Consumer Electronics
- Digital Payments
- Medical Devices
- Smart Logistics

