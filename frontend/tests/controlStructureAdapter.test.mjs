import assert from 'node:assert/strict'
import { test } from 'node:test'

import { buildControlStructureModel } from '../src/utils/controlStructureAdapter.js'

function createBaseGraph() {
  return {
    target_entity_id: 170,
    target_company: { name: 'Target Co' },
    nodes: [
      { entity_id: 170, name: 'Target Co', entity_type: 'company', country: 'China' },
      { entity_id: 100, name: 'Single Controller', entity_type: 'company', country: 'China' },
      { entity_id: 300, name: 'Multi Path Controller', entity_type: 'company', country: 'China' },
      { entity_id: 350, name: 'Intermediate HoldCo', entity_type: 'company', country: 'China' },
      { entity_id: 400, name: 'Joint Controller', entity_type: 'company', country: 'China' },
      { entity_id: 500, name: 'Fallback Controller', entity_type: 'company', country: 'China' },
    ],
    edges: [
      { id: 1, from_entity_id: 100, to_entity_id: 170, relation_type: 'equity', holding_ratio: '62%' },
      { id: 2, from_entity_id: 300, to_entity_id: 170, relation_type: 'equity', holding_ratio: '35%' },
      { id: 3, from_entity_id: 300, to_entity_id: 350, relation_type: 'equity', holding_ratio: '70%' },
      { id: 4, from_entity_id: 350, to_entity_id: 170, relation_type: 'equity', holding_ratio: '20%' },
      { id: 5, from_entity_id: 400, to_entity_id: 170, relation_type: 'joint_control' },
      { id: 6, from_entity_id: 500, to_entity_id: 170, relation_type: 'equity', holding_ratio: '51%' },
    ],
  }
}

test('renders fallback path when no actual controller is available but country attribution has top path', () => {
  const model = buildControlStructureModel({
    company: {
      id: 170,
      name: 'Target Co',
      incorporation_country: 'China',
    },
    controlAnalysis: {
      control_relationships: [],
    },
    countryAttribution: {
      actual_control_country: 'China',
      attribution_type: 'fallback_incorporation',
      basis: {
        actual_controller_entity_id: 500,
        top_candidates: [{ controller_name: 'Fallback Controller' }],
        top_paths: [
          {
            path_entity_ids: [500, 170],
            path_entity_names: ['Fallback Controller', 'Target Co'],
          },
        ],
      },
    },
    relationshipGraph: createBaseGraph(),
  })

  assert.equal(model.hasDiagram, true)
  assert.equal(model.actualControllerId, '500')
  assert.deepEqual(model.keyPathNodeIds, ['500', '170'])
})

test('renders a single automatic actual controller path', () => {
  const actualRelationship = {
    controller_entity_id: 100,
    controller_name: 'Single Controller',
    controller_type: 'company',
    is_actual_controller: true,
    control_type: 'equity_control',
    control_path: [
      {
        path_entity_ids: [100, 170],
        path_entity_names: ['Single Controller', 'Target Co'],
        is_primary: true,
      },
    ],
  }

  const model = buildControlStructureModel({
    company: { id: 170, name: 'Target Co', incorporation_country: 'China' },
    controlAnalysis: {
      actual_controller: actualRelationship,
      control_relationships: [actualRelationship],
    },
    countryAttribution: {},
    relationshipGraph: createBaseGraph(),
  })

  assert.equal(model.hasDiagram, true)
  assert.equal(model.actualControllerId, '100')
  assert.equal(model.primaryPathSource, 'automatic_paths')
  assert.deepEqual(model.keyPathNodeIds, ['100', '170'])
})

