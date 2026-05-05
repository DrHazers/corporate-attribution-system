# 项目交接文档：Corporate Attribution System

本文档面向即将接手本项目的新同学，基于当前仓库代码、配置、模型、接口、前端页面、脚本和测试整理。凡是能从代码或当前仓库确认的信息，本文直接写明；无法确认的内容统一标注为“待确认”。

更新时间：2026-05-02

## 1. 项目概述

### 1.1 项目名称与主要目标

项目名称：`Corporate Attribution System`，中文可理解为“企业归属与控制分析系统”。

当前项目更适合定位为一个毕业设计与研究演示型系统，核心目标是围绕目标企业完成两条主线分析：

- 企业控制关系识别、控制链展示与实际控制国别归属判定。
- 企业业务线整理、GICS 产业分类、人工复核和人工修订留痕。

当前系统不是生产级互联网数据抓取平台，也不是完整商业化风控系统。它的重点是把企业、股东主体、控制关系、控制分析结果、国家归属、业务线和产业分类组织成一套可运行、可解释、可展示的闭环。

### 1.2 系统解决的核心问题

系统解决的核心问题是：给定一个 `company_id`，如何基于数据库中的公司主数据、股东主体、股权或语义控制关系，输出目标企业的控制链、候选控制主体、实际控制主体、实际控制国别，并将结果和产业分类结果汇总到前端展示。

具体包括：

- 从 `companies` 定位目标企业。
- 通过 `shareholder_entities.company_id` 找到目标企业在控制图中的实体节点。
- 读取 `shareholder_structures` 构建控制关系图。
- 识别股权控制、协议控制、董事会控制、表决权控制、VIE、代持、信托等不同控制边。
- 输出 `control_relationships` 和 `country_attributions`。
- 读取 `business_segments` 和 `business_segment_classifications` 展示企业业务线与产业分类。
- 允许人工对控制结果和产业分类结果进行修订，并保留留痕。

### 1.3 主要用户与使用场景

主要用户：

- 研究人员：查询企业，查看控制链、实际控制人、实际控制国别、业务线与产业分类。
- 数据整理或标注人员：维护公司基础信息、股东主体、股权和语义控制关系、业务线和分类结果。
- 项目开发维护人员：继续完善算法、接口、前端展示、导入脚本和测试集。
- 答辩或演示使用者：基于典型企业样本展示控制链和产业分析结果。

典型使用场景：

- 在前端搜索企业，进入综合分析页面查看企业基本信息、控制分析、控制结构图和产业分析。
- 调用后端接口刷新某家公司的控制分析结果。
- 对自动识别的实际控制人进行人工确认、人工征订或恢复自动结果。
- 对业务线运行规则分类、调用 DeepSeek 辅助建议，再由人工确认写回正式分类。
- 批量运行脚本刷新或验证大库中的控制分析结果。

### 1.4 当前完成情况与仍需完善部分

已完成并能从代码确认的部分：

- 后端 FastAPI 应用入口和 CORS 配置：`backend/main.py`。
- SQLite 默认数据库连接和自动补列、建索引、历史字段回填：`backend/database.py`、`backend/database_config.py`。
- 公司、股东主体、股东结构、控制关系、国家归属、业务线、产业分类、人工修订、审计运行等 ORM 模型。
- 公司 CRUD、公司搜索、控制链读取和刷新、国家归属读取、关系图、人工控制修订、产业分析、产业工作台等 API。
- 统一控制推断主链路：`backend/analysis/control_inference.py` 和 `backend/analysis/ownership_penetration.py`。
- 规则型业务线分类与 DeepSeek 辅助建议：`backend/analysis/industry_classification.py`。
- 前端 Vue 3 单页应用，包含公司综合分析页和产业工作台页。
- 后端和前端均有测试文件，前端有 `npm run test:manual-paths`，后端有多组 `pytest` 测试。

仍需完善或待确认：

- 生产部署方式待确认。当前仓库主要体现本地开发和演示运行方式。
- Node.js 精确版本待确认。当前 `package.json` 可确认依赖，但本地沙箱未能成功读取 `node --version`。
- 旧文档与当前代码存在数据库默认名差异，后续应统一文档口径。
- `relationship_sources` 和 `entity_aliases` 在当前默认大库中为空，证据来源和别名能力已有模型/API，但数据层仍待补充。
- 业务线分类是规则型为主，不是完整机器学习分类器；物流、工业设备等行业覆盖仍不完整。
- DeepSeek API 依赖外部服务和密钥，网络与密钥配置需单独确认。
- 真实生产级权限、登录、审计流、角色管理、部署监控待确认或未实现。

## 2. 技术栈说明

### 2.1 后端技术栈

后端目录：`backend/`

主要技术：

- Python：本地 venv 查询为 Python 3.12.3。
- FastAPI：`fastapi==0.135.1`。
- Uvicorn：`uvicorn==0.42.0`。
- SQLAlchemy：`SQLAlchemy==2.0.48`。
- Pydantic：`pydantic==2.12.5`。
- Pytest：`pytest==9.0.2`。
- Pandas、NumPy、NetworkX：用于数据处理、图分析和验证脚本。
- OpenAI SDK：`openai==2.6.1`，当前用于兼容方式调用 DeepSeek。
- Pyvis：用于后端 HTML 控制图可视化。

依赖文件：`requirements.txt`。

### 2.2 前端技术栈

前端目录：`frontend/`

主要技术：

- Vue 3：`vue ^3.5.13`。
- Vue Router：`vue-router ^4.5.0`。
- Vite：`vite ^5.4.11`。
- Axios：`axios ^1.8.4`。
- Element Plus：`element-plus ^2.9.7`。
- ECharts：`echarts ^5.6.0`。

依赖文件：`frontend/package.json`、`frontend/package-lock.json`。

前端入口：

- `frontend/src/main.js`
- `frontend/src/App.vue`
- `frontend/src/router/index.js`

### 2.3 数据库与 ORM

当前默认数据存储为 SQLite。代码也安装了 `psycopg2-binary`，并且 SQLAlchemy 理论上可接 PostgreSQL URL，但当前默认运行路径是 SQLite。

当前代码内置默认数据库：

```text
ultimate_controller_enhanced_dataset_industry_working.db
```

配置文件：

- `backend/database_config.py`
- `backend/database.py`

数据库 URL 优先级：

1. 显式环境变量 `DATABASE_URL`。
2. `CORP_DEFAULT_DATABASE_PATH` 指定完整或相对路径。
3. `CORP_DEFAULT_DATABASE_NAME` 指定项目根目录下数据库文件名。
4. 代码内置默认值 `ultimate_controller_enhanced_dataset_industry_working.db`。

ORM 基类与会话：

- `Base = declarative_base()`
- `engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})`
- `SessionLocal = sessionmaker(...)`

注意：`connect_args={"check_same_thread": False}` 是 SQLite 连接参数。如果切换 PostgreSQL，需确认该参数是否需要调整。当前代码未针对非 SQLite 分支做额外适配，属于待确认事项。

### 2.4 其他工具、脚本和第三方服务

脚本目录：`scripts/`

常用脚本：

- `scripts/import_raw_dataset.py`：导入原始数据。
- `scripts/import_industry_analysis_csvs.py`：导入产业分析 CSV。
- `scripts/run_industry_classification_refresh.py`：刷新业务线分类。
- `scripts/run_large_control_validation.py`：批量控制分析验证。
- `scripts/run_refresh_on_enhanced_working_db.py`：刷新增强工作库。
- `scripts/build_demo_visualizations.py`：生成控制图 HTML 可视化。
- `scripts/export_input_csvs.py`、`scripts/export_input_csvs_from_original_copy.py`：导出输入 CSV。
- `scripts/upgrade_db_to_v2.py`、`scripts/verify_db_v2.py`：数据库结构升级和校验相关脚本。

第三方服务：

- DeepSeek：通过 `backend/services/llm/deepseek_client.py` 使用 OpenAI SDK 兼容方式调用。
- 默认模型：`deepseek-chat`。
- Base URL：`https://api.deepseek.com`。
- API Key 配置：
  - 环境变量 `DEEPSEEK_API_KEY`。
  - 或文件路径 `DEEPSEEK_API_KEY_FILE`，默认 `docs/deepseek_api.txt`。
