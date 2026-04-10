<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts/core'
import { TooltipComponent } from 'echarts/components'
import { GraphChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'

import {
  buildRelationshipGraphModel,
  formatEdgeTooltip,
  formatNodeTooltip,
} from '@/utils/graphAdapter'

echarts.use([TooltipComponent, GraphChart, CanvasRenderer])

const props = defineProps({
  graphData: {
    type: Object,
    default: () => ({
      nodes: [],
      edges: [],
      node_count: 0,
      edge_count: 0,
      message: '',
    }),
  },
  controlAnalysis: {
    type: Object,
    default: () => ({}),
  },
  countryAttribution: {
    type: Object,
    default: () => ({}),
  },
  actualControllerEntityId: {
    type: [Number, String, null],
    default: null,
  },
  graphError: {
    type: String,
    default: '',
  },
})

const chartRef = ref(null)
const chartInstance = shallowRef(null)
const resizeObserver = ref(null)
const renderError = ref('')

const adaptedGraph = computed(() =>
  buildRelationshipGraphModel(props.graphData, {
    controlAnalysis: props.controlAnalysis,
    countryAttribution: props.countryAttribution,
    actualControllerEntityId: props.actualControllerEntityId,
  }),
)

const fallbackNodeNames = computed(() =>
  adaptedGraph.value.nodes.slice(0, 10).map((node) => node.name),
)

const dataWarnings = computed(() => adaptedGraph.value.dataWarnings || [])

function buildChartOption(model) {
  return {
    animationDuration: 700,
    animationEasingUpdate: 'quinticInOut',
    tooltip: {
      confine: true,
      backgroundColor: 'rgba(24, 34, 44, 0.94)',
      borderWidth: 0,
      textStyle: {
        color: '#f7f9fb',
        fontSize: 12,
        lineHeight: 18,
      },
      formatter(params) {
        if (params.dataType === 'edge') {
          return formatEdgeTooltip(params.data)
        }
        return formatNodeTooltip(params.data)
      },
    },
    series: [
      {
        type: 'graph',
        layout: 'none',
        left: 4,
        right: 4,
        top: 4,
        bottom: 4,
        roam: true,
        zoom: model.layoutMeta?.preferredZoom ?? 0.9,
        scaleLimit: {
          min: model.layoutMeta?.scaleMin ?? 0.24,
          max: 3,
        },
        draggable: false,
        focusNodeAdjacency: true,
        selectedMode: false,
        data: model.nodes,
        links: model.links,
        categories: model.categories,
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 9],
        edgeLabel: {
          show: false,
        },
        label: {
          show: true,
          position: 'top',
          distance: 7,
          fontSize: 11,
          color: '#24384d',
          width: 132,
          overflow: 'truncate',
          formatter: ({ data }) => data.displayLabel,
        },
        labelLayout: {
          hideOverlap: true,
        },
        lineStyle: {
          opacity: 0.76,
        },
        emphasis: {
          focus: 'adjacency',
          scale: 1.08,
          lineStyle: {
            opacity: 1,
          },
          label: {
            show: true,
          },
        },
      },
    ],
  }
}

function ensureChartInstance() {
  if (!chartRef.value) {
    return null
  }

  if (!chartInstance.value) {
    chartInstance.value = echarts.init(chartRef.value)
  }

  return chartInstance.value
}

async function renderChart() {
  await nextTick()

  if (!adaptedGraph.value.hasData || renderError.value) {
    chartInstance.value?.clear()
    return
  }

  try {
    const instance = ensureChartInstance()
    if (!instance) {
      return
    }

    renderError.value = ''
    instance.setOption(buildChartOption(adaptedGraph.value), true)
    instance.resize()
  } catch (error) {
    renderError.value = error instanceof Error ? error.message : '关系图渲染失败。'
  }
}

function handleResize() {
  chartInstance.value?.resize()
}

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver.value = new ResizeObserver(() => {
      handleResize()
    })

    if (chartRef.value) {
      resizeObserver.value.observe(chartRef.value)
    }
  }

  window.addEventListener('resize', handleResize)
  void renderChart()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  resizeObserver.value?.disconnect()
  if (chartInstance.value) {
    chartInstance.value.dispose()
    chartInstance.value = null
  }
})

watch(
  () => [
    props.graphData,
    props.actualControllerEntityId,
    props.controlAnalysis,
    props.countryAttribution,
  ],
  () => {
    renderError.value = ''
    void renderChart()
  },
  { deep: true },
)

watch(
  dataWarnings,
  (warnings) => {
    warnings.forEach((warning) => {
      console.warn(`[RelationshipGraphCard] ${warning}`)
    })
  },
  { immediate: true },
)
</script>

