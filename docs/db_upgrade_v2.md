# 数据库升级到 V2 的说明

本次升级的目标不是替换原始输入层，而是在尽量保留现有 `companies`、`shareholder_entities`、`shareholder_structures` 基础设计的前提下，把输出层和分析留痕层升级到可以长期承载“最终实际控制人识别”。

## 1. 库文件口径

- 原库：`company_test_analysis_industry.db`
- 新库：`company_test_analysis_industry_v2.db`

本轮已经按要求完成复制与升级，原库不改，后续默认开发/联调库切到：

- `sqlite:///d:/graduation_project/corp_attribution_system/company_test_analysis_industry_v2.db`

对应默认配置位于：

- [backend/database.py](/d:/graduation_project/corp_attribution_system/backend/database.py)

## 2. 为什么要升级

旧版结果层更偏向“最强控制候选人识别”，主要问题是：

1. 直接控制主体和最终实际控制人没有明确分层
2. 无法稳定表达“从中间层继续上卷到更上游终局主体”
3. 共同控制、leading candidate、fallback 等状态留痕不够完整
4. 国家归属与控制层级耦合较重
5. refresh 结果缺少 run / audit 级别的过程记录

V2 的目标是把这些层级和留痕补齐，同时尽量不推翻现有输入表设计。

## 3. 本次新增/增强的表和字段

### 3.1 `shareholder_entities`

新增字段：

- `entity_subtype`
- `ultimate_owner_hint`
- `look_through_priority`
- `controller_class`
- `beneficial_owner_disclosed`

### 3.2 `shareholder_structures`

新增字段：

- `voting_ratio`
- `economic_ratio`
- `is_beneficial_control`
- `look_through_allowed`
- `termination_signal`
- `effective_control_ratio`

### 3.3 `control_relationships`

新增字段：

- `control_tier`
- `is_direct_controller`
- `is_intermediate_controller`
- `is_ultimate_controller`
- `promotion_source_entity_id`
- `promotion_reason`
- `control_chain_depth`
- `is_terminal_inference`
- `terminal_failure_reason`
- `immediate_control_ratio`
- `aggregated_control_score`
- `terminal_control_score`
- `inference_run_id`

兼容约定：

- 旧字段 `is_actual_controller` 仍保留
- 在 V2 里它与 `is_ultimate_controller` 对齐，表示“最终实际控制人”

### 3.4 `country_attributions`

新增字段：

- `actual_controller_entity_id`
- `direct_controller_entity_id`
- `attribution_layer`
- `country_inference_reason`
- `look_through_applied`
- `inference_run_id`

### 3.5 新表 `control_inference_runs`

用于记录每次 refresh 的参数、模式、阈值和摘要。

### 3.6 新表 `control_inference_audit_log`

用于记录关键终局判定动作，例如：

- `candidate_selected`
- `promotion_to_parent`
- `promotion_blocked`
- `terminal_confirmed`
- `joint_control_detected`

## 4. 如何生成和升级 V2 数据库

执行：

```powershell
$env:PYTHONPATH='d:\graduation_project\corp_attribution_system'
.\venv\Scripts\python.exe -m scripts.upgrade_db_to_v2 --force-copy
```

脚本位置：

- [scripts/upgrade_db_to_v2.py](/d:/graduation_project/corp_attribution_system/scripts/upgrade_db_to_v2.py)

它会做三件事：

1. 把 `company_test_analysis_industry.db` 复制成 `company_test_analysis_industry_v2.db`
2. 用 SQLAlchemy 建新表
3. 用 SQLite 升级逻辑补新字段、索引和默认回填

脚本可重复执行；如果传 `--force-copy`，会重新从原库复制一份再升级。

## 5. 如何验证升级结果

执行：

```powershell
$env:PYTHONPATH='d:\graduation_project\corp_attribution_system'
.\venv\Scripts\python.exe -m scripts.verify_db_v2
```

脚本位置：

- [scripts/verify_db_v2.py](/d:/graduation_project/corp_attribution_system/scripts/verify_db_v2.py)

它会检查：

1. 新表是否存在
2. 关键新字段是否存在
3. V2 结构是否满足当前代码预期

## 6. 代码适配范围

本轮已同步适配这些位置：

- [backend/analysis/control_inference.py](/d:/graduation_project/corp_attribution_system/backend/analysis/control_inference.py)
- [backend/analysis/ownership_penetration.py](/d:/graduation_project/corp_attribution_system/backend/analysis/ownership_penetration.py)
- [backend/analysis/control_chain.py](/d:/graduation_project/corp_attribution_system/backend/analysis/control_chain.py)
- [backend/analysis/country_attribution_analysis.py](/d:/graduation_project/corp_attribution_system/backend/analysis/country_attribution_analysis.py)
- [backend/analysis/industry_analysis.py](/d:/graduation_project/corp_attribution_system/backend/analysis/industry_analysis.py)
- [backend/models/shareholder.py](/d:/graduation_project/corp_attribution_system/backend/models/shareholder.py)
- [backend/models/control_relationship.py](/d:/graduation_project/corp_attribution_system/backend/models/control_relationship.py)
- [backend/models/country_attribution.py](/d:/graduation_project/corp_attribution_system/backend/models/country_attribution.py)
- [backend/models/control_inference_run.py](/d:/graduation_project/corp_attribution_system/backend/models/control_inference_run.py)
- [backend/models/control_inference_audit_log.py](/d:/graduation_project/corp_attribution_system/backend/models/control_inference_audit_log.py)

## 7. 如何运行测试

本轮新增/覆盖的关键测试包括：

- [tests/test_db_upgrade_v2.py](/d:/graduation_project/corp_attribution_system/tests/test_db_upgrade_v2.py)
- [tests/test_terminal_controller_v2.py](/d:/graduation_project/corp_attribution_system/tests/test_terminal_controller_v2.py)

推荐先跑这一组：

```powershell
.\venv\Scripts\python.exe -m pytest `
  tests/test_db_upgrade_v2.py `
  tests/test_terminal_controller_v2.py `
  tests/test_control_inference_engine.py `
  tests/test_control_summary_candidates.py `
  tests/test_mixed_control_paths.py `
  tests/test_ownership_penetration.py -q
```

## 8. 当前实现边界

这次已经把“结构能承载终局识别”和“结果能分层写回”做起来了，但仍有几个后续可继续优化的边界：

1. `ultimate_owner_hint` / `look_through_priority` 当前已接入，但仍偏规则化，后续还能更细
2. `termination_signal` 已参与终局阻断，但还不是完整专家系统
3. Public Float / nominee / beneficial-owner 相关展示策略仍值得单独细化
4. 终局竞争场景目前已能避免误写 actual controller，但 leading candidate 的展示话术还可以继续优化
