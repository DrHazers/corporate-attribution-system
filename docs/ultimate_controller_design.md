# 最终实际控制人识别设计说明

本文说明当前 V2 版本下，“direct controller / intermediate controller / ultimate controller” 是如何区分的，以及终局上卷的基本判定口径。

对应实现主入口：

- [backend/analysis/control_inference.py](/d:/graduation_project/corp_attribution_system/backend/analysis/control_inference.py)
- [backend/analysis/ownership_penetration.py](/d:/graduation_project/corp_attribution_system/backend/analysis/ownership_penetration.py)

## 1. 三层主体的定义

### 1.1 Direct Controller

直接控制主体，指在目标公司这一层上，直接连到目标公司的主导候选主体。

在当前实现里，它会单独写回：

- `control_relationships.is_direct_controller = 1`
- `country_attributions.direct_controller_entity_id`

### 1.2 Intermediate Controller

中间控制层，指位于最终控制链中间的主体。

例如：

- `A -> Target = 70%`
- `C -> A = 90%`

那么：

- `A` 是 direct controller
- `A` 同时也是 intermediate controller
- `C` 是 ultimate controller

### 1.3 Ultimate Controller

最终实际控制人，指在终局上卷后仍成立的控制主体。

兼容口径：

- `is_actual_controller`
- `is_ultimate_controller`

在当前 V2 里保持一致，表示终局实控结果。

## 2. 当前终局上卷的基本流程

### 步骤 1：先做公司层候选人识别

系统仍先按统一控制推断引擎生成公司层候选人：

1. 搜索所有有效控制路径
2. 聚合同一主体的多条路径
3. 计算公司层的 `aggregated_control_score`

### 步骤 2：选出 direct controller

系统会优先从“深度为 1 的候选人”里选 direct controller，也就是：

- 候选人的最短路径深度 `min_depth = 1`

### 步骤 3：判断是否继续向上 look through

如果 direct controller 本身又被更上游主体控制，系统会继续检查其父层候选人。

当前会综合考虑：

- 父层是否对当前控制层形成 `control`
- 上卷后的父层是否仍然对目标公司形成足够强的公司层控制
- `entity_subtype`
- `ultimate_owner_hint`
- `look_through_priority`
- `controller_class`
- `look_through_allowed`
- `termination_signal`

### 步骤 4：决定终局结果

当前会出现四种主要结果：

1. 成功上卷到唯一父层  
   例：`A -> Target 70%`，`C -> A 90%`，则 `C` 成为 ultimate controller

2. direct controller 即终局  
   例：上面没有满足条件的唯一父层，或者继续上卷后已不足以对目标公司形成终局控制

3. 无法唯一识别终局主体  
   例：父层 close competition、joint control、beneficial owner unknown  
   这时：
   - 不写 actual controller
   - 保留 leading candidate
   - 记录 `terminal_failure_reason`

4. 完全没有足够控制信号  
   这时回退到 `fallback_incorporation`

## 3. 写回层怎么表示“从 A 上卷到 C”

如果发生上卷：

- `A`
  - `is_direct_controller = 1`
  - `is_intermediate_controller = 1`
  - `control_tier = direct`

- `C`
  - `is_ultimate_controller = 1`
  - `is_actual_controller = 1`
  - `control_tier = ultimate`
  - `promotion_source_entity_id = A`
  - `promotion_reason = controls_direct_controller / look_through_holding_vehicle / beneficial_owner_priority`

同时：

- `country_attributions.actual_controller_entity_id = C`
- `country_attributions.direct_controller_entity_id = A`
- `country_attributions.attribution_layer = ultimate_controller_country`
- `country_attributions.look_through_applied = 1`

## 4. 两个分数的区别

### 4.1 `aggregated_control_score`

这是候选人针对目标公司的聚合控制分。

例如：

- `C -> A = 90%`
- `A -> Target = 70%`

则 `C` 对目标公司的聚合控制分约为：

- `0.9 * 0.7 = 0.63`

### 4.2 `terminal_control_score`

这是终局判定步骤里真正用来确认“是否继续向上”的那一步分数。

在上面的例子里：

- `C` 对 `A` 的终局控制分是 `0.90`

所以：

- `aggregated_control_score = 0.63`
- `terminal_control_score = 0.90`

这两个分数一起保留，可以把“公司层影响力”和“终局上卷依据”区分开。

## 5. 审计日志会记什么

每次 refresh 会生成一条 `control_inference_runs` 记录，并按关键步骤写 `control_inference_audit_log`。

当前重点留痕的动作包括：

- `candidate_selected`
- `promotion_to_parent`
- `promotion_blocked`
- `terminal_confirmed`
- `joint_control_detected`

这能回答几类关键问题：

1. 为什么先选了某个 direct controller
2. 为什么又从 A 上卷到了 C
3. 为什么没有继续上卷
4. 为什么最终没有写 actual controller

## 6. 当前边界

当前版本已经能稳定支撑：

- direct / intermediate / ultimate 分层
- 从 direct controller 向父层继续上卷
- close competition / joint control / fallback 的结果留痕
- 国家归属与控制层级解耦

但还不是“终极版专家系统”。后续仍可继续增强：

1. Public Float 的展示策略
2. nominee / beneficial owner 的终止条件细化
3. state / fund / trust 结构的终局偏好规则
4. 多层 mixed-control 场景下的解释文案
