<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import ControlStructurePlaceholder from '@/components/ControlStructurePlaceholder.vue'
import { buildControlStructureModel } from '@/utils/controlStructureAdapter'
import { computeControlStructureLayout } from '@/utils/controlStructureLayout'

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
      nodes: [],
      edges: [],
    }),
  },
})

const stageRef = ref(null)
const hoverCard = ref(null)
const expandedByNodeId = reactive({})
const viewportSize = reactive({
  width: 0,
  height: 0,
})
const viewportTransform = reactive({
  x: 0,
  y: 0,
  scale: 1,
  userAdjusted: false,
})
const panState = reactive({
  active: false,
  pointerId: null,
  startX: 0,
  startY: 0,
  originX: 0,
  originY: 0,
})

const MIN_ZOOM = 0.32
const MAX_ZOOM = 2.6
const FIT_PADDING = 0.92
let resizeObserver = null

const ENTITY_TYPE_LABELS = {
  company: '公司主体',
  person: '自然人',
  fund: '基金 / 公众持股集合',
  institution: '机构投资者',
  government: '政府 / 国资主体',
  other: '其他主体',
}

const RELATION_TYPE_LABELS = {
  equity: '股权控制',
  agreement: '协议控制',
  agreement_control: '协议控制',
  board_control: '董事会 / 席位控制',
  voting_right: '表决权安排',
  nominee: '代持 / 名义持有人',
  vie: 'VIE 结构',
  vie_control: 'VIE 结构',
  mixed_control: '混合控制',
  joint_control: '共同控制',
}

const DISPLAY_MODE_LABELS = {
  'progressive-expand': '分层展开',
  'summary-first': '摘要优先',
}

const displayController = computed(
  () =>
    props.controlAnalysis?.display_controller ||
    props.controlAnalysis?.actual_controller ||
    props.controlAnalysis?.leading_candidate ||
    null,
)

const controlRelationships = computed(() =>
  Array.isArray(props.controlAnalysis?.control_relationships)
    ? props.controlAnalysis.control_relationships
    : [],
)
const actualControllerFromRows = computed(() =>
  controlRelationships.value.find(
    (relationship) =>
      isTruthy(relationship?.is_actual_controller) && !isOwnershipPatternRelationship(relationship),
  ) || null,
)
const hasConfirmedActualAxis = computed(() =>
  Boolean(
    (!isOwnershipPatternRelationship(props.controlAnalysis?.actual_controller) &&
      (props.controlAnalysis?.actual_controller?.controller_entity_id ||
        props.controlAnalysis?.actual_controller?.controller_name)) ||
      actualControllerFromRows.value?.controller_entity_id ||
      actualControllerFromRows.value?.controller_name,
  ),
)
const countryBasis = computed(() => parseMaybeJson(props.countryAttribution?.basis) || {})

function isOwnershipPatternRelationship(relationship) {
  if (!relationship) {
    return false
  }

  const terminalIdentifiability = normalizeKey(firstAvailable(relationship, 'terminal_identifiability'))
  const terminalSuitability = normalizeKey(firstAvailable(relationship, 'terminal_suitability'))
  const terminalFailureReason = normalizeKey(firstAvailable(relationship, 'terminal_failure_reason'))
  const selectionReason = normalizeKey(firstAvailable(relationship, 'selection_reason'))

  return (
    isTruthy(firstAvailable(relationship, 'ownership_pattern_signal')) ||
    terminalIdentifiability === 'aggregation_like' ||
    terminalSuitability === 'pattern_only' ||
    terminalFailureReason === 'ownership_aggregation_pattern' ||
    selectionReason === 'excluded_from_actual_race_due_to_terminal_profile'
  )
}

