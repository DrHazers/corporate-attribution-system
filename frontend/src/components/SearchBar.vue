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

const emit = defineEmits(['update:modelValue', 'search', 'select-company'])

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
</script>

<template>
  <el-card class="surface-card search-bar-card" shadow="never">
    <div class="search-bar-card__layout">
      <div class="search-bar-card__intro">
        <div class="section-heading">
          <div>
            <h2>企业综合分析</h2>
            <p>
              可按公司名称、股票代码搜索企业；如需按 ID 精确查询，可输入 <code>/ID</code>。
              系统将展示控制链、国别归属与产业结构分析结果。
            </p>
          </div>
        </div>
      </div>

      <div class="search-bar-card__controls">
        <el-input
          v-model="inputValue"
          clearable
          size="large"
          placeholder="输入公司名称、股票代码，或 /ID 精确查询"
          @keyup.enter="triggerSearch()"
        />
        <el-button type="primary" size="large" :loading="searching" @click="triggerSearch()">
          查询
        </el-button>
      </div>
    </div>

    <div class="search-bar-card__hint">
      按 ID 精确查询请使用 <code>/ID</code>，例如 <code>/128</code>。
    </div>

    <div class="search-bar-card__examples">
      <span class="search-bar-card__examples-label">推荐演示 ID</span>
      <el-tag
        v-for="demoId in demoIds"
        :key="demoId"
        class="search-bar-card__tag"
        effect="plain"
        @click="triggerSearch(`/${demoId}`)"
      >
        /{{ demoId }}
      </el-tag>
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
.search-bar-card {
  display: grid;
  gap: 14px;
}

.search-bar-card__layout {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.search-bar-card__intro {
  flex: 1;
  min-width: 0;
}

.search-bar-card__controls {
  display: flex;
  gap: 12px;
  width: min(560px, 100%);
}

.search-bar-card__controls :deep(.el-input) {
  flex: 1;
}

.search-bar-card__hint {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.search-bar-card__examples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--text-secondary);
}

.search-bar-card__examples-label {
  font-size: 13px;
  line-height: 32px;
}

.search-bar-card__tag {
  cursor: pointer;
}

.search-bar-card__results {
  min-height: 48px;
  padding-top: 4px;
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

@media (max-width: 980px) {
  .search-bar-card__layout {
    flex-direction: column;
    align-items: stretch;
  }

  .search-bar-card__controls {
    width: 100%;
  }
}

@media (max-width: 640px) {
  .search-bar-card__controls,
  .search-result-item__head {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