- 超时配置：`DEEPSEEK_TIMEOUT_SECONDS`，默认 45 秒。

## 3. 项目目录结构

根目录主要结构：

```text
.
├── backend/                  # FastAPI 后端、ORM、API、分析逻辑
│   ├── analysis/             # 控制推断、控制链、国家归属、产业分析、人工修订
│   ├── api/                  # FastAPI 路由
│   ├── crud/                 # 数据库 CRUD 封装
│   ├── models/               # SQLAlchemy ORM 模型
│   ├── schemas/              # Pydantic 请求/响应模型
│   ├── services/llm/         # DeepSeek LLM 客户端
│   ├── tasks/                # 批量任务
│   ├── visualization/        # 后端控制图可视化
│   ├── database.py           # SQLAlchemy engine、Session、建表和 SQLite 补列
│   ├── database_config.py    # 默认数据库路径和 URL 解析
│   ├── llm_config.py         # DeepSeek Key 和超时配置
│   └── main.py               # FastAPI 应用入口
├── frontend/                 # Vue 3 前端应用
│   ├── src/api/              # Axios 封装和接口函数
│   ├── src/components/       # 页面组件
│   ├── src/router/           # 前端路由
│   ├── src/utils/            # 图适配、人工路径、产业分析工具函数
│   ├── src/views/            # 页面级组件
│   ├── tests/                # 前端 Node 测试
│   ├── package.json
│   └── vite.config.js
├── docs/                     # 项目文档、算法说明、数据库说明、论文支撑材料
│   ├── thesis_support/       # 论文/答辩支撑材料
│   └── archive/              # 历史文档
├── scripts/                  # 导入、刷新、验证、导出、可视化脚本
├── tests/                    # 后端 pytest 测试
├── data/                     # 数据目录，具体内容待确认
├── exports/                  # 导出结果、交接 CSV、可视化输出等
├── logs/                     # 日志目录
├── requirements.txt          # 后端 Python 依赖
├── README.md                 # 项目说明，当前终端显示存在编码问题
├── PRD.md                    # 项目需求说明，当前终端显示存在编码问题
└── *.db                      # 多个 SQLite 工作库、测试库、备份库
```

关键目录说明：

- `backend/analysis/` 是后端业务核心，不是简单工具目录。控制推断、业务线分类、人工修订合成逻辑都在这里。
- `backend/api/` 是 HTTP 接口层。接口通常只做校验、调用 analysis 或 CRUD，然后返回 Pydantic schema。
- `backend/models/` 是数据库结构核心，新同学理解表关系必须先看这里。
- `frontend/src/views/CompanyAnalysisView.vue` 是当前最重要的前端页面，串起搜索、汇总、关系图、人工复核、产业分析。
- `frontend/src/components/IndustryWorkbenchContent.vue` 是产业工作台核心组件。
- `docs/algorithm_core_code_map.md` 是当前算法代码导览，适合和本文档配合阅读。
- `docs/database_handoff_guide.md` 对输入表和输出表区别说明较清楚，但其中部分文字可能落后于当前代码，需交叉核对。

## 4. 本地运行与部署方式

### 4.1 环境准备

后端：

- Python 3.12.3 已在当前 venv 中确认。
- 推荐使用项目内 `venv`。
- 精确 Python 兼容范围待确认。

前端：

- Node.js 精确版本待确认。
- 依赖以 `frontend/package.json` 和 `frontend/package-lock.json` 为准。

数据库：

- 推荐使用当前代码默认库：

```text
d:/graduation_project/corp_attribution_system/ultimate_controller_enhanced_dataset_industry_working.db
```

该库当前可确认表行数如下：

| 表 | 当前行数 |
| --- | ---: |
| `companies` | 10030 |
| `shareholder_entities` | 27177 |
| `shareholder_structures` | 104112 |
| `relationship_sources` | 0 |
| `entity_aliases` | 0 |
| `control_relationships` | 19141 |
| `country_attributions` | 10050 |
| `business_segments` | 45747 |
| `business_segment_classifications` | 45747 |
| `manual_control_overrides` | 44 |
| `annotation_logs` | 60 |
| `control_inference_runs` | 10030 |
| `control_inference_audit_log` | 23167 |

### 4.2 安装依赖

后端：

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

前端：

```powershell
cd frontend
npm install
```

### 4.3 数据库初始化方式

后端启动时会执行：

```python
@app.on_event("startup")
def on_startup():
    database_module.init_db()
```

`init_db()` 位于 `backend/database.py`，主要做：

- 导入 `backend.models`，保证 ORM 模型注册。
- `Base.metadata.create_all(bind=engine)` 创建缺失表。
- 对 SQLite 执行 `ensure_sqlite_schema()`：
  - 为已有表补充新增字段。
  - 创建索引。
  - 回填关系类型、置信度、分类状态、结果状态等兼容字段。
- 如果使用种子开发库 `company.db` 或 `company_import_test.db`，会调用 `backend/dev_seed.py` 写入开发种子数据。

注意：`create_all` 不等于完整数据库迁移工具。当前项目没有 Alembic。新增字段主要靠 `backend/database.py` 的 SQLite 补列逻辑维护。

### 4.4 后端启动命令

推荐显式指定数据库：

```powershell
$env:DATABASE_URL='sqlite:///d:/graduation_project/corp_attribution_system/ultimate_controller_enhanced_dataset_industry_working.db'
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

健康检查：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health'
```

根接口：

```text
GET http://127.0.0.1:8000/
```

返回：

```json
{"message":"Corporate Attribution System API is running."}
```

### 4.5 前端启动命令

```powershell
cd frontend
npm run dev
```

默认地址：

```text
http://127.0.0.1:5173
```

默认后端地址由 `frontend/src/api/http.js` 决定：

```js
import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
```

如需修改，在 `frontend/.env` 中配置：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### 4.6 常见启动问题与解决办法

1. 前端提示“无法连接后端接口”
   - 检查 FastAPI 是否已启动。
   - 检查 `VITE_API_BASE_URL` 是否指向正确地址。
   - 检查后端 CORS 是否允许前端端口。当前 `backend/main.py` 允许 `5173` 和 `4173`。

2. 接口返回 “Mapped shareholder entity not found for company.”
   - 说明 `companies.id` 存在，但 `shareholder_entities.company_id = companies.id` 的目标实体不存在。
   - 控制算法需要这个实体作为控制图入口。

3. 刷新接口很慢
   - 单公司刷新会跑控制推断和写回。
   - 大库批量刷新请优先用脚本，不要从前端反复触发。

4. README 或历史文档显示乱码
   - 当前终端读取 `README.md`、`PRD.md` 时出现编码显示问题。
   - 新交接以当前源码和本文档为准。

5. 默认数据库名混乱
   - 当前代码默认是 `ultimate_controller_enhanced_dataset_industry_working.db`。
   - 部分旧文档提到 `ultimate_controller_enhanced_dataset_working.db`，属于历史口径，需要后续统一。

6. DeepSeek 相关接口报 400、502 或 504
   - 400 常见于密钥缺失或配置错误。
   - 502 常见于远端 API 调用失败或空响应。
   - 504 常见于 DeepSeek 超时。
   - 检查 `DEEPSEEK_API_KEY` 或 `docs/deepseek_api.txt`。

## 5. 数据库与数据模型说明

### 5.1 主要数据表

公司基础：

- `companies`：目标公司主表。

控制图输入：

- `shareholder_entities`：股东、公司、自然人、机构、基金、政府等主体节点。
- `shareholder_structures`：主体之间的股权、协议、董事会、表决权、VIE、代持等关系边。
- `relationship_sources`：关系边的证据来源。
- `entity_aliases`：主体别名。
- `shareholder_structure_history`：股东结构变更历史。

控制分析输出：

- `control_relationships`：控制候选、直接控制人、实际控制人、终局控制人、路径、得分和依据。
- `country_attributions`：实际控制国别、归属类型、归属层级和依据。
- `control_inference_runs`：每次控制推断运行记录。
- `control_inference_audit_log`：每次控制推断过程中的关键动作和审计日志。

