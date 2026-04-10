<script setup>
import { computed, ref } from 'vue'

import { buildControlChainDiagramModel } from '@/utils/legacyControlChainAdapter'
import { computeControlChainDiagramLayout } from '@/utils/legacyControlChainLayout'

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

const diagramModel = computed(() =>
  buildControlChainDiagramModel({
    company: props.company,
    controlAnalysis: props.controlAnalysis,
    countryAttribution: props.countryAttribution,
    relationshipGraph: props.relationshipGraph,
  }),
)

const diagramLayout = computed(() =>
  diagramModel.value.hasDiagram ? computeControlChainDiagramLayout(diagramModel.value) : null,
)

const canvasStyle = computed(() => {
  if (!diagramLayout.value) {
    return {}
  }

  return {
    minHeight: `${diagramLayout.value.canvasHeight}px`,
  }
})

const filterSummary = computed(() => diagramModel.value.filterSummary || {})

const filterModeLabel = computed(() => {
  const mode = filterSummary.value.mode || 'small'
  return `adaptive ${mode}`
})

const equityThresholdLabel = computed(() => {
  const value = filterSummary.value.equityRatioThreshold
  if (value === null || value === undefined || value === '') {
    return '2%'
  }
  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return String(value)
  }
  return `${(numeric * 100).toFixed(2)}%`
})

function showHover(event, item) {
  const rect = stageRef.value?.getBoundingClientRect()
  if (!rect || !item) {
    return
  }

  hoverCard.value = {
    title: item.tooltipTitle,
    lines: item.tooltipLines || [],
    x: event.clientX - rect.left + 14,
    y: event.clientY - rect.top + 14,
  }
}

