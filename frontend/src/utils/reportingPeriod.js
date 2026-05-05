export function normalizeReportingPeriod(value) {
  const normalized = String(value ?? '').trim()
  return normalized || ''
}

export function resolveSelectedReportingPeriod(industryAnalysis = {}) {
  const availablePeriods = Array.isArray(industryAnalysis?.available_reporting_periods)
    ? industryAnalysis.available_reporting_periods
    : []
  return (
    normalizeReportingPeriod(industryAnalysis?.selected_reporting_period) ||
    normalizeReportingPeriod(industryAnalysis?.latest_reporting_period) ||
    normalizeReportingPeriod(availablePeriods[0]) ||
    ''
  )
}

export function reportingPeriodDisplayText(industryAnalysis = {}) {
  return resolveSelectedReportingPeriod(industryAnalysis) || '暂无报告期'
}

export function buildIndustryAnalysisPeriodRefreshPayload(currentPeriod, nextPeriod) {
  const current = normalizeReportingPeriod(currentPeriod)
  const next = normalizeReportingPeriod(nextPeriod)
  if (!next || next === current) {
    return null
  }
  return {
    reportingPeriod: next,
    includeHistory: true,
  }
}

export function findHistoryItemForReportingPeriod(items = [], reportingPeriod) {
  const target = normalizeReportingPeriod(reportingPeriod)
  if (!target) {
    return null
  }
  return items.find((item) => normalizeReportingPeriod(item?.reporting_period) === target) || null
}

export function shouldRefreshOuterIndustryAnalysis(revisedPeriod, selectedReportingPeriod) {
  const revised = normalizeReportingPeriod(revisedPeriod)
  const selected = normalizeReportingPeriod(selectedReportingPeriod)
  return Boolean(revised && selected && revised === selected)
}
