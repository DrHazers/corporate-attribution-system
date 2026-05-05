<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  fetchCompanyAnalysisSummary,
  fetchCompanyControlChain,
  fetchCompanyIndustryAnalysis,
  fetchShareholderEntities,
  importOwnershipFacts,
  restoreAutomaticControlResult,
  submitManualControlOverride,
} from '@/api/analysis'
import { fetchCompanyRelationshipGraph, searchCompanies } from '@/api/company'
import CompanyOverviewCard from '@/components/CompanyOverviewCard.vue'
import ControlRelationsTable from '@/components/ControlRelationsTable.vue'
import ControlStructureDiagram from '@/components/ControlStructureDiagram.vue'
import ControlSummaryCard from '@/components/ControlSummaryCard.vue'
import FloatingModuleNav from '@/components/FloatingModuleNav.vue'
import IndustryAnalysisPanel from '@/components/IndustryAnalysisPanel.vue'
import IndustryWorkbenchDrawer from '@/components/IndustryWorkbenchDrawer.vue'
import SearchBar from '@/components/SearchBar.vue'
import {
  buildManualPathPayloads as buildManualPathPayloadRecords,
  deriveManualPathDisplay,
  manualPathIntermediateNames,
  middleNamesFromLegacyPathText,
  middleNamesFromManualPathRecord,
  pathRatioFromManualPathRecord,
} from '@/utils/manualPathBuilder'

const route = useRoute()
const router = useRouter()

const companyIdInput = ref('')
const companySearchResults = ref([])
const companySearchLoading = ref(false)
const companySearchAttempted = ref(false)
const companySearchEmptyMessage = ref('')
const loading = ref(false)
const hasSearched = ref(false)
const pageError = ref('')
const resolvedCompanyId = ref('')
const summaryData = ref(null)
const relationshipGraph = ref(null)
const manualPanelExpanded = ref(false)
const industryWorkbenchVisible = ref(false)
const manualSaving = ref(false)
const ownershipImportVisible = ref(false)
const ownershipImportSubmitting = ref(false)
const ownershipImportFileList = ref([])
const ownershipImportResult = ref(null)
const dataImportActiveTab = ref('ownership')
const ownershipImportExampleCollapse = ref([])
const shareholderEntityOptions = ref([])
const shareholderEntityLoading = ref(false)
let manualPathKeySeed = 0
let manualNodeKeySeed = 0

const floatingModuleNavTopItem = { label: '回到顶部', targetId: 'module-top' }
const floatingModuleNavGroups = [
  {
    title: '基础信息',
    items: [
      { label: '企业搜索', targetId: 'module-company-search' },
      { label: '公司总览', targetId: 'module-company-overview' },
    ],
  },
  {
    title: '控股结构',
    items: [
      { label: '控股结构分析', targetId: 'module-control-analysis' },
      { label: '控制链与国别归属', targetId: 'module-control-summary' },
      { label: '控制结构图', targetId: 'module-control-structure' },
      { label: '控制结论明细', targetId: 'module-control-details' },
      { label: '人工复核', targetId: 'module-manual-review' },
    ],
  },
  {
    title: '产业分析',
    items: [
      { label: '产业分析', targetId: 'module-industry-analysis' },
      { label: '业务结构图', targetId: 'module-business-structure' },
      { label: '业务线明细', targetId: 'module-business-segments' },
    ],
  },
]

const SUBJECT_MODE_EXISTING_ENTITY = 'existing_entity'
const SUBJECT_MODE_NEW_ENTITY = 'new_entity'
const SUBJECT_MODE_NAME_SNAPSHOT = 'name_snapshot'

function createManualPathNode(name = '') {
  manualNodeKeySeed += 1
  return {
    key: `manual-node-${manualNodeKeySeed}`,
    name,
  }
}

function createManualPathRow(intermediateNames = [], pathRatio = '') {
  manualPathKeySeed += 1
  return {
    key: `manual-path-${manualPathKeySeed}`,
    intermediate_nodes: intermediateNames.map((name) => createManualPathNode(name)),
    path_ratio: pathRatio,
  }
}

const manualForm = reactive({
  actual_controller_subject_mode: SUBJECT_MODE_EXISTING_ENTITY,
  actual_controller_entity_id: '',
  actual_controller_name: '',
  new_actual_controller_name: '',
  new_actual_controller_type: 'other',
  new_actual_controller_country: '',
  new_actual_controller_notes: '',
  actual_control_country: '',
  manual_control_ratio: '',
  manual_control_strength_label: '',
  manual_control_path: '',
  manual_paths: [createManualPathRow()],
  manual_control_type: '',
  manual_decision_reason: '',
  manual_path_count: '',
  manual_path_depth: '',
  reason: '',
  evidence: '',
})
const ownershipImportForm = reactive({
  mode: 'validate',
  conflictStrategy: 'fail',
  analysisStrategy: 'missing_only',
})
const sectionErrors = reactive({
  graph: '',
})

function normalizeCompanyId(value) {
  const normalized = String(value ?? '').trim()
  if (!normalized) {
    throw new Error('请选择需要展示的企业。')
  }
  if (!/^\d+$/.test(normalized)) {
    throw new Error('企业 ID 格式无效。')
  }
  return normalized
}

function isSlashIdQuery(value) {
  return /^\/\d+$/.test(String(value ?? '').trim())
}

function normalizeSearchQuery(value) {
  return String(value ?? '').trim()
}

