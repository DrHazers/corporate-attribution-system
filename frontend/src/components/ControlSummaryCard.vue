<script setup>
import { computed } from 'vue'

import ControlStructureDiagram from '@/components/ControlStructureDiagram.vue'
import ControlStructurePlaceholder from '@/components/ControlStructurePlaceholder.vue'

const ENABLE_REBUILT_CONTROL_STRUCTURE_DIAGRAM = true

const props = defineProps({
  company: {
    type: Object,
    default: () => ({}),
  },
  controlAnalysis: {
    type: Object,
    default: () => ({}),
  },
  countryAttribution: {
    type: Object,
    default: () => ({}),
  },
  relationshipGraph: {
    type: Object,
    default: () => ({
      node_count: 0,
      edge_count: 0,
      nodes: [],
      edges: [],
      message: '后续接入控制链图展示',
    }),
  },
  graphError: {
    type: String,
    default: '',
  },
})

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
  board_control: '董事会席位控制',
  voting_right: '表决权安排',
  voting_right_control: '表决权安排',
  nominee: '代持 / 名义持有人',
  nominee_control: '代持 / 名义持有人',
  vie: 'VIE 结构',
  vie_control: 'VIE 结构',
  mixed_control: '混合控制',
  joint_control: '共同控制',
  manual_override: '人工征订',
  manual_confirmed: '人工确认',
  manual_judgment: '人工判定',
}

const ATTRIBUTION_TYPE_LABELS = {
  equity_control: '股权控制归属',
  agreement_control: '协议控制归属',
  board_control: '董事会席位控制归属',
  voting_right_control: '表决权安排归属',
  mixed_control: '混合控制归属',
  joint_control: '共同控制归属',
  fallback_incorporation: '回落至注册地',
  fallback_listing: '回落至上市地',
  fallback_listing_country: '回落至上市地',
  fallback_headquarters: '回落至总部所在地',
  fallback_unknown: '未识别',
  manual_override: '人工征订归属',
  manual_confirmed: '人工确认归属',
  manual_judgment: '人工判定归属',
}

const ATTRIBUTION_LAYER_LABELS = {
  direct_controller_country: '直接控制人国家/地区',
  ultimate_controller_country: '最终控制人国家/地区',
  fallback_incorporation: '注册地兜底',
  joint_control_undetermined: '共同控制未定',
}

const CONTROL_MODE_LABELS = {
  numeric: '数值控制',
  semantic: '语义控制',
  mixed: '混合控制',
}

const PROMOTION_REASON_LABELS = {
  disclosed_ultimate_parent: '上层母体披露清晰，本次根据上层控制主体形成最终控制判断。',
  beneficial_owner_priority: '受益控制人线索更具解释力，本次采用上层主体作为最终控制判断。',
  controls_direct_controller: '上层主体能够控制直接控制人，因此结论继续上卷至上层主体。',
  look_through_holding_vehicle: '直接控制人为控股平台或 SPV 等中间载体，本次继续向上穿透。',
  trust_vehicle_lookthrough: '信托载体具备继续穿透条件，本次采用上层控制主体作为解释对象。',
}

const PROMOTION_REASON_SHORT_LABELS = {
  disclosed_ultimate_parent: '披露上层母体',
  beneficial_owner_priority: '受益控制人优先',
  controls_direct_controller: '上层控制直接控制人',
  look_through_holding_vehicle: '中间载体穿透',
  trust_vehicle_lookthrough: '信托载体穿透',
}

const STATUS_LABELS = {
  actual_controller_identified: '已识别实际控制人',
  no_actual_controller_but_leading_candidate_found: '未形成唯一实际控制人',
  joint_control_identified: '共同控制，未形成唯一实际控制人',
  no_meaningful_controller_signal: '未形成明显控制信号',
}

const COUNTRY_INFERENCE_REASON_LABELS = {
  derived_from_direct_controller: '根据直接控制人所在国家/地区确定。',
  derived_from_ultimate_controller: '根据 ultimate / actual controller 所在国家/地区确定。',
  fallback_to_incorporation: '当前未形成唯一实际控制人，按注册地兜底。',
  joint_control_no_single_country: '存在共同控制，暂不输出单一控制国家/地区。',
}

