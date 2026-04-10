<script setup>
import { computed, ref } from 'vue'

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

const diagramModel = computed(() =>
  buildControlStructureModel({
    company: props.company,
    controlAnalysis: props.controlAnalysis,
    countryAttribution: props.countryAttribution,
    relationshipGraph: props.relationshipGraph,
  }),
)

const diagramLayout = computed(() =>
  diagramModel.value.hasDiagram ? computeControlStructureLayout(diagramModel.value) : null,
)

const canvasStyle = computed(() => {
  if (!diagramLayout.value) {
    return {}
  }

  return {
    minHeight: `${diagramLayout.value.canvasHeight}px`,
  }
})

function clearHover() {
  hoverCard.value = null
}

function showHover(event, item) {
  const rect = stageRef.value?.getBoundingClientRect()
  if (!rect || !item) {
    return
  }

  hoverCard.value = {
    title: item.name || item.relationType || 'control relation',
    lines: buildTooltipLines(item),
    x: event.clientX - rect.left + 14,
    y: event.clientY - rect.top + 14,
  }
}

function buildTooltipLines(item) {
  if (item.source && item.target) {
    return [
      item.isPrimary ? '关键控制路径' : '控制关系',
      `关系类型：${item.relationType}`,
      item.controlRatio !== null && item.controlRatio !== undefined
        ? `控制比例：${Number(item.controlRatio).toFixed(2)}%`
        : null,
    ].filter(Boolean)
  }

  return [
    `主体类型：${item.entityType}`,
    `节点角色：${item.role}`,
    item.controlType ? `控制类型：${item.controlType}` : null,
    item.controlRatio !== null && item.controlRatio !== undefined
      ? `控制比例：${Number(item.controlRatio).toFixed(2)}%`
      : null,
  ].filter(Boolean)
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
  const maxChars = 14
  const lines = []
  for (let index = 0; index < text.length && lines.length < 2; index += maxChars) {
    lines.push(text.slice(index, index + maxChars))
  }
  if (text.length > maxChars * 2) {
    lines[1] = `${lines[1].slice(0, maxChars - 1)}…`
  }
  return lines
}

function nodeRectX(node) {
  return -node.width / 2
}

function nodeRectY(node) {
  return -node.height / 2
}
</script>

<template>
  <section class="control-structure-diagram">
    <header class="control-structure-diagram__header">
      <div>
        <h3>主要控制结构图</h3>
        <p>summary-first 结构示意图：强主链、硬分层、弱网络感。</p>
      </div>
      <el-tag effect="plain" type="danger">{{ diagramModel.displayMode || 'summary-first' }}</el-tag>
    </header>

    <div class="control-structure-diagram__main">
      <section class="control-structure-diagram__stage">
        <div v-if="!diagramModel.hasDiagram" class="control-structure-diagram__empty">
          <strong>{{ diagramModel.placeholderTitle }}</strong>
          <span>{{ diagramModel.placeholderDescription }}</span>
        </div>

        <div
          v-else
          ref="stageRef"
          class="control-structure-diagram__canvas"
          :style="canvasStyle"
          @mouseleave="clearHover"
        >
          <svg
            class="control-structure-diagram__svg"
            :viewBox="`0 0 ${diagramLayout.width} ${diagramLayout.height}`"
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="control structure diagram"
          >
            <g class="structure-edges">
              <path
                v-for="edge in diagramLayout.edges"
                :key="edge.id"
                :d="edge.path"
                :class="[
                  'structure-edge',
                  `structure-edge--${edge.relationType}`,
                  edge.isPrimary ? 'structure-edge--primary' : '',
                  edge.isKeyPath ? 'structure-edge--key' : '',
                ]"
                @mousemove="showHover($event, edge)"
              />
            </g>

            <g class="structure-nodes">
              <g
                v-for="node in diagramLayout.nodes"
                :key="node.id"
                :transform="`translate(${node.x}, ${node.y})`"
                :class="['structure-node', `structure-node--${node.role}`]"
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
                    :key="`${node.id}-${index}`"
                    x="0"
                    :dy="index === 0 ? -4 : 15"
                  >
                    {{ line }}
                  </tspan>
                </text>
              </g>
            </g>
          </svg>

          <div v-if="hoverCard" class="control-structure-tooltip" :style="hoverCardStyle()">
            <strong>{{ hoverCard.title }}</strong>
            <span v-for="line in hoverCard.lines" :key="line">{{ line }}</span>
          </div>
        </div>

        <div v-if="diagramModel.hasDiagram" class="control-structure-diagram__footnote">
          target company 位于底部中心；actual controller 与 key path 作为主链高亮展示。
          <strong>{{ diagramModel.omittedRelationshipCount || 0 }}</strong>
          条低优先级控制关系未进入默认图。
        </div>
      </section>

      <aside class="control-structure-diagram__legend" aria-label="control structure legend">
        <div class="legend-block">
          <h4>节点颜色 / 主体类型</h4>
          <div class="legend-row">
            <span class="legend-dot legend-dot--company" />
            <span><strong>company</strong>公司主体</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--person" />
            <span><strong>person</strong>自然人</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--fund" />
            <span><strong>fund</strong>基金/公众持股</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--government" />
            <span><strong>government</strong>政府/主权主体</span>
          </div>
          <div class="legend-row">
            <span class="legend-dot legend-dot--other" />
            <span><strong>other</strong>其他主体</span>
          </div>
        </div>

        <div class="legend-block">
          <h4>节点角色</h4>
          <div class="legend-row">
            <span class="legend-role legend-role--target" />
            <span><strong>target company</strong>目标公司</span>
          </div>
          <div class="legend-row">
            <span class="legend-role legend-role--focused" />
            <span><strong>focused controller / candidate</strong>当前关注控制人/候选控制人</span>
          </div>
          <div class="legend-row">
            <span class="legend-role legend-role--actual" />
            <span><strong>actual controller</strong>实际控制人</span>
          </div>
        </div>

        <div class="legend-block">
          <h4>边类型</h4>
          <div class="legend-line-row"><span class="legend-line legend-line--equity" /><span>equity</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--agreement" /><span>agreement</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--board" /><span>board_control</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--voting" /><span>voting_right</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--nominee" /><span>nominee</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--vie" /><span>vie</span></div>
          <div class="legend-line-row"><span class="legend-line legend-line--key" /><span>key path</span></div>
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
}

