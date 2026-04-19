<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  fetchCompanyAnalysisSummary,
  fetchCompanyControlChain,
  fetchCompanyIndustryAnalysis,
  restoreAutomaticControlResult,
  submitManualControlOverride,
} from '@/api/analysis'
import { fetchCompanyRelationshipGraph } from '@/api/company'
import BusinessSegmentsTable from '@/components/BusinessSegmentsTable.vue'
import CompanyOverviewCard from '@/components/CompanyOverviewCard.vue'
import ControlRelationsTable from '@/components/ControlRelationsTable.vue'
import ControlSummaryCard from '@/components/ControlSummaryCard.vue'
import IndustrySummaryCard from '@/components/IndustrySummaryCard.vue'
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
const loading = ref(false)
const hasSearched = ref(false)
const pageError = ref('')
const resolvedCompanyId = ref('')
const summaryData = ref(null)
const relationshipGraph = ref(null)
const manualPanelExpanded = ref(false)
const manualSaving = ref(false)
let manualPathKeySeed = 0
let manualNodeKeySeed = 0

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
  actual_controller_entity_id: '',
  actual_controller_name: '',
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

    const normalizedCompanyId = rawValue.trim()
    if (normalizedCompanyId !== resolvedCompanyId.value) {
      manualPanelExpanded.value = false
    }
    await loadCompanyData(normalizedCompanyId)
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
const automaticControlAnalysis = computed(
  () => summaryData.value?.automatic_control_analysis || {},
)
const automaticCountryAttribution = computed(
  () => summaryData.value?.automatic_country_attribution || {},
)
const automaticActualController = computed(
  () => automaticControlAnalysis.value?.actual_controller || null,
)
const currentResultSourceLabel = computed(() => {
  const source = summaryData.value?.control_analysis?.result_source || summaryData.value?.country_attribution?.result_source
  if (source === 'manual_confirmed') {
    return '人工确认自动结果'
  }
  if (source === 'manual_override') {
    return '人工征订生效'
  }
  return '自动分析结果'
})

const manualControllerEntityId = computed(() => {
  const rawValue = String(manualForm.actual_controller_entity_id ?? '').trim()
  return /^\d+$/.test(rawValue) ? Number(rawValue) : null
})

const manualControllerLabel = computed(() => {
  const name = String(manualForm.actual_controller_name ?? '').trim()
  if (name) {
    return name
  }
  if (manualControllerEntityId.value !== null) {
    return `主体 ${manualControllerEntityId.value}`
  }
  return '待填写实际控制人'
})

const manualTargetCompanyName = computed(() => company.value?.name || '当前目标公司')

const manualPathDisplay = computed(() =>
  deriveManualPathDisplay({
    paths: manualForm.manual_paths,
    controllerEntityId: manualControllerEntityId.value,
    controllerName: manualForm.actual_controller_name,
    targetCompanyName: manualTargetCompanyName.value,
  }),
)

const manualHasControllerForPaths = computed(() => manualPathDisplay.value.hasController)

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
  manualForm.actual_controller_entity_id = override?.actual_controller_entity_id
    ? String(override.actual_controller_entity_id)
    : ''
  manualForm.actual_controller_name = override?.actual_controller_name || ''
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

  const snapshotPaths = Array.isArray(override?.manual_result_snapshot?.manual_paths)
    ? override.manual_result_snapshot.manual_paths
    : []
  const overridePathRows = pathRowsFromManualRecords(override?.manual_paths)
  const snapshotPathRows = pathRowsFromManualRecords(snapshotPaths)
  const pathRows = overridePathRows.length
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
    controllerEntityId: manualControllerEntityId.value,
    controllerName: manualForm.actual_controller_name,
    targetCompanyId: company.value?.id ? Number(company.value.id) : null,
    targetCompanyName: manualTargetCompanyName.value,
  })
}