function clearHover() {
  hoverCard.value = null
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

function markerEnd(edge) {
  return edge.kind === 'primary' ? 'url(#control-chain-arrow-primary)' : 'url(#control-chain-arrow-support)'
}

function rectX(node) {
  return -(node.width || 0) / 2
}

function rectY(node) {
  return -(node.height || 0) / 2
}

function labelY(node) {
  const halfHeight = node.shape === 'roundRect' ? node.height / 2 : node.radius
  return halfHeight + 22
}
</script>

<template>
  <div class="control-chain-diagram">
    <div class="control-chain-diagram__header">
      <div>
        <h3>自适应主要控制结构图</h3>
        <p>简单结构尽量全展示，复杂结构按阈值筛选；关键控制链始终保留。</p>
      </div>
      <el-tag effect="plain" type="danger">{{ filterModeLabel }}</el-tag>
    </div>

    <div class="control-chain-diagram__main">
      <section class="control-chain-diagram__stage">
        <div v-if="!diagramModel.hasDiagram" class="control-chain-diagram__placeholder">
          <div class="placeholder-mark">Adaptive</div>
          <h4>{{ diagramModel.placeholderTitle }}</h4>
          <p>{{ diagramModel.placeholderDescription }}</p>
          <div class="placeholder-note">
            新图会优先保留 summary/control_relationships 中的关键路径，再按结构复杂度决定展示范围。
          </div>
        </div>

        <div
          v-else
          ref="stageRef"
          class="control-chain-diagram__canvas"
          :style="canvasStyle"
          @mouseleave="clearHover"
        >
          <svg
            class="control-chain-diagram__svg"
            :viewBox="`0 0 ${diagramLayout.width} ${diagramLayout.height}`"
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="adaptive control structure diagram"
          >
            <defs>
              <marker
                id="control-chain-arrow-primary"
                markerWidth="12"
                markerHeight="12"
                refX="10"
                refY="6"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path d="M 0 0 L 12 6 L 0 12 z" class="arrow arrow--primary" />
              </marker>
              <marker
                id="control-chain-arrow-support"
                markerWidth="10"
                markerHeight="10"
                refX="9"
                refY="5"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" class="arrow arrow--support" />
              </marker>
            </defs>

            <g class="diagram-edges">
              <path
                v-for="edge in diagramLayout.edges"
                :key="edge.id"
                :d="edge.path"
                :class="[
                  'diagram-edge',
                  `diagram-edge--${edge.kind}`,
                  edge.isKeyPath ? 'diagram-edge--key' : '',
                  edge.relationType && edge.relationType !== 'equity' ? 'diagram-edge--semantic' : '',
                ]"
                :marker-end="markerEnd(edge)"
                @mousemove="showHover($event, edge)"
              />
            </g>

            <g class="diagram-nodes">
              <g
                v-for="node in diagramLayout.nodes"
                :key="node.id"
                :transform="`translate(${node.x}, ${node.y})`"
                :class="['diagram-node', `diagram-node--${node.role}`]"
                @mousemove="showHover($event, node)"
              >
                <circle
                  v-if="node.role === 'actualController'"
                  class="node-ring node-ring--actual"
                  :r="node.ringRadius"
                />

                <rect
                  v-if="node.shape === 'roundRect'"
                  :x="rectX(node)"
                  :y="rectY(node)"
                  :width="node.width"
                  :height="node.height"
                  :rx="node.radius"
                  :class="['node-shape', `node-shape--${node.role}`, `node-fill--${node.entityType}`]"
                />
                <circle
                  v-else
                  :r="node.radius"
                  :class="['node-shape', `node-shape--${node.role}`, `node-fill--${node.entityType}`]"
                />

                <text class="node-initial" text-anchor="middle" dominant-baseline="middle">
                  {{ node.name.slice(0, 1).toUpperCase() }}
                </text>

                <text class="node-label" text-anchor="middle" :y="labelY(node)">
                  <tspan
                    v-for="(line, index) in node.labelLines"
                    :key="`${node.id}-label-${index}`"
                    x="0"
                    :dy="index === 0 ? 0 : 15"
                  >
                    {{ line }}
                  </tspan>
                </text>
              </g>
            </g>
          </svg>

          <div v-if="hoverCard" class="control-chain-tooltip" :style="hoverCardStyle()">
            <strong>{{ hoverCard.title }}</strong>
            <span v-for="line in hoverCard.lines" :key="line">{{ line }}</span>
          </div>
        </div>

        <div class="control-chain-diagram__footnote">
          当前模式 {{ filterSummary.mode || 'small' }}；直接上游
          <strong>{{ filterSummary.selectedDirectUpstreamCount || 0 }}</strong>
          /
          <strong>{{ filterSummary.directUpstreamCount || 0 }}</strong>
          个进入默认图，普通 equity 阈值 {{ equityThresholdLabel }}。
        </div>
      </section>

      <aside class="control-chain-diagram__legend">
        <div class="legend-block">
          <h4>视图口径</h4>
          <p>Adaptive Control Structure</p>
          <span>少量节点尽量全展示；复杂结构筛选普通 equity，关键路径和重要非 equity 控制关系强制保留。</span>
        </div>

        <div v-if="diagramModel.hasDiagram" class="legend-block">
          <h4>关键结论</h4>
          <dl>
            <div>
              <dt>实际控制人</dt>
              <dd>{{ diagramModel.actualControllerName }}</dd>
            </div>
            <div>
              <dt>目标公司</dt>
              <dd>{{ diagramModel.targetName }}</dd>
            </div>
            <div>
              <dt>实际控制地</dt>
              <dd>{{ diagramModel.actualControlCountry }}</dd>
            </div>
          </dl>
        </div>

        <div class="legend-block">
          <h4>图例</h4>
          <div class="legend-row">
            <span class="legend-symbol legend-symbol--actual" />
            <span>actual controller</span>
          </div>
          <div class="legend-row">
            <span class="legend-symbol legend-symbol--intermediate" />
            <span>key intermediate node</span>
          </div>
          <div class="legend-row">
            <span class="legend-symbol legend-symbol--target" />
            <span>target company</span>
          </div>
          <div class="legend-row">
            <span class="legend-line legend-line--primary" />
            <span>key control path</span>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.control-chain-diagram {
  margin-top: 18px;
  padding: 14px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  background: #f7fafc;
}

.control-chain-diagram__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.control-chain-diagram__header h3 {
  margin: 0;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.control-chain-diagram__header p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.control-chain-diagram__main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 230px;
  gap: 12px;
  margin-top: 14px;
}

.control-chain-diagram__stage,
.control-chain-diagram__legend {
  min-width: 0;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.92);
}

.control-chain-diagram__stage {
  overflow: hidden;
}

.control-chain-diagram__canvas {
  position: relative;
  min-height: 520px;
}

.control-chain-diagram__svg {
  display: block;
  width: 100%;
  height: 100%;
  min-height: inherit;
}

.control-chain-diagram__placeholder {
  display: grid;
  place-items: center;
  min-height: 420px;
  padding: 32px;
  text-align: center;
}

.placeholder-mark {
  width: 112px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(190, 18, 60, 0.22);
  color: #be123c;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
}

