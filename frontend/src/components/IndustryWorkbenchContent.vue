<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'

import IndustryStructurePieChart from '@/components/IndustryStructurePieChart.vue'
import {
  buildMockLlmClassification,
  classificationLabel,
  classificationLabelFromLevels,
  compactRuleExplanation,
  createWorkbenchSegment,
  formatConfidence,
  formatFlexiblePercent,
  pieChartRows,
  primaryClassification,
  profitPieChartRows,
  readableMappingBasis,
  reviewStatusLabel,
  runWorkbenchRuleAnalysis,
  segmentTypeLabel,
  segmentTypeTagType,
} from '@/utils/industryAnalysis'

const props = defineProps({
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
  mode: {
    type: String,
    default: 'page',
  },
})

const emit = defineEmits(['close'])

const companyForm = reactive({
  company_name: '',
  company_description: '',
})

const seed = ref(1)
const segmentRows = ref([createWorkbenchSegment(1)])
const analysisResult = ref(null)
const detailDrawerVisible = ref(false)
const selectedWorkbenchSegmentId = ref(null)
const selectedResultSource = ref({})
const llmResults = ref({})
const confirmationState = ref({})
const manualDrafts = ref({})

const currentSegments = computed(() =>
  Array.isArray(props.industryAnalysis?.segments) ? props.industryAnalysis.segments : [],
)

const hasOfficialSegments = computed(() => currentSegments.value.length > 0)
const analysisSegments = computed(() => analysisResult.value?.segments || [])
const revenueChartRows = computed(() => pieChartRows(analysisSegments.value, 'revenue_ratio', 6))
const profitChartRows = computed(() => profitPieChartRows(analysisSegments.value, 6))
const pendingSampleCount = computed(() =>
  analysisSegments.value.filter((segment) =>
    ['needs_llm_review', 'conflicted', 'unmapped'].includes(
      primaryClassification(segment)?.review_status,
    ),
  ).length,
)
const summaryValue = computed(
  () => analysisResult.value?.primary_industries?.[0] || '待生成主营分类摘要',
)

function nextSeedValue() {
  seed.value += 1
  return seed.value
}

function buildManualDraft(segment) {
  const current = primaryClassification(segment)
  return {
    level_1: current?.level_1 || '',
    level_2: current?.level_2 || '',
    level_3: current?.level_3 || '',
    level_4: current?.level_4 || '',
    manual_override_basis: '',
    appliedClassification: null,
  }
}

function ensureManualDraft(segment) {
  if (!segment) {
    return null
  }
  if (!manualDrafts.value[segment.id]) {
    manualDrafts.value = {
      ...manualDrafts.value,
      [segment.id]: buildManualDraft(segment),
    }
  }
  return manualDrafts.value[segment.id]
}

const presentedSegments = computed(() =>
  analysisSegments.value.map((segment) => {
    const ruleClassification = primaryClassification(segment)
    const llmClassification = llmResults.value[segment.id] || null
    const selectedSource = selectedResultSource.value[segment.id] || 'rule'
    const draft = manualDrafts.value[segment.id]
    const appliedClassification = draft?.appliedClassification || null
    const selectedClassification =
      selectedSource === 'llm' && llmClassification ? llmClassification : ruleClassification
    const finalClassification = appliedClassification || selectedClassification

    return {
      ...segment,
      ruleClassification,
      llmClassification,
      selected_result_source: selectedSource,
      readable_mapping_basis: readableMappingBasis(
        ruleClassification?.mapping_basis,
        ruleClassification?.review_reason,
        ruleClassification?.review_status,
      ),
      compact_rule_explanation: compactRuleExplanation(
        ruleClassification?.mapping_basis,
        ruleClassification?.review_reason,
        ruleClassification?.review_status,
      ),
      finalClassification,
      finalSourceLabel: appliedClassification
        ? '人工修订'
        : selectedSource === 'llm'
          ? 'LLM'
          : '规则',
      finalStatus: confirmationState.value[segment.id] || '待确认',
    }
  }),
)

const selectedSegmentPresentation = computed(
  () =>
    presentedSegments.value.find(
      (segment) => String(segment.id) === String(selectedWorkbenchSegmentId.value),
    ) || null,
)

function resetWorkbenchInput() {
  companyForm.company_name = props.company?.name || ''
  companyForm.company_description = ''
  seed.value = 1
  segmentRows.value = [createWorkbenchSegment(1)]
  analysisResult.value = null
  llmResults.value = {}
  selectedResultSource.value = {}
  confirmationState.value = {}
  manualDrafts.value = {}
  selectedWorkbenchSegmentId.value = null
  detailDrawerVisible.value = false
}

