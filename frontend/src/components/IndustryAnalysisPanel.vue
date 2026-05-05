<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'

import {
  confirmBusinessSegmentLlmClassification,
  fetchBusinessSegmentClassifications,
  requestBusinessSegmentLlmAnalysis,
  submitBusinessSegmentManualClassification,
} from '@/api/analysis'
import IndustryStructurePieChart from '@/components/IndustryStructurePieChart.vue'
import {
  classificationSummary,
  classifierTypeLabel,
  deriveIndustryStatusCounts,
  formatConfidence,
  formatFlexiblePercent,
  llmRecommended,
  needsFurtherAnalysis,
  pieChartRows,
  primaryClassification,
  reviewReasonLabel,
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
  loading: {
    type: Boolean,
    default: false,
  },
})
const emit = defineEmits(['refresh-industry-analysis'])

const detailDrawerVisible = ref(false)
const detailLoading = ref(false)
const llmLoading = ref(false)
const llmConfirming = ref(false)
const manualSaving = ref(false)
const llmErrorMessage = ref('')
const selectedSegmentId = ref(null)
const selectedSegmentSnapshot = ref(null)
const detailClassifications = ref([])
const llmSuggestionPayload = ref(null)
const manualOverrides = ref({})
const manualDraft = reactive({
  level_1: '',
  level_2: '',
  level_3: '',
  level_4: '',
  mapping_basis: '',
  final_confirmed: true,
})

const rawSegments = computed(() => props.industryAnalysis?.segments || [])
const displaySegments = computed(() => rawSegments.value.map((segment) => applyOverride(segment)))
const localIndustryAnalysis = computed(() => ({
  ...props.industryAnalysis,
  segments: displaySegments.value,
}))
const statusCounts = computed(() => deriveIndustryStatusCounts(localIndustryAnalysis.value))
const revenueChartRows = computed(() => pieChartRows(displaySegments.value, 'revenue_ratio', 6))
const profitChartRows = computed(() => pieChartRows(displaySegments.value, 'profit_ratio', 6))
const primaryIndustrySummary = computed(
  () => props.industryAnalysis?.primary_industries?.[0] || '待进一步归纳',
)
const reportPeriod = computed(
  () => props.industryAnalysis?.selected_reporting_period || '暂无',
)
const qualityWarnings = computed(() => props.industryAnalysis?.quality_warnings || [])
const allIndustryLabels = computed(() => props.industryAnalysis?.all_industry_labels || [])
const flaggedSegments = computed(() =>
  displaySegments.value.filter((segment) =>
    ['pending', 'needs_llm_review', 'needs_manual_review', 'conflicted', 'unmapped'].includes(
      resolvedClassification(segment)?.review_status,
    ),
  ),
)

function cloneClassification(classification) {
  if (!classification) {
    return null
  }
  return {
    ...classification,
    confidence: classification.confidence,
  }
}

function applyOverride(segment) {
  const override = manualOverrides.value[segment.id]
  if (!override) {
    return segment
  }
  return {
    ...segment,
    classifications: [override],
    classification_labels: [
      [override.level_1, override.level_2, override.level_3, override.level_4]
        .filter(Boolean)
        .join(' > '),
    ].filter(Boolean),
    confidence: override.confidence,
  }
}

const legacyTopSummaryMetrics = computed(() => [
  {
    label: '业务线总数',
    value: props.industryAnalysis?.business_segment_count ?? displaySegments.value.length,
    emphasis: false,
  },
  {
    label: '主营分类摘要',
    value: primaryIndustrySummary.value,
    emphasis: true,
  },
  {
    label: '当前报告期',
    value: reportPeriod.value,
    emphasis: false,
  },
  {
    label: '待进一步分析',
    value: needsFurtherAnalysis(localIndustryAnalysis.value) ? '是' : '否',
    emphasis: needsFurtherAnalysis(localIndustryAnalysis.value),
  },
])

const pendingAnalysisSummary = computed(() => {
  const counts = statusCounts.value
  const total =
    counts.pending +
    counts.needs_llm_review +
    counts.needs_manual_review +
    counts.conflicted +
    counts.unmapped

  const tags = [
    { key: 'needs-llm-review', label: '待模型补判', value: counts.needs_llm_review },
    { key: 'conflicted', label: '候选冲突', value: counts.conflicted },
    { key: 'pending', label: '保守保留', value: counts.pending },
    { key: 'unmapped', label: '未映射', value: counts.unmapped },
    { key: 'needs-manual-review', label: '待人工确认', value: counts.needs_manual_review },
  ].filter((item) => item.value > 0)

  return {
    total,
    leadText: total ? `存在 ${total} 条待进一步分析业务线` : '当前无需进一步分析',
    description: total
      ? `${counts.confirmed} 条业务线已形成分类结果，可优先查看待复核样本。`
      : '当前业务线已形成可展示的分类结果。',
    tags,
    emphasis: total > 0,
  }
})

const primaryIndustryTags = computed(() =>
  allIndustryLabels.value
    .filter(Boolean)
    .slice(0, 6)
    .map((label, index) => ({
      key: `industry-label-${index}`,
      label,
    })),
)

const companyInfoTags = computed(() => {
  const tags = []
  if (props.company?.stock_code) {
    tags.push({ key: 'stock-code', label: `股票代码 ${props.company.stock_code}` })
  }
  if (props.company?.incorporation_country) {
    tags.push({ key: 'incorporation-country', label: `注册地 ${props.company.incorporation_country}` })
  }
  if (props.company?.listing_country) {
    tags.push({ key: 'listing-country', label: `上市地 ${props.company.listing_country}` })
  }
  return tags.slice(0, 2)
})

const topSummaryMetrics = computed(() => [
  {
    key: 'company-info',
    label: '当前公司',
    value: props.company?.name || `公司 ID ${props.companyId || '未提供'}`,
    description: props.company?.id ? `当前分析对象 ID：${props.company.id}` : '当前分析对象信息待补充',
    tags: companyInfoTags.value,
    emphasis: true,
  },
  {
    key: 'segment-count',
    label: '业务线总数',
    value: String(props.industryAnalysis?.business_segment_count ?? displaySegments.value.length),
    description: '纳入当前报告期分析',
    emphasis: false,
  },
  {
    key: 'primary-summary',
    label: '主营分类摘要',
    value: primaryIndustrySummary.value,
    description: '展示当前业务线的主要行业分类',
    tags: primaryIndustryTags.value,
    emphasis: true,
  },
  {
    key: 'report-period',
    label: '当前报告期',
    value: reportPeriod.value,
    description: '图表与明细沿用该期口径',
    emphasis: false,
  },
  {
    key: 'pending-analysis',
    label: '待进一步分析',
    value: pendingAnalysisSummary.value.leadText,
    description: pendingAnalysisSummary.value.description,
    tags: pendingAnalysisSummary.value.tags,
    emphasis: pendingAnalysisSummary.value.emphasis,
  },
])