const COUNTRY_INFERENCE_REASON_HEADLINES = {
  derived_from_direct_controller: '根据直接控制人归属确定',
  derived_from_ultimate_controller: '根据最终控制人归属确定',
  fallback_to_incorporation: '当前按注册地兜底',
  joint_control_no_single_country: '共同控制，暂不输出单一归属',
}

function normalizeKey(value) {
  return String(value ?? '').trim().toLowerCase()
}

function firstNonEmpty(...values) {
  return values.find((value) => String(value ?? '').trim() !== '') ?? null
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

function entityTypeLabel(value) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return '暂无'
  }
  return ENTITY_TYPE_LABELS[normalized] || '其他主体'
}

function controlTypeLabel(value) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return '暂无'
  }
  return CONTROL_TYPE_LABELS[normalized] || String(value)
}

function attributionTypeLabel(value) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return '暂无'
  }
  return ATTRIBUTION_TYPE_LABELS[normalized] || String(value)
}

function attributionLayerLabel(value) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return '暂无'
  }
  return ATTRIBUTION_LAYER_LABELS[normalized] || String(value)
}

function controlModeLabel(value) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return '暂无'
  }
  return CONTROL_MODE_LABELS[normalized] || String(value)
}

function reasonLabel(value, dictionary) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return '暂无'
  }
  return dictionary[normalized] || String(value)
}

function truncateText(value, maxLength = 120) {
  const normalized = String(value ?? '').replace(/\s+/g, ' ').trim()
  if (normalized.length <= maxLength) {
    return normalized
  }
  return `${normalized.slice(0, maxLength - 1)}…`
}

function isPublicFloatController(controller) {
  const name = normalizeKey(controller?.controller_name)
  return (
    name.includes('public float') ||
    name.includes('public holding') ||
    name.includes('dispersed ownership') ||
    name.includes('dispersed holding')
  )
}

function hasController(controller) {
  return Boolean(firstNonEmpty(controller?.controller_name, controller?.controller_entity_id))
}

function controllerFallbackLabel(role) {
  if (role === 'direct') {
    return '暂无明确直接控制人'
  }
  if (role === 'actual') {
    return '未形成唯一实际控制人'
  }
  if (role === 'leading') {
    return '未保留领先候选主体'
  }
  return '暂无'
}

function controllerName(controller, role = '') {
  if (!hasController(controller)) {
    return controllerFallbackLabel(role)
  }
  return controller?.controller_name || `主体 ${controller.controller_entity_id}`
}

function formatRatio(value) {
  if (value === null || value === undefined || value === '') {
    return ''
  }

  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return String(value)
  }

  const normalized = numeric <= 1 ? numeric * 100 : numeric
  return `${normalized.toFixed(2)}%`
}

function sameController(left, right) {
  const leftId = getEntityId(left)
  const rightId = getEntityId(right)
  if (leftId && rightId) {
    return leftId === rightId
  }
  return Boolean(
    left?.controller_name &&
      right?.controller_name &&
      normalizeKey(left.controller_name) === normalizeKey(right.controller_name),
  )
}

function controllerTypeText(controller) {
  if (isPublicFloatController(controller)) {
    return '公众持股 / 分散流通股'
  }
  return entityTypeLabel(controller?.controller_type)
}

function controlStrengthSourceLabel(controller) {
  const basis = parseMaybeJson(controller?.basis) || {}
  return (
    controller?.manual_display_control_strength_source_label ||
    basis.manual_display_control_strength_source_label ||
    ''
  )
}

function controllerControlStrengthText(controller, role = '') {
  const ratioText = formatRatio(controller?.control_ratio)
  if (!ratioText) {
    return ''
  }

  if (role === 'actual' && manualControllerEffective.value) {
    const sourceLabel = controlStrengthSourceLabel(controller) || manualSourceLabel.value || '人工征订'
    return `${ratioText}（${sourceLabel}）`
  }

  return ratioText
}

