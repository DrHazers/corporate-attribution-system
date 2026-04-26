# 当前产业分析模块与业务结构征订规则说明

本文档仅基于当前仓库代码、表结构、API 与前端页面整理，重点对应：

- `backend/models/business_segment.py`
- `backend/models/business_segment_classification.py`
- `backend/models/annotation_log.py`
- `backend/schemas/business_segment*.py`
- `backend/schemas/industry_analysis.py`
- `backend/crud/business_segment*.py`
- `backend/crud/annotation_log.py`
- `backend/analysis/industry_analysis.py`
- `backend/analysis/industry_classification.py`
- `backend/analysis/industry_workbench.py`
- `backend/api/industry_analysis.py`
- `frontend/src/views/CompanyAnalysisView.vue`
- `frontend/src/views/IndustryWorkbenchView.vue`
- `frontend/src/components/IndustryAnalysisPanel.vue`
- `frontend/src/components/BusinessSegmentsTable.vue`
- `frontend/src/components/IndustryWorkbenchContent.vue`
- `frontend/src/components/IndustryWorkbenchDrawer.vue`

## 1. 模块定位

当前产业分析模块解决的问题不是“控制链分析”，而是围绕企业业务结构进行整理、展示、分类和人工征订留痕。

它在整个系统中的位置是：

- 控制链 / 国别归属模块回答“谁控制该企业、控制国别是什么”
- 产业分析模块回答“企业当前有哪些业务线、这些业务线被映射到什么产业分类、哪些结果需要人工确认”

两者关系为：

- 属于同一公司分析页面下的并列分析模块
- 在 `backend/analysis/industry_analysis.py` 的 `get_company_analysis_summary()` 中被聚合到同一摘要接口
- 当前并不存在“产业分类结果反向参与控制链计算”的主逻辑

因此论文中更适合把它描述为：

- 企业业务结构整理与产业分类修订模块

而不是控制链算法的一部分。

## 2. 当前涉及的核心表及其与 `companies` 的关系

### 2.1 `business_segments`

`business_segments` 是业务线事实表。

它通过：

- `company_id -> companies.id`

与公司主表关联。一家公司可以有多条业务线记录。

### 2.2 `business_segment_classifications`

`business_segment_classifications` 是业务线分类结果表。

它通过：

- `business_segment_id -> business_segments.id`

与业务线关联。一条业务线可对应一条或多条分类记录，但当前很多流程会保留“当前有效”的主要分类结果。

### 2.3 `annotation_logs`

`annotation_logs` 是人工征订/修改留痕表。

它通过：

- `target_type`
- `target_id`

关联到被操作对象。当前主要服务于：

- `business_segment`
- `business_segment_classification`

的变更留痕，也在控制人工覆盖模块中复用类似思路。

## 3. 各表字段含义与实际用途

### 3.1 `business_segments`

当前模型定义位于 `backend/models/business_segment.py`。

关键字段及用途如下：

- `id`：业务线主键
- `company_id`：所属公司
- `segment_name`：业务线名称，最核心事实输入
- `segment_alias`：业务线别名，用于补充识别
- `segment_type`：业务线类型
- `revenue_ratio`：收入占比
- `profit_ratio`：利润占比
- `description`：业务描述
- `currency`：货币单位
- `source`：数据来源说明
- `reporting_period`：报告期
- `is_current`：是否当前有效
- `confidence`：事实层置信度
- `created_at` / `updated_at`：时间戳

实际作用上：

- 这是分类输入事实，不是分类结果
- 当前页面展示的主营业务、分业务线结构、历史期间对比，都以它为基础

### 3.2 `business_segment_classifications`

模型定义位于 `backend/models/business_segment_classification.py`。

关键字段及用途如下：

- `id`
- `business_segment_id`
- `standard_system`：分类体系名称，当前默认并实际主要使用 `GICS`
- `level_1` ~ `level_4`：四级行业层级
- `is_primary`：是否为主分类
- `mapping_basis`：分类依据文本
- `review_status`：审核/确认状态
- `classifier_type`：分类来源类型
- `confidence`：分类置信度
- `review_reason`：需要复核或确认的原因
- `created_at` / `updated_at`

实际作用上：

- 它是分类结果层，不是原始事实输入
- 既可由规则刷新产生，也可由 LLM 建议确认后写入，也可经人工修改/CRUD 直接写入

### 3.3 `annotation_logs`

模型定义位于 `backend/models/annotation_log.py`。

关键字段包括：

- `target_type`
- `target_id`
- `action_type`
- `old_value`
- `new_value`
- `reason`
- `operator`
- `created_at`

实际作用上：

- 这是人工征订和变更留痕层
- 不是事实输入，也不是正式分类结果
- 它记录“谁对什么对象做了什么变更、变更前后是什么、原因是什么”

## 4. 当前 API / service 如何读取、聚合和返回产业分析数据

### 4.1 聚合分析主函数

当前正式产业分析聚合主函数在 `backend/analysis/industry_analysis.py`，主要包括：

- `get_company_industry_analysis()`
- `_build_industry_analysis_payload()`
- `_build_quality_assessment()`
- `analyze_industry_structure_change()`
- `get_company_analysis_summary()`

