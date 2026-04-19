<script setup>
import { computed } from 'vue'

const props = defineProps({
  company: {
    type: Object,
    default: () => ({}),
  },
  autoControlAnalysis: {
    type: Object,
    default: () => ({}),
  },
  autoCountryAttribution: {
    type: Object,
    default: () => ({}),
  },
  currentControlAnalysis: {
    type: Object,
    default: () => ({}),
  },
  currentCountryAttribution: {
    type: Object,
    default: () => ({}),
  },
  manualOverride: {
    type: Object,
    default: null,
  },
})

const NO_UNIQUE_CONTROLLER_TEXT = '暂无唯一实际控制人'
const NO_DATA_TEXT = '暂无'

const CONTROL_TYPE_LABELS = {
  equity: '股权控制',
  equity_control: '股权控制',
  direct_equity_control: '股权控制',
  indirect_equity_control: '股权控制',
  significant_influence: '重大影响',
  agreement: '协议控制',
  agreement_control: '协议控制',
  board_control: '董事会控制',
  voting_right: '表决权控制',
  voting_right_control: '表决权控制',
  nominee: '代持/名义持有',
  nominee_control: '代持/名义持有',
  vie: 'VIE 控制',
  vie_control: 'VIE 控制',
  mixed_control: '混合控制',
  joint_control: '共同控制',
}

const PROMOTION_REASON_LABELS = {
  disclosed_ultimate_parent: '上层主体具备更强终局控制特征。',
  beneficial_owner_priority: '受益所有人线索更强，优先采用上层主体。',
  controls_direct_controller: '上层主体能够控制直接控制人，因此继续上卷认定。',
  direct_controller_look_through: '直接控制层更像中间平台，继续向上穿透。',
  holding_vehicle_look_through: '直接控制人属于中间持股平台，继续向上穿透。',
  intermediate_holding_look_through: '中间控股平台已被穿透，按上层主体形成终局判断。',
  upstream_controller_priority: '上层主体具备更强终局控制信号。',
  ultimate_owner_hint: '存在终局控制人披露线索，按上层主体进行认定。',
  look_through_holding_vehicle: '中间控股平台已被穿透，按上层主体形成终局判断。',
  trust_vehicle_lookthrough: '信托或载体层已被穿透，按上层主体形成终局判断。',
}

const TERMINAL_FAILURE_REASON_LABELS = {
  joint_control: '存在共同控制，未形成唯一实际控制人。',
  beneficial_owner_unknown: '受益所有人未充分披露，自动结果保守阻断。',
  nominee_without_disclosure: '存在代持或名义持有结构，但缺少可穿透披露。',
  low_confidence_evidence_weak: '证据强度不足，未形成唯一实际控制人。',
  close_competition: '多个候选主体信号接近，暂未形成唯一实际控制人。',
  look_through_not_allowed: '当前不满足继续向上穿透条件，未形成唯一实际控制人。',
  protective_right_only: '仅发现保护性权利，不足以构成实际控制。',
  no_control_relationships: '缺少可用于判定的控制关系数据。',
  no_candidate: '未发现满足控制阈值的候选主体。',
  insufficient_evidence: '证据不足，未形成唯一实际控制人。',
  evidence_insufficient: '证据不足，未形成唯一实际控制人。',
  ownership_aggregation_pattern: '检测到公众持股/分散持股聚合表达。',
}

const COUNTRY_INFERENCE_REASON_LABELS = {
  derived_from_direct_controller: '根据直接控制人所在国家/地区确定。',
  derived_from_ultimate_controller: '根据实际控制人所在国家/地区确定。',
  fallback_to_incorporation: '已按注册地进行归属回退。',
  fallback_no_identifiable_terminal_controller: '未识别到可归属的终局控制主体，已按注册地进行归属回退。',
  joint_control_no_single_country: '存在共同控制，暂不输出单一控制国家/地区。',
}

const TERMINAL_IDENTIFIABILITY_LABELS = {
  identifiable_single_or_group: '可识别终局主体',
  aggregation_like: '结构信号主体',
  unknown_or_blocked: '已排除出 actual race',
}

const TERMINAL_SUITABILITY_LABELS = {
  suitable_terminal: '可作为终局主体',
  prefer_rollup: '需继续向上识别',
  blocked_terminal: '不适合作为终局主体',
  pattern_only: '不适合作为终局主体',
}

const TERMINAL_PROFILE_REASON_LABELS = {
  terminal_identity_signal: '主体画像可支撑终局识别。',
  default_identifiable_entity: '主体本身可识别且可归属。',
  rollup_intermediary_entity: '主体更像中间持股层或穿透节点。',
  ownership_pattern_entity_profile: '主体画像更接近公众持股/分散持股聚合表达。',
  ownership_pattern_edge_signal: '路径和边证据显示为 ownership aggregation。',
  reused_non_terminal_ownership_bucket: '主体更像复用型持股池，不适合作为终局主体。',
  weak_name_hint: '当前仅存在较弱名称线索。',
  high_ratio_but_no_terminal_governance: '比例较高，但缺少终局治理控制证据。',
  excluded_from_actual_race_due_to_terminal_profile: '已因终局画像被排除出 actual race。',
  manual_result: '当前结果来自人工处理快照。',
}