function controllerMeta(controller, role = '') {
  if (!hasController(controller)) {
    if (role === 'actual' && hasController(leadingCandidate.value)) {
      return '后端未输出唯一 actual controller，可参考 Leading Candidate'
    }
    return '当前结果集中未返回该层级主体'
  }

  const items = [
    controllerTypeText(controller),
    controlTypeLabel(controller?.control_type),
    controllerControlStrengthText(controller, role),
  ]
    .filter((item) => item && item !== '暂无')

  if (role === 'actual' && sameController(controller, directController.value)) {
    items.push('Direct = Ultimate')
  }
  if (role === 'leading' && sameController(controller, actualController.value)) {
    items.push('与实际控制人一致')
  }
  if (isPublicFloatController(controller)) {
    items.push('Public Float')
  }

  return items.join(' / ') || '当前层级主体信息不完整'
}

function getEntityId(controller) {
  return controller?.controller_entity_id === null || controller?.controller_entity_id === undefined
    ? null
    : String(controller.controller_entity_id)
}

const displayController = computed(
  () =>
    props.controlAnalysis?.display_controller ||
    props.controlAnalysis?.actual_controller ||
    props.controlAnalysis?.leading_candidate ||
    null,
)
const directController = computed(() => props.controlAnalysis?.direct_controller || null)
const actualController = computed(() => props.controlAnalysis?.actual_controller || null)
const leadingCandidate = computed(() => props.controlAnalysis?.leading_candidate || null)
const preferredController = computed(
  () => actualController.value || directController.value || leadingCandidate.value || displayController.value,
)
const hasActualController = computed(() => hasController(actualController.value))
const countryBasis = computed(() => parseMaybeJson(props.countryAttribution?.basis) || {})
const promotionReasonFromBasis = computed(() => {
  const reasonMap = countryBasis.value?.promotion_reason_by_entity_id
  if (!reasonMap || typeof reasonMap !== 'object') {
    return null
  }

  const candidateIds = [
    getEntityId(actualController.value),
    getEntityId(directController.value),
    getEntityId(leadingCandidate.value),
  ].filter(Boolean)

  for (const entityId of candidateIds) {
    if (reasonMap[entityId]) {
      return reasonMap[entityId]
    }
  }

  return null
})
const promotionReason = computed(() =>
  firstNonEmpty(
    actualController.value?.promotion_reason,
    directController.value?.promotion_reason,
    leadingCandidate.value?.promotion_reason,
    promotionReasonFromBasis.value,
  ),
)
const terminalFailureReason = computed(() =>
  firstNonEmpty(
    leadingCandidate.value?.terminal_failure_reason,
    directController.value?.terminal_failure_reason,
    actualController.value?.terminal_failure_reason,
    countryBasis.value?.terminal_failure_reason,
  ),
)
const controlType = computed(
  () => controlTypeLabel(preferredController.value?.control_type),
)
const controlMode = computed(
  () => controlModeLabel(preferredController.value?.control_mode),
)
const attributionType = computed(
  () => attributionTypeLabel(props.countryAttribution?.attribution_type),
)
const attributionLayer = computed(
  () => attributionLayerLabel(props.countryAttribution?.attribution_layer),
)
const actualControlCountry = computed(
  () => props.countryAttribution?.actual_control_country || '未识别',
)
const manualControllerEffective = computed(() => Boolean(props.controlAnalysis?.is_manual_effective))
const manualCountryEffective = computed(() => Boolean(props.countryAttribution?.is_manual_effective))
const manualEffective = computed(() => manualControllerEffective.value || manualCountryEffective.value)
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
  return ''
})
const automaticActualControllerName = computed(
  () =>
    manualOverride.value?.automatic_control_snapshot?.actual_controller?.controller_name ||
    props.countryAttribution?.basis?.automatic_actual_controller_name ||
    '',
)
const automaticActualControlCountry = computed(
  () =>
    manualOverride.value?.automatic_country_snapshot?.actual_control_country ||
    props.countryAttribution?.automatic_country_attribution?.actual_control_country ||
    '',
)
const controlRelationshipCount = computed(
  () =>
    props.controlAnalysis?.controller_count ??
    props.controlAnalysis?.control_relationships?.length ??
    0,
)
const hasControlData = computed(() => controlRelationshipCount.value > 0)
const controlRelationshipNote = computed(() =>
  hasControlData.value
    ? '当前用于控制识别与路径解释的关系记录。'
    : '当前接口未返回控制关系记录。',
)
const recognitionStatusCode = computed(
  () =>
    props.controlAnalysis?.identification_status ||
    props.controlAnalysis?.controller_status ||
    countryBasis.value?.controller_status ||
    '',
)
const recognitionStatus = computed(() => {
  if (manualControllerEffective.value) {
    return `${manualSourceLabel.value || '人工征订'}确定实际控制结论`
  }
  if (isFallbackIncorporation.value && !hasActualController.value) {
    return '当前按注册地兜底归属'
  }
  return STATUS_LABELS[recognitionStatusCode.value] || '未形成明确控制结论'
})
const lookThroughApplied = computed(() => props.countryAttribution?.look_through_applied === true)
const lookThroughHeadline = computed(() => (lookThroughApplied.value ? '已应用穿透' : '未应用穿透'))
const lookThroughDetail = computed(() => {
  if (!lookThroughApplied.value) {
    return '当前未继续向上穿透识别，归属结论保留在现有控制层级。'
  }
  const shortReason = promotionReason.value
    ? reasonLabel(promotionReason.value, PROMOTION_REASON_SHORT_LABELS)
    : '上层控制链'
  return `已结合${shortReason}进行穿透判断。`
})
const isFallbackIncorporation = computed(
  () =>
    normalizeKey(props.countryAttribution?.attribution_type) === 'fallback_incorporation' ||
    normalizeKey(props.countryAttribution?.attribution_layer) === 'fallback_incorporation',
)
const fallbackExplanation = computed(() => {
  if (!isFallbackIncorporation.value || hasActualController.value) {
    return ''
  }

  const incorporationCountry = props.company?.incorporation_country || '公司注册地'
  return `未识别出唯一实际控制人，当前按 ${incorporationCountry} 进行注册地兜底归属；这不是已确认 actual controller 后的强归属结论。`
})
const promotionReasonExplanation = computed(() =>
  promotionReason.value
    ? reasonLabel(promotionReason.value, PROMOTION_REASON_LABELS)
    : lookThroughApplied.value
      ? '本次已应用穿透，但接口未返回单独的上卷原因。'
      : hasActualController.value
        ? '本次未触发上卷判定，当前结论无需继续上卷。'
        : '未应用上卷提升，当前停留在候选主体或保守归属层级。',
)
const countryInferenceReasonCode = computed(
  () => props.countryAttribution?.country_inference_reason || countryBasis.value?.country_inference_reason || '',
)
const countryInferenceReasonExplanation = computed(() => {
  if (!countryInferenceReasonCode.value) {
    return ''
  }
  const normalized = normalizeKey(countryInferenceReasonCode.value)
  return COUNTRY_INFERENCE_REASON_LABELS[normalized] || '根据当前控制分析结果综合确定。'
})

