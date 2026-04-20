import { createRouter, createWebHistory } from 'vue-router'

import CompanyAnalysisView from '@/views/CompanyAnalysisView.vue'
import IndustryWorkbenchView from '@/views/IndustryWorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      alias: '/company-analysis',
      name: 'company-analysis',
      component: CompanyAnalysisView,
    },
    {
      path: '/industry-workbench',
      name: 'industry-workbench',
      component: IndustryWorkbenchView,
    },
  ],
})

export default router
