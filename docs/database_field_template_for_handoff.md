# 数据库字段模板文档（对接版）

本文档用于和同组同学对接基础股权/控制数据。  
你同学主要需要理解两件事：

1. 哪些表是需要提供给分析侧的基础输入表
2. 每张表的字段含义、是否必填、推荐取值方式

## 1. 对接范围

### 1.1 基础输入表

这三张表是穿刺分析的核心输入：

- `companies`
- `shareholder_entities`
- `shareholder_structures`

### 1.2 可选辅助表

如果对方有更完整的来源信息或别名信息，可以额外提供：

- `relationship_sources`
- `entity_aliases`

### 1.3 算法输出表

这两张表一般由分析程序写回，不要求基础数据提供方填写：

- `control_relationships`
- `country_attributions`

## 2. 先给同学的最小交付要求

如果当前阶段只需要你这边做穿刺分析，对方至少需要给你：

| 表名 | 是否必须提供 | 说明 |
| --- | --- | --- |
| `companies` | 是 | 待分析公司主表 |
| `shareholder_entities` | 是 | 图中的所有主体节点 |
| `shareholder_structures` | 是 | 主体之间的直接股权/控制边 |
| `relationship_sources` | 否 | 关系来源证据 |
| `entity_aliases` | 否 | 实体别名 |
| `control_relationships` | 否 | 算法产出 |
| `country_attributions` | 否 | 算法产出 |

## 3. 枚举和值域约定

### 3.1 `shareholder_entities.entity_type`

推荐取值：

- `company`
- `person`
- `institution`
- `fund`
- `government`
- `other`

### 3.2 `shareholder_structures.relation_type`

推荐取值：

- `equity`
- `agreement`
- `board_control`
- `voting_right`
- `nominee`
- `vie`
- `other`

如果当前只做股权穿透，统一使用 `equity` 即可。

### 3.3 `shareholder_structures.relation_role`

推荐取值：

- `ownership`
- `control`
- `governance`
- `nominee`
- `contractual`
- `other`

### 3.4 `shareholder_structures.confidence_level`

推荐取值：

- `high`
- `medium`
- `low`
- `unknown`

## 4. 字段模板

### 4.1 `companies`（基础输入表）

| 字段名 | 是否必填 | 含义 | 示例值 |
| --- | --- | --- | --- |
| `id` | 是 | 公司主键；跨表关联时必须稳定 | `19` |
| `name` | 是 | 公司全称 | `Sterling Electric Holdings plc` |
| `stock_code` | 是 | 股票代码或内部唯一代码 | `SEH` |
| `incorporation_country` | 是 | 注册地国家/地区 | `UK` |
| `listing_country` | 是 | 上市地国家/地区 | `UK` |
| `headquarters` | 是 | 总部所在地 | `London, UK` |
| `description` | 否 | 备注、行业说明、样例标签等 | `industrial equipment | seeded sample` |

### 4.2 `shareholder_entities`（基础输入表）

说明：这张表表示股东图里的所有节点。  
每个待分析公司，通常都需要在本表里有一条“映射实体”记录，即：

- `entity_type = company`
- `company_id = companies.id`

| 字段名 | 是否必填 | 含义 | 示例值 |
| --- | --- | --- | --- |
| `id` | 是 | 实体主键；会被边表引用 | `4` |
| `entity_name` | 是 | 实体名称 | `Tencent Holdings Ltd.` |
| `entity_type` | 是 | 实体类型 | `company` |
| `country` | 否 | 实体所属国家/地区 | `China` |
| `company_id` | 条件必填 | 如果该实体本身对应 `companies` 中的一家公司，则填写对应公司 `id`；否则可为空 | `4` |
| `identifier_code` | 否 | 实体识别码，如统一社会信用代码、注册号、内部码 | `TENCENT_HK_0004` |
| `is_listed` | 否 | 是否上市主体 | `true` |
| `notes` | 否 | 备注、别名说明、数据来源补充 | `mapped listed company entity` |

### 4.3 `shareholder_structures`（基础输入表，最核心）

说明：这张表表示实体之间的边。  
当前算法主要读取“当前有效的直接边”，也就是：

- `is_direct = 1`
- `is_current = 1`
- `effective_date` 未失效
- `expiry_date` 未过期

建议只提供直接边，不要把间接边预先展开。

