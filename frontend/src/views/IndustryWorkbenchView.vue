<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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

const route = useRoute()
const router = useRouter()

const companyForm = reactive({
  company_name: '',
  company_description: '',
})

const seed = ref(2)
const segmentRows = ref([createWorkbenchSegment(1), createWorkbenchSegment(2)])
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

const chartRows = computed(() => pieChartRows(analysisResult.value?.segments || [], 'revenue_ratio', 6))
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
  const statuses = segments.map((segment) => primaryClassification(segment)?.review_status).filter(Boolean)
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
      value: statuses.filter((status) => ['needs_llm_review', 'conflicted', 'unmapped'].includes(status)).length,
    },
  ]
})

function addWorkbenchSegment() {
  seed.value += 1
  segmentRows.value.push(createWorkbenchSegment(seed.value))
}

function removeWorkbenchSegment(localId) {
  if (segmentRows.value.length === 1) {
    ElMessage.info('至少保留一条业务线用于试算。')
    return
  }
  segmentRows.value = segmentRows.value.filter((item) => item.localId !== localId)
}

function runRuleAnalysis() {
  const hasValidSegment = segmentRows.value.some((segment) => String(segment.segment_name || '').trim())
  if (!hasValidSegment) {
    ElMessage.warning('请至少填写一条业务线名称后再执行规则分析。')
    return
  }
  analysisResult.value = runWorkbenchRuleAnalysis({
    companyName: companyForm.company_name,
    companyDescription: companyForm.company_description,
    segments: segmentRows.value,
  })
  ElMessage.success('已完成临时规则分析。当前结果仅保留在前端工作台，不写入正式数据库。')
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
    all_industry_labels: [
      ...new Set(nextSegments.flatMap((segment) => segment.classification_labels || [])),
    ],
  }
  manualDrawerVisible.value = false
  ElMessage.success('已在工作台内暂存人工征订结果。该结果仅用于本次临时分析展示。')
}

function triggerWorkbenchLlm() {
  ElMessage.info('LLM 分析位已预留。后续可在工作台接入真实模型或临时分析接口。')
}