const topSummaryMetricMap = computed(() =>
  Object.fromEntries(topSummaryMetrics.value.map((metric) => [metric.key, metric])),
)

const topSummaryRows = computed(() => {
  const metricMap = topSummaryMetricMap.value
  return [
    {
      key: 'primary',
      items: ['company-info', 'segment-count']
        .map((metricKey) => metricMap[metricKey])
        .filter(Boolean),
    },
    {
      key: 'status',
      items: ['report-period', 'pending-analysis']
        .map((metricKey) => metricMap[metricKey])
        .filter(Boolean),
    },
    {
      key: 'focus',
      items: ['primary-summary']
        .map((metricKey) => metricMap[metricKey])
        .filter(Boolean),
    },
  ]
})

const selectedSegment = computed(() =>
  displaySegments.value.find((segment) => String(segment.id) === String(selectedSegmentId.value)) ||
  selectedSegmentSnapshot.value,
)
const effectiveClassifications = computed(() => {
  if (selectedSegment.value && manualOverrides.value[selectedSegment.value.id]) {
    return [manualOverrides.value[selectedSegment.value.id]]
  }
  return detailClassifications.value.length
    ? detailClassifications.value
    : selectedSegment.value?.classifications || []
})
const selectedClassification = computed(() => effectiveClassifications.value[0] || null)

function normalizeComparableValue(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }
  return String(value).trim()
}

function sameClassificationShape(left, right) {
  if (!left || !right) {
    return false
  }
  return [
    'standard_system',
    'level_1',
    'level_2',
    'level_3',
    'level_4',
    'mapping_basis',
    'classifier_type',
    'review_status',
    'review_reason',
  ].every((field) => normalizeComparableValue(left[field]) === normalizeComparableValue(right[field])) &&
    Boolean(left.is_primary) === Boolean(right.is_primary) &&
    normalizeComparableValue(left.confidence) === normalizeComparableValue(right.confidence)
}

function resolvedClassification(segment) {
  return manualOverrides.value[segment.id] || primaryClassification(segment)
}

function resetManualDraft(classification) {
  manualDraft.level_1 = classification?.level_1 || ''
  manualDraft.level_2 = classification?.level_2 || ''
  manualDraft.level_3 = classification?.level_3 || ''
  manualDraft.level_4 = classification?.level_4 || ''
  manualDraft.mapping_basis = ''
  manualDraft.final_confirmed = true
}

async function openSegmentDetail(segment, options = {}) {
  selectedSegmentId.value = segment.id
  selectedSegmentSnapshot.value = segment
  detailDrawerVisible.value = true
  llmSuggestionPayload.value = null
  llmErrorMessage.value = ''
  detailLoading.value = true

  try {
    const classifications = await fetchBusinessSegmentClassifications(segment.id)
    detailClassifications.value = classifications
  } catch (error) {
    detailClassifications.value = segment.classifications || []
    ElMessage.warning(error.message || '业务线分类详情刷新失败，已回退使用当前页数据。')
  } finally {
    detailLoading.value = false
  }

  resetManualDraft(resolvedClassification(segment))
  if (options.triggerLlm) {
    await triggerLlmAnalysis(segment)
  }
}

async function triggerLlmAnalysis(segment = selectedSegment.value) {
  if (!segment?.id) {
    return
  }
  llmErrorMessage.value = ''
  llmSuggestionPayload.value = null
  llmLoading.value = true
  try {
    llmSuggestionPayload.value = await requestBusinessSegmentLlmAnalysis(segment.id)
    if (!detailDrawerVisible.value) {
      detailDrawerVisible.value = true
    }
  } catch (error) {
    ElMessage.warning(error.message || '模型分析入口暂不可用。')
  } finally {
    llmLoading.value = false
  }
}

function applyConfirmedClassificationLocally(classification) {
  if (!selectedSegment.value?.id || !classification) {
    return
  }

  const confirmedClassification = cloneClassification(classification)
  detailClassifications.value = [confirmedClassification]

  const activeSegment = selectedSegment.value || selectedSegmentSnapshot.value
  if (!activeSegment) {
    return
  }

  selectedSegmentSnapshot.value = {
    ...activeSegment,
    classifications: [confirmedClassification],
    classification_labels: [confirmedClassification.industry_label].filter(Boolean),
    confidence: confirmedClassification.confidence,
  }
}

async function refreshSelectedSegmentClassifications(segmentId = selectedSegment.value?.id) {
  if (!segmentId) {
    return []
  }
  const classifications = await fetchBusinessSegmentClassifications(segmentId)
  detailClassifications.value = classifications
  return classifications
}

async function confirmLlmSuggestion() {
  if (!selectedSegment.value?.id || !llmSuggestionClassification()) {
    return
  }

  llmConfirming.value = true
  try {
    const response = await confirmBusinessSegmentLlmClassification(
      selectedSegment.value.id,
      {
        suggested_classification: llmSuggestionClassification(),
      },
    )
    applyConfirmedClassificationLocally(response.confirmed_classification)
    llmSuggestionPayload.value = {
      ...llmSuggestionPayload.value,
      status: response.status,
      message: response.message,
      current_classification: response.confirmed_classification,
    }
    const nextOverrides = { ...manualOverrides.value }
    delete nextOverrides[selectedSegment.value.id]
    manualOverrides.value = nextOverrides
    emit('refresh-industry-analysis')
    ElMessage.success('模型建议已应用。')
  } catch (error) {
    ElMessage.warning(error.message || '模型建议应用失败。')
  } finally {
    llmConfirming.value = false
  }
}

function currentClassificationSummary(segment) {
  return classificationSummary(segment)
}

function llmSuggestionClassification() {
  return llmSuggestionPayload.value?.suggested_classification || null
}

function llmSuggestionLabel() {
  return classificationSummary({
    classifications: llmSuggestionClassification() ? [llmSuggestionClassification()] : [],
  })
}

const llmSuggestionAdopted = computed(() => {
  const suggestion = llmSuggestionClassification()
  const current = selectedClassification.value
  if (!suggestion || !current) {
    return false
  }

  return sameClassificationShape(
    {
      ...suggestion,
      classifier_type: 'llm_assisted',
      review_status: 'confirmed',
      review_reason: 'llm_suggested',
    },
    current,
  )
})

function llmClassifierTypeLabel(value) {
  if (value === 'llm_assisted') {
    return '模型辅助结果'
  }
  return classifierTypeLabel(value)
}

function llmReviewReasonLabel(value) {
  const localLabels = {
    llm_inconclusive: '模型未形成稳定判断',
    llm_response_parse_failed: '模型返回解析失败',
    clear_gics_alignment: '分类方向较为明确',
    segment_fits_gics_structure: '已匹配当前 GICS 分类结构',
    segment_clearly_fits_level_2: '已明确匹配到二级分类',
  }
  return localLabels[value] || reviewReasonLabel(value)
}

