<script setup>
import { computed, reactive, watch } from 'vue'

const props = defineProps({
  relationships: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
})

const EMPTY_TEXT = '—'
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

const ENTITY_TYPE_LABELS = {
  company: '公司主体',
  person: '自然人',
  fund: '基金 / 公众持股',
  government: '政府 / 国资主体',
  other: '其他主体',
}

const CONTROL_TYPE_LABELS = {
  equity: '股权控制',
  equity_control: '股权控制',
  direct_equity_control: '股权控制',
  indirect_equity_control: '股权控制',
  significant_influence: '重大影响',
  agreement: '协议控制',
  agreement_control: '协议控制',
  board_control: '董事会/席位控制',
  voting_right: '表决权安排',
  voting_right_control: '表决权安排',
  nominee: '代持/名义持有人',
  nominee_control: '代持/名义持有人',
  vie: 'VIE结构',
  vie_control: 'VIE结构',
  mixed_control: '混合控制',
  joint_control: '共同控制',
  unknown: EMPTY_TEXT,
  null: EMPTY_TEXT,
}

const BASIS_MODE_LABELS = {
  numeric: '数值计算',
  semantic: '语义规则',
  mixed: '综合判断',
  sum_cap: '路径汇总',
}

const BASIS_TEXT_LABELS = {
  auto: '自动生成',
  'legacy auto': '历史自动结果',
  'manual control': '人工认定',
  ownership_penetration: '股权穿透分析',
  unified_control_inference_v1: '统一控制推断',
  unified_control_inference_v2: '统一控制推断',
}

const CONTROL_TIER_LABELS = {
  direct: '直接控制层',
  intermediate: '中间控制层',
  ultimate: '最终控制层',
  candidate: '候选控制层',
}

const PROMOTION_REASON_LABELS = {
  beneficial_owner_priority: '受益控制人线索优先，结论继续上卷至上层主体。',
  controls_direct_controller: '上层主体控制直接控制人，最终归属继续上卷。',
  direct_controller_look_through: '直接控制层具备中间平台特征，继续向上穿透。',
  holding_vehicle_look_through: '直接控制人为控股平台或 SPV，最终归属继续上卷。',
  intermediate_holding_look_through: '中间控股平台已被穿透，按上层主体形成最终判断。',
  upstream_controller_priority: '上层主体具备更强最终控制信号，优先作为实际控制人。',
  ultimate_owner_hint: '存在最终控制人披露线索，按上层主体进行认定。',
}

const TERMINAL_FAILURE_REASON_LABELS = {
  joint_control: '存在共同控制，暂未形成唯一实际控制人。',
  beneficial_owner_unknown: '受益所有人未充分披露，暂未确认唯一实际控制人。',
  nominee_without_disclosure: '存在名义持有人或代持结构，但缺少可穿透披露。',
  low_confidence_evidence_weak: '证据强度不足，暂未形成唯一实际控制人。',
  close_competition: '多个候选主体控制信号接近，当前仅保留领先候选。',
  look_through_not_allowed: '上层穿透受到限制，结论保留在当前层级。',
  protective_right_only: '仅发现保护性权利，尚不足以构成实际控制。',
  no_control_relationships: '缺少可用于判定的控制关系数据。',
  no_candidate: '未发现达到控制判定条件的候选主体。',
}

const SELECTION_REASON_LABELS = {
  actual_controller_strict_control_threshold_met: '控制强度达到实际控制人判定条件。',
  leading_candidate: '当前为控制信号最强的候选主体。',
  leading_candidate_weak_evidence: '控制比例较高，但证据强度不足以确认唯一实际控制人。',
  leading_candidate_relative_control_signal: '相对控制信号较强，暂作为领先候选保留。',
  leading_candidate_close_competition: '候选主体之间差距较小，暂未形成唯一实际控制人。',
}

const expandedPathRows = reactive({})

watch(
  () => props.relationships,
  () => {
    Object.keys(expandedPathRows).forEach((key) => {
      delete expandedPathRows[key]
    })
  },
  { deep: false },
)

