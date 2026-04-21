<script setup>
import { useRoute, useRouter } from 'vue-router'

import IndustryWorkbenchContent from '@/components/IndustryWorkbenchContent.vue'

const route = useRoute()
const router = useRouter()

function handleClose() {
  if (window.history.length > 1) {
    router.back()
    return
  }
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
    <IndustryWorkbenchContent mode="page" @close="handleClose" />
  </div>
</template>