产业分析：

- `business_segments`：公司业务线。
- `business_segment_classifications`：业务线对应的 GICS 分类结果。

人工修订与留痕：

- `manual_control_overrides`：控制结果人工确认、人工征订、人工判定和恢复记录。
- `annotation_logs`：业务线、分类、人工控制结果等操作留痕。

### 5.2 核心表关系

企业基础信息：

- `companies.id` 是公司主键。
- 每个可分析公司通常需要一条 `shareholder_entities.company_id = companies.id` 的映射实体。
- 这条映射实体是控制图中的目标节点。

控制关系：

- `shareholder_structures.from_entity_id` 指向上游控制或持股主体。
- `shareholder_structures.to_entity_id` 指向下游被持股或被控制主体。
- 两者均引用 `shareholder_entities.id`。
- 当前算法主要加载 `is_current = 1`、`is_direct = 1` 且日期有效的边。

控制分析结果：

- `control_relationships.company_id` 引用 `companies.id`。
- `control_relationships.controller_entity_id` 可引用 `shareholder_entities.id`。
- `control_relationships.inference_run_id` 可引用 `control_inference_runs.id`。

国别归属结果：

- `country_attributions.company_id` 引用 `companies.id`。
- `country_attributions.actual_controller_entity_id`、`direct_controller_entity_id` 存主体 ID，但模型中没有显式外键。
- `country_attributions.inference_run_id` 引用 `control_inference_runs.id`。

产业分析：

- `business_segments.company_id` 引用 `companies.id`。
- `business_segment_classifications.business_segment_id` 引用 `business_segments.id`。

人工修订：

- `manual_control_overrides.company_id` 引用 `companies.id`。
- `manual_control_overrides.control_relationship_id` 可引用人工写入的 `control_relationships.id`。
- `manual_control_overrides.country_attribution_id` 可引用人工写入的 `country_attributions.id`。
- `annotation_logs` 使用 `target_type + target_id` 记录操作对象，不是强外键。

### 5.3 重要字段含义

`companies`：

- `name`：公司名称。
- `stock_code`：股票代码或内部代码，唯一。
- `incorporation_country`：注册地。无有效控制人时，国别归属 fallback 会使用。
- `listing_country`：上市地。
- `headquarters`：总部。

`shareholder_entities`：

- `entity_name`：主体名称。
- `entity_type`：`company/person/institution/fund/government/other`。
- `country`：主体国家或地区，实际控制人国家优先取这里。
- `company_id`：当主体映射到某个公司时填写。
- `entity_subtype`：`holding_company/spv/family_vehicle/trust` 等细分类型。
- `ultimate_owner_hint`：是否提示为终局所有人。
- `look_through_priority`：穿透优先级。
- `controller_class`：`natural_person/state/fund_complex/trust_structure` 等控制人类别。
- `beneficial_owner_disclosed`：是否披露受益所有人。

`shareholder_structures`：

- `from_entity_id`：上游主体。
- `to_entity_id`：下游主体。
- `holding_ratio`：持股比例，0 到 100。
- `voting_ratio`：表决权比例。
- `economic_ratio`：经济收益比例。
- `relation_type`：标准关系类型，包含 `equity/agreement/board_control/voting_right/nominee/vie/other`。
- `has_numeric_ratio`：是否有数值比例。
- `is_beneficial_control`：是否受益控制。
- `look_through_allowed`：是否允许继续向上穿透。
- `termination_signal`：终止或阻断信号，如 `joint_control`、`beneficial_owner_unknown`、`protective_right_only`。
- `effective_control_ratio`：有效控制比例，股权边优先参考。
- `control_basis`、`nomination_rights`、`agreement_scope`：非股权语义控制证据文本。
- `relation_metadata`：JSON 扩展字段，例如董事会总席位、表决权等。
- `confidence_level`：证据置信度。
- `effective_date`、`expiry_date`：关系生效和失效日期。
- `is_current`：是否当前有效。

`control_relationships`：

- `controller_name`、`controller_type`：控制主体名称和类型。
- `control_type`：控制类型，如股权控制、混合控制、显著影响等规范化结果。
- `control_ratio`：展示用控制比例。
- `control_path`：控制路径，通常是 JSON 文本。
- `is_actual_controller`：是否被认定为实际控制人。
- `control_tier`：`direct/intermediate/ultimate/candidate`。
- `is_direct_controller`、`is_intermediate_controller`、`is_ultimate_controller`：层级标记。
- `promotion_reason`：向上穿透或上推原因。
- `terminal_failure_reason`：无法认定终局控制人的阻断原因。
- `immediate_control_ratio`、`aggregated_control_score`、`terminal_control_score`：直接比例、聚合得分、终局得分。
- `basis`：JSON 形式的解释依据。
- `control_mode`：`numeric/semantic/mixed`。
- `semantic_flags`：语义控制标签。
- `review_status`：`auto/manual_confirmed/manual_rejected/needs_review` 等。

`country_attributions`：

- `actual_control_country`：实际控制国别。
- `attribution_type`：归属类型。
- `actual_controller_entity_id`：实际控制主体 ID。
- `direct_controller_entity_id`：直接控制主体 ID。
- `attribution_layer`：`direct_controller_country/ultimate_controller_country/fallback_incorporation/joint_control_undetermined`。
- `country_inference_reason`：国家推断原因。
- `look_through_applied`：是否发生穿透。
- `basis`：国家归属解释依据。
- `is_manual`：是否人工结果。
- `source_mode`：`control_chain_analysis/fallback_rule/manual_override/hybrid`。

`business_segments`：

- `segment_name`：业务线名称。
- `segment_alias`：业务线别名。
- `segment_type`：`primary/secondary/emerging/other` 等。
- `revenue_ratio`、`profit_ratio`：收入和利润占比。
- `description`：业务说明。
- `reporting_period`：报告期。
- `is_current`：是否当前有效。

`business_segment_classifications`：

- `standard_system`：默认 `GICS`。
- `level_1` 到 `level_4`：GICS 分级。
- `is_primary`：是否主分类。
- `mapping_basis`：分类依据。
- `review_status`：`confirmed/pending/needs_llm_review/needs_manual_review/conflicted/unmapped` 等。
- `classifier_type`：`rule_based/manual/llm_assisted/hybrid` 等。
- `confidence`：分类置信度。
- `review_reason`：状态原因。

### 5.4 数据写入、刷新和读取流程

基础数据写入：

- 公司：`POST /companies`。
- 股东主体：`POST /shareholders/entities`。
- 股东结构：`POST /shareholders/structures`。
- 业务线：`POST /companies/{company_id}/business-segments`。
- 业务线分类：`POST /business-segments/{segment_id}/classifications`。

控制分析刷新：

1. 调用 `POST /companies/{company_id}/analysis/refresh`。
2. API 调用 `refresh_company_control_analysis()`。
3. 分析层构建控制图上下文，执行统一控制推断。
4. 删除或覆盖旧自动结果，保留人工结果。
5. 写回 `control_relationships`、`country_attributions`、`control_inference_runs`、`control_inference_audit_log`。

读取结果：

- 当前有效层，默认包含人工结果合成：`GET /companies/{company_id}/control-chain`。
- 纯自动层：`GET /companies/{company_id}/control-chain?result_layer=auto`。
- 国家归属同理：`GET /companies/{company_id}/country-attribution` 或 `?result_layer=auto`。
- 前端主入口：`GET /companies/{company_id}/analysis/summary`。

产业分类刷新：

1. 调用 `POST /industry-analysis/classifications/refresh`。
2. 后端执行 `refresh_business_segment_classifications()`。
3. 对 `business_segments` 进行规则匹配。
4. 写回 `business_segment_classifications`，并保护 `manual/llm_assisted/hybrid` 等人工或模型辅助结果。

人工修订：

- 控制结果人工征订：`POST /companies/{company_id}/manual-control-override`。
- 控制结果人工判定候选：`POST /companies/{company_id}/manual-control-judgment`。
- 恢复自动结果：`POST /companies/{company_id}/manual-control-override/restore-auto`。
- 业务线分类人工写回：`POST /business-segments/{segment_id}/manual-classification`。