function normalizeKey(value) {
  return String(value ?? '').trim().toLowerCase()
}

function parseMaybeJson(value) {
  if (!value) {
    return null
  }
  if (typeof value === 'object') {
    return value
  }
  if (typeof value !== 'string') {
    return null
  }
  const trimmed = value.trim()
  if (!trimmed || !['{', '['].includes(trimmed[0])) {
    return null
  }
  try {
    return JSON.parse(trimmed)
  } catch {
    return null
  }
}

function firstNonEmpty(...values) {
  for (const value of values) {
    if (value !== null && value !== undefined && String(value).trim() !== '') {
      return value
    }
  }
  return null
}

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function isTruthy(value) {
  if (typeof value === 'boolean') {
    return value
  }
  if (typeof value === 'number') {
    return value !== 0
  }
  if (typeof value === 'string') {
    return ['1', 'true', 'yes', 'y'].includes(normalizeKey(value))
  }
  return false
}

function toPercentNumber(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const normalized = typeof value === 'string' ? value.replace('%', '').trim() : value
  const numeric = Number(normalized)
  if (Number.isNaN(numeric)) {
    return null
  }
  return numeric <= 1 ? numeric * 100 : numeric
}

function formatPercent(value) {
  const numeric = toPercentNumber(value)
  if (numeric === null) {
    return ''
  }
  const fixed = numeric >= 10 ? numeric.toFixed(1) : numeric.toFixed(2)
  return `${fixed.replace(/\.0+$/, '').replace(/(\.\d*[1-9])0+$/, '$1')}%`
}

function safeText(value, fallback = NO_DATA_TEXT) {
  return firstNonEmpty(value) || fallback
}

function controllerName(controller, fallback = NO_UNIQUE_CONTROLLER_TEXT) {
  return (
    firstNonEmpty(
      controller?.controller_name,
      controller?.actual_controller_name,
      controller?.name,
      controller?.entity_name,
      controller?.controller_entity_id ? `主体 ${controller.controller_entity_id}` : null,
      controller?.entity_id ? `主体 ${controller.entity_id}` : null,
    ) || fallback
  )
}

function sameEntity(left, right) {
  const leftId = String(
    firstNonEmpty(left?.controller_entity_id, left?.actual_controller_entity_id, left?.entity_id) || '',
  ).trim()
  const rightId = String(
    firstNonEmpty(right?.controller_entity_id, right?.actual_controller_entity_id, right?.entity_id) || '',
  ).trim()
  if (leftId && rightId) {
    return leftId === rightId
  }
  const leftName = normalizeKey(controllerName(left, ''))
  const rightName = normalizeKey(controllerName(right, ''))
  return Boolean(leftName && rightName && leftName === rightName)
}

function uniqueStrings(values) {
  return Array.from(new Set(values.filter(Boolean)))
}

function controlTypeLabel(value) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return ''
  }
  return CONTROL_TYPE_LABELS[normalized] || String(value)
}

function reasonLabel(value, dictionary) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return ''
  }
  return dictionary[normalized] || String(value)
}

function pathText(path) {
  const names = asArray(path?.path_entity_names)
    .map((name) => String(name ?? '').trim())
    .filter(Boolean)
  if (names.length) {
    return names.join(' → ')
  }
  const ids = asArray(path?.path_entity_ids)
    .map((id) => String(id ?? '').trim())
    .filter(Boolean)
  return ids.length ? ids.map((id) => `主体 ${id}`).join(' → ') : ''
}

function pathDepth(path) {
  const names = asArray(path?.path_entity_names).filter(Boolean)
  if (names.length > 1) {
    return names.length - 1
  }
  const ids = asArray(path?.path_entity_ids).filter(Boolean)
  return ids.length > 1 ? ids.length - 1 : null
}

function candidateKey(candidate) {
  return String(
    firstNonEmpty(
      candidate?.controller_entity_id,
      candidate?.entity_id,
      candidate?.actual_controller_entity_id,
      controllerName(candidate, ''),
    ) || '',
  )
}

