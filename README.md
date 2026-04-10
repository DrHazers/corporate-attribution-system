# Corporate Attribution System

## 演示数据库约定

前后端联调、截图和最终演示请统一使用：

```powershell
$env:DATABASE_URL='sqlite:///d:/graduation_project/corp_attribution_system/company_test_analysis_industry.db'
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

说明：
- 不设置 `DATABASE_URL` 时，后端会按 `backend/database.py` 的默认配置连接项目根目录下的 `company.db`。
- 前端演示推荐固定连接 `company_test_analysis_industry.db`，这份库覆盖控制链、国别归属、产业分析、多报告期和质量提示等演示场景。
- HTML 验证图、前端 API、手工数据库查询应尽量使用同一份数据库，避免出现“图里有结果、前端接口看不到”或记录 ID 不一致的排查噪音。
- 这里仅是运行环境约定，不改变 unified control inference、refresh 主链路或任何表结构。

## 项目定位
这是一个面向产业研究的企业控制链、国别归属与产业分析系统。

当前项目的后端重点已经不是普通 CRUD，而是围绕以下主线组织：

- 基于企业控制网络进行控制链分析
- 输出实际控制人与国别归属结果
- 将分析结果写回数据库，供图展示和后续产业分析模块复用
- 为答辩展示提供稳定、一致、可解释的分析闭环

当前默认分析主链路已经统一为 `unified control inference`，旧版 legacy 股权路径仍保留，但不再是默认运行方式。

## 当前已实现能力

### 1. 基础数据与主体建模
- 企业基础信息管理：`companies`
- 主体建模：`shareholder_entities`
- 原始关系建模：`shareholder_structures`
- 控制分析结果存储：`control_relationships`
- 国别归属结果存储：`country_attributions`

### 2. 控制分析能力
- 多层控制链分析
- 实际控制人识别
- 国别归属推断
- 控制分析结果写回数据库
- 支持股权边与语义控制边混合判断
- 支持 `agreement`、`board_control`、`voting_right`、`nominee`、`vie` 等关系类型参与 unified 分析

### 3. 展示与演示支撑
- 控制链结果读取接口
- 国别归属读取接口
- 控制链图展示支撑
- 基于 `NetworkX + PyVis` 生成 HTML 图的后端能力
- 批量演示数据与图构建脚本

### 4. 当前默认算法事实
- 默认主链路：`backend/analysis/control_inference.py`
- 默认分析入口仍以 `company_id` 为核心
- `shareholder_structures` 是核心原始事实来源
- `control_relationships` / `country_attributions` 是分析结果表，不是底层事实来源
- 当前开发数据库仍为 SQLite

## 当前核心数据模型

### 原始事实层
- `companies`：研究对象公司主表
- `shareholder_entities`：控制网络中的主体节点
- `shareholder_structures`：主体之间的原始关系边，是控制分析的基础输入

### 结果层
- `control_relationships`：控制链分析结果
- `country_attributions`：国别归属分析结果

可以把当前系统理解为：

1. 先维护公司、主体和原始关系
2. 再基于 `company_id` 定位目标实体
3. 用 unified 引擎完成控制分析
4. 将结果写回结果表
5. 最后由接口与图展示模块读取这些结果

## 当前系统运行方式

### 默认分析闭环
当前最稳定、最适合展示和答辩的运行方式是：

1. 输入 `company_id`
2. 调用 refresh 入口触发重算
3. unified 引擎基于 `shareholder_structures` 计算控制链、实际控制人与国别归属
4. 写回 `control_relationships` / `country_attributions`
5. 读接口和图展示模块读取预计算结果

### refresh 与读取的区别
- `refresh` 入口会真正重算并写回结果
- 普通 GET 读取接口默认只是读库，不会自动重算
- 图展示层默认依赖预计算结果，而不是在展示时临时重跑算法

### 当前主要分析入口
当前仓库真正稳定支持的分析入口是 `company_id`。

如果上层未来要做“公司名搜索”，也应先完成：

1. 公司查询
2. 名称到 `company_id` 的映射
3. 再进入当前分析主链路

不应绕开 `company_id` 直接另起一套分析逻辑。

## 关键接口

只列当前最关键、最稳定的接口：

### 重算入口
- `POST /companies/{company_id}/analysis/refresh`

### 读取控制链结果
- `GET /analysis/control-chain/{company_id}`
- `GET /companies/{company_id}/control-chain`

### 读取国别归属结果
- `GET /analysis/country-attribution/{company_id}`
- `GET /companies/{company_id}/country-attribution`

### 图展示相关读取
- `GET /companies/{company_id}/relationship-graph`
- 后端图构建模块：`backend/visualization/control_graph.py`

说明：

- `GET ...?refresh=true` 可以兼容触发重算
- 常规展示建议仍以显式 refresh 后再读取结果为主

## 快速开始

### 1. 安装依赖
```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 启动后端
```powershell
$env:DATABASE_URL='sqlite:///d:/graduation_project/corp_attribution_system/company_test_analysis_industry.db'
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

### 3. 运行测试
```powershell
.\venv\Scripts\python.exe -m pytest
```

### 4. 常用脚本
- `scripts/import_raw_dataset.py`：导入原始数据
- `scripts/build_demo_analysis_db.py`：构建演示分析数据库
- `scripts/build_demo_visualizations.py`：批量生成演示图

## 项目结构

```text
.
├─ backend/
│  ├─ analysis/           # 控制分析、控制链读取、国别归属分析
│  ├─ api/                # FastAPI 路由
│  ├─ crud/               # 基础数据库查询与写入
│  ├─ models/             # SQLAlchemy ORM 模型
│  ├─ schemas/            # Pydantic schema
│  ├─ tasks/              # 批量重算、离线任务
│  ├─ visualization/      # 控制链图展示支撑
│  ├─ database.py         # 数据库初始化与会话管理
│  ├─ shareholder_relations.py
│  └─ main.py             # FastAPI 应用入口
├─ docs/                  # 项目说明、算法规则、协作规则
├─ scripts/               # 数据导入、演示构建脚本
├─ tests/                 # 测试与演示输出
├─ data/                  # 项目数据与样例数据
├─ company.db             # 当前开发期 SQLite 数据库
├─ PRD.md
└─ README.md
```

## 当前开发进度

当前项目已经完成从“早期数据管理后端”向“控制分析结果驱动的研究系统”收口，当前状态可以概括为：

- unified control inference 已成为默认主链路
- refresh、批量重算、图展示相关读取的默认参数已统一
- 图层过滤规则已经与分析口径核对
- 默认运行时更强调结果一致、展示一致、答辩可解释

这意味着项目当前更适合进入下一阶段：

1. 公司查询与分析入口整理
2. 股权链路图展示优化
3. 产业分析模块接入与整合
4. 最终展示闭环打通

## 当前项目边界

当前阶段明确暂不重点做：

- PostgreSQL 正式迁移
- 复杂前端工程化
- 全自动复杂金融结构识别的进一步扩展
- 大模型深度接入主控制判别主链路
- 再次大规模重构核心控制算法

这些内容不是永久不做，而是不是当前最优先的毕设推进方向。

## 当前阶段的协作原则

如果要继续开发，优先遵循以下事实：

- 先保证分析结果一致，再增加功能
- 先围绕 `company_id -> refresh -> 结果读取 -> 图展示` 做闭环
- 不要把 `control_relationships` 当作底层事实来源
- 不要绕开 unified 默认主链路另起一套分析逻辑
- 新增展示或产业分析能力时，优先复用当前预计算结果

## 相关文档
- `docs/current_algorithm_rules.md`：当前控制分析规则的真实实现说明
- `docs/algorithm_runtime_cleanup.md`：最近一轮算法运行时收口后的默认行为说明
- `docs/codex_rules.md`：当前阶段的开发协作约束
