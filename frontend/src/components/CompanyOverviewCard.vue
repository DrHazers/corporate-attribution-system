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
  manualEffective: {
    type: Boolean,
    default: false,
  },
  manualPanelExpanded: {
    type: Boolean,
    default: false,
  },
  resultSourceLabel: {
    type: String,
    default: '自动分析结果',
  },
})

const emit = defineEmits(['toggle-manual-panel'])

const displayController = computed(
  () => props.controlAnalysis?.display_controller || props.controlAnalysis?.actual_controller || null,
)
const controllerDisplayText = computed(() => {
  const name = displayController.value?.controller_name
  if (!name) {
    return '暂无'
  }
  return props.controlAnalysis?.display_controller_role === 'leading_candidate'
    ? `重点控制候选：${name}`
    : name
})
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
const manualButtonLabel = computed(() => {
  if (props.manualPanelExpanded) {
    return '收起人工征订'
  }
  return props.manualEffective ? '查看/校正' : '人工征订/校正'
})

const overviewItems = computed(() => [
  { label: '公司名称', value: props.company?.name || '暂无' },
  { label: 'Company ID', value: props.company?.id ?? '暂无' },
  { label: 'Stock Code', value: props.company?.stock_code || '暂无' },
  { label: '注册地', value: props.company?.incorporation_country || '暂无' },
  { label: '上市地', value: props.company?.listing_country || '暂无' },
  { label: '控制主体', value: controllerDisplayText.value },
  { label: '实际控制地', value: actualControlCountry.value },
  { label: '控制结论来源', value: props.resultSourceLabel || '自动分析结果' },
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
        <div class="overview-manual-entry">
          <el-button
            class="overview-manual-entry__button"
            size="small"
            plain
            @click="emit('toggle-manual-panel')"
          >
            {{ manualButtonLabel }}
          </el-button>
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
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.overview-manual-entry {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
}

.overview-manual-entry__button {
  border-radius: 8px;
}

.overview-grid__item {
  padding: 12px 14px;
  border-radius: 14px;
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
  margin-top: 6px;
  color: var(--brand-ink);
  font-size: 15px;
  font-weight: 600;
  line-height: 1.45;
  word-break: break-word;
}

.overview-warning {
  margin-top: 12px;
}

:deep(.el-card__body) {
  padding-top: 18px;
  padding-bottom: 18px;
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

  .overview-manual-entry {
    justify-content: flex-start;
  }
}

@media (max-width: 560px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
