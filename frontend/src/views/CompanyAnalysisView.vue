<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { fetchCompanyAnalysisSummary, fetchCompanyControlChain, fetchCompanyIndustryAnalysis } from '@/api/analysis'
import { fetchCompanyRelationshipGraph } from '@/api/company'
import BusinessSegmentsTable from '@/components/BusinessSegmentsTable.vue'
import CompanyOverviewCard from '@/components/CompanyOverviewCard.vue'
import ControlRelationsTable from '@/components/ControlRelationsTable.vue'
import ControlSummaryCard from '@/components/ControlSummaryCard.vue'
import IndustrySummaryCard from '@/components/IndustrySummaryCard.vue'
import SearchBar from '@/components/SearchBar.vue'

const route = useRoute()
const router = useRouter()

const companyIdInput = ref('')
const loading = ref(false)
const hasSearched = ref(false)
const pageError = ref('')
const resolvedCompanyId = ref('')
const summaryData = ref(null)
const relationshipGraph = ref(null)
const sectionErrors = reactive({
  graph: '',
})

function normalizeCompanyId(value) {
  const normalized = String(value ?? '').trim()
  if (!normalized) {
    throw new Error('请输入 company_id 后再查询。')
  }
  if (!/^\d+$/.test(normalized)) {
    throw new Error('company_id 需为正整数。')
  }
  return normalized
}

function buildEmptyGraphState(companyId, message = '后续接入控制链图展示') {
  return {
    company_id: companyId ? Number(companyId) : null,
    message,
    target_company: null,
    target_entity_id: null,
    node_count: 0,
    edge_count: 0,
    nodes: [],
    edges: [],
  }
}

async function loadCompanyData(companyId) {
  loading.value = true
  hasSearched.value = true
  pageError.value = ''
  sectionErrors.graph = ''

  try {
    let summary = await fetchCompanyAnalysisSummary(companyId)

    if (!Array.isArray(summary?.control_analysis?.control_relationships)) {
      const controlChain = await fetchCompanyControlChain(companyId).catch(() => null)
      if (controlChain) {
        summary = {
          ...summary,
          control_analysis: {
            ...summary.control_analysis,
            controller_count:
              controlChain.controller_count ?? summary.control_analysis?.controller_count ?? 0,
            control_relationships: controlChain.control_relationships ?? [],
          },
        }
      }
    }

    if (!Array.isArray(summary?.industry_analysis?.segments)) {
      const industryAnalysis = await fetchCompanyIndustryAnalysis(companyId).catch(() => null)
      if (industryAnalysis) {
        summary = {
          ...summary,
          industry_analysis: industryAnalysis,
        }
      }
    }

    summaryData.value = summary
    resolvedCompanyId.value = companyId

    try {
      relationshipGraph.value = await fetchCompanyRelationshipGraph(companyId)
    } catch (error) {
      sectionErrors.graph = error.message
      relationshipGraph.value = buildEmptyGraphState(companyId, '关系图数据暂不可用。')
    }
  } catch (error) {
    pageError.value = error.message
    if (!summaryData.value || resolvedCompanyId.value !== companyId) {
      summaryData.value = null
      relationshipGraph.value = buildEmptyGraphState(companyId, '未获取到关系图数据。')
    }
  } finally {
    loading.value = false
  }
}

async function handleSearch() {
  try {
    const normalizedCompanyId = normalizeCompanyId(companyIdInput.value)
    if (route.query.companyId === normalizedCompanyId) {
      await loadCompanyData(normalizedCompanyId)
      return
    }
    await router.replace({
      name: 'company-analysis',
      query: { companyId: normalizedCompanyId },
    })
  } catch (error) {
    pageError.value = error.message
    hasSearched.value = true
    ElMessage.warning(error.message)
  }
}

watch(
  () => route.query.companyId,
  async (companyIdFromRoute) => {
    const rawValue = typeof companyIdFromRoute === 'string' ? companyIdFromRoute : ''
    companyIdInput.value = rawValue

    if (!rawValue) {
      hasSearched.value = false
      pageError.value = ''
      return
    }

    if (!/^\d+$/.test(rawValue.trim())) {
      hasSearched.value = true
      pageError.value = 'company_id 需为正整数。'
      return
    }

    await loadCompanyData(rawValue.trim())
  },
  { immediate: true },
)

const company = computed(() => summaryData.value?.company || null)
const controlAnalysis = computed(() => summaryData.value?.control_analysis || {})
const countryAttribution = computed(() => summaryData.value?.country_attribution || {})
const industryAnalysis = computed(() => summaryData.value?.industry_analysis || {})
const controlRelationships = computed(
  () => summaryData.value?.control_analysis?.control_relationships || [],
)
const businessSegments = computed(
  () => summaryData.value?.industry_analysis?.segments || [],
)

const currentSummaryNote = computed(() => {
  if (!company.value) {
    return '请输入 company_id 后查询企业综合分析结果。'
  }

  return `当前展示企业：${company.value.name}（company_id: ${company.value.id}）`
})
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div class="page-kicker">毕业设计演示版 · 企业综合分析</div>
      <h1 class="page-title">企业综合分析展示页</h1>
      <p class="page-subtitle">
        以现有后端接口为主入口，聚合展示企业基础信息、控制链与国别归属、业务结构与产业标注，以及底部明细表格。
      </p>
    </header>

    <SearchBar v-model="companyIdInput" :loading="loading" @search="handleSearch" />

    <el-alert
      v-if="pageError"
      class="status-banner"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
    />

    <el-card v-if="!hasSearched && !loading" class="helper-empty" shadow="never">
      <el-empty description="请输入 company_id 后查询企业综合分析结果" :image-size="96">
        <template #description>
          <div class="table-text table-text--muted">
            可直接使用上方推荐演示 ID，例如 128、240、9717。
          </div>
        </template>
      </el-empty>
    </el-card>

    <template v-else-if="summaryData">
      <div v-loading="loading">
        <el-alert
          class="status-banner"
          type="info"
          show-icon
          :closable="false"
          :title="currentSummaryNote"
        />

        <CompanyOverviewCard
          :company="company"
          :control-analysis="controlAnalysis"
          :country-attribution="countryAttribution"
          :industry-analysis="industryAnalysis"
        />

        <div class="analysis-report">
          <ControlSummaryCard
            :company="company"
            :control-analysis="controlAnalysis"
            :country-attribution="countryAttribution"
            :relationship-graph="relationshipGraph || buildEmptyGraphState(resolvedCompanyId)"
            :graph-error="sectionErrors.graph"
          />

          <ControlRelationsTable
            :relationships="controlRelationships"
            :loading="loading"
            :control-analysis="controlAnalysis"
            :country-attribution="countryAttribution"
            :company="company"
          />

          <IndustrySummaryCard :industry-analysis="industryAnalysis" />

          <BusinessSegmentsTable :segments="businessSegments" :loading="loading" />
        </div>
      </div>
    </template>

    <el-card v-else class="helper-empty" shadow="never">
      <el-empty description="未获取到企业分析结果" :image-size="96">
        <template #description>
          <div class="table-text table-text--muted">
            请检查 company_id 是否有效，以及后端服务是否已启动。
          </div>
        </template>
      </el-empty>
    </el-card>
  </div>
</template>