<template>
  <div class="relationship-graph-card">
    <div class="relationship-graph-card__header">
      <div>
        <h3>控制链图</h3>
        <p>
          图中仅显示主体名称；详细实体、比例和路径信息通过 hover 查看。
        </p>
      </div>
    </div>

    <el-alert
      v-if="graphError"
      class="relationship-graph-card__alert"
      type="warning"
      :closable="false"
      show-icon
      :title="graphError"
    />

    <el-alert
      v-for="warning in dataWarnings"
      :key="warning"
      class="relationship-graph-card__alert"
      type="warning"
      :closable="false"
      show-icon
      :title="warning"
    />

    <el-alert
      v-if="!graphError && adaptedGraph.message && !adaptedGraph.hasData"
      class="relationship-graph-card__alert"
      type="info"
      :closable="false"
      show-icon
      :title="adaptedGraph.message"
    />

    <el-alert
      v-if="renderError"
      class="relationship-graph-card__alert"
      type="error"
      :closable="false"
      show-icon
      :title="`图组件渲染失败：${renderError}`"
    />

    <div class="relationship-graph-card__main">
      <div class="relationship-graph-card__stage">
        <div
          v-if="adaptedGraph.hasData && !renderError"
          ref="chartRef"
          class="relationship-graph-card__canvas"
        />

        <div v-else-if="adaptedGraph.hasData" class="relationship-graph-card__fallback">
          <p class="relationship-graph-card__fallback-text">
            已拿到关系图数据，但浏览器图形渲染失败，当前降级展示部分节点名称：
          </p>
          <div class="tag-cloud">
            <el-tag
              v-for="nodeName in fallbackNodeNames"
              :key="nodeName"
              effect="plain"
              type="info"
            >
              {{ nodeName }}
            </el-tag>
          </div>
        </div>

        <el-empty
          v-else
          description="当前企业暂无可展示的关系图数据"
          :image-size="88"
        />
      </div>

      <aside class="relationship-graph-card__legend" aria-label="control graph legend">
        <div class="legend-section">
          <h4>节点颜色 / 主体类型</h4>
          <div
            v-for="item in adaptedGraph.legend.entityTypes"
            :key="item.key"
            class="legend-row"
          >
            <span class="legend-dot" :style="{ backgroundColor: item.color }" />
            <div>
              <strong>{{ item.name }}</strong>
              <span>{{ item.label }}</span>
            </div>
          </div>
        </div>

        <div class="legend-section">
          <h4>节点角色</h4>
          <div
            v-for="item in adaptedGraph.legend.roles"
            :key="item.key"
            class="legend-row"
          >
            <span class="legend-role-ring" :style="{ borderColor: item.color }" />
            <div>
              <strong>{{ item.label }}</strong>
              <span>{{ item.description }}</span>
            </div>
          </div>
        </div>

        <div class="legend-section">
          <h4>边类型</h4>
          <div
            v-for="item in adaptedGraph.legend.edgeTypes"
            :key="item.key"
            class="legend-row"
          >
            <span
              class="legend-line"
              :style="{ borderTopColor: item.color, borderTopStyle: item.lineType }"
            />
            <div>
              <strong>{{ item.label }}</strong>
              <span>{{ item.description }}</span>
            </div>
          </div>
          <div class="legend-row">
            <span class="legend-line legend-line--key" />
            <div>
              <strong>key path</strong>
              <span>关键控制路径高亮</span>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.relationship-graph-card {
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.95), rgba(243, 247, 251, 0.94));
}

.relationship-graph-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.relationship-graph-card__header h3 {
  margin: 0;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.relationship-graph-card__header p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.relationship-graph-card__alert {
  margin-top: 14px;
}

.relationship-graph-card__main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 208px;
  gap: 10px;
  margin-top: 16px;
  align-items: stretch;
}

.relationship-graph-card__stage {
  min-width: 0;
  min-height: clamp(660px, 72vh, 800px);
  border-radius: 18px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background:
    radial-gradient(circle at 50% 8%, rgba(35, 87, 122, 0.08), transparent 38%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(247, 250, 253, 0.92));
  overflow: hidden;
}

.relationship-graph-card__canvas {
  width: 100%;
  height: clamp(660px, 72vh, 800px);
}

.relationship-graph-card__fallback {
  margin: 18px;
  padding: 18px;
  border-radius: 16px;
  border: 1px dashed rgba(31, 59, 87, 0.2);
  background: rgba(255, 255, 255, 0.74);
}

.relationship-graph-card__fallback-text {
  margin: 0 0 12px;
  color: var(--text-secondary);
}

.relationship-graph-card__legend {
  padding: 12px;
  border-radius: 18px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  background: rgba(255, 255, 255, 0.82);
}

.legend-section + .legend-section {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid rgba(31, 59, 87, 0.08);
}

.legend-section h4 {
  margin: 0 0 10px;
  color: var(--brand-ink);
  font-size: 14px;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.legend-row {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-height: 28px;
}

.legend-row + .legend-row {
  margin-top: 8px;
}

.legend-row strong {
  display: block;
  color: #25364a;
  font-size: 12px;
  line-height: 1.35;
}

.legend-row span:last-child {
  display: block;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.35;
}

.legend-dot {
  width: 14px;
  height: 14px;
  border-radius: 999px;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.86), 0 0 0 3px rgba(31, 59, 87, 0.08);
}

.legend-role-ring {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  border: 4px solid;
  background: rgba(248, 250, 252, 0.96);
}

.legend-line {
  width: 26px;
  border-top-width: 3px;
  border-top-style: solid;
}

.legend-line--key {
  border-top-color: #be123c;
  border-top-width: 4px;
}

@media (max-width: 1180px) {
  .relationship-graph-card__main {
    grid-template-columns: 1fr;
  }

  .relationship-graph-card__legend {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 16px;
  }

  .legend-section + .legend-section {
    margin-top: 0;
    padding-top: 0;
    border-top: 0;
  }
}

@media (max-width: 760px) {
  .relationship-graph-card__legend {
    grid-template-columns: 1fr;
  }

  .relationship-graph-card__stage {
    min-height: 420px;
  }

  .relationship-graph-card__canvas {
    height: 420px;
  }
}
</style>
