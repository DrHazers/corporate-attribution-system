import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  __controlRelationsMergeTestUtils,
  mergeControlRelationRows,
} from '../src/utils/controlRelationsMerge.js'

const manualJudgmentRow = {
  id: -10,
  controller_entity_id: 101,
  controller_name: 'Controller A',
  controller_type: 'company',
  control_type: 'equity_control',
  control_ratio: '63.5',
  source_type: 'manual_judgment',
  result_source: 'manual_judgment',
  is_manual_effective: true,
  is_current_effective: true,
  is_actual_controller: true,
  control_path: [
    {
      path_entity_ids: [101, 200],
      path_entity_names: ['Controller A', 'Target Co'],
      source_type: 'manual_judgment',
    },
  ],
}

const automaticSameSubjectRow = {
  id: 20,
  controller_entity_id: 101,
  controller_name: 'Controller A',
  controller_type: 'company',
  control_type: 'direct_equity_control',
  control_ratio: '63.5',
  source_type: 'automatic',
  is_manual_effective: false,
  automatic_result_superseded: true,
  automatic_is_actual_controller: true,
  is_actual_controller: false,
  control_path: [
    {
      path_entity_ids: [101, 200],
      path_entity_names: ['Controller A', 'Target Co'],
      source_type: 'automatic',
    },
  ],
}

test('merges manual judgment row with same-subject automatic actual reference', () => {
  const rows = mergeControlRelationRows([manualJudgmentRow, automaticSameSubjectRow])

  assert.equal(rows.length, 1)
  assert.equal(rows[0].controller_entity_id, 101)
  assert.equal(rows[0]._hasMergedAutoReference, true)
  assert.equal(rows[0]._autoReferenceRelationship.id, 20)
  assert.equal(rows[0]._autoReferenceIsSamePath, true)
})

test('merges same-subject automatic reference even when it is not flagged as original actual controller', () => {
  const automaticReference = {
    ...automaticSameSubjectRow,
    automatic_is_actual_controller: false,
  }
  const rows = mergeControlRelationRows([manualJudgmentRow, automaticReference])

  assert.equal(rows.length, 1)
  assert.equal(rows[0]._hasMergedAutoReference, true)
})

test('keeps separate rows when same-subject automatic row was not superseded and no manual row exists', () => {
  const automaticCandidate = {
    ...automaticSameSubjectRow,
    automatic_result_superseded: false,
    automatic_is_actual_controller: false,
    is_actual_controller: true,
    controller_status: 'actual_controller',
  }
  const rows = mergeControlRelationRows([manualJudgmentRow, automaticCandidate])

  assert.equal(rows.length, 1)
  assert.equal(rows[0]._secondaryRelationships.length, 1)
})

test('merges same-name same-type rows when entity ids differ but semantics match', () => {
  const mismatchedIdAuto = {
    ...automaticSameSubjectRow,
    controller_entity_id: 202,
    controller_name: manualJudgmentRow.controller_name,
    controller_type: manualJudgmentRow.controller_type,
  }

  assert.equal(
    __controlRelationsMergeTestUtils.canMergeManualJudgmentWithAutoReference(
      manualJudgmentRow,
      mismatchedIdAuto,
    ).merge,
    true,
  )
})

test('keeps separate rows for different subjects', () => {
  const differentAuto = {
    ...automaticSameSubjectRow,
    controller_entity_id: 999,
    controller_name: 'Different Controller',
  }
  const rows = mergeControlRelationRows([manualJudgmentRow, differentAuto])

  assert.equal(rows.length, 2)
})

test('keeps separate rows for conflicting type or ratio', () => {
  const typeConflict = {
    ...automaticSameSubjectRow,
    control_type: 'board_control',
  }
  const ratioConflict = {
    ...automaticSameSubjectRow,
    control_ratio: '30',
  }

  assert.equal(
    __controlRelationsMergeTestUtils.canMergeManualJudgmentWithAutoReference(
      manualJudgmentRow,
      typeConflict,
    ).merge,
    false,
  )
  assert.equal(
    __controlRelationsMergeTestUtils.canMergeManualJudgmentWithAutoReference(
      manualJudgmentRow,
      ratioConflict,
    ).merge,
    false,
  )
})

test('merges same-subject automatic reference with supplemental path semantics', () => {
  const supplementalAuto = {
    ...automaticSameSubjectRow,
    control_path: [
      {
        path_entity_ids: [101, 150, 200],
        path_entity_names: ['Controller A', 'Intermediate', 'Target Co'],
        source_type: 'automatic',
      },
    ],
  }
  const rows = mergeControlRelationRows([manualJudgmentRow, supplementalAuto])

  assert.equal(rows.length, 1)
  assert.equal(rows[0]._hasMergedAutoReference, true)
  assert.equal(rows[0]._autoReferenceIsSamePath, false)
  assert.equal(rows[0]._autoReferencePathText, 'Controller A -> Intermediate -> Target Co')
})

test('keeps one primary row when manual result and same-subject automatic rows coexist', () => {
  const rows = mergeControlRelationRows([
    manualJudgmentRow,
    automaticSameSubjectRow,
    {
      ...automaticSameSubjectRow,
      id: 21,
      automatic_result_superseded: false,
      is_direct_controller: true,
      control_tier: 'direct',
    },
  ])

  assert.equal(rows.length, 1)
  assert.equal(rows[0].controller_entity_id, 101)
  assert.equal(rows[0]._secondaryRelationships.length, 2)
  assert.equal(rows[0].is_direct_controller, true)
  assert.equal(rows[0]._hasMergedAutoReference, true)
})

test('keeps one primary row for same-subject automatic rows and prefers actual row', () => {
  const rows = mergeControlRelationRows([
    {
      id: 30,
      controller_entity_id: 201,
      controller_name: 'Controller B',
      controller_type: 'company',
      control_type: 'equity_control',
      control_ratio: '55',
      source_type: 'automatic',
      is_actual_controller: false,
      is_direct_controller: true,
      control_tier: 'direct',
    },
    {
      id: 31,
      controller_entity_id: 201,
      controller_name: 'Controller B',
      controller_type: 'company',
      control_type: 'equity_control',
      control_ratio: '55',
      source_type: 'automatic',
      is_actual_controller: true,
      controller_status: 'actual_controller',
      control_tier: 'ultimate',
    },
  ])

  assert.equal(rows.length, 1)
  assert.equal(rows[0].id, 31)
  assert.equal(rows[0].is_direct_controller, true)
  assert.equal(rows[0]._secondaryRelationships.length, 1)
})