function formatLlmLevel(value) {
  return value || '未细分'
}

function llmDisplayMessage() {
  if (llmErrorMessage.value) {
    return llmErrorMessage.value
  }
  return llmSuggestionPayload.value?.message || '尚未生成模型建议。'
}

function llmContextSummary() {
  const requestContext = llmSuggestionPayload.value?.request_context
  if (!requestContext) {
    return '暂无上下文摘要'
  }
  return (
    requestContext.company_description ||
    requestContext.company_text ||
    requestContext.peer_text ||
    '暂无上下文摘要'
  )
}

const BASIS_DECISION_LABELS = {
  confirmed: '规则结果已确认',
  pending: '当前结果暂作保守保留',
  needs_llm_review: '建议引入模型辅助补判',
  needs_manual_review: '建议人工进一步复核',
  conflicted: '候选分类仍存在冲突',
  unmapped: '当前尚未形成稳定映射',
}

const BASIS_DEPTH_LABELS = {
  none: '尚未形成稳定层级',
  level_1: '已定位到一级分类',
  level_2: '已定位到二级分类',
  level_3: '已定位到三级分类',
  level_4: '已定位到四级分类',
}

const BASIS_RULE_LABELS = {
  application_software: '应用软件',
  transaction_and_payment_processing: '支付处理服务',
  interactive_media_and_advertising: '互动媒体与广告服务',
  semiconductor_manufacturing: '半导体',
  technology_hardware_devices: '硬件设备',
  renewable_power_producers: '可再生能源发电',
  none_stable: '未形成稳定规则命中',
  manual_override: '人工修订',
}

const BASIS_HIT_SCOPE_LABELS = {
  name: '业务线名称',
  alias: '业务线别名',
  description: '业务线说明',
  company: '公司上下文',
  peer: '同业参照',
}

function parseMappingBasis(raw) {
  if (!raw) {
    return {}
  }
  return raw
    .split('|')
    .map((part) => part.trim())
    .filter(Boolean)
    .reduce((accumulator, part) => {
      const separatorIndex = part.indexOf('=')
      if (separatorIndex === -1) {
        return accumulator
      }
      const key = part.slice(0, separatorIndex).trim()
      const value = part.slice(separatorIndex + 1).trim()
      accumulator[key] = value
      return accumulator
    }, {})
}

function formatBasisRule(rule) {
  if (!rule) {
    return ''
  }
  return BASIS_RULE_LABELS[rule] || rule.replace(/_/g, ' ')
}

function summarizeBasisRules(value) {
  if (!value) {
    return ''
  }
  const rules = value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => formatBasisRule(item))
  return rules.join('、')
}

function summarizeBasisHits(value) {
  if (!value) {
    return ''
  }
  const sections = []
  const matches = value.matchAll(/([a-z_]+)\[([^\]]*)\]/gi)
  for (const match of matches) {
    const scope = match[1]
    const content = match[2]?.trim()
    if (!content) {
      continue
    }
    sections.push(`${BASIS_HIT_SCOPE_LABELS[scope] || scope}命中：${content}`)
  }
  return sections.join('；')
}

function summarizeBasisComment(value) {
  if (!value) {
    return ''
  }
  const normalized = value.toLowerCase()
  if (normalized.includes('text too generic')) {
    return '文本描述过泛，需补充更具体的业务上下文。'
  }
  if (normalized.includes('generic boundary phrase needs richer business evidence')) {
    return '业务表述偏边界化，需补充更具体的经营证据。'
  }
  if (normalized.includes('no stable family rule matched current text context')) {
    return '当前文本上下文未命中稳定分类规则。'
  }
  if (normalized.includes('multiple family candidates remained too close')) {
    return '多个候选分类过于接近，暂时无法稳定区分。'
  }
  if (normalized.includes('leaf withheld for safety')) {
    return '为稳妥起见，当前暂不下钻到更细层级。'
  }
  if (normalized.includes('local manual override draft')) {
    return '当前为人工修订草案。'
  }
  return value
}

function mappingBasisSummaryItems(classification) {
  const parsed = parseMappingBasis(classification?.mapping_basis)
  const items = []
  const decision = BASIS_DECISION_LABELS[parsed.decision]
  const rules = summarizeBasisRules(parsed.rules)
  const hits = summarizeBasisHits(parsed.hits)
  const depth = BASIS_DEPTH_LABELS[parsed.depth]
  const comment = summarizeBasisComment(parsed.comment)

  if (decision) {
    items.push({ label: '当前处理结论', value: decision })
  }
  if (rules) {
    items.push({ label: '命中规则', value: rules })
  }
  if (hits) {
    items.push({ label: '主要依据', value: hits })
  }
  if (depth) {
    items.push({ label: '定位层级', value: depth })
  }
  if (comment) {
    items.push({ label: '补充说明', value: comment })
  }

  if (!items.length) {
    items.push({ label: '映射依据摘要', value: classification?.mapping_basis || '暂无映射依据' })
  }

  return items
}

function displayReviewReason(classification) {
  if (!classification?.review_reason) {
    return '当前规则结果已进入可展示状态。'
  }
  return reviewReasonLabel(classification.review_reason)
}

function isStatusClassificationSummary(segment) {
  const current = resolvedClassification(segment)
  if (!current) {
    return true
  }
  return !Boolean(
    current.industry_label ||
    current.level_1 ||
    current.level_2 ||
    current.level_3 ||
    current.level_4,
  )
}

function llmButtonType(segment) {
  return llmRecommended(segment) ? 'danger' : 'primary'
}

async function submitManualClassification() {
  if (!selectedSegment.value?.id) {
    return
  }
  if (!manualDraft.level_1 && !manualDraft.level_2 && !manualDraft.level_3 && !manualDraft.level_4) {
    ElMessage.warning('请至少填写一个产业层级后再应用人工征订。')
    return
  }
  if (!manualDraft.mapping_basis?.trim()) {
    ElMessage.warning('请填写人工修订依据后再应用人工征订。')
    return
  }

  manualSaving.value = true
  try {
    const response = await submitBusinessSegmentManualClassification(selectedSegment.value.id, {
      standard_system: 'GICS',
      level_1: manualDraft.level_1 || null,
      level_2: manualDraft.level_2 || null,
      level_3: manualDraft.level_3 || null,
      level_4: manualDraft.level_4 || null,
      is_primary: selectedSegment.value.segment_type === 'primary',
      mapping_basis: manualDraft.mapping_basis,
      review_status: 'confirmed',
      confidence: 1,
      mark_as_final: manualDraft.final_confirmed,
    })

    applyConfirmedClassificationLocally(response.confirmed_classification)
    await refreshSelectedSegmentClassifications(selectedSegment.value.id)
    const nextOverrides = { ...manualOverrides.value }
    delete nextOverrides[selectedSegment.value.id]
    manualOverrides.value = nextOverrides
    resetManualDraft(response.confirmed_classification)
    emit('refresh-industry-analysis')
    ElMessage.success('人工征订结果已更新。')
  } catch (error) {
    ElMessage.warning(error.message || '人工征订更新失败。')
  } finally {
    manualSaving.value = false
  }
}