function normalizeCandidate(candidate) {
  if (!candidate || typeof candidate !== 'object') {
    return null
  }
  const controlPath = asArray(
    firstNonEmpty(candidate.control_path, candidate.top_paths, candidate.path_summary),
  )
  const key = candidateKey(candidate)
  if (!key) {
    return null
  }
  return {
    key,
    controllerEntityId: firstNonEmpty(
      candidate.controller_entity_id,
      candidate.entity_id,
      candidate.actual_controller_entity_id,
    ),
    name: controllerName(candidate, ''),
    controlType: firstNonEmpty(candidate.control_type, candidate.classification),
    controlRatio: firstNonEmpty(candidate.control_ratio, candidate.immediate_control_ratio),
    aggregatedControlScore: firstNonEmpty(candidate.aggregated_control_score, candidate.total_score),
    terminalControlScore: candidate.terminal_control_score,
    controlMode: candidate.control_mode,
    controlTier: candidate.control_tier,
    semanticFlags: asArray(candidate.semantic_flags),
    terminalFailureReason: candidate.terminal_failure_reason,
    terminalIdentifiability: candidate.terminal_identifiability,
    terminalSuitability: candidate.terminal_suitability,
    terminalProfileReasons: asArray(candidate.terminal_profile_reasons),
    ownershipPatternSignal: isTruthy(candidate.ownership_pattern_signal),
    selectionReason: candidate.selection_reason,
    promotionReason: candidate.promotion_reason,
    isActualController: isTruthy(
      firstNonEmpty(candidate.is_actual_controller, candidate.whether_actual_controller),
    ),
    isLeadingCandidate: isTruthy(candidate.is_leading_candidate),
    isDirectController: isTruthy(candidate.is_direct_controller),
    controlPath,
    pathCount: candidate.path_count ?? controlPath.length ?? null,
    controlChainDepth:
      candidate.control_chain_depth ??
      pathDepth(controlPath[0]) ??
      null,
  }
}

function relationshipAsCandidate(relationship) {
  if (!relationship || typeof relationship !== 'object') {
    return null
  }
  const basis = parseMaybeJson(relationship.basis)
  return normalizeCandidate({
    ...basis,
    ...relationship,
    aggregated_control_score:
      relationship.aggregated_control_score ??
      basis?.aggregated_control_score ??
      basis?.total_score,
    terminal_control_score:
      relationship.terminal_control_score ?? basis?.terminal_control_score,
    path_count: basis?.path_count,
    terminal_profile_reasons:
      relationship.terminal_profile_reasons ?? basis?.terminal_profile_reasons,
    ownership_pattern_signal:
      relationship.ownership_pattern_signal ?? basis?.ownership_pattern_signal,
    semantic_flags: relationship.semantic_flags ?? basis?.semantic_flags,
  })
}

const autoCountryBasis = computed(() => {
  const parsed = parseMaybeJson(props.autoCountryAttribution?.basis)
  return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
})

const autoActualController = computed(
  () => props.autoControlAnalysis?.actual_controller || autoCountryBasis.value?.actual_controller || null,
)

const autoLeadingCandidate = computed(() =>
  firstNonEmpty(
    props.autoControlAnalysis?.leading_candidate,
    props.autoCountryAttribution?.leading_candidate,
    autoCountryBasis.value?.leading_candidate,
  ),
)

const autoDirectCandidate = computed(() =>
  firstNonEmpty(
    props.autoControlAnalysis?.direct_controller,
    props.autoCountryAttribution?.direct_controller,
    autoCountryBasis.value?.direct_controller,
  ),
)

const autoCandidates = computed(() => {
  const merged = new Map()
  const sources = [
    ...asArray(autoCountryBasis.value?.top_candidates),
    ...asArray(props.autoCountryAttribution?.top_candidates),
    ...asArray(props.autoControlAnalysis?.top_candidates),
    ...asArray(props.autoControlAnalysis?.candidates),
  ]
  for (const candidate of sources) {
    const normalized = normalizeCandidate(candidate)
    if (normalized && !merged.has(normalized.key)) {
      merged.set(normalized.key, normalized)
    }
  }

  if (!merged.size) {
    const relationships = asArray(props.autoControlAnalysis?.control_relationships)
    for (const relationship of relationships) {
      const normalized = relationshipAsCandidate(relationship)
      if (normalized && !merged.has(normalized.key)) {
        merged.set(normalized.key, normalized)
      }
    }
  }

  const actual = normalizeCandidate(autoActualController.value)
  const leading = normalizeCandidate(autoLeadingCandidate.value)
  const direct = normalizeCandidate(autoDirectCandidate.value)
  for (const special of [actual, leading, direct]) {
    if (special && !merged.has(special.key)) {
      merged.set(special.key, special)
    }
  }

  return Array.from(merged.values())
    .map((candidate) => {
      const isActual = actual ? sameEntity(candidate, actual) : candidate.isActualController
      const isLeading = leading ? sameEntity(candidate, leading) : candidate.isLeadingCandidate
      const isDirect = direct ? sameEntity(candidate, direct) : candidate.isDirectController
      return {
        ...candidate,
        isActualController: isActual || candidate.isActualController,
        isLeadingCandidate: isLeading || candidate.isLeadingCandidate,
        isDirectController: isDirect || candidate.isDirectController,
      }
    })
    .sort((left, right) => {
      const leftPriority =
        (left.isActualController ? 300 : 0) +
        (left.isLeadingCandidate ? 200 : 0) +
        (left.isDirectController ? 80 : 0) +
        (!left.ownershipPatternSignal ? 20 : 0)
      const rightPriority =
        (right.isActualController ? 300 : 0) +
        (right.isLeadingCandidate ? 200 : 0) +
        (right.isDirectController ? 80 : 0) +
        (!right.ownershipPatternSignal ? 20 : 0)
      if (leftPriority !== rightPriority) {
        return rightPriority - leftPriority
      }
      const leftScore = toPercentNumber(left.terminalControlScore ?? left.aggregatedControlScore) ?? -1
      const rightScore = toPercentNumber(right.terminalControlScore ?? right.aggregatedControlScore) ?? -1
      if (leftScore !== rightScore) {
        return rightScore - leftScore
      }
      return (toPercentNumber(right.controlRatio) ?? -1) - (toPercentNumber(left.controlRatio) ?? -1)
    })
})

