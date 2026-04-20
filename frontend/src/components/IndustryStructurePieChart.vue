<script setup>
import * as echarts from 'echarts'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
  title: {
    type: String,
    default: '业务结构饼图',
  },
  metricLabel: {
    type: String,
    default: '收入占比',
  },
  emptyDescription: {
    type: String,
    default: '当前缺少可用于绘制结构图的比例数据',
  },
})

const chartRef = ref(null)
let chartInstance = null
let resizeObserver = null

function renderChart() {
  if (!chartRef.value) {
    return
  }

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const colors = ['#28536b', '#a86a3d', '#4f7d73', '#c08a3e', '#7a5c61', '#4f6d9c', '#909cad']
  chartInstance.setOption({
    color: colors,
    animationDuration: 450,
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(18, 35, 52, 0.94)',
      borderColor: 'rgba(255,255,255,0.08)',
      textStyle: {
        color: '#f5f2eb',
      },
      formatter(params) {
        const item = params.data
        return `
          <div style="display:grid;gap:6px;min-width:220px">
            <strong style="font-size:14px">${item.rawName || item.name}</strong>
            <span>${props.metricLabel}: ${Number(item.value).toFixed(2)}%</span>
            <span>业务类型: ${item.segmentType || '未标注'}</span>
            <span style="line-height:1.5">分类: ${item.classificationSummary || '待补充'}</span>
          </div>
        `
      },
    },
    legend: {
      type: 'scroll',
      orient: 'horizontal',
      left: 'center',
      bottom: 6,
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 14,
      textStyle: {
        color: '#4b5c70',
        fontSize: 11,
        lineHeight: 16,
      },
    },
    series: [
      {
        name: props.metricLabel,
        type: 'pie',
        radius: ['44%', '64%'],
        center: ['50%', '40%'],
        minAngle: 4,
        avoidLabelOverlap: true,
        itemStyle: {
          borderColor: '#fffaf2',
          borderWidth: 2,
          borderRadius: 6,
        },
        label: {
          color: '#314255',
          fontSize: 11,
          lineHeight: 16,
          formatter: '{b}\n{d}%',
        },
        labelLine: {
          length: 10,
          length2: 8,
        },
        data: props.rows,
      },
    ],
  })
}

function disposeChart() {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
}

onMounted(async () => {
  await nextTick()
  renderChart()
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => {
      chartInstance?.resize()
    })
    resizeObserver.observe(chartRef.value)
  }
})

watch(
  () => props.rows,
  async () => {
    await nextTick()
    renderChart()
  },
  { deep: true },
)

watch(
  () => props.metricLabel,
  async () => {
    await nextTick()
    renderChart()
  },
)

onBeforeUnmount(() => {
  disposeChart()
})
</script>

<template>
  <div class="industry-pie">
    <div v-if="rows.length" ref="chartRef" class="industry-pie__canvas" />
    <el-empty
      v-else
      class="industry-pie__empty"
      :description="emptyDescription"
      :image-size="88"
    />
  </div>
</template>

<style scoped>
.industry-pie {
  min-height: 316px;
  min-width: 0;
}

.industry-pie__canvas {
  width: 100%;
  height: 316px;
}

.industry-pie__empty {
  min-height: 316px;
  display: grid;
  place-items: center;
  border-radius: 18px;
  border: 1px dashed rgba(31, 59, 87, 0.16);
  background: rgba(255, 255, 255, 0.55);
}
</style>
