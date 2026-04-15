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
  fund: '基金 / 公众持股',
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

function displayModeLabel(value) {
  return DISPLAY_MODE_LABELS[value] || value || '分层展开'
}

function nodeRoleLabel(node) {
  if (node.role === 'actualSummary') {
    return '实际控制人'
  }
  if (node.role === 'target') {
    return '目标公司'
  }
  if (node.depthFromTarget === 1) {
    return '直接上游主体'
  }
  if (node.isKeyPath) {
    return '关键路径节点'
  }
  return `第 ${node.depthFromTarget} 层上游主体`
}

function edgeTitle(edge) {
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
    return [
      item.controlSubjectName ? `控制主体：${item.controlSubjectName}` : null,
      item.controlObjectName ? `控制对象：${item.controlObjectName}` : null,
      relationTypeLabel(item.relationType) ? `控制类型：${relationTypeLabel(item.relationType)}` : null,
      item.controlRatio !== null && item.controlRatio !== undefined && item.controlRatio !== ''
        ? `控制 / 持股比例：${formatPercent(item.controlRatio)}`
        : null,
      `关键路径：${yesNo(item.isPrimary || item.isKeyPath)}`,
      item.isCollapsed ? '说明：中间路径已折叠显示' : null,
    ].filter(Boolean)
  }

  return [
    `节点角色：${nodeRoleLabel(item)}`,
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
  return edge.isPrimary || edge.isKeyPath
    ? 'url(#control-structure-arrow-key)'
    : 'url(#control-structure-arrow-normal)'
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
          主链按“实际控制人 → 目标公司”纵向呈现，直接上游主体在目标公司下方分支展开，
          可逐层查看每个节点的局部上游结构。
        </p>
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
                    v-if="node.expandable"
                    class="structure-node__toggle"
                    :transform="`translate(0, ${node.height / 2 + 18})`"
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

        <div class="control-structure-diagram__footnote">
          默认层次：
          <strong>实际控制人</strong>位于顶部主轴，
          <strong>目标公司</strong>位于中轴，
          <strong>直接上游主体</strong>位于目标公司下方。
          可滚轮缩放、拖拽空白区域平移，点击“适应视图”可恢复居中。
        </div>
      </section>

      <aside class="control-structure-diagram__legend" aria-label="控制结构图图例">
        <div class="legend-block">
          <h4>主体类型</h4>
          <div class="legend-row">
            <span class="legend-dot legend-dot--company" />
            <span><strong>公司主体</strong>企业、控股平台或经营主体</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--person" />
            <span><strong>自然人</strong>个人控制主体</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--fund" />
            <span><strong>基金 / 公众持股</strong>基金、公众流通股等</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--government" />
            <span><strong>政府 / 国资主体</strong>政府、主权或国资相关主体</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--other" />
            <span><strong>其他主体</strong>暂未归类的上游主体</span>
          </div>
        </div>

        <div class="legend-block">
          <h4>节点角色</h4>
          <div class="legend-row">
            <span class="legend-role legend-role--actual" />
            <span><strong>实际控制人</strong>顶部主链节点</span>
          </div>
          <div class="legend-row">
            <span class="legend-role legend-role--target" />
            <span><strong>目标公司</strong>中轴锚点节点</span>
          </div>
          <div class="legend-row">
            <span class="legend-role legend-role--key" />
            <span><strong>关键路径节点</strong>控制主路径上的节点</span>
          </div>
        </div>

        <div class="legend-block">
          <h4>边样式</h4>
          <div class="legend-line-row"><span class="legend-line legend-line--plain" /><span>普通控制关系</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--key" /><span>关键路径</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--collapsed" /><span>折叠路径提示</span></div>
        </div>

        <div class="legend-block">
          <h4>交互说明</h4>
          <div class="legend-toggle-row">
            <span class="legend-toggle">+</span>
            <span>展开该节点的下一层上游结构</span>
          </div>
          <div class="legend-toggle-row">
            <span class="legend-toggle">-</span>
            <span>仅收起该节点的局部子树</span>
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

.control-structure-diagram__footnote {
  padding: 10px 12px;
  border-top: 1px solid rgba(31, 59, 87, 0.08);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
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

.legend-line--collapsed {
  border-top-color: #b91c1c;
  border-top-style: dashed;
}

.legend-toggle {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  border: 1px solid rgba(37, 54, 74, 0.25);
  background: #fff;
  color: #0f172a;
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