## 6. 后端模块说明

### 6.1 应用入口

文件：`backend/main.py`

主要职责：

- 创建 FastAPI 应用。
- 配置 CORS，允许本地 Vite 开发和 preview 端口。
- 注册路由：
  - `analysis_router`
  - `company_router`
  - `control_relationship_router`
  - `country_attribution_router`
  - `industry_analysis_router`
  - `shareholder_router`
  - `relationship_support_router`
- 启动时执行 `init_db()`。
- 提供 `/` 和 `/health`。

### 6.2 公司查询与公司维度接口

文件：`backend/api/company.py`

主要接口：

| 接口 | 方法 | 功能 | 主要参数 | 调用场景 |
| --- | --- | --- | --- | --- |
| `/companies` | `POST` | 创建公司 | 请求体 `CompanyCreate` | 写入公司主数据 |
| `/companies` | `GET` | 列出公司 | 无 | 简单列表 |
| `/companies/search` | `GET` | 搜索公司 | `query`、`limit` | 前端搜索框 |
| `/companies/{company_id}` | `GET` | 公司详情 | `company_id` | 公司基本信息 |
| `/companies/{company_id}` | `PUT` | 更新公司 | `CompanyUpdate` | 修改主数据 |
| `/companies/{company_id}` | `DELETE` | 删除公司 | `company_id` | 删除主数据 |
| `/companies/{company_id}/control-chain` | `GET` | 控制链结果 | `refresh`、`result_layer` | 前端控制链展示 |
| `/companies/{company_id}/actual-controller` | `GET` | 实际控制人 | `refresh`、`result_layer` | 单独读取实际控制人 |
| `/companies/{company_id}/country-attribution` | `GET` | 国别归属 | `refresh`、`result_layer` | 国别归属展示 |
| `/companies/{company_id}/analysis/refresh` | `POST` | 刷新控制分析 | `company_id` | 触发重算和写回 |
| `/companies/{company_id}/relationship-graph` | `GET` | 关系图数据 | `company_id` | 前端 ECharts 关系图 |
| `/companies/{company_id}/special-control-relations` | `GET` | 特殊控制关系摘要 | `company_id` | 语义控制辅助展示 |

`result_layer` 说明：

- `current`：默认，读取当前有效结果，可能合成人工修订。
- `auto`：读取自动分析结果，不叠加人工结果。

### 6.3 控制链分析与国别归属接口

文件：`backend/api/analysis.py`

主要接口：

| 接口 | 方法 | 功能 |
| --- | --- | --- |
| `/analysis/control-chain/{company_id}` | `GET` | 控制链分析包装接口，支持 `refresh` 和 `result_layer` |
| `/analysis/country-attribution/{company_id}` | `GET` | 国家归属分析包装接口，支持 `refresh` 和 `result_layer` |
| `/analysis/entities/{entity_id}/upstream-shareholders` | `GET` | 查询某主体的直接上游股东 |

注意：当前公司维度接口和 `/analysis/*` 接口存在部分功能重叠。前端主要使用 `/companies/{company_id}/analysis/summary`、`/companies/{company_id}/control-chain` 和 `/companies/{company_id}/relationship-graph`。

### 6.4 股东主体与控制关系输入接口

文件：`backend/api/shareholder.py`

主要接口：

| 接口 | 方法 | 功能 |
| --- | --- | --- |
| `/shareholders/entities` | `POST` | 创建股东主体 |
| `/shareholders/entities` | `GET` | 查询主体列表，支持 `skip/limit/q` |
| `/shareholders/entities/{id}` | `GET` | 主体详情 |
| `/shareholders/entities/{id}` | `PUT` | 更新主体 |
| `/shareholders/entities/{id}` | `DELETE` | 删除主体 |
| `/shareholders/structures` | `POST` | 创建股东或控制结构边 |
| `/shareholders/structures` | `GET` | 查询结构边，支持上游、下游、关系类型、是否当前等过滤 |
| `/shareholders/structures/{id}` | `GET` | 结构边详情 |
| `/shareholders/structures/{id}` | `PUT` | 更新结构边 |
| `/shareholders/structures/{id}` | `DELETE` | 删除结构边 |

这些接口维护的是控制算法输入事实，不是算法结果。

### 6.5 控制结果和国家归属结果 CRUD

文件：

- `backend/api/control_relationship.py`
- `backend/api/country_attribution.py`

用途：

- 对 `control_relationships` 和 `country_attributions` 提供结果表 CRUD。
- 适合调试或维护结果表，但新同学要注意，不应把这两张表当作原始输入事实表。

### 6.6 产业分析接口

文件：`backend/api/industry_analysis.py`

主要接口：

| 接口 | 方法 | 功能 |
| --- | --- | --- |
| `/companies/{company_id}/business-segments` | `POST` | 新增业务线 |
| `/companies/{company_id}/business-segments` | `GET` | 查询公司业务线 |
| `/business-segments/{segment_id}` | `GET` | 业务线详情 |
| `/business-segments/{segment_id}` | `PUT` | 更新业务线 |
| `/business-segments/{segment_id}` | `DELETE` | 删除业务线 |
| `/business-segments/{segment_id}/classifications` | `POST` | 新增分类 |
| `/business-segments/{segment_id}/classifications` | `GET` | 查询业务线分类 |
| `/business-segment-classifications/{classification_id}` | `PUT` | 更新分类 |
| `/business-segment-classifications/{classification_id}` | `DELETE` | 删除分类 |
| `/industry-analysis/classifications/refresh` | `POST` | 批量规则刷新业务线分类 |
| `/business-segments/{segment_id}/classify-with-llm` | `POST` | 对单条业务线生成 LLM 分类建议，不直接写正式结果 |
| `/business-segments/{segment_id}/confirm-llm-classification` | `POST` | 确认 LLM 建议并写回正式分类 |
| `/business-segments/{segment_id}/manual-classification` | `POST` | 人工写回分类 |
| `/industry-workbench/rule-analysis` | `POST` | 临时产业工作台规则分析，不写数据库 |
| `/industry-workbench/classify-with-llm` | `POST` | 临时产业工作台 LLM 分析，不写正式业务线表 |
| `/companies/{company_id}/industry-analysis` | `GET` | 公司产业分析快照 |
| `/companies/{company_id}/industry-analysis/periods` | `GET` | 可选报告期列表 |
| `/companies/{company_id}/industry-analysis/quality` | `GET` | 数据质量提示 |
| `/companies/{company_id}/industry-analysis/change` | `GET` | 两个报告期的业务结构变化 |
| `/companies/{company_id}/analysis/summary` | `GET` | 公司综合分析首页推荐入口 |

### 6.7 人工修订接口

文件：`backend/api/company.py` 调用 `backend/analysis/manual_control_override.py`

主要接口：

| 接口 | 方法 | 功能 |
| --- | --- | --- |
| `/companies/{company_id}/manual-control-override` | `GET` | 查询人工控制修订状态和历史 |
| `/companies/{company_id}/manual-control-override` | `POST` | 写入人工征订结果 |
| `/companies/{company_id}/manual-control-judgment` | `POST` | 从候选控制人中进行人工判定 |
| `/companies/{company_id}/manual-control-judgment/restore` | `POST` | 恢复人工判定前状态 |
| `/companies/{company_id}/manual-control-override/restore-auto` | `POST` | 恢复自动结果 |

人工修订写入后，会新增或更新：

- `manual_control_overrides`
- `control_relationships` 中的人工结果行
- `country_attributions` 中的人工结果行
- `annotation_logs`

### 6.8 核心业务逻辑文件

控制分析主链路：

- `backend/analysis/ownership_penetration.py`
  - `refresh_company_control_analysis()`
  - `_refresh_company_control_analysis_with_unified_context()`
  - `_apply_unified_company_analysis_records()`
  - `get_company_control_chain_data()`
  - `get_company_actual_controller_data()`
  - `get_company_country_attribution_data()`
- `backend/analysis/control_inference.py`
  - `build_control_context()`
  - `edge_to_factor()`
  - `collect_control_paths()`
  - `infer_controllers()`

国家归属包装：

- `backend/analysis/country_attribution_analysis.py`