function manualPayload(actionType) {
  const entityIdText = String(manualForm.actual_controller_entity_id ?? '').trim()
  const manualPaths = buildManualPathPayloads()
  return {
    action_type: actionType,
    actual_controller_entity_id: entityIdText ? Number(entityIdText) : null,
    actual_controller_name: String(manualForm.actual_controller_name ?? '').trim() || null,
    actual_control_country: String(manualForm.actual_control_country ?? '').trim() || null,
    manual_control_ratio: String(manualForm.manual_control_ratio ?? '').trim() || null,
    manual_control_strength_label: String(manualForm.manual_control_strength_label ?? '').trim() || null,
    manual_control_path: manualGeneratedPathSummary.value || null,
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
  if (!payload.actual_controller_entity_id && !payload.actual_controller_name && !payload.actual_control_country) {
    ElMessage.warning('请至少填写实际控制人或实际控制国别。')
    return
  }
  manualSaving.value = true
  try {
    await submitManualControlOverride(resolvedCompanyId.value, payload)
    await refreshAfterManualChange('人工征订结果已写回数据库并设为当前生效。')
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
          :manual-effective="manualEffective"
          :manual-panel-expanded="manualPanelExpanded"
          :result-source-label="currentResultSourceLabel"
          @toggle-manual-panel="toggleManualPanel"
        />

        <transition name="manual-panel">
          <section v-if="manualPanelExpanded" class="manual-control-panel">
            <div class="manual-control-panel__head">
              <div>
                <h2>人工征订结果层</h2>
                <p>
                  当前生效：<strong>{{ currentResultSourceLabel }}</strong>。
                  人工征订会写回数据库，自动分析结果保留在下方可查看。
                </p>
              </div>
              <span
                class="manual-control-panel__status"
                :class="manualEffective ? 'manual-control-panel__status--manual' : 'manual-control-panel__status--auto'"
              >
                {{ manualEffective ? '人工征订/确认生效' : '自动结果生效' }}
              </span>
            </div>

            <el-alert
              v-if="manualEffective"
              class="manual-control-panel__alert"
              type="warning"
              show-icon
              :closable="false"
              title="当前实际控制结论由人工征订或人工确认确定"
              :description="`说明：${optionalText(manualOverride?.reason)}；依据：${optionalText(manualOverride?.evidence)}`"
            />

            <div class="manual-control-panel__grid">
              <div class="manual-control-panel__form">
                <el-form label-position="top">
                  <el-form-item label="实际控制人 entity_id">
                    <el-input
                      v-model="manualForm.actual_controller_entity_id"
                      placeholder="可留空，仅征订国别"
                      clearable
                    />
                  </el-form-item>
                  <el-form-item label="实际控制人名称快照">
                    <el-input
                      v-model="manualForm.actual_controller_name"
                      placeholder="未填时按 entity_id 或自动结果补全"
                      clearable
                    />
                  </el-form-item>
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
                      placeholder="例如：根据研究材料确认最终控制人为该主体"
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
                        <h3>控制路径 Path Builder</h3>
                        <p>起点固定为当前征订控制人，终点固定为当前目标公司。</p>
                      </div>
                      <el-button size="small" type="primary" plain @click="addManualPath">
                        添加路径
                      </el-button>
                    </div>

                    <el-alert
                      v-if="!manualHasControllerForPaths"
                      class="manual-path-builder__alert"
                      type="info"
                      show-icon
                      :closable="false"
                      title="填写实际控制人后，路径起点会自动同步为该控制人。"
                    />

                    <div class="manual-path-builder__stats">
                      <div>
                        <span>自动摘要</span>
                        <strong>{{ manualGeneratedPathSummary || '待填写实际控制人后生成' }}</strong>
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
                                clearable
                              />
                              <el-button
                                size="small"
                                link
                                type="danger"
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
                              placeholder="整条路径口径，例如 63.5 或 63.5%"
                              clearable
                            />
                          </el-form-item>
                          <span>
                            表示该路径对控制结论的支持强度，仅针对本路径。可留空；留空时仅表示结构支持关系。
                          </span>
                        </div>
                        <div class="manual-path-row__actions">
                          <el-button size="small" plain @click="addManualIntermediateNode(path)">
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
                            placeholder="例如：63.5 或 63.5%"
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

              <div class="manual-control-panel__auto">
                <h3>自动分析结果</h3>
                <dl>
                  <div>
                    <dt>自动 actual controller</dt>
                    <dd>{{ optionalText(automaticActualController?.controller_name) }}</dd>
                  </div>
                  <div>
                    <dt>自动 actual control country</dt>
                    <dd>{{ optionalText(automaticCountryAttribution?.actual_control_country) }}</dd>
                  </div>
                  <div>
                    <dt>自动 attribution type</dt>
                    <dd>{{ optionalText(automaticCountryAttribution?.attribution_type) }}</dd>
                  </div>
                </dl>
                <el-collapse class="manual-control-panel__collapse">
                  <el-collapse-item title="查看自动结果原始摘要" name="auto">
                    <pre>{{ JSON.stringify({
                      actual_controller: automaticActualController,
                      country_attribution: automaticCountryAttribution,
                    }, null, 2) }}</pre>
                  </el-collapse-item>
                </el-collapse>
              </div>
            </div>
          </section>
        </transition>

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

<style scoped>
.manual-control-panel {
  display: grid;
  gap: 14px;
  margin: 18px 0;
  padding: 18px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 8px;
  background: rgba(248, 251, 253, 0.94);
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

.manual-control-panel__head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.manual-control-panel__head h2,
.manual-control-panel__auto h3 {
  margin: 0;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.manual-control-panel__head p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  line-height: 1.65;
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

.manual-control-panel__grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.8fr);
  gap: 18px;
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

.manual-control-panel__auto {
  display: grid;
  align-content: start;
  gap: 12px;
  min-width: 0;
  padding: 14px;
  border-radius: 8px;
  border: 1px dashed rgba(48, 95, 131, 0.2);
  background: rgba(255, 255, 255, 0.74);
}

.manual-control-panel__auto dl {
  display: grid;
  gap: 10px;
  margin: 0;
}

.manual-control-panel__auto dl > div {
  display: grid;
  grid-template-columns: 148px minmax(0, 1fr);
  gap: 10px;
}

.manual-control-panel__auto dt {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.manual-control-panel__auto dd {
  margin: 0;
  color: var(--brand-ink);
  font-size: 13px;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.manual-control-panel__collapse pre {
  max-height: 280px;
  overflow: auto;
  margin: 0;
  color: #314255;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
}

@media (max-width: 980px) {
  .manual-control-panel__head,
  .manual-control-panel__grid {
    grid-template-columns: 1fr;
  }

  .manual-control-panel__head {
    display: grid;
  }
}

@media (max-width: 560px) {
  .manual-control-panel__inline-fields,
  .manual-path-builder__stats {
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

  .manual-control-panel__auto dl > div {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>
