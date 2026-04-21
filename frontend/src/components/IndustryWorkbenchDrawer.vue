<script setup>
import { computed } from 'vue'

import IndustryWorkbenchContent from '@/components/IndustryWorkbenchContent.vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
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
})

const emit = defineEmits(['update:modelValue'])

const drawerVisible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
</script>

<template>
  <el-drawer
    v-model="drawerVisible"
    size="72%"
    :with-header="false"
    class="industry-workbench-drawer"
    modal-class="industry-workbench-drawer__mask"
    append-to-body
    :destroy-on-close="false"
  >
    <IndustryWorkbenchContent
      mode="drawer"
      :company="company"
      :industry-analysis="industryAnalysis"
      :company-id="companyId"
      @close="drawerVisible = false"
    />
  </el-drawer>
</template>

<style scoped>
:global(.industry-workbench-drawer__mask) {
  background: rgba(11, 20, 31, 0.58);
  backdrop-filter: blur(2px);
}

:deep(.industry-workbench-drawer) {
  width: min(1440px, 72vw) !important;
  max-width: calc(100vw - 24px);
  min-width: 920px;
  box-shadow: -24px 0 52px rgba(15, 30, 46, 0.22);
}

:deep(.industry-workbench-drawer .el-drawer__body) {
  padding: 20px;
  background:
    radial-gradient(circle at top right, rgba(225, 211, 188, 0.22), transparent 24%),
    linear-gradient(180deg, rgba(249, 247, 243, 0.98), rgba(255, 255, 255, 0.96));
}

@media (max-width: 1200px) {
  :deep(.industry-workbench-drawer) {
    min-width: 0;
    width: min(96vw, 1440px) !important;
  }
}
</style>