关系图：

- `backend/analysis/ownership_graph.py`

产业分析：

- `backend/analysis/industry_analysis.py`
- `backend/analysis/industry_classification.py`
- `backend/analysis/industry_workbench.py`

人工修订：

- `backend/analysis/manual_control_override.py`

## 7. 前端模块说明

### 7.1 页面入口和路由

入口：

- `frontend/src/main.js` 创建 Vue 应用，挂载 Element Plus 和 Router。
- `frontend/src/App.vue` 只渲染 `<router-view />`。

路由：

文件：`frontend/src/router/index.js`

| 路径 | 页面 | 说明 |
| --- | --- | --- |
| `/` | `CompanyAnalysisView.vue` | 默认公司综合分析页 |
| `/company-analysis` | `CompanyAnalysisView.vue` | 公司综合分析页别名 |
| `/industry-workbench` | `IndustryWorkbenchView.vue` | 独立产业工作台页 |

### 7.2 前端 API 封装

HTTP 基础封装：

- `frontend/src/api/http.js`
- 默认 base URL：`http://127.0.0.1:8000`
- 超时：45 秒。
- 将后端 `detail` 规范化为前端错误消息。

公司接口：

- `frontend/src/api/company.js`
  - `fetchCompanyDetail(companyId)`
  - `searchCompanies(query, params)`
  - `fetchCompanyRelationshipGraph(companyId)`

综合分析与产业接口：

- `frontend/src/api/analysis.js`
  - `fetchCompanyAnalysisSummary(companyId)`
  - `fetchCompanyIndustryAnalysis(companyId, params)`
  - `fetchCompanyControlChain(companyId)`
  - `fetchCompanyAutomaticControlChain(companyId)`
  - `fetchShareholderEntities(params)`
  - `submitManualControlOverride(companyId, payload)`
  - `submitManualControlJudgment(companyId, payload)`
  - `restoreManualControlJudgment(companyId, payload)`
  - `restoreAutomaticControlResult(companyId, payload)`
  - `requestBusinessSegmentLlmAnalysis(segmentId)`
  - `confirmBusinessSegmentLlmClassification(segmentId, payload)`
  - `submitBusinessSegmentManualClassification(segmentId, payload)`
  - `runIndustryWorkbenchRuleAnalysis(payload)`
  - `runIndustryWorkbenchLlmAnalysis(payload)`

### 7.3 公司综合分析页面

文件：`frontend/src/views/CompanyAnalysisView.vue`

主要功能：

- 企业搜索：调用 `searchCompanies()`，支持名称、代码或 `/ID` 形式。
- 根据路由 query `companyId` 自动加载企业。
- 首先调用 `fetchCompanyAnalysisSummary(companyId)`。
- 如果 summary 中缺少 `control_analysis.control_relationships`，追加调用 `fetchCompanyControlChain(companyId)` 兜底。
- 如果 summary 中缺少 `industry_analysis.segments`，追加调用 `fetchCompanyIndustryAnalysis(companyId)` 兜底。
- 调用 `fetchCompanyRelationshipGraph(companyId)` 加载关系图。
- 展示公司总览、控制摘要、自动分析解释、控制结构图、关系图、控制明细、人工复核、产业分析。
- 打开 `IndustryWorkbenchDrawer` 进行产业分析工作台操作。

关键组件：

- `SearchBar.vue`：搜索输入和结果列表。
- `CompanyOverviewCard.vue`：公司基础信息。
- `ControlSummaryCard.vue`：控制链和国别归属摘要。
- `AutoAnalysisExplainPanel.vue`：自动分析依据、候选和阻断原因解释。
- `ControlStructureDiagram.vue`：当前控制结构图。
- `RelationshipGraphCard.vue`：基于 ECharts 的关系图。
- `ControlRelationsTable.vue`：控制关系明细表。
- `IndustryAnalysisPanel.vue`：产业分析主面板。
- `IndustryWorkbenchDrawer.vue`：产业工作台抽屉。
- `FloatingModuleNav.vue`：页面模块导航。

### 7.4 控制链展示相关组件

控制摘要：

- `frontend/src/components/ControlSummaryCard.vue`
- 数据来源：`summaryData.control_analysis` 和 `summaryData.country_attribution`。

控制结构图：

- `frontend/src/components/ControlStructureDiagram.vue`
- 工具函数：
  - `frontend/src/utils/controlStructureAdapter.js`
  - `frontend/src/utils/controlStructureLayout.js`
- 数据来源：控制分析结果中的 controller、候选、路径字段。

关系图：

- `frontend/src/components/RelationshipGraphCard.vue`
- 工具函数：
  - `frontend/src/utils/graphAdapter.js`
  - `frontend/src/utils/controlGraphLayout.js`
- 数据来源：`GET /companies/{company_id}/relationship-graph`。
- 图表库：ECharts Graph。

旧版控制链组件：

- `frontend/src/components/LegacyControlChainDiagram.vue`
- `frontend/src/utils/legacyControlChainAdapter.js`
- `frontend/src/utils/legacyControlChainLayout.js`

旧版组件仍在仓库中，但理解当前主页面时，应优先看 `ControlStructureDiagram.vue` 和 `RelationshipGraphCard.vue`。

### 7.5 业务线与产业分类展示

主要组件：

- `IndustryAnalysisPanel.vue`：产业分析汇总、业务结构、业务线明细和分类操作入口。
- `IndustrySummaryCard.vue`：产业摘要卡片。
- `IndustryStructurePieChart.vue`：业务结构饼图。
- `BusinessSegmentsTable.vue`：业务线和分类明细表。
- `IndustryWorkbenchContent.vue`：产业工作台表单、规则分析、LLM 分析和临时结果展示。
- `IndustryWorkbenchDrawer.vue`：在公司综合分析页内以抽屉方式打开工作台。
- `IndustryWorkbenchView.vue`：独立页面方式打开工作台。

数据来源：

- 公司分析页默认从 `summaryData.industry_analysis` 读取。
- 刷新产业分析时调用 `fetchCompanyIndustryAnalysis(companyId)`。
- 单条业务线 LLM 建议调用 `/business-segments/{segment_id}/classify-with-llm`。
- 人工写回调用 `/business-segments/{segment_id}/manual-classification`。
- 临时工作台不写正式库，调用 `/industry-workbench/rule-analysis` 和 `/industry-workbench/classify-with-llm`。

### 7.6 人工征订页面

当前人工控制征订不是独立路由，而是在 `CompanyAnalysisView.vue` 的“人工复核”模块中实现。

功能：

- 选择已有主体、新建主体或仅名称快照。
- 填写人工实际控制国家、控制路径、路径比例、控制类型、判定原因、证据。
- 支持多路径输入和中间节点编辑。
- 写入人工征订：`submitManualControlOverride()`。
- 确认自动结果：同样通过人工 override action 写入。
- 恢复自动结果：`restoreAutomaticControlResult()`。

辅助工具：

- `frontend/src/utils/manualPathBuilder.js`
- `frontend/src/utils/manualJudgment.js`

## 8. 核心业务流程说明

### 8.1 企业控制链分析流程

主入口：

- API：`POST /companies/{company_id}/analysis/refresh`
- 函数：`backend.analysis.ownership_penetration.refresh_company_control_analysis()`

流程：

1. API 校验 `companies.id` 是否存在。
2. 检查 `shareholder_entities.company_id = company_id` 的映射实体是否存在。
3. 创建或准备一次控制推断运行记录。
4. `build_control_context()` 加载公司、实体、关系边和证据来源。
5. `edge_to_factor()` 将每条有效 `shareholder_structures` 转为控制因子。
6. `collect_control_paths()` 搜索从候选主体到目标实体的多层路径。
7. `infer_controllers()` 聚合路径得分、语义证据、候选排序、实际控制 gate、共同控制、fallback 和 promotion 逻辑。
8. `_apply_unified_company_analysis_records()` 写回数据库。
9. API 返回刷新摘要。

### 8.2 实际控制国别归属判定流程

国家归属不是单独从头计算的一套孤立算法，而是在控制推断和写回过程中与控制人识别联动完成。

流程：

