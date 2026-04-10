<script setup>
import { computed } from 'vue'

import ControlStructureDiagram from '@/components/ControlStructureDiagram.vue'
import ControlStructurePlaceholder from '@/components/ControlStructurePlaceholder.vue'

const ENABLE_REBUILT_CONTROL_STRUCTURE_DIAGRAM = false

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
const recognitionStatus = computed(() =>
  actualController.value !== '暂无' && actualControlCountry.value !== '未识别'
    ? '已识别'
    : '待补充',
)
</script>

<template>
  <el-card class="surface-card" shadow="never">
    <template #header>
      <div class="section-heading">
        <div>
          <h2>控制链与国别归属</h2>
          <p>上半区域预留新版控制结构示意图位置，下半区域保留控制分析摘要与国别归属说明。</p>
        </div>
      </div>
    </template>

    <div class="control-summary-grid">
      <div class="control-summary-card">
        <div class="control-summary-card__title">控制分析摘要</div>
        <dl class="compact-facts">
          <div>
            <dt>实际控制人</dt>
            <dd>{{ actualController }}</dd>
          </div>
          <div>
            <dt>控制主体类型</dt>
            <dd>{{ actualControllerType }}</dd>
          </div>
          <div>
            <dt>控制类型</dt>
            <dd>{{ actualControlType }}</dd>
          </div>
          <div>
            <dt>控制比例</dt>
            <dd>{{ actualControlRatio }}</dd>
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
            <dt>实际控制人</dt>
            <dd>{{ actualController }}</dd>
          </div>
          <div>
            <dt>实际控制地</dt>
            <dd>{{ actualControlCountry }}</dd>
          </div>
          <div>
            <dt>识别状态</dt>
            <dd>
              <el-tag :type="recognitionStatus === '已识别' ? 'success' : 'warning'" effect="plain">
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
      class="control-graph-wide"
      :company="company"
      :control-analysis="controlAnalysis"
      :country-attribution="countryAttribution"
      :relationship-graph="relationshipGraph"
    />
    <ControlStructurePlaceholder v-else class="control-graph-wide" />
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
