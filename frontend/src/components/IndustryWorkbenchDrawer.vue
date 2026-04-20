<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import IndustryStructurePieChart from '@/components/IndustryStructurePieChart.vue'
import {
  classificationSummary,
  createWorkbenchSegment,
  formatConfidence,
  formatFlexiblePercent,
  pieChartRows,
  primaryClassification,
  reviewReasonLabel,
  reviewStatusLabel,
  reviewStatusTagType,
  runWorkbenchRuleAnalysis,
  segmentTypeLabel,
  segmentTypeTagType,
} from '@/utils/industryAnalysis'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  company: {
    type: Object,
    default: null,
  },
  industryAnalysis: {
    type: Object,
    default: () => ({}),
  },
  companyId: {
    type: [Number, String],
    default: null,
  },
})

const emit = defineEmits(['update:modelValue'])

const companyForm = reactive({
  company_name: '',
  company_description: '',
})

const seed = ref(1)
const segmentRows = ref([createWorkbenchSegment(1)])
const analysisResult = ref(null)
const manualDrawerVisible = ref(false)
const selectedWorkbenchSegmentId = ref(null)
const manualDraft = reactive({
  level_1: '',
  level_2: '',
  level_3: '',
  level_4: '',
  mapping_basis: '',
})

const drawerVisible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const currentSegments = computed(() =>
  Array.isArray(props.industryAnalysis?.segments) ? props.industryAnalysis.segments : [],
)
const hasOfficialSegments = computed(() => currentSegments.value.length > 0)
const chartRows = computed(() =>
  pieChartRows(analysisResult.value?.segments || [], 'revenue_ratio', 6),
)
const selectedWorkbenchSegment = computed(
  () =>
    analysisResult.value?.segments?.find(
      (segment) => segment.id === selectedWorkbenchSegmentId.value,
    ) || null,
)
const selectedWorkbenchClassification = computed(
  () => primaryClassification(selectedWorkbenchSegment.value),
)
const resultMetrics = computed(() => {
  const segments = analysisResult.value?.segments || []
  const statuses = segments
    .map((segment) => primaryClassification(segment)?.review_status)
    .filter(Boolean)
  return [
    {
      label: '临时业务线数量',
      value: segments.length,
    },
    {
      label: '主营分类摘要',
      value: analysisResult.value?.primary_industries?.[0] || '待生成',
    },
    {
      label: '待补判样本',
      value: statuses.filter((status) =>
        ['needs_llm_review', 'conflicted', 'unmapped'].includes(status),
      ).length,
    },
  ]
})
const workbenchHint = computed(() => {
  if (!analysisResult.value) {
    return '输入内容后在当前抽屉内运行规则分析，结果只保留在工作台中，不写入正式数据库。'
  }
  return '当前结果为临时试算结果，仅在工作台内展示，可继续修改输入后重复分析。'
})

function nextSeedValue() {
  seed.value += 1
  return seed.value
}

function resetCompanyForm() {
  companyForm.company_name = props.company?.name || ''
  companyForm.company_description = ''
}

function resetWorkbenchSegments() {
  seed.value = 1
  segmentRows.value = [createWorkbenchSegment(1)]
}

function ensureDefaultContext() {
  if (!companyForm.company_name) {
    companyForm.company_name = props.company?.name || ''
  }
  if (!segmentRows.value.length) {
    resetWorkbenchSegments()
  }
}

function clearWorkbenchInput() {
  resetCompanyForm()
  resetWorkbenchSegments()
  analysisResult.value = null
  selectedWorkbenchSegmentId.value = null
  manualDrawerVisible.value = false
  ElMessage.info('已清空当前工作台输入与临时分析结果。')
}

function cloneOfficialSegmentToWorkbench(segment, index) {
  const cloned = createWorkbenchSegment(index + 1)
  cloned.segment_name = segment?.segment_name || ''
  cloned.segment_alias = segment?.segment_alias || ''
  cloned.description = segment?.description || ''
  cloned.revenue_ratio =
    segment?.revenue_ratio === null || segment?.revenue_ratio === undefined
      ? ''
      : String(segment.revenue_ratio)
  cloned.profit_ratio =
    segment?.profit_ratio === null || segment?.profit_ratio === undefined
      ? ''
      : String(segment.profit_ratio)
  cloned.segment_type = segment?.segment_type || cloned.segment_type
  cloned.reporting_period =
    segment?.reporting_period || props.industryAnalysis?.selected_reporting_period || '2025A'
  return cloned
}