const actualControlCountryNote = computed(() => {
  if (manualCountryEffective.value) {
    return '当前国别归属优先采用人工征订/确认结果。'
  }
  if (isFallbackIncorporation.value && !hasActualController.value) {
    return '当前为注册地兜底归属。'
  }
  return '当前控制分析输出的国家/地区归属。'
})
const attributionLayerNote = computed(() => {
  const layer = normalizeKey(props.countryAttribution?.attribution_layer)
  if (layer === 'ultimate_controller_country') {
    return '归属已上卷至最终控制人层。'
  }
  if (layer === 'direct_controller_country') {
    return '归属停留在直接控制人层。'
  }
  if (layer === 'fallback_incorporation') {
    return '未形成唯一控制人时采用的保守层级。'
  }
  if (layer === 'joint_control_undetermined') {
    return '共同控制场景下暂不输出单一层级。'
  }
  return '说明当前归属结论落在哪一层。'
})
const attributionTypeNote = computed(() => {
  if (manualCountryEffective.value) {
    return '依据方式为人工征订/确认，非算法自动识别结果。'
  }
  const type = normalizeKey(props.countryAttribution?.attribution_type)
  if (type === 'fallback_incorporation') {
    return '兜底归属，不等同于已确认实际控制人。'
  }
  if (type.includes('agreement')) {
    return '以协议或治理安排作为主要依据。'
  }
  if (type.includes('mixed')) {
    return '综合股权与非股权控制线索。'
  }
  if (type.includes('joint')) {
    return '共同控制边界下的归属结果。'
  }
  return '对应当前主版本的归属判断口径。'
})
const controlTypeNote = computed(() => {
  const type = normalizeKey(preferredController.value?.control_type)
  if (type.includes('equity')) {
    return '主要依据股权或持股路径。'
  }
  if (type.includes('agreement') || type.includes('board') || type.includes('voting')) {
    return '主要依据协议、席位或表决权安排。'
  }
  if (type.includes('mixed')) {
    return '综合数值比例与治理控制线索。'
  }
  return '描述当前控制来源的主要口径。'
})
const controlModeNote = computed(() => {
  const mode = normalizeKey(preferredController.value?.control_mode)
  if (mode === 'numeric') {
    return '主要根据比例与路径分数计算。'
  }
  if (mode === 'semantic') {
    return '主要根据协议、治理等语义线索判断。'
  }
  if (mode === 'mixed') {
    return '综合比例与语义控制线索。'
  }
  return '说明当前判定采用的计算模式。'
})

