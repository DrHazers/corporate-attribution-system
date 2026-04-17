<script setup>
import { computed, reactive, watch } from 'vue'

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

const EMPTY_TEXT = '—'
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

const ENTITY_TYPE_LABELS = {
  company: '公司主体',
  person: '自然人',
  fund: '基金 / 公众持股',
  government: '政府 / 国资主体',
  other: '其他主体',
}

const CONTROL_TYPE_LABELS = {
  equity: '股权控制',
  equity_control: '股权控制',
  direct_equity_control: '股权控制',
  indirect_equity_control: '股权控制',
  significant_influence: '重大影响',
  agreement: '协议控制',
  agreement_control: '协议控制',
  board_control: '董事会/席位控制',
  voting_right: '表决权安排',
  voting_right_control: '表决权安排',
  nominee: '代持/名义持有人',
  nominee_control: '代持/名义持有人',
  vie: 'VIE结构',
  vie_control: 'VIE结构',
  mixed_control: '混合控制',
  joint_control: '共同控制',
  unknown: EMPTY_TEXT,
  null: EMPTY_TEXT,
}

const BASIS_MODE_LABELS = {
  numeric: '数值计算',
  semantic: '语义规则',
  mixed: '综合判断',
  sum_cap: '路径汇总',
}

const BASIS_TEXT_LABELS = {
  auto: '自动生成',
  'legacy auto': '历史自动结果',
  'manual control': '人工认定',
  ownership_penetration: '股权穿透分析',
  unified_control_inference_v1: '统一控制推断',
}

const expandedPathRows = reactive({})

watch(
  () => props.relationships,
  () => {
    Object.keys(expandedPathRows).forEach((key) => {
      delete expandedPathRows[key]
    })
  },
  { deep: false },
)

const sortedRelationships = computed(() =>
  [...props.relationships]
    .map((relationship, index) => ({
      ...relationship,
      _tableKey: buildRelationshipKey(relationship, index),
      _sourceIndex: index,
    }))
    .sort((left, right) => {
      const actualPriority = Number(Boolean(right.is_actual_controller)) - Number(Boolean(left.is_actual_controller))
      if (actualPriority !== 0) {
        return actualPriority
      }

      const ratioPriority = sortRatioValue(right.control_ratio) - sortRatioValue(left.control_ratio)
      if (ratioPriority !== 0) {
        return ratioPriority
      }

      return left._sourceIndex - right._sourceIndex
    }),
)

function buildRelationshipKey(relationship, index) {
  return [
    relationship?.id,
    relationship?.controller_entity_id,
    relationship?.controller_name,
    index,
  ]
    .filter((item) => item !== null && item !== undefined && item !== '')
    .join('-')
}

function normalizeKey(value) {
  return String(value ?? '').trim().toLowerCase()
}

function tryParseJson(value) {
  if (typeof value !== 'string') {
    return value
  }

  const trimmed = value.trim()
  if (!trimmed || !['{', '['].includes(trimmed[0])) {
    return value
  }

  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function toPercentNumber(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return null
  }

  return numeric <= 1 ? numeric * 100 : numeric
}

function sortRatioValue(value) {
  return toPercentNumber(value) ?? -1
}

function formatRatio(value) {
  const numeric = toPercentNumber(value)
  return numeric === null ? EMPTY_TEXT : `${numeric.toFixed(2)}%`
}

function controllerTypeLabel(value) {
  const normalized = normalizeKey(value)
  return ENTITY_TYPE_LABELS[normalized] || ENTITY_TYPE_LABELS.other
}

function controlTypeLabel(value) {
  const normalized = normalizeKey(value)
  if (!normalized || normalized === 'unknown' || normalized === 'null') {
    return EMPTY_TEXT
  }
  return CONTROL_TYPE_LABELS[normalized] || '未识别类型'
}

function basisModeLabel(value) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return ''
  }
  return BASIS_MODE_LABELS[normalized] || BASIS_TEXT_LABELS[normalized] || String(value).trim()
}