const primaryCandidate = computed(() => {
  const actual = autoCandidates.value.find((candidate) => candidate.isActualController)
  if (actual) {
    return actual
  }
  const leading = autoCandidates.value.find((candidate) => candidate.isLeadingCandidate)
  if (leading) {
    return leading
  }
  const direct = autoCandidates.value.find((candidate) => candidate.isDirectController)
  if (direct) {
    return direct
  }
  return autoCandidates.value[0] || null
})

const hasAutoActualController = computed(() => Boolean(controllerName(autoActualController.value, '')))

const autoActualControllerName = computed(() =>
  hasAutoActualController.value
    ? controllerName(autoActualController.value)
    : NO_UNIQUE_CONTROLLER_TEXT,
)

const autoActualControlCountry = computed(() =>
  firstNonEmpty(
    props.autoCountryAttribution?.actual_control_country,
    autoCountryBasis.value?.actual_control_country,
  ) || NO_DATA_TEXT,
)

const autoAttributionType = computed(() =>
  firstNonEmpty(
    props.autoCountryAttribution?.attribution_type,
    autoCountryBasis.value?.attribution_type,
  ) || NO_DATA_TEXT,
)

const promotionReason = computed(() => {
  const reasonMap = autoCountryBasis.value?.promotion_reason_by_entity_id
  const candidateId = String(primaryCandidate.value?.controllerEntityId ?? '').trim()
  return (
    firstNonEmpty(
      autoActualController.value?.promotion_reason,
      autoLeadingCandidate.value?.promotion_reason,
      autoDirectCandidate.value?.promotion_reason,
      candidateId && reasonMap && typeof reasonMap === 'object' ? reasonMap[candidateId] : null,
    ) || ''
  )
})

const terminalFailureReason = computed(() =>
  firstNonEmpty(
    props.autoControlAnalysis?.terminal_failure_reason,
    autoActualController.value?.terminal_failure_reason,
    autoLeadingCandidate.value?.terminal_failure_reason,
    autoDirectCandidate.value?.terminal_failure_reason,
    primaryCandidate.value?.terminalFailureReason,
    autoCountryBasis.value?.terminal_failure_reason,
  ) || '',
)

const countryInferenceReason = computed(() =>
  firstNonEmpty(
    props.autoCountryAttribution?.country_inference_reason,
    autoCountryBasis.value?.country_inference_reason,
  ) || '',
)

const controlTypeValue = computed(() =>
  firstNonEmpty(
    autoActualController.value?.control_type,
    primaryCandidate.value?.controlType,
    autoCountryBasis.value?.control_type,
    autoCountryBasis.value?.classification,
  ) || '',
)

const semanticFlags = computed(() =>
  uniqueStrings([
    ...asArray(primaryCandidate.value?.semanticFlags),
    ...asArray(autoCountryBasis.value?.semantic_flags),
  ]),
)

const terminalIdentifiability = computed(() =>
  firstNonEmpty(
    primaryCandidate.value?.terminalIdentifiability,
    autoCountryBasis.value?.terminal_identifiability,
  ) || '',
)

const terminalSuitability = computed(() =>
  firstNonEmpty(
    primaryCandidate.value?.terminalSuitability,
    autoCountryBasis.value?.terminal_suitability,
  ) || '',
)

const terminalProfileReasons = computed(() =>
  uniqueStrings([
    ...asArray(primaryCandidate.value?.terminalProfileReasons),
    ...asArray(autoCountryBasis.value?.terminal_profile_reasons),
  ]),
)

const ownershipPatternSignal = computed(() =>
  Boolean(
    primaryCandidate.value?.ownershipPatternSignal ||
      isTruthy(autoCountryBasis.value?.ownership_pattern_signal),
  ),
)

const selectedPaths = computed(() => {
  const candidatePaths = asArray(primaryCandidate.value?.controlPath)
  if (candidatePaths.length) {
    return candidatePaths
  }
  return asArray(autoCountryBasis.value?.top_paths)
})

const selectedPathCount = computed(() =>
  firstNonEmpty(
    primaryCandidate.value?.pathCount,
    autoCountryBasis.value?.path_count,
    selectedPaths.value.length ? selectedPaths.value.length : null,
  ),
)

const selectedPathDepth = computed(() =>
  firstNonEmpty(
    primaryCandidate.value?.controlChainDepth,
    autoCountryBasis.value?.path_depth,
    pathDepth(selectedPaths.value[0]),
  ),
)

const primaryPathText = computed(() => pathText(selectedPaths.value[0]))
const supplementalPathCount = computed(() =>
  Math.max((Number(selectedPathCount.value) || selectedPaths.value.length || 0) - 1, 0),
)

const isFallbackIncorporation = computed(
  () => normalizeKey(autoAttributionType.value) === 'fallback_incorporation',
)

