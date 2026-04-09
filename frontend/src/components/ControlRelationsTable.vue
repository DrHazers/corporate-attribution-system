<script setup>
const props = defineProps({
  relationships: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
})

function formatRatio(value) {
  if (value === null || value === undefined || value === '') {
    return '暂无'
  }
  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return String(value)
  }
  return `${numeric.toFixed(2)}%`
}

function formatControlPath(controlPath) {
  if (!Array.isArray(controlPath) || !controlPath.length) {
    return '暂无'
  }

  const pathTexts = controlPath
    .map((path) =>
      Array.isArray(path?.path_entity_names) && path.path_entity_names.length
        ? path.path_entity_names.join(' -> ')
        : '',
    )
    .filter(Boolean)

  if (!pathTexts.length) {
    return '暂无'
  }

  const preview = pathTexts.slice(0, 2).join(' ｜ ')
  return pathTexts.length > 2 ? `${preview}（共 ${pathTexts.length} 条路径）` : preview
}

function formatBasis(basis) {
  if (!basis) {
    return '暂无'
  }

  if (typeof basis === 'string') {
    return basis
  }

  if (typeof basis === 'object') {
    return [
      basis.classification,
      basis.control_mode,
      basis.as_of,
      basis.path_count !== undefined ? `${basis.path_count} 条路径` : null,
    ]
      .filter(Boolean)
      .join(' | ')
  }

  return String(basis)
}
</script>

<template>
  <el-card class="surface-card" shadow="never">
    <template #header>
      <div class="section-heading">
        <div>
          <h2>控制关系表</h2>
          <p>展示综合分析接口返回的控制关系明细。</p>
        </div>
      </div>
    </template>

    <el-table
      v-loading="loading"
      :data="relationships"
      stripe
      border
      empty-text="暂无控制关系数据"
    >
      <el-table-column type="index" label="#" width="60" />
      <el-table-column prop="controller_name" label="Controller Name" min-width="200" />
      <el-table-column prop="controller_type" label="Controller Type" min-width="120" />
      <el-table-column prop="control_type" label="Control Type" min-width="140" />
      <el-table-column label="Control Ratio" min-width="120">
        <template #default="{ row }">
          {{ formatRatio(row.control_ratio) }}
        </template>
      </el-table-column>
      <el-table-column label="Control Path" min-width="280">
        <template #default="{ row }">
          <div class="table-text table-multi-line">
            {{ formatControlPath(row.control_path) }}
          </div>
        </template>
      </el-table-column>
      <el-table-column label="Actual Controller" min-width="120">
        <template #default="{ row }">
          <el-tag :type="row.is_actual_controller ? 'danger' : 'info'" effect="plain">
            {{ row.is_actual_controller ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Basis" min-width="220">
        <template #default="{ row }">
          <div class="table-text table-multi-line">
            {{ formatBasis(row.basis) }}
          </div>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>
