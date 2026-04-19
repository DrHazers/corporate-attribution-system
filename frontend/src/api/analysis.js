import http from './http'

export function fetchCompanyAnalysisSummary(companyId) {
  return http.get(`/companies/${companyId}/analysis/summary`)
}

export function fetchCompanyIndustryAnalysis(companyId, params = {}) {
  return http.get(`/companies/${companyId}/industry-analysis`, { params })
}

export function fetchCompanyControlChain(companyId) {
  return http.get(`/companies/${companyId}/control-chain`)
}

export function fetchCompanyAutomaticControlChain(companyId) {
  return http.get(`/companies/${companyId}/control-chain`, {
    params: { result_layer: 'auto' },
  })
}

export function submitManualControlOverride(companyId, payload) {
  return http.post(`/companies/${companyId}/manual-control-override`, payload)
}

export function restoreAutomaticControlResult(companyId, payload = {}) {
  return http.post(`/companies/${companyId}/manual-control-override/restore-auto`, payload)
}
