# 本科毕业论文项目综述：企业国别归属与业务结构征订系统

本文档面向本科毕业论文写作，基于当前仓库真实代码、数据库结构、API、前端页面、测试与脚本进行系统梳理。若历史设计文档、README、前端预留文案与代码不一致，应以当前代码实现为准。

## 1. 项目名称、定位与应用场景

从当前代码看，项目后端应用标题为：

- `Corporate Attribution System`

结合当前功能，更适合在论文中使用的中文名称是：

- 企业国别归属与业务结构征订系统

系统定位是一个面向研究与分析场景的企业分析平台，主要服务于：

- 企业实际控制关系识别
- 企业实际控制国别归属判定
- 企业业务线结构整理
- 产业分类修订与人工征订

适用场景更偏向：

- 产业研究
- 企业控制权分析
- 企业国别归属研究
- 业务结构整理与辅助标注

而不是实时互联网数据服务平台。

## 2. 当前系统解决的核心问题

当前仓库中已经形成的核心问题域主要有两条：

### 2.1 控制关系与国别归属

围绕公司、股东实体、股东关系，系统当前可以：

- 建模股权/协议/治理类控制关系
- 分析多层控制链
- 区分 direct controller、actual controller、leading candidate
- 支持一定程度的 ultimate controller 上推
- 输出企业实际控制国别
- 在无明确信号时回落到注册地

### 2.2 业务结构与产业分类征订

围绕业务线与分类结果，系统当前可以：

- 维护企业业务线事实
- 按业务线类型组织企业业务结构
- 将业务线映射到 GICS 分类
- 对分类结果进行质量检查
- 支持人工确认、修订与留痕
- 在前端统一展示企业控制结果与产业结果

## 3. 当前已实现的总体架构

### 3.1 后端

后端采用：

- Python
- FastAPI
- SQLAlchemy
- Pydantic

主要目录结构为：

- `backend/api/`：接口层
- `backend/crud/`：数据库 CRUD 层
- `backend/models/`：ORM 模型层
- `backend/schemas/`：数据 schema 层
- `backend/analysis/`：分析算法与聚合逻辑层
- `backend/tasks/`：批量重算任务
- `backend/visualization/`：HTML 可视化辅助

### 3.2 数据库

当前默认应用数据库是 SQLite。相关默认配置位于：

- `backend/database.py`
- `backend/database_config.py`

默认应用库名是：

- `ultimate_controller_enhanced_dataset_industry_working.db`

代码中安装了 `psycopg2-binary`，因此从依赖层面看支持 PostgreSQL URL，但当前仓库默认运行与测试主路径仍以 SQLite 为主。

### 3.3 前端

前端采用：

- Vue 3
- Vue Router
- Vite
- Axios
- Element Plus
- ECharts

入口与页面主要在：

- `frontend/src/views/CompanyAnalysisView.vue`
- `frontend/src/views/IndustryWorkbenchView.vue`

### 3.4 分析模块协作关系

当前主要协作链路为：

1. 前端按公司查询
2. 后端读取或刷新控制分析与国别归属结果
3. 后端读取并聚合业务线与产业分析结果
4. `GET /companies/{company_id}/analysis/summary` 返回统一摘要
5. 前端按模块展示公司总览、控制链、控制关系表、产业分析结果

## 4. 当前主要技术栈

### 4.1 后端技术

- Python 3
- FastAPI
- SQLAlchemy 2.x
- Pydantic 2.x
- Uvicorn

### 4.2 数据处理与验证

- SQLite
- 可选 PostgreSQL 驱动依赖
- Pandas
- NetworkX
- Pytest

### 4.3 前端技术

- Vue 3
- Vite
- Vue Router
- Axios
- Element Plus
- ECharts

### 4.4 LLM 相关

当前仓库存在：

- `openai` 依赖
- `DeepSeekChatClient` 调用路径

但大模型能力当前主要用于产业分类建议与辅助，而不是整个系统所有主功能都依赖大模型。

## 5. 当前数据库分层

结合当前表结构，可以把数据库分为四层。

### 5.1 基础事实层

主要包括：

- `companies`
- `shareholder_entities`
- `shareholder_structures`
- `relationship_sources`
- `business_segments`

这层保存企业基础信息、控制关系原始事实和业务线原始事实。

### 5.2 算法结果层

主要包括：

- `control_relationships`
- `country_attributions`
- `control_inference_runs`
- `control_inference_audit_log`

这层保存控制分析和国别归属的自动推断结果及审计信息。

### 5.3 产业分析扩展层

主要包括：

- `business_segment_classifications`

这层保存业务线分类映射结果。

### 5.4 人工征订 / 留痕层

主要包括：

- `manual_control_overrides`
- `annotation_logs`

这层保存人工确认、覆盖、判断、恢复和业务线/分类变更留痕。