function initializeDerivedState(segments) {
  selectedResultSource.value = Object.fromEntries(segments.map((segment) => [segment.id, 'rule']))
  confirmationState.value = {}
  llmResults.value = {}
  manualDrafts.value = Object.fromEntries(
    segments.map((segment) => [segment.id, buildManualDraft(segment)]),
  )
}

function runRuleAnalysis() {
  const hasValidSegment = segmentRows.value.some((segment) =>
    String(segment.segment_name || '').trim(),
  )
  if (!hasValidSegment) {
    ElMessage.warning('请至少填写一条业务线名称后再执行规则分析。')
    return
  }

  const result = runWorkbenchRuleAnalysis({
    companyName: companyForm.company_name,
    companyDescription: companyForm.company_description,
    segments: segmentRows.value,
  })
  analysisResult.value = result
  initializeDerivedState(result.segments || [])
  ElMessage.success('已完成临时规则分析，结果当前保留在前端工作台中。')
}

function triggerWorkbenchLlm() {
  if (!analysisSegments.value.length) {
    ElMessage.info('请先完成规则分析，再生成 LLM 占位结果。')
    return
  }

  // TODO: replace mock LLM result with backend llm analysis API
  llmResults.value = Object.fromEntries(
    analysisSegments.value.map((segment) => [segment.id, buildMockLlmClassification(segment)]),
  )
  ElMessage.success('已生成 LLM 占位结果，可用于前端流程演示。')
}

function addWorkbenchSegment() {
  segmentRows.value.push(createWorkbenchSegment(nextSeedValue()))
}

function removeWorkbenchSegment(localId) {
  if (segmentRows.value.length === 1) {
    ElMessage.info('至少保留一条业务线用于试算。')
    return
  }
  segmentRows.value = segmentRows.value.filter((segment) => segment.localId !== localId)
}

function clearWorkbenchInput() {
  resetWorkbenchInput()
  ElMessage.info('已清空当前输入和临时分析结果。')
}

function cloneOfficialSegment(segment, index) {
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
    ElMessage.info('当前没有可载入的正式业务线。')
    return
  }
  companyForm.company_name = props.company?.name || companyForm.company_name
  companyForm.company_description = ''
  segmentRows.value = currentSegments.value.map((segment, index) =>
    cloneOfficialSegment(segment, index),
  )
  seed.value = Math.max(segmentRows.value.length, 1)
  analysisResult.value = null
  llmResults.value = {}
  selectedResultSource.value = {}
  confirmationState.value = {}
  manualDrafts.value = {}
  ElMessage.success('已载入当前公司的正式业务线，可继续进行临时分析。')
}

function updateSelectedSource(segmentId, source) {
  selectedResultSource.value = {
    ...selectedResultSource.value,
    [segmentId]: source,
  }
}

function toggleConfirmation(segmentId) {
  const current = confirmationState.value[segmentId] || '待确认'
  confirmationState.value = {
    ...confirmationState.value,
    [segmentId]: current === '已确认' ? '待确认' : '已确认',
  }
}

function openDetailDrawer(segment) {
  ensureManualDraft(segment)
  selectedWorkbenchSegmentId.value = segment.id
  detailDrawerVisible.value = true
}

function openManualOverrideDrawer(segment) {
  openDetailDrawer(segment)
}

function closeDetailDrawer() {
  detailDrawerVisible.value = false
}

function applyManualOverride(segmentId) {
  const segment = analysisSegments.value.find((item) => String(item.id) === String(segmentId))
  const draft = manualDrafts.value[segmentId]
  if (!segment || !draft) {
    return
  }
  const fallbackBasis = '人工修订（未填写详细依据）'
  const appliedClassification = {
    id: `${segmentId}-manual-override`,
    business_segment_id: segmentId,
    standard_system: 'GICS',
    level_1: draft.level_1 || null,
    level_2: draft.level_2 || null,
    level_3: draft.level_3 || null,
    level_4: draft.level_4 || null,
    industry_label: classificationLabelFromLevels(
      draft.level_1 || null,
      draft.level_2 || null,
      draft.level_3 || null,
      draft.level_4 || null,
    ),
    is_primary: segment.segment_type === 'primary',
    mapping_basis: draft.manual_override_basis || fallbackBasis,
    review_status: 'confirmed',
    classifier_type: 'manual',
    confidence: 1,
    review_reason: 'manual_override',
    readable_mapping_basis: draft.manual_override_basis || fallbackBasis,
  }

  // TODO: persist manual override to official override table/API
  manualDrafts.value = {
    ...manualDrafts.value,
    [segmentId]: {
      ...draft,
      appliedClassification,
    },
  }
  confirmationState.value = {
    ...confirmationState.value,
    [segmentId]: '已确认',
  }
  ElMessage.success('已在前端本地应用人工修订。')
}