function evidenceSignals(value) {
  const normalized = normalizeKey(value)
  if (normalized.includes('fallback to incorporation')) {
    return ['当前未达到唯一控制人阈值，归属结论采用注册地兜底。']
  }
  if (normalized.includes('joint control prevents unique attribution')) {
    return ['存在共同控制，暂不强行归为单一实际控制人。']
  }

  const signals = []
  if (normalized.includes('direct equity ownership') && normalized.includes('residual free float')) {
    signals.push('直接股权控制', '公众流通股 / 分散持股集合')
  } else if (normalized.includes('direct equity ownership')) {
    signals.push('直接股权控制')
  } else if (normalized.includes('residual free float')) {
    signals.push('公众流通股 / 分散持股集合')
  }

  if (normalized.includes('shareholder agreement') || normalized.includes('agreement')) {
    signals.push('股东协议控制')
  }
  if (
    normalized.includes('board nomination') ||
    normalized.includes('appoint majority') ||
    normalized.includes('nominate majority') ||
    normalized.includes('directors')
  ) {
    signals.push('董事会席位或任命权')
  }
  if (
    normalized.includes('budget') ||
    normalized.includes('operating policies') ||
    normalized.includes('strategic') ||
    normalized.includes('key decisions')
  ) {
    signals.push('关键经营决策主导权')
  }
  if (normalized.includes('intermediate spv') || normalized.includes('holding company')) {
    signals.push('中间控股平台 / SPV 载体')
  }
  if (normalized.includes('upstream should be ultimate')) {
    signals.push('上层主体具备最终控制人信号')
  }
  if (normalized.includes('upstream of non-equity controller')) {
    signals.push('上游非股权控制链')
  }
  if (normalized.includes('voting')) {
    signals.push('表决权安排')
  }
  if (normalized.includes('vie')) {
    signals.push('VIE 控制结构')
  }
  if (normalized.includes('nominee')) {
    signals.push('名义持有 / 代持线索')
  }

  return signals
}

function evidenceText(value) {
  const signals = evidenceSignals(value)
  if (signals.length > 0) {
    return [...new Set(signals)].join('、')
  }
  return truncateText(String(value ?? '').replace(/\s+\|\s+/g, '；'), 80)
}

const evidenceSummary = computed(() => {
  const items = Array.isArray(countryBasis.value?.evidence_summary)
    ? countryBasis.value.evidence_summary
    : []
  const mapped = [...new Set(items.map(evidenceText).filter(Boolean))]
  if (mapped.length === 0) {
    return ''
  }

  const summary = mapped.slice(0, 2).join('、')
  if (/[。！？]$/.test(summary)) {
    return summary
  }
  return `主要依据为${summary}。`
})

