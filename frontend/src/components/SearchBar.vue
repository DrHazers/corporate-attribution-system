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
  demoIds: {
    type: Array,
    default: () => ['128', '240', '9717', '8', '170'],
  },
})

const emit = defineEmits(['update:modelValue', 'search'])

const inputValue = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

function triggerSearch(value = props.modelValue) {
  emit('update:modelValue', value)
  emit('search')
}
</script>

<template>
  <el-card class="surface-card search-bar-card" shadow="never">
    <div class="search-bar-card__layout">
      <div class="search-bar-card__intro">
        <div class="section-heading">
          <div>
            <h2>企业综合分析页</h2>
            <p>
              输入 <code>company_id</code> 后查询公司总览、控制分析、国别归属、产业分析与明细表格。
            </p>
          </div>
        </div>
      </div>

      <div class="search-bar-card__controls">
        <el-input
          v-model="inputValue"
          clearable
          size="large"
          placeholder="请输入 company_id，例如 128"
          @keyup.enter="triggerSearch()"
        />
        <el-button type="primary" size="large" :loading="loading" @click="triggerSearch()">
          查询
        </el-button>
      </div>
    </div>

    <div class="search-bar-card__examples">
      <span class="search-bar-card__examples-label">推荐演示 ID</span>
      <el-tag
        v-for="demoId in demoIds"
        :key="demoId"
        class="search-bar-card__tag"
        effect="plain"
        @click="triggerSearch(String(demoId))"
      >
        {{ demoId }}
      </el-tag>
    </div>
  </el-card>
</template>

<style scoped>
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
  width: min(520px, 100%);
}

.search-bar-card__controls :deep(.el-input) {
  flex: 1;
}

.search-bar-card__examples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;
  color: var(--text-secondary);
}

.search-bar-card__examples-label {
  font-size: 13px;
  line-height: 32px;
}

.search-bar-card__tag {
  cursor: pointer;
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
  .search-bar-card__controls {
    flex-direction: column;
  }
}
</style>