### 4.2 正式分析读取逻辑

当前正式公司产业分析读取时，会：

1. 按公司读取 `business_segments`
2. 按段落关联 `business_segment_classifications`
3. 自动选择默认报告期  
   规则是优先当前有效期间，再选最新可用期间
4. 将业务线分组为：
   - `primary_segments`
   - `secondary_segments`
   - `emerging_segments`
   - `other_segments`
5. 生成：
   - `primary_industries`
   - `all_industry_labels`
   - `data_completeness`
   - `structure_flags`
   - `quality_warnings`
   - `quality_summary`

### 4.3 主要接口

`backend/api/industry_analysis.py` 当前提供的正式接口包括：

- `GET /companies/{company_id}/industry-analysis`
- `GET /companies/{company_id}/industry-analysis/periods`
- `GET /companies/{company_id}/industry-analysis/quality`
- `GET /companies/{company_id}/industry-analysis/change`
- `GET /companies/{company_id}/analysis/summary`

以及业务线、分类、日志相关 CRUD / 工具接口：

- `POST /companies/{company_id}/business-segments`
- `GET /companies/{company_id}/business-segments`
- `GET /business-segments/{segment_id}`
- `PUT /business-segments/{segment_id}`
- `DELETE /business-segments/{segment_id}`
- `POST /business-segments/{segment_id}/classifications`
- `GET /business-segments/{segment_id}/classifications`
- `PUT /business-segment-classifications/{classification_id}`
- `DELETE /business-segment-classifications/{classification_id}`
- `GET /business-segments/{segment_id}/annotation-logs`
- `GET /business-segment-classifications/{classification_id}/annotation-logs`

### 4.4 summary 聚合位置

公司总览页常用的一屏接口是：

- `GET /companies/{company_id}/analysis/summary`

其后端实现位于：

- `backend/analysis/industry_analysis.py:get_company_analysis_summary()`

它会把：

- 公司基础信息
- 当前控制分析
- 当前国别归属
- 自动控制分析
- 自动国别归属
- 当前产业分析结果

一起返回给前端。

## 5. 当前是否实现自动行业分类规则

### 5.1 当前已实现：规则型分类刷新

当前仓库并非只有“展示已有分类结果”，而是已经实现一套正式的规则型分类刷新逻辑，核心位于：

- `backend/analysis/industry_classification.py`

正式刷新入口为：

- `refresh_business_segment_classifications()`

接口入口为：

- `POST /industry-analysis/classifications/refresh`

脚本入口为：

- `scripts/run_industry_classification_refresh.py`

因此论文中可以写：

- 当前系统已实现基于规则的业务线到行业分类映射

### 5.2 当前分类规则的真实特点

当前实现不是机器学习分类器，也不是通用 NLP 自动抽取器，而是：

- 面向 `segment_name`、`segment_alias`、`description`
- 辅以公司名称、公司简介、同公司其他业务线文本
- 通过一组手工规则进行分层匹配与评分

它更接近：

- 规则库驱动的文本映射系统

### 5.3 当前未实现或不宜夸大的内容

当前未实现或仅部分支持的内容包括：

- 当前未实现“从年报原文自动抽取业务线事实”的正式链路
- 当前未实现基于机器学习训练集的自动行业分类模型
- 当前未实现大规模自动持续抓取企业文本并端到端分类

因此不能把它写成：

- “已实现自动年报解析与机器学习产业识别”

## 6. 当前支持的业务线类型

`segment_type` 当前在模型、schema 和前端中实际支持的主要类型包括：

- `primary`
- `secondary`
- `emerging`
- `other`

实际含义可概括为：

- `primary`：主营业务线
- `secondary`：次要或重要辅助业务线
- `emerging`：新兴业务线
- `other`：其他业务线

前端与分析汇总会按这四类分开展示。

## 7. 当前支持的分类体系与层级组织

### 7.1 分类体系

当前代码正式使用并默认写入的分类体系是：

- `GICS`

虽然 `standard_system` 是开放字符串字段，但当前规则刷新、LLM 建议、前端展示和测试样例都以 `GICS` 为主。

### 7.2 层级组织

分类结果按以下四级字段组织：

- `level_1`
- `level_2`
- `level_3`
- `level_4`

前端和后端会把它们进一步拼接为可读的 `industry_label` 或标签列表，但数据库中核心仍是这四级结构。

## 8. 当前如何体现人工征订、确认、修订与留痕

### 8.1 `review_status`

当前分类结果中的人工/复核状态主要体现在 `review_status`。当前代码中会出现的状态包括：

- `confirmed`
- `pending`
- `needs_llm_review`
- `needs_manual_review`
- `conflicted`
- `unmapped`

这类状态的作用是：

- 标记分类结果是否稳定
- 标记是否需要人工复核
- 标记当前规则无法可靠落到具体分类

### 8.2 `classifier_type`

当前分类来源类型包括：

- `rule_based`
- `llm_assisted`
- `manual`
- `hybrid`

它回答的是“这条分类结果是怎么来的”，而不是“它是否最终正确”。