| 字段名 | 是否必填 | 含义 | 示例值 |
| --- | --- | --- | --- |
| `id` | 是 | 边主键 | `118` |
| `from_entity_id` | 是 | 上游实体 `id` | `4` |
| `to_entity_id` | 是 | 下游实体 `id` | `19` |
| `holding_ratio` | 股权场景必填 | 持股比例，建议统一按 `0-100` 百分比存储 | `51.31` |
| `is_direct` | 是 | 是否为直接关系；建议直接边填 `1` | `1` |
| `control_type` | 否 | 历史兼容字段；如无特殊要求可与 `relation_type` 保持一致或股权填 `equity` | `equity` |
| `relation_type` | 是 | 关系类型，决定算法按股权还是按控制语义处理 | `equity` |
| `has_numeric_ratio` | 否 | 是否存在数值比例；股权边通常为 `1` | `1` |
| `relation_role` | 否 | 关系角色 | `ownership` |
| `control_basis` | 控制关系建议填写 | 控制依据文本，适用于协议控制/董事会控制等 | `right to nominate majority of directors` |
| `board_seats` | 董事会场景建议填写 | 可控制的董事席位数 | `3` |
| `nomination_rights` | 董事会场景建议填写 | 提名权、任命权说明 | `appoint 3 of 5 directors` |
| `agreement_scope` | 协议/VIE 场景建议填写 | 协议控制范围说明 | `exclusive service agreement covering operating decisions` |
| `relation_metadata` | 否 | JSON 扩展字段，补充投票权比例、董事会总席位等 | `{"effective_voting_ratio": 70, "total_board_seats": 5}` |
| `relation_priority` | 否 | 关系优先级；为空时算法使用默认优先级 | `30` |
| `confidence_level` | 否 | 证据置信度 | `high` |
| `reporting_period` | 否 | 报告期 | `2025Q4` |
| `effective_date` | 否 | 生效日期 | `2025-01-01` |
| `expiry_date` | 否 | 失效日期 | `2026-12-31` |
| `is_current` | 是 | 当前是否有效 | `1` |
| `source` | 否 | 关系来源名称或来源系统 | `annual_report_2025` |
| `remarks` | 否 | 备注信息；无法结构化的附加文本可放这里 | `direct equity ownership` |

### 4.4 `relationship_sources`（可选辅助表）

说明：这张表不是穿刺分析必需表，但如果要保留证据链，建议提供。

| 字段名 | 是否必填 | 含义 | 示例值 |
| --- | --- | --- | --- |
| `id` | 否 | 记录主键 | `1` |
| `structure_id` | 是 | 对应的 `shareholder_structures.id` | `118` |
| `source_type` | 否 | 来源类型 | `annual_report` |
| `source_name` | 否 | 来源名称 | `FY2025 Annual Report` |
| `source_url` | 否 | 来源链接 | `https://example.com/report.pdf` |
| `source_date` | 否 | 来源日期 | `2025-12-31` |
| `excerpt` | 否 | 证据摘录 | `Tencent directly holds 51.31% of Sterling Electric Holdings plc.` |
| `confidence_level` | 否 | 证据置信度 | `high` |

### 4.5 `entity_aliases`（可选辅助表）

说明：如果存在中英文名、简称、旧名，可提供该表方便实体清洗和展示。

| 字段名 | 是否必填 | 含义 | 示例值 |
| --- | --- | --- | --- |
| `id` | 否 | 记录主键 | `1` |
| `entity_id` | 是 | 对应的 `shareholder_entities.id` | `4` |
| `alias_name` | 是 | 别名 | `腾讯控股有限公司` |
| `alias_type` | 否 | 别名类型，如英文名、中文名、简称、旧名 | `chinese` |
| `is_primary` | 否 | 是否主别名 | `0` |

### 4.6 `control_relationships`（算法输出表）

说明：这张表一般由分析程序自动生成。  
一家公司可能有多条候选控制人记录，其中通常只有 0 或 1 条会被标为 `is_actual_controller = 1`。

| 字段名 | 是否必填 | 含义 | 示例值 |
| --- | --- | --- | --- |
| `id` | 否 | 输出记录主键 | `10` |
| `company_id` | 是 | 被分析公司 `id` | `19` |
| `controller_entity_id` | 否 | 控制人实体 `id` | `4` |
| `controller_name` | 是 | 控制人名称 | `Tencent Holdings Ltd.` |
| `controller_type` | 是 | 控制人类型 | `company` |
| `control_type` | 是 | 判定类型 | `equity_control` |
| `control_ratio` | 否 | 控制得分或控制比例（百分比口径） | `51.31` |
| `control_path` | 否 | JSON 格式的控制路径明细 | `[{"path_entity_names":["Tencent Holdings Ltd.","Sterling Electric Holdings plc"]}]` |
| `is_actual_controller` | 是 | 是否为最终选中的实际控制人 | `true` |
| `basis` | 否 | 判定依据摘要或结构化 JSON | `{"classification":"equity_control"}` |
| `notes` | 否 | 备注 | `auto generated` |
| `control_mode` | 否 | 控制模式：数值、语义或混合 | `numeric` |
| `semantic_flags` | 否 | JSON 数组，记录控制语义标记 | `["board_control","needs_review"]` |
| `review_status` | 否 | 复核状态 | `auto` |

