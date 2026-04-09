<script setup>
import { computed } from 'vue'

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
const graphNodePreview = computed(
  () => props.relationshipGraph?.nodes?.slice(0, 6) || [],
)
</script>

<template>
  <el-card class="surface-card" shadow="never">
    <template #header>
      <div class="section-heading">
        <div>
          <h2>控制链与国别归属</h2>
          <p>当前先展示控制图占位区、控制摘要与国别归属说明。</p>
        </div>
      </div>
    </template>

    <div class="graph-placeholder">
      <div class="graph-placeholder__title-row">
        <h3>控制链图</h3>
        <el-tag effect="plain" type="info">占位展示</el-tag>
      </div>
      <p class="graph-placeholder__text">
        后续接入控制链图展示。当前已接入关系图数据，可展示节点数、边数与目标实体信息。
      </p>

      <div class="graph-placeholder__metrics">
        <div class="graph-metric">
          <span class="graph-metric__label">节点数</span>
          <strong>{{ relationshipGraph?.node_count ?? 0 }}</strong>
        </div>
        <div class="graph-metric">
          <span class="graph-metric__label">边数</span>
          <strong>{{ relationshipGraph?.edge_count ?? 0 }}</strong>
        </div>
        <div class="graph-metric">
          <span class="graph-metric__label">目标实体</span>
          <strong>{{ relationshipGraph?.target_entity_id ?? '暂无' }}</strong>
        </div>
      </div>

      <div v-if="graphNodePreview.length" class="tag-cloud">
        <el-tag
          v-for="node in graphNodePreview"
          :key="node.entity_id"
          effect="plain"
          :type="node.is_root ? 'primary' : 'info'"
        >
          {{ node.name }}
        </el-tag>
      </div>

      <el-alert
        v-if="relationshipGraph?.message || graphError"
        class="graph-placeholder__alert"
        type="info"
        :closable="false"
        show-icon
        :title="graphError || relationshipGraph?.message"
      />
    </div>

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
.graph-placeholder {
  padding: 18px;
  border-radius: 18px;
  border: 1px dashed rgba(31, 59, 87, 0.22);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(244, 248, 252, 0.92));
}

.graph-placeholder__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.graph-placeholder__title-row h3,
.summary-block h3 {
  margin: 0 0 12px;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.graph-placeholder__text {
  margin: 12px 0 18px;
  color: var(--text-secondary);
}

.graph-placeholder__metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.graph-metric {
  padding: 14px;
  border-radius: 14px;
  background: rgba(248, 250, 253, 0.92);
  border: 1px solid rgba(31, 59, 87, 0.08);
}

.graph-metric__label {
  display: block;
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.graph-metric strong {
  color: var(--brand-ink);
  font-size: 20px;
}

.graph-placeholder__alert {
  margin-top: 16px;
}

.summary-block {
  margin-top: 18px;
}

@media (max-width: 640px) {
  .graph-placeholder__metrics {
    grid-template-columns: 1fr;
  }
}
</style>
