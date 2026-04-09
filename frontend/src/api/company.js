import http from './http'

export function fetchCompanyDetail(companyId) {
  return http.get(`/companies/${companyId}`)
}

export function fetchCompanyRelationshipGraph(companyId) {
  return http.get(`/companies/${companyId}/relationship-graph`)
}