function loadFromCurrentResult() {
  if (!hasOfficialSegments.value) {
    ElMessage.info('当前公司没有可载入的正式业务线结果。')
    return
  }
  companyForm.company_name = props.company?.name || companyForm.company_name
  companyForm.company_description = ''
  segmentRows.value = currentSegments.value.map((segment, index) =>
    cloneOfficialSegmentToWorkbench(segment, index),
  )
  seed.value = Math.max(segmentRows.value.length, 1)
  analysisResult.value = null
  ElMessage.success('已将当前公司的正式业务线载入工作台，可继续调整后重新试算。')
}

function addWorkbenchSegment() {
  segmentRows.value.push(createWorkbenchSegment(nextSeedValue()))
}

function removeWorkbenchSegment(localId) {
  if (segmentRows.value.length === 1) {
    ElMessage.info('至少保留一条业务线用于临时分析。')
    return
  }
  segmentRows.value = segmentRows.value.filter((item) => item.localId !== localId)
}

function runRuleAnalysis() {
  const hasValidSegment = segmentRows.value.some((segment) =>
    String(segment.segment_name || '').trim(),
  )
  if (!hasValidSegment) {
    ElMessage.warning('请至少填写一条业务线名称后再执行规则分析。')
    return
  }

  analysisResult.value = runWorkbenchRuleAnalysis({
    companyName: companyForm.company_name,
    companyDescription: companyForm.company_description,
    segments: segmentRows.value,
  })
  ElMessage.success('已完成临时规则分析。结果当前仅保留在工作台中，不会写入正式数据库。')
}

function openManualDrawer(segment) {
  selectedWorkbenchSegmentId.value = segment.id
  manualDraft.level_1 = primaryClassification(segment)?.level_1 || ''
  manualDraft.level_2 = primaryClassification(segment)?.level_2 || ''
  manualDraft.level_3 = primaryClassification(segment)?.level_3 || ''
  manualDraft.level_4 = primaryClassification(segment)?.level_4 || ''
  manualDraft.mapping_basis = primaryClassification(segment)?.mapping_basis || ''
  manualDrawerVisible.value = true
}

function applyManualWorkbenchOverride() {
  if (!selectedWorkbenchSegment.value) {
    return
  }

  const nextClassification = {
    ...primaryClassification(selectedWorkbenchSegment.value),
    level_1: manualDraft.level_1 || null,
    level_2: manualDraft.level_2 || null,
    level_3: manualDraft.level_3 || null,
    level_4: manualDraft.level_4 || null,
    industry_label: [
      manualDraft.level_1,
      manualDraft.level_2,
      manualDraft.level_3,
      manualDraft.level_4,
    ]
      .filter(Boolean)
      .join(' > '),
    mapping_basis:
      manualDraft.mapping_basis ||
      'decision=confirmed | rules=manual_override | hits=name[] alias[] description[] company[] peer[] | negatives=[] | depth=level_4 | comment=workbench manual override',
    review_status: 'confirmed',
    classifier_type: 'manual',
    confidence: 1,
    review_reason: 'manual_override',
  }

  const nextSegments = (analysisResult.value?.segments || []).map((segment) =>
    segment.id === selectedWorkbenchSegment.value.id
      ? {
          ...segment,
          classifications: [nextClassification],
          classification_labels: [nextClassification.industry_label].filter(Boolean),
        }
      : segment,
  )

  analysisResult.value = {
    ...analysisResult.value,
    segments: nextSegments,
    primary_industries: [
      ...new Set(
        nextSegments
          .filter((segment) => segment.segment_type === 'primary')
          .map((segment) => classificationSummary(segment))
          .filter(Boolean),
      ),
    ],
    all_industry_labels: [
      ...new Set(nextSegments.flatMap((segment) => segment.classification_labels || [])),
    ],
  }

  manualDrawerVisible.value = false
  ElMessage.success('已在工作台内暂存人工修订结果，仅用于本次临时分析展示。')
}

function triggerWorkbenchLlm() {
  ElMessage.info('LLM 分析入口已预留。当前阶段仅保留按钮与占位，不写入正式数据库。')
}

watch(
  () => drawerVisible.value,
  (visible) => {
    if (visible) {
      ensureDefaultContext()
    }
  },
)

watch(
  () => props.company?.name,
  (name) => {
    if (!companyForm.company_name) {
      companyForm.company_name = name || ''
    }
  },
)
</script>

