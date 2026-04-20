<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import {
  restoreManualControlJudgment,
  submitManualControlJudgment,
} from '@/api/analysis'
import { mergeControlRelationRows } from '@/utils/controlRelationsMerge'
import { isManualJudgmentCandidateRow } from '@/utils/manualJudgment'

const props = defineProps({
  companyId: {
    type: [Number, String],
    default: null,
  },
  relationships: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  controlAnalysis: {
    type: Object,
    default: () => ({}),
  },
  countryAttribution: {
    type: Object,
    default: () => ({}),
  },
  company: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['manual-judgment-change'])

const EMPTY_TEXT = '—'
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

const ENTITY_TYPE_LABELS = {
  company: '公司主体',
  person: '自然人',
  fund: '基金 / 公众持股',
  institution: '机构投资者',
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
  manual_override: '人工征订',
  manual_confirmed: '人工确认',
  manual_judgment: '人工判定',
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
  insufficient_evidence: '证据不足，暂未形成唯一实际控制人。',
  evidence_insufficient: '证据不足，暂未形成唯一实际控制人。',
  ownership_aggregation_pattern: '公众持股/分散持股聚合表达，不适合作为实际控制主体。',
}

const SELECTION_REASON_LABELS = {
  actual_controller_strict_control_threshold_met: '控制强度达到实际控制人判定条件。',
  leading_candidate: '当前为控制信号最强的候选主体。',
  leading_candidate_absolute_control: '数值信号较强，但仍需结合终局适格性和阻断规则判断。',
  leading_candidate_significant_influence: '达到显著影响水平，保留为候选观察项。',
  leading_candidate_weak_evidence: '控制比例较高，但证据强度不足以确认唯一实际控制人。',
  leading_candidate_relative_control_signal: '相对控制信号较强，暂作为领先候选保留。',
  leading_candidate_close_competition: '候选主体之间差距较小，暂未形成唯一实际控制人。',
  excluded_from_actual_race_due_to_terminal_profile: '已因终局主体画像排除出实际控制人竞选，仅保留为结构信号。',
  supporting_candidate: '作为辅助候选保留，用于解释控制链和竞争格局。',
  joint_control_candidate: '作为共同控制候选保留，不单独认定为实际控制人。',
  direct_controller_candidate: '作为直接控制层主体进入判定。',
}

const TERMINAL_IDENTIFIABILITY_LABELS = {
  identifiable_single_or_group: '可识别控制主体',
  aggregation_like: '聚合表达',
  unknown_or_blocked: '未知或阻断',
}

const TERMINAL_SUITABILITY_LABELS = {
  suitable_terminal: '适合终局停留',
  prefer_rollup: '优先继续上卷',
  blocked_terminal: '终局阻断',
  pattern_only: '仅结构信号',
}

const TERMINAL_PROFILE_REASON_LABELS = {
  terminal_identity_signal: '存在明确终局主体画像',
  default_identifiable_entity: '主体可识别并可归责',
  rollup_intermediary_entity: '更像中间层或控股平台',
  ownership_pattern_entity_profile: '主体画像接近公众持股/分散持股池',
  ownership_pattern_edge_signal: '关系证据指向 ownership aggregation',
  reused_non_terminal_ownership_bucket: '复用型非终局持股池',
  weak_name_hint: '名称仅作为弱辅助提示',
  high_ratio_but_no_terminal_governance: '比例较高但缺少终局治理控制证据',
}

const expandedPathRows = reactive({})
const judgmentDialogVisible = ref(false)
const judgmentSaving = ref(false)
const judgmentTargetRow = ref(null)
const judgmentForm = reactive({
  reason: '',
  evidence: '',
})

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
  mergeControlRelationRows(props.relationships)
    .map((relationship, index) => ({
      ...relationship,
      _tableKey: buildRelationshipKey(relationship, index),
      _sourceIndex: index,
    }))
    .sort((left, right) => {
      const displayPriority = rowDisplayPriority(left) - rowDisplayPriority(right)
      if (displayPriority !== 0) {
        return displayPriority
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

const manualEffective = computed(() => Boolean(props.controlAnalysis?.is_manual_effective))
const manualCountryEffective = computed(
  () =>
    Boolean(props.countryAttribution?.is_manual_effective) &&
    !Boolean(props.controlAnalysis?.is_manual_effective),
)
const manualOverride = computed(
  () => props.controlAnalysis?.manual_override || props.countryAttribution?.manual_override || {},
)
const manualSourceLabel = computed(() => {
  const source = props.controlAnalysis?.result_source || props.countryAttribution?.result_source
  if (source === 'manual_confirmed') {
    return '人工确认'
  }
  if (source === 'manual_judgment') {
    return '人工判定'
  }
  if (source === 'manual_override') {
    return '人工征订'
  }
  return '人工征订'
})
const isManualConfirmedResult = computed(
  () =>
    (props.controlAnalysis?.result_source || props.countryAttribution?.result_source) ===
    'manual_confirmed',
)
const isManualJudgmentResult = computed(
  () =>
    (props.controlAnalysis?.result_source || props.countryAttribution?.result_source) ===
    'manual_judgment',
)

const highestDirectControllerRatio = computed(() => {
  const ratios = props.relationships
    .filter((relationship) => isDirectRow(relationship))
    .map((relationship) => toPercentNumber(relationship.control_ratio))
    .filter((ratio) => ratio !== null)

  return ratios.length ? Math.max(...ratios) : null
})

const tableEmptyExplanation = computed(() => {
  const attributionType = normalizeKey(props.countryAttribution?.attribution_type)
  const countryBasis = tryParseJson(props.countryAttribution?.basis)
  const basis = countryBasis && typeof countryBasis === 'object' && !Array.isArray(countryBasis)
    ? countryBasis
    : {}
  const failure = normalizeKey(
    props.controlAnalysis?.terminal_failure_reason ||
      basis.terminal_failure_reason ||
      props.countryAttribution?.country_inference_reason,
  )

  if (attributionType === 'fallback_incorporation') {
    if (failure === 'ownership_aggregation_pattern') {
      return '当前无唯一实际控制人；主要控制信号来自公众持股/分散持股聚合表达，国别按注册地回退。'
    }
    if (failure === 'beneficial_owner_unknown' || failure === 'nominee_without_disclosure') {
      return '当前候选存在受益人不明或代持不透明，未形成唯一实际控制人，国别按注册地回退。'
    }
    return '当前未识别唯一实际控制人，国别按注册地回退。'
  }

  return '当前无控制关系明细；可结合上方控制摘要查看是否为共同控制、证据阻断或暂无有效输入。'
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

  const normalized = typeof value === 'string' ? value.replace('%', '').trim() : value
  const numeric = Number(normalized)
  if (Number.isNaN(numeric)) {
    return null
  }

  return numeric <= 1 ? numeric * 100 : numeric
}

function sortRatioValue(value) {
  return toPercentNumber(value) ?? -1
}

function rowDisplayPriority(row) {
  if (isCurrentEffectiveResultRow(row) && isManualEffectiveRow(row)) {
    return 0
  }
  if (isCurrentEffectiveResultRow(row)) {
    return 1
  }
  if (isAutomaticSupersededRow(row)) {
    return 2
  }
  if (isDirectRow(row)) {
    return 3
  }
  if (isLeadingRow(row)) {
    return 4
  }
  if (isBlockedCandidateRow(row)) {
    return 5
  }
  if (isOwnershipPatternRow(row)) {
    return 6
  }
  return 7
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
  if (/[\u4e00-\u9fff]/.test(String(value))) {
    return String(value).trim()
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

function manualField(row, key) {
  const overrideValue = manualOverride.value?.[key]
  return firstAvailable(row, key) ?? overrideValue
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

function terminalIdentifiability(row) {
  return normalizeKey(firstAvailable(row, 'terminal_identifiability'))
}

function terminalSuitability(row) {
  return normalizeKey(firstAvailable(row, 'terminal_suitability'))
}

function terminalProfileReasons(row) {
  const value = firstAvailable(row, 'terminal_profile_reasons')
  const parsed = tryParseJson(value)
  return Array.isArray(parsed) ? parsed.map((item) => normalizeKey(item)).filter(Boolean) : []
}

function terminalProfileText(row) {
  const identifiability = terminalIdentifiability(row)
  const suitability = terminalSuitability(row)
  const parts = []
  if (identifiability) {
    parts.push(TERMINAL_IDENTIFIABILITY_LABELS[identifiability] || identifiability)
  }
  if (suitability) {
    parts.push(TERMINAL_SUITABILITY_LABELS[suitability] || suitability)
  }
  return parts.join(' / ')
}

function terminalProfileReasonText(row) {
  return terminalProfileReasons(row)
    .map((reason) => TERMINAL_PROFILE_REASON_LABELS[reason] || reason)
    .filter(Boolean)
    .join('；')
}

function terminalFailureReason(row) {
  return normalizeKey(firstAvailable(row, 'terminal_failure_reason'))
}

function isOwnershipPatternRow(row) {
  return (
    isTruthy(firstAvailable(row, 'ownership_pattern_signal')) ||
    terminalIdentifiability(row) === 'aggregation_like' ||
    terminalSuitability(row) === 'pattern_only' ||
    terminalFailureReason(row) === 'ownership_aggregation_pattern'
  )
}

function isJointControlRow(row) {
  return (
    terminalFailureReason(row) === 'joint_control' ||
    normalizeKey(row?.control_type) === 'joint_control'
  )
}

function isBeneficialOwnerBlockedRow(row) {
  return ['beneficial_owner_unknown', 'nominee_without_disclosure'].includes(terminalFailureReason(row))
}

function isLowConfidenceRow(row) {
  return terminalFailureReason(row) === 'low_confidence_evidence_weak' || semanticFlags(row).includes('low_confidence')
}

function isEvidenceBlockedRow(row) {
  return ['insufficient_evidence', 'evidence_insufficient', 'close_competition'].includes(terminalFailureReason(row))
}

function isBlockedCandidateRow(row) {
  return (
    !isOwnershipPatternRow(row) &&
    !isActualRow(row) &&
    (isJointControlRow(row) || isBeneficialOwnerBlockedRow(row) || isLowConfidenceRow(row) || isEvidenceBlockedRow(row))
  )
}

function isPreferRollupRow(row) {
  return terminalSuitability(row) === 'prefer_rollup' || (isDirectRow(row) && hasPromotionSignal(row))
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
  if (isAutomaticSupersededRow(row)) {
    return false
  }
  if (isOwnershipPatternRow(row)) {
    return false
  }
  return (
    boolField(row, 'is_actual_controller') ||
    isUltimateRow(row) ||
    normalizeKey(firstAvailable(row, 'controller_status')) === 'actual_controller'
  )
}

function isManualEffectiveRow(row) {
  return (
    isTruthy(firstAvailable(row, 'is_manual_effective')) ||
    isTruthy(row?.is_current_effective) && normalizeKey(row?.result_source).startsWith('manual') ||
    normalizeKey(firstAvailable(row, 'source_type')).startsWith('manual') ||
    normalizeKey(firstAvailable(row, 'manual_result_source')).startsWith('manual')
  )
}

function isManualJudgmentEffectiveRow(row) {
  return (
    normalizeKey(firstAvailable(row, 'source_type')) === 'manual_judgment' ||
    normalizeKey(firstAvailable(row, 'result_source')) === 'manual_judgment' ||
    normalizeKey(firstAvailable(row, 'manual_result_source')) === 'manual_judgment'
  )
}

function isManualCountryOnlyRow(row) {
  return manualCountryEffective.value && isActualRow(row) && !isAutomaticSupersededRow(row)
}

function isAutomaticSupersededRow(row) {
  return isTruthy(row?.automatic_result_superseded) || isTruthy(firstAvailable(row, 'automatic_result_superseded'))
}

function hasMergedAutoReference(row) {
  return Boolean(row?._hasMergedAutoReference)
}

function isCurrentEffectiveResultRow(row) {
  if (isAutomaticSupersededRow(row)) {
    return false
  }
  if (isManualEffectiveRow(row)) {
    return true
  }
  if (isTruthy(row?.is_current_effective) || isTruthy(firstAvailable(row, 'is_current_effective'))) {
    return isActualRow(row)
  }
  return !manualEffective.value && isActualRow(row)
}

function canManualJudgeRow(row) {
  return isManualJudgmentCandidateRow(row, {
    isCurrentEffective: isCurrentEffectiveResultRow(row),
    isAutomaticSuperseded: isAutomaticSupersededRow(row),
  })
}

function openManualJudgmentDialog(row) {
  judgmentTargetRow.value = row
  judgmentForm.reason = ''
  judgmentForm.evidence = ''
  judgmentDialogVisible.value = true
}

async function handleSubmitManualJudgment() {
  const companyId = props.companyId || props.company?.id
  const target = judgmentTargetRow.value
  const reason = String(judgmentForm.reason ?? '').trim()
  if (!companyId) {
    ElMessage.warning('缺少 company_id，无法写入人工判定。')
    return
  }
  if (!target?.controller_entity_id) {
    ElMessage.warning('该行缺少主体 entity_id，无法人工判定。')
    return
  }
  if (!reason) {
    ElMessage.warning('请填写人工判定说明。')
    return
  }
  judgmentSaving.value = true
  try {
    await submitManualControlJudgment(companyId, {
      selected_controller_entity_id: Number(target.controller_entity_id),
      reason,
      evidence: String(judgmentForm.evidence ?? '').trim() || null,
      operator: 'researcher',
    })
    judgmentDialogVisible.value = false
    ElMessage.success('已将候选主体设为当前实际控制人（人工判定）。')
    emit('manual-judgment-change')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    judgmentSaving.value = false
  }
}

async function handleRestoreManualJudgment() {
  const companyId = props.companyId || props.company?.id
  if (!companyId) {
    ElMessage.warning('缺少 company_id，无法撤销人工判定。')
    return
  }
  judgmentSaving.value = true
  try {
    await restoreManualControlJudgment(companyId, {
      action_type: 'restore_manual_judgment',
      reason: '撤销人工判定，恢复更高优先级结果或自动分析结果。',
      operator: 'researcher',
    })
    ElMessage.success('已撤销人工判定。')
    emit('manual-judgment-change')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    judgmentSaving.value = false
  }
}

function isLeadingRow(row) {
  if (isOwnershipPatternRow(row) || isBlockedCandidateRow(row)) {
    return false
  }
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
  if (isManualEffectiveRow(row)) {
    if (isManualJudgmentEffectiveRow(row)) {
      return (
        manualField(row, 'manual_decision_reason') ||
        firstAvailable(row, 'manual_reason') ||
        '基于现有候选主体人工判定为当前实际控制人。'
      )
    }
    return (
      manualField(row, 'manual_decision_reason') ||
      (normalizeKey(firstAvailable(row, 'source_type')) === 'manual_confirmed'
        ? '经人工确认后采用当前自动分析结论。'
        : '人工征订确定当前实际控制人，基于人工构建控制路径生效。')
    )
  }
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
  return formatRatio(
    path?.path_ratio ??
      path?.control_ratio ??
      path?.ratio ??
      path?.path_strength ??
      path?.path_score_pct ??
      path?.path_score,
  )
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

function primaryPathRatioText(row) {
  return pathScoreText(pathSummary(row).paths[0])
}

function displayControlStrength(row) {
  if (isManualEffectiveRow(row)) {
    const backendValue = manualField(row, 'manual_display_control_strength')
    const backendSource = normalizeKey(manualField(row, 'manual_display_control_strength_source'))
    const backendSourceLabel = manualField(row, 'manual_display_control_strength_source_label')
    if (backendValue) {
      return {
        value: backendValue,
        text: formatRatio(backendValue),
        source:
          backendSource === 'manual_primary_path_ratio'
            ? 'manual_primary_path_ratio'
            : 'manual_final_strength',
        note:
          backendSource === 'manual_primary_path_ratio'
            ? '来自主路径'
            : backendSourceLabel || manualSourceLabel.value || '人工征订',
      }
    }

    const finalStrength = manualField(row, 'manual_control_ratio')
    if (finalStrength) {
      return {
        value: finalStrength,
        text: formatRatio(finalStrength),
        source: 'manual_final_strength',
        note: manualSourceLabel.value || '人工征订',
      }
    }

    const primaryPathRatio = primaryPathRatioText(row)
    if (primaryPathRatio !== EMPTY_TEXT) {
      return {
        value: primaryPathRatio,
        text: primaryPathRatio,
        source: 'manual_primary_path_ratio',
        note: '来自主路径',
      }
    }

    return {
      value: null,
      text: EMPTY_TEXT,
      source: 'empty',
      note: '未填写精确比例',
    }
  }

  return {
    value: row?.control_ratio,
    text: formatRatio(row?.control_ratio),
    source: 'automatic',
    note: '自动分析',
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
  if (isManualEffectiveRow(row)) {
    const tags = [
      { label: '实际控制人', type: 'actual' },
      {
        label: isManualJudgmentEffectiveRow(row)
          ? '人工判定生效'
          : isManualConfirmedResult.value
            ? '人工确认生效'
            : '人工征订生效',
        type: 'manual',
      },
    ]
    if (hasMergedAutoReference(row)) {
      tags.push({ label: '自动分析结果（参考）', type: 'neutral' })
    }
    return tags
  }

  if (isAutomaticSupersededRow(row)) {
    return [
      { label: '自动分析结果（参考）', type: 'neutral' },
      { label: '已被人工覆盖', type: 'boundary' },
    ]
  }

  if (isOwnershipPatternRow(row)) {
    return [
      { label: '结构信号', type: 'pattern' },
      { label: '非实际控制主体', type: 'not-controller' },
    ]
  }

  if (isJointControlRow(row) && !isActualRow(row)) {
    return [{ label: '共同控制', type: 'boundary' }]
  }

  if (isBeneficialOwnerBlockedRow(row) && !isActualRow(row)) {
    return [{ label: '受益人未明', type: 'boundary' }]
  }

  if (isLowConfidenceRow(row) && !isActualRow(row)) {
    return [{ label: '低置信候选', type: 'boundary' }]
  }

  const tags = []
  if (isCurrentEffectiveResultRow(row)) {
    tags.push({ label: '实际控制人', type: 'actual' })
  } else if (isActualRow(row)) {
    tags.push({ label: '自动分析结果', type: 'neutral' })
  }
  if (isManualCountryOnlyRow(row)) {
    tags.push({ label: '国别人工征订', type: 'manual' })
  }
  if (isDirectRow(row)) {
    tags.push({ label: '直接控制人', type: 'direct' })
  }
  if (isIntermediateRow(row)) {
    tags.push({ label: '中间层', type: 'intermediate' })
  }
  if (isPreferRollupRow(row) && !isActualRow(row)) {
    tags.push({ label: '继续上卷', type: 'promotion' })
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
  if (isManualEffectiveRow(row)) {
    if (isManualJudgmentEffectiveRow(row)) {
      if (hasMergedAutoReference(row)) {
        return '当前生效结论由人工判定确定；自动分析同主体结果已合并为参考信息。'
      }
      return '当前生效结论由研究人员从现有候选主体中人工判定。'
    }
    return isManualConfirmedResult.value
      ? '当前生效结论为人工确认后的自动分析结果。'
      : '当前生效结论由人工征订写回数据库，非算法自动识别。'
  }
  if (isManualCountryOnlyRow(row)) {
    return '控制主体沿用当前结论，实际控制国别经人工征订调整。'
  }
  if (isAutomaticSupersededRow(row)) {
    return '自动分析结果保留为参考信息，不再作为当前生效主记录。'
  }
  if (isOwnershipPatternRow(row)) {
    return '结构信号主体：保留研究价值，但不参与实际控制人主结论。'
  }
  if (isBlockedCandidateRow(row)) {
    return `阻断候选：${terminalFailureText(row) || determinationStatus(row).note}`
  }
  if (isPreferRollupRow(row) && !isActualRow(row)) {
    return '中间层主体，当前结论继续向上穿透。'
  }
  const tier = controlTierLabel(row)
  if (tier) {
    return tier
  }
  if (getControlPaths(row.control_path).length) {
    return '控制路径主体'
  }
  return ''
}

function determinationStatus(row) {
  const profile = terminalProfileText(row)
  if (isManualEffectiveRow(row)) {
    if (isManualJudgmentEffectiveRow(row)) {
      return {
        label: '当前生效结论',
        type: 'manual',
        note: hasMergedAutoReference(row)
          ? '人工判定结果（自动分析同主体参考已合并）'
          : '人工判定结果，基于现有候选，非算法自动识别唯一控制人',
      }
    }
    const label = manualSourceLabel.value || '人工征订'
    return {
      label: '当前生效结论',
      type: 'manual',
      note: label === '人工确认'
        ? '自动结果经人工确认后继续生效'
        : `${label}结果，当前生效，非算法自动识别`,
    }
  }
  if (isManualCountryOnlyRow(row)) {
    return {
      label: '国别人工征订',
      type: 'manual',
      note: '控制主体沿用当前结论，国别以人工征订为准',
    }
  }
  if (isAutomaticSupersededRow(row)) {
    if (isManualJudgmentResult.value) {
      return {
        label: '自动分析结果（参考）',
        type: 'neutral',
        note: '已被人工判定覆盖，非当前生效结果',
      }
    }
    return {
      label: isManualConfirmedResult.value ? '自动分析结果（已确认）' : '自动分析结果（参考）',
      type: 'neutral',
      note: isManualConfirmedResult.value
        ? '原自动结论已由人工确认行承接，非单独当前行'
        : '已被人工征订覆盖，非当前生效结果',
    }
  }
  if (isOwnershipPatternRow(row)) {
    return {
      label: '结构信号',
      type: 'pattern',
      note: profile || '仅作为结构信号保留',
    }
  }
  if (isActualRow(row)) {
    return {
      label: isDirectRow(row) ? '已采纳' : '上卷采纳',
      type: 'accepted',
      note: isDirectRow(row) ? '已计入当前实际控制人结论' : '作为上卷后的当前实际控制人结论采纳',
    }
  }
  if (isPreferRollupRow(row)) {
    return {
      label: '继续上卷',
      type: 'rollup',
      note: profile || '当前主体更适合作为中间层继续上卷',
    }
  }
  if (isJointControlRow(row)) {
    return {
      label: '共同控制',
      type: 'blocked',
      note: '不硬选单一实际控制人',
    }
  }
  if (isBeneficialOwnerBlockedRow(row)) {
    return {
      label: '受益人未明',
      type: 'blocked',
      note: '受益所有人披露不足',
    }
  }
  if (isLowConfidenceRow(row)) {
    return {
      label: '低置信',
      type: 'warning',
      note: '证据强度不足',
    }
  }
  if (isEvidenceBlockedRow(row)) {
    return {
      label: '证据阻断',
      type: 'blocked',
      note: terminalFailureText(row) || '未形成唯一控制结论',
    }
  }
  if (isLeadingRow(row)) {
    return {
      label: '候选保留',
      type: 'candidate',
      note: '未进入 actual 结论',
    }
  }
  return {
    label: '辅助候选',
    type: 'neutral',
    note: profile || '用于解释控制链',
  }
}

function ratioMeaning(row) {
  if (isManualEffectiveRow(row)) {
    return displayControlStrength(row).note
  }
  if (isOwnershipPatternRow(row)) {
    return '股权聚合比例，不参与实际控制人竞选'
  }
  const mode = normalizeKey(firstAvailable(row, 'control_mode'))
  const type = normalizeKey(row?.control_type)
  if (isActualRow(row)) {
    return isDirectRow(row) ? '终局控制得分，已采纳' : '上卷后终局控制得分'
  }
  if (isPreferRollupRow(row)) {
    return '中间层控制比例，需继续上卷'
  }
  if (mode === 'semantic' || ['agreement_control', 'board_control', 'voting_right_control', 'vie_control'].includes(type)) {
    return '语义控制强度，不等同于持股比例'
  }
  if (mode === 'mixed' || type === 'mixed_control') {
    return '股权与治理语义综合得分'
  }
  if (type === 'significant_influence') {
    return '显著影响水平，非实际控制结论'
  }
  return '控制路径折算得分'
}

function pathSemanticLabel(row, path) {
  if (isManualEffectiveRow(row)) {
    if (isManualJudgmentEffectiveRow(row)) {
      return '人工判定复用路径'
    }
    return isManualConfirmedResult.value ? '人工确认自动路径' : '人工征订路径'
  }
  if (isOwnershipPatternRow(row)) {
    return 'ownership aggregation path'
  }
  const flags = semanticFlags(row)
  if (flags.includes('vie')) {
    return 'VIE 控制路径'
  }
  if (flags.includes('board_control')) {
    return '董事会控制路径'
  }
  if (flags.includes('voting_right')) {
    return '表决权控制路径'
  }
  if (flags.includes('agreement')) {
    return '协议控制路径'
  }
  if (hasPromotionSignal(row) || pathKind(row, path) === 'indirect') {
    return '股权上卷路径'
  }
  return '股权控制路径'
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

  if (isManualEffectiveRow(row)) {
    if (isManualJudgmentEffectiveRow(row)) {
      headline = '人工判定确定实际控制人'
      details.push('当前实际控制人为人工判定确定，基于现有候选主体选择。')
      details.push(
        hasMergedAutoReference(row)
          ? '自动分析结果与该主体一致，已合并为本行参考信息。'
          : '该结论非算法自动形成的唯一实际控制人，自动分析结果保留用于参考。',
      )
      details.push('当前展示以人工判定生效结果为准。')
      details.push(`人工判定说明：${manualOverride.value?.reason || firstAvailable(row, 'manual_reason') || '未填写'}`)
      details.push(`人工判定依据：${manualOverride.value?.evidence || firstAvailable(row, 'manual_evidence') || '未填写'}`)
      const primaryPathText = pathSummary(row).primaryPathText
      if (primaryPathText && primaryPathText !== EMPTY_TEXT) {
        details.push(`当前生效路径摘要：${primaryPathText}。`)
      }
      if (hasMergedAutoReference(row) && row._autoReferencePathText && row._autoReferencePathText !== primaryPathText) {
        details.push(`自动分析路径摘要：${row._autoReferencePathText}。`)
      }
      const autoName = firstAvailable(row, 'automatic_actual_controller_name')
      if (autoName && !hasMergedAutoReference(row)) {
        details.push(`自动分析结果为：${autoName}。`)
      }
      if (hasMergedAutoReference(row)) {
        details.push(
          row._autoReferenceIsSamePath
            ? '自动分析路径与当前生效路径一致。'
            : '自动分析路径作为参考补充，不再拆分为第二行。',
        )
      }
      return {
        headline,
        details: dedupeList(details).slice(0, 7),
      }
    }
    const isConfirmed = manualSourceLabel.value === '人工确认'
    headline = isConfirmed ? '人工确认自动结果' : '人工征订确定实际控制人'
    details.push(
      isConfirmed
        ? '当前结果为自动分析结果，经人工确认后继续生效。'
        : '当前实际控制人为人工征订确定，非算法自动识别结果。',
    )
    if (!isConfirmed) {
      details.push('当前主路径由人工征订构建，并优先驱动路径摘要、路径数量与链路深度。')
    }
    details.push(`${isConfirmed ? '人工确认说明' : '本次征订说明'}：${manualOverride.value?.reason || firstAvailable(row, 'manual_reason') || '未填写'}`)
    details.push(`${isConfirmed ? '人工确认依据' : '本次征订依据'}：${manualOverride.value?.evidence || firstAvailable(row, 'manual_evidence') || '未填写'}`)
    const decisionReason = selectionReasonText(row)
    if (decisionReason) {
      details.push(`判定原因：${decisionReason}`)
    }
    const strengthDisplay = displayControlStrength(row)
    if (strengthDisplay.value && strengthDisplay.source === 'manual_final_strength') {
      details.push(`最终展示控制强度：${strengthDisplay.text}（人工征订指定值）。`)
    } else if (strengthDisplay.value && strengthDisplay.source === 'manual_primary_path_ratio') {
      details.push(`当前控制强度基于主路径支持比例：${strengthDisplay.text}。`)
    }
    const primaryPathText = pathSummary(row).primaryPathText
    if (primaryPathText && primaryPathText !== EMPTY_TEXT) {
      details.push(
        `人工控制路径：${primaryPathText}。`,
      )
    }
    if (!isConfirmed) {
      details.push('路径支持比例如未填写，仅表示结构支持关系，不代表已录入精确控制比例。')
    }
    const autoName = firstAvailable(row, 'automatic_actual_controller_name')
    if (autoName) {
      details.push(`自动分析结果为：${autoName}。`)
    }
    return {
      headline,
      details: dedupeList(details).slice(0, 7),
    }
  } else if (isManualCountryOnlyRow(row)) {
    headline = '实际控制国别经人工征订调整'
    details.push('实际控制国别经人工征订调整。')
    details.push('控制主体仍沿用当前控制结论。')
    details.push(`人工征订说明：${manualOverride.value?.reason || '未填写'}`)
    details.push(`人工征订依据：${manualOverride.value?.evidence || '未填写'}`)
    if (props.countryAttribution?.actual_control_country) {
      details.push(`当前实际控制国别：${props.countryAttribution.actual_control_country}。`)
    }
  } else if (isAutomaticSupersededRow(row)) {
    headline = isManualConfirmedResult.value ? '自动分析结果（已确认）' : '自动分析结果（参考）'
    details.push('该行来自自动分析结果，当前仅供查看。')
    details.push(
      isManualJudgmentResult.value
        ? '当前生效结论已由人工判定结果优先覆盖。'
        : isManualConfirmedResult.value
        ? '当前生效结论已由人工确认行承接展示。'
        : '当前生效结论已由人工征订结果优先覆盖。',
    )
  } else if (isOwnershipPatternRow(row)) {
    headline = '结构信号：非实际控制主体'
    details.push('该主体更像公众持股/分散持股聚合表达，不代表统一控制意志。')
    details.push(terminalProfileText(row) || '缺少可归责的终局主体画像。')
    details.push('已排除出“实际控制人 / 直接控制人 / 领先候选”主表达，仅保留为研究结构信号。')
  } else if (isJointControlRow(row) && !isActualRow(row)) {
    headline = '共同控制阻断'
    details.push(terminalText || '存在共同控制结构，后端不硬选单一实际控制人。')
    details.push('该主体保留用于解释共同控制格局。')
    details.push('结果影响：未单独计入实际控制人结论。')
  } else if (isBeneficialOwnerBlockedRow(row) && !isActualRow(row)) {
    headline = '受益人未明 / 穿透阻断'
    details.push(terminalText || '受益所有人或代持披露不足，暂不形成唯一实际控制人。')
    details.push('结果影响：不进入实际控制人结论，需后续补充披露线索。')
  } else if (isLowConfidenceRow(row) && !isActualRow(row)) {
    headline = '低置信候选'
    details.push(terminalText || '控制证据强度不足，仅保留为候选或辅助说明。')
    details.push('结果影响：未计入实际控制人结论。')
  } else if (isActualRow(row)) {
    if (isDirectRow(row)) {
      headline = '直接控制并认定为实际控制人'
      details.push('该主体位于直接控制层，且满足最终控制判定条件。')
      details.push('结果影响：已计入“实际控制人 / 直接控制人”结论。')
    } else if (hasPromotionSignal(row)) {
      headline = '上卷后认定为实际控制人'
      details.push(promotionText || '直接控制层继续向上穿透，最终控制归属落在该上层主体。')
      details.push('结果影响：已计入“实际上卷后的最终控制人”结论。')
    } else {
      headline = '认定为实际控制人'
      details.push('后端已形成唯一实际控制人结论。')
      details.push('结果影响：已计入实际控制人结论。')
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
    details: dedupeList(details).slice(0, 4),
  }
}

function basisLinesFromObject(row, basis) {
  const lines = []
  const inferredPathCount = getControlPaths(row.control_path).length
  const pathCount = basis.path_count ?? inferredPathCount

  if (isManualEffectiveRow(row)) {
    const manualType = manualField(row, 'manual_control_type') || basis.classification || row.control_type
    const strengthDisplay = displayControlStrength(row)
    const manualPathCount = manualField(row, 'manual_path_count') ?? pathCount
    const manualPathDepth = manualField(row, 'manual_path_depth') ?? row.control_chain_depth ?? basis.control_chain_depth
    const manualPath = manualField(row, 'manual_control_path') || pathSummary(row).primaryPathText

    lines.push({
      label: '认定类型',
      value: controlTypeLabel(manualType) || manualSourceLabel.value,
    })
    lines.push({
      label: '依据方式',
      value: hasMergedAutoReference(row)
        ? `${manualSourceLabel.value}；自动分析同主体参考`
        : manualSourceLabel.value,
    })
    lines.push({
      label: '判定原因',
      value: selectionReasonText(row),
    })
    if (strengthDisplay.value) {
      lines.push({
        label: '控制强度',
        value: `${strengthDisplay.text}（${strengthDisplay.note}）`,
      })
    }
    if (manualPath && manualPath !== EMPTY_TEXT) {
      lines.push({
        label: '控制路径',
        value: manualPath,
      })
    }
    if (manualPathDepth) {
      lines.push({
        label: '链路深度',
        value: `${manualPathDepth}层`,
      })
    }
    if (manualPathCount) {
      lines.push({
        label: '路径数量',
        value: `${manualPathCount}条`,
      })
    }
    lines.push({
      label: '征订说明',
      value: manualOverride.value?.reason || basis.manual_reason || EMPTY_TEXT,
    })
    lines.push({
      label: '征订依据',
      value: manualOverride.value?.evidence || basis.manual_evidence || EMPTY_TEXT,
    })
    if (basis.manual_decided_at) {
      lines.push({
        label: '征订时间',
        value: basis.manual_decided_at,
      })
    }
    if (hasMergedAutoReference(row)) {
      lines.push({
        label: '自动参考',
        value: row._autoReferenceIsSamePath
          ? '自动分析同主体且路径一致，已合并展示'
          : '自动分析同主体，路径作为参考补充',
      })
      if (row._autoReferencePathText) {
        lines.push({
          label: '自动路径',
          value: row._autoReferencePathText,
        })
      }
      if (row._autoReferenceControlRatio !== null && row._autoReferenceControlRatio !== undefined && row._autoReferenceControlRatio !== '') {
        lines.push({
          label: '自动强度',
          value: formatRatio(row._autoReferenceControlRatio),
        })
      }
    }
    return lines
  }

  if (isManualCountryOnlyRow(row)) {
    lines.push({
      label: '认定类型',
      value: '国别人工征订',
    })
    lines.push({
      label: '判定原因',
      value: '实际控制国别经人工征订调整，控制主体仍沿用当前结论。',
    })
    lines.push({
      label: '控制国别',
      value: props.countryAttribution?.actual_control_country || EMPTY_TEXT,
    })
    lines.push({
      label: '征订说明',
      value: manualOverride.value?.reason || EMPTY_TEXT,
    })
    lines.push({
      label: '征订依据',
      value: manualOverride.value?.evidence || EMPTY_TEXT,
    })
    if (manualOverride.value?.created_at) {
      lines.push({
        label: '征订时间',
        value: manualOverride.value.created_at,
      })
    }
    return lines
  }

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

  if (firstAvailable(row, 'selection_reason')) {
    lines.push({
      label: '判定原因',
      value: selectionReasonText(row),
    })
  }

  if (terminalProfileText(row)) {
    lines.push({
      label: '终局画像',
      value: terminalProfileText(row),
    })
  }

  if (terminalProfileReasonText(row)) {
    lines.push({
      label: '画像理由',
      value: terminalProfileReasonText(row),
    })
  }

  if (isOwnershipPatternRow(row)) {
    lines.push({
      label: '结构信号',
      value: '是，非实际控制主体',
    })
  }

  if (terminalFailureText(row)) {
    lines.push({
      label: '阻断原因',
      value: terminalFailureText(row),
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
  if (isManualEffectiveRow(row) || isManualCountryOnlyRow(row)) {
    return 'control-relations-table__row--manual'
  }
  if (isAutomaticSupersededRow(row)) {
    return 'control-relations-table__row--superseded'
  }
  if (isActualRow(row)) {
    return 'control-relations-table__row--actual'
  }
  if (isOwnershipPatternRow(row)) {
    return 'control-relations-table__row--pattern'
  }
  if (isBlockedCandidateRow(row)) {
    return 'control-relations-table__row--blocked'
  }
  if (isPreferRollupRow(row)) {
    return 'control-relations-table__row--rollup'
  }
  return ''
}
</script>

<template>
  <el-card class="surface-card" shadow="never">
    <template #header>
      <div class="section-heading">
        <div>
          <h3>控制结论明细表</h3>
          <p>展示谁被采纳、谁被排除，以及候选主体、结构信号和控制路径的判定依据。</p>
        </div>
      </div>
    </template>

    <el-alert
      v-if="manualEffective || manualCountryEffective"
      class="manual-table-alert"
      type="warning"
      show-icon
      :closable="false"
      :title="manualCountryEffective ? '实际控制国别人工征订当前生效' : `${manualSourceLabel}结果当前生效`"
          :description="manualCountryEffective
        ? '控制主体沿用当前结论，实际控制国别以人工征订结果为准。'
        : isManualConfirmedResult
          ? '控制结论明细表已优先展示人工确认后的当前结果；自动分析原始信息仅保留为参考。'
          : isManualJudgmentResult
            ? '控制结论明细表已优先展示人工判定结果；同主体同语义的自动分析结果会合并为参考信息。'
            : `控制结论明细表已优先展示${manualSourceLabel}结果，并使用人工构建路径作为主路径；自动分析结果仅在需要时以参考信息保留。`"
    />

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
            <div v-if="isOwnershipPatternRow(row)" class="controller-subnote">
              结构信号主体 / 非实际控制主体
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

      <el-table-column label="判定状态" min-width="170">
        <template #default="{ row }">
          <div class="decision-status">
            <span
              :class="[
                'decision-badge',
                `decision-badge--${determinationStatus(row).type}`,
              ]"
            >
              {{ determinationStatus(row).label }}
            </span>
            <div class="decision-note">
              {{ determinationStatus(row).note }}
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="控制强度" min-width="142" align="center" header-align="center">
        <template #default="{ row }">
          <div class="ratio-stack">
            <span class="ratio-text">
              {{ displayControlStrength(row).text }}
            </span>
            <span class="ratio-note">
              {{ ratioMeaning(row) }}
            </span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="控制路径" min-width="400">
        <template #default="{ row }">
          <div class="control-path-cell">
            <template v-if="pathSummary(row).pathCount">
              <div class="table-text table-multi-line path-summary">
                <div v-if="isOwnershipPatternRow(row)" class="path-structure-note path-structure-note--pattern">
                  结构信号路径：保留用于研究，不作为实际控制人主路径。
                </div>
                <div v-if="pathSummary(row).hasDirectAndIndirect" class="path-structure-note">
                  路径结构：直接 + 间接多路径汇聚；图中突出主路径，其余作为补充路径。
                </div>
                <template v-if="pathSummary(row).hasMultiplePaths">
                  <div class="path-primary">
                    主路径（{{ pathKindLabel(pathSummary(row).primaryPathKind) }} / {{ pathSemanticLabel(row, pathSummary(row).paths[0]) }}）：{{ pathSummary(row).primaryPathText }}
                    <template v-if="pathScoreText(pathSummary(row).paths[0]) !== EMPTY_TEXT">
                      · 路径支持比例 {{ pathScoreText(pathSummary(row).paths[0]) }}
                    </template>
                  </div>
                  <div class="path-secondary">另有 {{ pathSummary(row).extraPathCount }} 条补充路径</div>
                </template>
                <template v-else>
                  <div class="path-primary">
                    {{ pathSemanticLabel(row, pathSummary(row).paths[0]) }}：{{ pathSummary(row).primaryPathText }}
                    <template v-if="pathScoreText(pathSummary(row).paths[0]) !== EMPTY_TEXT">
                      · 路径支持比例 {{ pathScoreText(pathSummary(row).paths[0]) }}
                    </template>
                  </div>
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
                      路径 {{ pathIndex + 1 }} · {{ pathKindLabel(pathKind(row, path)) }} · {{ pathSemanticLabel(row, path) }}
                    </span>
                    <span v-if="pathScoreText(path) !== EMPTY_TEXT" class="path-score">
                      路径支持比例 {{ pathScoreText(path) }}
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
            :class="isCurrentEffectiveResultRow(row) ? 'actual-badge--yes' : 'actual-badge--no'"
          >
            {{ isCurrentEffectiveResultRow(row) ? '是' : '否' }}
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

      <el-table-column label="人工判定" min-width="156" fixed="right" align="center" header-align="center">
        <template #default="{ row }">
          <div class="judgment-actions">
            <el-button
              v-if="canManualJudgeRow(row)"
              size="small"
              type="primary"
              plain
              @click="openManualJudgmentDialog(row)"
            >
              设为实际控制人
            </el-button>
            <span v-else-if="isManualJudgmentEffectiveRow(row)" class="judgment-current">
              人工判定生效
            </span>
            <span v-else class="table-text table-text--muted">—</span>
          </div>
        </template>
      </el-table-column>

      <template #empty>
        <div class="table-empty-explanation">
          <div class="table-empty-title">暂无控制结论明细</div>
          <p>{{ tableEmptyExplanation }}</p>
        </div>
      </template>
    </el-table>

    <div v-if="isManualJudgmentResult" class="manual-judgment-restore">
      <el-button size="small" plain type="warning" :loading="judgmentSaving" @click="handleRestoreManualJudgment">
        撤销人工判定
      </el-button>
      <span>撤销后恢复为人工征订结果或自动分析结果。</span>
    </div>

    <el-dialog
      v-model="judgmentDialogVisible"
      title="人工判定为实际控制人"
      width="520px"
      destroy-on-close
    >
      <div class="manual-judgment-dialog">
        <p>
          将 <strong>{{ judgmentTargetRow?.controller_name || EMPTY_TEXT }}</strong>
          设为当前实际控制人。该操作基于现有候选主体，不修改人工征订路径。
        </p>
        <el-form label-position="top">
          <el-form-item label="人工判定说明">
            <el-input
              v-model="judgmentForm.reason"
              type="textarea"
              :rows="3"
              placeholder="请说明为什么在当前候选中选择该主体"
            />
          </el-form-item>
          <el-form-item label="人工判定依据（可选）">
            <el-input
              v-model="judgmentForm.evidence"
              type="textarea"
              :rows="2"
              placeholder="例如披露文件、研究记录或补充材料"
            />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="judgmentDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="judgmentSaving" @click="handleSubmitManualJudgment">
          确认人工判定
        </el-button>
      </template>
    </el-dialog>
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

.manual-table-alert {
  margin-bottom: 14px;
}

.manual-judgment-restore {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 12px;
  color: var(--text-secondary);
  font-size: 13px;
}

.manual-judgment-dialog p {
  margin: 0 0 14px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.judgment-actions {
  display: grid;
  gap: 6px;
  justify-items: center;
}

.judgment-current {
  color: #8a4b12;
  font-size: 12px;
  font-weight: 700;
}

.control-relations-table :deep(.control-relations-table__row--manual > td) {
  background: rgba(155, 58, 58, 0.075);
}

.control-relations-table :deep(.control-relations-table__row--manual:hover > td) {
  background: rgba(155, 58, 58, 0.105) !important;
}

.control-relations-table :deep(.control-relations-table__row--superseded > td) {
  background: rgba(115, 131, 152, 0.055);
}

.control-relations-table :deep(.control-relations-table__row--superseded:hover > td) {
  background: rgba(115, 131, 152, 0.085) !important;
}

.control-relations-table :deep(.control-relations-table__row--actual > td) {
  background: rgba(168, 73, 73, 0.055);
}

.control-relations-table :deep(.control-relations-table__row--actual:hover > td) {
  background: rgba(168, 73, 73, 0.085) !important;
}

.control-relations-table :deep(.control-relations-table__row--pattern > td) {
  background: rgba(71, 99, 126, 0.055);
}

.control-relations-table :deep(.control-relations-table__row--pattern:hover > td) {
  background: rgba(71, 99, 126, 0.085) !important;
}

.control-relations-table :deep(.control-relations-table__row--blocked > td) {
  background: rgba(138, 90, 17, 0.045);
}

.control-relations-table :deep(.control-relations-table__row--blocked:hover > td) {
  background: rgba(138, 90, 17, 0.075) !important;
}

.control-relations-table :deep(.control-relations-table__row--rollup > td) {
  background: rgba(48, 95, 131, 0.035);
}

.control-relations-table :deep(.control-relations-table__row--rollup:hover > td) {
  background: rgba(48, 95, 131, 0.065) !important;
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

.controller-subnote {
  color: #647486;
  font-size: 12px;
  line-height: 1.45;
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

.relationship-role-badge--manual {
  color: #9b3a3a;
  border-color: rgba(155, 58, 58, 0.24);
  background: rgba(155, 58, 58, 0.12);
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

.relationship-role-badge--pattern,
.relationship-role-badge--not-controller {
  color: #486071;
  border-color: rgba(72, 96, 113, 0.2);
  background: rgba(72, 96, 113, 0.1);
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

.decision-status {
  display: grid;
  gap: 6px;
}

.decision-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  min-height: 26px;
  padding: 3px 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.decision-badge--accepted {
  color: #a33e3e;
  border-color: rgba(163, 62, 62, 0.2);
  background: rgba(163, 62, 62, 0.12);
}

.decision-badge--manual {
  color: #9b3a3a;
  border-color: rgba(155, 58, 58, 0.24);
  background: rgba(155, 58, 58, 0.12);
}

.decision-badge--pattern {
  color: #486071;
  border-color: rgba(72, 96, 113, 0.22);
  background: rgba(72, 96, 113, 0.1);
}

.decision-badge--blocked,
.decision-badge--warning,
.decision-badge--rollup {
  color: #8a5a11;
  border-color: rgba(138, 90, 17, 0.22);
  background: rgba(138, 90, 17, 0.1);
}

.decision-badge--candidate,
.decision-badge--neutral {
  color: #5a6878;
  border-color: rgba(90, 104, 120, 0.16);
  background: rgba(90, 104, 120, 0.07);
}

.decision-note {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.ratio-stack {
  display: grid;
  justify-items: center;
  gap: 4px;
}

.ratio-text {
  color: #243648;
  font-weight: 600;
  white-space: nowrap;
}

.ratio-note {
  max-width: 128px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.45;
  white-space: normal;
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

.path-structure-note--pattern {
  color: #486071;
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

.table-empty-explanation {
  display: grid;
  gap: 6px;
  max-width: 520px;
  margin: 0 auto;
  padding: 20px 12px;
  color: var(--text-secondary);
  line-height: 1.65;
}

.table-empty-title {
  color: var(--brand-ink);
  font-weight: 700;
}
</style>