const structuralAxisRelationship = computed(() => {
  if (hasConfirmedActualAxis.value) {
    return null
  }

  const candidates = [
    props.controlAnalysis?.display_controller,
    props.controlAnalysis?.leading_candidate,
    controlRelationships.value[0],
    displayController.value,
  ].filter(Boolean)

  return candidates.find((relationship) => isOwnershipPatternRelationship(relationship)) || null
})
const isOwnershipAggregationFallback = computed(() => {
  const terminalFailureReason = normalizeKey(
    props.controlAnalysis?.terminal_failure_reason ||
      countryBasis.value?.terminal_failure_reason ||
      props.countryAttribution?.terminal_failure_reason,
  )
  const countryInferenceReason = normalizeKey(props.countryAttribution?.country_inference_reason)
  const attributionType = normalizeKey(props.countryAttribution?.attribution_type)

  return (
    !hasConfirmedActualAxis.value &&
    (terminalFailureReason === 'ownership_aggregation_pattern' ||
      countryInferenceReason === 'fallback_no_identifiable_terminal_controller' ||
      (attributionType === 'fallback_incorporation' &&
        normalizeKey(countryBasis.value?.controller_status) === 'no_identifiable_terminal_controller'))
  )
})
const isStructuralAxis = computed(() =>
  Boolean(structuralAxisRelationship.value || isOwnershipAggregationFallback.value),
)
const summaryControllerRoleKey = computed(() => {
  if (isStructuralAxis.value) {
    return 'structural_signal'
  }
  if (props.controlAnalysis?.display_controller_role) {
    return props.controlAnalysis.display_controller_role
  }
  if (props.controlAnalysis?.actual_controller || displayController.value?.is_actual_controller) {
    return 'actual_controller'
  }
  if (props.controlAnalysis?.leading_candidate || displayController.value) {
    return 'leading_candidate'
  }
  return null
})
const summaryControllerRoleLabel = computed(() => {
  if (summaryControllerRoleKey.value === 'structural_signal') {
    return '结构信号主轴'
  }
  if (summaryControllerRoleKey.value === 'leading_candidate') {
    return '重点控制候选'
  }
  return '实际控制人'
})
const summaryControllerLegendTitle = computed(() => {
  if (summaryControllerRoleKey.value === 'structural_signal') {
    return '结构信号主轴'
  }
  if (summaryControllerRoleKey.value === 'leading_candidate') {
    return '重点控制候选'
  }
  if (summaryControllerRoleKey.value === 'actual_controller') {
    return '实际控制人'
  }
  return '顶部主轴控制主体'
})
const summaryControllerLegendDescription = computed(() => {
  if (summaryControllerRoleKey.value === 'structural_signal') {
    return '未识别唯一实际控制人时保留的研究展示主轴；用于解释 ownership aggregation / 分散持股结构，不等同于 actual controller。'
  }
  if (summaryControllerRoleKey.value === 'leading_candidate') {
    return '未形成唯一实际控制人时保留的 leading candidate；不等同于 actual controller，如有上游结构可继续展开。'
  }
  if (summaryControllerRoleKey.value === 'actual_controller') {
    return '当前识别到的 ultimate / actual controller；如存在上游结构，可继续向上展开。'
  }
  return '当前未识别到唯一实际控制人或领先候选主体时，顶部主轴不渲染控制主体节点。'
})
const diagramHeaderDescription = computed(() => {
  if (summaryControllerRoleKey.value === 'structural_signal') {
    return '当前顶部主轴仅表示研究展示路径 / ownership aggregation path；它不代表已确认实际控制主体，目标公司国别结论仍按后端 fallback 口径解释。'
  }
  if (summaryControllerRoleKey.value === 'leading_candidate') {
    return '主链保持“Leading Candidate → 中间层 → 目标公司”的向下语义；目标公司下方仅保留非主链路的并列上游主体。'
  }
  if (summaryControllerRoleKey.value === 'actual_controller') {
    return '主链保持“Ultimate / Actual Controller → 中间层 → 目标公司”的向下语义；若存在中间控股平台，会在主轴上逐层显示。'
  }
  return '未识别到唯一实际控制人或领先候选主体时，图中保留目标公司及其上游结构，避免出现误导性的顶部控制主体节点。'
})
const diagramFootnote = computed(() => {
  if (summaryControllerRoleKey.value === 'structural_signal') {
    return '顶部主轴节点为结构信号 / 研究主轴，连线以虚线弱化显示；它用于解释公众持股或分散持股聚合路径，不表示已确认实际控制。'
  }
  if (summaryControllerRoleKey.value === 'leading_candidate') {
    return '顶部主轴节点显示为领先候选主体，主链路中间层会沿中轴逐层展开；目标公司下方仅展示非主链路的并列上游主体。'
  }
  if (summaryControllerRoleKey.value === 'actual_controller') {
    return '顶部主轴节点显示为 ultimate / actual controller，中间控股平台会保留在主轴上，避免把多层控制链误读为直接控制。'
  }
  return '当前未识别到顶部主轴控制主体，图中仅展示目标公司及其上游结构。可滚轮缩放、拖拽平移，并用“适应视图”恢复居中。'
})
const interactionHint = computed(() => {
  if (summaryControllerRoleKey.value === 'structural_signal') {
    return '顶部结构信号主轴仅用于研究解释；可展开节点查看其上游结构，但不要将其理解为 actual controller。'
  }
  if (summaryControllerRoleKey.value === 'leading_candidate') {
    return '目标公司下方节点可向下展开；顶部领先候选如存在上游结构，可继续向上展开。'
  }
  if (summaryControllerRoleKey.value === 'actual_controller') {
    return '目标公司下方节点可向下展开；顶部实际控制人如存在上游结构，可继续向上展开。'
  }
  return '当前仅展示目标公司及其上游结构，可继续展开下方上游节点。'
})
const summaryLegendRoleClass = computed(() => {
  if (!summaryControllerRoleKey.value) {
    return 'legend-role--inactive'
  }
  if (summaryControllerRoleKey.value === 'structural_signal') {
    return 'legend-role--structural'
  }
  return summaryControllerRoleKey.value === 'leading_candidate' ? 'legend-role--leading' : 'legend-role--actual'
})

const diagramModel = computed(() =>
  buildControlStructureModel({
    company: props.company,
    controlAnalysis: props.controlAnalysis,
    countryAttribution: props.countryAttribution,
    relationshipGraph: props.relationshipGraph,
  }),
)

watch(
  () => diagramModel.value?.expansionSeed,
  () => {
    Object.keys(expandedByNodeId).forEach((key) => {
      delete expandedByNodeId[key]
    })

    const defaults = Array.isArray(diagramModel.value?.defaultExpandedNodeIds)
      ? diagramModel.value.defaultExpandedNodeIds
      : []
    defaults.forEach((nodeId) => {
      expandedByNodeId[String(nodeId)] = true
    })
    viewportTransform.userAdjusted = false
    nextTick(() => fitView())
  },
  { immediate: true },
)

const diagramState = computed(() => {
  try {
    const model = diagramModel.value

    if (!model?.hasDiagram) {
      const reason = model?.placeholderDescription || 'control structure data is missing'
      return {
        error: reason,
        model,
        layout: null,
      }
    }

    const layout = computeControlStructureLayout(model, expandedByNodeId)
    if (!layout?.nodes?.length) {
      return {
        error: 'layout returned no renderable nodes',
        model,
        layout: null,
      }
    }

    return {
      error: '',
      model,
      layout,
    }
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : String(error),
      model: null,
      layout: null,
    }
  }
})

const diagramLayout = computed(() => diagramState.value.layout)
const shouldFallback = computed(() => Boolean(diagramState.value.error || !diagramLayout.value))
const pathConvergenceItems = computed(() =>
  Array.isArray(diagramModel.value?.multiPathConvergences)
    ? diagramModel.value.multiPathConvergences
    : [],
)
const primaryPathConvergence = computed(() => pathConvergenceItems.value[0] || null)

const viewportWidth = computed(() =>
  Math.max(1, Math.round(viewportSize.width || diagramLayout.value?.width || 1)),
)
const viewportHeight = computed(() =>
  Math.max(1, Math.round(viewportSize.height || diagramLayout.value?.canvasHeight || 1)),
)
const viewportBox = computed(() => `0 0 ${viewportWidth.value} ${viewportHeight.value}`)
const contentTransform = computed(
  () =>
    `translate(${viewportTransform.x.toFixed(2)} ${viewportTransform.y.toFixed(2)}) scale(${viewportTransform.scale.toFixed(4)})`,
)

