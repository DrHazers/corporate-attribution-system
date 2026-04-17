# 最终实际控制人判定规则 V2

本文档固化当前 `v2` 数据库与代码下的终局判定规则，目标是把“direct controller / ultimate controller”区分清楚，并让 promotion、stop、joint control、leading candidate、fallback 都有稳定口径。

对应实现入口：

- [control_inference.py](/d:/graduation_project/corp_attribution_system/backend/analysis/control_inference.py)
- [ownership_penetration.py](/d:/graduation_project/corp_attribution_system/backend/analysis/ownership_penetration.py)
- [test_terminal_controller_v2.py](/d:/graduation_project/corp_attribution_system/tests/test_terminal_controller_v2.py)

## 判定顺序

1. 先对目标公司生成全部控制候选人。
2. 在 `min_depth = 1` 的候选人里选出 top direct candidate。
3. 只有当该候选人在目标公司层面达到 `control` 时，才把它视为 `direct controller`。
4. 若 direct controller 成立，再判断是否需要继续向上 promotion。
5. 若 promotion 成功，写 `ultimate controller`。
6. 若 promotion 被阻断，则根据阻断原因决定：
   - 保留 direct controller
   - 只保留 leading candidate
   - 或直接 fallback 到注册地

## Direct Controller 规则

`direct controller` 必须同时满足：

- 是目标公司的直接上一层候选人
- 在目标公司层面达到 `control`
- 不是 direct layer 的 `joint control`
- 不是 `nominee_without_disclosure` / `beneficial_owner_unknown` 这类直接证据阻断

若只达到 `significant influence`，则它不是 `direct controller`，只能保留为 `leading candidate`。

## Promotion 触发条件

当 direct controller 已成立时，若它本身又被更上游主体控制，则允许继续上卷。当前最小可执行规则是：

- 上游主体对当前主体达到 `control`
- 这种控制通常来自：
  - `>= 50%` 股权/有效控制比例
  - 或明确控制语义（协议控制、表决权控制、董事会控制等）
- 且该上游主体在目标公司层面聚合后仍达到 `control`

满足以上条件时，可从当前主体 promotion 到其父层候选人。

## Terminal Stop 条件

出现以下任一情况时，停止继续上卷：

- 当前主体本身更像终局层：
  - `natural_person`
  - `state`
  - `person` / `government`
  - `family_vehicle` / `founder_vehicle` / `government_agency`
  - `ultimate_owner_hint = true`
- 当前层之上不存在达到 `control` 的唯一父层主体
- 父层只有 `significant influence`，没有达到 `control`
- 出现 `look_through_not_allowed` / `protective_right_only`
- 出现 cycle

若停止时当前主体在目标公司层面仍然达到 `control`，则当前主体就是 `ultimate controller`。

## Joint Control 规则

以下情况判为 `joint control`，不写唯一 ultimate controller：

- 语义上已明确 joint control
- 同一层出现两个及以上控制候选人，且它们都达到 `control`，并且顶部分数在当前阈值内构成并列控制

当前规则里，典型 `50/50` 的父层控制会被视为 structural joint control。

## 只能保留 Leading Candidate 的情况

以下情况不写 `actual/ultimate controller`，只保留 `leading candidate`，并写 `terminal_failure_reason`：

- direct layer 本身没有达到 `control`
- 父层 close competition，无法唯一上卷
- `beneficial_owner_unknown`
- `nominee_without_disclosure`
- 其他证据明显不足，无法把某一主体稳定写成终局层

这里的 `leading candidate` 只是“当前最强候选”，不是“最终实际控制人”。

## Fallback 规则

国家归属当前按以下顺序处理：

1. 有唯一 `ultimate controller`：
   - `attribution_layer = ultimate_controller_country`
2. 没有唯一 ultimate，但存在稳定的 `direct controller`：
   - `attribution_layer = direct_controller_country`
3. direct 层也没有稳定控制主体：
   - `attribution_layer = fallback_incorporation`
4. 若是 joint control 且无单一国家：
   - `attribution_layer = joint_control_undetermined`

因此：

- “上卷失败但 direct controller 明确”不等于直接 fallback 注册地
- “连 direct control 都不成立”才 fallback 到 `incorporation_country`

## 写回字段口径

当前规则会稳定写回以下关键字段：

- `control_relationships.control_tier`
- `control_relationships.is_direct_controller`
- `control_relationships.is_ultimate_controller`
- `control_relationships.promotion_source_entity_id`
- `control_relationships.promotion_reason`
- `control_relationships.terminal_failure_reason`
- `control_relationships.control_chain_depth`
- `control_relationships.terminal_control_score`
- `country_attributions.actual_controller_entity_id`
- `country_attributions.direct_controller_entity_id`
- `country_attributions.attribution_layer`
- `country_attributions.look_through_applied`

## 当前已覆盖的边界

- 经典股权上卷：`A -> Target 70`, `C -> A 90`
- 直接层即终局层
- 父层 `50/50` 共同控制阻断 promotion
- 直接层控制不足，只保留 leading candidate
- `spv` / `holding_company` 这类中间壳层继续上卷
- `nominee_without_disclosure` 阻断 actual controller 写入

## 当前仍未完全覆盖的边界

- 更复杂的基金 `GP/LP`、信托、国家资本多层混合结构
- acting-in-concert 的更细粒度识别
- Public Float 作为候选主体时的专门展示策略
- 多层 mixed-control 里“控制力传导衰减”的更细规则
- 更多文本证据到 `beneficial_owner_unknown` 的自动映射