const sortedRelationships = computed(() =>
  [...props.relationships]
    .map((relationship, index) => ({
      ...relationship,
      _tableKey: buildRelationshipKey(relationship, index),
      _sourceIndex: index,
    }))
    .sort((left, right) => {
      const actualPriority = Number(isActualRow(right)) - Number(isActualRow(left))
      if (actualPriority !== 0) {
        return actualPriority
      }

      const ratioPriority = sortRatioValue(right.control_ratio) - sortRatioValue(left.control_ratio)
      if (ratioPriority !== 0) {
        return ratioPriority
      }

      return left._sourceIndex - right._sourceIndex
    }),
)

const actualControllerName = computed(() => {
  const actual = props.relationships.find((relationship) => isActualRow(relationship))
  return actual?.controller_name || ''
})

const highestDirectControllerRatio = computed(() => {
  const ratios = props.relationships
    .filter((relationship) => isDirectRow(relationship))
    .map((relationship) => toPercentNumber(relationship.control_ratio))
    .filter((ratio) => ratio !== null)

  return ratios.length ? Math.max(...ratios) : null
})

function buildRelationshipKey(relationship, index) {
  return [
    relationship?.id,
    relationship?.controller_entity_id,
    relationship?.controller_name,
    index,
  ]
    .filter((item) => item !== null && item !== undefined && item !== '')
    .join('-')
}

function normalizeKey(value) {
  return String(value ?? '').trim().toLowerCase()
}

function tryParseJson(value) {
  if (typeof value !== 'string') {
    return value
  }

  const trimmed = value.trim()
  if (!trimmed || !['{', '['].includes(trimmed[0])) {
    return value
  }

  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function toPercentNumber(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return null
  }

  return numeric <= 1 ? numeric * 100 : numeric
}

function sortRatioValue(value) {
  return toPercentNumber(value) ?? -1
}

function formatRatio(value) {
  const numeric = toPercentNumber(value)
  return numeric === null ? EMPTY_TEXT : `${numeric.toFixed(2)}%`
}

function controllerTypeLabel(value) {
  const normalized = normalizeKey(value)
  return ENTITY_TYPE_LABELS[normalized] || ENTITY_TYPE_LABELS.other
}

function controlTypeLabel(value) {
  const normalized = normalizeKey(value)
  if (!normalized || normalized === 'unknown' || normalized === 'null') {
    return EMPTY_TEXT
  }
  return CONTROL_TYPE_LABELS[normalized] || '未识别类型'
}

function basisModeLabel(value) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return ''
  }
  return BASIS_MODE_LABELS[normalized] || BASIS_TEXT_LABELS[normalized] || String(value).trim()
}

function basisTextLabel(value) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return ''
  }
  return BASIS_TEXT_LABELS[normalized] || String(value).trim()
}

function parsedBasis(row) {
  const parsed = tryParseJson(row?.basis)
  return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
}

