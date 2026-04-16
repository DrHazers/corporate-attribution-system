<script setup>
import { computed } from 'vue'

import ControlStructureDiagram from '@/components/ControlStructureDiagram.vue'
import ControlStructurePlaceholder from '@/components/ControlStructurePlaceholder.vue'

const ENABLE_REBUILT_CONTROL_STRUCTURE_DIAGRAM = true

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

const displayController = computed(
  () => props.controlAnalysis?.display_controller || props.controlAnalysis?.actual_controller || null,
)
const displayControllerRole = computed(
  () => props.controlAnalysis?.display_controller_role || (displayController.value ? 'actual_controller' : null),
)
const controllerRoleLabel = computed(() =>
  displayControllerRole.value === 'leading_candidate' ? '重点控制候选' : '实际控制人',
)
const controllerName = computed(
  () => displayController.value?.controller_name || '暂无',
)
const controllerType = computed(
  () => displayController.value?.controller_type || '暂无',
)
const controlType = computed(
  () => displayController.value?.control_type || '暂无',
)
const controlRatio = computed(() => {
  const value = displayController.value?.control_ratio
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
const actualControlCountry = computed(
  () => props.countryAttribution?.actual_control_country || '未识别',
)
const controlRelationshipCount = computed(
  () =>
    props.controlAnalysis?.controller_count ??
    props.controlAnalysis?.control_relationships?.length ??
    0,
)
const hasControlData = computed(() => controlRelationshipCount.value > 0)
const recognitionStatus = computed(() => {
  const status =
    props.controlAnalysis?.identification_status ||
    props.controlAnalysis?.controller_status

  if (status === 'actual_controller_identified') {
    return '已识别实际控制人'
  }
  if (status === 'no_actual_controller_but_leading_candidate_found') {
    return '已识别重点控制候选'
  }
  if (status === 'joint_control_identified') {
    return '存在共同控制信号'
  }
  return '暂无明确控制信号'
})
const recognitionTagType = computed(() => {
  if (recognitionStatus.value === '已识别实际控制人') {
    return 'success'
  }
  if (
    recognitionStatus.value === '已识别重点控制候选' ||
    recognitionStatus.value === '存在共同控制信号'
  ) {
    return 'warning'
  }
  return 'info'
})
</script>

<template>
  <el-card class="surface-card" shadow="never">
    <template #header>
      <div class="section-heading">
        <div>
          <h2>控制链与国别归属</h2>
          <p>上半区域展示新版控制结构示意图，下半区域保留控制分析摘要与国别归属说明。</p>
        </div>
      </div>
    </template>

    <div class="control-summary-grid">
      <div class="control-summary-card">
        <div class="control-summary-card__title">控制分析摘要</div>
        <dl class="compact-facts">
          <div>
            <dt>{{ controllerRoleLabel }}</dt>
            <dd>{{ controllerName }}</dd>
          </div>
          <div>
            <dt>控制主体类型</dt>
            <dd>{{ controllerType }}</dd>
          </div>
          <div>
            <dt>控制类型</dt>
            <dd>{{ controlType }}</dd>
          </div>
          <div>
            <dt>控制比例</dt>
            <dd>{{ controlRatio }}</dd>
          </div>
          <div>
            <dt>控制关系数量</dt>
            <dd>{{ controlRelationshipCount }}</dd>
          </div>
        </dl>
      </div>

      <div class="control-summary-card">
        <div class="control-summary-card__title">国别归属摘要</div>
        <dl class="compact-facts">
          <div>
            <dt>注册地</dt>
            <dd>{{ company?.incorporation_country || '暂无' }}</dd>
          </div>
          <div>
            <dt>上市地</dt>
            <dd>{{ company?.listing_country || '暂无' }}</dd>
          </div>
          <div>
            <dt>实际控制地</dt>
            <dd>{{ actualControlCountry }}</dd>
          </div>
          <div>
            <dt>归属类型</dt>
            <dd>{{ attributionType }}</dd>
          </div>
        </dl>
      </div>

      <div class="control-summary-card control-summary-card--emphasis">
        <div class="control-summary-card__title">关键结论</div>
        <dl class="compact-facts">
          <div>
            <dt>{{ controllerRoleLabel }}</dt>
            <dd>{{ controllerName }}</dd>
          </div>
          <div>
            <dt>实际控制地</dt>
            <dd>{{ actualControlCountry }}</dd>
          </div>
          <div>
            <dt>识别状态</dt>
            <dd>
              <el-tag :type="recognitionTagType" effect="plain">
                {{ recognitionStatus }}
              </el-tag>
            </dd>
          </div>
          <div>
            <dt>控制关系数据</dt>
            <dd>
              <el-tag :type="hasControlData ? 'success' : 'info'" effect="plain">
                {{ hasControlData ? '有数据' : '暂无数据' }}
              </el-tag>
            </dd>
          </div>
        </dl>
      </div>
    </div>

    <ControlStructureDiagram
      v-if="ENABLE_REBUILT_CONTROL_STRUCTURE_DIAGRAM"
      :company="company"
      :control-analysis="controlAnalysis"
      :country-attribution="countryAttribution"
      :relationship-graph="relationshipGraph"
    />
    <ControlStructurePlaceholder v-else />
  </el-card>
</template>

<style scoped>
.control-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.control-summary-card {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(249, 251, 254, 0.92);
}

.control-summary-card--emphasis {
  background:
    linear-gradient(135deg, rgba(255, 252, 247, 0.96), rgba(245, 249, 252, 0.94));
  border-color: rgba(139, 106, 61, 0.16);
}

.control-summary-card__title {
  margin-bottom: 12px;
  color: var(--brand-ink);
  font-weight: 700;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.compact-facts {
  display: grid;
  gap: 10px;
  margin: 0;
}

.compact-facts div {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.compact-facts dt {
  color: var(--text-secondary);
  font-size: 12px;
}

.compact-facts dd {
  margin: 0;
  color: var(--brand-ink);
  font-weight: 600;
  line-height: 1.45;
  word-break: break-word;
}

.control-graph-wide {
  margin-top: 18px;
}

@media (max-width: 1100px) {
  .control-summary-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .compact-facts div {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>
