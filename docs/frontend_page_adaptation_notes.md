# 前端页面适配简短说明

日期：2026-04-18

## 1. 当前摘要区使用字段

当前 `ControlSummaryCard.vue` 已消费：

- `control_analysis.direct_controller`
- `control_analysis.actual_controller`
- `control_analysis.leading_candidate`
- `control_analysis.display_controller`
- `control_analysis.controller_count`
- `control_analysis.identification_status / controller_status`
- controller 行内的 `controller_name`、`controller_type`、`control_type`、`control_ratio`、`control_mode`、`promotion_reason`、`terminal_failure_reason`
- `country_attribution.actual_control_country`
- `country_attribution.attribution_type`
- `country_attribution.attribution_layer`
- `country_attribution.look_through_applied`
- `country_attribution.country_inference_reason`
- `country_attribution.basis`

## 2. 当前图例说明过时点

`ControlStructureDiagram.vue` 的右侧说明仍有几处旧版语义：

- “基金 / 公众持股”说明过短，容易把 Public Float / dispersed ownership 看成普通基金。
- 节点角色说明偏向“实际控制人一定存在”，需要兼容 leading candidate 与无唯一实际控制人场景。
- “关键路径节点”没有说明其可能包含 direct controller、中间穿透载体、ultimate / leading candidate。
- 边样式说明过短，没有解释关键路径是后端判定参考路径，折叠提示不是新的控制类型。
- 交互说明默认提到“上方实际控制人”，在 leading candidate 场景需要动态表达。

## 3. 后端值得补展示字段

基于 `ultimate_controller_enhanced_dataset_working.db` 抽样，当前 summary / attribution / relationship graph 已足够支撑本轮前端升级：

- `direct_controller` 与 `actual_controller` 可能不同，如 company 365。
- `leading_candidate` 可在 fallback 场景保留，如 company 9。
- `attribution_layer = fallback_incorporation` 表示注册地兜底，不是唯一 actual controller 归属。
- `attribution_layer = joint_control_undetermined` 与 `terminal_failure_reason = joint_control` 表示共同控制阻断，如 company 108。
- `look_through_applied = true` 与 `promotion_reason` 可解释上卷，如 `beneficial_owner_priority`、`controls_direct_controller`、`disclosed_ultimate_parent`。
- `controller_name` 中的 `Public Float - ...` 需要按公众持股 / 分散流通股集合表达。

## 4. 本轮准备改动文件

- `frontend/src/components/ControlSummaryCard.vue`
  - 优化 direct / ultimate / leading 的占位与重复说明。
  - 优化 fallback、promotion、terminal failure、Public Float 的研究型文案。

- `frontend/src/components/ControlStructureDiagram.vue`
  - 不改图布局和节点交互。
  - 只升级右侧主体类型、节点角色、边样式、交互说明和少量 hover 文案。
