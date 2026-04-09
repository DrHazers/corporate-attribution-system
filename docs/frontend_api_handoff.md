# 前端对接说明

## 1. 推荐使用的数据库

为了覆盖控制分析、国别归属、产业分析、多报告期、变化分析与质量提示，最终演示建议使用：

`DATABASE_URL=sqlite:///d:/graduation_project/corp_attribution_system/company_test_analysis_industry.db`

说明：

- 仓库默认的 `company.db` 数据量很小，不适合作为产业分析与最终演示数据源。
- 以下推荐的 `company_id` 都基于 `company_test_analysis_industry.db` 验证。

## 2. 推荐给前端直接使用的接口

### 公司详情首屏主入口

- `GET /companies/{company_id}/analysis/summary`

用途：

- 作为公司详情页首屏主入口。
- 一次返回公司基本信息、控制分析、国别归属、产业分析当前默认快照。

首屏建议重点使用字段：

- `company.name`
- `company.stock_code`
- `company.incorporation_country`
- `company.listing_country`
- `control_analysis.controller_count`
- `control_analysis.actual_controller`
- `country_attribution.actual_control_country`
- `country_attribution.attribution_type`
- `industry_analysis.selected_reporting_period`
- `industry_analysis.business_segment_count`
- `industry_analysis.primary_industries`
- `industry_analysis.structure_flags`
- `industry_analysis.quality_warnings`

### 产业分析详情

- `GET /companies/{company_id}/industry-analysis`

用途：

- 产业分析详情区块主接口。
- 页面切换报告期时直接调用。

适合展示的页面区块：

- 业务线分组卡片
- 主产业标签
- 业务线清单
- 结构 flags
- 数据完整度提示
- 质量 warnings

### 报告期选择器

- `GET /companies/{company_id}/industry-analysis/periods`

用途：

- 只拉报告期，不必一开始就拉变化分析。
- 适合给报告期下拉框、时间轴、历史切换控件使用。

### 变化分析面板

- `GET /companies/{company_id}/industry-analysis/change?current_period=...&previous_period=...`

用途：

- 报告期比较面板。
- 展示新增业务线、移除业务线、primary 变化、emerging 变化、主产业变化摘要。

### 数据质量提示面板

- `GET /companies/{company_id}/industry-analysis/quality`

用途：

- 用于 QA 面板、调试抽屉、后台校验标签。
- 不建议替代主分析接口；建议作为补充面板或 warning badge 数据源。

### 关系图页面

- `GET /companies/{company_id}/relationship-graph`

用途：

- 控制链 / 关系图 tab。
- 返回稳定的 `nodes` / `edges` 结构，适合前端直接喂给 graph 组件。

## 3. 推荐调用顺序

### 公司详情页首屏

1. 先调 `GET /companies/{company_id}/analysis/summary`
2. 首屏直接渲染公司基本信息、控制摘要、国别摘要、产业摘要
3. 如果首屏需要报告期切换器，再补调 `GET /companies/{company_id}/industry-analysis/periods`

### 产业分析详情页 / 产业标签页

1. 调 `GET /companies/{company_id}/industry-analysis/periods`
2. 以 `current_reporting_period` 作为默认选中期
3. 调 `GET /companies/{company_id}/industry-analysis`
4. 用户切换报告期时，改用 `reporting_period` 重调
5. 用户展开历史时，追加 `include_history=true`

### 变化分析区块

1. 先从 `/industry-analysis/periods` 取到可用报告期
2. 默认用最近两期调用 `/industry-analysis/change`
3. 若只有一个报告期，则前端直接隐藏变化分析区块

### 关系图页签

1. 页面进入该页签时再调 `GET /companies/{company_id}/relationship-graph`
2. 若 `node_count=0` 且 `edge_count=0`，优先展示 `message`
3. 若返回非空 `nodes` / `edges`，直接渲染图组件

## 4. 空数据与错误语义约定

### 200 空数据

以下接口在“公司存在但该模块暂无数据”时，优先返回 `200`，并保持结构稳定：

- `/companies/{company_id}/analysis/summary`
- `/companies/{company_id}/industry-analysis`
- `/companies/{company_id}/industry-analysis/quality`
- `/companies/{company_id}/industry-analysis/periods`
- `/companies/{company_id}/relationship-graph`

前端可以依赖的处理方式：

- 列表字段仍然返回 `[]`
- 计数字段仍然返回 `0`
- 可空对象返回 `null`
- 若有空状态提示，优先看 `message` 或 `quality_warnings`

### 404

用于资源不存在：

- `company_id` 不存在
- 显式指定的 `reporting_period` 不存在
- 显式指定的变化分析 period 不存在

### 400

用于参数不合法：

- 路径参数类型错误
- 必填 query 参数缺失
- query/body 校验失败

错误响应统一为：

```json
{
  "detail": "path.company_id: Input should be a valid integer"
}
```

## 5. 推荐 demo company_id

以下样本公司适合用于最终演示，不同公司覆盖不同亮点：

### `9717` Atlantic Commerce Corporation

适合展示：

- 控制链较完整
- 关系图节点/边较多
- 国别归属明确
- 多业务线

简述：

- `controller_count=6`
- `actual_control_country=Singapore`
- `business_segment_count=3`

### `128` Liberty Telecom Group Inc.

适合展示：

- 多业务线
- 有报告期历史
- 有结构变化
- 质量较干净，适合“正常样例”

简述：

- `available_reporting_periods=['2025Q4', '2025']`
- `business_segment_count=2`
- `quality_warnings=[]`

### `240` Northstar Telecom Inc.

适合展示：

- 多业务线
- 有报告期历史
- 有变化分析
- 控制分析和产业分析都比较完整

简述：

- `controller_count=3`
- `available_reporting_periods=['2025Q4', '2025']`
- `business_segment_count=3`

### `8` Crescent Semiconductor Holdings Inc.

适合展示：

- 有报告期历史
- 有明显结构变化
- 有质量 warnings
- 适合演示“分析结果 + warning 提示”组合

简述：

- `available_reporting_periods=['2025Q4', '2025']`
- `business_segment_count=3`
- `quality_warnings` 包含无 primary segment 提示

### `170` Shengda Securities Industrial Group Co., Ltd.

适合展示：

- 关系图较丰富
- 国别归属明确
- 有变化分析
- 有质量 warnings

简述：

- `actual_control_country=China`
- `available_reporting_periods=['2025Q4', '2025']`
- `quality_warnings` 包含无 primary segment 提示

## 6. 前端实现建议

- 首屏只用 `/analysis/summary`，不要一开始并发把所有接口都打满。
- `industry-analysis/quality` 更适合做提示层，不建议替代主分析接口。
- `industry-analysis/change` 依赖双 period，建议仅在用户切到历史/变化面板时加载。
- `relationship-graph` 数据量相对更大，建议按页签懒加载。
