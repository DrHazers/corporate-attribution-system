import { createRouter, createWebHistory } from 'vue-router'

import CompanyAnalysisView from '@/views/CompanyAnalysisView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      alias: '/company-analysis',
      name: 'company-analysis',
      component: CompanyAnalysisView,
    },
  ],
})

export default router
