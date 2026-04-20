import http from './http'

export function fetchCompanyAnalysisSummary(companyId) {
  return http.get(`/companies/${companyId}/analysis/summary`)
}

export function fetchCompanyIndustryAnalysis(companyId, params = {}) {
  return http.get(`/companies/${companyId}/industry-analysis`, { params })
}

export function fetchBusinessSegmentClassifications(segmentId) {
  return http.get(`/business-segments/${segmentId}/classifications`)
}

export function requestBusinessSegmentLlmAnalysis(segmentId) {
  return http.post(`/business-segments/${segmentId}/classify-with-llm`)
}

export function fetchCompanyControlChain(companyId) {
  return http.get(`/companies/${companyId}/control-chain`)
}

export function fetchCompanyAutomaticControlChain(companyId) {
  return http.get(`/companies/${companyId}/control-chain`, {
    params: { result_layer: 'auto' },
  })
}

export function fetchShareholderEntities(params = {}) {
  return http.get('/shareholders/entities', { params })
}

export function submitManualControlOverride(companyId, payload) {
  return http.post(`/companies/${companyId}/manual-control-override`, payload)
}

export function submitManualControlJudgment(companyId, payload) {
  return http.post(`/companies/${companyId}/manual-control-judgment`, payload)
}

export function restoreManualControlJudgment(companyId, payload = {}) {
  return http.post(`/companies/${companyId}/manual-control-judgment/restore`, payload)
}

export function restoreAutomaticControlResult(companyId, payload = {}) {
  return http.post(`/companies/${companyId}/manual-control-override/restore-auto`, payload)
}
