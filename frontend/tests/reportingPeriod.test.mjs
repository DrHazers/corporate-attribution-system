import assert from 'node:assert/strict'

import {
  buildIndustryAnalysisPeriodRefreshPayload,
  findHistoryItemForReportingPeriod,
  reportingPeriodDisplayText,
  resolveSelectedReportingPeriod,
  shouldRefreshOuterIndustryAnalysis,
} from '../src/utils/reportingPeriod.js'

assert.equal(
  resolveSelectedReportingPeriod({
    selected_reporting_period: '2025A',
    latest_reporting_period: '2024A',
    available_reporting_periods: ['2024A'],
  }),
  '2025A',
)
assert.equal(
  resolveSelectedReportingPeriod({
    selected_reporting_period: '',
    latest_reporting_period: '2024A',
    available_reporting_periods: ['2023A'],
  }),
  '2024A',
)
assert.equal(
  resolveSelectedReportingPeriod({
    available_reporting_periods: ['2023A'],
  }),
  '2023A',
)
assert.equal(reportingPeriodDisplayText({ available_reporting_periods: [] }), '暂无报告期')

assert.deepEqual(
  buildIndustryAnalysisPeriodRefreshPayload('2025A', '2024A'),
  { reportingPeriod: '2024A', includeHistory: true },
)
assert.equal(buildIndustryAnalysisPeriodRefreshPayload('2025A', '2025A'), null)
assert.equal(buildIndustryAnalysisPeriodRefreshPayload('2025A', '   '), null)

const historyItems = [
  { business_segment_id: 11, reporting_period: '2024A', revenue_ratio: '40.0000' },
  { business_segment_id: 12, reporting_period: '2025A', revenue_ratio: '52.0000' },
]

assert.deepEqual(findHistoryItemForReportingPeriod(historyItems, '2024A'), historyItems[0])
assert.deepEqual(findHistoryItemForReportingPeriod(historyItems, ' 2025A '), historyItems[1])
assert.equal(findHistoryItemForReportingPeriod(historyItems, '2023A'), null)

assert.equal(shouldRefreshOuterIndustryAnalysis('2025A', '2025A'), true)
assert.equal(shouldRefreshOuterIndustryAnalysis('2024A', '2025A'), false)
assert.equal(shouldRefreshOuterIndustryAnalysis('', '2025A'), false)

console.log('reportingPeriod tests passed')