function resetManualDraftInput() {
  if (!selectedSegment.value?.id) {
    return
  }
  const nextOverrides = { ...manualOverrides.value }
  delete nextOverrides[selectedSegment.value.id]
  manualOverrides.value = nextOverrides
  detailClassifications.value = selectedSegmentSnapshot.value?.classifications || []
  resetManualDraft(primaryClassification(selectedSegmentSnapshot.value))
  ElMessage.info('已重置当前人工征订输入。')
}

watch(
  () => detailDrawerVisible.value,
  (visible) => {
    if (!visible) {
      llmSuggestionPayload.value = null
      llmErrorMessage.value = ''
    }
  },
)
</script>

<template>
  <div class="industry-panel">
    <section v-if="false" class="industry-hero surface-card">
      <div class="industry-hero__copy">
        <span class="industry-hero__eyebrow">Industry Intelligence Layer</span>
        <h3>产业分析结果层</h3>
        <p v-if="false">
          展示业务线分类结果，并提供人工复核与模型建议入口。
        </p>
        <p>展示业务线分类结果，并提供人工复核与模型建议入口。</p>
      </div>
      <div class="industry-hero__actions">
        <el-button type="primary">
          进入产业分析工作台
          人工征订入口
        </el-button>
      </div>
    </section>

    <section class="industry-summary-grid">
      <div
        v-for="row in topSummaryRows"
        :key="row.key"
        class="industry-summary-row"
        :class="`industry-summary-row--${row.key}`"
      >
        <article
          v-for="metric in row.items"
          :key="metric.key"
          class="industry-summary-tile"
          :class="[
            `industry-summary-tile--${metric.key}`,
            { 'industry-summary-tile--emphasis': metric.emphasis },
          ]"
        >
          <span class="industry-summary-tile__label">{{ metric.label }}</span>
          <strong class="industry-summary-tile__value">{{ metric.value }}</strong>
          <p v-if="metric.description" class="industry-summary-tile__description">
            {{ metric.description }}
          </p>
          <div v-if="metric.tags?.length" class="industry-summary-tile__tags">
            <span
              v-for="tag in metric.tags"
              :key="tag.key"
              class="industry-summary-tile__tag"
            >
              {{ tag.value === undefined ? tag.label : `${tag.label} ${tag.value} 条` }}
            </span>
          </div>
        </article>
      </div>
    </section>

    <section v-if="false" class="industry-status-strip surface-card">
      <div v-if="false" class="industry-status-strip__head">
        <div>
          <h3>状态概览</h3>
          <p>帮助前端区分哪些业务线已足够稳定，哪些业务线适合优先进入人工征订或模型辅助流程。</p>
        </div>
        <el-tag
          :type="needsFurtherAnalysis(props.industryAnalysis) ? 'warning' : 'success'"
          effect="dark"
        >
          {{ needsFurtherAnalysis(localIndustryAnalysis) ? '存在待进一步分析样本' : '当前主链路可直接展示' }}
        </el-tag>
      </div>
      <div class="industry-status-strip__items">
        <div
          v-for="item in statusItems"
          :key="item.key"
          class="industry-status-pill"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </section>

    <section class="industry-main-grid">
      <article id="module-business-structure" class="industry-chart-card surface-card module-anchor">
        <div class="section-heading">
          <div>
            <h3>业务结构图</h3>
            <p>展示企业业务线的收入占比与利润占比结构。</p>
          </div>
        </div>
        <div class="industry-chart-pair">
          <div class="industry-chart-panel">
            <div class="industry-chart-panel__head">
              <h4>收入占比结构</h4>
            </div>
            <IndustryStructurePieChart
              :rows="revenueChartRows"
              metric-label="收入占比"
            />
          </div>

          <div class="industry-chart-panel">
            <div class="industry-chart-panel__head">
              <h4>利润占比结构</h4>
            </div>
            <IndustryStructurePieChart
              :rows="profitChartRows"
              metric-label="利润占比"
              empty-description="当前利润占比数据不足，暂不展示"
            />
          </div>
        </div>
      </article>

      <article id="module-industry-review" class="industry-review-card surface-card module-anchor">
        <div class="section-heading">
          <div>
            <h3>人工复核与修订</h3>
            <p>集中展示需要优先复核的业务线，便于结合规则结果、模型建议与人工判断完成修订。</p>
          </div>
        </div>

        <div class="industry-review-card__priority">
          <span>人工复核结果优先生效</span>
          <p>确认或修订后的分类结果会作为当前业务线的有效分类结论。</p>
        </div>

        <div class="industry-review-card__queue">
          <div>
            <strong>{{ flaggedSegments.length }}</strong>
            <span>条业务线需要优先复核</span>
          </div>
        </div>


        <div v-if="flaggedSegments.length" class="industry-review-card__list-wrap">
          <div class="industry-review-card__list-head">
            <div>
              <h4>待处理业务线队列</h4>
              <p>以下业务线建议优先复核，可点击“查看”进入详情页进一步判断。</p>
            </div>
          </div>

          <div class="industry-review-card__list">
            <div
              v-for="segment in flaggedSegments.slice(0, 5)"
              :key="segment.id"
              class="industry-review-chip"
            >
              <div class="industry-review-chip__main">
                <span>{{ segment.segment_alias || segment.segment_name }}</span>
                <small>{{ reviewReasonLabel(resolvedClassification(segment)?.review_reason) }}</small>
              </div>
              <div class="industry-review-chip__aside">
                <el-tag
                  size="small"
                  :type="reviewStatusTagType(resolvedClassification(segment)?.review_status)"
                  effect="plain"
                >
                  {{ reviewStatusLabel(resolvedClassification(segment)?.review_status) }}
                </el-tag>
                <el-button link type="primary" @click="openSegmentDetail(segment)">
                  查看
                </el-button>
              </div>
            </div>
          </div>
        </div>
        <el-empty
          v-else
          description="当前没有高优先级待处理业务线"
          :image-size="72"
        />

      </article>
    </section>

    <article id="module-business-segments" class="industry-table-card surface-card module-anchor">
      <div class="section-heading">
        <div>
          <h3>业务线分类主表</h3>
          <p>展示各业务线的占比、分类结果与当前状态，可点击“查看与分析”进入更深入的分析与处理。</p>
        </div>
      </div>

      <div class="industry-table-shell">
        <el-table
          v-loading="loading"
          :data="displaySegments"
          row-key="id"
          stripe
          border
          empty-text="暂无业务线数据"
        >
          <el-table-column label="业务线名称" min-width="220">
            <template #default="{ row }">
              <div class="industry-table-name">
                <strong
                  class="industry-table-text industry-table-text--name"
                  :title="row.segment_alias || row.segment_name"
                >
                  {{ row.segment_alias || row.segment_name }}
                </strong>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="原始披露名" min-width="220">
            <template #default="{ row }">
              <div class="industry-table-text" :title="row.segment_name">
                {{ row.segment_name || '暂无' }}
              </div>
            </template>
          </el-table-column>

          <el-table-column label="业务类型" width="96">
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

          <el-table-column label="利润占比" width="96">
            <template #default="{ row }">
              {{ formatFlexiblePercent(row.profit_ratio) }}
            </template>
          </el-table-column>

          <el-table-column label="报告期" width="132">
            <template #default="{ row }">
              <div class="industry-table-text industry-table-text--single" :title="row.reporting_period">
                {{ row.reporting_period || '暂无' }}
              </div>
            </template>
          </el-table-column>

          <el-table-column label="当前分类摘要" min-width="280">
            <template #default="{ row }">
              <el-tooltip placement="top-start" effect="light" :show-after="200">
                <template #content>
                  <div class="industry-summary-tooltip">
                    {{ currentClassificationSummary(row) }}
                  </div>
                </template>
                <div
                  v-if="!isStatusClassificationSummary(row)"
                  class="industry-table-text industry-table-text--summary"
                >
                  {{ currentClassificationSummary(row) }}
                </div>
                <span v-else class="industry-table-status">
                  {{ currentClassificationSummary(row) }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>

          <el-table-column label="Review Status" width="132">
            <template #default="{ row }">
              <el-tag
                :type="reviewStatusTagType(resolvedClassification(row)?.review_status)"
                effect="plain"
              >
                {{ reviewStatusLabel(resolvedClassification(row)?.review_status) }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="Confidence" width="118">
            <template #default="{ row }">
              {{ formatConfidence(resolvedClassification(row)?.confidence) }}
            </template>
          </el-table-column>

          <el-table-column label="查看与分析" width="120" align="center">
            <template #default="{ row }">
              <div class="industry-table-actions">
                <el-button link type="primary" @click="openSegmentDetail(row)">
                  查看与分析
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </article>

    <article v-if="qualityWarnings.length" class="industry-quality-card surface-card">
      <div class="section-heading">
        <div>
          <h3>质量提示</h3>
          <p>仅在存在 warning 或口径异常时展开，作为次级研究提示保留。</p>
        </div>
      </div>
      <div class="industry-quality-list">
        <el-alert
          v-for="warning in qualityWarnings"
          :key="warning"
          type="warning"
          :closable="false"
          show-icon
          :title="warning"
        />
      </div>
    </article>

    <el-drawer
      v-model="detailDrawerVisible"
      size="min(920px, 94vw)"
      :with-header="false"
      class="industry-detail-drawer"
    >
      <div v-if="selectedSegment" class="industry-drawer">
        <div class="industry-drawer__header">
          <div class="industry-drawer__header-copy">
            <span class="industry-drawer__eyebrow">业务线详情</span>
            <div class="industry-drawer__title-row">
              <h3>{{ selectedSegment.segment_alias || selectedSegment.segment_name }}</h3>
              <div class="industry-drawer__badges">
                <el-tag :type="segmentTypeTagType(selectedSegment.segment_type)" effect="plain">
                  {{ segmentTypeLabel(selectedSegment.segment_type) }}
                </el-tag>
                <el-tag
                  :type="reviewStatusTagType(selectedClassification?.review_status)"
                  effect="dark"
                >
                  {{ reviewStatusLabel(selectedClassification?.review_status) }}
                </el-tag>
              </div>
            </div>
            <p>{{ selectedSegment.segment_name }}</p>
          </div>
          <el-tooltip content="返回" placement="left">
            <el-button circle plain :icon="ArrowLeft" @click="detailDrawerVisible = false" />
          </el-tooltip>
        </div>

        <div class="industry-drawer__meta">
          <div>
            <span>报告期</span>
            <strong>{{ selectedSegment.reporting_period || '—' }}</strong>
          </div>
          <div>
            <span>收入占比</span>
            <strong>{{ formatFlexiblePercent(selectedSegment.revenue_ratio) }}</strong>
          </div>
          <div>
            <span>利润占比</span>
            <strong>{{ formatFlexiblePercent(selectedSegment.profit_ratio) }}</strong>
          </div>
          <div>
            <span>来源</span>
            <strong>{{ selectedSegment.source || '—' }}</strong>
          </div>
        </div>

        <el-skeleton v-if="detailLoading" animated :rows="8" />

        <template v-else>
          <section class="industry-drawer-section">
            <div class="section-heading">
              <div>
                <h3>当前正式结果</h3>
                <p>这里展示当前业务线的分类结果、结果来源与映射依据。</p>
              </div>
            </div>
            <div class="industry-drawer-card">
              <div class="industry-level-grid">
                <div>
                  <span>一级分类</span>
                  <strong>{{ selectedClassification?.level_1 || '—' }}</strong>
                </div>
                <div>
                  <span>二级分类</span>
                  <strong>{{ selectedClassification?.level_2 || '—' }}</strong>
                </div>
                <div>
                  <span>三级分类</span>
                  <strong>{{ selectedClassification?.level_3 || '—' }}</strong>
                </div>
                <div>
                  <span>四级分类</span>
                  <strong>{{ selectedClassification?.level_4 || '—' }}</strong>
                </div>
              </div>
              <div class="industry-result-grid">
                <div>
                  <span>业务线说明</span>
                  <strong>{{ selectedSegment.description || '暂无披露说明' }}</strong>
                </div>
                <div>
                  <span>结果来源</span>
                  <strong>{{ classifierTypeLabel(selectedClassification?.classifier_type) }}</strong>
                </div>
                <div>
                  <span>置信度</span>
                  <strong>{{ formatConfidence(selectedClassification?.confidence) }}</strong>
                </div>
                <div>
                  <span>当前原因</span>
                  <strong>{{ displayReviewReason(selectedClassification) }}</strong>
                </div>
              </div>
              <div class="industry-basis-card">
                <div class="industry-basis-card__head">
                  <div>
                    <span>映射依据摘要</span>
                    <p>展示当前分类结果的摘要依据，便于核对分类结论。</p>
                  </div>
                </div>
                <div class="industry-basis-list">
                  <div
                    v-for="item in mappingBasisSummaryItems(selectedClassification)"
                    :key="item.label"
                    class="industry-basis-item"
                  >
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                  </div>
                </div>
                <details v-if="selectedClassification?.mapping_basis" class="industry-basis-raw">
                  <summary>展开查看原始映射依据</summary>
                  <pre>{{ selectedClassification.mapping_basis }}</pre>
                </details>
              </div>
            </div>
          </section>

          <section class="industry-drawer-section">
            <div class="section-heading">
              <div>
                <h3>人工征订 / 人工修订</h3>
                <p>可在这里提交人工修订，更新当前业务线的分类结果。</p>
              </div>
            </div>
            <div class="industry-drawer-card industry-drawer-card--manual">
              <el-form label-position="top" class="industry-manual-form">
                <div class="industry-manual-form__grid">
                  <el-form-item label="一级分类">
                    <el-input v-model="manualDraft.level_1" placeholder="例如 Information Technology" />
                  </el-form-item>
                  <el-form-item label="二级分类">
                    <el-input v-model="manualDraft.level_2" placeholder="例如 Software & Services" />
                  </el-form-item>
                  <el-form-item label="三级分类">
                    <el-input v-model="manualDraft.level_3" placeholder="例如 Software" />
                  </el-form-item>
                  <el-form-item label="四级分类">
                    <el-input v-model="manualDraft.level_4" placeholder="例如 Application Software" />
                  </el-form-item>
                </div>
                <el-form-item label="人工修订依据">
                  <el-input
                    v-model="manualDraft.mapping_basis"
                    type="textarea"
                    :rows="4"
                    placeholder="请填写人工调整当前分类结果的依据，例如业务线主营属性、披露描述、研究判断等。"
                  />
                </el-form-item>
                <el-form-item>
                  <el-checkbox v-model="manualDraft.final_confirmed">
                    标记为最终采用结果
                  </el-checkbox>
                </el-form-item>
              </el-form>
              <div class="industry-manual-form__actions">
                <el-button type="primary" :loading="manualSaving" @click="submitManualClassification">
                  应用人工征订
                </el-button>
                <el-button plain @click="resetManualDraftInput">
                  重置人工输入
                </el-button>
              </div>
            </div>
          </section>

          <section class="industry-drawer-section">
            <div class="section-heading">
              <div>
                <h3>模型辅助分析</h3>
                <p>可结合模型建议补充判断依据，并在人工复核后完成当前业务线分类结果的确认。</p>
              </div>
            </div>
            <div class="industry-drawer-card">
              <div class="industry-llm-head">
                <div>
                  <strong>建议入口</strong>
                  <p v-if="llmRecommended(selectedSegment)">
                    当前状态适合优先触发模型辅助补判。
                  </p>
                  <p v-else>
                    当前业务线已具备基础规则结果，模型入口作为补充研究位保留。
                  </p>
                </div>
                <el-button
                  :type="llmRecommended(selectedSegment) ? 'danger' : 'primary'"
                  :loading="llmLoading"
                  @click="triggerLlmAnalysis()"
                >
                  LLM分析
                </el-button>
              </div>

              <div v-if="llmLoading" class="industry-llm-loading">
                <strong>模型分析中...</strong>
                <p>正在向 DeepSeek 请求当前业务线的分类建议，请稍等片刻。</p>
              </div>
              <el-alert
                v-else-if="llmErrorMessage"
                type="error"
                :closable="false"
                show-icon
                :title="llmErrorMessage"
              />
              <div v-else-if="llmSuggestionPayload" class="industry-llm-result">
                <div class="industry-llm-summary">
                  <div>
                    <span>建议分类</span>
                    <strong>{{ llmSuggestionLabel() }}</strong>
                  </div>
                  <div>
                    <span>结果来源</span>
                    <strong>{{ llmClassifierTypeLabel(llmSuggestionClassification()?.classifier_type) }}</strong>
                  </div>
                  <div>
                    <span>建议状态</span>
                    <strong>{{ reviewStatusLabel(llmSuggestionClassification()?.review_status) }}</strong>
                  </div>
                  <div>
                    <span>置信度</span>
                    <strong>{{ formatConfidence(llmSuggestionClassification()?.confidence) }}</strong>
                  </div>
                </div>

                <div class="industry-llm-levels">
                  <div>
                    <span>一级分类</span>
                    <strong>{{ formatLlmLevel(llmSuggestionClassification()?.level_1) }}</strong>
                  </div>
                  <div>
                    <span>二级分类</span>
                    <strong>{{ formatLlmLevel(llmSuggestionClassification()?.level_2) }}</strong>
                  </div>
                  <div>
                    <span>三级分类</span>
                    <strong>{{ formatLlmLevel(llmSuggestionClassification()?.level_3) }}</strong>
                  </div>
                  <div>
                    <span>四级分类</span>
                    <strong>{{ formatLlmLevel(llmSuggestionClassification()?.level_4) }}</strong>
                  </div>
                </div>

                <div class="industry-llm-notes">
                  <div>
                    <span>当前原因</span>
                    <strong>{{ llmReviewReasonLabel(llmSuggestionClassification()?.review_reason) }}</strong>
                  </div>
                  <div>
                    <span>调用状态</span>
                    <strong>{{ llmDisplayMessage() }}</strong>
                  </div>
                </div>

                <div class="industry-llm-basis">
                  <span>映射依据</span>
                  <p>{{ llmSuggestionClassification()?.mapping_basis || '暂无映射依据' }}</p>
                </div>

                <div class="industry-llm-context">
                  <span>模型参考上下文</span>
                  <p>{{ llmContextSummary() }}</p>
                </div>
                <el-alert
                  v-if="llmSuggestionAdopted"
                  type="success"
                  :closable="false"
                  show-icon
                  title="该模型建议已采用。"
                />
                <div class="industry-llm-actions">
                  <el-button
                    type="primary"
                    :loading="llmConfirming"
                    :disabled="llmSuggestionAdopted"
                    @click="confirmLlmSuggestion"
                  >
                    采用该建议
                  </el-button>
                </div>
                <p><strong>状态：</strong>{{ llmSuggestionPayload.status }}</p>
                <p><strong>消息：</strong>{{ llmSuggestionPayload.message }}</p>
                <p><strong>建议分类：</strong>{{ llmSuggestionLabel() }}</p>
                <p><strong>建议 level_1：</strong>{{ llmSuggestionClassification()?.level_1 || '暂无' }}</p>
                <p><strong>建议 level_2：</strong>{{ llmSuggestionClassification()?.level_2 || '暂无' }}</p>
                <p><strong>建议 level_3：</strong>{{ llmSuggestionClassification()?.level_3 || '暂无' }}</p>
                <p><strong>建议 level_4：</strong>{{ llmSuggestionClassification()?.level_4 || '暂无' }}</p>
                <p><strong>置信度：</strong>{{ formatConfidence(llmSuggestionClassification()?.confidence) }}</p>
                <p><strong>结果来源：</strong>{{ classifierTypeLabel(llmSuggestionClassification()?.classifier_type) }}</p>
                <p><strong>建议 review_status：</strong>{{ reviewStatusLabel(llmSuggestionClassification()?.review_status) }}</p>
                <p><strong>建议映射依据：</strong>{{ llmSuggestionClassification()?.mapping_basis || '暂无' }}</p>
                <p><strong>模型输入上下文：</strong>{{ llmSuggestionPayload.request_context?.company_text || llmSuggestionPayload.request_context?.company_description || '暂无公司上下文' }}</p>
              </div>
              <el-empty
                v-else
                description="尚未生成模型分析结果，可使用模型辅助补充判断。"
                :image-size="72"
              />
            </div>
          </section>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.industry-panel {
  display: grid;
  gap: 18px;
  min-width: 0;
}

.industry-panel > * {
  min-width: 0;
}

.module-anchor {
  scroll-margin-top: 16px;
}

.industry-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: flex-start;
  gap: 18px;
  padding: 20px;
  border-radius: 20px;
  border: 1px solid rgba(118, 82, 31, 0.14);
  background:
    radial-gradient(circle at top left, rgba(221, 198, 162, 0.22), transparent 28%),
    linear-gradient(140deg, rgba(252, 248, 240, 0.96), rgba(255, 255, 255, 0.92));
  box-shadow: 0 18px 38px rgba(55, 44, 22, 0.08);
  min-width: 0;
}

.industry-hero__copy {
  max-width: 700px;
  min-width: 0;
}

.industry-hero__eyebrow,
.industry-drawer__eyebrow {
  display: inline-flex;
  padding: 5px 11px;
  border-radius: 999px;
  border: 1px solid rgba(144, 116, 77, 0.18);
  background: rgba(255, 250, 242, 0.84);
  color: #8b6a3d;
  font-size: 11px;
  line-height: 1.2;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.industry-hero__copy h3 {
  margin: 10px 0 6px;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.32;
}

.industry-panel .section-heading h3 {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.36;
}

.industry-drawer-section h3,
.industry-hero__copy p,
.industry-status-strip__head p,
.industry-drawer-section p,
.industry-review-card__priority p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.68;
}

.industry-hero__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: flex-end;
  align-self: start;
}