function basisTextLabel(value) {
  const normalized = normalizeKey(value)
  if (!normalized) {
    return ''
  }
  return BASIS_TEXT_LABELS[normalized] || String(value).trim()
}

function getControlPaths(controlPath) {
  const parsed = tryParseJson(controlPath)
  return Array.isArray(parsed) ? parsed : []
}

function buildPathText(path) {
  if (!path) {
    return ''
  }

  const nameList = Array.isArray(path.path_entity_names) ? path.path_entity_names.filter(Boolean) : []
  if (nameList.length) {
    return nameList.join(' → ')
  }

  const idList = Array.isArray(path.path_entity_ids) ? path.path_entity_ids.filter(Boolean) : []
  if (idList.length) {
    return idList.map((id) => `主体 ${id}`).join(' → ')
  }

  return ''
}

function pathScoreText(path) {
  return formatRatio(path?.path_score_pct ?? path?.path_score)
}

function pathSummary(row) {
  const paths = getControlPaths(row.control_path)
  const primaryPathText = paths.length ? buildPathText(paths[0]) : ''

  return {
    paths,
    pathCount: paths.length,
    primaryPathText: primaryPathText || EMPTY_TEXT,
    extraPathCount: Math.max(paths.length - 1, 0),
    hasMultiplePaths: paths.length > 1,
  }
}

function togglePath(row) {
  expandedPathRows[row._tableKey] = !expandedPathRows[row._tableKey]
}

function isPathExpanded(row) {
  return Boolean(expandedPathRows[row._tableKey])
}

function basisLinesFromObject(row, basis) {
  const lines = []
  const inferredPathCount = getControlPaths(row.control_path).length
  const pathCount = basis.path_count ?? inferredPathCount

  if (basis.classification || row.control_type) {
    lines.push({
      label: '认定类型',
      value: controlTypeLabel(basis.classification || row.control_type),
    })
  }

  if (basis.control_mode || basis.aggregator) {
    lines.push({
      label: '依据方式',
      value: basisModeLabel(basis.control_mode || basis.aggregator),
    })
  }

  if (basis.as_of) {
    lines.push({
      label: '分析日期',
      value: basis.as_of,
    })
  }

  if (pathCount) {
    lines.push({
      label: '路径数量',
      value: `${pathCount}条`,
    })
  }

  if (!lines.length && basis.analysis) {
    lines.push({
      label: '依据说明',
      value: basisTextLabel(basis.analysis),
    })
  }

  return lines
}

function basisLinesFromString(value) {
  const trimmed = String(value ?? '').trim()
  if (!trimmed) {
    return []
  }

  const segments = trimmed.split('|').map((segment) => segment.trim()).filter(Boolean)
  if (segments.length <= 1) {
    return [
      {
        label: '依据说明',
        value: basisTextLabel(trimmed),
      },
    ]
  }

  return segments.map((segment) => {
    const normalized = normalizeKey(segment)

    if (CONTROL_TYPE_LABELS[normalized]) {
      return {
        label: '认定类型',
        value: controlTypeLabel(segment),
      }
    }

    if (BASIS_MODE_LABELS[normalized] || BASIS_TEXT_LABELS[normalized]) {
      return {
        label: '依据方式',
        value: basisModeLabel(segment),
      }
    }

    if (DATE_PATTERN.test(segment)) {
      return {
        label: '分析日期',
        value: segment,
      }
    }

    if (/^\d+\s*(条路径|paths?)$/i.test(segment)) {
      return {
        label: '路径数量',
        value: segment.replace(/\s*paths?$/i, '条').replace(/\s+/g, ''),
      }
    }

    return {
      label: '依据说明',
      value: basisTextLabel(segment),
    }
  })
}

function basisLines(row) {
  const parsed = tryParseJson(row.basis)

  if (!parsed) {
    return []
  }

  if (typeof parsed === 'object' && !Array.isArray(parsed)) {
    return basisLinesFromObject(row, parsed)
  }

  return basisLinesFromString(parsed)
}