function buildEmptyGraphState(companyId, message = '暂无控制结构图数据。') {
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

async function runTimedStep(label, task) {
  console.time(label)
  try {
    return await task()
  } finally {
    console.timeEnd(label)
  }
}

async function loadCompanyData(companyId) {
  const loadLabel = `[company-analysis] load:${companyId}`
  loading.value = true
  hasSearched.value = true
  pageError.value = ''
  sectionErrors.graph = ''

  try {
    console.time(loadLabel)
    console.info('[company-analysis] start load', { companyId })

    let summary = await runTimedStep(
      `${loadLabel}:summary`,
      () => fetchCompanyAnalysisSummary(companyId),
    )

    if (!Array.isArray(summary?.control_analysis?.control_relationships)) {
      const controlChain = await runTimedStep(
        `${loadLabel}:control-chain-fallback`,
        () => fetchCompanyControlChain(companyId).catch(() => null),
      )
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
      const industryAnalysis = await runTimedStep(
        `${loadLabel}:industry-fallback`,
        () => fetchCompanyIndustryAnalysis(companyId).catch(() => null),
      )
      if (industryAnalysis) {
        summary = {
          ...summary,
          industry_analysis: industryAnalysis,
        }
      }
    }

    summaryData.value = summary
    resolvedCompanyId.value = companyId
    if (!companyIdInput.value || isSlashIdQuery(companyIdInput.value) || /^\d+$/.test(companyIdInput.value.trim())) {
      companyIdInput.value = summary?.company?.name || companyIdInput.value
    }

    try {
      relationshipGraph.value = await runTimedStep(
        `${loadLabel}:relationship-graph`,
        () => fetchCompanyRelationshipGraph(companyId),
      )
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
    console.timeEnd(loadLabel)
    loading.value = false
  }
}

async function refreshIndustryAnalysisData(optionsOrCompanyId = null) {
  const options =
    optionsOrCompanyId && typeof optionsOrCompanyId === 'object'
      ? optionsOrCompanyId
      : {}
  const companyId =
    options.companyId ||
    (optionsOrCompanyId && typeof optionsOrCompanyId !== 'object' ? optionsOrCompanyId : null) ||
    company.value?.id ||
    resolvedCompanyId.value
  if (!companyId || !summaryData.value) {
    return
  }

  try {
    const reportingPeriod =
      options.reportingPeriod ?? summaryData.value?.industry_analysis?.selected_reporting_period
    const params = {
      include_history: options.includeHistory ?? true,
    }
    if (reportingPeriod) {
      params.reporting_period = reportingPeriod
    }
    const nextIndustryAnalysis = await fetchCompanyIndustryAnalysis(companyId, params)
    summaryData.value = {
      ...summaryData.value,
      industry_analysis: nextIndustryAnalysis,
    }
  } catch (error) {
    ElMessage.warning(error.message || '产业分析结果刷新失败。')
    throw error
  }
}

async function handleSearch(rawQuery = companyIdInput.value) {
  const query = normalizeSearchQuery(rawQuery)
  if (!query) {
    companySearchResults.value = []
    companySearchAttempted.value = true
    companySearchEmptyMessage.value = '请输入公司名称、股票代码，或使用 /ID 精确查询。'
    ElMessage.warning(companySearchEmptyMessage.value)
    return
  }

  companySearchLoading.value = true
  companySearchAttempted.value = true
  companySearchEmptyMessage.value = ''
  try {
    const results = await searchCompanies(query, { limit: 10 })
    companySearchResults.value = results
    if (!results.length) {
      companySearchEmptyMessage.value = isSlashIdQuery(query)
        ? '未找到该 ID 对应的企业。'
        : '未找到匹配企业，请尝试更换关键词。'
    }
  } catch (error) {
    companySearchResults.value = []
    companySearchEmptyMessage.value = error.message || '企业搜索失败，请稍后重试。'
    ElMessage.warning(error.message)
  } finally {
    companySearchLoading.value = false
  }
}

async function handleSelectCompany(companyOption) {
  const normalizedCompanyId = normalizeCompanyId(companyOption?.id)
  companyIdInput.value = companyOption?.name || `/${normalizedCompanyId}`
  companySearchResults.value = []
  companySearchAttempted.value = false
  companySearchEmptyMessage.value = ''

  if (route.query.companyId === normalizedCompanyId) {
    await loadCompanyData(normalizedCompanyId)
    return
  }

  await router.replace({
    name: 'company-analysis',
    query: { companyId: normalizedCompanyId },
  })
}

watch(
  () => route.query.companyId,
  async (companyIdFromRoute) => {
    const rawValue = typeof companyIdFromRoute === 'string' ? companyIdFromRoute : ''

    if (!rawValue) {
      hasSearched.value = false
      pageError.value = ''
      return
    }

    if (!/^\d+$/.test(rawValue.trim())) {
      hasSearched.value = true
      pageError.value = '企业 ID 格式无效。'
      return
    }

    const normalizedCompanyId = rawValue.trim()
    if (normalizedCompanyId !== resolvedCompanyId.value) {
      manualPanelExpanded.value = false
      industryWorkbenchVisible.value = false
    }
    await loadCompanyData(normalizedCompanyId)
  },
  { immediate: true },
)

watch(
  () => manualPanelExpanded.value,
  (expanded) => {
    if (expanded && !shareholderEntityOptions.value.length) {
      searchShareholderEntityOptions()
    }
  },
)

const company = computed(() => summaryData.value?.company || null)
const controlAnalysis = computed(() => summaryData.value?.control_analysis || {})
const countryAttribution = computed(() => summaryData.value?.country_attribution || {})
const industryAnalysis = computed(() => summaryData.value?.industry_analysis || {})
const controlRelationships = computed(
  () => summaryData.value?.control_analysis?.control_relationships || [],
)
const currentSummaryNote = computed(() => {
  if (!company.value) {
    return '请选择企业后查看综合分析结果。'
  }

  return `当前展示：${company.value.name}（ID：${company.value.id}）`
})

function openIndustryWorkbench() {
  industryWorkbenchVisible.value = true
}

function openOwnershipImportDialog() {
  dataImportActiveTab.value = 'ownership'
  ownershipImportVisible.value = true
}

function handleOwnershipImportFileChange(file, fileList) {
  ownershipImportFileList.value = fileList.slice(-1)
  ownershipImportResult.value = null
}

function clearOwnershipImportFile() {
  ownershipImportFileList.value = []
}

function analysisStatusLabel(status) {
  const labels = {
    reused: '已有结果',
    generated: '已生成',
    missing_facts: '缺少事实',
    failed: '计算失败',
  }
  return labels[status] || status || '未知'
}

watch(
  () => ownershipImportForm.mode,
  (mode) => {
    if (mode === 'commit_and_analyze' && ownershipImportForm.conflictStrategy === 'fail') {
      ownershipImportForm.conflictStrategy = 'skip'
    }
  },
)

async function handleOwnershipImport() {
  const uploadFile = ownershipImportFileList.value[0]?.raw
  if (!uploadFile) {
    ElMessage.warning('请选择需要导入的 CSV 或 ZIP 文件。')
    return
  }

  if (ownershipImportForm.mode === 'commit_and_analyze' && ownershipImportForm.conflictStrategy === 'fail') {
    ownershipImportForm.conflictStrategy = 'skip'
  }

  ownershipImportSubmitting.value = true
  try {
    const requestMode = ownershipImportForm.mode
    const requestConflictStrategy = ownershipImportForm.conflictStrategy
    const result = await importOwnershipFacts({
      file: uploadFile,
      mode: requestMode,
      conflictStrategy: requestConflictStrategy,
      analysisStrategy: ownershipImportForm.analysisStrategy,
    })
    ownershipImportResult.value = result
    const warningCount = Array.isArray(result?.warnings) ? result.warnings.length : 0
    const failedCompanyIds = (result?.analysis?.failed_company_ids || []).map((id) => String(id))
    const missingFactCompanyIds = (result?.analysis?.missing_fact_company_ids || []).map((id) => String(id))
    if (!result?.success) {
      ElMessage.warning('导入处理完成，但存在错误。')
    } else if (failedCompanyIds.length || warningCount) {
      ElMessage.warning('导入完成，但存在需要关注的警告。')
    } else {
      ElMessage.success(requestMode === 'validate' ? '校验完成，未写入数据库。' : '导入完成。')
    }

    const currentCompanyId = String(resolvedCompanyId.value || '')
    if (currentCompanyId && missingFactCompanyIds.includes(currentCompanyId)) {
      ElMessage.warning('已导入数据，但该公司仍缺少可用于控制分析的有效关系事实。')
    }
    if (currentCompanyId && failedCompanyIds.includes(currentCompanyId)) {
      ElMessage.warning('导入成功，但控制分析生成失败，请查看导入结果中的警告信息。')
    }

    const reloadCompanyIds = [
      ...(result?.analysis?.generated_company_ids || []),
      ...(result?.analysis?.reused_company_ids || []),
    ].map((id) => String(id))
    if (
      requestMode === 'commit_and_analyze' &&
      result?.success &&
      currentCompanyId &&
      reloadCompanyIds.includes(currentCompanyId)
    ) {
      await loadCompanyData(resolvedCompanyId.value)
    }
  } catch (error) {
    ElMessage.error(error.message || '控制关系数据导入失败。')
  } finally {
    ownershipImportSubmitting.value = false
  }
}

const manualOverride = computed(
  () =>
    summaryData.value?.manual_override ||
    summaryData.value?.control_analysis?.manual_override ||
    summaryData.value?.country_attribution?.manual_override ||
    null,
)
const manualEffective = computed(
  () =>
    Boolean(summaryData.value?.control_analysis?.is_manual_effective) ||
    Boolean(summaryData.value?.country_attribution?.is_manual_effective),
)
const manualSnapshotOnlyActive = computed(() => {
  const override = manualOverride.value
  return Boolean(
    override?.actual_controller_subject_mode === SUBJECT_MODE_NAME_SNAPSHOT &&
      override?.actual_controller_name &&
      !override?.actual_controller_entity_id,
  )
})
const currentResultSourceLabel = computed(() => {
  const source = summaryData.value?.control_analysis?.result_source || summaryData.value?.country_attribution?.result_source
  if (source === 'manual_confirmed') {
    return '人工确认自动结果'
  }
  if (source === 'manual_judgment') {
    return '人工判定生效'
  }
  if (source === 'manual_override') {
    return '人工征订生效'
  }
  return '自动分析结果'
})

const manualSubjectMode = computed(() => manualForm.actual_controller_subject_mode)
const isExistingEntityMode = computed(() => manualSubjectMode.value === SUBJECT_MODE_EXISTING_ENTITY)
const isNewEntityMode = computed(() => manualSubjectMode.value === SUBJECT_MODE_NEW_ENTITY)
const isNameSnapshotMode = computed(() => manualSubjectMode.value === SUBJECT_MODE_NAME_SNAPSHOT)

const manualControllerEntityId = computed(() => {
  const rawValue = String(manualForm.actual_controller_entity_id ?? '').trim()
  return /^\d+$/.test(rawValue) ? Number(rawValue) : null
})

const manualPathControllerEntityId = computed(() => {
  if (isExistingEntityMode.value || isNewEntityMode.value) {
    return manualControllerEntityId.value
  }
  return null
})

const manualPathControllerName = computed(() => {
  if (isNewEntityMode.value) {
    return String(manualForm.new_actual_controller_name ?? '').trim()
  }
  if (isNameSnapshotMode.value) {
    return ''
  }
  return String(manualForm.actual_controller_name ?? '').trim()
})

const manualControllerLabel = computed(() => {
  const name = manualPathControllerName.value
  if (name) {
    return name
  }
  if (manualPathControllerEntityId.value !== null) {
    return `主体 ${manualPathControllerEntityId.value}`
  }
  if (isNameSnapshotMode.value) {
    return '仅名称快照，不生成正式路径起点'
  }
  return '待填写实际控制人'
})

const manualTargetCompanyName = computed(() => company.value?.name || '当前目标公司')

const manualPathDisplay = computed(() =>
  deriveManualPathDisplay({
    paths: manualForm.manual_paths,
    controllerEntityId: manualPathControllerEntityId.value,
    controllerName: manualPathControllerName.value,
    allowNameOnlyStart: isNewEntityMode.value,
    targetCompanyName: manualTargetCompanyName.value,
  }),
)

const manualHasControllerForPaths = computed(() => manualPathDisplay.value.hasController)
const manualCanEditPaths = computed(() => manualHasControllerForPaths.value)
const manualPathBuilderBlockedTitle = computed(() => {
  if (isNameSnapshotMode.value) {
    return '仅名称快照未绑定实体库，不能作为正式控制路径起点。若需构建正式控制路径，请先选择现有主体或新建主体。'
  }
  if (isExistingEntityMode.value) {
    return '请选择已有主体 entity_id 后，路径起点才会同步为正式实体。'
  }
  return '填写新建主体名称后，保存时会先创建主体并绑定为正式路径起点。'
})

const manualGeneratedPathTexts = computed(() => manualPathDisplay.value.pathTexts)

const manualGeneratedPathSummary = computed(() => manualPathDisplay.value.summary)

const manualGeneratedPathCount = computed(() => manualPathDisplay.value.pathCount)

const manualGeneratedPathDepth = computed(() => manualPathDisplay.value.pathDepth)

function toggleManualPanel() {
  manualPanelExpanded.value = !manualPanelExpanded.value
}

function optionalText(value) {
  return String(value ?? '').trim() || '暂无'
}

function entityOptionLabel(entity) {
  const typeLabel = entity?.entity_type ? ` / ${entity.entity_type}` : ''
  const countryLabel = entity?.country ? ` / ${entity.country}` : ''
  return `${entity?.entity_name || '未命名主体'}（ID ${entity?.id}${typeLabel}${countryLabel}）`
}

async function searchShareholderEntityOptions(query = '') {
  shareholderEntityLoading.value = true
  try {
    shareholderEntityOptions.value = await fetchShareholderEntities({
      q: String(query ?? '').trim() || undefined,
      limit: 30,
    })
  } catch (error) {
    ElMessage.warning(error.message || '主体搜索暂不可用。')
  } finally {
    shareholderEntityLoading.value = false
  }
}

function syncSelectedExistingEntity(entityId) {
  const selected = shareholderEntityOptions.value.find(
    (entity) => String(entity.id) === String(entityId),
  )
  if (!selected) {
    return
  }
  manualForm.actual_controller_name = selected.entity_name || ''
  if (!manualForm.actual_control_country && selected.country) {
    manualForm.actual_control_country = selected.country
  }
}

function ensureManualPathRows() {
  if (!manualForm.manual_paths.length) {
    manualForm.manual_paths.push(createManualPathRow())
  }
}

function addManualPath() {
  manualForm.manual_paths.push(createManualPathRow())
}

function removeManualPath(pathIndex) {
  if (manualForm.manual_paths.length <= 1) {
    return
  }
  manualForm.manual_paths.splice(pathIndex, 1)
}

function addManualIntermediateNode(path) {
  path.intermediate_nodes.push(createManualPathNode())
}

function removeManualIntermediateNode(path, nodeIndex) {
  path.intermediate_nodes.splice(nodeIndex, 1)
}

function resetManualPaths(pathRows = [createManualPathRow()]) {
  manualForm.manual_paths.splice(0, manualForm.manual_paths.length, ...pathRows)
  ensureManualPathRows()
}

watch(
  () => manualForm.actual_controller_subject_mode,
  (mode) => {
    if (mode === SUBJECT_MODE_NAME_SNAPSHOT) {
      resetManualPaths([createManualPathRow()])
      return
    }
    if (mode === SUBJECT_MODE_EXISTING_ENTITY && !shareholderEntityOptions.value.length) {
      searchShareholderEntityOptions()
    }
  },
)

watch(
  () => manualForm.actual_controller_entity_id,
  (entityId) => {
    if (isExistingEntityMode.value || isNewEntityMode.value) {
      syncSelectedExistingEntity(entityId)
    }
  },
)

function pathRowsFromManualRecords(paths) {
  if (!Array.isArray(paths) || !paths.length) {
    return []
  }
  return paths.map((path) => {
    return createManualPathRow(
      middleNamesFromManualPathRecord(path),
      pathRatioFromManualPathRecord(path),
    )
  })
}

function pathRowsFromLegacyPathText(value) {
  const middleNames = middleNamesFromLegacyPathText(value)
  return [createManualPathRow(middleNames)]
}

const manualFormSeedKey = ref('')

function populateManualFormFromOverride(override) {
  const snapshot = override?.manual_result_snapshot || {}
  const rawMode = override?.actual_controller_subject_mode ||
    snapshot?.actual_controller_subject_mode ||
    (override?.actual_controller_entity_id
      ? SUBJECT_MODE_EXISTING_ENTITY
      : override?.actual_controller_name
        ? SUBJECT_MODE_NAME_SNAPSHOT
        : SUBJECT_MODE_EXISTING_ENTITY)
  const inferredMode = override?.actual_controller_entity_id
    ? SUBJECT_MODE_EXISTING_ENTITY
    : rawMode

  manualForm.actual_controller_subject_mode = inferredMode
  manualForm.actual_controller_entity_id = override?.actual_controller_entity_id
    ? String(override.actual_controller_entity_id)
    : ''
  manualForm.actual_controller_name = override?.actual_controller_name || ''
  manualForm.new_actual_controller_name =
    inferredMode === SUBJECT_MODE_NEW_ENTITY ? override?.actual_controller_name || '' : ''
  manualForm.new_actual_controller_type =
    inferredMode === SUBJECT_MODE_NEW_ENTITY ? override?.actual_controller_type || 'other' : 'other'
  manualForm.new_actual_controller_country =
    inferredMode === SUBJECT_MODE_NEW_ENTITY ? override?.actual_control_country || '' : ''
  manualForm.new_actual_controller_notes =
    inferredMode === SUBJECT_MODE_NEW_ENTITY
      ? snapshot?.created_actual_controller_entity?.notes || ''
      : ''
  manualForm.actual_control_country = override?.actual_control_country || ''
  manualForm.manual_control_ratio = override?.manual_control_ratio || ''
  manualForm.manual_control_strength_label = override?.manual_control_strength_label || ''
  manualForm.manual_control_path = override?.manual_path_summary || override?.manual_control_path || ''
  manualForm.manual_control_type = override?.manual_control_type || ''
  manualForm.manual_decision_reason = override?.manual_decision_reason || ''
  manualForm.manual_path_count = override?.manual_path_count ? String(override.manual_path_count) : ''
  manualForm.manual_path_depth = override?.manual_path_depth ? String(override.manual_path_depth) : ''
  manualForm.reason = override?.reason || ''
  manualForm.evidence = override?.evidence || ''

  const snapshotPaths = Array.isArray(snapshot?.manual_paths)
    ? snapshot.manual_paths
    : []
  const overridePathRows = pathRowsFromManualRecords(override?.manual_paths)
  const snapshotPathRows = pathRowsFromManualRecords(snapshotPaths)
  const pathRows = inferredMode === SUBJECT_MODE_NAME_SNAPSHOT
    ? []
    : overridePathRows.length
      ? overridePathRows
      : snapshotPathRows.length
        ? snapshotPathRows
        : pathRowsFromLegacyPathText(override?.manual_path_summary || override?.manual_control_path)
  resetManualPaths(pathRows.length ? pathRows : [createManualPathRow()])
}

watch(
  () => `${company.value?.id || 'none'}:${manualOverride.value?.id || 'auto'}`,
  (seedKey) => {
    if (seedKey === manualFormSeedKey.value) {
      return
    }
    manualFormSeedKey.value = seedKey
    populateManualFormFromOverride(manualOverride.value)
  },
  { immediate: true },
)

function buildManualPathPayloads() {
  return buildManualPathPayloadRecords({
    paths: manualForm.manual_paths,
    controllerEntityId: manualPathControllerEntityId.value,
    controllerName: manualPathControllerName.value,
    allowNameOnlyStart: isNewEntityMode.value,
    targetCompanyId: company.value?.id ? Number(company.value.id) : null,
    targetCompanyName: manualTargetCompanyName.value,
  })
}

function manualPayload(actionType) {
  const entityIdText = String(manualForm.actual_controller_entity_id ?? '').trim()
  const subjectMode = manualForm.actual_controller_subject_mode
  const manualPaths = subjectMode === SUBJECT_MODE_NAME_SNAPSHOT ? [] : buildManualPathPayloads()
  const existingControllerName = String(manualForm.actual_controller_name ?? '').trim()
  const newControllerName = String(manualForm.new_actual_controller_name ?? '').trim()
  const snapshotControllerName = String(manualForm.actual_controller_name ?? '').trim()

  return {
    action_type: actionType,
    actual_controller_subject_mode: subjectMode,
    actual_controller_entity_id:
      subjectMode === SUBJECT_MODE_EXISTING_ENTITY && entityIdText ? Number(entityIdText) : null,
    actual_controller_name:
      subjectMode === SUBJECT_MODE_NEW_ENTITY
        ? newControllerName || null
        : subjectMode === SUBJECT_MODE_NAME_SNAPSHOT
          ? snapshotControllerName || null
          : existingControllerName || null,
    new_actual_controller_name:
      subjectMode === SUBJECT_MODE_NEW_ENTITY ? newControllerName || null : null,
    new_actual_controller_type:
      subjectMode === SUBJECT_MODE_NEW_ENTITY
        ? String(manualForm.new_actual_controller_type ?? '').trim() || 'other'
        : null,
    new_actual_controller_country:
      subjectMode === SUBJECT_MODE_NEW_ENTITY
        ? String(manualForm.new_actual_controller_country ?? '').trim() || null
        : null,
    new_actual_controller_notes:
      subjectMode === SUBJECT_MODE_NEW_ENTITY
        ? String(manualForm.new_actual_controller_notes ?? '').trim() || null
        : null,
    actual_control_country: String(manualForm.actual_control_country ?? '').trim() || null,
    manual_control_ratio: String(manualForm.manual_control_ratio ?? '').trim() || null,
    manual_control_strength_label: String(manualForm.manual_control_strength_label ?? '').trim() || null,
    manual_control_path:
      subjectMode === SUBJECT_MODE_NAME_SNAPSHOT ? null : manualGeneratedPathSummary.value || null,
    manual_paths: manualPaths.length ? manualPaths : null,
    manual_control_type: String(manualForm.manual_control_type ?? '').trim() || null,
    manual_decision_reason: String(manualForm.manual_decision_reason ?? '').trim() || null,
    manual_path_count: null,
    manual_path_depth: null,
    reason: String(manualForm.reason ?? '').trim() || null,
    evidence: String(manualForm.evidence ?? '').trim() || null,
    operator: 'researcher',
  }
}

async function refreshAfterManualChange(message) {
  if (resolvedCompanyId.value) {
    await loadCompanyData(resolvedCompanyId.value)
  }
  ElMessage.success(message)
}

async function handleConfirmAutomaticResult() {
  if (!resolvedCompanyId.value) {
    return
  }
  manualSaving.value = true
  try {
    await submitManualControlOverride(resolvedCompanyId.value, {
      action_type: 'confirm_auto',
      reason: String(manualForm.reason ?? '').trim() || '人工确认自动分析结果。',
      evidence: String(manualForm.evidence ?? '').trim() || null,
      operator: 'researcher',
    })
    await refreshAfterManualChange('已写入人工确认记录，当前生效结果标记为人工确认。')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    manualSaving.value = false
  }
}

async function handleSubmitManualOverride() {
  if (!resolvedCompanyId.value) {
    return
  }
  const payload = manualPayload('override_result')
  if (payload.actual_controller_subject_mode === SUBJECT_MODE_EXISTING_ENTITY && !payload.actual_controller_entity_id && payload.actual_controller_name) {
    ElMessage.warning('使用现有主体时请先选择或填写有效 entity_id；若只记录名称，请切换为“仅名称快照”。')
    return
  }
  if (payload.actual_controller_subject_mode === SUBJECT_MODE_NEW_ENTITY && !payload.new_actual_controller_name) {
    ElMessage.warning('新建主体模式下请填写主体名称。')
    return
  }
  if (!payload.actual_controller_entity_id && !payload.actual_controller_name && !payload.actual_control_country) {
    ElMessage.warning('请至少填写实际控制人或实际控制国别。')
    return
  }
  manualSaving.value = true
  try {
    await submitManualControlOverride(resolvedCompanyId.value, payload)
    await refreshAfterManualChange('人工征订结果已设为当前生效。')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    manualSaving.value = false
  }
}

async function handleRestoreAutomaticResult() {
  if (!resolvedCompanyId.value) {
    return
  }
  manualSaving.value = true
  try {
    await restoreAutomaticControlResult(resolvedCompanyId.value, {
      action_type: 'restore_auto',
      reason: String(manualForm.reason ?? '').trim() || '恢复为自动分析结果。',
      operator: 'researcher',
    })
    await refreshAfterManualChange('已恢复为自动分析结果。')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    manualSaving.value = false
  }
}
</script>

<template>
  <div id="module-top" class="page-shell">
    <header class="page-header">
      <h1 class="page-title">全球上市公司实际国别归属及主要业务线征订系统</h1>
      <p class="page-subtitle">
        面向全球上市公司研究场景，系统综合企业基础信息、控制链结构、实际控制国别与主要业务线分类结果，支持对企业归属判断和产业结构标签进行复核、修订与追踪。
      </p>
    </header>

    <div id="module-company-search" class="module-anchor">
      <SearchBar
        v-model="companyIdInput"
        :loading="loading"
        :searching="companySearchLoading"
        :results="companySearchResults"
        :has-searched="companySearchAttempted"
        :empty-message="companySearchEmptyMessage"
        @search="handleSearch"
        @select-company="handleSelectCompany"
        @open-import="openOwnershipImportDialog"
      />
    </div>

    <el-alert
      v-if="pageError"
      class="status-banner"
      type="error"
      show-icon
      :closable="false"
      :title="pageError"
    />

    <el-card v-if="!hasSearched && !loading" class="helper-empty" shadow="never">
      <el-empty description="请输入公司名称、股票代码，或使用 /ID 精确查询" :image-size="96">
        <template #description>
          <div class="table-text table-text--muted">
            可直接使用上方推荐演示 ID，例如 /128、/240、/9717。
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

        <div id="module-company-overview" class="module-anchor">
          <CompanyOverviewCard
            :company="company"
            :control-analysis="controlAnalysis"
            :country-attribution="countryAttribution"
            :industry-analysis="industryAnalysis"
            :result-source-label="currentResultSourceLabel"
          />
        </div>

        <div class="analysis-report">
          <section id="module-control-analysis" class="analysis-module analysis-module--control module-anchor">
              <div class="analysis-module__header">
                <div>
                  <h2>控股结构分析</h2>
                  <p>展示企业控制主体、控制路径与国别归属判断结果。</p>
                </div>
              </div>

            <div class="analysis-module__body">
              <div id="module-control-summary" class="module-anchor">
                <ControlSummaryCard
                  :company="company"
                  :control-analysis="controlAnalysis"
                  :country-attribution="countryAttribution"
                />
              </div>

              <div id="module-control-structure" class="module-anchor">
                <ControlStructureDiagram
                  :company="company"
                  :control-analysis="controlAnalysis"
                  :country-attribution="countryAttribution"
                  :relationship-graph="relationshipGraph || buildEmptyGraphState(resolvedCompanyId)"
                />
              </div>

              <div id="module-control-details" class="module-anchor">
                <ControlRelationsTable
                  :company-id="resolvedCompanyId"
                  :relationships="controlRelationships"
                  :loading="loading"
                  :control-analysis="controlAnalysis"
                  :country-attribution="countryAttribution"
                  :company="company"
                  @manual-judgment-change="loadCompanyData(resolvedCompanyId)"
                />
              </div>

              <section id="module-manual-review" class="manual-entry-card module-anchor">
                <div class="manual-entry-card__head">
                  <div>
                    <h3>人工征订与确认</h3>
                    <p>用于补充或调整控制主体、控制国别与控制路径。</p>
                  </div>
                  <div class="manual-entry-card__actions">
                    <span
                      class="manual-control-panel__status"
                      :class="manualEffective ? 'manual-control-panel__status--manual' : 'manual-control-panel__status--auto'"
                    >
                      {{ manualEffective ? '人工征订/确认生效' : '自动结果生效' }}
                    </span>
                    <el-button size="small" plain @click="toggleManualPanel">
                      {{ manualPanelExpanded ? '收起人工征订' : '展开人工征订' }}
                    </el-button>
                  </div>
                </div>

                <div class="manual-entry-card__summary">
                  当前生效：<strong>{{ currentResultSourceLabel }}</strong>。
                </div>

                <el-alert
                  v-if="manualSnapshotOnlyActive"
                  class="manual-control-panel__alert"
                  type="info"
                  show-icon
                  :closable="false"
                  title="当前人工征订控制人仅为名称快照，未绑定实体库；图中未作为正式结构节点展示。"
                  :description="`当前人工征订控制人名称：${manualOverride?.actual_controller_name}`"
                />

                <el-alert
                  v-if="manualEffective"
                  class="manual-control-panel__alert"
                  type="warning"
                  show-icon
                  :closable="false"
                  title="当前实际控制结论由人工征订或人工确认确定"
                  :description="`说明：${optionalText(manualOverride?.reason)}；依据：${optionalText(manualOverride?.evidence)}`"
                />

                <transition name="manual-panel">
                  <section v-if="manualPanelExpanded" class="manual-control-panel">
                    <div class="manual-control-panel__form">
                      <el-form label-position="top">
                        <el-form-item label="实际控制人主体来源" class="manual-subject-source">
                          <div class="manual-subject-source__control">
                            <el-radio-group
                              v-model="manualForm.actual_controller_subject_mode"
                              class="manual-subject-source__radio-group"
                            >
                              <el-radio-button :label="SUBJECT_MODE_EXISTING_ENTITY">
                                使用现有主体
                              </el-radio-button>
                              <el-radio-button :label="SUBJECT_MODE_NEW_ENTITY">
                                新建主体并入库
                              </el-radio-button>
                              <el-radio-button :label="SUBJECT_MODE_NAME_SNAPSHOT">
                                仅名称快照
                              </el-radio-button>
                            </el-radio-group>
                          </div>
                          <p class="manual-subject-source__help">
                            仅绑定 entity_id 的主体会进入正式结构图和控制路径构建。
                          </p>
                        </el-form-item>

                        <template v-if="isExistingEntityMode">
                          <el-form-item label="选择现有主体">
                            <el-select
                              v-model="manualForm.actual_controller_entity_id"
                              filterable
                              remote
                              reserve-keyword
                              clearable
                              :remote-method="searchShareholderEntityOptions"
                              :loading="shareholderEntityLoading"
                              placeholder="输入主体名称或 entity_id 搜索"
                              @change="syncSelectedExistingEntity"
                            >
                              <el-option
                                v-for="entity in shareholderEntityOptions"
                                :key="entity.id"
                                :label="entityOptionLabel(entity)"
                                :value="String(entity.id)"
                              />
                            </el-select>
                          </el-form-item>
                          <el-form-item label="实际控制人 entity_id">
                            <el-input
                              v-model="manualForm.actual_controller_entity_id"
                              placeholder="也可直接填写 entity_id；仅征订国别时可留空"
                              clearable
                            />
                          </el-form-item>
                          <el-form-item label="实际控制人名称快照（可选）">
                            <el-input
                              v-model="manualForm.actual_controller_name"
                              placeholder="未填写时后端按 entity_id 对应主体名称补全"
                              clearable
                            />
                          </el-form-item>
                        </template>

                        <template v-else-if="isNewEntityMode">
                          <el-form-item label="新建主体名称">
                            <el-input
                              v-model="manualForm.new_actual_controller_name"
                              placeholder="保存时先写入 shareholder_entities，再绑定为实际控制人"
                              clearable
                            />
                          </el-form-item>
                          <div class="manual-control-panel__inline-fields">
                            <el-form-item label="主体类型">
                              <el-select v-model="manualForm.new_actual_controller_type" placeholder="主体类型">
                                <el-option label="公司主体" value="company" />
                                <el-option label="自然人" value="person" />
                                <el-option label="机构投资者" value="institution" />
                                <el-option label="基金 / 公众持股" value="fund" />
                                <el-option label="政府 / 国资主体" value="government" />
                                <el-option label="其他主体" value="other" />
                              </el-select>
                            </el-form-item>
                            <el-form-item label="国家 / 地区（可选）">
                              <el-input
                                v-model="manualForm.new_actual_controller_country"
                                placeholder="例如 China、United States"
                                clearable
                              />
                            </el-form-item>
                          </div>
                          <el-form-item label="新建主体备注（可选）">
                            <el-input
                              v-model="manualForm.new_actual_controller_notes"
                              type="textarea"
                              :rows="2"
                              placeholder="例如：由人工征订创建，用于绑定控制结论"
                            />
                          </el-form-item>
                        </template>

                        <template v-else>
                          <el-form-item label="实际控制人名称快照">
                            <el-input
                              v-model="manualForm.actual_controller_name"
                              placeholder="仅记录名称，不创建实体，不绑定 entity_id"
                              clearable
                            />
                            <span class="manual-control-panel__field-help">
                              仅名称快照不会写入 shareholder_entities，也不会作为正式结构节点进入图或路径。
                            </span>
                          </el-form-item>
                        </template>

                        <el-form-item label="实际控制国别">
                          <el-input
                            v-model="manualForm.actual_control_country"
                            placeholder="可单独征订国别"
                            clearable
                          />
                        </el-form-item>
                        <el-form-item label="征订说明">
                          <el-input
                            v-model="manualForm.reason"
                            type="textarea"
                            :rows="2"
                            placeholder="例如：根据研究资料确认最终控制人为该主体"
                          />
                        </el-form-item>
                        <el-form-item label="征订依据">
                          <el-input
                            v-model="manualForm.evidence"
                            type="textarea"
                            :rows="2"
                            placeholder="例如：年报、监管披露、人工核验记录"
                          />
                        </el-form-item>

                        <section class="manual-path-builder">
                          <div class="manual-path-builder__head">
                            <div>
                              <h3>控制路径构建</h3>
                              <p>设置控制路径时，起点为控制主体，终点为当前目标公司。</p>
                            </div>
                            <el-button
                              size="small"
                              type="primary"
                              plain
                              :disabled="!manualCanEditPaths"
                              @click="addManualPath"
                            >
                              添加路径
                            </el-button>
                          </div>

                          <el-alert
                            v-if="!manualHasControllerForPaths"
                            class="manual-path-builder__alert"
                            type="info"
                            show-icon
                            :closable="false"
                            :title="manualPathBuilderBlockedTitle"
                          />

                          <div class="manual-path-builder__stats">
                            <div>
                              <span>自动摘要</span>
                              <strong>{{ manualGeneratedPathSummary || '未生成正式路径' }}</strong>
                            </div>
                            <div>
                              <span>路径数量</span>
                              <strong>{{ manualGeneratedPathCount }} 条</strong>
                            </div>
                            <div>
                              <span>主路径链路深度</span>
                              <strong>{{ manualGeneratedPathDepth ?? '—' }}</strong>
                            </div>
                          </div>

                          <div class="manual-path-builder__list">
                            <div
                              v-for="(path, pathIndex) in manualForm.manual_paths"
                              :key="path.key"
                              class="manual-path-row"
                            >
                              <div class="manual-path-row__head">
                                <strong>路径 {{ pathIndex + 1 }}{{ pathIndex === 0 ? ' · 主路径' : '' }}</strong>
                                <el-button
                                  v-if="manualForm.manual_paths.length > 1"
                                  size="small"
                                  link
                                  type="danger"
                                  :disabled="!manualCanEditPaths"
                                  @click="removeManualPath(pathIndex)"
                                >
                                  删除路径
                                </el-button>
                              </div>
                              <div class="manual-path-row__nodes">
                                <span class="manual-path-node manual-path-node--fixed">
                                  {{ manualControllerLabel }}
                                </span>
                                <span class="manual-path-arrow">→</span>
                                <template
                                  v-for="(node, nodeIndex) in path.intermediate_nodes"
                                  :key="node.key"
                                >
                                  <div class="manual-path-node manual-path-node--editable">
                                    <el-input
                                      v-model="node.name"
                                      size="small"
                                      placeholder="中间节点名称"
                                      :disabled="!manualCanEditPaths"
                                      clearable
                                    />
                                    <el-button
                                      size="small"
                                      link
                                      type="danger"
                                      :disabled="!manualCanEditPaths"
                                      @click="removeManualIntermediateNode(path, nodeIndex)"
                                    >
                                      删除
                                    </el-button>
                                  </div>
                                  <span class="manual-path-arrow">→</span>
                                </template>
                                <span class="manual-path-node manual-path-node--fixed">
                                  {{ manualTargetCompanyName }}
                                </span>
                              </div>
                              <div class="manual-path-row__ratio">
                                <el-form-item label="路径支持比例（可选）">
                                  <el-input
                                    v-model="path.path_ratio"
                                    size="small"
                                    placeholder="例如 63.5 或 63.5%"
                                    :disabled="!manualCanEditPaths"
                                    clearable
                                  />
                                </el-form-item>
                                <span>表示该路径对控制结论的支持强度，仅针对本路径，可留空。</span>
                              </div>
                              <div class="manual-path-row__actions">
                                <el-button
                                  size="small"
                                  plain
                                  :disabled="!manualCanEditPaths"
                                  @click="addManualIntermediateNode(path)"
                                >
                                  添加中间节点
                                </el-button>
                              </div>
                            </div>
                          </div>
                        </section>

                        <el-collapse class="manual-control-panel__optional">
                          <el-collapse-item title="可选补充展示信息" name="manual-details">
                            <div class="manual-control-panel__optional-grid">
                              <el-form-item label="最终展示控制强度（可选）">
                                <el-input
                                  v-model="manualForm.manual_control_ratio"
                                  placeholder="例如 63.5 或 63.5%"
                                  clearable
                                />
                                <span class="manual-control-panel__field-help">
                                  用于控制结论明细表展示的最终控制强度。若未填写，将优先使用主路径比例。
                                  <template v-if="manualForm.manual_paths.length === 1">
                                    当前仅一条路径，默认使用该路径比例作为展示值。
                                  </template>
                                </span>
                              </el-form-item>
                              <el-form-item label="控制强度标签">
                                <el-input
                                  v-model="manualForm.manual_control_strength_label"
                                  placeholder="例如：人工认定强控制"
                                  clearable
                                />
                              </el-form-item>
                              <el-form-item label="认定类型">
                                <el-input
                                  v-model="manualForm.manual_control_type"
                                  placeholder="例如：股权控制（人工征订）"
                                  clearable
                                />
                              </el-form-item>
                              <el-form-item label="判定原因">
                                <el-input
                                  v-model="manualForm.manual_decision_reason"
                                  type="textarea"
                                  :rows="2"
                                  placeholder="例如：根据研究资料人工确认最终控制人为该主体"
                                />
                              </el-form-item>
                            </div>
                          </el-collapse-item>
                        </el-collapse>
                      </el-form>

                      <div class="manual-control-panel__actions">
                        <el-button
                          type="primary"
                          :loading="manualSaving"
                          @click="handleSubmitManualOverride"
                        >
                          写入人工征订
                        </el-button>
                        <el-button
                          :loading="manualSaving"
                          @click="handleConfirmAutomaticResult"
                        >
                          确认自动结果
                        </el-button>
                        <el-button
                          v-if="manualEffective"
                          type="warning"
                          plain
                          :loading="manualSaving"
                          @click="handleRestoreAutomaticResult"
                        >
                          恢复自动结果
                        </el-button>
                      </div>
                    </div>
                  </section>
                </transition>
              </section>
            </div>
          </section>

          <section id="module-industry-analysis" class="analysis-module analysis-module--industry module-anchor">
            <div class="analysis-module__header analysis-module__header--actionable">
              <div>
                <h2>产业分析</h2>
                <p>展示企业业务线结构、行业分类结果与待复核样本。</p>
              </div>
              <el-button type="primary" @click="openIndustryWorkbench">
                进入产业分析工作台
              </el-button>
            </div>

            <div class="analysis-module__body">
              <IndustryAnalysisPanel
                :company="company"
                :company-id="company?.id || resolvedCompanyId"
                :industry-analysis="industryAnalysis"
                :loading="loading"
                @refresh-industry-analysis="refreshIndustryAnalysisData"
              />
            </div>
          </section>
        </div>

        <IndustryWorkbenchDrawer
          v-model="industryWorkbenchVisible"
          :company="company"
          :company-id="company?.id || resolvedCompanyId"
          :industry-analysis="industryAnalysis"
        />
      </div>
    </template>

    <el-card v-else class="helper-empty" shadow="never">
      <el-empty description="未获取到企业分析结果" :image-size="96">
        <template #description>
          <div class="table-text table-text--muted">
            请检查所选企业是否有效，以及后端服务是否已经启动。
          </div>
        </template>
      </el-empty>
    </el-card>

    <el-dialog
      v-model="ownershipImportVisible"
      title="数据导入中心"
      width="860px"
      destroy-on-close
    >
      <div class="data-import-center">
        <el-tabs v-model="dataImportActiveTab">
          <el-tab-pane label="控制关系事实导入" name="ownership">
            <div class="ownership-import">
              <section class="ownership-import-format" aria-label="导入格式说明">
                <h3>导入格式说明</h3>
                <p class="ownership-import-format__intro">
                  请上传一个 ZIP 文件，文件中建议包含以下 CSV：
                </p>
                <ol class="ownership-import-format__list">
                  <li>
                    <strong>companies.csv：公司基础信息</strong>
                    <div class="ownership-import-format__item">
                      <span>必填字段：<code>company_key</code>、<code>name</code></span>
                      <span>常用字段：<code>stock_code</code>、<code>incorporation_country</code>、<code>listing_country</code>、<code>headquarters</code>、<code>description</code></span>
                    </div>
                  </li>
                  <li>
                    <strong>shareholder_entities.csv：控制主体 / 股东节点</strong>
                    <div class="ownership-import-format__item">
                      <span>必填字段：<code>entity_key</code>、<code>entity_name</code>、<code>entity_type</code></span>
                      <span>常用字段：<code>country</code>、<code>linked_company_key</code>、<code>entity_subtype</code>、<code>beneficial_owner_disclosed</code></span>
                      <span>说明：<code>linked_company_key</code> 用于把某个控制主体绑定到 <code>companies.csv</code> 中的公司。</span>
                    </div>
                  </li>
                  <li>
                    <strong>shareholder_structures.csv：控制关系边</strong>
                    <div class="ownership-import-format__item">
                      <span>必填字段：<code>structure_key</code>、<code>from_entity_key</code>、<code>to_entity_key</code>、<code>relation_type</code></span>
                      <span>常用字段：<code>holding_ratio</code>、<code>effective_control_ratio</code>、<code>is_direct</code>、<code>is_current</code>、<code>confidence_level</code>、<code>remarks</code></span>
                      <span>说明：<code>from_entity_key</code> 表示控制方，<code>to_entity_key</code> 表示被控制方。</span>
                    </div>
                  </li>
                  <li>
                    <strong>relationship_sources.csv：证据来源，可选</strong>
                    <div class="ownership-import-format__item">
                      <span>必填字段：<code>structure_key</code>、<code>source_type</code>、<code>source_name</code></span>
                      <span>常用字段：<code>source_url</code>、<code>source_date</code>、<code>excerpt</code>、<code>confidence_level</code></span>
                    </div>
                  </li>
                </ol>
                <p class="ownership-import-format__note">
                  导入文件中的 <code>company_key</code>、<code>entity_key</code>、<code>structure_key</code> 只用于描述文件内部关系，不是数据库 ID。系统会在导入时自动生成数据库 ID，并建立公司、主体和控制关系之间的关联。
                </p>
              </section>

              <el-collapse v-model="ownershipImportExampleCollapse" class="ownership-import-example">
                <el-collapse-item title="查看最小示例" name="minimal-example">
                  <div class="ownership-import-example__content">
                    <pre><code>companies.csv
company_key,name,stock_code,incorporation_country
target,Import Target Co,IMP-9001,China

shareholder_entities.csv
entity_key,entity_name,entity_type,country,linked_company_key
target,Import Target Co Entity,company,China,target
parent,Import Parent Ltd,company,Singapore,

shareholder_structures.csv
structure_key,from_entity_key,to_entity_key,relation_type,holding_ratio,effective_control_ratio,is_direct,is_current
s001,parent,target,equity,60%,60%,true,true</code></pre>
                    <p class="ownership-import-example__note">
                      <code>parent -&gt; target</code> 表示 Import Parent Ltd 控制 Import Target Co Entity；<code>target</code> 通过 <code>linked_company_key</code> 绑定到 <code>companies.csv</code> 中的 Import Target Co。
                    </p>
                  </div>
                </el-collapse-item>
              </el-collapse>
              <el-form label-position="top">
                <el-form-item label="ZIP 文件">
                  <el-upload
                    drag
                    action=""
                    :auto-upload="false"
                    :limit="1"
                    :file-list="ownershipImportFileList"
                    accept=".zip"
                    :on-change="handleOwnershipImportFileChange"
                    :on-remove="clearOwnershipImportFile"
                  >
                    <div class="ownership-import__upload-text">
                      将包含 companies.csv、shareholder_entities.csv、shareholder_structures.csv、relationship_sources.csv 的 ZIP 拖到此处，或点击选择文件
                    </div>
                  </el-upload>
                </el-form-item>

                <div class="ownership-import__options">
                  <el-form-item label="导入模式">
                    <el-radio-group v-model="ownershipImportForm.mode">
                      <el-radio-button label="validate">仅校验</el-radio-button>
                      <el-radio-button label="commit">导入保存</el-radio-button>
                      <el-radio-button label="commit_and_analyze">导入并生成分析结果</el-radio-button>
                    </el-radio-group>
                  </el-form-item>
                  <el-form-item label="冲突处理">
                    <el-radio-group v-model="ownershipImportForm.conflictStrategy">
                      <el-radio-button
                        v-if="ownershipImportForm.mode !== 'commit_and_analyze'"
                        label="fail"
                      >
                        发现重复即失败
                      </el-radio-button>
                      <el-radio-button label="skip">跳过重复</el-radio-button>
                      <el-radio-button label="update">更新已有</el-radio-button>
                    </el-radio-group>
                    <span
                      v-if="ownershipImportForm.mode === 'commit_and_analyze'"
                      class="ownership-import__field-help"
                    >
                      已有数据默认跳过，并继续生成或复用控制分析结果。
                    </span>
                  </el-form-item>
                  <el-form-item
                    v-if="ownershipImportForm.mode === 'commit_and_analyze'"
                    label="分析策略"
                  >
                    <el-radio-group v-model="ownershipImportForm.analysisStrategy">
                      <el-radio-button label="missing_only">仅缺失时生成</el-radio-button>
                      <el-radio-button label="force">强制重新分析</el-radio-button>
                    </el-radio-group>
                  </el-form-item>
                </div>
              </el-form>

              <div class="ownership-import__actions">
                <el-button @click="ownershipImportVisible = false">关闭</el-button>
                <el-button
                  type="primary"
                  :loading="ownershipImportSubmitting"
                  @click="handleOwnershipImport"
                >
                  开始导入
                </el-button>
              </div>

              <section v-if="ownershipImportResult" class="ownership-import__result">
                <div class="ownership-import__stats">
                  <div>
                    <span>公司</span>
                    <strong>{{ ownershipImportResult.summary?.companies_created || 0 }} / {{ ownershipImportResult.summary?.companies_matched || 0 }} / {{ ownershipImportResult.summary?.companies_updated || 0 }}</strong>
                  </div>
                  <div>
                    <span>控制主体</span>
                    <strong>{{ ownershipImportResult.summary?.entities_created || 0 }} / {{ ownershipImportResult.summary?.entities_matched || 0 }} / {{ ownershipImportResult.summary?.entities_updated || 0 }}</strong>
                  </div>
                  <div>
                    <span>控制关系</span>
                    <strong>{{ ownershipImportResult.summary?.structures_created || 0 }} / {{ ownershipImportResult.summary?.structures_matched || 0 }} / {{ ownershipImportResult.summary?.structures_updated || 0 }}</strong>
                  </div>
                  <div>
                    <span>证据来源</span>
                    <strong>{{ ownershipImportResult.summary?.sources_created || 0 }} / {{ ownershipImportResult.summary?.sources_matched || 0 }} / {{ ownershipImportResult.summary?.sources_updated || 0 }}</strong>
                  </div>
                  <div>
                    <span>错误</span>
                    <strong>{{ ownershipImportResult.summary?.error_count || 0 }}</strong>
                  </div>
                </div>
                <p class="ownership-import__stats-note">摘要数值顺序：新增 / 匹配跳过 / 更新。</p>

                <el-table
                  v-if="ownershipImportResult.errors?.length"
                  :data="ownershipImportResult.errors"
                  size="small"
                  border
                  max-height="260"
                >
                  <el-table-column prop="file" label="文件" min-width="170" />
                  <el-table-column prop="row" label="行" width="72" />
                  <el-table-column prop="field" label="字段" min-width="150" />
                  <el-table-column prop="message" label="错误信息" min-width="260" />
                </el-table>

                <el-alert
                  v-if="ownershipImportResult.warnings?.length"
                  type="warning"
                  show-icon
                  :closable="false"
                  title="导入完成，但存在需要关注的警告。"
                />

                <el-table
                  v-if="ownershipImportResult.warnings?.length"
                  :data="ownershipImportResult.warnings"
                  size="small"
                  border
                  max-height="220"
                >
                  <el-table-column prop="file" label="文件" min-width="170" />
                  <el-table-column prop="row" label="行" width="72" />
                  <el-table-column prop="field" label="字段" min-width="150" />
                  <el-table-column prop="message" label="警告信息" min-width="260" />
                </el-table>

                <section
                  v-if="ownershipImportResult.analysis?.items?.length"
                  class="ownership-import__analysis"
                >
                  <h3>分析处理结果</h3>
                  <el-table
                    :data="ownershipImportResult.analysis.items"
                    size="small"
                    border
                    max-height="280"
                  >
                    <el-table-column prop="company_name" label="公司名称" min-width="180" />
                    <el-table-column label="状态" width="110">
                      <template #default="{ row }">
                        {{ analysisStatusLabel(row.analysis_status) }}
                      </template>
                    </el-table-column>
                    <el-table-column prop="control_relationship_count" label="控制关系数量" width="120" />
                    <el-table-column prop="actual_control_country" label="实际控制国别" min-width="130" />
                    <el-table-column prop="attribution_type" label="归属类型" min-width="150" />
                    <el-table-column prop="message" label="说明" min-width="240" />
                  </el-table>
                </section>
              </section>
            </div>
          </el-tab-pane>

          <el-tab-pane label="业务线事实导入" name="business-segments">
            <div class="data-import-placeholder">
              <h3>业务线事实导入</h3>
              <p>用于导入企业业务线事实数据，如业务线名称、收入占比、报告期和说明。该功能后续支持。</p>
              <el-tag type="info" effect="plain">后续支持</el-tag>
            </div>
          </el-tab-pane>

          <el-tab-pane label="产业分类结果导入" name="industry-classifications">
            <div class="data-import-placeholder">
              <h3>产业分类结果导入</h3>
              <p>后续可用于导入 business_segment_classifications.csv，支持产业分类结果批量维护。</p>
              <el-tag type="info" effect="plain">后续支持</el-tag>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-dialog>

    <FloatingModuleNav
      :top-item="floatingModuleNavTopItem"
      :groups="floatingModuleNavGroups"
      :hidden="industryWorkbenchVisible"
    />
  </div>
</template>

<style scoped>
.module-anchor {
  min-width: 0;
  scroll-margin-top: 16px;
}

.analysis-report {
  display: grid;
  gap: 28px;
  margin-top: 24px;
  min-width: 0;
}

.analysis-module {
  display: grid;
  gap: 18px;
  padding: 20px;
  border-radius: 18px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 14px 34px rgba(17, 37, 58, 0.05);
  min-width: 0;
}

.analysis-module--control {
  background: linear-gradient(180deg, rgba(248, 251, 254, 0.96), rgba(255, 255, 255, 0.94));
  border-color: rgba(48, 95, 131, 0.14);
}

.analysis-module--industry {
  background: linear-gradient(180deg, rgba(252, 250, 246, 0.96), rgba(255, 255, 255, 0.94));
  border-color: rgba(144, 116, 77, 0.14);
}

.analysis-module__header {
  display: grid;
  gap: 8px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(31, 59, 87, 0.08);
}

.analysis-module__header--actionable {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: 16px;
}

.analysis-module__header h2 {
  margin: 0;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.analysis-module__header p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.analysis-module__body {
  display: grid;
  gap: 18px;
  min-width: 0;
}

@media (max-width: 720px) {
  .analysis-module__header--actionable {
    grid-template-columns: 1fr;
  }
}

.manual-entry-card {
  display: grid;
  gap: 14px;
  padding: 18px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 14px;
  background: rgba(248, 251, 253, 0.9);
}

.manual-entry-card__head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.manual-entry-card__head h3 {
  margin: 0;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.manual-entry-card__head p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  line-height: 1.65;
}

.manual-entry-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: flex-end;
}

.manual-entry-card__summary {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid rgba(48, 95, 131, 0.12);
  background: rgba(255, 255, 255, 0.74);
  color: var(--text-secondary);
  line-height: 1.7;
}

.manual-control-panel {
  display: grid;
  gap: 14px;
  padding: 18px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.82);
}

.manual-panel-enter-active,
.manual-panel-leave-active {
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}

.manual-panel-enter-from,
.manual-panel-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.manual-control-panel__status {
  flex: 0 0 auto;
  min-height: 28px;
  padding: 5px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.3;
}

.manual-control-panel__status--manual {
  color: #9b3a3a;
  border-color: rgba(155, 58, 58, 0.24);
  background: rgba(155, 58, 58, 0.1);
}

.manual-control-panel__status--auto {
  color: #305f83;
  border-color: rgba(48, 95, 131, 0.2);
  background: rgba(48, 95, 131, 0.08);
}

.manual-control-panel__alert {
  margin: 0;
}

.manual-control-panel__form {
  min-width: 0;
}

.manual-path-builder {
  display: grid;
  gap: 12px;
  margin-bottom: 14px;
  padding: 14px;
  border: 1px solid rgba(48, 95, 131, 0.16);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
}

.manual-path-builder__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.manual-path-builder__head h3 {
  margin: 0;
  color: var(--brand-ink);
  font-size: 15px;
}

.manual-path-builder__head p {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.manual-path-builder__alert {
  margin: 0;
}

.manual-path-builder__stats {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(96px, 0.4fr) minmax(120px, 0.4fr);
  gap: 10px;
}

.manual-path-builder__stats > div {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  border-radius: 8px;
  background: rgba(248, 251, 253, 0.86);
}

.manual-path-builder__stats span {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.manual-path-builder__stats strong {
  color: var(--brand-ink);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.manual-path-builder__list {
  display: grid;
  gap: 10px;
}

.manual-path-row {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
}

.manual-path-row__head,
.manual-path-row__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.manual-path-row__head strong {
  color: var(--brand-ink);
  font-size: 13px;
}

.manual-path-row__nodes {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.manual-path-row__ratio {
  display: grid;
  grid-template-columns: minmax(180px, 260px) minmax(0, 1fr);
  align-items: end;
  gap: 10px;
}

.manual-path-row__ratio :deep(.el-form-item) {
  margin-bottom: 0;
}

.manual-path-row__ratio span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.manual-path-node {
  min-height: 32px;
  min-width: 128px;
  max-width: 100%;
  border-radius: 8px;
}

.manual-path-node--fixed {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border: 1px solid rgba(48, 95, 131, 0.14);
  color: var(--brand-ink);
  background: rgba(248, 251, 253, 0.96);
  font-size: 12px;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.manual-path-node--editable {
  display: inline-grid;
  grid-template-columns: minmax(150px, 220px) auto;
  align-items: center;
  gap: 6px;
}

.manual-path-arrow {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
}

.manual-control-panel__optional {
  margin-bottom: 14px;
  border-radius: 8px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  background: rgba(255, 255, 255, 0.62);
}

.manual-control-panel__optional :deep(.el-collapse-item__header) {
  padding: 0 12px;
  color: var(--brand-ink);
  font-weight: 700;
  background: transparent;
}

.manual-control-panel__optional :deep(.el-collapse-item__content) {
  padding: 4px 12px 12px;
}

.manual-control-panel__optional-grid {
  display: grid;
  gap: 8px;
}

.manual-control-panel__field-help {
  display: block;
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.manual-subject-source {
  margin-bottom: 16px;
}

.manual-subject-source :deep(.el-form-item__content) {
  display: grid;
  align-items: start;
}

.manual-subject-source__control {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  margin-bottom: 8px;
}

.manual-subject-source__radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.manual-subject-source__radio-group :deep(.el-radio-button) {
  margin: 0;
}

.manual-subject-source__radio-group :deep(.el-radio-button__inner) {
  border-radius: 8px;
  white-space: normal;
}

.manual-subject-source__help {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.manual-control-panel__inline-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.manual-control-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.ownership-import {
  display: grid;
  gap: 16px;
}

.data-import-center {
  min-width: 0;
}

.data-import-placeholder {
  display: grid;
  gap: 10px;
  padding: 18px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  background: rgba(248, 251, 253, 0.86);
}

.data-import-placeholder h3 {
  margin: 0;
  color: var(--brand-ink);
  font-size: 15px;
}

.data-import-placeholder p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.ownership-import-format {
  display: grid;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  background: rgba(248, 251, 253, 0.9);
}

.ownership-import-format h3 {
  margin: 0;
  color: var(--brand-ink);
  font-size: 15px;
}

.ownership-import-format__intro,
.ownership-import-format__note {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.65;
}

.ownership-import-format__list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding-left: 20px;
}

.ownership-import-format__list li {
  color: var(--brand-ink);
  line-height: 1.55;
}

.ownership-import-format__item {
  display: grid;
  gap: 3px;
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.55;
}

.ownership-import-format code,
.ownership-import-example code {
  padding: 1px 4px;
  border-radius: 4px;
  background: rgba(31, 59, 87, 0.08);
  color: var(--brand-ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 0.95em;
}

.ownership-import-example {
  overflow: hidden;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.92);
}

.ownership-import-example :deep(.el-collapse-item__header) {
  height: 42px;
  padding: 0 14px;
  border-bottom-color: rgba(31, 59, 87, 0.08);
  color: var(--brand-ink);
  font-size: 13px;
  font-weight: 700;
}

.ownership-import-example :deep(.el-collapse-item__content) {
  padding: 12px 14px 14px;
}

.ownership-import-example__content {
  display: grid;
  gap: 10px;
}

.ownership-import-example pre {
  max-height: 260px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border: 1px solid rgba(31, 59, 87, 0.08);
  border-radius: 8px;
  background: rgba(248, 251, 253, 0.95);
  color: var(--brand-ink);
  font-size: 12px;
  line-height: 1.55;
}

.ownership-import-example pre code {
  padding: 0;
  background: transparent;
  font-size: inherit;
}

.ownership-import-example__note {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.65;
}

.ownership-import__upload-text {
  color: var(--brand-ink);
  font-weight: 700;
}

.ownership-import__field-help {
  display: block;
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.ownership-import__options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.ownership-import__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.ownership-import__result {
  display: grid;
  gap: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(31, 59, 87, 0.1);
}

.ownership-import__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.ownership-import__stats > div {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  background: rgba(248, 251, 253, 0.9);
}

.ownership-import__stats span {
  color: var(--text-secondary);
  font-size: 12px;
}

.ownership-import__stats strong {
  color: var(--brand-ink);
  font-size: 16px;
}

.ownership-import__stats-note {
  margin: -6px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.ownership-import__analysis {
  display: grid;
  gap: 10px;
}

.ownership-import__analysis h3 {
  margin: 0;
  color: var(--brand-ink);
  font-size: 15px;
}

@media (max-width: 980px) {
  .manual-entry-card__head {
    display: grid;
  }
}

@media (max-width: 560px) {
  .analysis-module {
    padding: 16px;
  }

  .manual-control-panel__inline-fields,
  .manual-path-builder__stats,
  .ownership-import__options,
  .ownership-import__stats {
    grid-template-columns: 1fr;
  }

  .manual-path-builder__head {
    display: grid;
  }

  .manual-path-node--editable {
    grid-template-columns: minmax(0, 1fr);
    width: 100%;
  }

  .manual-path-row__ratio {
    grid-template-columns: 1fr;
  }
}
</style>

