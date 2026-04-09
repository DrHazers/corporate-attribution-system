# Corporate Attribution System 前端设计规划文档

## 一、文档目的

本文档用于明确 **Corporate Attribution System（企业国别归属与业务结构分析系统）** 的前端设计目标、页面结构、模块划分、交互方式、接口对接思路与后续迭代方向，为后续前端开发和展示层接入提供统一参考。

当前项目后端已经具备较成熟的分析能力，包括：

- 企业基础信息管理
- 控制链分析
- 实际控制人识别
- 国别归属推断
- 多业务线产业分析
- 产业分类映射
- 报告期维度读取
- 跨期业务结构变化分析
- 数据质量检查
- 留痕追踪
- 统一分析总览聚合

因此，前端建设的目标不再是单纯做 CRUD 页面，而是围绕“**企业综合分析展示**”进行设计。

---

## 二、前端建设目标

前端的核心目标包括：

1. 为研究人员提供清晰的企业分析结果展示界面
2. 将后端已有的控制分析、国别归属和产业分析能力可视化
3. 支持查看分析结论、分析依据、控制路径与历史变化
4. 支持对业务线与产业分类进行人工修订
5. 为后续答辩演示、论文截图和系统展示提供完整界面支撑

前端整体定位为：

**面向产业研究场景的企业综合分析与征订管理界面**

---

## 三、设计原则

### 1. 分析结果优先
前端应重点展示分析结果，而不是优先展示底层表数据。

### 2. 综合展示优先
尽量以“企业”为中心组织界面，而不是把控制链、国别归属、产业分析割裂成完全独立的系统。

### 3. 可解释性优先
对于控制分析和国别归属，前端不仅展示结论，还要展示路径、依据、类型和辅助说明。

### 4. 时间维度清晰
产业分析已支持报告期和跨期对比，因此前端必须体现“当前期 / 历史期 / 对比期”的概念。

### 5. 渐进式建设
先完成展示型页面，再逐步补充人工修订、编辑、留痕查看和更复杂的图交互。

---

## 四、建议技术方案

本阶段建议采用较轻量且易落地的前端方案：

### 推荐栈
- 前端框架：Vue 3 或 React
- UI 组件库：Element Plus（Vue）或 Ant Design（React）
- 路由：Vue Router / React Router
- 请求库：Axios
- 图展示：
  - 初期可直接嵌入后端生成的 HTML 图
  - 后续可升级为前端图组件（如 ECharts Graph、Cytoscape.js）

### 推荐原因
- 组件丰富，适合快速搭建管理与分析页面
- 表格、抽屉、标签页、表单、时间选择器等功能成熟
- 适合后续扩展 CRUD + 分析展示混合型系统

---

## 五、系统前端总体结构设计

建议采用如下页面层级：

```text
前端系统
├─ 首页 / Dashboard
├─ 企业列表页
├─ 企业详情页
│  ├─ 基础信息
│  ├─ 综合分析总览
│  ├─ 控制链分析
│  ├─ 国别归属分析
│  ├─ 产业分析
│  ├─ 产业变化分析
│  ├─ 数据质量检查
│  └─ 留痕与征订记录
├─ 业务线管理页
├─ 分类映射管理页
└─ 预留：系统管理 / 数据导入 / 批量重算
```

---

## 六、核心页面规划

## 6.1 首页 / Dashboard

### 页面目标
展示系统定位、模块入口和若干统计摘要，作为演示首页和导航页。

### 建议展示内容
- 系统标题与简介
- 功能模块入口卡片
- 企业总数（后续可补）
- 已完成分析的企业数（后续可补）
- 最近查看企业（可后续实现）
- 快速搜索企业入口

### 作用
- 提升系统完整度
- 适合作为答辩展示第一页
- 为进入企业分析流程提供统一入口

---

## 6.2 企业列表页

### 页面目标
展示企业基础列表，并支持进入企业详情页。

### 建议字段
- 公司名称
- 股票代码
- 注册地
- 上市地
- 总部
- 操作列（查看详情）

### 建议功能
- 关键词搜索（公司名 / 股票代码）
- 分页
- 点击行进入详情页
- 可预留筛选条件（注册地、上市地、是否已完成分析）

### 页面价值
这是用户进入分析页面的主要入口。

---

## 6.3 企业详情页

企业详情页应作为系统最核心的页面，建议采用：