.industry-summary-grid {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.industry-summary-row {
  display: grid;
  gap: 12px;
  align-items: stretch;
  min-width: 0;
}

.industry-summary-row--primary {
  grid-template-columns: minmax(0, 1.52fr) minmax(180px, 0.72fr);
}

.industry-summary-row--status {
  grid-template-columns: minmax(180px, 0.74fr) minmax(0, 1.5fr);
}

.industry-summary-row--focus {
  grid-template-columns: minmax(0, 1fr);
}

.industry-summary-tile {
  display: grid;
  gap: 10px;
  align-content: start;
  padding: 16px 18px;
  border-radius: 16px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(255, 255, 255, 0.82);
  min-width: 0;
}

.industry-summary-tile__label {
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.35;
}

.industry-summary-tile__value {
  color: var(--brand-ink);
  font-size: 16px;
  font-weight: 700;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.industry-summary-tile--segment-count .industry-summary-tile__value {
  font-size: 28px;
  line-height: 1.08;
}

.industry-summary-tile--report-period .industry-summary-tile__value {
  font-size: 18px;
}

.industry-summary-tile--company-info .industry-summary-tile__value,
.industry-summary-tile--primary-summary .industry-summary-tile__value,
.industry-summary-tile--pending-analysis .industry-summary-tile__value {
  font-size: 17px;
  line-height: 1.55;
}

.industry-summary-row--focus .industry-summary-tile {
  padding: 18px 20px;
}

.industry-summary-tile__description {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.industry-summary-tile__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.industry-summary-tile--primary-summary .industry-summary-tile__tags {
  margin-top: 2px;
}

.industry-summary-tile__tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(241, 246, 252, 0.96);
  color: #496179;
  font-size: 11px;
  line-height: 1.35;
}

.industry-summary-tile--company-info .industry-summary-tile__tag {
  background: rgba(244, 247, 253, 0.96);
  color: #48607f;
}

.industry-summary-tile--primary-summary .industry-summary-tile__tag {
  background: rgba(243, 250, 245, 0.96);
  color: #4d6d5b;
}

.industry-summary-tile--emphasis {
  background: linear-gradient(180deg, rgba(253, 248, 239, 0.95), rgba(255, 255, 255, 0.9));
  border-color: rgba(144, 116, 77, 0.18);
}

.industry-status-strip,
.industry-review-card,
.industry-table-card {
  padding: 18px;
  border-radius: 20px;
  min-width: 0;
  overflow: hidden;
}

.industry-chart-card {
  display: grid;
  gap: 22px;
  padding: 20px 18px 22px;
  border-radius: 20px;
  min-width: 0;
  overflow: hidden;
}

.industry-chart-card .section-heading {
  display: grid;
  gap: 10px;
}

.industry-chart-card .section-heading p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.68;
}

.industry-status-strip__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.industry-status-strip__head h3 {
  margin: 0;
  font-size: 18px;
  line-height: 1.36;
}

.industry-status-strip__items {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
  min-width: 0;
}

.industry-status-pill {
  display: grid;
  gap: 8px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(249, 251, 254, 0.84);
  min-width: 0;
}

.industry-status-pill span {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.35;
}

.industry-status-pill strong {
  color: var(--brand-ink);
  font-size: 19px;
  line-height: 1.2;
}

.industry-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.95fr);
  gap: 18px;
  align-items: start;
  min-width: 0;
}

