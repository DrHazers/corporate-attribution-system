<script setup>
import { computed } from 'vue'

const props = defineProps({
  company: {
    type: Object,
    default: null,
  },
  controlAnalysis: {
    type: Object,
    default: () => ({}),
  },
  countryAttribution: {
    type: Object,
    default: () => ({}),
  },
  industryAnalysis: {
    type: Object,
    default: () => ({}),
  },
})

const actualController = computed(
  () => props.controlAnalysis?.actual_controller?.controller_name || '暂无',
)
const actualControlCountry = computed(
  () => props.countryAttribution?.actual_control_country || '未识别',
)
const primaryIndustry = computed(
  () => props.industryAnalysis?.primary_industries?.[0] || '未识别',
)
const businessSegmentCount = computed(
  () => props.industryAnalysis?.business_segment_count ?? 0,
)
const warnings = computed(() => props.industryAnalysis?.quality_warnings || [])

const overviewItems = computed(() => [
  { label: '公司名称', value: props.company?.name || '暂无' },
  { label: 'Company ID', value: props.company?.id ?? '暂无' },
  { label: 'Stock Code', value: props.company?.stock_code || '暂无' },
  { label: '注册地', value: props.company?.incorporation_country || '暂无' },
  { label: '上市地', value: props.company?.listing_country || '暂无' },
  { label: '实际控制人', value: actualController.value },
  { label: '实际控制地', value: actualControlCountry.value },
  { label: '主产业', value: primaryIndustry.value },
  { label: '业务线数量', value: businessSegmentCount.value },
])
</script>

<template>
  <el-card class="surface-card" shadow="never">
    <template #header>
      <div class="section-heading">
        <div>
          <h2>公司总览</h2>
          <p>聚合展示公司基础信息、控制结果与当前产业分析摘要。</p>
        </div>
      </div>
    </template>

    <div class="overview-grid">
      <div v-for="item in overviewItems" :key="item.label" class="overview-grid__item">
        <div class="overview-grid__label">{{ item.label }}</div>
        <div class="overview-grid__value">{{ item.value }}</div>
      </div>
    </div>

    <el-alert
      v-if="warnings.length"
      class="overview-warning"
      type="warning"
      :closable="false"
      show-icon
      title="当前产业分析包含质量提示"
      :description="warnings.join('；')"
    />
  </el-card>
</template>

<style scoped>
.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.overview-grid__item {
  padding: 16px 18px;
  border-radius: 16px;
  background: rgba(249, 251, 254, 0.9);
  border: 1px solid rgba(31, 59, 87, 0.08);
}

.overview-grid__label {
  color: var(--text-secondary);
  font-size: 12px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.overview-grid__value {
  margin-top: 10px;
  color: var(--brand-ink);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.6;
  word-break: break-word;
}

.overview-warning {
  margin-top: 18px;
}

@media (max-width: 1200px) {
  .overview-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
