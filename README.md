# Corporate Attribution System

面向本科毕业设计与研究演示的企业综合分析系统，聚焦两条主线：

- 企业控制关系识别与实际控制国别归属判定
- 企业业务结构整理、GICS 产业分类与人工征订留痕

当前 README 已按 `docs/thesis_support/` 下最新 4 份支撑文档统一更新，若历史文档与代码不一致，以当前代码实现为准。

## 项目定位

本项目更适合定位为“企业国别归属与业务结构征订系统”，服务于：

- 企业实际控制人识别
- 企业实际控制国别判定
- 企业业务线结构整理
- 产业分类修订、确认与留痕

它是研究型分析系统，不是面向真实互联网环境的大规模全自动生产平台。

## 核心能力

### 1. 控制链与国别归属

- 以 `shareholder_entities` 和 `shareholder_structures` 为核心建模企业控制网络
- 默认采用 `unified control inference` 作为主算法
- 支持 `equity`、`agreement`、`board_control`、`voting_right`、`nominee`、`vie` 等关系类型
- 支持 direct controller、actual controller、leading candidate、一定程度的 ultimate controller 上推
- 支持 joint control 识别，以及 `fallback_incorporation` 注册地兜底
- 自动结果写回 `control_relationships`、`country_attributions`

### 2. 业务结构与产业分析

- 以 `business_segments` 维护企业业务线事实
- 以 `business_segment_classifications` 保存业务线到 `GICS` 的分类结果
- 已实现规则型分类刷新，不是机器学习训练型分类器
- 支持 `primary`、`secondary`、`emerging`、`other` 四类业务线
- 支持 LLM 辅助建议、人工确认、分类质量检查与历史期间变化分析

### 3. 人工征订与留痕

- 控制结果人工覆盖与恢复：`manual_control_overrides`
- 业务线与分类结果操作留痕：`annotation_logs`
- 系统同时保留自动结果层 `auto` 和当前有效结果层 `current`

## 当前总体架构

### 后端

- Python 3
- FastAPI
- SQLAlchemy 2.x
- Pydantic 2.x
- Uvicorn

### 前端

- Vue 3
- Vue Router
- Vite
- Axios
- Element Plus
- ECharts

### 数据与分析

- SQLite 为默认运行数据库
- 依赖层支持 PostgreSQL URL，但当前默认运行主路径仍以 SQLite 为主
- Pandas、NetworkX 用于数据处理与图分析
- Pytest 用于测试验证

## 数据库分层

当前数据库设计可以概括为 4 层加运行审计层：

- 基础事实层：`companies`、`shareholder_entities`、`shareholder_structures`、`relationship_sources`、`business_segments`
- 算法结果层：`control_relationships`、`country_attributions`
- 产业分析结果层：`business_segment_classifications`
- 人工征订 / 留痕层：`manual_control_overrides`、`annotation_logs`
- 运行审计层：`control_inference_runs`、`control_inference_audit_log`

这套设计强调：

- 原始事实与分析结果分离
- 自动结果与人工修订分离
- 控制分析与产业分析共享同一公司分析主入口

## 关键分析链路

### 控制分析主链

1. 以 `company_id` 作为稳定分析入口
2. `refresh_company_control_analysis()` 触发单公司刷新
3. `build_control_context()` 构造控制图上下文
4. `infer_controllers()` 识别 direct / actual / leading / country attribution
5. 自动结果写回 `control_relationships`、`country_attributions`
6. 前端默认更多读取 `current` 结果层，而不是仅看自动结果

### 产业分析主链

1. 读取 `business_segments`
2. 关联 `business_segment_classifications`
3. 按默认报告期聚合业务结构
4. 生成主行业标签、完整性标记、质量警告和变化分析
5. 通过公司总览接口统一返回

## 关键接口

### 控制分析

- `POST /companies/{company_id}/analysis/refresh`
- `GET /analysis/control-chain/{company_id}`
- `GET /companies/{company_id}/control-chain`
- `GET /analysis/country-attribution/{company_id}`
- `GET /companies/{company_id}/country-attribution`
- `GET /companies/{company_id}/relationship-graph`

### 公司总览与产业分析

- `GET /companies/{company_id}/analysis/summary`
- `GET /companies/{company_id}/industry-analysis`
- `GET /companies/{company_id}/industry-analysis/periods`
- `GET /companies/{company_id}/industry-analysis/quality`
- `GET /companies/{company_id}/industry-analysis/change`
- `POST /industry-analysis/classifications/refresh`

说明：

- 普通读取接口默认是读库，不会自动重算
- 需要实时刷新时，请显式调用 refresh 接口或使用 `?refresh=true`

## 默认数据库约定

当前代码默认应用数据库为：

- `ultimate_controller_enhanced_dataset_industry_working.db`

对应默认配置位于：

- `backend/database_config.py`

如不手动设置 `DATABASE_URL`，后端会优先连接该默认工作库。若后续切换到同结构的新工作库，优先使用以下环境变量，而不是到处手改文件名：

- `CORP_DEFAULT_DATABASE_PATH`
- `CORP_DEFAULT_DATABASE_NAME`

推荐启动方式：

```powershell
$env:DATABASE_URL='sqlite:///d:/graduation_project/corp_attribution_system/ultimate_controller_enhanced_dataset_industry_working.db'
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

## 快速开始

### 1. 安装后端依赖

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 启动后端

```powershell
$env:DATABASE_URL='sqlite:///d:/graduation_project/corp_attribution_system/ultimate_controller_enhanced_dataset_industry_working.db'
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

### 3. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

### 4. 运行测试

```powershell
.\venv\Scripts\python.exe -m pytest
```

### 5. 常用脚本

- `scripts/import_raw_dataset.py`：导入原始控制关系数据
- `scripts/import_industry_analysis_csvs.py`：导入产业分析相关 CSV
- `scripts/run_industry_classification_refresh.py`：刷新业务线分类
- `scripts/run_large_control_validation.py`：批量控制分析验证
- `scripts/build_demo_visualizations.py`：生成 HTML 控制图

## 主要目录

```text
.
├─ backend/
│  ├─ analysis/         # 控制分析、国别归属、产业分析聚合
│  ├─ api/              # FastAPI 路由
│  ├─ crud/             # 数据库读写
│  ├─ models/           # SQLAlchemy ORM 模型
│  ├─ schemas/          # Pydantic schema
│  ├─ tasks/            # 批量重算任务
│  ├─ visualization/    # 控制图可视化支撑
│  ├─ database.py
│  ├─ database_config.py
│  └─ main.py
├─ frontend/            # Vue 3 前端
├─ docs/                # 项目文档与 thesis_support 支撑材料
├─ scripts/             # 导入、刷新、验证、演示脚本
├─ tests/               # 测试与验证输出
└─ README.md
```

## 当前边界

以下内容当前不宜描述为“已完整实现”：

- 全球实时数据抓取
- 从年报全文自动抽取正式业务线并自动入库
- 机器学习训练型行业分类模型
- 图数据库主架构
- 所有读取接口实时重算
- 对所有 nominee / trust / hidden beneficial owner 场景的完全自动识别
- 以上市地或总部地作为后端正式国别兜底规则
- Industry Workbench 作为正式入库生产流

## 相关文档

本 README 主要对齐以下 4 份最新支撑文档：

- `docs/thesis_support/current_project_overview_for_thesis.md`
- `docs/thesis_support/current_control_algorithm_overview.md`
- `docs/thesis_support/current_industry_analysis_rules.md`
- `docs/thesis_support/current_database_structure_overview.md`

如需更细的论文口径、字段说明或实现边界，请优先阅读这些文件。