.control-chain-diagram__placeholder h4 {
  margin: 18px 0 0;
  color: #172033;
  font-size: 18px;
}

.control-chain-diagram__placeholder p,
.placeholder-note {
  max-width: 460px;
  margin: 10px 0 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.placeholder-note {
  font-size: 13px;
}

.diagram-edge {
  fill: none;
  pointer-events: stroke;
}

.diagram-edge--primary {
  stroke: #be123c;
  stroke-width: 5;
  opacity: 0.94;
}

.diagram-edge--support {
  stroke: #64748b;
  stroke-width: 2.2;
  stroke-dasharray: 7 6;
  opacity: 0.58;
}

.diagram-edge--key {
  stroke-width: 3.4;
  opacity: 0.86;
}

.diagram-edge--semantic {
  stroke: #7c3aed;
  stroke-dasharray: 5 5;
}

.arrow--primary {
  fill: #be123c;
}

.arrow--support {
  fill: #64748b;
}

.diagram-node {
  cursor: default;
}

.node-ring {
  fill: rgba(190, 18, 60, 0.08);
  stroke: rgba(190, 18, 60, 0.3);
  stroke-width: 3;
}

.node-shape {
  stroke-width: 3;
  filter: drop-shadow(0 8px 16px rgba(20, 30, 43, 0.1));
}

.node-shape--actualController {
  stroke: #be123c;
}

.node-shape--focused {
  stroke: #7c3aed;
}

.node-shape--target {
  stroke: #172033;
}

.node-shape--intermediate,
.node-shape--support {
  stroke: #31536f;
}

.node-fill--company {
  fill: #dbeafe;
}

.node-fill--person {
  fill: #fee2e2;
}

.node-fill--fund {
  fill: #dcfce7;
}

.node-fill--government {
  fill: #ffedd5;
}

.node-fill--other {
  fill: #e2e8f0;
}

.node-initial {
  fill: #172033;
  font-size: 18px;
  font-weight: 800;
  pointer-events: none;
}

.node-label {
  fill: #24384d;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  pointer-events: none;
}

.control-chain-tooltip {
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

.control-chain-tooltip strong,
.control-chain-tooltip span {
  display: block;
}

.control-chain-tooltip strong {
  margin-bottom: 6px;
  font-size: 13px;
}

.control-chain-tooltip span {
  font-size: 12px;
  line-height: 1.55;
}

.control-chain-diagram__footnote {
  padding: 10px 12px;
  border-top: 1px solid rgba(31, 59, 87, 0.08);
  color: var(--text-secondary);
  font-size: 12px;
}

.control-chain-diagram__footnote strong {
  color: #be123c;
}

.control-chain-diagram__legend {
  padding: 12px;
}

.legend-block + .legend-block {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(31, 59, 87, 0.08);
}

.legend-block h4 {
  margin: 0 0 8px;
  color: var(--brand-ink);
  font-size: 14px;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.legend-block p {
  margin: 0 0 6px;
  color: #172033;
  font-size: 13px;
  font-weight: 700;
}

.legend-block span,
.legend-block dt {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.legend-block dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.legend-block dl div {
  display: grid;
  gap: 2px;
}

.legend-block dd {
  margin: 0;
  color: #172033;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.45;
  word-break: break-word;
}

.legend-row {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-height: 28px;
}

.legend-row + .legend-row {
  margin-top: 6px;
}

.legend-symbol {
  width: 16px;
  height: 16px;
  border-radius: 999px;
  border: 3px solid #31536f;
  background: #dbeafe;
}

.legend-symbol--actual {
  border-color: #be123c;
  box-shadow: 0 0 0 4px rgba(190, 18, 60, 0.12);
}

.legend-symbol--intermediate {
  border-color: #31536f;
}

.legend-symbol--target {
  width: 22px;
  border-radius: 6px;
  border-color: #172033;
}

.legend-line {
  width: 26px;
  border-top: 4px solid #be123c;
}

@media (max-width: 1180px) {
  .control-chain-diagram__main {
    grid-template-columns: 1fr;
  }

  .control-chain-diagram__legend {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
  }

  .legend-block + .legend-block {
    margin-top: 0;
    padding-top: 0;
    border-top: 0;
  }
}

@media (max-width: 760px) {
  .control-chain-diagram__header {
    display: grid;
  }

  .control-chain-diagram__legend {
    grid-template-columns: 1fr;
  }

  .control-chain-diagram__canvas {
    min-height: 440px;
  }
}
</style>
