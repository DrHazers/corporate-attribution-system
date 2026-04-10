<script setup>
import { computed } from 'vue'

import RelationshipGraphCard from '@/components/RelationshipGraphCard.vue'

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

const actualController = computed(
  () => props.controlAnalysis?.actual_controller?.controller_name || '暂无',
)
const actualControllerType = computed(
  () => props.controlAnalysis?.actual_controller?.controller_type || '暂无',
)
const actualControlType = computed(
  () => props.controlAnalysis?.actual_controller?.control_type || '暂无',
)
const actualControllerEntityId = computed(
  () => props.controlAnalysis?.actual_controller?.controller_entity_id ?? null,
)
const actualControlRatio = computed(() => {
  const value = props.controlAnalysis?.actual_controller?.control_ratio
  if (value === null || value === undefined || value === '') {
    return '暂无'
  }

  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return String(value)
  }

  return `${numeric.toFixed(2)}%`
})

const attributionType = computed(
  () => props.countryAttribution?.attribution_type || '暂无',
)
</script>

<template>
  <el-card class="surface-card" shadow="never">
    <template #header>
      <div class="section-heading">
        <div>
          <h2>控制链与国别归属</h2>
          <p>上半区域展示真实关系图，下半区域保留控制分析摘要与国别归属说明。</p>
        </div>
      </div>
    </template>

    <RelationshipGraphCard
      :graph-data="relationshipGraph"
      :actual-controller-entity-id="actualControllerEntityId"
      :graph-error="graphError"
    />

    <div class="summary-block">
      <h3>控制分析摘要</h3>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="实际控制人">
          {{ actualController }}
        </el-descriptions-item>
        <el-descriptions-item label="控制主体类型">
          {{ actualControllerType }}
        </el-descriptions-item>
        <el-descriptions-item label="控制类型">
          {{ actualControlType }}
        </el-descriptions-item>
        <el-descriptions-item label="控制比例">
          {{ actualControlRatio }}
        </el-descriptions-item>
        <el-descriptions-item label="控制关系数量">
          {{ controlAnalysis?.controller_count ?? 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="实际控制地">
          {{ countryAttribution?.actual_control_country || '未识别' }}
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <div class="summary-block">
      <h3>国别归属补充说明</h3>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="注册地">
          {{ company?.incorporation_country || '暂无' }}
        </el-descriptions-item>
        <el-descriptions-item label="上市地">
          {{ company?.listing_country || '暂无' }}
        </el-descriptions-item>
        <el-descriptions-item label="实际控制地">
          {{ countryAttribution?.actual_control_country || '未识别' }}
        </el-descriptions-item>
        <el-descriptions-item label="归属类型">
          {{ attributionType }}
        </el-descriptions-item>
      </el-descriptions>
    </div>
  </el-card>
</template>

<style scoped>
.summary-block {
  margin-top: 18px;
}

.summary-block h3 {
  margin: 0 0 12px;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}
</style>