function firstAvailable(row, key) {
  const basis = parsedBasis(row)
  return row?.[key] ?? basis?.[key]
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

function boolField(row, key) {
  const basis = parsedBasis(row)
  return isTruthy(row?.[key]) || isTruthy(basis?.[key])
}

function isDirectRow(row) {
  return boolField(row, 'is_direct_controller') || normalizeKey(firstAvailable(row, 'control_tier')) === 'direct'
}

function isIntermediateRow(row) {
  return (
    boolField(row, 'is_intermediate_controller') ||
    normalizeKey(firstAvailable(row, 'control_tier')) === 'intermediate'
  )
}

function isUltimateRow(row) {
  return boolField(row, 'is_ultimate_controller') || normalizeKey(firstAvailable(row, 'control_tier')) === 'ultimate'
}

function isActualRow(row) {
  return (
    boolField(row, 'is_actual_controller') ||
    isUltimateRow(row) ||
    normalizeKey(firstAvailable(row, 'controller_status')) === 'actual_controller'
  )
}

function isLeadingRow(row) {
  const status = normalizeKey(firstAvailable(row, 'controller_status'))
  return (
    boolField(row, 'is_leading_candidate') ||
    status === 'leading_candidate' ||
    status === 'no_actual_controller_but_leading_candidate_found'
  )
}

function controlTierLabel(row) {
  const tier = normalizeKey(firstAvailable(row, 'control_tier'))
  return CONTROL_TIER_LABELS[tier] || ''
}

function promotionReasonText(row) {
  const reason = firstAvailable(row, 'promotion_reason')
  const normalized = normalizeKey(reason)
  if (!normalized) {
    return ''
  }
  return PROMOTION_REASON_LABELS[normalized] || '已根据上层控制线索继续上卷认定。'
}

function terminalFailureText(row) {
  const reason = firstAvailable(row, 'terminal_failure_reason')
  const normalized = normalizeKey(reason)
  if (!normalized) {
    return ''
  }
  return TERMINAL_FAILURE_REASON_LABELS[normalized] || '当前存在会阻断唯一实际控制人认定的因素。'
}

function selectionReasonText(row) {
  const reason = firstAvailable(row, 'selection_reason')
  const normalized = normalizeKey(reason)
  if (!normalized) {
    return ''
  }
  return SELECTION_REASON_LABELS[normalized] || '当前主体保留为控制判断候选。'
}

function hasPromotionSignal(row) {
  const basis = parsedBasis(row)
  const depth = Number(firstAvailable(row, 'control_chain_depth') ?? 0)
  const promotionPath = Array.isArray(basis.promotion_path_entity_ids)
    ? basis.promotion_path_entity_ids
    : []

  return Boolean(firstAvailable(row, 'promotion_reason')) || depth > 1 || promotionPath.length > 1
}

function formatScore(value) {
  return formatRatio(value)
}

function getControlPaths(controlPath) {
  const parsed = tryParseJson(controlPath)
  return Array.isArray(parsed) ? parsed : []
}

function buildPathText(path) {
  if (!path) {
    return ''
  }

  const nameList = Array.isArray(path.path_entity_names) ? path.path_entity_names.filter(Boolean) : []
  if (nameList.length) {
    return nameList.join(' → ')
  }

  const idList = Array.isArray(path.path_entity_ids) ? path.path_entity_ids.filter(Boolean) : []
  if (idList.length) {
    return idList.map((id) => `主体 ${id}`).join(' → ')
  }

  return ''
}

function pathScoreText(path) {
  return formatRatio(path?.path_score_pct ?? path?.path_score)
}

function pathEntityIds(path) {
  return Array.isArray(path?.path_entity_ids) ? path.path_entity_ids.map((id) => String(id)) : []
}

function pathKind(row, path) {
  const ids = pathEntityIds(path)
  const controllerId = String(row?.controller_entity_id ?? '')
  if (ids.length >= 2 && controllerId && ids[0] === controllerId) {
    return ids.length === 2 ? 'direct' : 'indirect'
  }

  const names = Array.isArray(path?.path_entity_names) ? path.path_entity_names.filter(Boolean) : []
  return Math.max(ids.length, names.length) <= 2 ? 'direct' : 'indirect'
}

function pathKindLabel(kind) {
  return kind === 'direct' ? '直接路径' : '间接路径'
}

function pathSummary(row) {
  const paths = getControlPaths(row.control_path)
  const primaryPathText = paths.length ? buildPathText(paths[0]) : ''
  const pathKinds = paths.map((path) => pathKind(row, path))
  const directPathCount = pathKinds.filter((kind) => kind === 'direct').length
  const indirectPathCount = pathKinds.filter((kind) => kind === 'indirect').length

  return {
    paths,
    pathKinds,
    pathCount: paths.length,
    primaryPathText: primaryPathText || EMPTY_TEXT,
    primaryPathKind: pathKinds[0] || '',
    extraPathCount: Math.max(paths.length - 1, 0),
    hasMultiplePaths: paths.length > 1,
    directPathCount,
    indirectPathCount,
    hasDirectAndIndirect: directPathCount > 0 && indirectPathCount > 0,
  }
}

function togglePath(row) {
  expandedPathRows[row._tableKey] = !expandedPathRows[row._tableKey]
}

function isPathExpanded(row) {
  return Boolean(expandedPathRows[row._tableKey])
}

function semanticFlags(row) {
  const basis = parsedBasis(row)
  const candidates = [row?.semantic_flags, basis.semantic_flags]
  for (const candidate of candidates) {
    const parsed = tryParseJson(candidate)
    if (Array.isArray(parsed)) {
      return parsed.map((item) => normalizeKey(item)).filter(Boolean)
    }
  }
  return []
}

function collectEvidenceItems(row) {
  const basis = parsedBasis(row)
  const items = []
  const addEvidence = (value) => {
    if (Array.isArray(value)) {
      value.forEach(addEvidence)
      return
    }
    const text = String(value ?? '').trim()
    if (!text) {
      return
    }
    text
      .split(/[;|]/)
      .map((segment) => segment.trim())
      .filter(Boolean)
      .forEach((segment) => items.push(segment))
  }

  addEvidence(basis.evidence_summary)

  if (Array.isArray(basis.top_paths)) {
    basis.top_paths.forEach((path) => {
      if (!Array.isArray(path?.edges)) {
        return
      }
      path.edges.forEach((edge) => {
        addEvidence(edge?.evidence_summary)
        addEvidence(edge?.control_basis)
        addEvidence(edge?.remarks)
      })
    })
  }

  return items
}

function mapEvidenceItem(value) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return ''
  }
  if (normalized.includes('spv') || normalized.includes('holding company') || normalized.includes('holding platform')) {
    return '直接控制层具备控股平台 / SPV 特征。'
  }
  if (normalized.includes('beneficial') || normalized.includes('ultimate owner')) {
    return '存在受益控制人或最终控制人线索。'
  }
  if (normalized.includes('look through') || normalized.includes('upstream')) {
    return '上层控制链支持继续穿透判断。'
  }
  if (normalized.includes('appoint') || normalized.includes('board') || normalized.includes('director')) {
    return '包含董事会任命权或治理控制线索。'
  }
  if (normalized.includes('agreement') || normalized.includes('contract')) {
    return '包含股东协议或协议控制线索。'
  }
  if (normalized.includes('voting')) {
    return '包含表决权安排线索。'
  }
  if (normalized.includes('direct equity ownership') || normalized.includes('equity')) {
    return '存在股权控制路径支持。'
  }
  if (normalized.includes('public float') || normalized.includes('dispersed') || normalized.includes('free float')) {
    return '公众流通股 / 分散持股更适合作为候选信号。'
  }
  if (normalized.includes('low confidence')) {
    return '证据可信度不足，未直接形成终局控制结论。'
  }
  return ''
}