.control-structure-diagram__main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 230px;
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

.control-structure-diagram__empty {
  display: grid;
  place-items: center;
  min-height: 520px;
  color: var(--text-secondary);
  text-align: center;
}

.control-structure-diagram__empty strong,
.control-structure-diagram__empty span {
  display: block;
}

.structure-edge {
  fill: none;
  stroke: #111827;
  stroke-width: 2;
  opacity: 0.72;
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
  stroke-dasharray: 3 4;
}

.structure-edge--nominee {
  stroke: #be185d;
}

.structure-edge--vie {
  stroke: #0891b2;
}

.structure-edge--key,
.structure-edge--primary {
  stroke: #be123c;
  stroke-width: 4.6;
  opacity: 0.96;
}

.structure-node__box {
  stroke: #334155;
  stroke-width: 1.6;
  filter: drop-shadow(0 8px 16px rgba(15, 23, 42, 0.1));
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
  stroke: #0f172a;
  stroke-width: 4;
}

.structure-node__box--role-actualController {
  stroke: #be123c;
  stroke-width: 5;
}

.structure-node__box--role-focused {
  stroke: #7c3aed;
  stroke-width: 4;
}

.structure-node__label {
  fill: #f8fafc;
  font-size: 12px;
  font-weight: 700;
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
}

.control-structure-diagram__footnote strong {
  color: #be123c;
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
.legend-line-row {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-height: 28px;
}

.legend-row + .legend-row,
.legend-line-row + .legend-line-row {
  margin-top: 7px;
}

.legend-row span:last-child,
.legend-line-row span:last-child {
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

.legend-role--target {
  border-color: #0f172a;
}

.legend-role--focused {
  border-color: #7c3aed;
}

.legend-role--actual {
  border-color: #be123c;
}

.legend-line {
  width: 28px;
  border-top: 3px solid #111827;
}

.legend-line--agreement,
.legend-line--nominee,
.legend-line--vie {
  border-top-style: dashed;
}

.legend-line--agreement {
  border-top-color: #7c3aed;
}

.legend-line--board {
  border-top-color: #ea580c;
}

.legend-line--voting {
  border-top-color: #0f766e;
  border-top-style: dotted;
}

.legend-line--nominee {
  border-top-color: #be185d;
}

.legend-line--vie {
  border-top-color: #0891b2;
}

.legend-line--key {
  border-top-color: #be123c;
  border-top-width: 4px;
}

@media (max-width: 1180px) {
  .control-structure-diagram__main {
    grid-template-columns: 1fr;
  }

  .control-structure-diagram__legend {
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
  .control-structure-diagram__header {
    display: grid;
  }

  .control-structure-diagram__legend {
    grid-template-columns: 1fr;
  }

  .control-structure-diagram__canvas {
    min-height: 460px;
  }
}
</style>
