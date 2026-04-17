# Semantic Control Evidence Model v1

本文档说明 unified control inference 中语义控制边的第一版结构化证据打分模型。它不是机器学习模型，而是规则化、可解释、可测试的 evidence scoring layer，用于替代继续在各类关系里堆零散关键词。

## 目标

语义控制关系包括：

- `agreement`
- `voting_right`
- `board_control`
- `nominee`
- `vie`

模型目标是把这些关系拆成多个证据信号维度，分别评分后合成 `semantic_strength`，再进入现有路径搜索、候选人汇总、direct/ultimate 判定、promotion/stop/fallback 逻辑。

## 评分输出

每条语义边会生成一个 `SemanticEvidenceScore`：

- `semantic_strength`：0 到 1，用作该边的 `semantic_factor`
- `confidence_adjustment`：0 到 1，目前记录为 reliability 解释，实际路径置信度仍沿用 `confidence_level` 映射
- `flags`：语义标签，例如 `power_rights`、`economic_benefits`、`needs_review`
- `breakdown`：结构化解释，写入边证据 payload，便于控制路径 basis 和 HTML/调试检查

## 维度 A：Power Signals

Power 反映“谁能控制决策权”。来源包括：

- `effective_voting_ratio`
- `voting_ratio`
- `voting proxy`
- `power of attorney`
- `appoint majority directors`
- `nomination_rights`
- `control relevant activities`
- `de facto control`
- board seats / board size

示例规则：

- board seats 可计算时，`board_seats / total_board_seats` 直接作为 power score
- `full voting control`、`controlling voting rights` 可升到强控制
- `super-voting` 按有效表决权比例放大，但封顶为 1
- VIE / agreement 中出现强合同控制信号时，power score 至少进入强语义区间

## 维度 B：Economics Signals

Economics 反映“谁享有控制带来的收益或风险”。来源包括：

- `economic_ratio`
- `benefit_capture`
- residual returns
- loss absorption
- equity pledge
- contractual rights to variable returns
- substantially all benefits

示例规则：

- `benefit_capture` / `economic_ratio` 作为结构化比例优先使用
- `variable returns`、`economic benefits`、`equity pledge` 等文本证据作为中等经济信号
- `substantially all benefits` 作为强经济信号

## 维度 C：Exclusivity / Irrevocability Signals

Exclusivity / irrevocability 区分弱协议和强控制安排。来源包括：

- exclusive business cooperation
- exclusive service agreement
- exclusive option
- exclusive operating control
- irrevocable voting proxy
- irrevocable power of attorney
- long-term non-revocable arrangements

示例规则：

- 排他安排会增加强控制可信度，并打 `exclusive_control_arrangement`
- 不可撤销安排会打 `irrevocable_control_arrangement`
- 单独的 exclusivity 一般不直接等于 actual controller，但会支撑 agreement / VIE 进入强语义控制

## 维度 D：Disclosure / Beneficial Ownership Signals

Disclosure 反映受益所有人披露状态和 nominee 是否可被穿透。来源包括：

- `beneficial_owner_disclosed`
- `beneficial_owner_confirmed`
- `beneficiary_controls`
- `beneficial_owner_controls`
- `beneficial_owner_unknown`
- nominee / custodian / held on behalf 文本

示例规则：

- nominee 未披露受益所有人时，promotion 继续被 `nominee_without_disclosure` 阻断
- metadata 标记受益所有人未知时，继续被 `beneficial_owner_unknown` 阻断
- 已披露并带明确控制文本时，nominee 可形成较强语义链条

## 维度 E：Reliability / Confidence Signals

Reliability 反映证据质量。来源包括：

- `confidence_level`
- `relation_metadata` 是否存在
- `control_basis` 是否存在
- `agreement_scope` 是否存在
- 证据文本是否足够丰富
- source 是否存在

当前实现中，路径置信度仍主要由 `confidence_level` 转为 `confidence_weight`：

- high -> 0.9
- medium -> 0.7
- unknown -> 0.6
- low -> 0.4

Actual / ultimate 输出继续受低置信度闸门限制：

- 候选人刚过控制阈值
- 且总体置信度低于 0.50
- 则不写 direct/actual controller，而是保留 leading candidate，并写 `low_confidence_evidence_weak`

## 合成规则

不同关系类型采用不同的合成方式：

- `board_control`：以 power score 为核心，能计算董事席位比例时直接使用
- `voting_right`：以 voting power 为核心，强表决权文本可增强
- `nominee`：以 disclosure + explicit beneficial-owner control 为核心，未披露继续阻断
- `vie`：power + economics 同时存在时为强语义控制；强 exclusivity / irrevocability 可支持进入 control；只有单边证据则保守为 `needs_review`
- `agreement`：power、economics、exclusivity 共同决定；弱协议默认不升为 control

## 阻断项

以下逻辑继续保留：

- `joint_control_candidate`：触发 joint control 路径，不选唯一 actual controller
- `protective_rights`：保护性权利不形成控制
- `beneficial_owner_unknown`
- `nominee_without_disclosure`
- `look_through_not_allowed`
- `evidence_insufficient`
- `low_confidence_evidence_weak`

## 当前边界

v1 仍是规则模型，不做复杂证据概率融合。后续可以继续细化：

- 将 `confidence_adjustment` 纳入路径 `confidence_weight`
- 对 source quality 建立更细等级
- 对 power/economics/exclusivity 使用可配置权重表
- 区分 VIE、普通 agreement、voting proxy 的最终 attribution subtype