function goBack() {
  if (route.query.companyId) {
    router.push({
      name: 'company-analysis',
      query: { companyId: route.query.companyId },
    })
    return
  }
  router.push({ name: 'company-analysis' })
}
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div class="page-kicker">Industry Workbench</div>
      <h1 class="page-title">产业分析工作台</h1>
      <p class="page-subtitle">
        用于临时输入公司与业务线结构，先做规则分析、人工征订预演与后续模型辅助位预留。当前不会把结果直接写入正式数据库。
      </p>
      <div class="workbench-header__actions">
        <el-button plain @click="goBack">
          返回公司详情页
        </el-button>
      </div>
    </header>

    <div class="workbench-layout">
      <section class="surface-card workbench-form-card">
        <div class="section-heading">
          <div>
            <h3>基础输入</h3>
            <p>先输入轻量公司信息与多条业务线结构，作为临时分析上下文。</p>
          </div>
        </div>

        <el-form label-position="top">
          <div class="workbench-company-grid">
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
                placeholder="可补充业务模式、行业定位或公司简介，用于辅助规则判断"
              />
            </el-form-item>
          </div>
        </el-form>

        <div class="workbench-segment-head">
          <div>
            <h3>业务线结构输入</h3>
            <p>支持多条业务线录入，当前先做前端临时分析，不写正式表。</p>
          </div>
          <el-button type="primary" plain @click="addWorkbenchSegment">
            添加业务线
          </el-button>
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
              <el-form-item label="segment_name">
                <el-input v-model="segment.segment_name" placeholder="例如：Cloud ERP Platform" />
              </el-form-item>
              <el-form-item label="segment_alias（可选）">
                <el-input v-model="segment.segment_alias" placeholder="例如：Enterprise SaaS" />
              </el-form-item>
              <el-form-item label="segment_type">
                <el-select v-model="segment.segment_type">
                  <el-option label="主营" value="primary" />
                  <el-option label="补充" value="secondary" />
                  <el-option label="新兴" value="emerging" />
                  <el-option label="其他" value="other" />
                </el-select>
              </el-form-item>
              <el-form-item label="reporting_period">
                <el-input v-model="segment.reporting_period" placeholder="例如：2025A" />
              </el-form-item>
              <el-form-item label="revenue_ratio">
                <el-input v-model="segment.revenue_ratio" placeholder="例如：42 或 0.42" />
              </el-form-item>
              <el-form-item label="profit_ratio（可选）">
                <el-input v-model="segment.profit_ratio" placeholder="例如：18 或 0.18" />
              </el-form-item>
            </div>
            <el-form-item label="description（可选）">
              <el-input
                v-model="segment.description"
                type="textarea"
                :rows="3"
                placeholder="补充业务线产品、客户、商业模式或行业描述"
              />
            </el-form-item>
          </article>
        </div>

        <div class="workbench-action-bar">
          <el-button type="primary" @click="runRuleAnalysis">
            规则分析
          </el-button>
          <el-button plain @click="analysisResult && openManualDrawer(analysisResult.segments[0])">
            人工征订
          </el-button>
          <el-button plain @click="triggerWorkbenchLlm">
            LLM分析
          </el-button>
        </div>
      </section>

      <section class="surface-card workbench-result-card">
        <div class="section-heading">
          <div>
            <h3>临时分析结果</h3>
            <p>规则分析后即时展示结构图、分类结果与状态信息。当前结果仅存在于前端工作台状态中。</p>
          </div>
        </div>

        <template v-if="analysisResult">
          <div class="workbench-result-metrics">
            <div v-for="metric in resultMetrics" :key="metric.label" class="workbench-result-metric">
              <span>{{ metric.label }}</span>
              <strong>{{ metric.value }}</strong>
            </div>
          </div>

          <IndustryStructurePieChart :rows="chartRows" metric-label="收入占比" />

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
            <el-table-column label="分类摘要" min-width="240">
              <template #default="{ row }">
                {{ classificationSummary(row) }}
              </template>
            </el-table-column>
            <el-table-column label="状态" min-width="120">
              <template #default="{ row }">
                <el-tag :type="reviewStatusTagType(primaryClassification(row)?.review_status)" effect="plain">
                  {{ reviewStatusLabel(primaryClassification(row)?.review_status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="置信度" min-width="100">
              <template #default="{ row }">
                {{ formatConfidence(primaryClassification(row)?.confidence) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" min-width="180" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openManualDrawer(row)">
                  人工征订
                </el-button>
                <el-button link @click="triggerWorkbenchLlm">
                  LLM分析
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>

        <el-empty
          v-else
          description="尚未运行规则分析"
          :image-size="88"
        >
          <template #description>
            <div class="table-text table-text--muted">
              输入公司与业务线结构后，点击“规则分析”生成临时结果。当前阶段不会写入正式数据库。
            </div>
          </template>
        </el-empty>
      </section>
    </div>

    <el-drawer
      v-model="manualDrawerVisible"
      size="42%"
      :with-header="false"
    >
      <div v-if="selectedWorkbenchSegment" class="workbench-drawer">
        <span class="page-kicker">Manual Override Sandbox</span>
        <h2>{{ selectedWorkbenchSegment.segment_alias || selectedWorkbenchSegment.segment_name }}</h2>
        <p class="workbench-drawer__subtitle">{{ selectedWorkbenchSegment.segment_name }}</p>

        <section class="workbench-drawer__section">
          <h3>当前结果</h3>
          <p><strong>分类摘要：</strong>{{ classificationSummary(selectedWorkbenchSegment) }}</p>
          <p><strong>状态：</strong>{{ reviewStatusLabel(selectedWorkbenchClassification?.review_status) }}</p>
          <p><strong>原因：</strong>{{ reviewReasonLabel(selectedWorkbenchClassification?.review_reason) }}</p>
          <p><strong>mapping_basis：</strong>{{ selectedWorkbenchClassification?.mapping_basis || '暂无' }}</p>
        </section>

        <section class="workbench-drawer__section">
          <h3>人工征订</h3>
          <el-form label-position="top">
            <div class="workbench-manual-grid">
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
              <el-input v-model="manualDraft.mapping_basis" type="textarea" :rows="4" />
            </el-form-item>
          </el-form>
          <el-button type="primary" @click="applyManualWorkbenchOverride">
            应用人工征订
          </el-button>
        </section>

        <section class="workbench-drawer__section">
          <h3>模型辅助分析</h3>
          <el-empty description="模型辅助分析位已预留，后续可接真实 LLM 接口或临时分析接口。" :image-size="72" />
          <el-button plain @click="triggerWorkbenchLlm">
            LLM分析
          </el-button>
        </section>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.workbench-header__actions {
  margin-top: 18px;
}

.workbench-layout {
  display: grid;
  grid-template-columns: minmax(420px, 0.95fr) minmax(0, 1.05fr);
  gap: 20px;
}

.workbench-form-card,
.workbench-result-card {
  padding: 22px;
  border-radius: 24px;
}

.workbench-company-grid,
.workbench-segment-grid,
.workbench-result-metrics,
.workbench-manual-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.workbench-segment-head,
.workbench-action-bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.workbench-segment-list {
  display: grid;
  gap: 14px;
  margin-top: 18px;
}

.workbench-segment-card {
  display: grid;
  gap: 10px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background:
    linear-gradient(180deg, rgba(252, 249, 243, 0.92), rgba(255, 255, 255, 0.88));
}

.workbench-segment-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.workbench-segment-card__head strong,
.workbench-result-metric strong,
.workbench-drawer h2 {
  color: var(--brand-ink);
}

.workbench-result-metrics {
  margin-bottom: 18px;
}

.workbench-result-metric {
  display: grid;
  gap: 8px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(249, 251, 254, 0.84);
}

.workbench-result-metric span {
  color: var(--text-secondary);
  font-size: 12px;
}

.workbench-action-bar {
  margin-top: 18px;
  justify-content: flex-start;
  flex-wrap: wrap;
}

.workbench-drawer {
  display: grid;
  gap: 18px;
}

.workbench-drawer__subtitle {
  margin: -8px 0 0;
  color: var(--text-secondary);
}

.workbench-drawer__section {
  display: grid;
  gap: 10px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(31, 59, 87, 0.08);
  background: rgba(255, 255, 255, 0.82);
}

.workbench-drawer__section h3 {
  margin: 0;
  color: var(--brand-ink);
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
}

.workbench-drawer__section p {
  margin: 0;
  color: #314255;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

@media (max-width: 1120px) {
  .workbench-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .workbench-company-grid,
  .workbench-segment-grid,
  .workbench-result-metrics,
  .workbench-manual-grid {
    grid-template-columns: 1fr;
  }

  .workbench-segment-head,
  .workbench-action-bar {
    display: grid;
  }
}
</style>
