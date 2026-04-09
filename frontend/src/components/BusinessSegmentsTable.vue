<script setup>
const props = defineProps({
  segments: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
})

function formatFlexiblePercent(value) {
  if (value === null || value === undefined || value === '') {
    return '暂无'
  }
  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return String(value)
  }
  const normalized = numeric <= 1 ? numeric * 100 : numeric
  return `${normalized.toFixed(2)}%`
}

function formatConfidence(value) {
  if (value === null || value === undefined || value === '') {
    return '暂无'
  }
  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return String(value)
  }
  return numeric.toFixed(2)
}

function formatClassificationLabels(row) {
  return row?.classification_labels?.length
    ? row.classification_labels.join(' ｜ ')
    : '暂无'
}

function getReviewStatuses(row) {
  const statuses = [...new Set((row?.classifications || []).map((item) => item.review_status).filter(Boolean))]
  return statuses
}

function segmentTagType(segmentType) {
  return (
    {
      primary: 'primary',
      secondary: 'info',
      emerging: 'warning',
      other: '',
    }[segmentType] || 'info'
  )
}
</script>

<template>
  <el-card class="surface-card" shadow="never">
    <template #header>
      <div class="section-heading">
        <div>
          <h2>业务线与产业分类明细表</h2>
          <p>展示当前选中报告期下的业务线、比例信息、分类标签与审核状态。</p>
        </div>
      </div>
    </template>

    <el-table
      v-loading="loading"
      :data="segments"
      stripe
      border
      empty-text="暂无业务线数据"
    >
      <el-table-column type="index" label="#" width="60" />
      <el-table-column prop="segment_name" label="Segment Name" min-width="180" />
      <el-table-column label="Segment Type" min-width="120">
        <template #default="{ row }">
          <el-tag :type="segmentTagType(row.segment_type)" effect="plain">
            {{ row.segment_type || '暂无' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Revenue Ratio" min-width="120">
        <template #default="{ row }">
          {{ formatFlexiblePercent(row.revenue_ratio) }}
        </template>
      </el-table-column>
      <el-table-column label="Profit Ratio" min-width="120">
        <template #default="{ row }">
          {{ formatFlexiblePercent(row.profit_ratio) }}
        </template>
      </el-table-column>
      <el-table-column prop="reporting_period" label="Reporting Period" min-width="140" />
      <el-table-column label="Classification Labels" min-width="320">
        <template #default="{ row }">
          <div class="table-text table-multi-line">
            {{ formatClassificationLabels(row) }}
          </div>
        </template>
      </el-table-column>
      <el-table-column label="Review Status" min-width="180">
        <template #default="{ row }">
          <div v-if="getReviewStatuses(row).length" class="tag-cloud">
            <el-tag
              v-for="status in getReviewStatuses(row)"
              :key="status"
              effect="plain"
              type="success"
            >
              {{ status }}
            </el-tag>
          </div>
          <span v-else class="table-text table-text--muted">暂无</span>
        </template>
      </el-table-column>
      <el-table-column label="Confidence" min-width="110">
        <template #default="{ row }">
          {{ formatConfidence(row.confidence) }}
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>