- 顶部基础信息卡片
- 中部 Tab 标签页
- 各分析模块分区展示

推荐标签页结构：

1. 综合分析总览
2. 控制链分析
3. 国别归属
4. 产业分析
5. 产业变化分析
6. 数据质量
7. 留痕记录

---

## 七、综合分析总览页设计

## 7.1 页面定位

该页对应后端：

- `GET /companies/{company_id}/analysis/summary`

作为企业详情页默认第一页。

### 展示目标
把企业最重要的分析结论集中展示，避免用户一进来就面对大量细节。

### 页面结构建议

#### 1）企业基础信息卡片
展示：
- 公司名称
- 股票代码
- 注册地
- 上市地
- 总部
- 公司描述

#### 2）控制分析摘要卡片
展示：
- 是否识别出实际控制人
- 实际控制人名称
- 控制类型
- 控制比例 / 控制得分
- 是否存在联合控制
- 是否存在特殊控制结构标记

#### 3）国别归属摘要卡片
展示：
- 实际控制地国别
- attribution_type
- 是否为 fallback 结果
- 推断依据摘要

#### 4）产业分析摘要卡片
展示：
- 当前报告期
- 主产业标签
- 全部产业标签
- primary / secondary / emerging 数量
- 是否存在人工修订
- 是否存在质量警告

### 设计重点
- 用卡片而不是原始 JSON
- 每个模块提供“查看详情”按钮跳转到对应标签页
- 让用户在一个页面先看结论，再决定看细节

---

## 八、控制链分析页设计

## 8.1 页面目标

用于展示企业控制分析结果、实际控制人信息和控制路径。

### 对应后端能力
- 控制分析读取接口
- control_relationships 结果表
- 图展示支撑
- refresh 重算机制

### 页面模块建议

#### 1）控制结论概览区
展示：
- 实际控制人
- 控制主体类型
- 控制类型
- 控制比例 / 得分
- 是否实际控制人
- basis / review_status（若有）

#### 2）控制路径列表区
展示字段建议：
- 控制主体名称
- 控制主体类型
- 控制方式
- 控制比例 / 得分
- 控制路径
- 是否为实际控制人
- basis

可以采用：
- 表格展示
- 支持展开查看完整 path
- 支持复制路径文本

#### 3）控制关系图展示区
初期方案：
- 直接嵌入后端生成的 HTML 图
- 或提供“打开图谱”按钮

后续方案：
- 前端自己渲染图谱
- 支持缩放、节点点击、路径高亮、图例说明

### 设计重点
- 先保证“能看懂”
- 再逐步增强“能交互”
- 图只是辅助，结论表格必须始终清晰可读

---

## 九、国别归属分析页设计

## 9.1 页面目标

展示企业最终国别归属结论及其依据。

### 展示内容建议

#### 1）归属结论卡片
- 注册地国别
- 上市地国别
- 实际控制地国别
- attribution_type
- source_mode
- 是否人工修订

#### 2）归属依据说明区
展示：
- 推断依据 basis
- 实际控制主体国别来源
- 是否引用 mapped company 的注册地
- 是否 fallback 到 incorporation_country

#### 3）关联控制链摘要区
展示：
- 实际控制人
- 控制路径摘要
- 控制方式摘要

### 页面价值
这是项目主题中“企业实际国别归属”最核心的展示页之一，建议在视觉上突出“注册地 / 上市地 / 实控地”的差异对比。

可采用三列对比卡片：

- 注册地
- 上市地
- 实际控制地

如果三者不同，页面效果会非常直观，适合答辩演示。

---

## 十、产业分析页设计

## 10.1 页面目标

展示某公司在某一报告期下的业务线结构与产业分类结果。

### 对应后端接口
- `GET /companies/{company_id}/industry-analysis`
- `GET /companies/{company_id}/industry-analysis/periods`

### 页面模块建议

#### 1）报告期选择器
- 下拉选择 reporting_period
- 默认选 latest_reporting_period
- 切换后刷新页面内容

#### 2）产业分析摘要区
展示：
- 当前报告期
- 可用报告期列表
- 最新报告期
- 主产业标签
- 全部产业标签
- 是否存在人工修订
- data_completeness
- structure_flags
- quality_summary

#### 3）业务线结构表格
建议字段：
- 业务线名称
- segment_type
- revenue_ratio
- profit_ratio
- description
- source
- confidence
- 是否 current

