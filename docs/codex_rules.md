# Corporate Attribution System 后端开发规范草案 v0.1

## 1. 文档目标
本规范用于统一后续后端开发行为，约束 Codex 在本项目中的代码生成范围、命名方式、模块职责、数据流向和分析逻辑。

本规范优先解决以下问题：
- 明确各数据表的角色：事实表、节点表、关系表、结论表。
- 明确控制链分析与国别归属推断的实现入口。
- 明确哪些内容可以自动生成，哪些内容不能直接覆盖人工结果。
- 明确 API、schema、service、crud 的职责边界。
- 为后续使用 Codex 分阶段生成代码提供统一依据。

## 2. 项目定位
本项目不是普通企业信息管理系统，而是一个：

**基于企业控制网络的研究型分析系统**

核心能力包括：
- 企业基础信息管理
- 主体建模
- 股权/控制关系建模
- 多层控制链分析
- 实际控制人识别
- 国别归属推断
- 特殊结构识别（后续可引入 LLM）

## 3. 数据模型角色定义

### 3.1 companies
**角色：研究对象公司表**

用途：
- 存储需要重点分析的公司基础信息
- 作为国别归属分析与业务结构分析的目标对象

说明：
- companies 不是整个控制网络的唯一节点表
- 它代表“系统重点研究公司”
- 后续分析入口通常从 company_id 开始

---

### 3.2 shareholder_entities
**角色：统一主体表 / 网络节点表**

用途：
- 表示控制网络中的任意主体

主体可以是：
- 公司
- 自然人
- 政府机构
- 基金
- 投资平台
- 其他组织

说明：
- 图建模中的节点，统一来自 shareholder_entities
- 若某主体同时也是系统中的研究公司，则通过 company_id 关联到 companies.id

---

### 3.3 shareholder_structures
**角色：原始关系事实表 / 网络边表**

用途：
- 表示主体到主体之间的持股/控制关系
- 是控制链分析和控制权计算的唯一事实来源

说明：
- 所有图分析必须优先基于此表
- 不允许从 control_relationships 反推控制链

关系语义：
- from_entity_id -> to_entity_id 表示 from_entity 对 to_entity 持股或拥有某类控制关系

---

### 3.4 control_relationships
**角色：控制分析结论表**

用途：
- 存储针对目标公司的控制分析结果
- 用于前端展示、接口直接输出、人工校核后的结果存档

说明：
- 本表不是原始关系表
- 本表可以由分析服务自动生成
- 本表也允许人工修订
- 后续自动任务不能无条件覆盖人工确认结果

---

### 3.5 country_attributions
**角色：国别归属结论表**

用途：
- 存储公司归属分析结果
- 展示注册地、上市地、实际控制地三种维度

说明：
- companies 中的国家字段是原始事实
- country_attributions 是推断/确认后的结论快照

---

## 4. 字段语义统一规则

### 4.1 shareholder_entities.entity_type
必须使用受控枚举，不允许自由文本乱写。

建议枚举值：
- company
- natural_person
- government
- institution
- fund
- platform
- unknown

规则：
- 所有新建 entity 必须指定 entity_type
- 不确定时用 unknown
- 后续代码不得硬编码中文类型名

---

### 4.2 shareholder_entities.company_id
语义：
- 若该主体对应 companies 表中的某家公司，则填入对应 company_id
- 否则为 NULL

规则：
- 自然人通常为 NULL
- 外部未建档公司可先为 NULL
- 若后续该主体被补录为研究公司，可再建立映射

---

### 4.3 shareholder_entities.country
语义：
- company：注册/归属国家
- natural_person：国籍或主要归属国家
- 其他主体：最合理的所属国家
- 无法判断时可空

---

### 4.4 shareholder_structures.is_direct
语义：
- 是否为原始披露的直接关系

规则：
- True：原始一跳关系
- False：间接或业务标记关系
- 不可与“图遍历一跳”混淆

---

### 4.5 shareholder_structures.control_type
建议枚举：
- equity
- agreement
- voting_right
- concerted_action
- other

### 4.6 control_relationships.control_path
当前统一规则：
- 存储 JSON 数组字符串
- 不使用自由拼接文本作为标准格式

示例：
`["Entity A", "Entity B", "Target Company"]`

说明：
- 对前端展示时可再格式化为 `A -> B -> C`
- 对程序处理时必须按 JSON 解析

### 4.7 country_attributions.attribution_type
建议枚举值：
- auto_inferred
- manual_confirmed
- manual_override
- rule_based
- undetermined