const canvasStyle = computed(() => {
  if (!diagramLayout.value) {
    return {}
  }

  return {
    minHeight: `${diagramLayout.value.canvasHeight}px`,
  }
})

function toKey(value) {
  return value === null || value === undefined ? '' : String(value)
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

function firstAvailable(row, key) {
  const basis = parseMaybeJson(row?.basis)
  return row?.[key] ?? basis?.[key]
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function measureViewport() {
  const rect = stageRef.value?.getBoundingClientRect()
  if (!rect) {
    return
  }

  viewportSize.width = Math.max(1, rect.width)
  viewportSize.height = Math.max(1, rect.height)
}

function attachResizeObserver() {
  if (resizeObserver || !stageRef.value || typeof ResizeObserver === 'undefined') {
    return
  }

  resizeObserver = new ResizeObserver(() => {
    measureViewport()
    if (!viewportTransform.userAdjusted) {
      fitView()
    }
  })
  resizeObserver.observe(stageRef.value)
}

function fitView() {
  measureViewport()
  const layout = diagramLayout.value
  if (!layout?.width || !layout?.height) {
    return
  }

  const availableWidth = viewportWidth.value
  const availableHeight = viewportHeight.value
  const nextScale = clamp(
    Math.min(availableWidth / layout.width, availableHeight / layout.height) * FIT_PADDING,
    MIN_ZOOM,
    MAX_ZOOM,
  )

  viewportTransform.scale = nextScale
  viewportTransform.x = (availableWidth - layout.width * nextScale) / 2
  viewportTransform.y = (availableHeight - layout.height * nextScale) / 2
}

function resetView() {
  viewportTransform.userAdjusted = false
  fitView()
}

function resetHover() {
  hoverCard.value = null
}

function formatPercent(value) {
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

function entityTypeLabel(value) {
  return ENTITY_TYPE_LABELS[value] || ENTITY_TYPE_LABELS.other
}

function relationTypeLabel(value) {
  if (!value) {
    return ''
  }
  return RELATION_TYPE_LABELS[value] || String(value)
}

function pathKindLabel(value) {
  return value === 'direct' ? '直接路径' : '间接路径'
}

function pathScoreLabel(path) {
  const rendered = formatPercent(path?.score)
  return rendered ? `约 ${rendered}` : ''
}

function displayModeLabel(value) {
  return DISPLAY_MODE_LABELS[value] || value || '分层展开'
}

function summaryNodeVariantClass(node) {
  if (node?.role !== 'actualSummary') {
    return ''
  }
  if (summaryControllerRoleKey.value === 'structural_signal') {
    return 'structure-node__box--summary-structural_signal'
  }
  if (summaryControllerRoleKey.value === 'leading_candidate') {
    return 'structure-node__box--summary-leading_candidate'
  }
  if (summaryControllerRoleKey.value === 'actual_controller') {
    return 'structure-node__box--summary-actual_controller'
  }
  return 'structure-node__box--summary-focused'
}

function nodeRoleLabel(node) {
  if (node.role === 'actualSummary') {
    return summaryControllerRoleLabel.value
  }
  if (node.role === 'target') {
    return '目标公司'
  }
  if (node.isMainPath && node.isKeyPath) {
    return node.role === 'direct' ? '主链路直接控制人' : '主链路中间层'
  }
  if (node.depthFromTarget === 1) {
    return '直接上游主体'
  }
  if (node.isKeyPath) {
    return '关键路径节点'
  }
  return `第 ${node.depthFromTarget} 层上游主体`
}

function resolvedNodeRoleLabel(node) {
  if (node.role === 'actualSummary') {
    return summaryControllerRoleLabel.value
  }
  if (node.role === 'target') {
    return '目标公司'
  }
  if (node.isMainPath && node.isKeyPath) {
    return node.role === 'direct' ? '主链路直接控制人' : '主链路中间层'
  }
  if (node.depthFromTarget === 1) {
    return '直接上游主体'
  }
  if (node.branchDirection === 'up') {
    return `${summaryControllerRoleLabel.value}上方第 ${Math.max(1, Math.abs(Number(node.depthFromTarget) || 0) - 1)} 层主体`
  }
  if (node.isKeyPath) {
    return '关键路径节点'
  }
  return `第 ${Math.max(2, Number(node.depthFromTarget) || 0)} 层上游主体`
}

function edgeTitle(edge) {
  if (edge.isPrimary && summaryControllerRoleKey.value === 'structural_signal') {
    return '结构信号路径'
  }
  if (edge.isPrimary && edge.isCollapsed) {
    return '折叠关键路径提示'
  }
  if (edge.isPrimary) {
    return '关键控制路径'
  }
  if (edge.isKeyPath) {
    return '关键路径片段'
  }
  return '控制关系'
}

function yesNo(value) {
  return value ? '是' : '否'
}

function buildTooltipLines(item) {
  if (item?.sourceRenderKey && item?.targetRenderKey) {
    const convergence = diagramModel.value?.multiPathConvergenceByNodeId?.[toKey(item.controlSubjectId)]
    if (item.isPrimary && summaryControllerRoleKey.value === 'structural_signal') {
      return [
        item.controlSubjectName ? `结构信号主体：${item.controlSubjectName}` : null,
        item.controlObjectName ? `展示对象：${item.controlObjectName}` : null,
        '路径语义：研究展示主轴 / ownership aggregation path',
        '结论状态：非实际控制主体，未进入 actual/direct/leading 主表达',
        '结果影响：当前未识别唯一实际控制人，国别按 fallback 口径处理',
        item.controlRatio !== null && item.controlRatio !== undefined && item.controlRatio !== ''
          ? `聚合比例 / 控制强度：${formatPercent(item.controlRatio)}`
          : null,
        convergence
          ? `路径结构：直接 + 间接多路径汇聚，另有 ${convergence.supplementalPathCount} 条补充路径`
          : null,
      ].filter(Boolean)
    }
    return [
      item.controlSubjectName ? `控制主体：${item.controlSubjectName}` : null,
      item.controlObjectName ? `控制对象：${item.controlObjectName}` : null,
      relationTypeLabel(item.relationType) ? `控制类型：${relationTypeLabel(item.relationType)}` : null,
      item.controlRatio !== null && item.controlRatio !== undefined && item.controlRatio !== ''
        ? `控制 / 持股比例：${formatPercent(item.controlRatio)}`
        : null,
      `关键路径：${yesNo(item.isPrimary || item.isKeyPath)}`,
      convergence
        ? `路径结构：直接 + 间接多路径汇聚，另有 ${convergence.supplementalPathCount} 条补充路径`
        : null,
      item.isCollapsed ? '说明：中间路径已折叠显示' : null,
    ].filter(Boolean)
  }

  const convergence = item?.multiPathConvergence || null
  if (item?.role === 'actualSummary' && summaryControllerRoleKey.value === 'structural_signal') {
    return [
      '节点角色：结构信号主轴',
      `主体类型：${entityTypeLabel(item.entityType)}`,
      item.country ? `国家 / 地区：${item.country}` : null,
      '结论状态：非实际控制主体',
      '用途：解释 ownership aggregation / dispersed ownership 结构特征',
      '结果影响：未进入 actual/direct/leading 主表达',
      normalizeKey(props.countryAttribution?.attribution_type) === 'fallback_incorporation'
        ? '国别结论：当前按注册地 fallback 处理'
        : null,
      item.controlRatio !== null && item.controlRatio !== undefined && item.controlRatio !== ''
        ? `聚合比例 / 控制强度：${formatPercent(item.controlRatio)}`
        : null,
    ].filter(Boolean)
  }
  return [
    `节点角色：${resolvedNodeRoleLabel(item)}`,
    `主体类型：${entityTypeLabel(item.entityType)}`,
    item.country ? `国家 / 地区：${item.country}` : null,
    item.controlRatio !== null && item.controlRatio !== undefined && item.controlRatio !== ''
      ? `控制 / 持股比例：${formatPercent(item.controlRatio)}`
      : null,
    relationTypeLabel(item.relationType) ? `控制类型：${relationTypeLabel(item.relationType)}` : null,
    item.relatedEntityName
      ? `${item.relationDirection === 'controlledBy' ? '关联主体' : '控制对象'}：${item.relatedEntityName}`
      : null,
    `关键路径：${yesNo(item.isKeyPath)}`,
    convergence
      ? `路径结构：直接 + 间接多路径汇聚，图中仅突出主解释路径`
      : null,
    convergence?.primaryPath?.text
      ? `主路径：${pathKindLabel(convergence.primaryPath.kind)}，${convergence.primaryPath.text}`
      : null,
    ...(convergence?.supplementalPaths || []).slice(0, 2).map((path) =>
      `补充路径：${pathKindLabel(path.kind)}，${path.text}`,
    ),
    item.expandable
      ? item.expanded
        ? '展开状态：已展开'
        : `展开状态：已收起（隐藏 ${item.hiddenUpstreamCount || 0} 个上游主体）`
      : null,
  ].filter(Boolean)
}

function showHover(event, item) {
  const rect = stageRef.value?.getBoundingClientRect()
  if (!rect || !item) {
    return
  }

  hoverCard.value = {
    title: item?.sourceRenderKey ? edgeTitle(item) : item.name || 'node',
    lines: buildTooltipLines(item),
    x: event.clientX - rect.left + 12,
    y: event.clientY - rect.top + 12,
  }
}

function hoverCardStyle() {
  if (!hoverCard.value) {
    return {}
  }

  return {
    left: `${hoverCard.value.x}px`,
    top: `${hoverCard.value.y}px`,
  }
}

function labelLines(value) {
  const text = String(value || '').trim()
  if (!text) {
    return ['未命名主体']
  }

  const limit = 16
  if (text.length <= limit) {
    return [text]
  }

  const words = text.split(/\s+/).filter(Boolean)
  if (words.length > 1) {
    const lines = []
    let buffer = ''

    words.forEach((word) => {
      const candidate = buffer ? `${buffer} ${word}` : word
      if (candidate.length <= limit || !buffer) {
        buffer = candidate
      } else if (lines.length < 1) {
        lines.push(buffer)
        buffer = word
      }
    })

    if (buffer) {
      lines.push(buffer)
    }

    if (lines.length >= 2) {
      return [lines[0], lines.slice(1).join(' ').slice(0, limit)]
    }
  }

  return [text.slice(0, limit), text.slice(limit, limit * 2)]
}

function nodeRectX(node) {
  return -node.width / 2
}

function nodeRectY(node) {
  return -node.height / 2
}

function markerEnd(edge) {
  if (edge.isPrimary && summaryControllerRoleKey.value === 'structural_signal') {
    return 'url(#control-structure-arrow-structural)'
  }
  if (edge.isPrimary && summaryControllerRoleKey.value === 'leading_candidate') {
    return 'url(#control-structure-arrow-leading)'
  }
  if (edge.isPrimary && summaryControllerRoleKey.value !== 'actual_controller') {
    return 'url(#control-structure-arrow-normal)'
  }
  return edge.isPrimary || edge.isKeyPath
    ? 'url(#control-structure-arrow-key)'
    : 'url(#control-structure-arrow-normal)'
}

function toggleTransform(node) {
  const direction = node?.branchDirection === 'up' || node?.role === 'actualSummary' ? -1 : 1
  return `translate(0, ${direction * (node.height / 2 + 18)})`
}

function pathBadgeTransform(node) {
  return `translate(${node.width / 2 - 34}, ${-node.height / 2 - 10})`
}

function handleWheel(event) {
  if (!diagramLayout.value) {
    return
  }

  const rect = stageRef.value?.getBoundingClientRect()
  if (!rect) {
    return
  }

  const pointerX = event.clientX - rect.left
  const pointerY = event.clientY - rect.top
  const previousScale = viewportTransform.scale
  const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY
  const nextScale = clamp(previousScale * Math.exp(-delta * 0.0012), MIN_ZOOM, MAX_ZOOM)
  if (Math.abs(nextScale - previousScale) < 0.001) {
    return
  }

  const ratio = nextScale / previousScale
  viewportTransform.x = pointerX - (pointerX - viewportTransform.x) * ratio
  viewportTransform.y = pointerY - (pointerY - viewportTransform.y) * ratio
  viewportTransform.scale = nextScale
  viewportTransform.userAdjusted = true
}

function startPan(event) {
  if (event.button !== 0) {
    return
  }

  panState.active = true
  panState.pointerId = event.pointerId
  panState.startX = event.clientX
  panState.startY = event.clientY
  panState.originX = viewportTransform.x
  panState.originY = viewportTransform.y
  viewportTransform.userAdjusted = true
  resetHover()
  event.currentTarget?.setPointerCapture?.(event.pointerId)
}

function handlePanMove(event) {
  if (!panState.active || panState.pointerId !== event.pointerId) {
    return
  }

  viewportTransform.x = panState.originX + event.clientX - panState.startX
  viewportTransform.y = panState.originY + event.clientY - panState.startY
}

function endPan(event) {
  if (panState.pointerId !== null && panState.pointerId !== event.pointerId) {
    return
  }

  panState.active = false
  panState.pointerId = null
  event.currentTarget?.releasePointerCapture?.(event.pointerId)
}

function toggleNode(node) {
  if (!node?.expandable) {
    return
  }
  const key = toKey(node.id)
  expandedByNodeId[key] = !expandedByNodeId[key]
}

function toggleGlyph(node) {
  return node?.expanded ? '-' : '+'
}

watch(
  () => [
    diagramLayout.value?.width,
    diagramLayout.value?.height,
    viewportSize.width,
    viewportSize.height,
  ],
  () => {
    if (!viewportTransform.userAdjusted) {
      nextTick(() => {
        attachResizeObserver()
        fitView()
      })
    }
  },
  { flush: 'post' },
)

onMounted(() => {
  nextTick(() => {
    measureViewport()
    attachResizeObserver()
    fitView()
  })
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})
</script>

<template>
  <ControlStructurePlaceholder
    v-if="shouldFallback"
    title="控制结构图"
  />

  <section v-else class="control-structure-diagram">
    <header class="control-structure-diagram__header">
      <div>
        <h3>控制结构示意图</h3>
        <p>
          主链自上游解释主体向目标公司向下展示；顶部节点的控制语义以当前状态说明为准。
          目标公司下方第一层及其子层统一向上汇聚到父节点。
        </p>
        <p class="control-structure-diagram__header-copy">{{ diagramHeaderDescription }}</p>
      </div>
      <el-tag effect="plain" type="danger">{{ displayModeLabel(diagramModel.displayMode) }}</el-tag>
    </header>

    <div class="control-structure-diagram__main">
      <section class="control-structure-diagram__stage">
        <div
          ref="stageRef"
          :class="['control-structure-diagram__canvas', panState.active ? 'is-panning' : '']"
          :style="canvasStyle"
          @mouseleave="resetHover"
        >
          <div class="control-structure-viewport-controls">
            <button type="button" class="viewport-control-button" @click="resetView">
              适应视图
            </button>
          </div>

          <svg
            class="control-structure-diagram__svg"
            :viewBox="viewportBox"
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="控制结构图"
            @wheel.prevent="handleWheel"
          >
            <defs>
              <marker
                id="control-structure-arrow-normal"
                markerWidth="10"
                markerHeight="10"
                refX="8"
                refY="5"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" class="structure-arrow structure-arrow--normal" />
              </marker>
              <marker
                id="control-structure-arrow-key"
                markerWidth="12"
                markerHeight="12"
                refX="10"
                refY="6"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path d="M 0 0 L 12 6 L 0 12 z" class="structure-arrow structure-arrow--key" />
              </marker>
              <marker
                id="control-structure-arrow-leading"
                markerWidth="12"
                markerHeight="12"
                refX="10"
                refY="6"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path d="M 0 0 L 12 6 L 0 12 z" class="structure-arrow structure-arrow--leading" />
              </marker>
              <marker
                id="control-structure-arrow-structural"
                markerWidth="11"
                markerHeight="11"
                refX="9"
                refY="5.5"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path d="M 0 0 L 11 5.5 L 0 11 z" class="structure-arrow structure-arrow--structural" />
              </marker>
            </defs>

            <rect
              class="structure-pan-catcher"
              x="0"
              y="0"
              :width="viewportWidth"
              :height="viewportHeight"
              @pointerdown="startPan"
              @pointermove="handlePanMove"
              @pointerup="endPan"
              @pointercancel="endPan"
            />

            <g class="structure-viewport-content" :transform="contentTransform">
              <g class="structure-edges">
                <path
                  v-for="edge in diagramLayout.edges"
                  :key="edge.id"
                  :d="edge.path"
                  :marker-end="markerEnd(edge)"
                  :class="[
                    'structure-edge',
                    `structure-edge--${edge.relationType}`,
                    edge.isBranch ? 'structure-edge--branch' : '',
                    edge.branchDepth >= 2 ? 'structure-edge--subtree' : '',
                    edge.isKeyPath ? 'structure-edge--key' : '',
                    edge.isPrimary ? 'structure-edge--primary' : '',
                    edge.isPrimary && summaryControllerRoleKey === 'leading_candidate'
                      ? 'structure-edge--primary-candidate'
                      : '',
                    edge.isPrimary && summaryControllerRoleKey === 'structural_signal'
                      ? 'structure-edge--primary-structural'
                      : '',
                    edge.isPrimary &&
                    !['actual_controller', 'leading_candidate', 'structural_signal'].includes(summaryControllerRoleKey)
                      ? 'structure-edge--primary-focused'
                      : '',
                    edge.isCollapsed ? 'structure-edge--collapsed' : '',
                  ]"
                  @mousemove="showHover($event, edge)"
                />
              </g>

              <g class="structure-nodes">
                <g
                  v-for="node in diagramLayout.nodes"
                  :key="node.renderKey"
                  :transform="`translate(${node.x}, ${node.y})`"
                  :class="[
                    'structure-node',
                    `structure-node--${node.role}`,
                    node.isKeyPath ? 'structure-node--key' : '',
                    node.role === 'actualSummary' && summaryControllerRoleKey === 'structural_signal'
                      ? 'structure-node--structural-axis'
                      : '',
                  ]"
                  @mousemove="showHover($event, node)"
                  @pointerdown.stop
                >
                  <rect
                    :x="nodeRectX(node)"
                    :y="nodeRectY(node)"
                    :width="node.width"
                    :height="node.height"
                    :rx="node.radius"
                    :class="[
                      'structure-node__box',
                      `structure-node__box--${node.entityType}`,
                      `structure-node__box--role-${node.role}`,
                      summaryNodeVariantClass(node),
                    ]"
                  />
                  <text class="structure-node__label" text-anchor="middle" dominant-baseline="middle">
                    <tspan
                      v-for="(line, index) in labelLines(node.name)"
                      :key="`${node.renderKey}-${index}`"
                      x="0"
                      :dy="index === 0 ? -5 : 15"
                    >
                      {{ line }}
                    </tspan>
                  </text>

                  <g
                    v-if="node.multiPathConvergence"
                    class="structure-node__path-badge"
                    :transform="pathBadgeTransform(node)"
                  >
                    <rect x="-31" y="-11" width="62" height="22" rx="8" />
                    <text text-anchor="middle" dominant-baseline="middle">多路径</text>
                  </g>

                  <g
                    v-if="node.expandable"
                    class="structure-node__toggle"
                    :transform="toggleTransform(node)"
                    role="button"
                    tabindex="0"
                    @pointerdown.stop
                    @click.stop="toggleNode(node)"
                    @keydown.enter.prevent.stop="toggleNode(node)"
                    @keydown.space.prevent.stop="toggleNode(node)"
                  >
                    <circle cx="0" cy="0" r="11" class="structure-node__toggle-circle" />
                    <text class="structure-node__toggle-glyph" text-anchor="middle" dominant-baseline="middle">
                      {{ toggleGlyph(node) }}
                    </text>
                  </g>
                </g>
              </g>
            </g>
          </svg>

          <div v-if="hoverCard" class="control-structure-tooltip" :style="hoverCardStyle()">
            <strong>{{ hoverCard.title }}</strong>
            <span v-for="line in hoverCard.lines" :key="line">{{ line }}</span>
          </div>
        </div>

        <div v-if="primaryPathConvergence" class="control-path-convergence-panel">
          <div class="control-path-convergence-panel__head">
            <strong>控制路径说明</strong>
            <span>direct + indirect</span>
          </div>
          <p>
            {{ primaryPathConvergence.controllerName }} 同时通过直接路径与间接路径对目标公司形成控制影响；
            图中仅突出主解释路径，其余路径列为补充路径。
          </p>
          <div class="control-path-convergence-panel__rows">
            <div class="control-path-convergence-row">
              <span>主路径</span>
              <strong>{{ pathKindLabel(primaryPathConvergence.primaryPath.kind) }}</strong>
              <small>
                {{ primaryPathConvergence.primaryPath.text }}
                <template v-if="pathScoreLabel(primaryPathConvergence.primaryPath)">
                  · {{ pathScoreLabel(primaryPathConvergence.primaryPath) }}
                </template>
              </small>
            </div>
            <div
              v-for="path in primaryPathConvergence.supplementalPaths.slice(0, 2)"
              :key="`${primaryPathConvergence.nodeId}-supplement-${path.index}`"
              class="control-path-convergence-row"
            >
              <span>补充路径</span>
              <strong>{{ pathKindLabel(path.kind) }}</strong>
              <small>
                {{ path.text }}
                <template v-if="pathScoreLabel(path)"> · {{ pathScoreLabel(path) }}</template>
              </small>
            </div>
          </div>
          <div
            v-if="primaryPathConvergence.supplementalPathCount > 2"
            class="control-path-convergence-panel__more"
          >
            另有 {{ primaryPathConvergence.supplementalPathCount - 2 }} 条补充路径，可在下方控制结论明细表展开查看。
          </div>
        </div>

        <div class="control-structure-diagram__footnote control-structure-diagram__footnote--legacy">
          默认层次：
          顶部主轴在已识别时表示<strong>实际控制人</strong>，未识别唯一实际控制人时可降级为<strong>结构信号主轴</strong>；
          <strong>目标公司</strong>位于中轴，
          <strong>直接上游主体</strong>位于目标公司下方并向上指向父节点。
          可滚轮缩放、拖拽空白区域平移，点击“适应视图”可恢复居中。
        </div>
        <div class="control-structure-diagram__footnote">{{ diagramFootnote }}</div>
      </section>

      <aside class="control-structure-diagram__legend" aria-label="控制结构图图例">
        <div class="legend-block">
          <h4>主体类型</h4>
          <div class="legend-row">
            <span class="legend-dot legend-dot--company" />
            <span><strong>公司主体</strong>经营主体、控股平台、SPV 或 holding company</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--person" />
            <span><strong>自然人</strong>个人控制主体</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--fund" />
            <span><strong>基金 / 公众持股</strong>基金、Public Float、分散流通股或公众持股集合</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--government" />
            <span><strong>政府 / 国资主体</strong>政府、主权或国资相关主体</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--other" />
            <span><strong>其他主体</strong>暂未归类的上游主体；nominee、trust vehicle 等可能暂列此类</span>
          </div>
        </div>

        <div class="legend-block">
          <h4>节点角色</h4>
          <div class="legend-row legend-row--role">
            <span :class="['legend-role', summaryLegendRoleClass]" />
            <span class="legend-role-copy">
              <strong>{{ summaryControllerLegendTitle }}</strong>
              <small>{{ summaryControllerLegendDescription }}</small>
            </span>
          </div>
          <div class="legend-row legend-row--role">
            <span class="legend-role legend-role--target" />
            <span class="legend-role-copy">
              <strong>目标公司</strong>
              <small>中轴锚点节点，承接上下游聚类关系。</small>
            </span>
          </div>
          <div class="legend-row legend-row--role">
            <span class="legend-role legend-role--key" />
            <span class="legend-role-copy">
              <strong>关键路径节点</strong>
              <small>后端判定重点参考的路径节点，可能包含 direct controller、穿透中间层、ultimate / leading candidate。</small>
            </span>
          </div>
        </div>

        <div class="legend-block">
          <h4>边样式</h4>
          <div class="legend-line-row"><span class="legend-line legend-line--plain" /><span>普通控制关系：一般上游持股、协议或治理控制连接</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--key" /><span>关键路径：后端判定时重点参考的主解释路径</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--structural" /><span>结构信号主轴：研究展示路径，不代表已确认实际控制</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--collapsed" /><span>折叠路径提示：局部收起后的视觉连接，不代表新的控制类型</span></div>
        </div>

        <div class="legend-block">
          <h4>交互说明</h4>
          <div class="legend-toggle-row legend-toggle-row--item">
            <span class="legend-toggle">+</span>
            <span class="legend-role-copy">
              <strong>展开节点</strong>
              <small>{{ interactionHint }}</small>
            </span>
          </div>
          <div class="legend-toggle-row legend-toggle-row--item">
            <span class="legend-toggle">-</span>
            <span class="legend-role-copy">
              <strong>收起节点</strong>
              <small>仅收起该节点的局部子树，不影响当前主链路与其它已展开分支。</small>
            </span>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.control-structure-diagram {
  margin-top: 18px;
  padding: 14px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  background: #f7fafc;
}