function ensureDefaultCompanyContext() {
  if (!companyForm.company_name) {
    companyForm.company_name = props.company?.name || ''
  }
}

watch(
  () => props.company?.name,
  (value) => {
    if (!companyForm.company_name) {
      companyForm.company_name = value || ''
    }
  },
  { immediate: true },
)

watch(
  () => props.mode,
  () => {
    ensureDefaultCompanyContext()
  },
  { immediate: true },
)
</script>

<template>
  <div class="workbench-shell">
    <header class="workbench-shell__header surface-card">
      <div class="workbench-shell__header-copy">
        <span class="workbench-shell__eyebrow">产业分析工作台</span>
        <div class="workbench-shell__title-row">
          <h2>{{ mode === 'drawer' ? '产业分析工作台' : '产业分析工作台' }}</h2>
          <el-tag effect="plain" type="info">临时试算</el-tag>
        </div>
        <p>先完成页面级试算与结果确认，再逐步接入真实后端结果。</p>
      </div>
      <el-tooltip content="返回" placement="left">
        <el-button circle plain :icon="ArrowLeft" @click="emit('close')" />
      </el-tooltip>
    </header>

    <div class="workbench-shell__body">
      <section class="surface-card workbench-panel workbench-panel--input">
        <div class="workbench-input-workspace">
          <div class="section-heading section-heading--primary">
            <div>
              <h3>输入区</h3>
            </div>
          </div>

          <div class="workbench-input-subsection">
            <el-form label-position="top" class="workbench-company-form">
              <div class="workbench-company-stack">
                <el-form-item label="公司名称">
                  <el-input
                    v-model="companyForm.company_name"
                    placeholder="例如：某产业集团"
                  />
                </el-form-item>
                <el-form-item label="公司简介（可选）">
                  <el-input
                    v-model="companyForm.company_description"
                    type="textarea"
                    :rows="3"
                    placeholder="补充公司主营方向、产业定位或平台特征。"
                  />
                </el-form-item>
              </div>
            </el-form>
          </div>

          <div class="workbench-input-subsection workbench-input-subsection--segments">
            <div class="workbench-segment-head">
              <div>
                <h3>业务线输入列表</h3>
              </div>
              <div class="workbench-segment-head__actions">
                <el-button plain type="primary" @click="addWorkbenchSegment">新增业务线</el-button>
                <el-button plain :disabled="!hasOfficialSegments" @click="loadFromCurrentResult">
                  载入已有业务线
                </el-button>
                <el-button plain class="workbench-button--danger" @click="clearWorkbenchInput">
                  清空输入
                </el-button>
              </div>
            </div>

            <div class="workbench-segment-list">
              <article
                v-for="segment in segmentRows"
                :key="segment.localId"
                class="workbench-segment-card"
              >
                <div class="workbench-segment-card__head">
                  <strong>{{ segment.segment_name || `业务线 ${segment.localId.split('-').pop()}` }}</strong>
                  <el-button link type="danger" @click="removeWorkbenchSegment(segment.localId)">
                    删除
                  </el-button>
                </div>

                <div class="workbench-segment-grid">
                  <el-form-item label="业务线名称">
                    <el-input
                      v-model="segment.segment_name"
                      placeholder="例如：云基础设施服务"
                    />
                  </el-form-item>
                  <el-form-item label="业务线别名（可选）">
                    <el-input
                      v-model="segment.segment_alias"
                      placeholder="例如：Cloud Infrastructure"
                    />
                  </el-form-item>
                  <el-form-item label="业务类型">
                    <el-select v-model="segment.segment_type">
                      <el-option label="主营" value="primary" />
                      <el-option label="补充" value="secondary" />
                      <el-option label="新兴" value="emerging" />
                      <el-option label="其他" value="other" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="报告期">
                    <el-input
                      v-model="segment.reporting_period"
                      placeholder="例如：2025A"
                    />
                  </el-form-item>
                  <el-form-item label="收入占比">
                    <el-input
                      v-model="segment.revenue_ratio"
                      placeholder="例如：42 或 0.42"
                    />
                  </el-form-item>
                  <el-form-item label="利润占比（可选）">
                    <el-input
                      v-model="segment.profit_ratio"
                      placeholder="例如：18 或 0.18"
                    />
                  </el-form-item>
                </div>

                <el-form-item label="业务说明（可选）">
                  <el-input
                    v-model="segment.description"
                    type="textarea"
                    :rows="3"
                    placeholder="补充业务产品、客户、商业模式或行业描述。"
                  />
                </el-form-item>
              </article>
            </div>
          </div>
        </div>

        <div class="workbench-list-actions-shell">
          <div class="workbench-list-actions">
            <el-button plain type="primary" @click="runRuleAnalysis">规则分析</el-button>
            <el-button plain type="primary" @click="triggerWorkbenchLlm">LLM 分析</el-button>
          </div>
        </div>
      </section>

      <section class="surface-card workbench-panel">
        <div class="section-heading">
          <div>
            <h3>分析结果区</h3>
          </div>
        </div>

        <template v-if="analysisResult">
          <div class="workbench-results-flow">
            <div class="workbench-metrics-grid">
              <article class="workbench-metric-card">
                <span>临时业务线数量</span>
                <strong>{{ analysisSegments.length }}</strong>
              </article>
              <article class="workbench-metric-card">
                <span>待补判样本</span>
                <strong>{{ pendingSampleCount }}</strong>
              </article>
            </div>

            <article class="workbench-summary-card">
              <span>主营分类摘要</span>
              <strong>{{ summaryValue }}</strong>
            </article>

            <div class="workbench-chart-grid">
              <article class="workbench-chart-card">
                <div class="workbench-chart-card__head">
                  <h4>收入占比图</h4>
                </div>
                <IndustryStructurePieChart
                  :rows="revenueChartRows"
                  metric-label="收入占比"
                  empty-description="当前没有可用于生成收入结构图的业务线占比数据。"
                />
              </article>

              <article class="workbench-chart-card">
                <div class="workbench-chart-card__head">
                  <h4>利润占比图</h4>
                </div>
                <IndustryStructurePieChart
                  :rows="profitChartRows"
                  metric-label="利润占比"
                  empty-description="利润占比图（占位，待更多利润字段补齐）"
                />
              </article>
            </div>

            <div class="workbench-result-section">
              <div class="workbench-result-section__head">
                <h4>分析结果表</h4>
              </div>

              <div class="workbench-table-shell">
                <el-table :data="presentedSegments" border stripe class="workbench-table">
                <el-table-column label="业务线名称" min-width="180">
                  <template #default="{ row }">
                    <div
                      class="workbench-name-cell"
                      :title="row.segment_alias && row.segment_alias !== row.segment_name ? `${row.segment_name} / ${row.segment_alias}` : row.segment_name"
                    >
                      {{ row.segment_name }}
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="业务类型" width="92">
                  <template #default="{ row }">
                    <el-tag :type="segmentTypeTagType(row.segment_type)" effect="plain">
                      {{ segmentTypeLabel(row.segment_type) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="收入占比" width="92">
                  <template #default="{ row }">
                    {{ formatFlexiblePercent(row.revenue_ratio) }}
                  </template>
                </el-table-column>
                <el-table-column label="规则结果" min-width="196">
                  <template #default="{ row }">
                    <div class="workbench-result-block" :title="classificationLabel(row.ruleClassification)">
                      <strong>{{ classificationLabel(row.ruleClassification) }}</strong>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="LLM 结果" min-width="196">
                  <template #default="{ row }">
                    <div
                      class="workbench-result-block"
                      :title="row.llmClassification ? classificationLabel(row.llmClassification) : '待分析'"
                    >
                      <strong>
                        {{ row.llmClassification ? classificationLabel(row.llmClassification) : '待分析' }}
                      </strong>
                      <span>
                        {{ row.llmClassification ? '前端占位结果' : '点击“LLM 分析”后生成占位结果' }}
                      </span>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="采用来源" min-width="154">
                  <template #default="{ row }">
                    <el-radio-group
                      :model-value="row.selected_result_source"
                      size="small"
                      @update:model-value="(value) => updateSelectedSource(row.id, value)"
                    >
                      <el-radio-button label="rule">规则</el-radio-button>
                      <el-radio-button label="llm" :disabled="!row.llmClassification">LLM</el-radio-button>
                    </el-radio-group>
                  </template>
                </el-table-column>
                <el-table-column label="规则依据摘要" min-width="220">
                  <template #default="{ row }">
                    <div class="workbench-readable-basis" :title="row.readable_mapping_basis">
                      {{ row.compact_rule_explanation }}
                    </div>
                  </template>
                </el-table-column>
                <el-table-column
                  label="详情"
                  width="92"
                  align="center"
                  class-name="workbench-table__action-cell"
                >
                  <template #default="{ row }">
                    <el-button link type="primary" @click="openDetailDrawer(row)">查看详情</el-button>
                  </template>
                </el-table-column>
                </el-table>
              </div>
            </div>

            <div class="workbench-result-section">
              <div class="workbench-result-section__head">
                <h4>确认结果表</h4>
              </div>

              <div class="workbench-table-shell">
                <el-table :data="presentedSegments" border stripe class="workbench-table">
                <el-table-column label="业务线名称" min-width="180">
                  <template #default="{ row }">
                    <div
                      class="workbench-name-cell"
                      :title="row.segment_alias && row.segment_alias !== row.segment_name ? `${row.segment_name} / ${row.segment_alias}` : row.segment_name"
                    >
                      {{ row.segment_name }}
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="业务类型" width="92">
                  <template #default="{ row }">
                    <el-tag :type="segmentTypeTagType(row.segment_type)" effect="plain">
                      {{ segmentTypeLabel(row.segment_type) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="收入占比" width="92">
                  <template #default="{ row }">
                    {{ formatFlexiblePercent(row.revenue_ratio) }}
                  </template>
                </el-table-column>
                <el-table-column label="采用来源" width="104">
                  <template #default="{ row }">
                    {{ row.finalSourceLabel }}
                  </template>
                </el-table-column>
                <el-table-column label="最终分类结果" min-width="220">
                  <template #default="{ row }">
                    <div class="workbench-result-block" :title="classificationLabel(row.finalClassification)">
                      <strong>{{ classificationLabel(row.finalClassification) }}</strong>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="置信度" width="88">
                  <template #default="{ row }">
                    {{ formatConfidence(row.finalClassification?.confidence) }}
                  </template>
                </el-table-column>
                <el-table-column label="当前状态" width="92">
                  <template #default="{ row }">
                    {{ row.finalStatus }}
                  </template>
                </el-table-column>
                <el-table-column
                  label="确认"
                  width="92"
                  align="center"
                  class-name="workbench-table__action-cell"
                >
                  <template #default="{ row }">
                    <el-button link type="primary" @click="toggleConfirmation(row.id)">
                      {{ row.finalStatus === '已确认' ? '取消确认' : '标记确认' }}
                    </el-button>
                  </template>
                </el-table-column>
                <el-table-column
                  label="修订"
                  width="92"
                  align="center"
                  class-name="workbench-table__action-cell"
                >
                  <template #default="{ row }">
                    <el-button link @click="openManualOverrideDrawer(row)">人工征订</el-button>
                  </template>
                </el-table-column>
                </el-table>
              </div>
            </div>
          </div>
        </template>

        <el-empty
          v-else
          description="尚未运行规则分析"
          :image-size="88"
        />
      </section>
    </div>

    <el-drawer
      v-model="detailDrawerVisible"
      size="min(980px, 94vw)"
      :with-header="false"
      append-to-body
    >
      <div v-if="selectedSegmentPresentation" class="workbench-detail">
        <header class="workbench-detail__header">
          <div class="workbench-detail__copy">
            <span class="workbench-shell__eyebrow">业务线详情</span>
            <div class="workbench-detail__title-row">
              <h3>{{ selectedSegmentPresentation.segment_alias || selectedSegmentPresentation.segment_name }}</h3>
              <el-tag effect="plain">
                {{ reviewStatusLabel(selectedSegmentPresentation.ruleClassification?.review_status) }}
              </el-tag>
              <el-tag effect="plain" type="info">
                {{ segmentTypeLabel(selectedSegmentPresentation.segment_type) }}
              </el-tag>
            </div>
            <p>{{ selectedSegmentPresentation.segment_name }}</p>
          </div>
          <el-tooltip content="返回" placement="left">
            <el-button circle plain :icon="ArrowLeft" @click="closeDetailDrawer" />
          </el-tooltip>
        </header>

        <section class="workbench-detail__section">
          <div class="section-heading">
            <div>
              <h3>当前规则结果</h3>
            </div>
          </div>

          <div class="workbench-detail__grid">
            <article class="workbench-detail__card">
              <span>当前确认分类</span>
              <strong>{{ classificationLabel(selectedSegmentPresentation.finalClassification) }}</strong>
            </article>
            <article class="workbench-detail__card">
              <span>当前状态</span>
              <strong>{{ selectedSegmentPresentation.finalStatus }}</strong>
            </article>
            <article class="workbench-detail__card">
              <span>一级分类</span>
              <strong>{{ selectedSegmentPresentation.ruleClassification?.level_1 || '—' }}</strong>
            </article>
            <article class="workbench-detail__card">
              <span>二级分类</span>
              <strong>{{ selectedSegmentPresentation.ruleClassification?.level_2 || '—' }}</strong>
            </article>
            <article class="workbench-detail__card">
              <span>三级分类</span>
              <strong>{{ selectedSegmentPresentation.ruleClassification?.level_3 || '—' }}</strong>
            </article>
            <article class="workbench-detail__card">
              <span>四级分类</span>
              <strong>{{ selectedSegmentPresentation.ruleClassification?.level_4 || '—' }}</strong>
            </article>
            <article class="workbench-detail__card">
              <span>结果来源</span>
              <strong>规则结果</strong>
            </article>
            <article class="workbench-detail__card">
              <span>规则依据（可读）</span>
              <strong>{{ selectedSegmentPresentation.readable_mapping_basis }}</strong>
            </article>
          </div>

          <details
            v-if="selectedSegmentPresentation.ruleClassification?.mapping_basis"
            class="workbench-detail__raw"
          >
            <summary>展开查看原始规则依据</summary>
            <pre>{{ selectedSegmentPresentation.ruleClassification.mapping_basis }}</pre>
          </details>
        </section>

        <section class="workbench-detail__section">
          <div class="section-heading">
            <div>
              <h3>LLM 分析结果</h3>
            </div>
          </div>

          <div class="workbench-detail__grid">
            <article class="workbench-detail__card">
              <span>结果来源</span>
              <strong>{{ selectedSegmentPresentation.llmClassification ? '模型辅助结果（占位）' : '待分析' }}</strong>
            </article>
            <article class="workbench-detail__card">
              <span>分类摘要</span>
              <strong>
                {{
                  selectedSegmentPresentation.llmClassification
                    ? classificationLabel(selectedSegmentPresentation.llmClassification)
                    : '尚未生成 LLM 占位结果'
                }}
              </strong>
            </article>
            <article class="workbench-detail__card workbench-detail__card--wide">
              <span>可读解释</span>
              <strong>
                {{
                  selectedSegmentPresentation.llmClassification?.readable_mapping_basis ||
                  '点击工作台中的“LLM 分析”后，会先生成一版占位结果。'
                }}
              </strong>
            </article>
          </div>
        </section>

        <section class="workbench-detail__section">
          <div class="section-heading">
            <div>
              <h3>人工征订</h3>
            </div>
          </div>

          <div class="workbench-detail__manual-grid">
            <el-form-item label="人工修订后 Level1">
              <el-input v-model="manualDrafts[selectedSegmentPresentation.id].level_1" placeholder="一级分类" />
            </el-form-item>
            <el-form-item label="人工修订后 Level2">
              <el-input v-model="manualDrafts[selectedSegmentPresentation.id].level_2" placeholder="二级分类" />
            </el-form-item>
            <el-form-item label="人工修订后 Level3">
              <el-input v-model="manualDrafts[selectedSegmentPresentation.id].level_3" placeholder="三级分类" />
            </el-form-item>
            <el-form-item label="人工修订后 Level4">
              <el-input v-model="manualDrafts[selectedSegmentPresentation.id].level_4" placeholder="四级分类" />
            </el-form-item>
          </div>
          <el-form-item label="人工修订依据">
            <el-input
              v-model="manualDrafts[selectedSegmentPresentation.id].manual_override_basis"
              type="textarea"
              :rows="4"
              placeholder="请填写人工调整当前分类结果的依据，例如业务线主营属性、披露描述、研究判断等。"
            />
          </el-form-item>
          <div class="workbench-detail__manual-actions">
            <el-button type="primary" @click="applyManualOverride(selectedSegmentPresentation.id)">
              应用人工修订
            </el-button>
          </div>
        </section>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.workbench-shell {
  --workbench-section-gap: 28px;
  --workbench-panel-padding: 24px;
  --workbench-panel-radius: 24px;
  --workbench-content-gap: 18px;
  --workbench-subsection-gap: 24px;
  --workbench-heading-gap: 10px;
  --workbench-card-gap: 16px;
  --workbench-field-gap: 16px;
  --workbench-button-gap: 10px;
  --workbench-table-gap: 12px;
  --workbench-table-cell-y: 10px;
  --workbench-table-cell-x: 12px;
  --workbench-section-title-size: 18px;
  --workbench-section-title-weight: 600;
  --workbench-subtitle-size: 16px;
  --workbench-body-size: 13px;
  --workbench-label-size: 13px;
  --workbench-caption-size: 12px;
  --workbench-secondary-text: #6f8194;
  display: grid;
  gap: var(--workbench-section-gap);
  min-width: 0;
  padding-bottom: 32px;
}

.workbench-shell__header,
.workbench-panel {
  padding: var(--workbench-panel-padding);
  border-radius: var(--workbench-panel-radius);
  min-width: 0;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 16px 36px rgba(15, 35, 58, 0.04);
}

.workbench-shell__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.workbench-shell__header-copy {
  display: grid;
  gap: 14px;
  min-width: 0;
}

.workbench-shell__eyebrow {
  display: inline-flex;
  width: fit-content;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(144, 116, 77, 0.18);
  background: rgba(255, 249, 240, 0.84);
  color: #8b6a3d;
  font-size: 11px;
  line-height: 1.2;
  letter-spacing: 0.08em;
}

.workbench-shell__title-row,
.workbench-detail__title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.workbench-shell__title-row h2,
.workbench-detail__title-row h3 {
  margin: 0;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
  line-height: 1.3;
}

.workbench-shell__title-row h2 {
  font-size: 28px;
}

.workbench-shell__header-copy p,
.workbench-detail__copy p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.72;
}

.workbench-shell__body {
  display: grid;
  gap: var(--workbench-section-gap);
}

.section-heading {
  display: grid;
  gap: var(--workbench-heading-gap);
  margin-bottom: 20px;
}

.section-heading h3 {
  margin: 0;
  color: var(--brand-ink);
  font-size: var(--workbench-section-title-size);
  font-weight: var(--workbench-section-title-weight);
  line-height: 1.4;
}

.section-heading--primary h3 {
  font-size: var(--workbench-section-title-size);
  font-weight: var(--workbench-section-title-weight);
  line-height: 1.4;
}

.workbench-input-workspace,
.workbench-results-flow {
  display: grid;
  gap: 28px;
}

.workbench-input-subsection {
  display: grid;
  gap: 20px;
}

.workbench-input-subsection--segments {
  padding: 0;
  border-radius: 0;
  background: transparent;
  border: 0;
}

.workbench-company-form {
  display: grid;
}

.workbench-company-stack,
.workbench-segment-grid,
.workbench-detail__grid,
.workbench-detail__manual-grid {
  display: grid;
  gap: var(--workbench-field-gap);
}

.workbench-segment-grid,
.workbench-detail__grid,
.workbench-detail__manual-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.workbench-segment-head,
.workbench-result-section__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.workbench-segment-head {
  margin-bottom: 16px;
}

.workbench-segment-head h3,
.workbench-result-section__head h4,
.workbench-chart-card__head h4 {
  margin: 0;
  color: var(--brand-ink);
  font-size: var(--workbench-subtitle-size);
  font-weight: 600;
  line-height: 1.45;
}

.workbench-segment-head__actions,
.workbench-list-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--workbench-button-gap);
}

.workbench-segment-head__actions {
  justify-content: flex-end;
}

.workbench-segment-list {
  display: grid;
  gap: 22px;
}

.workbench-segment-card {
  display: grid;
  gap: var(--workbench-card-gap);
  padding: 22px;
  border-radius: 18px;
  border: 1px solid rgba(48, 95, 131, 0.12);
  background: linear-gradient(180deg, rgba(252, 249, 243, 0.94), rgba(255, 255, 255, 0.9));
}

.workbench-segment-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding-bottom: 2px;
}

