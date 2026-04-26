import http from './http'

export function fetchCompanyDetail(companyId) {
  return http.get(`/companies/${companyId}`)
}

export function searchCompanies(query, params = {}) {
  return http.get('/companies/search', {
    params: {
      query,
      limit: params.limit ?? 10,
    },
  })
}

export function fetchCompanyRelationshipGraph(companyId) {
  return http.get(`/companies/${companyId}/relationship-graph`)
}