1. 控制推断识别 actual controller、direct controller 或 leading candidate。
2. `_resolve_controller_country()` 优先取控制主体 `shareholder_entities.country`。
3. 如果实际控制主体缺失或无法认定，按规则 fallback。
4. `country_attributions` 写入：
   - `actual_control_country`
   - `attribution_type`
   - `actual_controller_entity_id`
   - `direct_controller_entity_id`
   - `attribution_layer`
   - `country_inference_reason`
   - `look_through_applied`
   - `basis`
5. 读取时通过：
   - 自动层：`get_company_country_attribution_data()`
   - 当前层：`get_current_effective_country_attribution_data()`

常见 `attribution_layer`：

- `ultimate_controller_country`：终局控制主体国家。
- `direct_controller_country`：直接控制主体国家。
- `fallback_incorporation`：无有效控制人时回退注册地。
- `joint_control_undetermined`：共同控制导致无法判定唯一实际控制国家。

### 8.3 主要业务线征订与产业分类流程

正式库业务线流程：

1. 业务线数据写入 `business_segments`。
2. 调用 `POST /industry-analysis/classifications/refresh`。
3. `refresh_business_segment_classifications()` 读取业务线和公司上下文。
4. 规则系统基于业务线名称、别名、描述、公司上下文、同公司其它业务线进行分类。
5. 写入或更新 `business_segment_classifications`。
6. `get_company_industry_analysis()` 聚合为前端可读结构。

单条 LLM 辅助流程：

1. 调用 `POST /business-segments/{segment_id}/classify-with-llm`。
2. DeepSeek 返回建议分类。
3. 前端展示建议，不直接写正式结果。
4. 用户确认后调用 `POST /business-segments/{segment_id}/confirm-llm-classification`。
5. 正式写回 `business_segment_classifications` 并写入 `annotation_logs`。

临时产业工作台流程：

1. 前端在 `IndustryWorkbenchContent.vue` 录入临时公司和业务线。
2. 调用 `/industry-workbench/rule-analysis` 或 `/industry-workbench/classify-with-llm`。
3. 返回临时分析结果，不写入 `business_segments` 或 `business_segment_classifications`。

### 8.4 自动分析结果与人工修订结果的合成逻辑

自动结果：

- `review_status = auto`。
- `source_mode = control_chain_analysis` 或 `fallback_rule`。
- 由控制推断刷新写入。

人工结果：

- 记录在 `manual_control_overrides`。
- 同时生成人工 `control_relationships` 和 `country_attributions`。
- `review_status` 常见为 `manual_confirmed`。
- `source_type` 或 `source_mode` 标识为 `manual_override/manual_confirmed/manual_judgment` 等。

当前有效读取：

- `get_current_effective_control_chain_data()`：
  - 若无有效人工修订，返回自动结果，并标记 `result_source = automatic`。
  - 若有有效人工修订，将人工控制关系插入当前结果，自动实际控制结果标记为被覆盖。
- `get_current_effective_country_attribution_data()`：
  - 若人工修订包含国家归属，以人工结果作为当前有效国家。
  - 同时保留 `automatic_country_attribution` 供对比。

恢复自动结果：

- `restore_automatic_control_result()` 将当前人工结果置为非当前有效，并记录恢复动作。

### 8.5 结果展示与回显流程

前端页面加载：

1. 路由 query 中有 `companyId`。
2. `CompanyAnalysisView.vue` 调用 `fetchCompanyAnalysisSummary(companyId)`。
3. 后端 `get_company_analysis_summary()` 返回：
   - `company`
   - `control_analysis`
   - `country_attribution`
   - `automatic_control_analysis`
   - `automatic_country_attribution`
   - `manual_override`
   - `industry_analysis`
4. 前端如发现控制关系数组或产业 segments 缺失，会分别调用 control-chain 或 industry-analysis 接口兜底。
5. 前端再调用 relationship graph 接口渲染控制关系图。
6. 人工修订后，后端返回当前控制分析、当前国家归属、自动控制分析和自动国家归属，前端刷新展示。

## 9. 关键算法与规则说明

### 9.1 控制关系图如何构建

核心函数：`build_control_context()`，位于 `backend/analysis/control_inference.py`。

构建步骤：

- 加载 `companies`、`shareholder_entities`、`shareholder_structures`。
- 通过 `shareholder_entities.company_id` 找到目标公司实体。
- 加载当前有效、直接关系边。
- 将 `relationship_sources` 按结构边组织为证据 payload。
- 建立实体映射、公司映射、实体到公司映射和边集合。

有效边条件主要包括：

- `is_current = True`。
- `is_direct = True`。
- `effective_date` 不晚于分析日期。
- `expiry_date` 不早于分析日期。

### 9.2 控制边如何转换成控制因子

核心函数：`edge_to_factor()`。

一条 `shareholder_structures` 会被规范化为 `EdgeFactor`，包含：

- 上游主体 ID。
- 下游主体 ID。
- 关系类型。
- 控制得分。
- 置信度。
- 控制模式：数值、语义或混合。
- 优先级。
- 语义标签和证据摘要。

股权边主要读取：

- `effective_control_ratio`
- `holding_ratio`
- `voting_ratio`

语义边主要读取：

- `relation_type`
- `control_basis`
- `nomination_rights`
- `agreement_scope`
- `remarks`
- `relation_metadata`
- `board_seats`
- `confidence_level`

### 9.3 多层控制路径如何搜索

核心函数：`collect_control_paths()`。

当前默认参数：

- `DEFAULT_MAX_DEPTH = 10`
- `DEFAULT_MIN_PATH_SCORE = 0.0001`

搜索方式：

- 从目标实体反向寻找上游控制主体。
- 使用 DFS 搜索多层路径。
- 避免环路。
- 每条路径累计控制因子得分、路径置信度和路径模式。
- 低于最小路径得分的路径会被剪枝。

### 9.4 控制比例和路径分值如何计算

当前统一引擎内部使用 0 到 1 的概率或强度分数，展示时可转为百分比。

股权路径：

- 单边比例来自 `effective_control_ratio`、`holding_ratio` 或 `voting_ratio`。
- 多层路径会组合边强度。

多路径聚合：

- 默认聚合器：`DEFAULT_AGGREGATOR = "sum_cap"`。
- 另有 `aggregate_scores_noisy_or()` 等函数。
- `sum_cap` 的含义是多路径得分相加后封顶，避免超过 1。

候选人关键得分：

- `immediate_control_ratio`：直接边强度。
- `aggregated_control_score`：多路径聚合得分。
- `terminal_control_score`：结合终局推断后的控制得分。
- `control_ratio`：落库或展示用比例。

### 9.5 控制阈值和显著影响阈值

当前默认阈值位于 `backend/analysis/control_inference.py`：

| 常量 | 值 | 含义 |
| --- | ---: | --- |
| `DEFAULT_CONTROL_THRESHOLD` | `0.5` | 控制阈值，通常对应 50% |
| `DEFAULT_SIGNIFICANT_THRESHOLD` | `0.2` | 显著影响阈值，通常对应 20% |
| `DEFAULT_DISCLOSURE_THRESHOLD` | `0.2` | 候选披露或展示阈值 |
| `DEFAULT_RELATIVE_CONTROL_CANDIDATE_THRESHOLD` | `0.35` | 相对控制候选阈值 |
| `DEFAULT_RELATIVE_CONTROL_GAP_THRESHOLD` | `0.08` | 领先差距阈值 |
| `DEFAULT_RELATIVE_CONTROL_RATIO_THRESHOLD` | `1.2` | 领先比例阈值 |
| `DEFAULT_CLOSE_COMPETITION_GAP_THRESHOLD` | `0.05` | 接近竞争差距 |
| `DEFAULT_CLOSE_COMPETITION_RATIO_THRESHOLD` | `1.1` | 接近竞争比例 |
| `DEFAULT_MIN_ACTUAL_CONFIDENCE` | `0.50` | 实际控制认定最低置信度 |

控制层级分类：

- 分数达到控制阈值：可进入控制候选或实际控制判断。
- 分数达到显著影响阈值但未达控制阈值：通常为显著影响或候选。
- 分数不足或置信不足：可能只作为普通候选或不展示。