<template>
  <el-drawer
    v-model="drawerVisible"
    size="70%"
    :with-header="false"
    class="industry-workbench-drawer"
    modal-class="industry-workbench-drawer__mask"
    append-to-body
    :destroy-on-close="false"
  >
    <div class="industry-workbench-panel">
      <header class="industry-workbench-panel__header">
        <div class="industry-workbench-panel__header-copy">
          <span class="industry-workbench-panel__eyebrow">Industry Workbench</span>
          <h2>产业分析工作台</h2>
          <p>用于临时录入公司与业务线结构，在抽屉内完成规则分析，并为后续 LLM 分析预留承接位置。</p>
        </div>
        <div class="industry-workbench-panel__header-actions">
          <el-button plain @click="drawerVisible = false">
            关闭
          </el-button>
        </div>
      </header>

      <div class="industry-workbench-panel__body">
        <section class="surface-card industry-workbench-panel__input-shell">
          <div class="section-heading">
            <div>
              <h3>临时分析输入区</h3>
              <p>这里是工作台主区域。可单独输入公司与业务线结构，后续在抽屉内直接进行规则分析与临时试算。</p>
            </div>
          </div>

          <el-form label-position="top" class="industry-workbench-panel__company-form">
            <div class="industry-workbench-panel__company-grid">
              <el-form-item label="公司名称">
                <el-input
                  v-model="companyForm.company_name"
                  placeholder="例如：某新能源平台公司"
                />
              </el-form-item>
              <el-form-item label="公司简介（可选）">
                <el-input
                  v-model="companyForm.company_description"
                  type="textarea"
                  :rows="3"
                  placeholder="可补充业务模式、行业定位或公司简介，作为规则试算与后续模型分析的上下文。"
                />
              </el-form-item>
            </div>
          </el-form>

          <div class="industry-workbench-panel__segment-head">
            <div>
              <h3>业务线输入列表</h3>
              <p>支持新增、删除和调整业务线字段。当前阶段只做前端状态管理，不写正式库。</p>
            </div>
            <el-button type="primary" plain @click="addWorkbenchSegment">
              新增业务线
            </el-button>
          </div>

          <div class="industry-workbench-panel__segment-list">
            <article
              v-for="segment in segmentRows"
              :key="segment.localId"
              class="industry-workbench-panel__segment-card"
            >
              <div class="industry-workbench-panel__segment-card-head">
                <strong>{{ segment.segment_name || `业务线 ${segment.localId.split('-').pop()}` }}</strong>
                <el-button link type="danger" @click="removeWorkbenchSegment(segment.localId)">
                  删除
                </el-button>
              </div>

              <div class="industry-workbench-panel__segment-row industry-workbench-panel__segment-row--identity">
                <el-form-item label="segment_name">
                  <el-input
                    v-model="segment.segment_name"
                    placeholder="例如：Cloud ERP Platform"
                  />
                </el-form-item>
                <el-form-item label="segment_alias（可选）">
                  <el-input
                    v-model="segment.segment_alias"
                    placeholder="例如：Enterprise SaaS"
                  />
                </el-form-item>
                <el-form-item label="segment_type">
                  <el-select v-model="segment.segment_type">
                    <el-option label="主营" value="primary" />
                    <el-option label="补充" value="secondary" />
                    <el-option label="新兴" value="emerging" />
                    <el-option label="其他" value="other" />
                  </el-select>
                </el-form-item>
              </div>

              <div class="industry-workbench-panel__segment-row industry-workbench-panel__segment-row--metrics">
                <el-form-item label="reporting_period">
                  <el-input
                    v-model="segment.reporting_period"
                    placeholder="例如：2025A"
                  />
                </el-form-item>
                <el-form-item label="revenue_ratio">
                  <el-input
                    v-model="segment.revenue_ratio"
                    placeholder="例如：42 或 0.42"
                  />
                </el-form-item>
                <el-form-item label="profit_ratio（可选）">
                  <el-input
                    v-model="segment.profit_ratio"
                    placeholder="例如：18 或 0.18"
                  />
                </el-form-item>
              </div>

              <el-form-item class="industry-workbench-panel__segment-description" label="description（可选）">
                <el-input
                  v-model="segment.description"
                  type="textarea"
                  :rows="3"
                  placeholder="补充业务线产品、客户、商业模式或行业描述。"
                />
              </el-form-item>
            </article>
          </div>
        </section>

        <section class="surface-card industry-workbench-panel__action-shell">
          <div class="section-heading">
            <div>
              <h3>分析动作区</h3>
              <p>先录入或调整输入内容，再执行临时规则分析。当前阶段所有结果都仅保留在工作台内。</p>
            </div>
          </div>

          <div class="industry-workbench-panel__action-bar">
            <el-button type="primary" @click="runRuleAnalysis">
              规则分析
            </el-button>
            <el-button plain @click="triggerWorkbenchLlm">
              LLM 分析
            </el-button>
            <el-button plain @click="clearWorkbenchInput">
              清空输入
            </el-button>
            <el-button plain :disabled="!hasOfficialSegments" @click="loadFromCurrentResult">
              载入已有业务线
            </el-button>
          </div>
          <p class="industry-workbench-panel__footnote">
            {{ workbenchHint }}
          </p>
        </section>

        <section class="surface-card industry-workbench-panel__result-shell">
          <div class="section-heading">
            <div>
              <h3>分析结果区</h3>
              <p>规则分析后，在工作台内直接展示临时结果。当前结果不会默认写入正式 `business_segments` 或分类表。</p>
            </div>
          </div>

          <template v-if="analysisResult">
            <div class="industry-workbench-panel__result-metrics">
              <div
                v-for="metric in resultMetrics"
                :key="metric.label"
                class="industry-workbench-panel__result-metric"
              >
                <span>{{ metric.label }}</span>
                <strong>{{ metric.value }}</strong>
              </div>
            </div>

            <div class="industry-workbench-panel__chart-shell">
              <div class="industry-workbench-panel__chart-head">
                <h4>业务结构图</h4>
                <small>当前先展示基于临时输入的收入占比结构图。</small>
              </div>
              <IndustryStructurePieChart :rows="chartRows" metric-label="收入占比" />
            </div>

            <div class="industry-workbench-panel__table-shell">
              <el-table :data="analysisResult.segments" border stripe>
                <el-table-column prop="segment_name" label="业务线" min-width="180" />
                <el-table-column label="业务类型" min-width="110">
                  <template #default="{ row }">
                    <el-tag :type="segmentTypeTagType(row.segment_type)" effect="plain">
                      {{ segmentTypeLabel(row.segment_type) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="收入占比" min-width="100">
                  <template #default="{ row }">
                    {{ formatFlexiblePercent(row.revenue_ratio) }}
                  </template>
                </el-table-column>
                <el-table-column label="分类结果" min-width="240">
                  <template #default="{ row }">
                    {{ classificationSummary(row) }}
                  </template>
                </el-table-column>
                <el-table-column label="review_status" min-width="130">
                  <template #default="{ row }">
                    <el-tag
                      :type="reviewStatusTagType(primaryClassification(row)?.review_status)"
                      effect="plain"
                    >
                      {{ reviewStatusLabel(primaryClassification(row)?.review_status) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="confidence" min-width="100">
                  <template #default="{ row }">
                    {{ formatConfidence(primaryClassification(row)?.confidence) }}
                  </template>
                </el-table-column>
                <el-table-column label="review_reason" min-width="150">
                  <template #default="{ row }">
                    {{ reviewReasonLabel(primaryClassification(row)?.review_reason) }}
                  </template>
                </el-table-column>
                <el-table-column label="mapping_basis" min-width="360">
                  <template #default="{ row }">
                    <div class="industry-workbench-panel__mapping-basis">
                      {{ primaryClassification(row)?.mapping_basis || '暂无' }}
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="操作" min-width="160" fixed="right">
                  <template #default="{ row }">
                    <el-button link type="primary" @click="openManualDrawer(row)">
                      人工调整
                    </el-button>
                    <el-button link @click="triggerWorkbenchLlm">
                      LLM 分析
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="industry-workbench-panel__llm-shell">
              <div>
                <h4>LLM 分析预留区</h4>
                <p>后续可在这里承接模型补判、比对建议和采纳回写；当前阶段仅保留交互入口与承接位置。</p>
              </div>
              <el-button plain @click="triggerWorkbenchLlm">
                打开 LLM 分析占位
              </el-button>
            </div>
          </template>

          <el-empty
            v-else
            description="尚未运行规则分析"
            :image-size="88"
          >
            <template #description>
              <div class="table-text table-text--muted">
                先在左侧录入公司与业务线结构，再点击“规则分析”生成临时结果。当前阶段所有输入和结果都只停留在工作台内。
              </div>
            </template>
          </el-empty>
        </section>
      </div>

      <el-drawer
        v-model="manualDrawerVisible"
        size="42%"
        :with-header="false"
        append-to-body
      >
        <div v-if="selectedWorkbenchSegment" class="industry-workbench-panel__manual-drawer">
          <span class="industry-workbench-panel__eyebrow">Manual Override Sandbox</span>
          <h2>{{ selectedWorkbenchSegment.segment_alias || selectedWorkbenchSegment.segment_name }}</h2>
          <p class="industry-workbench-panel__manual-subtitle">
            当前修改只作用于本次工作台临时分析结果。
          </p>

          <section class="industry-workbench-panel__manual-section">
            <h3>当前结果</h3>
            <p><strong>分类摘要：</strong>{{ classificationSummary(selectedWorkbenchSegment) }}</p>
            <p><strong>状态：</strong>{{ reviewStatusLabel(selectedWorkbenchClassification?.review_status) }}</p>
            <p><strong>原因：</strong>{{ reviewReasonLabel(selectedWorkbenchClassification?.review_reason) }}</p>
            <p><strong>mapping_basis：</strong>{{ selectedWorkbenchClassification?.mapping_basis || '暂无' }}</p>
          </section>

          <section class="industry-workbench-panel__manual-section">
            <h3>人工征订</h3>
            <el-form label-position="top">
              <div class="industry-workbench-panel__manual-grid">
                <el-form-item label="Level 1">
                  <el-input v-model="manualDraft.level_1" />
                </el-form-item>
                <el-form-item label="Level 2">
                  <el-input v-model="manualDraft.level_2" />
                </el-form-item>
                <el-form-item label="Level 3">
                  <el-input v-model="manualDraft.level_3" />
                </el-form-item>
                <el-form-item label="Level 4">
                  <el-input v-model="manualDraft.level_4" />
                </el-form-item>
              </div>
              <el-form-item label="mapping_basis">
                <el-input
                  v-model="manualDraft.mapping_basis"
                  type="textarea"
                  :rows="4"
                />
              </el-form-item>
            </el-form>
            <el-button type="primary" @click="applyManualWorkbenchOverride">
              应用人工调整
            </el-button>
          </section>
        </div>
      </el-drawer>
    </div>
  </el-drawer>
</template>

<style scoped>
:global(.industry-workbench-drawer__mask) {
  background: rgba(11, 20, 31, 0.58);
  backdrop-filter: blur(2px);
}

:deep(.industry-workbench-drawer) {
  width: min(1400px, 70vw) !important;
  max-width: calc(100vw - 24px);
  min-width: 860px;
  box-shadow: -24px 0 52px rgba(15, 30, 46, 0.22);
}

:deep(.industry-workbench-drawer .el-drawer__body) {
  padding: 0;
  background:
    radial-gradient(circle at top right, rgba(225, 211, 188, 0.22), transparent 24%),
    linear-gradient(180deg, rgba(249, 247, 243, 0.98), rgba(255, 255, 255, 0.96));
}

.industry-workbench-panel {
  display: grid;
  gap: 18px;
  min-height: 100%;
  padding: 24px;
  color: var(--brand-ink);
}

.industry-workbench-panel__header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  align-items: start;
  padding: 24px 28px;
  border-radius: 24px;
  border: 1px solid rgba(144, 116, 77, 0.18);
  background:
    linear-gradient(145deg, rgba(255, 252, 247, 0.98), rgba(251, 247, 240, 0.9));
  box-shadow: 0 18px 36px rgba(46, 37, 24, 0.08);
}

.industry-workbench-panel__header-copy {
  display: grid;
  gap: 10px;
  max-width: 760px;
}

.industry-workbench-panel__eyebrow {
  display: inline-flex;
  width: fit-content;
  padding: 6px 11px;
  border-radius: 999px;
  border: 1px solid rgba(144, 116, 77, 0.18);
  background: rgba(255, 249, 240, 0.84);
  color: #8b6a3d;
  font-size: 11px;
  line-height: 1.2;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.industry-workbench-panel__header-copy h2,
.industry-workbench-panel__manual-drawer h2 {
  margin: 0;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
  font-size: 26px;
  line-height: 1.3;
}

.industry-workbench-panel__header-copy p,
.industry-workbench-panel__llm-shell p,
.industry-workbench-panel__manual-subtitle {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.industry-workbench-panel__header-actions {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
}

.industry-workbench-panel__body {
  display: grid;
  gap: 20px;
}

.industry-workbench-panel__input-shell,
.industry-workbench-panel__action-shell,
.industry-workbench-panel__result-shell {
  padding: 24px 26px;
  border-radius: 22px;
  min-width: 0;
}

.industry-workbench-panel__input-shell {
  display: grid;
  gap: 22px;
}

.industry-workbench-panel__company-grid,
.industry-workbench-panel__result-metrics,
.industry-workbench-panel__manual-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.industry-workbench-panel__segment-head,
.industry-workbench-panel__action-bar,
.industry-workbench-panel__llm-shell {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.industry-workbench-panel__segment-list {
  display: grid;
  gap: 18px;
}

.industry-workbench-panel__segment-card {
  display: grid;
  gap: 16px;
  padding: 20px;
  border-radius: 20px;
  border: 1px solid rgba(48, 95, 131, 0.12);
  background:
    linear-gradient(180deg, rgba(252, 249, 243, 0.94), rgba(255, 255, 255, 0.9));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.industry-workbench-panel__segment-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.industry-workbench-panel__segment-card-head strong,
.industry-workbench-panel__result-metric strong {
  color: var(--brand-ink);
}

.industry-workbench-panel__segment-row {
  display: grid;
  gap: 14px;
}

.industry-workbench-panel__segment-row--identity,
.industry-workbench-panel__segment-row--metrics {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.industry-workbench-panel__segment-description {
  margin-top: 2px;
}

.industry-workbench-panel__action-shell {
  display: grid;
  gap: 16px;
  background:
    linear-gradient(180deg, rgba(247, 250, 255, 0.92), rgba(255, 255, 255, 0.94));
}

.industry-workbench-panel__action-bar {
  flex-wrap: wrap;
  justify-content: flex-start;
  gap: 12px 10px;
}

.industry-workbench-panel__footnote {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.65;
}

.industry-workbench-panel__result-shell {
  display: grid;
  gap: 20px;
}

.industry-workbench-panel__result-metric {
  display: grid;
  gap: 8px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(249, 251, 254, 0.84);
}

.industry-workbench-panel__result-metric span,
.industry-workbench-panel__chart-head small {
  color: var(--text-secondary);
  font-size: 12px;
}

.industry-workbench-panel__chart-shell {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(255, 255, 255, 0.84);
}

.industry-workbench-panel__chart-head {
  display: grid;
  gap: 4px;
}

.industry-workbench-panel__chart-head h4,
.industry-workbench-panel__llm-shell h4,
.industry-workbench-panel__manual-section h3 {
  margin: 0;
  color: var(--brand-ink);
}

.industry-workbench-panel__table-shell {
  min-width: 0;
}

.industry-workbench-panel__table-shell :deep(.el-table) {
  width: 100%;
  min-width: 1080px;
}

.industry-workbench-panel__mapping-basis {
  color: #314255;
  font-size: 12px;
  line-height: 1.55;
  white-space: normal;
  overflow-wrap: anywhere;
}

.industry-workbench-panel__llm-shell {
  padding: 16px;
  border-radius: 18px;
  border: 1px dashed rgba(48, 95, 131, 0.18);
  background: rgba(246, 250, 255, 0.82);
}

.industry-workbench-panel__manual-drawer {
  display: grid;
  gap: 18px;
}

.industry-workbench-panel__manual-section {
  display: grid;
  gap: 10px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(255, 255, 255, 0.82);
}

.industry-workbench-panel__manual-section p {
  margin: 0;
  color: #314255;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

@media (max-width: 1320px) {
  :deep(.industry-workbench-drawer) {
    width: min(1240px, 76vw) !important;
    min-width: 720px;
  }
}

@media (max-width: 860px) {
  :deep(.industry-workbench-drawer) {
    width: calc(100vw - 16px) !important;
    min-width: 0;
  }

  .industry-workbench-panel {
    padding: 16px;
  }

  .industry-workbench-panel__header {
    grid-template-columns: 1fr;
  }

  .industry-workbench-panel__header-actions {
    justify-content: flex-start;
  }

  .industry-workbench-panel__company-grid,
  .industry-workbench-panel__result-metrics,
  .industry-workbench-panel__manual-grid {
    grid-template-columns: 1fr;
  }

  .industry-workbench-panel__segment-row--identity,
  .industry-workbench-panel__segment-row--metrics {
    grid-template-columns: 1fr;
  }

  .industry-workbench-panel__segment-head,
  .industry-workbench-panel__action-bar,
  .industry-workbench-panel__llm-shell {
    display: grid;
  }
}
</style>