.control-structure-diagram__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.control-structure-diagram__header h3 {
  margin: 0;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.control-structure-diagram__header p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.control-structure-diagram__header p:not(.control-structure-diagram__header-copy) {
  display: none;
}

.control-structure-diagram__main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 250px;
  gap: 12px;
  margin-top: 14px;
}

.control-structure-diagram__stage,
.control-structure-diagram__legend {
  min-width: 0;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
}

.control-structure-diagram__stage {
  overflow: hidden;
}

.control-structure-diagram__canvas {
  position: relative;
  min-height: 540px;
  overflow: hidden;
  cursor: default;
}

.control-structure-diagram__canvas.is-panning {
  cursor: grabbing;
}

.control-structure-viewport-controls {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 3;
  display: flex;
  gap: 6px;
}

.viewport-control-button {
  padding: 5px 9px;
  border: 1px solid rgba(37, 54, 74, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  color: #25364a;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 6px 14px rgba(15, 23, 42, 0.08);
}

.viewport-control-button:hover {
  border-color: rgba(190, 18, 60, 0.34);
  color: #be123c;
}

.control-structure-diagram__svg {
  display: block;
  width: 100%;
  height: 100%;
  min-height: inherit;
  touch-action: none;
  user-select: none;
}

.structure-pan-catcher {
  fill: transparent;
  cursor: grab;
}

.control-structure-diagram__canvas.is-panning .structure-pan-catcher {
  cursor: grabbing;
}

.structure-edge {
  fill: none;
  stroke: #475569;
  stroke-width: 1.75;
  opacity: 0.48;
  pointer-events: stroke;
}

.structure-edge--agreement,
.structure-edge--nominee,
.structure-edge--vie {
  stroke-dasharray: 7 5;
}

.structure-edge--agreement {
  stroke: #7666cf;
}

.structure-edge--board_control {
  stroke: #c56b2d;
}

.structure-edge--voting_right {
  stroke: #24736f;
  stroke-dasharray: 4 4;
}

.structure-edge--nominee {
  stroke: #a64270;
}

.structure-edge--vie {
  stroke: #2f8ca7;
}

.structure-edge--key {
  stroke: #b91c1c;
  stroke-width: 3;
  opacity: 0.84;
}

.structure-edge--branch {
  stroke-width: 1.9;
  opacity: 0.5;
}

.structure-edge--subtree {
  stroke-width: 1.5;
  opacity: 0.38;
}

.structure-edge--key.structure-edge--branch {
  stroke-width: 3;
  opacity: 0.84;
}

.structure-edge--primary {
  stroke: #b91c1c;
  stroke-width: 4.6;
  opacity: 0.94;
}

.structure-edge--primary-candidate {
  stroke: #5b50ad;
}

.structure-edge--primary-structural {
  stroke: #60758a;
  stroke-width: 3;
  stroke-dasharray: 10 7;
  opacity: 0.78;
}

.structure-edge--primary-focused {
  stroke: #60758a;
  stroke-width: 3;
  opacity: 0.72;
}

.structure-edge--collapsed {
  stroke-dasharray: 9 6;
}

.structure-arrow--normal {
  fill: #475569;
  opacity: 0.56;
}

.structure-arrow--key {
  fill: #b91c1c;
}

.structure-arrow--leading {
  fill: #5b50ad;
}

.structure-arrow--structural {
  fill: #60758a;
  opacity: 0.78;
}

.structure-node__box {
  stroke: #334155;
  stroke-width: 1.6;
  filter: drop-shadow(0 6px 10px rgba(15, 23, 42, 0.07));
}

.structure-node__box--company {
  fill: #3b6fa8;
}

.structure-node__box--person {
  fill: #c2413b;
}

.structure-node__box--fund {
  fill: #3b9b6d;
}

.structure-node__box--government {
  fill: #c9792d;
}

.structure-node__box--other {
  fill: #6b7280;
}

.structure-node__box--role-target {
  fill: #2f5f9f;
  stroke: #1e293b;
  stroke-width: 3.6;
  filter: drop-shadow(0 9px 13px rgba(15, 23, 42, 0.16));
}

.structure-node__box--role-actualSummary {
  fill: #c2413b;
  stroke: #b91c1c;
  stroke-width: 4.2;
  filter: drop-shadow(0 9px 14px rgba(185, 28, 28, 0.18));
}

.structure-node__box--summary-leading_candidate {
  fill: #7666cf;
  stroke: #5b50ad;
  filter: drop-shadow(0 9px 14px rgba(91, 80, 173, 0.18));
}

.structure-node__box--summary-focused {
  fill: #6f7f91;
  stroke: #475569;
  stroke-width: 3;
  filter: drop-shadow(0 7px 12px rgba(71, 85, 105, 0.12));
}

.structure-node__box--summary-structural_signal {
  fill: #eef4f7;
  stroke: #60758a;
  stroke-width: 3;
  stroke-dasharray: 9 5;
  filter: drop-shadow(0 7px 12px rgba(71, 85, 105, 0.12));
}

.structure-node--structural-axis .structure-node__label {
  fill: #2d3f51;
}

.structure-node__box--role-focused {
  fill: #7666cf;
  stroke: #5b50ad;
  stroke-width: 3.4;
}

.structure-node--key .structure-node__box {
  stroke-width: 3.2;
}

.structure-node--support .structure-node__box,
.structure-node--intermediate .structure-node__box {
  opacity: 0.9;
}

.structure-node__label {
  fill: #f8fafc;
  font-size: 12px;
  font-weight: 700;
  pointer-events: none;
}

.structure-node__path-badge {
  pointer-events: none;
}

.structure-node__path-badge rect {
  fill: #ffffff;
  stroke: rgba(31, 59, 87, 0.22);
  stroke-width: 1;
  filter: drop-shadow(0 3px 8px rgba(15, 23, 42, 0.1));
}

.structure-node__path-badge text {
  fill: #36506a;
  font-size: 11px;
  font-weight: 700;
}

.structure-node__toggle {
  cursor: pointer;
}

.structure-node__toggle-circle {
  fill: #ffffff;
  stroke: #475569;
  stroke-width: 1.4;
  filter: drop-shadow(0 3px 8px rgba(15, 23, 42, 0.08));
}

.structure-node__toggle-glyph {
  fill: #0f172a;
  font-size: 14px;
  font-weight: 800;
  pointer-events: none;
}

.control-structure-tooltip {
  position: absolute;
  z-index: 4;
  max-width: 300px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(24, 34, 44, 0.96);
  color: #f8fafc;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.18);
  pointer-events: none;
}

.control-structure-tooltip strong,
.control-structure-tooltip span {
  display: block;
}

.control-structure-tooltip strong {
  margin-bottom: 6px;
  font-size: 13px;
}

.control-structure-tooltip span {
  font-size: 12px;
  line-height: 1.55;
}

.control-path-convergence-panel {
  display: grid;
  gap: 8px;
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  background: rgba(31, 59, 87, 0.035);
}

.control-path-convergence-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.control-path-convergence-panel__head strong {
  color: var(--brand-ink);
  font-size: 13px;
}

.control-path-convergence-panel__head span {
  color: #5b50ad;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
}

.control-path-convergence-panel p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.65;
}