### 9.6 控制主体和实际控制国别如何判定

候选控制主体生成：

- `_build_candidates_for_target_entity()` 聚合目标实体的所有上游路径。
- 对每个候选计算总得分、置信度、路径、语义标签。

候选排序：

- `_controller_sort_key()`
- `_direct_candidate_sort_key()`

实际控制人判定：

- `infer_controllers()` 综合直接候选、领先候选、实际控制 gate、共同控制、promotion、terminal profile。
- 如果存在共同控制或接近竞争，系统可能不输出唯一实际控制人。
- 如果候选分数达到但证据不足，可能被 `_actual_control_evidence_block_reason()` 阻断。

国别判定：

- 优先使用实际控制主体国家。
- 若实际控制主体不可判定，按 direct controller、joint control 或 fallback 逻辑处理。
- fallback 常用 `companies.incorporation_country`。

### 9.7 业务分类结果如何判定

核心文件：`backend/analysis/industry_classification.py`

分类输入：

- 业务线名称 `segment_name`。
- 业务线别名 `segment_alias`。
- 业务线描述 `description`。
- 公司名称和简介。
- 同公司其它业务线文本。

分类方法：

1. 文本标准化。
2. 判断规则家族。
3. 在规则家族内部匹配细分规则。
4. 计算规则得分、比较候选差距。
5. 决定输出层级和状态。

已实现规则家族包括：

- `digital_commerce`
- `media_adtech`
- `fintech`
- `software_it_services`
- `semiconductors`
- `technology_hardware`
- `automotive_mobility`
- `energy_transition`
- `health_technology`

分类状态：

- `confirmed`：证据充分，可确认。
- `pending`：方向基本明确，但细分层级保守。
- `needs_llm_review`：规则不足，建议模型辅助。
- `needs_manual_review`：需要人工确认。
- `conflicted`：候选冲突。
- `unmapped`：当前规则未覆盖或文本不足。

### 9.8 证据不足或结果不确定时如何处理

控制分析：

- 若没有映射实体，刷新接口返回 400。
- 若没有有效上游边，控制结果可能为空，国家归属 fallback 到注册地。
- 若候选接近竞争，可能标记 close competition 或不输出唯一实际控制人。
- 若有共同控制信号，可能输出 `joint_control_undetermined`。
- 若 nominee、beneficial owner unknown、protective rights 等阻断信号出现，会保守处理。
- `terminal_failure_reason`、`basis`、`control_inference_audit_log` 记录不确定原因。

产业分类：

- 规则置信不足时输出 `pending` 或 `needs_llm_review`。
- 候选冲突时输出 `conflicted`。
- 规则未覆盖时输出 `unmapped`。
- 人工或 LLM 已确认结果会被刷新流程保护，不被普通规则刷新覆盖。

## 10. 测试与验证

### 10.1 已有测试文件

后端测试目录：`tests/`

控制推断相关：

- `tests/test_control_inference_engine.py`
- `tests/test_ultimate_controller_dataset_regression.py`
- `tests/test_extended_semantic_controls.py`
- `tests/test_mixed_control_paths.py`
- `tests/test_mixed_and_non_equity_threshold_tuning.py`
- `tests/test_rollup_success_promotion_tuning.py`
- `tests/test_trust_control_rules.py`
- `tests/test_semantic_control_evidence_model.py`
- `tests/test_terminal_controller_v2.py`
- `tests/test_terminal_candidate_profile.py`

API 相关：

- `tests/test_company_api.py`
- `tests/test_control_chain_api.py`
- `tests/test_control_chain_generation_api.py`
- `tests/test_control_relationship_api.py`
- `tests/test_country_attribution_api.py`
- `tests/test_shareholder_api.py`
- `tests/test_upstream_shareholders_api.py`
- `tests/import_db_api/test_api_on_import_db.py`
- `tests/import_db_api/test_manual_control_override_api.py`

产业分析相关：

- `tests/test_industry_classification_refresh.py`
- `tests/test_prepare_industry_working_db.py`
- 根目录下还有 `test_industry_analysis_mvp_api.py`、`test_industry_analysis_on_db_copy.py`。

配置与数据库：

- `tests/test_database_config.py`
- `tests/test_db_upgrade_v2.py`
- `tests/test_deepseek_config.py`

前端测试目录：`frontend/tests/`

- `manualPathBuilder.test.mjs`
- `manualJudgment.test.mjs`
- `controlStructureAdapter.test.mjs`
- `controlRelationsMerge.test.mjs`

前端测试命令：

```powershell
cd frontend
npm run test:manual-paths
```

后端测试命令：

```powershell
.\venv\Scripts\python.exe -m pytest
```

### 10.2 推荐新同学自测流程

1. 后端健康检查：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health'
```

2. 综合分析接口：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/companies/128/analysis/summary'
```

3. 控制链接口：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/companies/128/control-chain'
```

4. 关系图接口：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/companies/128/relationship-graph'
```

5. 产业分析接口：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/companies/128/industry-analysis'
```

6. 前端访问：

```text
http://127.0.0.1:5173/?companyId=128
```

### 10.3 典型测试用例

推荐使用当前文档和 README 中出现过的演示 `company_id`：

- `128`
- `240`
- `9717`
- `8`
- `170`

自测要覆盖：

- 有实际控制人的公司。
- 只有 leading candidate 或显著影响的公司。
- fallback 到注册地的公司。
- 有业务线和 GICS 分类的公司。
- 有人工修订记录的公司。

具体样本含义需结合当前数据库结果确认。

### 10.4 如何确认联调正常

后端正常：

- `/health` 返回 `status = ok`。
- `database_url` 指向预期数据库。
- `/companies/{id}/analysis/summary` 返回公司、控制、国家归属和产业分析。

前端正常：

- 搜索框可以搜到公司。
- 选择公司后 URL 出现 `?companyId=...`。
- 公司总览、控制摘要、关系图、控制明细、产业分析能正常渲染。
- 后端未启动时前端会给出明确错误。

数据库正常：

- 目标公司存在于 `companies`。
- `shareholder_entities` 有 `company_id` 映射实体。
- `shareholder_structures` 有当前有效边，或系统能合理 fallback。
- 控制刷新后 `control_relationships`、`country_attributions`、`control_inference_runs` 行数或更新时间变化。

## 11. 常见问题与注意事项

### 11.1 容易出错的配置项

- `DATABASE_URL`：最容易造成“前端和脚本结果不一致”。确保后端、脚本、手工查询使用同一数据库。
- `CORP_DEFAULT_DATABASE_PATH` 和 `CORP_DEFAULT_DATABASE_NAME`：仅在未设置 `DATABASE_URL` 时生效。
- `VITE_API_BASE_URL`：前端连接后端地址。
- `DEEPSEEK_API_KEY` 或 `DEEPSEEK_API_KEY_FILE`：LLM 分类相关接口需要。
- `DEEPSEEK_TIMEOUT_SECONDS`：LLM 超时配置。

### 11.2 数据库路径和版本注意事项

当前仓库根目录存在多个 `.db`：

- `ultimate_controller_enhanced_dataset_industry_working.db`：当前代码默认库。
- `ultimate_controller_enhanced_dataset_working.db`：旧文档中常提到的演示库。
- `ultimate_controller_enhanced_dataset_rollup_working.db`
- `ultimate_controller_enhanced_dataset_trust_working.db`
- `ultimate_controller_enhanced_dataset_tuned_working.db`
- `company_test_analysis_industry.db`
- `company_test_analysis_industry_v2.db`
- `test.db`
- 其他测试或备份库。

接手后建议第一步先确认当前要使用哪一个数据库，并固定在 `DATABASE_URL` 中。

### 11.3 依赖版本注意事项

- 后端依赖已经固定在 `requirements.txt`。
- 前端依赖版本在 `package.json` 和 `package-lock.json`。
- Node 精确版本待确认，建议新同学记录本机 `node --version` 和 `npm --version` 后补充到文档。

### 11.4 已知风险或未完成事项

- 当前无 Alembic 迁移，数据库结构演进依赖 `database.py` 中的补列逻辑，不适合复杂生产迁移。
- `relationship_sources` 当前默认库为空，但代码已支持来源表和部分可信度读取能力，后续数据补齐后需重新验证算法表现。
- `entity_aliases` 当前默认库为空，实体匹配和去重仍有扩展空间。
- 业务线分类规则覆盖有限，不应宣称“全行业完整分类”。
- DeepSeek 辅助分类依赖外部服务，不应作为离线必备能力。
- 旧文档与当前代码有口径差异，特别是默认数据库名。
- README 和 PRD 在当前终端输出存在编码问题，建议后续统一 UTF-8 保存并验证。
- 权限、登录、生产部署、备份恢复、监控告警待确认。

### 11.5 后续开发建议

优先级建议：

1. 统一文档中的默认数据库口径。
2. 为数据库迁移引入正式方案，例如 Alembic，或至少整理补列策略。
3. 补充 `relationship_sources` 数据并验证来源可信度对控制推断的影响。
4. 强化前端对不确定结果、fallback、joint control 的解释展示。
5. 扩充产业分类规则，尤其是物流、工业设备、传统制造等当前覆盖不足方向。
6. 为 DeepSeek 调用增加更完整的失败兜底、重试和审计。
7. 增加前端端到端测试或 Playwright 验证。

## 12. 快速上手路线

### 12.1 第一天先看哪些文件

建议阅读顺序：

1. `PROJECT_HANDOVER.md`：先建立整体地图。
2. `backend/main.py`：了解应用入口和路由注册。
3. `backend/database_config.py`、`backend/database.py`：了解数据库连接和初始化。
4. `backend/models/company.py`
5. `backend/models/shareholder.py`
6. `backend/models/control_relationship.py`
7. `backend/models/country_attribution.py`
8. `backend/models/business_segment.py`
9. `backend/models/business_segment_classification.py`
10. `backend/api/company.py`
11. `backend/api/industry_analysis.py`
12. `frontend/src/views/CompanyAnalysisView.vue`
13. `frontend/src/api/analysis.js`
14. `docs/algorithm_core_code_map.md`

### 12.2 第二步如何跑通项目

后端：

```powershell
$env:DATABASE_URL='sqlite:///d:/graduation_project/corp_attribution_system/ultimate_controller_enhanced_dataset_industry_working.db'
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开：