function relationshipRoleLabel(row) {
  if (row?.is_actual_controller) {
    return '实际控制人'
  }
  if (row?.is_leading_candidate) {
    return '重点控制候选'
  }
  if (normalizeKey(row?.controller_status) === 'joint_control_identified') {
    return '共同控制'
  }
  return ''
}

function relationshipRoleClass(row) {
  if (row?.is_actual_controller) {
    return 'actual'
  }
  if (row?.is_leading_candidate) {
    return 'leading'
  }
  if (normalizeKey(row?.controller_status) === 'joint_control_identified') {
    return 'joint'
  }
  return 'neutral'
}

function rowClassName({ row }) {
  return row.is_actual_controller ? 'control-relations-table__row--actual' : ''
}
</script>

<template>
  <el-card class="surface-card" shadow="never">
    <template #header>
      <div class="section-heading">
        <div>
          <h2>控制结论明细表</h2>
          <p>展示主要控制主体、控制方式、控制路径摘要与认定依据，便于结合上方控制结构图进行讲解。</p>
        </div>
      </div>
    </template>

    <el-table
      v-loading="loading"
      :data="sortedRelationships"
      :row-key="(row) => row._tableKey"
      :row-class-name="rowClassName"
      class="control-relations-table"
      stripe
      border
      empty-text="暂无控制结论数据"
    >
      <el-table-column type="index" label="序号" width="72" align="center" />

      <el-table-column label="控制主体" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <div class="controller-name-cell">
            <div class="controller-name">
              {{ row.controller_name || EMPTY_TEXT }}
            </div>
            <span
              v-if="relationshipRoleLabel(row)"
              :class="[
                'relationship-role-badge',
                `relationship-role-badge--${relationshipRoleClass(row)}`,
              ]"
            >
              {{ relationshipRoleLabel(row) }}
            </span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="主体类型" min-width="128" align="center" header-align="center">
        <template #default="{ row }">
          <span class="meta-chip meta-chip--entity">
            {{ controllerTypeLabel(row.controller_type) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="控制类型" min-width="128" align="center" header-align="center">
        <template #default="{ row }">
          <span class="meta-chip meta-chip--control">
            {{ controlTypeLabel(row.control_type) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="控制比例" min-width="110" align="center" header-align="center">
        <template #default="{ row }">
          <span class="ratio-text">
            {{ formatRatio(row.control_ratio) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="控制路径" min-width="360">
        <template #default="{ row }">
          <div class="control-path-cell">
            <template v-if="pathSummary(row).pathCount">
              <div class="table-text table-multi-line path-summary">
                <template v-if="pathSummary(row).hasMultiplePaths">
                  <div class="path-primary">主路径：{{ pathSummary(row).primaryPathText }}</div>
                  <div class="path-secondary">另有 {{ pathSummary(row).extraPathCount }} 条补充路径</div>
                </template>
                <template v-else>
                  <div class="path-primary">{{ pathSummary(row).primaryPathText }}</div>
                </template>
              </div>

              <el-button
                v-if="pathSummary(row).hasMultiplePaths"
                class="path-toggle"
                link
                type="primary"
                @click.stop="togglePath(row)"
              >
                {{ isPathExpanded(row) ? '收起路径' : `展开全部（共 ${pathSummary(row).pathCount} 条）` }}
              </el-button>

              <div v-if="isPathExpanded(row)" class="path-list">
                <div
                  v-for="(path, pathIndex) in pathSummary(row).paths"
                  :key="`${row._tableKey}-path-${pathIndex}`"
                  class="path-list-item"
                >
                  <div class="path-list-head">
                    <span class="path-index">路径 {{ pathIndex + 1 }}</span>
                    <span v-if="pathScoreText(path) !== EMPTY_TEXT" class="path-score">
                      约 {{ pathScoreText(path) }}
                    </span>
                  </div>
                  <div class="table-text table-multi-line path-detail">
                    {{ buildPathText(path) || EMPTY_TEXT }}
                  </div>
                </div>
              </div>
            </template>

            <span v-else class="table-text table-text--muted">{{ EMPTY_TEXT }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="是否实际控制人" min-width="132" align="center" header-align="center">
        <template #default="{ row }">
          <span
            class="actual-badge"
            :class="row.is_actual_controller ? 'actual-badge--yes' : 'actual-badge--no'"
          >
            {{ row.is_actual_controller ? '是' : '否' }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="认定依据" min-width="260">
        <template #default="{ row }">
          <div v-if="basisLines(row).length" class="basis-list">
            <div
              v-for="(item, itemIndex) in basisLines(row)"
              :key="`${row._tableKey}-basis-${itemIndex}`"
              class="basis-item"
            >
              <span class="basis-label">{{ item.label }}</span>
              <span class="table-text table-multi-line basis-value">{{ item.value }}</span>
            </div>
          </div>
          <span v-else class="table-text table-text--muted">{{ EMPTY_TEXT }}</span>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.control-relations-table :deep(.el-table__cell) {
  vertical-align: top;
}

.control-relations-table :deep(.cell) {
  line-height: 1.68;
}

.control-relations-table :deep(.el-table__row > td) {
  transition: background-color 0.18s ease;
}

.control-relations-table :deep(.el-table__row:hover > td) {
  background: rgba(31, 59, 87, 0.04) !important;
}

.control-relations-table :deep(.control-relations-table__row--actual > td) {
  background: rgba(168, 73, 73, 0.055);
}

.control-relations-table :deep(.control-relations-table__row--actual:hover > td) {
  background: rgba(168, 73, 73, 0.085) !important;
}

.controller-name {
  color: var(--brand-ink);
  font-weight: 600;
}

.controller-name-cell {
  display: grid;
  gap: 6px;
}

.relationship-role-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  min-height: 24px;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.relationship-role-badge--actual {
  color: #a33e3e;
  border-color: rgba(163, 62, 62, 0.2);
  background: rgba(163, 62, 62, 0.12);
}

.relationship-role-badge--leading {
  color: #5b50ad;
  border-color: rgba(91, 80, 173, 0.2);
  background: rgba(91, 80, 173, 0.1);
}

.relationship-role-badge--joint {
  color: #8a5a11;
  border-color: rgba(138, 90, 17, 0.22);
  background: rgba(138, 90, 17, 0.1);
}

.meta-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 12px;
  line-height: 1.3;
  text-align: center;
}

.meta-chip--entity {
  color: #5a6878;
  border-color: rgba(90, 104, 120, 0.16);
  background: rgba(90, 104, 120, 0.07);
}

.meta-chip--control {
  color: #305f83;
  border-color: rgba(48, 95, 131, 0.18);
  background: rgba(48, 95, 131, 0.08);
}

.ratio-text {
  color: #243648;
  font-weight: 600;
  white-space: nowrap;
}

.control-path-cell {
  display: grid;
  gap: 8px;
}

.path-summary {
  display: grid;
  gap: 4px;
}

.path-primary {
  color: #2d4156;
}

.path-secondary {
  color: var(--text-secondary);
  font-size: 12px;
}

.path-toggle {
  justify-self: flex-start;
  height: auto;
  padding: 0;
  font-size: 12px;
}

.path-list {
  display: grid;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(31, 59, 87, 0.12);
}

.path-list-item {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(31, 59, 87, 0.045);
}

.path-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
}

.path-index {
  color: var(--accent-gold);
  font-size: 12px;
  font-weight: 600;
}

.path-score {
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.path-detail {
  color: #314255;
}

.actual-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 48px;
  min-height: 28px;
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 12px;
  font-weight: 700;
}

.actual-badge--yes {
  color: #a33e3e;
  border-color: rgba(163, 62, 62, 0.2);
  background: rgba(163, 62, 62, 0.12);
}

.actual-badge--no {
  color: #738398;
  border-color: rgba(115, 131, 152, 0.18);
  background: rgba(115, 131, 152, 0.08);
}

.basis-list {
  display: grid;
  gap: 6px;
}

.basis-item {
  display: grid;
  grid-template-columns: 68px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.basis-label {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
  white-space: nowrap;
}

.basis-value {
  color: #314255;
}
</style>