function evidenceSummaryText(row) {
  const mapped = collectEvidenceItems(row)
    .map((item) => mapEvidenceItem(item))
    .filter(Boolean)
  const flags = semanticFlags(row)

  if (!mapped.length) {
    if (flags.includes('board_control')) {
      mapped.push('包含董事会或治理控制线索。')
    }
    if (flags.includes('agreement')) {
      mapped.push('包含协议控制线索。')
    }
    if (flags.includes('vie')) {
      mapped.push('包含 VIE 或非股权控制结构。')
    }
    if (flags.includes('low_confidence')) {
      mapped.push('证据可信度不足，未直接形成终局控制结论。')
    }
  }

  return dedupeList(mapped).slice(0, 2).join(' ')
}

function controlModeNote(row) {
  const mode = normalizeKey(firstAvailable(row, 'control_mode'))
  const type = normalizeKey(row?.control_type)
  if (mode === 'semantic') {
    return '本行主要依据协议、治理或非股权控制线索，不只按持股比例判断。'
  }
  if (mode === 'mixed' || type === 'mixed_control') {
    return '本行综合股权比例与治理、协议等控制线索判断。'
  }
  if (['agreement', 'agreement_control', 'board_control', 'voting_right', 'voting_right_control', 'vie', 'vie_control'].includes(type)) {
    return '本行控制口径包含非股权控制因素，比例不是唯一判断依据。'
  }
  return ''
}

function multiPathConvergenceNote(row) {
  const summary = pathSummary(row)
  if (!summary.hasDirectAndIndirect) {
    return ''
  }

  return '该主体既直接参与控制，也通过中间主体形成补充控制路径，最终判断综合多条路径。'
}

function hasHigherDirectLayerRatio(row) {
  const currentRatio = toPercentNumber(row?.control_ratio)
  return (
    isActualRow(row) &&
    !isDirectRow(row) &&
    currentRatio !== null &&
    highestDirectControllerRatio.value !== null &&
    highestDirectControllerRatio.value > currentRatio + 0.01
  )
}