#### 4）分类映射展示
建议展示每个业务线对应的：
- standard_system
- level_1
- level_2
- level_3
- level_4
- is_primary
- mapping_basis
- review_status

可以采用：
- 业务线卡片 + 下挂分类标签
- 或主表 + 可展开子表

### 设计重点
产业分析页的重点是：
- 看清企业有哪些业务线
- 哪些是 primary
- 映射到了哪些标准产业分类
- 当前这期的产业结构是否完整、可信

---

## 十一、产业变化分析页设计

## 11.1 页面目标

展示同一企业两个报告期之间的业务结构变化。

### 对应后端接口
- `GET /companies/{company_id}/industry-analysis/change`

### 页面模块建议

#### 1）对比期选择区
- previous_period 下拉框
- current_period 下拉框
- 点击“开始对比”

#### 2）变化摘要卡片
展示：
- 是否主产业发生变化
- previous_primary_industries
- current_primary_industries
- change_summary

#### 3）变化明细区
建议分组展示：
- 新增业务线
- 移除业务线
- 升级为 primary
- 取消 primary
- 新增 emerging
- 移除 emerging

### 页面价值
这个页面能体现系统不仅能“静态展示”，还能“动态识别业务演变”，非常适合作为展示亮点。

---

## 十二、数据质量检查页设计

## 12.1 页面目标

展示产业分析数据质量问题，帮助研究人员快速发现需要修订的地方。

### 对应后端接口
- `GET /companies/{company_id}/industry-analysis/quality`

### 建议展示内容
- has_primary_segment
- has_classifications
- duplicate_segment_names
- segments_without_classifications
- primary_segments_without_classifications
- segments_with_multiple_primary_classifications
- warnings
- quality_summary

### 展示方式建议
- 顶部给出整体状态标签：
  - 良好
  - 需检查
  - 存在明显问题
- 下方按问题类型分块列出明细

### 页面意义
这个页面可以让系统更像一个“研究辅助工具”，而不只是分析结果展示工具。

---

## 十三、留痕与征订记录页设计

## 13.1 页面目标

展示人工修改痕迹和征订记录。

### 对应后端接口
- `GET /business-segments/{segment_id}/annotation-logs`
- `GET /business-segment-classifications/{classification_id}/annotation-logs`

### 展示字段建议
- target_type
- target_id
- action_type
- old_value
- new_value
- reason
- operator
- created_at

### 页面建议
可以放在两处：
1. 企业详情页中的“留痕记录”标签
2. 业务线详情 / 分类映射详情的抽屉中

### 作用
- 体现“征订系统”的特点
- 体现审计与版本思路
- 适合作为论文和答辩中的系统特色点

---

## 十四、业务线管理页设计

## 14.1 页面目标

用于对某公司业务线数据进行录入、编辑和删除。

### 主要功能
- 新增业务线
- 修改业务线
- 删除业务线
- 查看业务线详情
- 跳转查看该业务线相关 classification 与 annotation logs

### 表单字段建议
- segment_name
- segment_type
- revenue_ratio
- profit_ratio
- description
- source
- reporting_period
- is_current
- confidence

### 设计说明
这一页偏管理页，建议和企业详情页中的产业分析展示页分开：
- 展示页重在看结果
- 管理页重在维护数据

---

## 十五、分类映射管理页设计

## 15.1 页面目标

用于维护业务线与标准产业分类之间的映射关系。

### 主要功能
- 新增分类映射
- 编辑分类映射
- 删除分类映射
- 查看映射留痕

### 建议字段
- standard_system
- level_1
- level_2
- level_3
- level_4
- is_primary
- mapping_basis
- review_status

### 设计重点
- 允许一个业务线有多个分类映射
- 但要清楚标识 primary 分类
- 对 review_status 做醒目标记

---

## 十六、前端路由规划建议

建议路由如下：

```text
/
 /dashboard
 /companies
 /companies/:id
 /companies/:id/summary
 /companies/:id/control
 /companies/:id/country
 /companies/:id/industry
 /companies/:id/industry-change
 /companies/:id/quality
 /companies/:id/logs
 /business-segments
 /business-segments/:id
 /classifications
 /classifications/:id
```

如果想先简化，也可以先采用：

```text
/companies
/companies/:id
```

