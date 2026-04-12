<script setup>
import { computed, reactive, ref, watch } from 'vue'

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

function nodeRoleLabel(node) {
  if (node.role === 'actualSummary') {
    return 'actual controller'
  }
  if (node.role === 'target') {
    return 'target company'
  }
  if (node.depthFromTarget === 1) {
    return 'direct upstream'
  }
  return `upstream layer ${node.depthFromTarget}`
}

function edgeTitle(edge) {
  if (edge.isPrimary && edge.isCollapsed) {
    return 'collapsed key path'
  }
  if (edge.isPrimary) {
    return 'key path'
  }
  if (edge.isKeyPath) {
    return 'key-path segment'
  }
  return 'control relation'
}

function buildTooltipLines(item) {
  if (item?.sourceRenderKey && item?.targetRenderKey) {
    return [
      `type: ${item.relationType}`,
      item.controlRatio !== null && item.controlRatio !== undefined && item.controlRatio !== ''
        ? `ratio: ${formatPercent(item.controlRatio)}`
        : null,
      item.isCollapsed ? 'collapsed: hidden upstream steps are summarized' : null,
    ].filter(Boolean)
  }

  return [
    `role: ${nodeRoleLabel(item)}`,
    `entity: ${item.entityType}`,
    item.country ? `country: ${item.country}` : null,
    item.expandable
      ? item.expanded
        ? 'state: expanded'
        : `state: collapsed (${item.hiddenUpstreamCount || 0} hidden)`
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
    return ['Unnamed entity']
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
</script>

<template>
  <ControlStructurePlaceholder
    v-if="shouldFallback"
    title="Control Structure"
  />

  <section v-else class="control-structure-diagram">
    <header class="control-structure-diagram__header">
      <div>
        <h3>Control Structure</h3>
        <p>
          Default view keeps the target at the bottom, shows only direct upstream entities, and
          keeps the actual-controller key path readable. Expand any visible node to reveal only its
          own upstream subtree.
        </p>
      </div>
      <el-tag effect="plain" type="danger">{{ diagramModel.displayMode || 'progressive-expand' }}</el-tag>
    </header>

    <div class="control-structure-diagram__main">
      <section class="control-structure-diagram__stage">
        <div
          ref="stageRef"
          class="control-structure-diagram__canvas"
          :style="canvasStyle"
          @mouseleave="resetHover"
        >
          <svg
            class="control-structure-diagram__svg"
            :viewBox="`0 0 ${diagramLayout.width} ${diagramLayout.height}`"
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="control structure diagram"
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

            <g class="structure-edges">
              <path
                v-for="edge in diagramLayout.edges"
                :key="edge.id"
                :d="edge.path"
                :marker-end="markerEnd(edge)"
                :class="[
                  'structure-edge',
                  `structure-edge--${edge.relationType}`,
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
          </svg>

          <div v-if="hoverCard" class="control-structure-tooltip" :style="hoverCardStyle()">
            <strong>{{ hoverCard.title }}</strong>
            <span v-for="line in hoverCard.lines" :key="line">{{ line }}</span>
          </div>
        </div>

        <div class="control-structure-diagram__footnote">
          Default layers:
          <strong>actual controller</strong> on top,
          <strong>direct upstream</strong> in the middle,
          <strong>target company</strong> at the bottom.
          Expanded branches stay inside their own local columns.
        </div>
      </section>

      <aside class="control-structure-diagram__legend" aria-label="control structure legend">
        <div class="legend-block">
          <h4>Entity Type</h4>
          <div class="legend-row">
            <span class="legend-dot legend-dot--company" />
            <span><strong>company</strong> corporate entity</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--person" />
            <span><strong>person</strong> natural person</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--fund" />
            <span><strong>fund</strong> fund or float</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--government" />
            <span><strong>government</strong> sovereign or state-linked</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--other" />
            <span><strong>other</strong> uncategorized entity</span>
          </div>
        </div>

        <div class="legend-block">
          <h4>Node Emphasis</h4>
          <div class="legend-row">
            <span class="legend-role legend-role--actual" />
            <span><strong>actual controller</strong> persistent top summary node</span>
          </div>
          <div class="legend-row">
            <span class="legend-role legend-role--target" />
            <span><strong>target company</strong> anchored at bottom center</span>
          </div>
          <div class="legend-row">
            <span class="legend-role legend-role--key" />
            <span><strong>key path node</strong> highlighted within expanded subtrees</span>
          </div>
        </div>

        <div class="legend-block">
          <h4>Line Style</h4>
          <div class="legend-line-row"><span class="legend-line legend-line--plain" /><span>ordinary relation</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--key" /><span>key path</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--collapsed" /><span>collapsed key-path jump</span></div>
        </div>

        <div class="legend-block">
          <h4>Toggle</h4>
          <div class="legend-toggle-row">
            <span class="legend-toggle">+</span>
            <span>expand the node's next upstream layer</span>
          </div>
          <div class="legend-toggle-row">
            <span class="legend-toggle">-</span>
            <span>collapse only that local subtree</span>
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
}

.control-structure-diagram__svg {
  display: block;
  width: 100%;
  height: 100%;
  min-height: inherit;
}

.structure-edge {
  fill: none;
  stroke: #111827;
  stroke-width: 1.9;
  opacity: 0.68;
  pointer-events: stroke;
}

.structure-edge--agreement,
.structure-edge--nominee,
.structure-edge--vie {
  stroke-dasharray: 7 5;
}

.structure-edge--agreement {
  stroke: #7c3aed;
}

.structure-edge--board_control {
  stroke: #ea580c;
}

.structure-edge--voting_right {
  stroke: #0f766e;
  stroke-dasharray: 4 4;
}

.structure-edge--nominee {
  stroke: #be185d;
}

.structure-edge--vie {
  stroke: #0891b2;
}

.structure-edge--key {
  stroke: #be123c;
  stroke-width: 3.2;
  opacity: 0.86;
}

.structure-edge--primary {
  stroke: #be123c;
  stroke-width: 5;
  opacity: 0.96;
}

.structure-edge--collapsed {
  stroke-dasharray: 9 6;
}

.structure-arrow--normal {
  fill: #111827;
  opacity: 0.72;
}

.structure-arrow--key {
  fill: #be123c;
}

.structure-node__box {
  stroke: #334155;
  stroke-width: 1.6;
  filter: drop-shadow(0 7px 12px rgba(15, 23, 42, 0.08));
}

.structure-node__box--company {
  fill: #2563eb;
}

.structure-node__box--person {
  fill: #dc2626;
}

.structure-node__box--fund {
  fill: #16a34a;
}

.structure-node__box--government {
  fill: #ea580c;
}

.structure-node__box--other {
  fill: #64748b;
}

.structure-node__box--role-target {
  fill: #1d4ed8;
  stroke: #0f172a;
  stroke-width: 4;
  filter: drop-shadow(0 11px 16px rgba(15, 23, 42, 0.18));
}

.structure-node__box--role-actualSummary {
  fill: #dc2626;
  stroke: #be123c;
  stroke-width: 5;
  filter: drop-shadow(0 12px 18px rgba(190, 18, 60, 0.22));
}

.structure-node__box--role-focused {
  fill: #7c3aed;
  stroke: #6d28d9;
  stroke-width: 4;
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
  stroke: #25364a;
  stroke-width: 1.4;
  filter: drop-shadow(0 4px 10px rgba(15, 23, 42, 0.1));
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
  background: #2563eb;
}

.legend-dot--person {
  background: #dc2626;
}

.legend-dot--fund {
  background: #16a34a;
}

.legend-dot--government {
  background: #ea580c;
}

.legend-dot--other {
  background: #64748b;
}

.legend-role {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  border: 4px solid #334155;
}

.legend-role--actual {
  border-color: #be123c;
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
  border-top-color: #be123c;
  border-top-width: 4px;
}

.legend-line--collapsed {
  border-top-color: #be123c;
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