## 5. 开发分层规范
后端目录建议采用以下职责分层：

`backend/`  
`├── api/`  # 路由层，只做参数接收、依赖注入、响应返回  
`├── crud/`  # 基础数据库操作  
`├── models/`  # SQLAlchemy ORM 模型  
`├── schemas/`  # Pydantic 请求/响应模型  
`├── services/`  # 业务服务层  
`├── analysis/`  # 图分析与算法层  
`├── core/`  # 配置、数据库连接、常量、枚举  
`└── tests/`  # pytest 测试  

规则：
- `api/` 不直接写复杂业务逻辑
- `crud/` 不写图算法
- `analysis/` 不直接操作 HTTP 响应
- `services/` 负责把 CRUD、analysis、schema 串起来

## 6. API 层规范

### 6.1 路由职责
每个路由函数只做四件事：
- 接收参数
- 注入数据库 session
- 调用 service/analysis
- 返回 schema

不得在路由函数里直接写：
- 递归穿透算法
- 控制权计算
- 复杂 SQL 拼装
- 人工字符串拼接逻辑

FastAPI 依赖统一使用 `Depends()` 管理。

### 6.2 响应模型
所有接口必须使用 Pydantic schema 返回，不允许直接返回 ORM 对象。

## 7. 控制链分析规范
这是当前项目的核心开发部分。

### 7.1 分析入口
所有控制链分析从 `company_id` 开始。

标准流程：
1. 根据 `company_id` 找到对应的 `entity_id`
2. 以该 `entity_id` 为目标节点
3. 在 `shareholder_structures` 中向上递归查找控制关系
4. 生成路径集合
5. 计算控制权
6. 输出控制结论

### 7.2 必备辅助函数
Codex 后续实现时，必须优先补齐以下函数：

```python
def get_entity_by_company_id(db: Session, company_id: int) -> ShareholderEntity | None: ...

def get_current_incoming_relationships(db: Session, to_entity_id: int) -> list[ShareholderStructure]: ...

def build_control_paths(db: Session, target_entity_id: int, max_depth: int = 10) -> list[list[ShareholderStructure]]: ...
```

### 7.3 路径遍历规则
第一版统一采用：
- DFS
- 防环
- 最大层级限制
- 仅分析 is_current = True 的关系
- 优先使用有 effective_date / expiry_date 且在有效期内的关系

### 7.4 防环规则
遍历过程中维护当前路径节点集合：
- 若下一个 from_entity_id 已出现在当前路径中，则视为循环
- 当前分支终止
- 记录循环统计信息，但不抛异常

## 8. 控制权计算规范

### 8.1 第一版模型
第一版只实现路径乘积 + 多路径求和，不实现复杂矩阵收敛模型。

规则：
- 单条路径控制权 = 路径上所有 holding_ratio 连乘
- 多条不同路径的控制权 = 各路径控制权求和
- 若某条边 holding_ratio 为空，且 control_type != equity，则该路径仅记录为“控制依据路径”，不计入数值乘积
- 第一版 control_ratio 可为空，若无法稳定量化则返回 NULL

### 8.2 推荐函数
def calculate_path_control_ratio(path: list[ShareholderStructure]) -> float | None: ...
def aggregate_controller_ratios(paths: list[list[ShareholderStructure]]) -> dict[int, float]: ...

### 8.3 第一版实际控制人识别规则
按以下优先级判断：
- 若已有显式 is_actual_controller = True 的历史结论且未被人工否定，可优先参考
- 否则选择控制链最上层主体
- 若有多个上层主体，则按控制权数值排序
- 若仍无法唯一确定，则标记为 undetermined

## 9. control_relationships 生成规则

### 9.1 本表写入来源
本表允许两种来源：
- 自动分析生成
- 人工确认/修订

建议后续增加字段区分来源；当前阶段先用：
- notes
- basis
- is_actual_controller
体现。

### 9.2 自动生成规则
自动写入时：
- company_id：目标公司
- controller_entity_id：识别出的控制主体
- controller_name：来自 entity_name
- controller_type：来自 entity_type
- control_type：根据路径主导关系得出
- control_ratio：若可算则写入
- control_path：JSON 数组字符串
- basis：简要解释规则来源

### 9.3 覆盖规则
自动任务不得无条件删除人工修改内容。

第一版建议：
- 自动分析先查是否已有该公司结论
- 若已有且备注/规则显示为人工确认，则只返回候选结果，不直接覆盖
- 若后续需要覆盖，必须显式调用专门 service

