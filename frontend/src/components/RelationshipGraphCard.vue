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
    actualControllerEntityId: props.actualControllerEntityId,
  }),
)

const fallbackNodeNames = computed(() =>
  adaptedGraph.value.nodes.slice(0, 8).map((node) => node.name),
)

function buildChartOption(model) {
  return {
    animationDuration: 900,
    animationEasingUpdate: 'quinticInOut',
    tooltip: {
      confine: true,
      backgroundColor: 'rgba(24, 34, 44, 0.92)',
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
        layout: 'force',
        roam: true,
        draggable: true,
        focusNodeAdjacency: true,
        selectedMode: false,
        symbol: 'circle',
        data: model.nodes,
        links: model.links,
        categories: model.categories,
        edgeSymbol: ['circle', 'arrow'],
        edgeSymbolSize: [4, 10],
        force: {
          repulsion: Math.max(320, model.nodeCount * 10),
          gravity: 0.08,
          edgeLength: [110, 220],
          friction: 0.08,
        },
        label: {
          show: true,
          position: 'right',
          distance: 8,
          fontSize: 11,
          color: '#24384d',
          width: 120,
          overflow: 'truncate',
          formatter: ({ data }) => data.displayLabel,
        },
        lineStyle: {
          opacity: 0.82,
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
    if (chartInstance.value) {
      chartInstance.value.clear()
    }
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
  resizeObserver.value = new ResizeObserver(() => {
    handleResize()
  })

  if (chartRef.value) {
    resizeObserver.value.observe(chartRef.value)
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
  () => [props.graphData, props.actualControllerEntityId],
  () => {
    renderError.value = ''
    void renderChart()
  },
  { deep: true },
)
</script>

<template>
  <div class="relationship-graph-card">
    <div class="relationship-graph-card__header">
      <div>
        <h3>控制链图</h3>
        <p>基于 <code>relationship-graph</code> 接口返回的节点与边数据生成。</p>
      </div>
      <div class="relationship-graph-card__stats">
        <div class="graph-stat">
          <span>目标主体</span>
          <strong>{{ adaptedGraph.targetCompanyName }}</strong>
        </div>
        <div class="graph-stat">
          <span>节点数</span>
          <strong>{{ adaptedGraph.nodeCount }}</strong>
        </div>
        <div class="graph-stat">
          <span>边数</span>
          <strong>{{ adaptedGraph.edgeCount }}</strong>
        </div>
      </div>
    </div>

    <div class="relationship-graph-card__legend">
      <el-tag effect="dark" color="#23577a">蓝色：目标公司</el-tag>
      <el-tag effect="dark" color="#b14d3f">红色：实际控制人</el-tag>
      <el-tag effect="plain" color="#8d9cab">灰蓝：其他主体</el-tag>
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
      v-else-if="adaptedGraph.message && !adaptedGraph.hasData"
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

    <div v-if="adaptedGraph.hasData && !renderError" ref="chartRef" class="relationship-graph-card__canvas" />

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
</template>

<style scoped>
.relationship-graph-card {
  padding: 18px;
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

.relationship-graph-card__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(90px, 1fr));
  gap: 10px;
  min-width: min(100%, 360px);
}

.graph-stat {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(248, 250, 253, 0.92);
  border: 1px solid rgba(31, 59, 87, 0.08);
}

.graph-stat span {
  display: block;
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.graph-stat strong {
  display: block;
  color: var(--brand-ink);
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
}

.relationship-graph-card__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.relationship-graph-card__alert {
  margin-top: 14px;
}

.relationship-graph-card__canvas {
  width: 100%;
  height: 460px;
  margin-top: 16px;
  border-radius: 18px;
  background:
    radial-gradient(circle at top, rgba(35, 87, 122, 0.06), transparent 38%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(247, 250, 253, 0.88));
}

.relationship-graph-card__fallback {
  margin-top: 16px;
  padding: 18px;
  border-radius: 16px;
  border: 1px dashed rgba(31, 59, 87, 0.2);
  background: rgba(255, 255, 255, 0.74);
}

.relationship-graph-card__fallback-text {
  margin: 0 0 12px;
  color: var(--text-secondary);
}

@media (max-width: 900px) {
  .relationship-graph-card__header {
    flex-direction: column;
  }

  .relationship-graph-card__stats {
    width: 100%;
  }
}

@media (max-width: 640px) {
  .relationship-graph-card__stats {
    grid-template-columns: 1fr;
  }

  .relationship-graph-card__canvas {
    height: 380px;
  }
}
</style>