const recognitionSubtext = computed(() => {
  if (manualControllerEffective.value) {
    const autoText = automaticActualControllerName.value
      ? `自动分析结果为 ${automaticActualControllerName.value}。`
      : '自动分析未形成可展示的实际控制人。'
    if (manualSourceLabel.value === '人工判定') {
      return `当前实际控制人为人工判定确定，基于现有候选主体选择，非算法自动形成唯一控制人。${autoText}`
    }
    return `当前实际控制人为人工征订确定，非算法自动识别结果。${autoText}`
  }
  if (hasActualController.value) {
    return '未发现关键阻断因素，已形成唯一控制结论。'
  }
  if (isFallbackIncorporation.value) {
    return '未识别出唯一实际控制人，当前采用注册地兜底归属。'
  }
  if (normalizeKey(recognitionStatusCode.value) === 'joint_control_identified') {
    return '存在共同控制，暂不强行选择单一控制人。'
  }
  if (hasController(leadingCandidate.value)) {
    return '未形成唯一实际控制人，保留领先候选主体。'
  }
  return '当前控制信号不足，页面展示保守判定边界。'
})

const promotionHeadline = computed(() => {
  if (promotionReason.value || lookThroughApplied.value) {
    return '已采用上卷判断'
  }
  if (hasActualController.value) {
    return '无需继续上卷'
  }
  return '未采用上卷提升'
})

const attributionBasisHeadline = computed(() => {
  if (manualCountryEffective.value) {
    return `${manualSourceLabel.value || '人工征订'}结果优先生效`
  }
  const normalized = normalizeKey(countryInferenceReasonCode.value)
  if (normalized && COUNTRY_INFERENCE_REASON_HEADLINES[normalized]) {
    return COUNTRY_INFERENCE_REASON_HEADLINES[normalized]
  }
  if (isFallbackIncorporation.value) {
    return '当前按注册地兜底'
  }
  if (hasActualController.value) {
    return '根据控制人归属确定'
  }
  return '根据控制分析结果确定'
})

const attributionBasisSubtext = computed(
  () => {
    if (manualCountryEffective.value) {
      const parts = [
        `本次征订依据：${manualOverride.value?.evidence || props.countryAttribution?.manual_evidence || '未填写'}`,
        `本次征订说明：${manualOverride.value?.reason || props.countryAttribution?.manual_reason || '未填写'}`,
      ]
      if (automaticActualControlCountry.value) {
        parts.push(`自动分析国别为 ${automaticActualControlCountry.value}`)
      }
      return parts.join('；')
    }
    return countryInferenceReasonExplanation.value || '当前接口未返回单独归属依据，页面根据控制分析结果展示。'
  },
)

const evidenceHeadline = computed(() => {
  if (manualCountryEffective.value) {
    return '人工征订依据生效'
  }
  if (isFallbackIncorporation.value && !hasActualController.value) {
    return '证据不足以确认唯一控制人'
  }
  if (terminalFailureReason.value) {
    return '阻断因素主导当前结论'
  }
  if (lookThroughApplied.value) {
    return '上层控制与穿透线索支持当前判断'
  }
  if (hasActualController.value) {
    return '控制线索支持当前判断'
  }
  if (hasController(leadingCandidate.value)) {
    return '已保留领先候选线索'
  }
  return '暂无明确证据摘要'
})

const evidenceSubtext = computed(
  () =>
    manualEffective.value
      ? manualOverride.value?.evidence || props.countryAttribution?.manual_evidence || '本次人工征订未填写单独依据。'
      : evidenceSummary.value || '当前接口未返回可摘要化证据。',
)

const dataStatusLine = computed(() =>
  hasControlData.value
    ? `数据状态：${controlRelationshipCount.value} 条控制关系记录可用于判定。`
    : '数据状态：当前未返回可用于判定的控制关系记录。',
)