.industry-review-card {
  display: grid;
  gap: 18px;
  background:
    linear-gradient(180deg, rgba(244, 247, 251, 0.96), rgba(255, 255, 255, 0.92));
  align-content: start;
}

.industry-chart-pair {
  display: grid;
  grid-template-columns: 1fr;
  gap: 26px;
  min-width: 0;
}

.industry-chart-panel {
  display: grid;
  gap: 14px;
  min-width: 0;
}

.industry-chart-panel__head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-inline: 2px;
}

.industry-chart-panel__head h4 {
  margin: 0;
  color: var(--brand-ink);
  font-size: 15px;
  font-weight: 700;
  line-height: 1.4;
}

.industry-review-card__priority {
  display: grid;
  gap: 8px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(48, 95, 131, 0.12);
  background: rgba(246, 250, 255, 0.9);
}

.industry-review-card__priority span,
.industry-drawer-card__stack strong {
  color: var(--brand-ink);
  font-weight: 700;
}

.industry-review-card__priority span {
  font-size: 14px;
  line-height: 1.4;
}

.industry-review-card__queue {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(255, 255, 255, 0.88);
}

.industry-review-card__queue strong {
  display: block;
  color: var(--brand-ink);
  font-size: 24px;
  line-height: 1.1;
}

.industry-review-card__queue span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.industry-review-card__list {
  display: grid;
  gap: 10px;
}