### 8.3 `annotation_logs`

当前对业务线与分类的创建、更新、删除会通过 CRUD 逻辑写入 `annotation_logs`。这意味着：

- 人工改动当前有留痕
- 论文中可以把它表述为“支持人工征订与操作记录”

### 8.4 LLM 建议与确认

当前代码中存在两步式 LLM 辅助流程：

- `classify_business_segment_with_llm()`
- `confirm_business_segment_llm_classification()`

对应接口：

- `POST /business-segments/{id}/classify-with-llm`
- `POST /business-segments/{id}/confirm-llm-classification`

其真实含义是：

- 第一步生成建议
- 第二步由用户确认后写为正式分类结果

因此 LLM 当前不是默认正式分类主链，而是辅助建议与确认工具。

### 8.5 `has_manual_adjustment`

在 `industry_analysis.py` 中，`has_manual_adjustment` 是一个前端友好标记。当前实现中，只要选定报告期内存在某些人工/需人工复核状态，就会把该标记设为真。

它是聚合结果字段，不是数据库原始字段。

## 9. 当前前端如何展示产业分析结果

### 9.1 页面入口

正式公司页入口位于：

- `frontend/src/views/CompanyAnalysisView.vue`

临时工作台页入口位于：

- `frontend/src/views/IndustryWorkbenchView.vue`

### 9.2 正式公司页展示内容

正式公司页通过 `IndustryAnalysisPanel.vue`、`BusinessSegmentsTable.vue` 等组件展示：

- 主营业务摘要
- 按 `primary/secondary/emerging/other` 分组的业务线
- 每条业务线对应的分类标签
- 主行业标签集合
- 质量警告与完整性提示
- 历史期间结构变化
- 段落详情与分类详情

### 9.3 LLM 与确认交互

前端 `IndustryAnalysisPanel.vue` 当前支持：

- 对正式业务线请求 LLM 分类建议
- 用户确认该建议并写回正式分类表

这说明：

- 正式业务线可在前端进行“建议 -> 确认”的修订
- 但它仍然不是全自动直接覆盖正式库

### 9.4 Industry Workbench

`IndustryWorkbenchContent.vue` 与 `IndustryWorkbenchDrawer.vue` 当前是一个临时工作台：

- 支持输入临时业务线
- 支持规则分析
- 支持 LLM 辅助分析

但当前真实边界是：

- 工作台结果默认不写入正式 `business_segments` / `business_segment_classifications`
- 前端中“导入正式库”按钮当前仍是占位/未完成状态

因此论文中应把它表述为：

- 临时分析和人工试验工作台

而不是“正式业务线采集入口”。

## 10. 当前模块的边界与不足

### 10.1 当前主要基于结构化输入数据

当前产业分析模块的正式输入前提是：

- `business_segments` 已经存在

也就是说，当前模块主要做的是：

- 结构化业务线数据的展示、分类和修订

而不是自动从原始年报全文抽取业务线。

### 10.2 自动分类是规则型，不是训练型模型

当前自动分类主链是规则库刷新，不是机器学习训练模型，也不是端到端深度学习文本分类。

### 10.3 LLM 是辅助，不是正式默认主链

当前 LLM 功能主要用于：

- 提供建议
- 辅助确认
- 支持临时工作台试验

不能写成“系统默认依赖大模型自动完成产业分类”。

### 10.4 工作台是临时态

当前 `industry_workbench` 不等同于正式业务数据表编辑模块。其真实定位是：

- 临时分析器
- 规则验证器
- LLM 辅助试验器

### 10.5 当前未实现的能力

当前未实现或未形成正式闭环的能力包括：

- 自动从 PDF/年报原文抽取业务线
- 批量自动生成正式业务线并自动入库
- 工作台结果一键稳定导入正式表
- 多分类体系并行正式支持

## 11. 适合论文写作的表述建议

### 11.1 可以强调的内容

- 系统已建立“业务线事实层 + 分类结果层 + 人工留痕层”的结构
- 已实现基于规则的业务线到 GICS 分类映射
- 支持业务线类型分组、主分类判定、质量检查、历史期间结构变化分析
- 支持人工征订、LLM 辅助建议与确认、注释留痕
- 可与公司总览页、控制链分析页形成一体化企业分析界面

### 11.2 不宜夸大的内容

- 不能写成“已自动解析年报形成业务线”
- 不能写成“已实现机器学习或 NLP 全自动行业分类”
- 不能写成“工作台分析结果默认直接写入正式库”
- 不能写成“控制链算法与产业分析算法已深度耦合”

### 11.3 可直接用于论文的简短总结

可表述为：

> 当前项目的产业分析模块以 `business_segments` 为业务事实输入，以 `business_segment_classifications` 为分类结果层，以 `annotation_logs` 为人工留痕层，形成了“业务线整理、行业分类、人工复核与结果展示”闭环。系统已实现基于规则的 GICS 分类刷新，并提供 LLM 辅助建议与人工确认机制，但当前仍主要依赖结构化业务线输入，尚未实现从年报全文到正式业务线结果的全自动抽取与入库。