然后在企业详情页中使用 Tabs 承载所有子模块。

---

## 十七、组件拆分建议

建议至少拆出以下通用组件：

### 基础组件
- `CompanyBasicCard`
- `SummaryStatCard`
- `StatusTag`
- `EmptyState`
- `SectionHeader`

### 分析组件
- `ControlSummaryCard`
- `ControlPathTable`
- `CountryAttributionCard`
- `IndustrySummaryCard`
- `IndustrySegmentTable`
- `IndustryClassificationTable`
- `IndustryChangePanel`
- `QualityWarningPanel`
- `AnnotationLogTable`

### 交互组件
- `ReportingPeriodSelector`
- `ComparePeriodSelector`
- `EditSegmentDialog`
- `EditClassificationDialog`

这样有利于后续维护和答辩前快速调整界面。

---

## 十八、接口对接建议

## 18.1 对接策略

前端对接时建议遵循以下顺序：

### 第一阶段：只读展示优先
优先对接：
- 企业列表
- 企业详情
- analysis/summary
- industry-analysis
- industry-analysis/change
- industry-analysis/quality
- 控制链读取接口
- 国别归属读取接口

先把展示做出来。

### 第二阶段：补充编辑能力
再接入：
- business_segments CRUD
- business_segment_classifications CRUD
- annotation_logs 查询

### 第三阶段：补充重算与高级交互
后续再考虑：
- refresh 重算按钮
- 图交互增强
- 批量处理入口

---

## 十九、展示优先级建议

为了尽快形成一个“能演示、能截图、能答辩”的系统，建议前端建设优先级如下：

### P0：必须先做
1. 企业列表页
2. 企业详情页整体骨架
3. 综合分析总览页
4. 控制链分析页
5. 国别归属页
6. 产业分析页

### P1：第二步做
1. 产业变化分析页
2. 数据质量检查页
3. 留痕记录页

### P2：后续增强
1. 业务线管理页
2. 分类映射管理页
3. 图谱前端交互增强
4. 批量分析入口
5. Dashboard 数据统计增强

---

## 二十、答辩展示建议

从答辩展示效果考虑，前端页面建议优先保证以下几个亮点：

### 1. 企业详情首页要“像一个分析系统”
不是简单表格堆积，而是：
- 顶部公司卡片
- 中间分析摘要卡片
- 下方详情标签页

### 2. 国别归属差异展示要直观
建议突出：
- 注册地
- 上市地
- 实际控制地

三者差异是项目主题的核心亮点。

### 3. 控制链页要能看到路径
即便图谱不够炫，至少要有清楚的路径表格。

### 4. 产业分析页要体现“报告期”
这样能体现系统不是静态标签系统，而是有时间维度的分析系统。

### 5. 产业变化页要做成亮点页
因为“跨期变化识别”是很好的展示点，容易打动老师。

---

## 二十一、当前阶段的推荐落地方案

结合目前项目情况，建议前端第一版采用如下策略：

### 第一版目标
实现一个“单公司综合分析展示原型”。

### 第一版页面范围
- 企业列表页
- 企业详情页
  - 综合分析总览
  - 控制链分析
  - 国别归属
  - 产业分析
  - 产业变化分析
  - 数据质量检查

### 第一版特点
- 先不追求复杂权限系统
- 先不追求复杂批量导入
- 先不追求复杂图编辑
- 优先完成展示与说明能力

这样最适合当前阶段推进，也最符合毕业设计节奏。

---

## 二十二、后续扩展方向

后续前端可逐步扩展：

1. 控制链图谱前端重绘与交互增强
2. 企业对比分析页
3. 批量企业分析面板
4. 人工征订工作台
5. 版本对比与历史回溯
6. 分析结果导出 PDF / Excel
7. 研究报告生成页

---

## 二十三、总结

当前项目前端不应再按普通后台管理系统思路设计，而应围绕“企业综合分析展示”来组织。

前端核心应服务于以下三条主线：

1. 控制链分析与实际控制人展示
2. 实际国别归属识别结果展示
3. 多业务线产业结构与变化分析展示

因此，前端第一阶段最合理的建设路径是：

**以企业详情页为中心，先完成综合分析展示，再逐步补充征订与管理能力。**

这将与当前后端已完成的分析能力形成良好闭环，也最适合后续答辩演示、论文截图和系统完善。