.industry-review-card__list-wrap {
  display: grid;
  gap: 10px;
}

.industry-review-card__list-head h4 {
  margin: 0 0 4px;
  color: var(--brand-ink);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.4;
}

.industry-review-card__list-head p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.55;
}

.industry-review-chip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 14px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.74);
  color: var(--brand-ink);
  min-width: 0;
  font-size: 13px;
  line-height: 1.45;
}

.industry-review-chip__main {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.industry-review-chip__main span {
  font-weight: 600;
}

.industry-review-chip__main small {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.industry-review-chip__aside {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.industry-quality-list {
  display: grid;
  gap: 10px;
}

.industry-quality-card {
  display: grid;
  gap: 14px;
  margin-top: 16px;
  padding: 16px 18px;
  border-radius: 18px;
  border: 1px solid rgba(201, 146, 34, 0.18);
  background: linear-gradient(180deg, rgba(255, 250, 240, 0.9), rgba(255, 255, 255, 0.94));
}

.industry-table-name {
  display: grid;
  gap: 0;
  min-width: 0;
}

.industry-table-name strong {
  color: var(--brand-ink);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.55;
}

.industry-table-text {
  display: -webkit-box;
  overflow: hidden;
  color: var(--text-primary);
  line-height: 1.6;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.industry-table-text--name {
  color: var(--brand-ink);
}

.industry-table-text--single {
  -webkit-line-clamp: 1;
}

.industry-table-text--summary {
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.industry-table-status {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 3px 8px;
  border: 1px solid rgba(120, 136, 160, 0.22);
  border-radius: 999px;
  background: rgba(120, 136, 160, 0.08);
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 1.45;
  white-space: nowrap;
}

.industry-summary-tooltip {
  max-width: 360px;
  white-space: normal;
  word-break: break-word;
  line-height: 1.55;
}

.industry-table-actions {
  display: flex;
  justify-content: center;
}

.industry-table-shell {
  width: 100%;
  min-width: 0;
  overflow: hidden;
}

.industry-table-shell :deep(.el-table) {
  width: 100%;
}

.industry-table-shell :deep(.el-table th) {
  font-size: 12px;
}

.industry-table-shell :deep(.el-table td) {
  vertical-align: top;
}

.industry-table-shell :deep(.el-table td),
.industry-table-shell :deep(.el-table .cell) {
  font-size: 13px;
  line-height: 1.6;
}

.industry-table-shell :deep(.el-table th > .cell),
.industry-table-shell :deep(.el-table td > .cell) {
  padding-top: 14px;
  padding-bottom: 14px;
}

.industry-table-shell :deep(.el-table th > .cell) {
  font-weight: 600;
  white-space: nowrap;
}

.industry-drawer {
  display: grid;
  gap: 18px;
  min-width: 0;
}

.industry-drawer__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.industry-drawer__header-copy {
  display: grid;
  gap: 10px;
}

.industry-drawer__title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.industry-drawer__header h3 {
  margin: 12px 0 8px;
  color: var(--brand-ink);
  font-size: 21px;
  font-weight: 700;
  line-height: 1.34;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.industry-drawer__header p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.industry-drawer__eyebrow {
  color: var(--text-secondary);
  font-size: 12px;
  letter-spacing: 0.08em;
}

.industry-drawer__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.industry-drawer__meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  min-width: 0;
}

.industry-drawer__meta > div,
.industry-level-grid > div {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(249, 251, 254, 0.78);
}

.industry-drawer__meta span,
.industry-level-grid span {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.35;
}

.industry-drawer__meta strong,
.industry-level-grid strong {
  color: var(--brand-ink);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.45;
}

.industry-drawer-section {
  display: grid;
  gap: 12px;
}

.industry-drawer-card {
  display: grid;
  gap: 14px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(255, 255, 255, 0.82);
  min-width: 0;
}

.industry-drawer-card--manual {
  background:
    linear-gradient(180deg, rgba(252, 248, 239, 0.84), rgba(255, 255, 255, 0.92));
  border-color: rgba(144, 116, 77, 0.18);
}

.industry-level-grid,
.industry-manual-form__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  min-width: 0;
}

.industry-result-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  min-width: 0;
}

.industry-drawer-card__stack {
  display: grid;
  gap: 10px;
}

.industry-result-grid > div {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(249, 251, 254, 0.82);
}

.industry-result-grid span {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.35;
}

.industry-result-grid strong {
  color: var(--brand-ink);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.industry-drawer-card__stack p,
.industry-llm-result p {
  margin: 0;
  color: #33465b;
  font-size: 13px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.industry-basis-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(77, 99, 124, 0.12);
  background: linear-gradient(180deg, rgba(247, 250, 255, 0.92), rgba(255, 255, 255, 0.96));
}

.industry-basis-card__head span {
  color: var(--brand-ink);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.45;
}

.industry-basis-card__head p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.55;
}

.industry-basis-list {
  display: grid;
  gap: 10px;
}

.industry-basis-item {
  display: grid;
  gap: 5px;
}

.industry-basis-item span {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.35;
}

.industry-basis-item strong {
  color: #33465b;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.industry-basis-raw {
  padding-top: 4px;
  border-top: 1px dashed rgba(77, 99, 124, 0.18);
}

.industry-basis-raw summary {
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.industry-basis-raw pre {
  margin: 10px 0 0;
  padding: 12px;
  overflow-x: auto;
  border-radius: 12px;
  background: rgba(18, 28, 45, 0.04);
  color: #40546a;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.industry-manual-form__actions,
.industry-llm-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.industry-llm-head p {
  margin-top: 6px;
}

.industry-llm-loading,
.industry-llm-basis,
.industry-llm-context {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(248, 251, 255, 0.86);
}

.industry-llm-loading strong,
.industry-llm-basis span,
.industry-llm-context span {
  color: var(--brand-ink);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.45;
}

.industry-llm-loading p,
.industry-llm-basis p,
.industry-llm-context p {
  margin: 0;
  color: #33465b;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.industry-llm-result {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(247, 250, 255, 0.9);
}

.industry-llm-result > p {
  display: none;
}

.industry-llm-actions {
  display: flex;
  justify-content: flex-end;
}

.industry-llm-summary,
.industry-llm-levels,
.industry-llm-notes {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.industry-llm-summary > div,
.industry-llm-levels > div,
.industry-llm-notes > div {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(255, 255, 255, 0.82);
}

.industry-llm-summary span,
.industry-llm-levels span,
.industry-llm-notes span {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.35;
}

.industry-llm-summary strong,
.industry-llm-levels strong,
.industry-llm-notes strong {
  color: var(--brand-ink);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.65;
  overflow-wrap: anywhere;
}


@media (max-width: 1200px) {
  .industry-summary-row--primary,
  .industry-summary-row--status {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .industry-status-strip__items,
  .industry-drawer__meta {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .industry-main-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .industry-hero,
  .industry-status-strip__head,
  .industry-manual-form__actions,
  .industry-llm-head,
  .industry-drawer__header {
    display: grid;
  }

  .industry-summary-grid,
  .industry-summary-row,
  .industry-status-strip__items,
  .industry-level-grid,
  .industry-result-grid,
  .industry-llm-summary,
  .industry-llm-levels,
  .industry-llm-notes,
  .industry-manual-form__grid,
  .industry-drawer__meta {
    grid-template-columns: 1fr;
  }

  .industry-table-shell :deep(.el-table) {
    min-width: 960px;
  }
}
</style>