test('captures multi-path convergence for one controller', () => {
  const multiPathRelationship = {
    controller_entity_id: 300,
    controller_name: 'Multi Path Controller',
    controller_type: 'company',
    is_actual_controller: true,
    control_type: 'equity_control',
    control_path: [
      {
        path_entity_ids: [300, 170],
        path_entity_names: ['Multi Path Controller', 'Target Co'],
        path_ratio: '35%',
        is_primary: true,
      },
      {
        path_entity_ids: [300, 350, 170],
        path_entity_names: ['Multi Path Controller', 'Intermediate HoldCo', 'Target Co'],
        path_ratio: '20%',
        is_primary: false,
      },
    ],
  }

  const model = buildControlStructureModel({
    company: { id: 170, name: 'Target Co', incorporation_country: 'China' },
    controlAnalysis: {
      actual_controller: multiPathRelationship,
      control_relationships: [multiPathRelationship],
    },
    countryAttribution: {},
    relationshipGraph: createBaseGraph(),
  })

  assert.equal(model.hasDiagram, true)
  assert.equal(model.multiPathConvergences.length, 1)
  assert.equal(model.multiPathConvergences[0].controllerName, 'Multi Path Controller')
  assert.equal(model.multiPathConvergences[0].pathCount, 2)
  assert.equal(model.multiPathConvergences[0].supplementalPathCount, 1)
})

test('does not force a unique actual controller when relationship is joint control', () => {
  const jointControlRelationship = {
    controller_entity_id: 400,
    controller_name: 'Joint Controller',
    controller_type: 'company',
    control_type: 'joint_control',
    is_actual_controller: false,
    control_path: [
      {
        path_entity_ids: [400, 170],
        path_entity_names: ['Joint Controller', 'Target Co'],
      },
    ],
  }

  const model = buildControlStructureModel({
    company: { id: 170, name: 'Target Co', incorporation_country: 'China' },
    controlAnalysis: {
      control_relationships: [jointControlRelationship],
    },
    countryAttribution: {
      attribution_type: 'fallback_incorporation',
      actual_control_country: 'China',
    },
    relationshipGraph: createBaseGraph(),
  })

  assert.equal(model.hasDiagram, true)
  assert.equal(model.actualControllerId, '')
  assert.equal(model.summaryControllerId, '400')
})

test('switches between manual path and automatic path sources cleanly', () => {
  const manualRelationship = {
    controller_entity_id: 300,
    controller_name: 'Multi Path Controller',
    controller_type: 'company',
    control_type: 'manual_override',
    result_source: 'manual_override',
    is_actual_controller: true,
    control_path: [
      {
        path_entity_ids: [300, 350, 170],
        path_entity_names: ['Multi Path Controller', 'Intermediate HoldCo', 'Target Co'],
        path_kind: 'manual_override',
        source_type: 'manual_override',
        is_primary: true,
      },
    ],
  }
  const automaticRelationship = {
    controller_entity_id: 100,
    controller_name: 'Single Controller',
    controller_type: 'company',
    control_type: 'equity_control',
    result_source: 'automatic',
    is_actual_controller: true,
    control_path: [
      {
        path_entity_ids: [100, 170],
        path_entity_names: ['Single Controller', 'Target Co'],
        is_primary: true,
      },
    ],
  }

  const manualModel = buildControlStructureModel({
    company: { id: 170, name: 'Target Co', incorporation_country: 'China' },
    controlAnalysis: {
      is_manual_effective: true,
      result_source: 'manual_override',
      actual_controller: manualRelationship,
      control_relationships: [manualRelationship],
    },
    countryAttribution: {},
    relationshipGraph: createBaseGraph(),
  })

  const restoredAutomaticModel = buildControlStructureModel({
    company: { id: 170, name: 'Target Co', incorporation_country: 'China' },
    controlAnalysis: {
      result_source: 'automatic',
      actual_controller: automaticRelationship,
      control_relationships: [automaticRelationship],
    },
    countryAttribution: {},
    relationshipGraph: createBaseGraph(),
  })

  assert.equal(manualModel.primaryPathSource, 'manual_paths')
  assert.equal(manualModel.isManualPathDriven, true)
  assert.equal(restoredAutomaticModel.primaryPathSource, 'automatic_paths')
  assert.equal(restoredAutomaticModel.isManualPathDriven, false)
})
