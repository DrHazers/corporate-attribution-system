<script setup>
import * as echarts from 'echarts'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { formatPercentNumber } from '@/utils/industryAnalysis'

const props = defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
})

const chartRef = ref(null)
let chartInstance = null
let resizeObserver = null

function buildSeriesData(metric) {
  return props.rows.map((row) => formatPercentNumber(row?.[metric]))
}

function renderChart() {
  if (!chartRef.value) {
    return
  }
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  chartInstance.setOption({
    animationDuration: 420,
    color: ['#28536b', '#a86a3d'],
    grid: {
      left: 42,
      right: 22,
      top: 28,
      bottom: 34,
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(18, 35, 52, 0.94)',
      borderColor: 'rgba(255,255,255,0.08)',
      textStyle: { color: '#f5f2eb' },
      valueFormatter(value) {
        return value === null || value === undefined ? '暂无' : `${Number(value).toFixed(2)}%`
      },
    },
    legend: {
      top: 0,
      right: 0,
      itemWidth: 10,
      itemHeight: 10,
      textStyle: {
        color: '#4b5c70',
        fontSize: 11,
      },
    },
    xAxis: {
      type: 'category',
      data: props.rows.map((row) => row.reporting_period || '暂无'),
      axisTick: { alignWithLabel: true },
      axisLabel: { color: '#667589', fontSize: 11 },
      axisLine: { lineStyle: { color: '#d7dde5' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: '#667589',
        fontSize: 11,
        formatter: '{value}%',
      },
      splitLine: { lineStyle: { color: 'rgba(31, 59, 87, 0.08)' } },
    },
    series: [
      {
        name: '收入占比',
        type: 'line',
        smooth: true,
        connectNulls: false,
        symbolSize: 7,
        data: buildSeriesData('revenue_ratio'),
      },
      {
        name: '利润占比',
        type: 'line',
        smooth: true,
        connectNulls: false,
        symbolSize: 7,
        data: buildSeriesData('profit_ratio'),
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

onBeforeUnmount(() => {
  disposeChart()
})
</script>

<template>
  <div ref="chartRef" class="segment-history-trend" />
</template>

<style scoped>
.segment-history-trend {
  width: 100%;
  height: 220px;
  min-width: 0;
}
</style>