const lookThroughApplied = computed(() =>
  Boolean(props.autoCountryAttribution?.look_through_applied || promotionReason.value),
)

const controlPathModeLabel = computed(() => {
  const normalizedType = normalizeKey(controlTypeValue.value)
  if (promotionReason.value || lookThroughApplied.value) {
    return '上卷识别'
  }
  if (normalizedType.includes('mixed')) {
    return 'mixed control 识别'
  }
  if (normalizedType.includes('vie')) {
    return 'VIE 识别'
  }
  if (normalizedType.includes('board')) {
    return 'board control 识别'
  }
  if (normalizedType.includes('voting')) {
    return 'voting right 识别'
  }
  if (normalizedType.includes('agreement')) {
    return '协议控制识别'
  }
  return '直接识别'
})

const controlTypeText = computed(() =>
  firstNonEmpty(
    controlTypeLabel(controlTypeValue.value),
    controlTypeValue.value,
  ) || NO_DATA_TEXT,
)

const failureReasonText = computed(() =>
  reasonLabel(terminalFailureReason.value, TERMINAL_FAILURE_REASON_LABELS) || '',
)

const countryInferenceReasonText = computed(() =>
  reasonLabel(countryInferenceReason.value, COUNTRY_INFERENCE_REASON_LABELS) || '',
)

const coreEvidenceText = computed(() => {
  if (promotionReason.value) {
    return reasonLabel(promotionReason.value, PROMOTION_REASON_LABELS)
  }
  const normalizedType = normalizeKey(controlTypeValue.value)
  if (normalizedType.includes('equity')) {
    return '股权路径满足控制阈值。'
  }
  if (normalizedType.includes('mixed')) {
    return '结合股权与治理线索识别实际控制人。'
  }
  if (
    normalizedType.includes('agreement') ||
    normalizedType.includes('vie') ||
    normalizedType.includes('board') ||
    normalizedType.includes('voting')
  ) {
    return '结合治理/协议线索识别实际控制人。'
  }
  if (ownershipPatternSignal.value) {
    return '检测到公众持股/分散持股聚合表达，相关主体仅保留为结构信号。'
  }
  return '当前控制线索支持该自动结论。'
})

const summaryItems = computed(() => {
  const lines = []

  if (hasAutoActualController.value) {
    lines.push(`判定路径：${controlPathModeLabel.value}`)
    lines.push(`主要控制方式：${controlTypeText.value}`)
    lines.push(`是否发生上卷：${lookThroughApplied.value ? '是' : '否'}`)
    lines.push(`核心依据：${coreEvidenceText.value}`)
    if (ownershipPatternSignal.value) {
      lines.push('检测到公众持股/分散持股聚合表达，但仅保留为结构信号。')
    }
    return lines.slice(0, 5)
  }

  lines.push('当前未识别唯一实际控制人')
  if (failureReasonText.value) {
    lines.push(`主要原因：${failureReasonText.value}`)
  }
  if (isFallbackIncorporation.value) {
    lines.push('当前按注册地回退')
  } else if (countryInferenceReasonText.value) {
    lines.push(`归属说明：${countryInferenceReasonText.value}`)
  }
  if (ownershipPatternSignal.value) {
    lines.push('检测到公众持股/分散持股聚合表达')
    lines.push('该主体保留为结构信号，不参与实际控制人认定')
  } else if (coreEvidenceText.value) {
    lines.push(`解释摘要：${coreEvidenceText.value}`)
  }
  return lines.slice(0, 5)
})

function candidateRole(candidate) {
  if (candidate.isActualController) {
    return 'actual'
  }
  if (candidate.isLeadingCandidate) {
    return 'leading'
  }
  if (
    candidate.ownershipPatternSignal ||
    normalizeKey(candidate.terminalIdentifiability) === 'aggregation_like' ||
    normalizeKey(candidate.terminalSuitability) === 'pattern_only'
  ) {
    return 'aggregation signal'
  }
  if (!candidateInActualRace(candidate)) {
    return 'blocked'
  }
  return 'candidate'
}

function candidateInActualRace(candidate) {
  const suitability = normalizeKey(candidate.terminalSuitability)
  const identifiability = normalizeKey(candidate.terminalIdentifiability)
  const selectionReason = normalizeKey(candidate.selectionReason)
  return !(
    candidate.ownershipPatternSignal ||
    suitability === 'blocked_terminal' ||
    suitability === 'pattern_only' ||
    identifiability === 'aggregation_like' ||
    selectionReason.includes('excluded_from_actual_race')
  )
}

function candidateStrengthText(candidate) {
  const ratio = formatPercent(candidate.controlRatio)
  if (ratio) {
    return ratio
  }
  const terminalScore = formatPercent(candidate.terminalControlScore)
  if (terminalScore) {
    return `终局得分 ${terminalScore}`
  }
  const aggregated = formatPercent(candidate.aggregatedControlScore)
  if (aggregated) {
    return `聚合得分 ${aggregated}`
  }
  return NO_DATA_TEXT
}