.control-path-convergence-panel__rows {
  display: grid;
  gap: 6px;
}

.control-path-convergence-row {
  display: grid;
  grid-template-columns: 58px 68px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  color: #314255;
  font-size: 12px;
  line-height: 1.55;
}

.control-path-convergence-row span {
  color: var(--text-secondary);
}

.control-path-convergence-row strong {
  color: #243648;
  font-size: 12px;
}

.control-path-convergence-row small {
  color: #526579;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.control-path-convergence-panel__more {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.control-structure-diagram__footnote {
  padding: 10px 12px;
  border-top: 1px solid rgba(31, 59, 87, 0.08);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.control-structure-diagram__footnote--legacy {
  display: none;
}

.control-structure-diagram__footnote strong {
  color: #25364a;
}

.control-structure-diagram__legend {
  padding: 12px;
}

.legend-block + .legend-block {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(31, 59, 87, 0.08);
}

.legend-block h4 {
  margin: 0 0 10px;
  color: var(--brand-ink);
  font-size: 14px;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.legend-row,
.legend-line-row,
.legend-toggle-row {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-height: 28px;
}

.legend-row--role {
  align-items: start;
}

.legend-toggle-row--item {
  align-items: start;
}

.legend-row + .legend-row,
.legend-line-row + .legend-line-row,
.legend-toggle-row + .legend-toggle-row {
  margin-top: 7px;
}

.legend-row span:last-child,
.legend-line-row span:last-child,
.legend-toggle-row span:last-child {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.35;
}

.legend-row strong {
  display: block;
  color: #25364a;
  font-size: 12px;
}

.legend-toggle-row strong {
  display: block;
  color: #25364a;
  font-size: 12px;
}

.legend-role-copy {
  min-width: 0;
}

.legend-role-copy small {
  display: block;
  margin-top: 3px;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  line-height: 1.4;
}

.legend-toggle-row__copy + span {
  display: none;
}

.legend-dot {
  width: 14px;
  height: 14px;
  border-radius: 999px;
}

.legend-dot--company {
  background: #3b6fa8;
}

.legend-dot--person {
  background: #c2413b;
}

.legend-dot--fund {
  background: #3b9b6d;
}

.legend-dot--government {
  background: #c9792d;
}

.legend-dot--other {
  background: #6b7280;
}

.legend-role {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  border: 4px solid #334155;
}

.legend-role--actual {
  border-color: #b91c1c;
}

.legend-role--leading {
  border-color: #5b50ad;
}

.legend-role--structural {
  border-color: #60758a;
  border-style: dashed;
}

.legend-role--inactive {
  border-color: #94a3b8;
}

.legend-role--target {
  border-color: #0f172a;
}

.legend-role--key {
  border-color: #7c2d12;
}

.legend-line {
  width: 30px;
  border-top: 3px solid #111827;
}

.legend-line--key {
  border-top-color: #b91c1c;
  border-top-width: 4px;
}

.legend-line--structural {
  border-top-color: #60758a;
  border-top-style: dashed;
  border-top-width: 3px;
}

.legend-line--collapsed {
  border-top-color: #b91c1c;
  border-top-style: dashed;
}

.legend-toggle {
  display: inline-grid;
  place-items: center;
  width: 20px;
  height: 20px;
  margin-top: 1px;
  border-radius: 999px;
  border: 1px solid rgba(37, 54, 74, 0.25);
  background: #fff;
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
}

@media (max-width: 1040px) {
  .control-structure-diagram__main {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .control-structure-diagram__header {
    display: grid;
  }

  .control-structure-diagram__canvas {
    min-height: 500px;
  }
}
</style>