## 6. 当前主要功能模块

### 6.1 企业基础信息管理

相关实现位于：

- `backend/models/company.py`
- `backend/crud/company.py`
- `backend/api/company.py`

当前已实现基础 CRUD 与按公司读取分析结果。

### 6.2 股权 / 控制关系建模

相关实现位于：

- `backend/models/shareholder.py`
- `backend/crud/shareholder.py`
- `backend/api/shareholder.py`

当前已支持：

- 股东实体建模
- 关系边建模
- 股权、协议控制、董事会控制、投票权安排、nominee、VIE 等关系类型

### 6.3 控制链分析

相关核心实现位于：

- `backend/analysis/control_inference.py`
- `backend/analysis/ownership_penetration.py`
- `backend/analysis/control_chain.py`

当前默认主算法是 unified control inference，支持多层路径搜索、去环、路径聚合与混合控制信号分析。

### 6.4 实际控制人识别

当前已实现：

- direct controller 识别
- actual controller 识别
- leading candidate 保留
- 一定程度的 ultimate controller 上推
- joint control 识别
- nominee / trust / beneficial owner disclosure 等复杂场景的部分支持

但当前不宜写成“完全自动解决所有复杂受益所有人识别问题”。

### 6.5 企业实际控制国别判定

当前已实现：

- 基于实际控制主体国别的归属判定
- 取控制主体实体 `country`，必要时取其映射公司注册地
- 在无有效控制人时回落到目标公司 `incorporation_country`

当前未正式实现：

- 以上市地或总部地为后端主回退规则

### 6.6 控制链可视化

当前有两类可视化能力：

- 前端结构图与关系图展示
- 后端基于 `NetworkX + PyVis` 生成 HTML 验证图

相关位置包括：

- `frontend/src/components/ControlStructureDiagram.vue`
- `backend/analysis/ownership_graph.py`
- `backend/visualization/control_graph.py`
- `scripts/build_demo_visualizations.py`

### 6.7 人工征订与结果校正

控制结果的人工作业主要位于：

- `backend/analysis/manual_control_override.py`
- `backend/models/manual_control_override.py`
- `backend/api/company.py`

当前已支持：

- 确认自动结果
- 人工覆盖控制人和国别
- 人工判断候选控制人
- 恢复自动结果

前端默认读取的 `current` 层结果，可能是自动结果与人工覆盖合成后的当前有效结果。

### 6.8 业务线与产业分类分析

核心实现位于：

- `backend/analysis/industry_analysis.py`
- `backend/analysis/industry_classification.py`
- `backend/analysis/industry_workbench.py`
- `backend/api/industry_analysis.py`

当前已支持：

- 业务线事实管理
- 规则型 GICS 分类刷新
- LLM 辅助分类建议与确认
- 分类质量检查
- 历史期间结构变化分析
- 临时工作台分析

### 6.9 测试、导入、刷新和验证脚本

当前仓库有较完整的测试和脚本层，主要包括：

- `tests/test_control_inference_engine.py`
- `tests/test_terminal_controller_v2.py`
- `tests/test_mixed_control_paths.py`
- `tests/test_trust_control_rules.py`
- `tests/test_recompute_analysis_results.py`
- `tests/test_industry_classification_refresh.py`
- `scripts/import_raw_dataset.py`
- `scripts/import_industry_analysis_csvs.py`
- `scripts/run_industry_classification_refresh.py`
- `scripts/run_large_control_validation.py`
- `scripts/build_demo_visualizations.py`

## 7. 当前前端页面结构与用户使用流程

### 7.1 页面结构

路由定义位于：

- `frontend/src/router/index.js`

当前主要页面为：

- `/company-analysis`：公司分析主页面
- `/industry-workbench`：产业分析工作台页面

### 7.2 公司分析主页面

`CompanyAnalysisView.vue` 当前会读取：

- 公司基础信息
- 当前控制分析
- 当前国别归属
- 自动控制分析
- 自动国别归属
- 关系图数据
- 产业分析结果

并组织为多个组件展示：

- `CompanyOverviewCard.vue`
- `ControlSummaryCard.vue`
- `ControlStructureDiagram.vue`
- `ControlRelationsTable.vue`
- `IndustryAnalysisPanel.vue`
- `IndustryWorkbenchDrawer.vue`

### 7.3 用户典型流程

当前真实用户流程大致为：

1. 选择或输入公司
2. 查看公司概览
3. 查看当前控制关系摘要和控制结构图
4. 查看控制关系表，必要时做人工确认/人工判断
5. 查看产业分析结果和业务线结构
6. 对正式业务线发起 LLM 分类建议或确认
7. 如需试验性分析，可打开 Industry Workbench 做临时规则/LLM 测试

## 8. 当前测试与验证情况

### 8.1 pytest 测试