const explanationItems = computed(() => [
  {
    key: 'recognition',
    label: '识别结论',
    headline: recognitionStatus.value,
    subtext: recognitionSubtext.value,
  },
  {
    key: 'path',
    label: '判定路径',
    headline: promotionHeadline.value,
    subtext: promotionReasonExplanation.value,
  },
  {
    key: 'attribution',
    label: '归属依据',
    headline: attributionBasisHeadline.value,
    subtext: attributionBasisSubtext.value,
  },
  {
    key: 'evidence',
    label: '证据摘要',
    headline: evidenceHeadline.value,
    subtext: evidenceSubtext.value,
    clamp: true,
  },
])
</script>

<template>
  <el-card class="surface-card" shadow="never">
    <template #header>
      <div class="section-heading">
        <div>
          <div class="control-summary-title-row">
            <h3>控制链与国别归属</h3>
            <span v-if="manualEffective" class="manual-source-badge">
              {{ manualSourceLabel || '人工征订' }}
            </span>
          </div>
          <p>上半区域展示控制结构图，下半区域展示控制分析摘要与国别归属结论。</p>
        </div>
      </div>
    </template>

    <div class="control-summary-grid">
      <div class="control-summary-card">
        <div class="control-summary-card__title">控制层级摘要</div>
        <div v-if="manualControllerEffective" class="manual-summary-note">
          当前实际控制人为人工征订确定，非算法自动识别结果。
        </div>
        <div v-else-if="manualCountryEffective" class="manual-summary-note">
          当前国别归属由人工征订确定，实际控制人仍按当前控制分析展示。
        </div>
        <dl class="compact-facts">
          <div>
            <dt>Direct Controller</dt>
            <dd>
              <strong>{{ controllerName(directController, 'direct') }}</strong>
              <span>{{ controllerMeta(directController, 'direct') }}</span>
            </dd>
          </div>
          <div>
            <dt>Ultimate / Actual</dt>
            <dd>
              <strong>{{ controllerName(actualController, 'actual') }}</strong>
              <span>{{ controllerMeta(actualController, 'actual') }}</span>
            </dd>
          </div>
          <div>
            <dt>Leading Candidate</dt>
            <dd>
              <strong>{{ controllerName(leadingCandidate, 'leading') }}</strong>
              <span>{{ controllerMeta(leadingCandidate, 'leading') }}</span>
            </dd>
          </div>
          <div>
            <dt>控制关系数量</dt>
            <dd>
              <strong>{{ controlRelationshipCount }}</strong>
              <span>{{ controlRelationshipNote }}</span>
            </dd>
          </div>
        </dl>
      </div>

      <div class="control-summary-card">
        <div class="control-summary-card__title">归属与控制口径</div>
        <dl class="compact-facts">
          <div>
            <dt>归属国家/地区</dt>
            <dd>
              <strong>{{ actualControlCountry }}</strong>
              <span>{{ actualControlCountryNote }}</span>
            </dd>
          </div>
          <div>
            <dt>归属层级</dt>
            <dd>
              <strong>{{ attributionLayer }}</strong>
              <span>{{ attributionLayerNote }}</span>
            </dd>
          </div>
          <div>
            <dt>归属类型</dt>
            <dd>
              <strong>{{ attributionType }}</strong>
              <span>{{ attributionTypeNote }}</span>
            </dd>
          </div>
          <div>
            <dt>控制口径</dt>
            <dd>
              <strong>{{ controlType }}</strong>
              <span>{{ controlTypeNote }}</span>
            </dd>
          </div>
          <div>
            <dt>控制模式</dt>
            <dd>
              <strong>{{ controlMode }}</strong>
              <span>{{ controlModeNote }}</span>
            </dd>
          </div>
          <div>
            <dt>上层穿透</dt>
            <dd>
              <strong>{{ lookThroughHeadline }}</strong>
              <span>{{ lookThroughDetail }}</span>
            </dd>
          </div>
        </dl>
      </div>

      <div class="control-summary-card control-summary-card--emphasis">
        <div class="control-summary-card__title">判定解释</div>
        <dl class="compact-facts compact-facts--explanation">
          <div
            v-for="item in explanationItems"
            :key="item.key"
            class="explanation-summary-item"
          >
            <dt>{{ item.label }}</dt>
            <dd>
              <strong>{{ item.headline }}</strong>
              <span
                :class="{ 'explanation-summary-item__subtext--clamped': item.clamp }"
                :title="item.subtext"
              >
                {{ item.subtext }}
              </span>
            </dd>
          </div>
        </dl>
        <p class="control-summary-card__footnote">{{ dataStatusLine }}</p>
      </div>
    </div>

    <el-alert
      v-if="fallbackExplanation"
      class="control-summary-explanation"
      type="warning"
      :closable="false"
      show-icon
      title="注册地兜底归属"
      :description="fallbackExplanation"
    />

    <el-alert
      v-if="manualEffective"
      class="control-summary-explanation"
      type="warning"
      :closable="false"
      show-icon
      :title="manualControllerEffective ? `${manualSourceLabel || '人工征订'}确定实际控制人` : `${manualSourceLabel || '人工征订'}确定国别归属`"
      :description="manualControllerEffective
        ? `当前生效结论由${manualSourceLabel || '人工征订'}确定；自动分析结果为 ${automaticActualControllerName || '未形成实际控制人'}，自动国别为 ${automaticActualControlCountry || '未识别'}。`
        : `当前国别归属由${manualSourceLabel || '人工征订'}确定；自动国别为 ${automaticActualControlCountry || '未识别'}。`"
    />

    <ControlStructureDiagram
      v-if="ENABLE_REBUILT_CONTROL_STRUCTURE_DIAGRAM"
      :company="company"
      :control-analysis="controlAnalysis"
      :country-attribution="countryAttribution"
      :relationship-graph="relationshipGraph"
    />
    <ControlStructurePlaceholder v-else />
  </el-card>