```text
http://127.0.0.1:5173/?companyId=128
```

若页面正常展示公司总览、控制分析、关系图和产业分析，说明主链路基本跑通。

### 12.3 第三步如何理解核心业务逻辑

控制链：

1. 从 `backend/api/company.py` 的 `/companies/{company_id}/analysis/refresh` 开始。
2. 进入 `backend/analysis/ownership_penetration.py` 的 `refresh_company_control_analysis()`。
3. 再进入 `backend/analysis/control_inference.py`：
   - `build_control_context()`
   - `edge_to_factor()`
   - `collect_control_paths()`
   - `infer_controllers()`
4. 最后回到 `_apply_unified_company_analysis_records()` 看写库字段。

前端展示：

1. `frontend/src/api/analysis.js`
2. `frontend/src/views/CompanyAnalysisView.vue`
3. `ControlSummaryCard.vue`
4. `AutoAnalysisExplainPanel.vue`
5. `ControlStructureDiagram.vue`
6. `RelationshipGraphCard.vue`

产业分类：

1. `backend/api/industry_analysis.py`
2. `backend/analysis/industry_classification.py`
3. `backend/analysis/industry_analysis.py`
4. `frontend/src/components/IndustryAnalysisPanel.vue`
5. `frontend/src/components/IndustryWorkbenchContent.vue`

人工修订：

1. `backend/analysis/manual_control_override.py`
2. `backend/schemas/manual_control_override.py`
3. `CompanyAnalysisView.vue` 中人工复核相关代码。
4. `frontend/src/utils/manualPathBuilder.js`

### 12.4 如果要继续开发，优先从哪些模块入手

如果目标是完善控制算法：

- `backend/analysis/control_inference.py`
- `backend/analysis/ownership_penetration.py`
- 对应测试：`tests/test_*control*`、`tests/test_*ultimate*`、`tests/test_*trust*`。

如果目标是完善前端展示：

- `frontend/src/views/CompanyAnalysisView.vue`
- `frontend/src/components/ControlSummaryCard.vue`
- `frontend/src/components/AutoAnalysisExplainPanel.vue`
- `frontend/src/components/ControlStructureDiagram.vue`
- `frontend/src/components/RelationshipGraphCard.vue`

如果目标是完善产业分类：

- `backend/analysis/industry_classification.py`
- `backend/analysis/industry_analysis.py`
- `frontend/src/components/IndustryAnalysisPanel.vue`
- `frontend/src/components/IndustryWorkbenchContent.vue`

如果目标是完善数据接入：

- `scripts/import_raw_dataset.py`
- `scripts/import_industry_analysis_csvs.py`
- `backend/crud/`
- `backend/models/`
- `docs/database_handoff_guide.md`

如果目标是提高可维护性：

- 先统一默认数据库文档。
- 再整理测试命令和最小样例。
- 然后考虑数据库迁移工具和前端端到端测试。

## 附录 A：当前最重要的接口清单

综合页面推荐入口：

```text
GET /companies/{company_id}/analysis/summary
```

控制分析：

```text
POST /companies/{company_id}/analysis/refresh
GET  /companies/{company_id}/control-chain
GET  /companies/{company_id}/actual-controller
GET  /companies/{company_id}/country-attribution
GET  /companies/{company_id}/relationship-graph
```

公司搜索：

```text
GET /companies/search?query=...&limit=10
```

人工控制修订：

```text
GET  /companies/{company_id}/manual-control-override
POST /companies/{company_id}/manual-control-override
POST /companies/{company_id}/manual-control-judgment
POST /companies/{company_id}/manual-control-judgment/restore
POST /companies/{company_id}/manual-control-override/restore-auto
```

产业分析：

```text
GET  /companies/{company_id}/industry-analysis
GET  /companies/{company_id}/industry-analysis/periods
GET  /companies/{company_id}/industry-analysis/quality
GET  /companies/{company_id}/industry-analysis/change
POST /industry-analysis/classifications/refresh
```

业务线与分类：

```text
GET  /companies/{company_id}/business-segments
POST /companies/{company_id}/business-segments
GET  /business-segments/{segment_id}
PUT  /business-segments/{segment_id}
DELETE /business-segments/{segment_id}
GET  /business-segments/{segment_id}/classifications
POST /business-segments/{segment_id}/classifications
POST /business-segments/{segment_id}/classify-with-llm
POST /business-segments/{segment_id}/confirm-llm-classification
POST /business-segments/{segment_id}/manual-classification
```

产业工作台：

```text
POST /industry-workbench/rule-analysis
POST /industry-workbench/classify-with-llm
```

股东主体和结构：

```text
GET  /shareholders/entities
POST /shareholders/entities
GET  /shareholders/entities/{shareholder_entity_id}
PUT  /shareholders/entities/{shareholder_entity_id}
DELETE /shareholders/entities/{shareholder_entity_id}

GET  /shareholders/structures
POST /shareholders/structures
GET  /shareholders/structures/{shareholder_structure_id}
PUT  /shareholders/structures/{shareholder_structure_id}
DELETE /shareholders/structures/{shareholder_structure_id}
```

## 附录 B：接手时最容易混淆的概念

- `companies` 是公司主数据；`shareholder_entities` 是控制图节点。一个目标公司必须映射到一个实体节点。
- `shareholder_structures` 是输入事实；`control_relationships` 是算法或人工输出结果。
- `country_attributions` 是国家归属输出，不是原始事实输入。
- `current` 结果层可能包含人工修订；`auto` 结果层只看自动分析。
- `actual_controller` 是实际控制人；`ultimate_controller` 是终局控制层级标记，两者在历史文档中有时被混用，读当前代码时应分开。
- `relationship-graph` 是关系图数据；`control-chain` 是分析结果数据，两者不是同一个接口。
- 产业工作台的临时分析不写正式业务线表；正式写回需要确认 LLM 建议或人工分类。
- 旧文档中的默认数据库名不一定等于当前代码默认数据库名，以 `backend/database_config.py` 为准。