### 4.7 `country_attributions`（算法输出表）

说明：这张表一般由分析程序自动生成。  
通常每家公司保留 1 条最终国家归属结果。

| 字段名 | 是否必填 | 含义 | 示例值 |
| --- | --- | --- | --- |
| `id` | 否 | 输出记录主键 | `8` |
| `company_id` | 是 | 被分析公司 `id` | `19` |
| `incorporation_country` | 是 | 注册地国家/地区 | `UK` |
| `listing_country` | 是 | 上市地国家/地区 | `UK` |
| `actual_control_country` | 是 | 算法判定的实际控制国家/地区 | `China` |
| `attribution_type` | 是 | 归属判定类型 | `equity_control` |
| `basis` | 否 | 判定依据摘要或结构化 JSON | `{"actual_controller":"Tencent Holdings Ltd."}` |
| `is_manual` | 否 | 是否为人工结果 | `false` |
| `notes` | 否 | 备注 | `generated by control chain analysis` |
| `source_mode` | 否 | 来源模式 | `control_chain_analysis` |

## 5. 对接时最重要的业务规则

### 5.1 必须保证公司和实体能映射上

对每个需要分析的公司，建议在 `shareholder_entities` 里存在一条对应实体：

- `entity_type = company`
- `company_id = companies.id`

否则分析程序很可能找不到该公司在股权图中的起点。

### 5.2 建议只提供直接边

`shareholder_structures` 建议只保留直接关系：

- A 直接持有 B
- B 直接持有 C

不要再额外提供 “A 间接持有 C” 这种人工展开边，否则容易和算法穿刺结果重复。

### 5.3 `holding_ratio` 建议统一为百分比口径

建议统一写成 `0-100`：

- `51.31` 表示 `51.31%`
- 不要有的写 `0.5131`，有的写 `51.31`

### 5.4 如果目前只有股权数据

可以先按下面方式最小化交付：

- `relation_type = equity`
- `control_type = equity`
- `relation_role = ownership`
- `holding_ratio` 填真实持股比例

这样你这边就可以先做股权穿透。

### 5.5 如果后续要支持协议/VIE/董事会控制

建议对方补充这些字段：

- `control_basis`
- `agreement_scope`
- `board_seats`
- `nomination_rights`
- `relation_metadata`
- `confidence_level`

## 6. 最小示例

下面是一个最简单的股权穿透样例：

### `companies`

| id | name | stock_code | incorporation_country | listing_country | headquarters |
| --- | --- | --- | --- | --- | --- |
| 19 | Sterling Electric Holdings plc | SEH | UK | UK | London, UK |

### `shareholder_entities`

| id | entity_name | entity_type | country | company_id |
| --- | --- | --- | --- | --- |
| 4 | Tencent Holdings Ltd. | company | China | 4 |
| 19 | Sterling Electric Holdings plc | company | UK | 19 |

### `shareholder_structures`

| id | from_entity_id | to_entity_id | holding_ratio | is_direct | relation_type | is_current |
| --- | --- | --- | --- | --- | --- | --- |
| 118 | 4 | 19 | 51.31 | 1 | equity | 1 |

## 7. 建议直接发给同学的一段说明

可以直接把下面这段发给对方：

> 我这边做控制链穿刺分析，最少需要你给我三张表：`companies`、`shareholder_entities`、`shareholder_structures`。  
> 其中 `shareholder_structures` 请尽量只给直接边，不要给间接边；`holding_ratio` 统一按百分比口径填写。  
> 每个待分析公司，最好在 `shareholder_entities` 里也有一条对应的 `company` 类型实体，并且 `company_id` 能关联到 `companies.id`。  
> 如果目前只有股权数据，`relation_type` 统一填 `equity` 就可以；如果还有协议控制、表决权、董事会控制、VIE 等信息，请把 `control_basis / agreement_scope / nomination_rights / relation_metadata` 一并给我。
