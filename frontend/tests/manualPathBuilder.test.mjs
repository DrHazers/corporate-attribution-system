import assert from 'node:assert/strict'

import {
  buildManualPathPayloads,
  deriveManualPathDisplay,
} from '../src/utils/manualPathBuilder.js'
import { buildControlStructureModel } from '../src/utils/controlStructureAdapter.js'

const defaultPathRows = [{ intermediate_nodes: [] }]
const defaultDisplay = deriveManualPathDisplay({
  paths: defaultPathRows,
  targetCompanyName: 'Shengda Securities Industrial Group Co., Ltd.',
})

assert.equal(defaultDisplay.pathTexts.length, 1)
assert.equal(defaultDisplay.pathCount, 0)
assert.equal(defaultDisplay.pathDepth, null)

const snapshotOnlyDisplay = deriveManualPathDisplay({
  paths: defaultPathRows,
  controllerName: 'Unbound Snapshot Controller',
  targetCompanyName: 'Shengda Securities Industrial Group Co., Ltd.',
})

assert.equal(snapshotOnlyDisplay.hasController, false)
assert.equal(snapshotOnlyDisplay.summary, '')
assert.deepEqual(
  buildManualPathPayloads({
    paths: defaultPathRows,
    controllerName: 'Unbound Snapshot Controller',
    targetCompanyId: 170,
    targetCompanyName: 'Shengda Securities Industrial Group Co., Ltd.',
  }),
  [],
)

const newEntityDisplay = deriveManualPathDisplay({
  paths: defaultPathRows,
  controllerName: 'New Controller Pending Insert',
  allowNameOnlyStart: true,
  targetCompanyName: 'Shengda Securities Industrial Group Co., Ltd.',
})

assert.equal(newEntityDisplay.hasController, true)
assert.equal(
  newEntityDisplay.summary,
  'New Controller Pending Insert → Shengda Securities Industrial Group Co., Ltd.',
)

const pendingNewEntityPayload = buildManualPathPayloads({
  paths: defaultPathRows,
  controllerName: 'New Controller Pending Insert',
  allowNameOnlyStart: true,
  targetCompanyId: 170,
  targetCompanyName: 'Shengda Securities Industrial Group Co., Ltd.',
})

assert.deepEqual(pendingNewEntityPayload[0].entity_ids, [null, 170])

const display = deriveManualPathDisplay({
  paths: [{ intermediate_nodes: [{ name: 'Intermediate Holding Platform' }], path_ratio: '63.5%' }],
  controllerEntityId: 10005,
  controllerName: 'Geode Capital Management',
  targetCompanyName: 'Shengda Securities Industrial Group Co., Ltd.',
})

assert.equal(display.pathCount, 1)
assert.equal(display.pathDepth, 2)
assert.equal(
  display.summary,
  'Geode Capital Management → Intermediate Holding Platform → Shengda Securities Industrial Group Co., Ltd.',
)
assert.equal(display.pathRatios[0], '63.5%')

const changedControllerDisplay = deriveManualPathDisplay({
  paths: [{ intermediate_nodes: [{ name: 'Intermediate Holding Platform' }] }],
  controllerEntityId: 10006,
  controllerName: 'Updated Controller',
  targetCompanyName: 'Shengda Securities Industrial Group Co., Ltd.',
})

assert.equal(
  changedControllerDisplay.summary,
  'Updated Controller → Intermediate Holding Platform → Shengda Securities Industrial Group Co., Ltd.',
)

const payloadPaths = buildManualPathPayloads({
  paths: [{ intermediate_nodes: [], path_ratio: '' }],
  controllerEntityId: 10005,
  controllerName: 'Geode Capital Management',
  targetCompanyId: 170,
  targetCompanyName: 'Shengda Securities Industrial Group Co., Ltd.',
})

assert.deepEqual(payloadPaths[0].entity_ids, [10005, 170])
assert.deepEqual(payloadPaths[0].entity_names, [
  'Geode Capital Management',
  'Shengda Securities Industrial Group Co., Ltd.',
])
assert.equal(payloadPaths[0].entity_names.includes('目标公司'), false)
assert.equal(Object.prototype.hasOwnProperty.call(payloadPaths[0], 'path_ratio'), false)

const ratioPayloadPaths = buildManualPathPayloads({
  paths: [{ intermediate_nodes: [], path_ratio: '40%' }],
  controllerEntityId: 10005,
  controllerName: 'Geode Capital Management',
  targetCompanyId: 170,
  targetCompanyName: 'Shengda Securities Industrial Group Co., Ltd.',
})
assert.equal(ratioPayloadPaths[0].path_ratio, '40%')