当前测试覆盖主要包括：

- 控制推断核心逻辑测试
- 控制链 API 测试
- 国别归属 API 测试
- 混合控制路径测试
- trust / nominee / joint control / protective rights 测试
- 批量重算与结果保留测试
- 产业分类刷新测试
- 导入库 API 测试

### 8.2 脚本验证

当前脚本可用于：

- 原始数据导入
- 业务线 CSV 导入
- 控制分析批量刷新
- 中大型样本验证
- 结果摘要输出
- HTML 图可视化输出

### 8.3 样本与输出文件

`tests/output/`、`tests/output_demo_graphs/` 等目录中当前保留了：

- JSON 验证摘要
- Markdown 验证摘要
- SQLite 验证库
- 多个公司可视化 HTML

因此论文中可以说：

- 当前项目具有测试样本、批量验证脚本与可视化验证产物

但不宜把这表述成完整的工业级自动化评测平台。

## 9. 当前项目可以写进论文的重点内容

更适合写进论文的重点包括：

- 基于企业控制关系图的统一控制链推断
- 股权与非股权控制信号混合分析
- 直接控制、实际控制、最终控制与候选控制人的分层建模
- 国别归属与控制链分析的联动
- 自动结果层与人工征订层的结合
- 业务线事实层、分类结果层、留痕层的分层设计
- 基于规则的 GICS 分类映射与人工确认机制
- 前后端一体化展示与验证闭环

## 10. 当前项目不应夸大的内容

以下内容当前不宜在论文中夸大为“已实现”：

- 并未实现全球实时数据抓取
- 并未实现全自动年报解析与业务线抽取
- 并未使用图数据库，当前主要仍是关系型数据库 + 内存图分析
- 并未实现大规模生产级部署
- 并非所有页面读取都实时重算算法
- 并非所有复杂 nominee / trust / hidden beneficial owner 场景都能完全自动解析
- 并未正式实现以上市地、总部地为后端主回退规则的国别判定
- Industry Workbench 并不是正式入库生产流

## 11. 适合后续论文写作的章节建议与主线建议

### 11.1 推荐主线

建议把论文主线组织为：

1. 问题背景  
   企业控制关系复杂、国别归属存在多层穿透与非股权控制问题，业务结构也需要标准化整理
2. 系统需求与总体设计  
   说明为何同时建设控制归属模块和业务结构征订模块
3. 数据模型设计  
   介绍公司、股东实体、股东关系、控制结果、国别结果、业务线、分类结果、人工留痕
4. 控制链分析与国别归属算法实现  
   重点写 unified 主算法、direct/actual/ultimate 分层、fallback 规则和审计留痕
5. 业务结构征订与产业分类实现  
   重点写业务线表、规则型 GICS 分类、人工确认与留痕
6. 前端展示与交互流程  
   说明一屏分析页、控制图、控制关系表和产业分析面板
7. 测试与案例验证  
   用 pytest、批量验证脚本、HTML 可视化样本支撑
8. 局限性与改进方向  
   明确当前未实现的自动化能力和工程化边界

### 11.2 推荐重点

建议重点写：

- 统一控制推断而非单纯股权穿透
- 自动分析与人工征订结合
- 控制归属与业务结构分析在同一系统中的协同展示

### 11.3 推荐弱化

建议弱化：

- “大模型驱动”表述
- “全自动”表述
- “生产级大规模部署”表述

## 12. 论文写作时建议强调 / 弱化内容清单

### 12.1 建议强调

- 当前系统已形成可运行的企业控制关系分析主链
- 默认主算法已能处理股权与非股权控制的混合信号
- 结果能落库、可审计、可前端展示、可人工纠偏
- 产业分析模块已具备业务线整理、规则分类、确认留痕能力
- 仓库内已有测试、脚本和样本验证材料支撑论文写作

### 12.2 建议弱化

- 全球实时数据获取能力
- 年报原文自动抽取能力
- 全自动复杂受益所有人识别能力
- 多数据库、多环境生产部署能力
- 大模型自动替代人工判断的能力

### 12.3 可直接用于论文的总括表述

可表述为：

> 当前项目实现了一个以企业控制关系分析和业务结构征订为核心的研究型系统。系统在后端采用 FastAPI、SQLAlchemy 与关系型数据库组织企业、股东实体和股东关系数据，在分析层以 unified control inference 为默认主算法识别直接控制人、实际控制人及实际控制国别，同时在产业分析侧维护业务线事实、GICS 分类结果和人工留痕。前端基于 Vue/Vite 提供公司总览、控制链展示、控制关系表和产业分析展示页面，并配有测试、导入、刷新和验证脚本。该系统适合在论文中定位为“面向企业控制国别归属与业务结构征订的综合分析系统”，但不宜夸大为面向真实互联网环境的大规模全自动生产平台。
