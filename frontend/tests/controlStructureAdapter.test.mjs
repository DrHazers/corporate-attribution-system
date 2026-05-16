import assert from 'node:assert/strict'
import { test } from 'node:test'

import { buildControlStructureModel } from '../src/utils/controlStructureAdapter.js'
import { computeControlStructureLayout } from '../src/utils/controlStructureLayout.js'

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

function createThreeShareholderGraph() {
  return {
    target_entity_id: 10,
    target_company: { name: 'Centered Target' },
    nodes: [
      { entity_id: 10, name: 'Centered Target', entity_type: 'company', country: 'US' },
      { entity_id: 1, name: 'Actual Controller', entity_type: 'person', country: 'US' },
      { entity_id: 2, name: 'Public Float - US', entity_type: 'public_float', country: 'US' },
      { entity_id: 3, name: 'Northern Media Inc.', entity_type: 'company', country: 'US' },
      { entity_id: 4, name: 'Helios Long Horizon Fund 4', entity_type: 'fund', country: 'US' },
    ],
    edges: [
      { id: 1, from_entity_id: 1, to_entity_id: 10, relation_type: 'equity', holding_ratio: '55%' },
      { id: 2, from_entity_id: 2, to_entity_id: 10, relation_type: 'equity', holding_ratio: '25%' },
      { id: 3, from_entity_id: 3, to_entity_id: 10, relation_type: 'equity', holding_ratio: '18%' },
      { id: 4, from_entity_id: 4, to_entity_id: 10, relation_type: 'equity', holding_ratio: '12%' },
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

test('layout shows first-layer direct shareholders by default and keeps their upstream collapsed', () => {
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
  const collapsedLayout = computeControlStructureLayout(model, {})
  const collapsedNames = collapsedLayout.nodes.map((node) => node.name)
  const supplementalGroup = collapsedLayout.supplementalGroup
  const intermediateRoot = collapsedLayout.nodes.find((node) => node.name === 'Intermediate HoldCo')
  const collapsedSupplementEdgeVisible = collapsedLayout.edges.some(
    (edge) =>
      edge.controlSubjectName === 'Multi Path Controller' &&
      edge.controlObjectName === 'Intermediate HoldCo',
  )
  const expandedLayout = computeControlStructureLayout(model, {
    350: true,
  })
  const expandedSupplementEdgeVisible = expandedLayout.edges.some(
    (edge) =>
      edge.controlSubjectName === 'Multi Path Controller' &&
      edge.controlObjectName === 'Intermediate HoldCo',
  )

  assert.equal(model.edges.length, 6)
  assert.equal(supplementalGroup.count, 0)
  assert.ok(collapsedNames.includes('Single Controller'))
  assert.ok(collapsedNames.includes('Target Co'))
  assert.ok(collapsedNames.includes('Multi Path Controller'))
  assert.ok(collapsedNames.includes('Joint Controller'))
  assert.ok(collapsedNames.includes('Fallback Controller'))
  assert.ok(intermediateRoot?.expandable)
  assert.equal(intermediateRoot?.expanded, false)
  assert.equal(collapsedSupplementEdgeVisible, false)
  assert.equal(expandedSupplementEdgeVisible, true)
  assert.ok(expandedLayout.nodes.length > collapsedLayout.nodes.length)
})

test('layout centers target and symmetrically arranges three direct shareholders', () => {
  const actualRelationship = {
    controller_entity_id: 1,
    controller_name: 'Actual Controller',
    controller_type: 'person',
    is_actual_controller: true,
    control_type: 'equity_control',
    control_path: [
      {
        path_entity_ids: [1, 10],
        path_entity_names: ['Actual Controller', 'Centered Target'],
        is_primary: true,
      },
    ],
  }

  const model = buildControlStructureModel({
    company: { id: 10, name: 'Centered Target', incorporation_country: 'US' },
    controlAnalysis: {
      actual_controller: actualRelationship,
      control_relationships: [actualRelationship],
    },
    countryAttribution: {},
    relationshipGraph: createThreeShareholderGraph(),
  })
  const layout = computeControlStructureLayout(model, {})
  const target = layout.nodes.find((node) => node.role === 'target')
  const directShareholders = layout.nodes
    .filter((node) => node.isFirstLayerShareholder)
    .sort((left, right) => left.x - right.x)

  assert.equal(directShareholders.length, 3)
  assert.equal(Math.round(target.x), Math.round(layout.width / 2))
  assert.equal(Math.round(directShareholders[1].x), Math.round(target.x))
  assert.equal(
    Math.round(directShareholders[0].x + directShareholders[2].x),
    Math.round(target.x * 2),
  )
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
