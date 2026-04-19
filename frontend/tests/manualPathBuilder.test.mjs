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
    nodes: [],
    edges: [],
  },
})

assert.equal(confirmedModel.isManualPathDriven, false)
assert.equal(confirmedModel.primaryPathSource, 'automatic_paths')