function immediateRatioNote(row) {
  const currentRatio = toPercentNumber(row?.control_ratio)
  const immediateRatio = toPercentNumber(row?.immediate_control_ratio)
  if (
    !isActualRow(row) ||
    isDirectRow(row) ||
    currentRatio === null ||
    immediateRatio === null ||
    Math.abs(currentRatio - immediateRatio) < 0.1
  ) {
    return ''
  }

  return `上层即时控制强度约 ${formatRatio(row.immediate_control_ratio)}，最终比例为路径折算结果。`
}

function dedupeList(items) {
  const seen = new Set()
  return items.filter((item) => {
    const normalized = normalizeKey(item)
    if (!normalized || seen.has(normalized)) {
      return false
    }
    seen.add(normalized)
    return true
  })
}

function relationshipRoleTags(row) {
  const tags = []
  if (isActualRow(row)) {
    tags.push({ label: '实际控制人', type: 'actual' })
  }
  if (isDirectRow(row)) {
    tags.push({ label: '直接控制人', type: 'direct' })
  }
  if (isIntermediateRow(row)) {
    tags.push({ label: '中间层', type: 'intermediate' })
  }
  if (isLeadingRow(row) && !isActualRow(row)) {
    tags.push({ label: '领先候选', type: 'leading' })
  }
  if (hasPromotionSignal(row) && isActualRow(row) && !isDirectRow(row)) {
    tags.push({ label: '上卷后认定', type: 'promotion' })
  }
  if (terminalFailureText(row) && !isActualRow(row)) {
    tags.push({ label: '边界结论', type: 'boundary' })
  }

  return tags.length ? tags : [{ label: '上游主体', type: 'neutral' }]
}

function roleNote(row) {
  const tier = controlTierLabel(row)
  if (tier) {
    return tier
  }
  if (getControlPaths(row.control_path).length) {
    return '控制路径主体'
  }
  return ''
}

function recognitionExplanation(row) {
  const details = []
  let headline = '候选控制主体'
  const promotionText = promotionReasonText(row)
  const terminalText = terminalFailureText(row)
  const evidenceText = evidenceSummaryText(row)
  const modeText = controlModeNote(row)
  const immediateText = immediateRatioNote(row)
  const convergenceText = multiPathConvergenceNote(row)

  if (isActualRow(row)) {
    if (isDirectRow(row)) {
      headline = '直接控制并认定为实际控制人'
      details.push('该主体位于直接控制层，且满足最终控制判定条件。')
    } else if (hasPromotionSignal(row)) {
      headline = '上卷后认定为实际控制人'
      details.push(promotionText || '直接控制层继续向上穿透，最终控制归属落在该上层主体。')
    } else {
      headline = '认定为实际控制人'
      details.push('后端已形成唯一实际控制人结论。')
    }

    if (hasHigherDirectLayerRatio(row)) {
      details.push('控制比例低于直接控制平台时，最终认定仍以穿透层级与上层控制能力为准。')
    }
    if (immediateText) {
      details.push(immediateText)
    }
  } else if (isDirectRow(row)) {
    headline = isIntermediateRow(row) ? '直接控制层 / 中间平台' : '直接控制人'
    details.push('该主体直接连接目标公司，用于识别第一层控制关系。')
    if (actualControllerName.value) {
      details.push(`最终归属继续上卷至 ${actualControllerName.value}。`)
    } else {
      details.push('若存在上层控制信号，最终归属可能继续向上穿透。')
    }
  } else if (isLeadingRow(row)) {
    headline = '领先候选主体'
    details.push(terminalText || selectionReasonText(row) || '存在较强控制信号，但暂未形成唯一实际控制人结论。')
  } else if (isIntermediateRow(row)) {
    headline = '中间控制层主体'
    details.push('该主体用于连接上下游控制链，帮助解释最终归属路径。')
  } else {
    details.push(selectionReasonText(row) || '作为上游控制关系记录保留，用于辅助解释整体控制链。')
  }

  if (promotionText && !isActualRow(row) && !details.includes(promotionText)) {
    details.push(promotionText)
  }
  if (terminalText && !isActualRow(row) && !details.includes(terminalText)) {
    details.push(terminalText)
  }
  if (modeText) {
    details.push(modeText)
  }
  if (convergenceText) {
    details.push(convergenceText)
  }
  if (evidenceText) {
    details.push(evidenceText)
  }

  return {
    headline,
    details: dedupeList(details).slice(0, 3),
  }
}

