<script setup>
import { computed } from 'vue'

const props = defineProps({
  industryAnalysis: {
    type: Object,
    default: () => ({}),
  },
})

const primarySegments = computed(() => props.industryAnalysis?.primary_segments || [])
const emergingSegments = computed(() => props.industryAnalysis?.emerging_segments || [])
const allIndustryLabels = computed(
  () => props.industryAnalysis?.all_industry_labels || [],
)
const qualityWarnings = computed(
  () => props.industryAnalysis?.quality_warnings || [],
)

const metrics = computed(() => [
  {
    label: '业务线数量',
    value: props.industryAnalysis?.business_segment_count ?? 0,
  },
  {
    label: '主产业',
    value: props.industryAnalysis?.primary_industries?.[0] || '未识别',
  },
  {
    label: '全部产业标签数量',
    value: allIndustryLabels.value.length,
  },
  {
    label: '是否人工修订',
    value: props.industryAnalysis?.has_manual_adjustment ? '是' : '否',
  },
  {
    label: '当前报告期',
    value: props.industryAnalysis?.selected_reporting_period || '暂无',
  },
])
</script>

<template>
  <el-card class="surface-card" shadow="never">
    <template #header>
      <div class="section-heading">
        <div>
          <h2>业务结构与产业标注</h2>
          <p>聚合展示产业摘要、主营业务、新兴业务与全部产业标签。</p>
        </div>
      </div>
    </template>

    <div class="industry-metrics">
      <div v-for="item in metrics" :key="item.label" class="industry-metrics__item">
        <div class="industry-metrics__label">{{ item.label }}</div>
        <div class="industry-metrics__value">{{ item.value }}</div>
      </div>
    </div>

    <div class="industry-lists">
      <div class="industry-list-card">
        <h3>主营业务</h3>
        <ul v-if="primarySegments.length" class="industry-list">
          <li v-for="segment in primarySegments" :key="segment.id">
            {{ segment.segment_name }}
          </li>
        </ul>
        <el-empty v-else description="暂无主营业务数据" :image-size="72" />
      </div>

      <div class="industry-list-card">
        <h3>新兴业务</h3>
        <ul v-if="emergingSegments.length" class="industry-list">
          <li v-for="segment in emergingSegments" :key="segment.id">
            {{ segment.segment_name }}
          </li>
        </ul>
        <el-empty v-else description="暂无新兴业务数据" :image-size="72" />
      </div>
    </div>

    <div class="industry-tags">
      <h3>产业分类标签</h3>
      <div v-if="allIndustryLabels.length" class="tag-cloud">
        <el-tag
          v-for="label in allIndustryLabels"
          :key="label"
          effect="plain"
          type="success"
        >
          {{ label }}
        </el-tag>
      </div>
      <el-empty v-else description="暂无产业标签" :image-size="72" />
    </div>

    <div v-if="qualityWarnings.length" class="industry-quality">
      <h3>质量提示</h3>
      <el-alert
        v-for="warning in qualityWarnings"
        :key="warning"
        class="industry-quality__alert"
        type="warning"
        :closable="false"
        show-icon
        :title="warning"
      />
    </div>
  </el-card>
</template>

<style scoped>
.industry-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.industry-metrics__item {
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(249, 251, 254, 0.92);
  border: 1px solid rgba(31, 59, 87, 0.08);
}

.industry-metrics__label {
  color: var(--text-secondary);
  font-size: 12px;
}

.industry-metrics__value {
  margin-top: 10px;
  color: var(--brand-ink);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.6;
}

.industry-lists {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
}

.industry-list-card {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(255, 255, 255, 0.82);
}

.industry-list-card h3,
.industry-tags h3,
.industry-quality h3 {
  margin: 0 0 12px;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.industry-list {
  margin: 0;
  padding-left: 18px;
  color: #314255;
  line-height: 1.8;
}

.industry-tags,
.industry-quality {
  margin-top: 18px;
}

.industry-quality__alert + .industry-quality__alert {
  margin-top: 10px;
}

@media (max-width: 640px) {
  .industry-metrics,
  .industry-lists {
    grid-template-columns: 1fr;
  }
}
</style>
