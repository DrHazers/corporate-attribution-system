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