const topCandidates = computed(() => autoCandidates.value.slice(0, 3))

const terminalProfileTags = computed(() => {
  const tags = []
  const identifiability = normalizeKey(terminalIdentifiability.value)
  const suitability = normalizeKey(terminalSuitability.value)

  if (identifiability && TERMINAL_IDENTIFIABILITY_LABELS[identifiability]) {
    tags.push(TERMINAL_IDENTIFIABILITY_LABELS[identifiability])
  }
  if (ownershipPatternSignal.value) {
    tags.push('结构信号主体')
  }
  if (['blocked_terminal', 'pattern_only'].includes(suitability)) {
    tags.push('不适合作为终局主体')
  }
  if (
    identifiability === 'unknown_or_blocked' ||
    terminalProfileReasons.value.some((reason) =>
      normalizeKey(reason).includes('excluded_from_actual_race'),
    )
  ) {
    tags.push('已排除出 actual race')
  }
  return uniqueStrings(tags)
})

const terminalProfileRows = computed(() => {
  const rows = []
  const identifiabilityText = reasonLabel(
    terminalIdentifiability.value,
    TERMINAL_IDENTIFIABILITY_LABELS,
  )
  const suitabilityText = reasonLabel(
    terminalSuitability.value,
    TERMINAL_SUITABILITY_LABELS,
  )
  const profileReasonText = terminalProfileReasons.value
    .map((reason) => reasonLabel(reason, TERMINAL_PROFILE_REASON_LABELS))
    .filter(Boolean)
    .join('；')

  if (identifiabilityText) {
    rows.push({
      label: '终局可识别性',
      value: identifiabilityText,
    })
  }
  if (suitabilityText) {
    rows.push({
      label: '终局适格性',
      value: suitabilityText,
    })
  }
  if (ownershipPatternSignal.value) {
    rows.push({
      label: '结构信号',
      value: '结构信号主体',
    })
  }
  if (profileReasonText) {
    rows.push({
      label: '画像依据',
      value: profileReasonText,
    })
  }
  return rows
})

const failureLogicRows = computed(() => {
  const rows = []
  if (!hasAutoActualController.value && failureReasonText.value) {
    rows.push({
      label: '失败原因',
      value: failureReasonText.value,
    })
  }
  if (!hasAutoActualController.value && countryInferenceReasonText.value) {
    rows.push({
      label: '归属推断',
      value: countryInferenceReasonText.value,
    })
  }
  if (!hasAutoActualController.value && isFallbackIncorporation.value) {
    rows.push({
      label: 'Fallback 说明',
      value: '已按注册地进行归属回退。',
    })
  }
  return rows
})

const pathLogicRows = computed(() => {
  const rows = []
  if (primaryPathText.value) {
    rows.push({
      label: '自动路径摘要',
      value: primaryPathText.value,
    })
  }
  if (selectedPathCount.value) {
    rows.push({
      label: '路径数量',
      value: `${selectedPathCount.value} 条`,
    })
  }
  if (selectedPathDepth.value !== null && selectedPathDepth.value !== undefined && selectedPathDepth.value !== '') {
    rows.push({
      label: '路径深度',
      value: `${selectedPathDepth.value}`,
    })
  }
  if (supplementalPathCount.value > 0) {
    rows.push({
      label: '补充路径',
      value: `主路径之外另有 ${supplementalPathCount.value} 条补充路径。`,
    })
  }
  return rows
})

const showDetailedLogic = computed(
  () =>
    topCandidates.value.length > 0 ||
    terminalProfileRows.value.length > 0 ||
    failureLogicRows.value.length > 0 ||
    pathLogicRows.value.length > 0,
)

const currentResultSource = computed(() =>
  normalizeKey(
    firstNonEmpty(
      props.currentControlAnalysis?.result_source,
      props.currentCountryAttribution?.result_source,
      props.manualOverride?.source_type,
    ) || 'automatic',
  ),
)

const effectiveSourceLabel = computed(() => {
  if (currentResultSource.value === 'manual_override') {
    return '人工征订'
  }
  if (currentResultSource.value === 'manual_judgment') {
    return '人工判定'
  }
  return '自动分析'
})

const currentEffectiveControllerName = computed(() =>
  firstNonEmpty(
    controllerName(props.currentControlAnalysis?.actual_controller, ''),
    props.manualOverride?.actual_controller_name,
  ) || NO_UNIQUE_CONTROLLER_TEXT,
)

const currentEffectiveCountry = computed(() =>
  firstNonEmpty(
    props.currentCountryAttribution?.actual_control_country,
    props.manualOverride?.actual_control_country,
  ) || NO_DATA_TEXT,
)

const manualResultExists = computed(
  () => Boolean(props.manualOverride) || currentResultSource.value.startsWith('manual'),
)

const autoMatchesCurrent = computed(() => {
  const sameController =
    normalizeKey(autoActualControllerName.value) === normalizeKey(currentEffectiveControllerName.value)
  const sameCountry =
    normalizeKey(autoActualControlCountry.value) === normalizeKey(currentEffectiveCountry.value)
  return sameController && sameCountry
})

