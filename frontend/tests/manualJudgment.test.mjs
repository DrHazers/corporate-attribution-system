import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  isManualJudgmentCandidateRow,
  isStructureSignalRow,
} from '../src/utils/manualJudgment.js'

test('manual judgment allows normal candidate rows', () => {
  assert.equal(
    isManualJudgmentCandidateRow({
      controller_entity_id: 101,
      controller_name: 'Candidate A',
      is_leading_candidate: true,
      terminal_suitability: 'suitable_terminal',
    }),
    true,
  )
})

test('manual judgment rejects structure signal rows', () => {
  const row = {
    controller_entity_id: 102,
    controller_name: 'Public Float',
    ownership_pattern_signal: true,
    terminal_identifiability: 'aggregation_like',
  }

  assert.equal(isStructureSignalRow(row), true)
  assert.equal(isManualJudgmentCandidateRow(row), false)
})

test('manual judgment rejects current effective and superseded rows', () => {
  const row = {
    controller_entity_id: 103,
    controller_name: 'Candidate B',
  }

  assert.equal(isManualJudgmentCandidateRow(row, { isCurrentEffective: true }), false)
  assert.equal(isManualJudgmentCandidateRow(row, { isAutomaticSuperseded: true }), false)
})