## 10. 国别归属推断规范

### 10.1 推断入口
所有国别归属推断基于：
- companies
- shareholder_entities
- shareholder_structures
- control_relationships（可作为缓存参考，但不是唯一依据）

### 10.2 推断规则 v1
第一版采用简单规则：
- 获取目标公司的实际控制主体
- 优先读取控制主体的 shareholder_entities.country
- 若为空且该实体映射到公司，则参考对应 companies 的国家信息
- 将所得结果作为 actual_control_country
- 与目标公司的 incorporation_country 和 listing_country 一并写入结论表

### 10.3 人工覆盖规则
若 country_attributions.is_manual = True：
- 自动推断接口默认不覆盖数据库记录
- 只返回“推荐推断值”

### 10.4 无法确定规则
若无法确定：
- actual_control_country = "Undetermined"
- attribution_type = "undetermined"

## 11. 特殊结构识别规范

本阶段不进入主控制算法，只作为扩展模块预留。

### 11.1 支持识别的特殊结构
后续可支持：
- VIE
- 红筹
- 多主体共同控制
- 离岸控股链
- 协议控制

### 11.2 第一阶段实现策略
第一阶段不做完全自动识别，只做：
- 规则标记
- 结构提示
- 特殊 control_type 路径展示

### 11.3 LLM 参与边界
大模型只参与：
- 非结构化文本解释
- 特殊结构候选识别
- 分析说明生成

大模型不直接参与：
- 主控制权数值计算
- 图遍历逻辑
- 基础事实写库

## 12. CRUD 与 Service 规范

### 12.1 CRUD 层
只负责：
- create
- read
- update
- delete
- 基础筛选查询

不得包含：
- 控制链递归
- 路径计算
- 国别推断

### 12.2 Service 层
负责：
- 调用 CRUD
- 调用 analysis
- 组织 schema
- 实现“自动分析但不覆盖人工结果”的规则

## 13. 测试规范

当前项目已有 pytest + test.db 体系，后续必须沿用。

### 13.1 测试优先级
先写以下测试：
- company_id -> entity_id 映射测试
- 单层控制链测试
- 多层控制链测试
- 环检测测试
- 多路径控制权聚合测试
- 实际控制人识别测试
- 国别归属推断测试
- 人工结果不被覆盖测试

### 13.2 基础样例集
建议至少准备以下样例：
- 线性结构：A -> B -> C
- 分叉结构：A -> C, B -> C
- 循环结构：A -> B -> A
- 离岸结构：Cayman HoldCo -> China OpCo
- 自然人控制：张三 -> A公司 -> B公司

## 14. Codex 使用规则

这是给 Codex 最重要的部分。

### 14.1 一次只做一个小目标
禁止一次性让 Codex 同时完成：
- 新模型
- 新路由
- 新算法
- 新测试
- 数据迁移

推荐一轮只做一个 commit 级任务。

### 14.2 优先级顺序
后续开发顺序固定为：
- company_id 到 entity_id 映射
- shareholder_structures 基础查询函数
- 递归控制链分析
- 控制权计算
- 实际控制人识别
- control_relationships 自动写入
- 国别归属推断
- 特殊结构识别扩展

### 14.3 Codex 指令模板

示例：
实现一个服务，将 company_id 映射到对应的股东主体（shareholder entity）。仅使用现有的 SQLAlchemy 模型，不要修改数据库结构（schema）。基于当前的 test.db 测试环境，添加 pytest 测试覆盖。

再例如：
实现基于 shareholder_structures 的递归控制链遍历。使用带有环检测（cycle protection）和最大深度限制（max_depth）的 DFS 算法。仅包含当前有效的关系（current relationships）。返回确定性的路径结果，并添加 API 测试。

## 15. 当前阶段不做的事

为避免范围失控，当前阶段禁止 Codex 主动扩展以下内容：
- 前端页面
- PostgreSQL 迁移
- Alembic 初始化
- BusinessSegment 模型
- AnnotationLog 模型
- 大模型接入代码
- 超图建模
- 复杂收敛矩阵控制算法

这些都属于后续阶段。

## 16. 第一阶段交付目标

当前阶段代码闭环应达到：
- 能从 company_id 找到网络中的目标实体
- 能基于 shareholder_structures 递归生成控制链
- 能输出候选控制主体和路径
- 能用简单规则给出实际控制人
- 能生成国别归属候选值
- 能保证人工结果不被自动覆盖