const comparisonStatusText = computed(() => {
  if (currentResultSource.value === 'manual_override') {
    return autoMatchesCurrent.value ? '自动结果与当前生效结果一致' : '已被人工征订覆盖'
  }
  if (currentResultSource.value === 'manual_judgment') {
    return autoMatchesCurrent.value ? '自动结果与当前生效结果一致' : '已被人工判定覆盖'
  }
  if (currentResultSource.value === 'manual_confirmed') {
    return '自动结果已确认'
  }
  return autoMatchesCurrent.value ? '自动结果与当前生效结果一致' : '自动分析'
})

const comparisonReferenceNote = computed(() =>
  ['manual_override', 'manual_judgment'].includes(currentResultSource.value)
    ? '自动分析结果仍保留作参考。'
    : '',
)

const showManualComparison = computed(() => manualResultExists.value)

const overviewStatusLabel = computed(() =>
  hasAutoActualController.value ? '已识别唯一实际控制人' : NO_UNIQUE_CONTROLLER_TEXT,
)
</script>

<template>
  <div class="auto-analysis-explain-panel">
    <section class="auto-analysis-explain-panel__section">
      <div class="auto-analysis-explain-panel__header">
        <div>
          <h3>自动分析结果</h3>
          <p>自动结果始终保留展示，用于和当前生效结果进行对照。</p>
        </div>
        <span
          class="auto-analysis-explain-panel__status"
          :class="{
            'auto-analysis-explain-panel__status--muted': !hasAutoActualController,
          }"
        >
          {{ overviewStatusLabel }}
        </span>
      </div>

      <dl class="explain-facts">
        <div>
          <dt>自动 actual controller</dt>
          <dd>{{ autoActualControllerName }}</dd>
        </div>
        <div>
          <dt>自动 actual control country</dt>
          <dd>{{ autoActualControlCountry }}</dd>
        </div>
        <div>
          <dt>自动 attribution type</dt>
          <dd>{{ autoAttributionType }}</dd>
        </div>
      </dl>
    </section>

    <section class="auto-analysis-explain-panel__section">
      <div class="auto-analysis-explain-panel__section-title">分析摘要</div>
      <ul class="summary-list">
        <li v-for="(item, index) in summaryItems" :key="`summary-${index}`">
          {{ item }}
        </li>
      </ul>
    </section>

    <el-collapse v-if="showDetailedLogic" class="logic-collapse">
      <el-collapse-item name="logic">
        <template #title>
          <span class="logic-collapse__title">详细分析逻辑</span>
        </template>

        <div class="logic-blocks">
          <section v-if="topCandidates.length" class="logic-block">
            <div class="logic-block__title">候选主体</div>
            <div class="candidate-list">
              <article
                v-for="candidate in topCandidates"
                :key="candidate.key"
                class="candidate-card"
              >
                <div class="candidate-card__head">
                  <strong>{{ candidate.name || NO_DATA_TEXT }}</strong>
                  <span
                    class="candidate-role"
                    :class="`candidate-role--${candidateRole(candidate).replace(/\s+/g, '-')}`"
                  >
                    {{ candidateRole(candidate) }}
                  </span>
                </div>
                <dl class="detail-facts">
                  <div>
                    <dt>控制强度 / 比例</dt>
                    <dd>{{ candidateStrengthText(candidate) }}</dd>
                  </div>
                  <div>
                    <dt>当前角色</dt>
                    <dd>{{ candidateRole(candidate) }}</dd>
                  </div>
                  <div>
                    <dt>进入 actual race</dt>
                    <dd>{{ candidateInActualRace(candidate) ? '是' : '否' }}</dd>
                  </div>
                </dl>
              </article>
            </div>
          </section>

          <section v-if="terminalProfileRows.length" class="logic-block">
            <div class="logic-block__title">终局画像</div>
            <div v-if="terminalProfileTags.length" class="profile-tags">
              <span
                v-for="tag in terminalProfileTags"
                :key="tag"
                class="profile-tag"
              >
                {{ tag }}
              </span>
            </div>
            <dl class="detail-facts">
              <div v-for="row in terminalProfileRows" :key="row.label">
                <dt>{{ row.label }}</dt>
                <dd>{{ row.value }}</dd>
              </div>
            </dl>
          </section>

          <section v-if="failureLogicRows.length" class="logic-block">
            <div class="logic-block__title">失败原因 / fallback 逻辑</div>
            <dl class="detail-facts">
              <div v-for="row in failureLogicRows" :key="row.label">
                <dt>{{ row.label }}</dt>
                <dd>{{ row.value }}</dd>
              </div>
            </dl>
          </section>

          <section v-if="pathLogicRows.length" class="logic-block">
            <div class="logic-block__title">自动控制路径摘要</div>
            <dl class="detail-facts">
              <div v-for="row in pathLogicRows" :key="row.label">
                <dt>{{ row.label }}</dt>
                <dd>{{ row.value }}</dd>
              </div>
            </dl>
          </section>
        </div>
      </el-collapse-item>
    </el-collapse>

    <section
      v-if="showManualComparison"
      class="auto-analysis-explain-panel__section auto-analysis-explain-panel__section--contrast"
    >
      <div class="auto-analysis-explain-panel__section-title">人工结果对比</div>

      <dl class="explain-facts">
        <div>
          <dt>当前生效结果来源</dt>
          <dd>{{ effectiveSourceLabel }}</dd>
        </div>
        <div>
          <dt>当前生效实际控制人</dt>
          <dd>{{ currentEffectiveControllerName }}</dd>
        </div>
        <div>
          <dt>自动分析实际控制人</dt>
          <dd>{{ autoActualControllerName }}</dd>
        </div>
        <div>
          <dt>当前生效控制国家</dt>
          <dd>{{ currentEffectiveCountry }}</dd>
        </div>
        <div>
          <dt>自动分析控制国家</dt>
          <dd>{{ autoActualControlCountry }}</dd>
        </div>
      </dl>

      <div class="comparison-status">
        {{ comparisonStatusText }}
      </div>
      <p v-if="comparisonReferenceNote" class="comparison-note">
        {{ comparisonReferenceNote }}
      </p>
    </section>
  </div>