const manualRelationship = {
  controller_entity_id: 10005,
  controller_name: 'Geode Capital Management',
  controller_type: 'institution',
  control_type: 'manual_override',
  is_actual_controller: true,
  control_path: [
    {
      path_entity_ids: [10005, 20011, 170],
      path_entity_names: [
        'Geode Capital Management',
        'Intermediate Holding Platform',
        'Shengda Securities Industrial Group Co., Ltd.',
      ],
      path_kind: 'manual_override',
      source_type: 'manual_override',
      path_ratio: '63.5%',
      is_primary: true,
    },
  ],
}

const model = buildControlStructureModel({
  company: {
    id: 170,
    name: 'Shengda Securities Industrial Group Co., Ltd.',
  },
  controlAnalysis: {
    is_manual_effective: true,
    actual_controller: manualRelationship,
    control_relationships: [manualRelationship],
  },
  countryAttribution: {},
  relationshipGraph: {
    target_entity_id: 99999,
    nodes: [],
    edges: [],
  },
})

assert.equal(model.isManualPathDriven, true)
assert.deepEqual(model.keyPathNodeIds, ['10005', '20011', '170'])
assert.equal(model.targetName, 'Shengda Securities Industrial Group Co., Ltd.')
assert.equal(model.multiPathConvergences[0].primaryPath.ratio, '63.5%')

const confirmedRelationship = {
  controller_entity_id: 10005,
  controller_name: 'Geode Capital Management',
  controller_type: 'institution',
  control_type: 'equity',
  result_source: 'manual_confirmed',
  source_type: 'manual_confirmed',
  is_actual_controller: true,
  control_path: [
    {
      path_entity_ids: [10005, 170],
      path_entity_names: [
        'Geode Capital Management',
        'Shengda Securities Industrial Group Co., Ltd.',
      ],
      path_kind: 'manual_confirmed',
      source_type: 'manual_confirmed',
      is_primary: true,
    },
  ],
}

const confirmedModel = buildControlStructureModel({
  company: {
    id: 170,
    name: 'Shengda Securities Industrial Group Co., Ltd.',
  },
  controlAnalysis: {
    is_manual_effective: true,
    result_source: 'manual_confirmed',
    actual_controller: confirmedRelationship,
    control_relationships: [confirmedRelationship],
  },
  countryAttribution: {},
  relationshipGraph: {
    target_entity_id: 170,
    target_company: { name: 'Shengda Securities Industrial Group Co., Ltd.' },
    nodes: [
      { entity_id: 170, name: 'Shengda Securities Industrial Group Co., Ltd.', entity_type: 'company' },
      { entity_id: 200, name: 'Existing Parent', entity_type: 'company' },
    ],
    edges: [
      { id: 1, from_entity_id: 200, to_entity_id: 170, relation_type: 'equity' },
    ],
  },
})

assert.equal(confirmedModel.isManualPathDriven, false)
assert.equal(confirmedModel.primaryPathSource, 'automatic_paths')

const unboundManualRelationship = {
  controller_entity_id: null,
  controller_name: 'Unbound Snapshot Controller',
  controller_type: 'other',
  control_type: 'manual_override',
  result_source: 'manual_override',
  source_type: 'manual_override',
  is_actual_controller: true,
  control_path: [
    {
      path_entity_ids: [null, 170],
      path_entity_names: [
        'Unbound Snapshot Controller',
        'Shengda Securities Industrial Group Co., Ltd.',
      ],
      path_kind: 'manual_override',
      source_type: 'manual_override',
      is_primary: true,
    },
  ],
}

const unboundManualModel = buildControlStructureModel({
  company: {
    id: 170,
    name: 'Shengda Securities Industrial Group Co., Ltd.',
  },
  controlAnalysis: {
    is_manual_effective: true,
    result_source: 'manual_override',
    actual_controller: unboundManualRelationship,
    control_relationships: [unboundManualRelationship],
  },
  countryAttribution: {},
  relationshipGraph: {
    target_entity_id: 170,
    target_company: { name: 'Shengda Securities Industrial Group Co., Ltd.' },
    nodes: [
      { entity_id: 170, name: 'Shengda Securities Industrial Group Co., Ltd.', entity_type: 'company' },
      { entity_id: 200, name: 'Existing Parent', entity_type: 'company' },
    ],
    edges: [
      { id: 1, from_entity_id: 200, to_entity_id: 170, relation_type: 'equity' },
    ],
  },
})

assert.equal(unboundManualModel.actualControllerId, '')
assert.equal(
  unboundManualModel.nodes.some((node) => node.name === 'Unbound Snapshot Controller'),
  false,
)