function basisLinesFromObject(row, basis) {
  const lines = []
  const inferredPathCount = getControlPaths(row.control_path).length
  const pathCount = basis.path_count ?? inferredPathCount

  if (basis.classification || row.control_type) {
    lines.push({
      label: '认定类型',
      value: controlTypeLabel(basis.classification || row.control_type),
    })
  }

  if (basis.control_mode || basis.aggregator) {
    lines.push({
      label: '依据方式',
      value: basisModeLabel(basis.control_mode || basis.aggregator),
    })
  }

  if (row.control_chain_depth || basis.control_chain_depth) {
    lines.push({
      label: '链路深度',
      value: `${row.control_chain_depth || basis.control_chain_depth}层`,
    })
  }

  if (basis.as_of) {
    lines.push({
      label: '分析日期',
      value: basis.as_of,
    })
  }

  if (pathCount) {
    lines.push({
      label: '路径数量',
      value: `${pathCount}条`,
    })
  }

  if (row.aggregated_control_score) {
    lines.push({
      label: '聚合得分',
      value: formatScore(row.aggregated_control_score),
    })
  }

  if (row.terminal_control_score) {
    lines.push({
      label: '终局得分',
      value: formatScore(row.terminal_control_score),
    })
  }

  if (!lines.length && basis.analysis) {
    lines.push({
      label: '依据说明',
      value: basisTextLabel(basis.analysis),
    })
  }

  return lines
}

function basisLinesFromString(value) {
  const trimmed = String(value ?? '').trim()
  if (!trimmed) {
    return []
  }

  const segments = trimmed.split('|').map((segment) => segment.trim()).filter(Boolean)
  if (segments.length <= 1) {
    return [
      {
        label: '依据说明',
        value: basisTextLabel(trimmed),
      },
    ]
  }

  return segments.map((segment) => {
    const normalized = normalizeKey(segment)

    if (CONTROL_TYPE_LABELS[normalized]) {
      return {
        label: '认定类型',
        value: controlTypeLabel(segment),
      }
    }

    if (BASIS_MODE_LABELS[normalized] || BASIS_TEXT_LABELS[normalized]) {
      return {
        label: '依据方式',
        value: basisModeLabel(segment),
      }
    }

    if (DATE_PATTERN.test(segment)) {
      return {
        label: '分析日期',
        value: segment,
      }
    }

    if (/^\d+\s*(条路径|paths?)$/i.test(segment)) {
      return {
        label: '路径数量',
        value: segment.replace(/\s*paths?$/i, '条').replace(/\s+/g, ''),
      }
    }

    return {
      label: '依据说明',
      value: basisTextLabel(segment),
    }
  })
}

function basisLines(row) {
  const parsed = tryParseJson(row.basis)

  if (!parsed) {
    return []
  }

  if (typeof parsed === 'object' && !Array.isArray(parsed)) {
    return basisLinesFromObject(row, parsed)
  }

  return basisLinesFromString(parsed)
}

function rowClassName({ row }) {
  return isActualRow(row) ? 'control-relations-table__row--actual' : ''
}
</script>

