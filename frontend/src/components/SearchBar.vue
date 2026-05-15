<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  loading: {
    type: Boolean,
    default: false,
  },
  searching: {
    type: Boolean,
    default: false,
  },
  results: {
    type: Array,
    default: () => [],
  },
  hasSearched: {
    type: Boolean,
    default: false,
  },
  emptyMessage: {
    type: String,
    default: '',
  },
  demoIds: {
    type: Array,
    default: () => ['128', '240', '9717', '8', '170'],
  },
})

const emit = defineEmits(['update:modelValue', 'search', 'select-company', 'open-import'])

const inputValue = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const showResults = computed(() => props.results.length > 0)
const showEmptyState = computed(
  () => props.hasSearched && !props.searching && !props.results.length && props.emptyMessage,
)

function triggerSearch(value = props.modelValue) {
  emit('update:modelValue', value)
  emit('search', String(value ?? ''))
}

function handleSelectCompany(company) {
  emit('select-company', company)
}

function openImportCenter() {
  emit('open-import')
}
</script>

<template>
  <el-card class="analysis-query-card" shadow="never">
    <div class="query-card-header">
      <h2>企业综合分析</h2>
      <p>选择或检索分析对象，查看控制链、国别归属与产业结构分析结果。</p>
    </div>

    <div class="query-toolbar">
      <el-input
        v-model="inputValue"
        clearable
        size="large"
        placeholder="请输入公司名称、股票代码或 /ID，例如 /128"
        @keyup.enter="triggerSearch()"
      />
      <el-button type="primary" class="query-button" :loading="searching" @click="triggerSearch()">
        查询
      </el-button>
      <el-button class="import-button" plain @click="openImportCenter">
        数据导入
      </el-button>
    </div>

    <div class="quick-sample-row">
      <span class="quick-sample-label">快捷样本</span>
      <button
        v-for="demoId in demoIds"
        :key="demoId"
        type="button"
        class="quick-sample-chip"
        @click="triggerSearch(`/${demoId}`)"
      >
        /{{ demoId }}
      </button>
    </div>

    <div
      v-if="searching || showResults || showEmptyState"
      v-loading="searching"
      class="search-bar-card__results"
    >
      <div v-if="showResults" class="search-result-list">
        <button
          v-for="company in results"
          :key="company.id"
          type="button"
          class="search-result-item"
          :disabled="loading"
          @click="handleSelectCompany(company)"
        >
          <div class="search-result-item__head">
            <strong>{{ company.name }}</strong>
            <span>ID: {{ company.id }}</span>
          </div>
          <div class="search-result-item__meta">
            <span>股票代码：{{ company.stock_code || '暂无' }}</span>
            <span>注册地：{{ company.incorporation_country || '暂无' }}</span>
            <span>上市地：{{ company.listing_country || '暂无' }}</span>
          </div>
          <div class="search-result-item__sub">
            总部：{{ company.headquarters || '暂无' }}
          </div>
        </button>
      </div>

      <el-empty
        v-else-if="showEmptyState"
        :description="emptyMessage"
        :image-size="72"
      />
    </div>
  </el-card>
</template>

<style scoped>
.analysis-query-card {
  border: 1px solid #e5ebf2;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}

.analysis-query-card :deep(.el-card__body) {
  display: grid;
  gap: 0;
  padding: 22px 24px 20px;
}

.query-card-header h2 {
  margin: 0;
  color: #1f3a5b;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", Georgia, serif;
  font-size: 23px;
  font-weight: 700;
  line-height: 1.35;
}

.query-card-header p {
  margin: 6px 0 0;
  color: #6f7f92;
  font-size: 14px;
  line-height: 1.7;
}

.query-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 18px;
}

.query-toolbar :deep(.el-input) {
  width: 560px;
  max-width: min(640px, 100%);
}

.query-button,
.import-button {
  height: 38px;
  border-radius: 6px;
  font-weight: 600;
}

.import-button {
  border-color: #dfe7f0;
  background: #fff;
  color: #56677d;
}

.quick-sample-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  color: #7b8794;
  font-size: 13px;
}

.quick-sample-label {
  margin-right: 4px;
  color: #7b8794;
}

.quick-sample-chip {
  border: 1px solid #dfe7f0;
  border-radius: 999px;
  background: #f8fafc;
  color: #4f6680;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
  padding: 4px 10px;
  transition:
    background-color 0.16s ease,
    border-color 0.16s ease,
    color 0.16s ease;
}

.quick-sample-chip:hover,
.quick-sample-chip:focus-visible {
  border-color: #cfdbe8;
  background: #eef4fb;
  color: #244765;
  outline: none;
}

.search-bar-card__results {
  min-height: 48px;
  padding-top: 14px;
}

.search-result-list {
  display: grid;
  gap: 10px;
}

.search-result-item {
  display: grid;
  gap: 8px;
  width: 100%;
  padding: 14px 16px;
  border: 1px solid rgba(31, 59, 87, 0.1);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.92);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.search-result-item:hover:not(:disabled) {
  border-color: rgba(48, 95, 131, 0.28);
  box-shadow: 0 10px 20px rgba(31, 59, 87, 0.08);
  transform: translateY(-1px);
}

.search-result-item:disabled {
  cursor: wait;
  opacity: 0.72;
}

.search-result-item__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.search-result-item__head strong {
  color: var(--brand-ink);
  font-size: 15px;
  line-height: 1.45;
}

.search-result-item__head span,
.search-result-item__sub {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.55;
}

.search-result-item__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: #40546a;
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .analysis-query-card :deep(.el-card__body) {
    padding: 18px;
  }

  .query-toolbar {
    flex-wrap: wrap;
  }

  .query-toolbar :deep(.el-input) {
    width: 100%;
    max-width: none;
  }

  .query-button,
  .import-button {
    flex: 1 1 140px;
  }

  .search-result-item__head {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