</template>

<style scoped>
.auto-analysis-explain-panel {
  display: grid;
  gap: 14px;
}

.auto-analysis-explain-panel__section {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  border-radius: 10px;
  background: rgba(248, 251, 253, 0.82);
}

.auto-analysis-explain-panel__section--contrast {
  background: linear-gradient(180deg, rgba(255, 250, 244, 0.9), rgba(248, 251, 253, 0.88));
  border-color: rgba(139, 106, 61, 0.18);
}

.auto-analysis-explain-panel__header {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
}

.auto-analysis-explain-panel__header h3,
.auto-analysis-explain-panel__section-title,
.logic-block__title {
  margin: 0;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.auto-analysis-explain-panel__header p {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.55;
}

.auto-analysis-explain-panel__status {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(48, 95, 131, 0.16);
  color: #305f83;
  background: rgba(48, 95, 131, 0.08);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.auto-analysis-explain-panel__status--muted {
  color: #8a5a11;
  border-color: rgba(138, 90, 17, 0.18);
  background: rgba(138, 90, 17, 0.08);
}

.explain-facts,
.detail-facts {
  display: grid;
  gap: 10px;
  margin: 0;
}

.explain-facts > div,
.detail-facts > div {
  display: grid;
  grid-template-columns: 152px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.explain-facts dt,
.detail-facts dt {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
}

.explain-facts dd,
.detail-facts dd {
  margin: 0;
  color: var(--brand-ink);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.summary-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding-left: 18px;
  color: #304356;
}

.summary-list li {
  line-height: 1.6;
}

.logic-collapse {
  border-radius: 10px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  background: rgba(255, 255, 255, 0.78);
}

.logic-collapse :deep(.el-collapse-item__header) {
  padding: 0 14px;
  color: var(--brand-ink);
  font-weight: 700;
  background: transparent;
}

.logic-collapse :deep(.el-collapse-item__wrap) {
  border-top: 1px solid rgba(31, 59, 87, 0.08);
  background: transparent;
}

.logic-collapse :deep(.el-collapse-item__content) {
  padding: 12px 14px 14px;
}

.logic-collapse__title {
  font-weight: 700;
}

.logic-blocks {
  display: grid;
  gap: 14px;
}

.logic-block {
  display: grid;
  gap: 10px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(248, 251, 253, 0.66);
}

.candidate-list {
  display: grid;
  gap: 10px;
}

.candidate-card {
  display: grid;
  gap: 10px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid rgba(48, 95, 131, 0.14);
  background: rgba(255, 255, 255, 0.86);
}

.candidate-card__head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  justify-content: space-between;
}

.candidate-card__head strong {
  color: var(--brand-ink);
  font-size: 14px;
  line-height: 1.5;
}

.candidate-role,
.profile-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  min-height: 24px;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
}

.candidate-role--actual {
  color: #a33e3e;
  border-color: rgba(163, 62, 62, 0.2);
  background: rgba(163, 62, 62, 0.12);
}

.candidate-role--leading {
  color: #5b50ad;
  border-color: rgba(91, 80, 173, 0.2);
  background: rgba(91, 80, 173, 0.1);
}

.candidate-role--candidate {
  color: #305f83;
  border-color: rgba(48, 95, 131, 0.18);
  background: rgba(48, 95, 131, 0.08);
}

.candidate-role--aggregation-signal,
.profile-tag {
  color: #486071;
  border-color: rgba(72, 96, 113, 0.2);
  background: rgba(72, 96, 113, 0.1);
}

.candidate-role--blocked {
  color: #8a5a11;
  border-color: rgba(138, 90, 17, 0.2);
  background: rgba(138, 90, 17, 0.1);
}

.profile-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.comparison-status {
  color: #8a4b12;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.5;
}

.comparison-note {
  margin: -4px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.55;
}

@media (max-width: 640px) {
  .auto-analysis-explain-panel__header,
  .candidate-card__head {
    display: grid;
  }

  .explain-facts > div,
  .detail-facts > div {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>