.workbench-segment-card__head strong {
  color: var(--brand-ink);
  font-size: 15px;
  font-weight: 700;
  line-height: 1.45;
}

.workbench-list-actions-shell {
  margin-top: 18px;
  padding: 16px 18px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(48, 95, 131, 0.08);
}

.workbench-list-actions {
  justify-content: flex-end;
  margin-top: 0;
  padding-top: 12px;
  border-top: 1px solid rgba(48, 95, 131, 0.12);
}

.workbench-metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.workbench-metric-card,
.workbench-summary-card,
.workbench-chart-card,
.workbench-detail__card {
  display: grid;
  gap: 8px;
  padding: 20px;
  border-radius: 14px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(249, 251, 254, 0.78);
}

.workbench-metric-card span,
.workbench-summary-card span,
.workbench-detail__card span {
  color: var(--workbench-secondary-text);
  font-size: var(--workbench-label-size);
  font-weight: 600;
  line-height: 1.5;
}

.workbench-metric-card strong,
.workbench-summary-card strong,
.workbench-detail__card strong {
  color: var(--brand-ink);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.66;
  overflow-wrap: anywhere;
}

.workbench-summary-card strong {
  font-size: 17px;
}

.workbench-summary-card {
  margin-top: 10px;
}

.workbench-chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.workbench-chart-card {
  display: grid;
  gap: 14px;
  padding: 18px;
}