</template>

<style scoped>
.control-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.control-summary-title-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.control-summary-title-row h2 {
  margin: 0;
}

.manual-source-badge {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 4px 10px;
  border-radius: 8px;
  border: 1px solid rgba(155, 58, 58, 0.24);
  color: #9b3a3a;
  background: rgba(155, 58, 58, 0.1);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.control-summary-card {
  padding: 16px;
  border-radius: 8px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(249, 251, 254, 0.92);
}

.control-summary-card--emphasis {
  background:
    linear-gradient(135deg, rgba(255, 252, 247, 0.96), rgba(245, 249, 252, 0.94));
  border-color: rgba(139, 106, 61, 0.16);
}

.control-summary-card__title {
  margin-bottom: 12px;
  color: var(--brand-ink);
  font-weight: 700;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.manual-summary-note {
  margin: -4px 0 12px;
  color: #9b3a3a;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.5;
}

.compact-facts {
  --summary-label-width: 96px;
  --summary-column-gap: 10px;
  --summary-item-gap: 11px;
  --summary-label-size: 12px;
  --summary-value-size: 14px;
  --summary-note-size: 12px;
  display: grid;
  gap: var(--summary-item-gap);
  margin: 0;
}

.compact-facts > div {
  display: grid;
  grid-template-columns: var(--summary-label-width) minmax(0, 1fr);
  gap: var(--summary-column-gap);
  align-items: start;
}

.compact-facts dt {
  color: var(--text-secondary);
  font-size: var(--summary-label-size);
  font-weight: 600;
  line-height: 1.4;
  padding-top: 2px;
}

.compact-facts dd {
  margin: 0;
  color: var(--brand-ink);
  font-size: var(--summary-value-size);
  font-weight: 700;
  line-height: 1.4;
  word-break: break-word;
}

.compact-facts dd strong,
.compact-facts dd span {
  display: block;
}

.compact-facts dd strong {
  color: inherit;
  font-size: inherit;
  font-weight: inherit;
  line-height: inherit;
}

.compact-facts dd span {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: var(--summary-note-size);
  font-weight: 500;
  line-height: 1.5;
}

.compact-facts--explanation dd span {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.explanation-summary-item__subtext--clamped {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.control-summary-card__footnote {
  margin: 10px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.45;
}

.control-summary-explanation {
  margin-top: 14px;
}

.control-graph-wide {
  margin-top: 18px;
}

@media (max-width: 1100px) {
  .control-summary-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .compact-facts > div {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>


