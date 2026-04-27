<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'

import {
  runIndustryWorkbenchLlmAnalysis,
  runIndustryWorkbenchRuleAnalysis,
} from '@/api/analysis'
import IndustryStructurePieChart from '@/components/IndustryStructurePieChart.vue'
import {
  classificationLabel,
  classifierTypeLabel,
  createWorkbenchSegment,
  formatConfidence,
  formatFlexiblePercent,
  pieChartRows,
  primaryClassification,
  profitPieChartRows,
  readableMappingBasis,
  reviewStatusLabel,
  reviewStatusTagType,
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
const ruleLoading = ref(false)
const llmLoading = ref(false)
const analysisResult = ref(null)
const llmResults = ref({})
const selectedResultSource = ref({})
const detailDrawerVisible = ref(false)
const selectedWorkbenchSegmentId = ref(null)

const currentSegments = computed(() =>
  Array.isArray(props.industryAnalysis?.segments) ? props.industryAnalysis.segments : [],
)
const hasOfficialSegments = computed(() => currentSegments.value.length > 0)
const analysisSegments = computed(() => analysisResult.value?.segments || [])
const revenueChartRows = computed(() => pieChartRows(analysisSegments.value, 'revenue_ratio', 6))
const profitChartRows = computed(() => profitPieChartRows(analysisSegments.value, 6))
const summaryValue = computed(
  () => analysisResult.value?.primary_industries?.[0] || '待生成主营分类摘要',
)
const qualityWarnings = computed(() => analysisResult.value?.quality_warnings || [])
const pendingSampleCount = computed(() =>
  analysisSegments.value.filter((segment) =>
    ['pending', 'needs_llm_review', 'needs_manual_review', 'conflicted', 'unmapped'].includes(
      primaryClassification(segment)?.review_status,
    ),
  ).length,
)

function displayValue(value, fallback = '待补充') {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

function normalizeOptionalText(value) {
  const normalized = String(value ?? '').trim()
  return normalized || null
}

function normalizeOptionalNumber(value) {
  const normalized = String(value ?? '').trim()
  return normalized || null
}

function nextSeedValue() {
  seed.value += 1
  return seed.value
}

const presentedSegments = computed(() =>
  analysisSegments.value.map((segment) => {
    const ruleClassification = primaryClassification(segment)
    const llmResult = llmResults.value[segment.id] || null
    const llmClassification = llmResult?.suggested_classification || null
    const selectedSource =
      selectedResultSource.value[segment.id] === 'llm' && llmClassification ? 'llm' : 'rule'
    const currentClassification =
      selectedSource === 'llm' && llmClassification ? llmClassification : ruleClassification
    const currentSourceLabel =
      selectedSource === 'llm' ? '模型辅助建议' : '规则分析结果'
    const currentStatusLabel = reviewStatusLabel(currentClassification?.review_status)

    return {
      ...segment,
      ruleClassification,
      llmResult,
      llmClassification,
      selectedSource,
      currentClassification,
      currentSourceLabel,
      currentStatusLabel,
      currentReadableBasis:
        selectedSource === 'llm'
          ? readableMappingBasis(
              llmClassification?.mapping_basis,
              llmClassification?.review_reason,
              llmClassification?.review_status,
            )
          : readableMappingBasis(
              ruleClassification?.mapping_basis,
              ruleClassification?.review_reason,
              ruleClassification?.review_status,
            ),
      ruleReadableBasis: readableMappingBasis(
        ruleClassification?.mapping_basis,
        ruleClassification?.review_reason,
        ruleClassification?.review_status,
      ),
      llmReadableBasis: readableMappingBasis(
        llmClassification?.mapping_basis,
        llmClassification?.review_reason,
        llmClassification?.review_status,
      ),
    }
  }),
)

const selectedSegmentPresentation = computed(
  () =>
    presentedSegments.value.find(
      (segment) => String(segment.id) === String(selectedWorkbenchSegmentId.value),
    ) || null,
)

function ensureDefaultCompanyContext() {
  if (!companyForm.company_name) {
    companyForm.company_name = props.company?.name || ''
  }
}

function resetWorkbenchInput() {
  companyForm.company_name = props.company?.name || ''
  companyForm.company_description = props.company?.description || ''
  seed.value = 1
  segmentRows.value = [createWorkbenchSegment(1)]
  analysisResult.value = null
  llmResults.value = {}
  selectedResultSource.value = {}
  detailDrawerVisible.value = false
  selectedWorkbenchSegmentId.value = null
}

function clearWorkbenchInput() {
  resetWorkbenchInput()
  ElMessage.info('已清空当前输入和分析结果。')
}

function addWorkbenchSegment() {
  segmentRows.value.push(createWorkbenchSegment(nextSeedValue()))
}

function removeWorkbenchSegment(localId) {
  if (segmentRows.value.length <= 1) {
    ElMessage.info('至少保留一条业务线用于试算。')
    return
  }
  segmentRows.value = segmentRows.value.filter((segment) => segment.localId !== localId)
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
  cloned.reporting_period =
    segment?.reporting_period || props.industryAnalysis?.selected_reporting_period || '2025A'
  cloned.segment_type = segment?.segment_type || cloned.segment_type
  return cloned
}

function loadFromCurrentResult() {
  if (!hasOfficialSegments.value) {
    ElMessage.info('当前没有可载入的正式业务线。')
    return
  }

  companyForm.company_name = props.company?.name || companyForm.company_name
  companyForm.company_description = props.company?.description || companyForm.company_description
  segmentRows.value = currentSegments.value.map((segment, index) =>
    cloneOfficialSegment(segment, index),
  )
  seed.value = Math.max(segmentRows.value.length, 1)
  analysisResult.value = null
  llmResults.value = {}
  selectedResultSource.value = {}
  detailDrawerVisible.value = false
  selectedWorkbenchSegmentId.value = null
  ElMessage.success('已载入当前企业业务线，可继续分析。')
}

function buildWorkbenchPayload() {
  const companyName = String(companyForm.company_name ?? '').trim()
  if (!companyName) {
    throw new Error('请先填写公司名称。')
  }

  const normalizedSegments = segmentRows.value
    .map((segment, index) => {
      const segmentName = String(segment.segment_name ?? '').trim()
      const hasAnyContent = [
        segmentName,
        String(segment.segment_alias ?? '').trim(),
        String(segment.description ?? '').trim(),
        String(segment.revenue_ratio ?? '').trim(),
        String(segment.profit_ratio ?? '').trim(),
        String(segment.reporting_period ?? '').trim(),
      ].some(Boolean)

      if (!hasAnyContent) {
        return null
      }
      if (!segmentName) {
        throw new Error(`第 ${index + 1} 条业务线缺少名称。`)
      }

      return {
        local_id: segment.localId,
        segment_name: segmentName,
        segment_alias: normalizeOptionalText(segment.segment_alias),
        description: normalizeOptionalText(segment.description),
        revenue_ratio: normalizeOptionalNumber(segment.revenue_ratio),
        profit_ratio: normalizeOptionalNumber(segment.profit_ratio),
        reporting_period: normalizeOptionalText(segment.reporting_period),
        segment_type: segment.segment_type || 'secondary',
      }
    })
    .filter(Boolean)

  if (!normalizedSegments.length) {
    throw new Error('请至少填写一条业务线后再执行分析。')
  }

  return {
    company_name: companyName,
    company_description: normalizeOptionalText(companyForm.company_description),
    segments: normalizedSegments,
  }
}

function initializeSegmentState(segments) {
  selectedResultSource.value = Object.fromEntries(
    segments.map((segment) => [segment.id, 'rule']),
  )
}

async function runRuleAnalysis() {
  let payload = null
  try {
    payload = buildWorkbenchPayload()
  } catch (error) {
    ElMessage.warning(error.message)
    return
  }

  ruleLoading.value = true
  try {
    const response = await runIndustryWorkbenchRuleAnalysis(payload)
    analysisResult.value = response
    llmResults.value = {}
    initializeSegmentState(response.segments || [])
    detailDrawerVisible.value = false
    selectedWorkbenchSegmentId.value = null
    ElMessage.success('已完成规则分析。')
  } catch (error) {
    ElMessage.warning(error.message || '规则分析失败，请稍后重试。')
  } finally {
    ruleLoading.value = false
  }
}

async function triggerWorkbenchLlm() {
  let payload = null
  try {
    payload = buildWorkbenchPayload()
  } catch (error) {
    ElMessage.warning(error.message)
    return
  }

  llmLoading.value = true
  try {
    const response = await runIndustryWorkbenchLlmAnalysis(payload)
    analysisResult.value = response.rule_analysis
    llmResults.value = Object.fromEntries(
      (response.llm_results || []).map((item) => [item.segment_id, item]),
    )
    initializeSegmentState(response.rule_analysis?.segments || [])
    ElMessage.success('已完成模型分析。')
  } catch (error) {
    ElMessage.warning(error.message || '模型分析失败，请稍后重试。')
  } finally {
    llmLoading.value = false
  }
}

function updateSelectedSource(segmentId, source) {
  if (source === 'llm' && !llmResults.value[segmentId]) {
    return
  }
  selectedResultSource.value = {
    ...selectedResultSource.value,
    [segmentId]: source,
  }
}

function openDetailDrawer(segment) {
  selectedWorkbenchSegmentId.value = segment.id
  detailDrawerVisible.value = true
}

function closeDetailDrawer() {
  detailDrawerVisible.value = false
}

function llmSourceLabel() {
  return '模型辅助建议'
}

function llmStatusLabel(status) {
  if (status === 'success') {
    return '建议已生成'
  }
  if (status === 'fallback') {
    return '保守回退'
  }
  return status || '待分析'
}

function llmStatusTagType(status) {
  if (status === 'success') {
    return 'success'
  }
  if (status === 'fallback') {
    return 'warning'
  }
  return 'info'
}

function contextSummary(row) {
  const requestContext = row?.llmResult?.request_context
  if (!requestContext) {
    return '尚未生成模型参考上下文。'
  }
  return (
    requestContext.company_description ||
    requestContext.company_text ||
    requestContext.peer_text ||
    requestContext.description ||
    '当前上下文信息较少。'
  )
}

watch(
  () => props.company?.name,
  () => {
    ensureDefaultCompanyContext()
  },
  { immediate: true },
)

watch(
  () => props.company?.description,
  (value) => {
    if (!companyForm.company_description) {
      companyForm.company_description = value || ''
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="workbench-shell">
    <header class="workbench-shell__header surface-card">
      <div class="workbench-shell__header-copy">
        <span class="workbench-shell__eyebrow">Industry Workbench</span>
        <div class="workbench-shell__title-row">
          <h2>产业分析工作台</h2>
        </div>
        <p>用于录入业务线样本，并对规则分析结果与模型建议进行对比。</p>
      </div>
      <el-tooltip content="返回" placement="left">
        <el-button circle plain :icon="ArrowLeft" @click="emit('close')" />
      </el-tooltip>
    </header>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="workbench-alert"
      title="工作台分析结果用于比较与复核，不影响当前企业分析页面。"
    />

    <div class="workbench-shell__body">
      <section class="surface-card workbench-panel">
        <div class="section-heading">
          <div>
            <h3>输入区</h3>
            <p>输入公司背景与业务线结构后，可分别触发规则分析或模型分析。</p>
          </div>
        </div>

        <div class="workbench-input-context">
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
                  placeholder="补充公司主营方向、产业定位、平台属性或上下游信息。"
                />
              </el-form-item>
            </div>
          </el-form>
        </div>

        <div class="workbench-input-list-section">
          <div class="workbench-segment-head">
            <div class="workbench-segment-head__copy">
              <h3>业务线输入列表</h3>
              <p>在这里整理业务线样本，并发起规则分析或模型分析。</p>
            </div>
            <div class="workbench-segment-head__actions">
              <el-button plain type="primary" @click="addWorkbenchSegment">新增业务线</el-button>
              <el-button plain :disabled="!hasOfficialSegments" @click="loadFromCurrentResult">
                载入当前正式业务线
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
                  placeholder="补充产品、客户、商业模式或行业语义，帮助规则和模型更准确判断。"
                />
              </el-form-item>
            </article>
          </div>
        </div>

        <div class="workbench-list-actions-shell">
          <div class="workbench-list-actions">
            <el-button
              type="primary"
              plain
              :loading="ruleLoading"
              :disabled="llmLoading"
              @click="runRuleAnalysis"
            >
              规则分析
            </el-button>
            <el-button
              type="primary"
              :loading="llmLoading"
              :disabled="ruleLoading"
              @click="triggerWorkbenchLlm"
            >
              LLM分析
            </el-button>
            <el-button disabled>导入正式结果</el-button>
          </div>
        </div>
      </section>

      <section class="surface-card workbench-panel">
        <div class="section-heading">
          <div>
            <h3>结果区</h3>
            <p>对比展示规则分析结果、模型建议与当前选定结果。</p>
          </div>
        </div>

        <template v-if="analysisResult">
          <div class="workbench-results-flow">
            <div class="workbench-metrics-grid">
              <article class="workbench-metric-card">
                <span>业务线数量</span>
                <strong>{{ analysisSegments.length }}</strong>
              </article>
              <article class="workbench-metric-card">
                <span>待进一步分析样本</span>
                <strong>{{ pendingSampleCount }}</strong>
              </article>
            </div>

            <article class="workbench-summary-card">
              <span>主营分类摘要</span>
              <strong>{{ summaryValue }}</strong>
            </article>

            <el-alert
              v-for="warning in qualityWarnings"
              :key="warning"
              type="warning"
              :closable="false"
              show-icon
              :title="warning"
            />

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
                  empty-description="当前没有可用于生成利润结构图的业务线占比数据。"
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
                      <div class="workbench-name-cell">
                        {{ row.segment_name }}
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column label="业务类型" width="100">
                    <template #default="{ row }">
                      <el-tag :type="segmentTypeTagType(row.segment_type)" effect="plain">
                        {{ segmentTypeLabel(row.segment_type) }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="收入占比" width="96">
                    <template #default="{ row }">
                      {{ formatFlexiblePercent(row.revenue_ratio) }}
                    </template>
                  </el-table-column>
                  <el-table-column label="规则分析结果" min-width="220">
                    <template #default="{ row }">
                      <div class="workbench-result-block">
                        <strong>{{ classificationLabel(row.ruleClassification) }}</strong>
                        <span>{{ row.ruleReadableBasis }}</span>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column label="模型辅助建议" min-width="240">
                    <template #default="{ row }">
                      <div v-if="row.llmClassification" class="workbench-result-block">
                        <div class="workbench-inline-tags">
                          <el-tag :type="llmStatusTagType(row.llmResult?.status)" effect="plain">
                            {{ llmStatusLabel(row.llmResult?.status) }}
                          </el-tag>
                          <el-tag effect="plain" type="info">DeepSeek</el-tag>
                        </div>
                        <strong>{{ classificationLabel(row.llmClassification) }}</strong>
                        <span>{{ row.llmResult?.message }}</span>
                      </div>
                      <span v-else class="workbench-empty-inline">尚未执行模型分析</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="结果来源" width="148">
                    <template #default="{ row }">
                      <el-radio-group
                        size="small"
                        :model-value="row.selectedSource"
                        @change="(value) => updateSelectedSource(row.id, value)"
                      >
                        <el-radio-button label="rule">规则</el-radio-button>
                        <el-radio-button label="llm" :disabled="!row.llmClassification">
                          模型
                        </el-radio-button>
                      </el-radio-group>
                    </template>
                  </el-table-column>
                  <el-table-column label="当前分析结果" min-width="240">
                    <template #default="{ row }">
                      <div class="workbench-result-block">
                        <strong>{{ classificationLabel(row.currentClassification) }}</strong>
                        <div class="workbench-inline-tags">
                          <el-tag
                            :type="row.manualClassification ? 'success' : reviewStatusTagType(row.currentClassification?.review_status)"
                            effect="plain"
                          >
                            {{ row.currentStatusLabel }}
                          </el-tag>
                          <el-tag effect="plain" type="info">
                            {{ row.currentSourceLabel }}
                          </el-tag>
                        </div>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column label="置信度" width="88">
                    <template #default="{ row }">
                      {{ formatConfidence(row.currentClassification?.confidence) }}
                    </template>
                  </el-table-column>
                  <el-table-column label="映射依据" min-width="220">
                    <template #default="{ row }">
                      <span class="workbench-readable-basis">{{ row.currentReadableBasis }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="详情" width="88" align="center">
                    <template #default="{ row }">
                      <el-button link type="primary" @click="openDetailDrawer(row)">
                        查看
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </div>
        </template>

        <el-empty
          v-else
          description="尚未运行分析"
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
            <span class="workbench-shell__eyebrow">结果对比与修订</span>
            <div class="workbench-detail__title-row">
              <h3>
                {{ selectedSegmentPresentation.segment_alias || selectedSegmentPresentation.segment_name }}
              </h3>
              <el-tag effect="plain">
                {{ segmentTypeLabel(selectedSegmentPresentation.segment_type) }}
              </el-tag>
            </div>
            <p>
              按“当前结果、模型建议、人工修订”的顺序查看这一条业务线，便于对比后再决定是否调整。
            </p>
          </div>
          <el-tooltip content="返回" placement="left">
            <el-button circle plain :icon="ArrowLeft" @click="closeDetailDrawer" />
          </el-tooltip>
        </header>

        <section class="workbench-detail__section">
          <div class="detail-section__header">
            <div>
              <h3>规则分析结果</h3>
              <p>这里展示当前业务线的规则分析结果，可作为后续比较的基准。</p>
            </div>
            <div class="workbench-inline-tags">
              <el-tag effect="plain" type="info">
                规则分析结果
              </el-tag>
              <el-tag
                :type="reviewStatusTagType(selectedSegmentPresentation.ruleClassification?.review_status)"
                effect="plain"
              >
                {{ reviewStatusLabel(selectedSegmentPresentation.ruleClassification?.review_status) }}
              </el-tag>
            </div>
          </div>

          <div class="detail-card-grid">
            <article class="detail-card detail-card--emphasis">
              <span>当前确认分类</span>
              <strong>{{ classificationLabel(selectedSegmentPresentation.ruleClassification) }}</strong>
            </article>
            <article class="detail-card">
              <span>当前状态</span>
              <strong>{{ reviewStatusLabel(selectedSegmentPresentation.ruleClassification?.review_status) }}</strong>
            </article>
            <article class="detail-card">
              <span>一级分类</span>
              <strong>{{ displayValue(selectedSegmentPresentation.ruleClassification?.level_1) }}</strong>
            </article>
            <article class="detail-card">
              <span>二级分类</span>
              <strong>{{ displayValue(selectedSegmentPresentation.ruleClassification?.level_2) }}</strong>
            </article>
            <article class="detail-card">
              <span>三级分类</span>
              <strong>{{ displayValue(selectedSegmentPresentation.ruleClassification?.level_3) }}</strong>
            </article>
            <article class="detail-card">
              <span>四级分类</span>
              <strong>{{ displayValue(selectedSegmentPresentation.ruleClassification?.level_4) }}</strong>
            </article>
            <article class="detail-card">
              <span>结果来源</span>
              <strong>规则分析结果</strong>
            </article>
            <article class="detail-card detail-card--wide">
              <span>规则依据</span>
              <strong>{{ selectedSegmentPresentation.ruleReadableBasis }}</strong>
            </article>
          </div>

          <details
            v-if="selectedSegmentPresentation.ruleClassification?.mapping_basis"
            class="detail-collapse"
          >
            <summary>查看原始规则依据</summary>
            <pre>{{ selectedSegmentPresentation.ruleClassification.mapping_basis }}</pre>
          </details>
        </section>

        <section class="workbench-detail__section">
          <div class="detail-section__header">
            <div>
              <h3>模型辅助建议</h3>
              <p>这里展示模型辅助建议，便于与规则分析结果进行比较。</p>
            </div>
            <div v-if="selectedSegmentPresentation.llmClassification" class="workbench-inline-tags">
              <el-tag :type="llmStatusTagType(selectedSegmentPresentation.llmResult?.status)" effect="plain">
                {{ llmStatusLabel(selectedSegmentPresentation.llmResult?.status) }}
              </el-tag>
              <el-tag effect="plain" type="info">DeepSeek</el-tag>
            </div>
          </div>

          <template v-if="selectedSegmentPresentation.llmClassification">
            <div class="detail-card-grid">
              <article class="detail-card detail-card--emphasis">
                <span>建议分类</span>
                <strong>{{ classificationLabel(selectedSegmentPresentation.llmClassification) }}</strong>
              </article>
              <article class="detail-card">
                <span>建议状态</span>
                <strong>{{ reviewStatusLabel(selectedSegmentPresentation.llmClassification?.review_status) }}</strong>
              </article>
              <article class="detail-card">
                <span>一级分类</span>
                <strong>{{ displayValue(selectedSegmentPresentation.llmClassification?.level_1) }}</strong>
              </article>
              <article class="detail-card">
                <span>二级分类</span>
                <strong>{{ displayValue(selectedSegmentPresentation.llmClassification?.level_2) }}</strong>
              </article>
              <article class="detail-card">
                <span>三级分类</span>
                <strong>{{ displayValue(selectedSegmentPresentation.llmClassification?.level_3) }}</strong>
              </article>
              <article class="detail-card">
                <span>四级分类</span>
                <strong>{{ displayValue(selectedSegmentPresentation.llmClassification?.level_4) }}</strong>
              </article>
              <article class="detail-card">
                <span>结果来源</span>
                <strong>{{ llmSourceLabel() }}</strong>
              </article>
              <article class="detail-card">
                <span>置信度</span>
                <strong>{{ formatConfidence(selectedSegmentPresentation.llmClassification?.confidence) }}</strong>
              </article>
              <article class="detail-card detail-card--wide">
                <span>建议依据</span>
                <strong>{{ selectedSegmentPresentation.llmReadableBasis }}</strong>
              </article>
            </div>

            <div class="detail-secondary-stack">
              <details class="detail-collapse">
                <summary>查看模型参考上下文</summary>
                <pre>{{ contextSummary(selectedSegmentPresentation) }}</pre>
              </details>

              <details
                v-if="selectedSegmentPresentation.llmClassification?.mapping_basis"
                class="detail-collapse"
              >
                <summary>查看原始建议依据</summary>
                <pre>{{ selectedSegmentPresentation.llmClassification.mapping_basis }}</pre>
              </details>
            </div>
          </template>

          <el-empty
            v-else
            description="尚未执行模型分析"
            :image-size="72"
          />
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
  --workbench-heading-gap: 10px;
  --workbench-card-gap: 16px;
  --workbench-field-gap: 16px;
  --workbench-button-gap: 10px;
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
.workbench-detail__copy p,
.section-heading p,
.detail-section__header p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.72;
}

.workbench-alert {
  border-radius: 18px;
}

.workbench-shell__body,
.workbench-results-flow,
.workbench-segment-list,
.workbench-company-form,
.workbench-detail {
  display: grid;
  gap: 24px;
}

.workbench-input-context,
.workbench-input-list-section {
  display: grid;
  gap: 20px;
}

.workbench-input-context {
  padding-bottom: 14px;
}

.workbench-input-list-section {
  gap: 26px;
  padding-top: 18px;
  border-top: 1px solid rgba(31, 59, 87, 0.08);
}

.section-heading,
.detail-section__header {
  display: grid;
  gap: var(--workbench-heading-gap);
}

.section-heading {
  margin-bottom: 20px;
}

.section-heading h3,
.detail-section__header h3 {
  margin: 0;
  color: var(--brand-ink);
  font-size: var(--workbench-section-title-size);
  font-weight: var(--workbench-section-title-weight);
  line-height: 1.4;
}

.workbench-company-stack {
  display: grid;
  gap: var(--workbench-field-gap);
  grid-template-columns: minmax(0, 1fr);
}

.workbench-segment-grid,
.detail-card-grid,
.detail-form-grid {
  display: grid;
  gap: var(--workbench-field-gap);
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.workbench-segment-head,
.workbench-result-section__head,
.workbench-detail__header,
.detail-section__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.workbench-segment-head {
  padding: 6px 0 4px;
}

.workbench-segment-head__actions,
.workbench-list-actions,
.workbench-inline-tags,
.detail-form-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.workbench-segment-head__actions {
  justify-content: flex-end;
  align-self: flex-start;
}

.workbench-segment-head__copy {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.workbench-segment-head__copy h3 {
  margin: 0;
  color: var(--brand-ink);
  font-size: var(--workbench-section-title-size);
  font-weight: var(--workbench-section-title-weight);
  line-height: 1.4;
}

.workbench-segment-head__copy p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.72;
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
}

.workbench-segment-card__head strong,
.workbench-name-cell {
  color: var(--brand-ink);
  font-size: 15px;
  font-weight: 700;
  line-height: 1.45;
}

.workbench-list-actions-shell {
  margin-top: 4px;
  padding: 16px 18px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(48, 95, 131, 0.08);
}

.workbench-list-actions {
  justify-content: flex-end;
}

.workbench-metrics-grid,
.workbench-chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.workbench-metric-card,
.workbench-summary-card,
.workbench-chart-card,
.detail-card,
.detail-form-shell {
  display: grid;
  gap: 8px;
  padding: 20px;
  border-radius: 18px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(249, 251, 254, 0.78);
}

.detail-card--emphasis {
  background: linear-gradient(180deg, rgba(251, 248, 241, 0.96), rgba(255, 255, 255, 0.92));
  border-color: rgba(155, 117, 67, 0.18);
}

.workbench-metric-card span,
.workbench-summary-card span,
.detail-card span {
  color: var(--workbench-secondary-text);
  font-size: var(--workbench-label-size);
  font-weight: 600;
  line-height: 1.5;
}

.workbench-metric-card strong,
.workbench-summary-card strong,
.detail-card strong,
.workbench-result-block strong {
  color: var(--brand-ink);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.66;
  overflow-wrap: anywhere;
}

.workbench-summary-card strong {
  font-size: 17px;
}

.workbench-chart-card {
  gap: 14px;
  padding: 18px;
}

.workbench-chart-card__head h4,
.workbench-result-section__head h4 {
  margin: 0;
  color: var(--brand-ink);
  font-size: var(--workbench-subtitle-size);
  font-weight: 600;
}

.workbench-result-section {
  display: grid;
  gap: 14px;
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(31, 59, 87, 0.08);
  min-width: 0;
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
}

.workbench-result-block {
  display: grid;
  gap: 6px;
}

.workbench-result-block span,
.workbench-readable-basis,
.workbench-empty-inline,
.detail-form-hint {
  color: var(--workbench-secondary-text);
  font-size: var(--workbench-caption-size);
  line-height: 1.55;
  white-space: normal;
  word-break: break-word;
}

.workbench-readable-basis {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
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

.workbench-table :deep(.el-button.is-link) {
  padding-top: 4px;
  padding-bottom: 4px;
  font-size: var(--workbench-body-size);
  font-weight: 600;
}

.workbench-table :deep(.el-radio-button__inner) {
  padding: 6px 10px;
  font-size: 11px;
}

.workbench-panel :deep(.el-form-item),
.workbench-detail :deep(.el-form-item) {
  margin-bottom: 0;
}

.workbench-panel :deep(.el-form-item__label),
.workbench-detail :deep(.el-form-item__label) {
  color: var(--workbench-secondary-text);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.55;
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

.workbench-detail__section,
.detail-secondary-stack {
  display: grid;
  gap: 18px;
}

.detail-card--wide {
  grid-column: span 2;
}

.detail-collapse {
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px dashed rgba(77, 99, 124, 0.18);
  background: rgba(255, 255, 255, 0.72);
}

.detail-collapse summary {
  cursor: pointer;
  color: #4d6278;
  font-size: 13px;
  font-weight: 600;
}

.detail-collapse pre {
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

@media (max-width: 960px) {
  .workbench-company-stack,
  .workbench-segment-grid,
  .workbench-metrics-grid,
  .workbench-chart-grid,
  .detail-card-grid {
    grid-template-columns: 1fr;
  }

  .detail-card--wide {
    grid-column: span 1;
  }

  .workbench-segment-head,
  .workbench-result-section__head,
  .workbench-detail__header,
  .detail-section__header,
  .workbench-shell__header {
    flex-direction: column;
    align-items: stretch;
  }

  .workbench-segment-head__actions,
  .workbench-list-actions {
    justify-content: flex-start;
  }
}
</style>