.workbench-chart-card__head {
  display: grid;
  gap: 8px;
  margin-bottom: 8px;
}

.workbench-chart-card :deep(.industry-pie) {
  margin-top: 8px;
}

.workbench-result-section {
  display: grid;
  gap: 14px;
  margin-top: 24px;
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(31, 59, 87, 0.08);
  min-width: 0;
}

.workbench-name-cell {
  color: var(--brand-ink);
  font-size: var(--workbench-body-size);
  font-weight: 600;
  line-height: 1.56;
  word-break: break-word;
}

.workbench-result-block {
  display: grid;
  gap: 6px;
}

.workbench-result-block strong {
  color: var(--brand-ink);
  font-size: var(--workbench-body-size);
  line-height: 1.52;
}

.workbench-result-block span,
.workbench-readable-basis {
  color: var(--workbench-secondary-text);
  font-size: var(--workbench-caption-size);
  line-height: 1.55;
  white-space: normal;
  word-break: break-word;
}

.workbench-readable-basis {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.workbench-table-shell {
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 14px 16px 10px;
  border-radius: 18px;
  background: rgba(250, 252, 255, 0.82);
  border: 1px solid rgba(31, 59, 87, 0.08);
  scrollbar-gutter: stable;
}

.workbench-table {
  width: 100%;
  margin-top: 12px;
}

.workbench-table :deep(.el-table th),
.workbench-table :deep(.el-table td) {
  padding-top: var(--workbench-table-cell-y);
  padding-bottom: var(--workbench-table-cell-y);
  padding-left: var(--workbench-table-cell-x);
  padding-right: var(--workbench-table-cell-x);
  vertical-align: middle;
}

.workbench-table :deep(.el-table th .cell) {
  color: #466077;
  font-size: var(--workbench-label-size);
  font-weight: 600;
  line-height: 1.5;
}

.workbench-table :deep(.el-table td .cell) {
  color: var(--brand-ink);
  font-size: var(--workbench-body-size);
  line-height: 1.5;
}

.workbench-table :deep(.el-table__body-wrapper .el-table__row td) {
  border-bottom-color: rgba(31, 59, 87, 0.08);
}

.workbench-table :deep(.el-button.is-link) {
  padding-top: 4px;
  padding-bottom: 4px;
  font-size: var(--workbench-body-size);
  font-weight: 600;
}

.workbench-table :deep(.workbench-table__action-cell .cell) {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
}

.workbench-table :deep(.el-tag) {
  font-size: var(--workbench-caption-size);
  line-height: 1.2;
  padding: 0 8px;
  border-radius: 999px;
}

.workbench-table :deep(.el-radio-button__inner) {
  padding: 6px 10px;
  font-size: 11px;
}

.workbench-table :deep(.el-table__header-wrapper),
.workbench-table :deep(.el-table__body-wrapper) {
  min-width: 0;
}

.workbench-panel :deep(.el-form-item) {
  margin-bottom: 0;
}

.workbench-panel :deep(.el-form-item__label),
.workbench-detail :deep(.el-form-item__label) {
  color: var(--workbench-secondary-text);
  font-size: var(--workbench-label-size);
  font-weight: 600;
  line-height: 1.6;
  padding-bottom: 8px;
}

.workbench-panel :deep(.el-input__wrapper),
.workbench-panel :deep(.el-select__wrapper),
.workbench-detail :deep(.el-input__wrapper) {
  min-height: 40px;
  font-size: var(--workbench-body-size);
  line-height: 1.65;
}

.workbench-panel :deep(.el-textarea__inner),
.workbench-detail :deep(.el-textarea__inner) {
  padding: 10px 12px;
  font-size: var(--workbench-body-size);
  line-height: 1.75;
}

.workbench-button--danger {
  color: #a85b4c;
  border-color: rgba(168, 91, 76, 0.26);
  background: rgba(255, 248, 246, 0.92);
}

.workbench-button--danger:hover,
.workbench-button--danger:focus-visible {
  color: #8f4436;
  border-color: rgba(143, 68, 54, 0.34);
  background: rgba(255, 243, 239, 0.98);
}

.workbench-detail {
  display: grid;
  gap: 24px;
  padding: 28px;
}

.workbench-detail__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.workbench-detail__copy {
  display: grid;
  gap: 12px;
}

.workbench-detail__section {
  display: grid;
  gap: 20px;
}

.workbench-detail__card--wide {
  grid-column: span 2;
}

.workbench-detail__raw {
  padding-top: 8px;
  border-top: 1px dashed rgba(77, 99, 124, 0.18);
}

.workbench-detail__raw summary {
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 12px;
}

.workbench-detail__raw pre {
  margin: 10px 0 0;
  padding: 14px;
  border-radius: 12px;
  background: rgba(18, 28, 45, 0.04);
  color: #40546a;
  font-size: 12px;
  line-height: 1.72;
  white-space: pre-wrap;
  word-break: break-word;
}

.workbench-detail__manual-actions {
  display: flex;
  justify-content: flex-start;
}

@media (max-width: 960px) {
  .workbench-segment-grid,
  .workbench-metrics-grid,
  .workbench-chart-grid,
  .workbench-detail__grid,
  .workbench-detail__manual-grid {
    grid-template-columns: 1fr;
  }

  .workbench-detail__card--wide {
    grid-column: span 1;
  }

  .workbench-segment-head,
  .workbench-result-section__head,
  .workbench-detail__header {
    flex-direction: column;
    align-items: stretch;
  }

  .workbench-segment-head__actions,
  .workbench-list-actions {
    justify-content: flex-start;
  }
}
</style>