<template>
  <el-card class="surface-card" shadow="never">
    <template #header>
      <div class="section-heading">
        <div>
          <h2>控制结论明细表</h2>
          <p>展示主要控制主体、控制方式、控制路径摘要与认定依据，便于结合上方控制结构图进行讲解。</p>
        </div>
      </div>
    </template>

    <el-table
      v-loading="loading"
      :data="sortedRelationships"
      :row-key="(row) => row._tableKey"
      :row-class-name="rowClassName"
      class="control-relations-table"
      stripe
      border
      empty-text="暂无控制结论数据"
    >
      <el-table-column type="index" label="序号" width="72" align="center" />

      <el-table-column label="控制主体" min-width="300">
        <template #default="{ row }">
          <div class="controller-name-cell">
            <div class="controller-name">
              {{ row.controller_name || EMPTY_TEXT }}
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="主体类型" min-width="128" align="center" header-align="center">
        <template #default="{ row }">
          <span class="meta-chip meta-chip--entity">
            {{ controllerTypeLabel(row.controller_type) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="控制类型" min-width="128" align="center" header-align="center">
        <template #default="{ row }">
          <span class="meta-chip meta-chip--control">
            {{ controlTypeLabel(row.control_type) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="控制层级/角色" min-width="170">
        <template #default="{ row }">
          <div class="role-stack">
            <div class="role-tag-list">
              <span
                v-for="tag in relationshipRoleTags(row)"
                :key="`${row._tableKey}-role-${tag.label}`"
                :class="[
                  'relationship-role-badge',
                  `relationship-role-badge--${tag.type}`,
                ]"
              >
                {{ tag.label }}
              </span>
            </div>
            <div v-if="roleNote(row)" class="role-note">
              {{ roleNote(row) }}
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="控制比例" min-width="110" align="center" header-align="center">
        <template #default="{ row }">
          <span class="ratio-text">
            {{ formatRatio(row.control_ratio) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="控制路径" min-width="400">
        <template #default="{ row }">
          <div class="control-path-cell">
            <template v-if="pathSummary(row).pathCount">
              <div class="table-text table-multi-line path-summary">
                <div v-if="pathSummary(row).hasDirectAndIndirect" class="path-structure-note">
                  路径结构：直接 + 间接多路径汇聚；图中突出主路径，其余作为补充路径。
                </div>
                <template v-if="pathSummary(row).hasMultiplePaths">
                  <div class="path-primary">
                    主路径（{{ pathKindLabel(pathSummary(row).primaryPathKind) }}）：{{ pathSummary(row).primaryPathText }}
                  </div>
                  <div class="path-secondary">另有 {{ pathSummary(row).extraPathCount }} 条补充路径</div>
                </template>
                <template v-else>
                  <div class="path-primary">{{ pathSummary(row).primaryPathText }}</div>
                </template>
              </div>

              <el-button
                v-if="pathSummary(row).hasMultiplePaths"
                class="path-toggle"
                link
                type="primary"
                @click.stop="togglePath(row)"
              >
                {{ isPathExpanded(row) ? '收起路径' : `展开全部（共 ${pathSummary(row).pathCount} 条）` }}
              </el-button>

              <div v-if="isPathExpanded(row)" class="path-list">
                <div
                  v-for="(path, pathIndex) in pathSummary(row).paths"
                  :key="`${row._tableKey}-path-${pathIndex}`"
                  class="path-list-item"
                >
                  <div class="path-list-head">
                    <span class="path-index">
                      路径 {{ pathIndex + 1 }} · {{ pathKindLabel(pathKind(row, path)) }}
                    </span>
                    <span v-if="pathScoreText(path) !== EMPTY_TEXT" class="path-score">
                      约 {{ pathScoreText(path) }}
                    </span>
                  </div>
                  <div class="table-text table-multi-line path-detail">
                    {{ buildPathText(path) || EMPTY_TEXT }}
                  </div>
                </div>
              </div>
            </template>

            <span v-else class="table-text table-text--muted">{{ EMPTY_TEXT }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="认定说明" min-width="330">
        <template #default="{ row }">
          <div class="recognition-cell">
            <div class="recognition-headline">
              {{ recognitionExplanation(row).headline }}
            </div>
            <div
              v-for="(detail, detailIndex) in recognitionExplanation(row).details"
              :key="`${row._tableKey}-recognition-${detailIndex}`"
              class="recognition-detail"
            >
              {{ detail }}
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="实际控制人" min-width="118" align="center" header-align="center">
        <template #default="{ row }">
          <span
            class="actual-badge"
            :class="isActualRow(row) ? 'actual-badge--yes' : 'actual-badge--no'"
          >
            {{ isActualRow(row) ? '是' : '否' }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="元数据" min-width="240">
        <template #default="{ row }">
          <div v-if="basisLines(row).length" class="basis-list">
            <div
              v-for="(item, itemIndex) in basisLines(row)"
              :key="`${row._tableKey}-basis-${itemIndex}`"
              class="basis-item"
            >
              <span class="basis-label">{{ item.label }}</span>
              <span class="table-text table-multi-line basis-value">{{ item.value }}</span>
            </div>
          </div>
          <span v-else class="table-text table-text--muted">{{ EMPTY_TEXT }}</span>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.control-relations-table :deep(.el-table__cell) {
  vertical-align: top;
}

.control-relations-table :deep(.cell) {
  line-height: 1.68;
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
}

.control-relations-table :deep(.el-table__row > td) {
  transition: background-color 0.18s ease;
}

.control-relations-table :deep(.el-table__row:hover > td) {
  background: rgba(31, 59, 87, 0.04) !important;
}

.control-relations-table :deep(.control-relations-table__row--actual > td) {
  background: rgba(168, 73, 73, 0.055);
}

.control-relations-table :deep(.control-relations-table__row--actual:hover > td) {
  background: rgba(168, 73, 73, 0.085) !important;
}

.controller-name {
  color: var(--brand-ink);
  font-weight: 600;
  line-height: 1.45;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.controller-name-cell {
  display: grid;
  gap: 6px;
}

.role-stack {
  display: grid;
  gap: 6px;
}

.role-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.relationship-role-badge {
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
}

.relationship-role-badge--actual {
  color: #a33e3e;
  border-color: rgba(163, 62, 62, 0.2);
  background: rgba(163, 62, 62, 0.12);
}

.relationship-role-badge--leading {
  color: #5b50ad;
  border-color: rgba(91, 80, 173, 0.2);
  background: rgba(91, 80, 173, 0.1);
}

.relationship-role-badge--direct {
  color: #305f83;
  border-color: rgba(48, 95, 131, 0.2);
  background: rgba(48, 95, 131, 0.1);
}

.relationship-role-badge--intermediate {
  color: #6b6475;
  border-color: rgba(107, 100, 117, 0.2);
  background: rgba(107, 100, 117, 0.09);
}

.relationship-role-badge--promotion {
  color: #8a5a11;
  border-color: rgba(138, 90, 17, 0.22);
  background: rgba(138, 90, 17, 0.1);
}

.relationship-role-badge--boundary {
  color: #8a5a11;
  border-color: rgba(138, 90, 17, 0.22);
  background: rgba(138, 90, 17, 0.1);
}

.relationship-role-badge--neutral {
  color: #738398;
  border-color: rgba(115, 131, 152, 0.18);
  background: rgba(115, 131, 152, 0.08);
}

.role-note {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.meta-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 12px;
  line-height: 1.3;
  text-align: center;
}

.meta-chip--entity {
  color: #5a6878;
  border-color: rgba(90, 104, 120, 0.16);
  background: rgba(90, 104, 120, 0.07);
}

.meta-chip--control {
  color: #305f83;
  border-color: rgba(48, 95, 131, 0.18);
  background: rgba(48, 95, 131, 0.08);
}

.ratio-text {
  color: #243648;
  font-weight: 600;
  white-space: nowrap;
}

.control-path-cell {
  display: grid;
  gap: 8px;
}

.path-summary {
  display: grid;
  gap: 4px;
}

.path-primary {
  color: #2d4156;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.path-structure-note {
  margin-bottom: 2px;
  color: #5b50ad;
  font-size: 12px;
  line-height: 1.55;
}

.path-secondary {
  color: var(--text-secondary);
  font-size: 12px;
}

.path-toggle {
  justify-self: flex-start;
  height: auto;
  padding: 0;
  font-size: 12px;
}

.path-list {
  display: grid;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(31, 59, 87, 0.12);
}

.path-list-item {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(31, 59, 87, 0.045);
}

.path-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
}

.path-index {
  color: var(--accent-gold);
  font-size: 12px;
  font-weight: 600;
}

.path-score {
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.path-detail {
  color: #314255;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.recognition-cell {
  display: grid;
  gap: 6px;
}

.recognition-headline {
  color: #243648;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.45;
}

.recognition-detail {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.actual-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 48px;
  min-height: 28px;
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 12px;
  font-weight: 700;
}

.actual-badge--yes {
  color: #a33e3e;
  border-color: rgba(163, 62, 62, 0.2);
  background: rgba(163, 62, 62, 0.12);
}

.actual-badge--no {
  color: #738398;
  border-color: rgba(115, 131, 152, 0.18);
  background: rgba(115, 131, 152, 0.08);
}

.basis-list {
  display: grid;
  gap: 5px;
}

.basis-item {
  display: grid;
  grid-template-columns: 62px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.basis-label {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
  white-space: nowrap;
}

.basis-value {
  color: #5d6b7a;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
</style>
