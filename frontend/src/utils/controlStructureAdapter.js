const EMPTY_TEXT = '暂无'

export const CONTROL_STRUCTURE_DISPLAY_CONFIG = {
  simpleMaxRelationshipCount: 6,
  simpleMaxNodeCount: 9,
  maxSupportControllers: 8,
  maxComplexSupportControllers: 6,
}

const ENTITY_TYPES = ['company', 'person', 'fund', 'government', 'other']
const SEMANTIC_RELATION_TYPES = new Set([
  'agreement',
  'board_control',
  'voting_right',
  'nominee',
  'vie',
  'agreement_control',
  'mixed_control',
  'joint_control',
])

function safeText(value, fallback = EMPTY_TEXT) {
  if (value === null || value === undefined) {
    return fallback
  }
  const rendered = String(value).trim()
  return rendered || fallback
}

function emptyText(value) {
  return safeText(value, '')
}

function toKey(value) {
  return value === null || value === undefined ? '' : String(value)
}

function sameId(left, right) {
  return toKey(left) !== '' && toKey(left) === toKey(right)
}

function normalizeEntityType(value) {
  const normalized = emptyText(value).toLowerCase()
  return ENTITY_TYPES.includes(normalized) ? normalized : 'other'
}

function normalizeRelationType(value) {
  const normalized = emptyText(value).toLowerCase()
  if (!normalized) {
    return 'equity'
  }
  if (normalized.includes('equity') || normalized === 'direct') {
    return 'equity'
  }
  if (normalized.includes('agreement')) {
    return 'agreement'
  }
  if (normalized.includes('board')) {
    return 'board_control'
  }
  if (normalized.includes('voting')) {
    return 'voting_right'
  }
  if (normalized.includes('nominee')) {
    return 'nominee'
  }
  if (normalized.includes('vie')) {
    return 'vie'
  }
  return normalized
}

function relationTypeOf(relationship) {
  return normalizeRelationType(relationship?.control_type)
}

function isSemanticRelationship(relationship) {
  return SEMANTIC_RELATION_TYPES.has(relationTypeOf(relationship))
}

function ratioScore(relationship) {
  const numeric = Number(relationship?.control_ratio)
  return Number.isNaN(numeric) ? -1 : numeric
}

function buildEntityLookup(relationshipGraph = {}) {
  const lookup = new Map()
  const nodes = Array.isArray(relationshipGraph?.nodes) ? relationshipGraph.nodes : []

  nodes.forEach((node) => {
    const key = toKey(node?.entity_id)
    if (!key) {
      return
    }

    lookup.set(key, {
      id: key,
      name: node.name || node.entity_name || `Entity ${key}`,
      entityType: normalizeEntityType(node.entity_type),
      country: node.country || null,
    })
  })

  return lookup
}

function pickActualController(controlAnalysis = {}) {
  const direct = controlAnalysis?.actual_controller
  if (direct?.controller_entity_id || direct?.controller_name) {
    return direct
  }

  return (controlAnalysis?.control_relationships || []).find(
    (relationship) => relationship?.is_actual_controller,
  )
}

function pickFocusedRelationship(controlAnalysis = {}, actualController = null) {
  if (actualController) {
    return actualController
  }

  const relationships = Array.isArray(controlAnalysis?.control_relationships)
    ? controlAnalysis.control_relationships
    : []
  return relationships[0] || null
}

function relationshipKey(relationship) {
  return [
    relationship?.controller_entity_id ?? relationship?.controller_name ?? '',
    relationship?.control_type ?? '',
    relationship?.control_ratio ?? '',
    relationship?.is_actual_controller ? 'actual' : 'candidate',
  ].join('|')
}

function controllerStep(relationship, fallbackIndex = 0) {
  const id =
    toKey(relationship?.controller_entity_id) ||
    `controller:${fallbackIndex}:${relationship?.controller_name || 'unknown'}`

  return {
    id,
    name: safeText(relationship?.controller_name, `Controller ${fallbackIndex + 1}`),
    entityType: normalizeEntityType(relationship?.controller_type),
  }
}

function targetStep({ company = {}, relationshipGraph = {}, pathItem = null }) {
  const pathIds = Array.isArray(pathItem?.path_entity_ids) ? pathItem.path_entity_ids : []
  const pathNames = Array.isArray(pathItem?.path_entity_names) ? pathItem.path_entity_names : []
  const id =
    toKey(relationshipGraph?.target_entity_id) ||
    toKey(pathIds[pathIds.length - 1]) ||
    toKey(company?.target_entity_id) ||
    `target:${company?.id ?? company?.name ?? 'company'}`

  return {
    id,
    name:
      relationshipGraph?.target_company?.name ||
      company?.name ||
      pathNames[pathNames.length - 1] ||
      'Target Company',
    entityType: 'company',
    country: company?.incorporation_country || null,
  }
}

function getControlPaths(relationship) {
  return Array.isArray(relationship?.control_path) ? relationship.control_path : []
}

function buildPathSteps(pathItem, { entityLookup, controller, target }) {
  const ids = Array.isArray(pathItem?.path_entity_ids) ? pathItem.path_entity_ids : []
  const names = Array.isArray(pathItem?.path_entity_names) ? pathItem.path_entity_names : []
  const count = Math.max(ids.length, names.length)

  if (!count) {
    return [controller, target]
  }

  return Array.from({ length: count }, (_, index) => {
    const id = toKey(ids[index])
    const lookup = id ? entityLookup.get(id) : null
    return {
      id: id || `path:${index}:${names[index] || 'node'}`,
      name: names[index] || lookup?.name || (id ? `Entity ${id}` : `Path Node ${index + 1}`),
      entityType: lookup?.entityType || (index === count - 1 ? 'company' : 'other'),
      country: lookup?.country || null,
    }
  })
}

function normalizePathDirection(steps, { controller, target }) {
  let normalized = [...steps]

  if (normalized.length > 1 && sameId(normalized[0].id, target.id)) {
    normalized = normalized.reverse()
  }
  if (normalized.length > 1 && sameId(normalized[normalized.length - 1].id, controller.id)) {
    normalized = normalized.reverse()
  }

  const controllerIndex = normalized.findIndex((step) => sameId(step.id, controller.id))
  if (controllerIndex > 0) {
    normalized = normalized.slice(controllerIndex)
  }
  if (!normalized.some((step) => sameId(step.id, controller.id))) {
    normalized.unshift(controller)
  }

  const targetIndex = normalized.findIndex((step) => sameId(step.id, target.id))
  if (targetIndex >= 0 && targetIndex < normalized.length - 1) {
    normalized = normalized.slice(0, targetIndex + 1)
  }
  if (!normalized.some((step) => sameId(step.id, target.id))) {
    normalized.push(target)
  }

  return normalized.filter(
    (step, index) => step.id && (index === 0 || !sameId(step.id, normalized[index - 1].id)),
  )
}

function relationshipPath(relationship, context, fallbackIndex = 0) {
  const controller = controllerStep(relationship, fallbackIndex)
  const pathItem = getControlPaths(relationship)[0] || null
  const rawSteps = buildPathSteps(pathItem, {
    entityLookup: context.entityLookup,
    controller,
    target: context.target,
  })

  return {
    relationship,
    pathItem,
    steps: normalizePathDirection(rawSteps, {
      controller,
      target: context.target,
    }),
  }
}

function sortRelationships(left, right) {
  if (Boolean(left?.is_actual_controller) !== Boolean(right?.is_actual_controller)) {
    return left?.is_actual_controller ? -1 : 1
  }
  if (isSemanticRelationship(left) !== isSemanticRelationship(right)) {
    return isSemanticRelationship(left) ? -1 : 1
  }
  const ratioDelta = ratioScore(right) - ratioScore(left)
  if (ratioDelta !== 0) {
    return ratioDelta
  }
  return safeText(left?.controller_name, '').localeCompare(safeText(right?.controller_name, ''))
}

function selectSupportRelationships({ relationships, primaryRelationship, mainPathIds, config }) {
  const primaryKey = relationshipKey(primaryRelationship)
  const candidates = relationships
    .filter((relationship) => relationshipKey(relationship) !== primaryKey)
    .filter((relationship) => !mainPathIds.has(toKey(relationship?.controller_entity_id)))
    .sort(sortRelationships)

  const simpleMode =
    relationships.length <= config.simpleMaxRelationshipCount ||
    mainPathIds.size + candidates.length <= config.simpleMaxNodeCount
  if (simpleMode) {
    return {
      mode: 'simple',
      relationships: candidates.slice(0, config.maxSupportControllers),
      omittedCount: Math.max(0, candidates.length - config.maxSupportControllers),
    }
  }

  const forced = candidates.filter(isSemanticRelationship)
  const forcedKeys = new Set(forced.map(relationshipKey))
  const ordinary = candidates.filter((relationship) => !forcedKeys.has(relationshipKey(relationship)))
  const limit = Math.max(0, config.maxComplexSupportControllers - forced.length)
  const selected = [...forced, ...ordinary.slice(0, limit)]

  return {
    mode: 'complex',
    relationships: selected,
    omittedCount: Math.max(0, candidates.length - selected.length),
  }
}

function makeNode({ step, role, relationship = null, isMainPath = false }) {
  return {
    id: toKey(step.id),
    name: safeText(step.name, '未命名主体'),
    entityType: normalizeEntityType(step.entityType),
    country: step.country || null,
    role,
    isMainPath,
    relationshipKey: relationship ? relationshipKey(relationship) : null,
    controlType: relationship?.control_type || null,
    controlRatio: relationship?.control_ratio ?? null,
  }
}

function makeEdge({
  source,
  target,
  relationship = null,
  relationType = null,
  isKeyPath = false,
  isPrimary = false,
  idPrefix = 'edge',
}) {
  const type = normalizeRelationType(relationType || relationship?.control_type)
  return {
    id: `${idPrefix}:${toKey(source)}->${toKey(target)}`,
    source: toKey(source),
    target: toKey(target),
    relationType: type,
    isKeyPath,
    isPrimary,
    controlRatio: relationship?.control_ratio ?? null,
  }
}

function addNode(nodeMap, node) {
  if (node?.id && !nodeMap.has(node.id)) {
    nodeMap.set(node.id, node)
  }
}

function addEdge(edgeMap, edge) {
  if (edge?.source && edge?.target && !edgeMap.has(edge.id)) {
    edgeMap.set(edge.id, edge)
  }
}

function attachmentForSupportPath(pathSteps, mainPathIds, targetId) {
  const attachment = pathSteps.slice(1).find((step) => mainPathIds.has(toKey(step.id)))
  return attachment?.id || targetId
}

export function buildControlStructureModel({
  company = {},
  controlAnalysis = {},
  countryAttribution = {},
  relationshipGraph = {},
  displayConfig = {},
} = {}) {
  const config = {
    ...CONTROL_STRUCTURE_DISPLAY_CONFIG,
    ...displayConfig,
  }
  const relationships = Array.isArray(controlAnalysis?.control_relationships)
    ? controlAnalysis.control_relationships
    : []
  const actualController = pickActualController(controlAnalysis)
  const focusedRelationship = pickFocusedRelationship(controlAnalysis, actualController)
  const primaryRelationship = actualController || focusedRelationship

  if (!primaryRelationship) {
    return {
      hasDiagram: false,
      placeholderTitle: '暂无可展示的控制结构',
      placeholderDescription: '当前 summary 中尚无可用于生成控制结构图的控制关系。',
      nodes: [],
      edges: [],
      mainPathNodeIds: [],
    }
  }

  const entityLookup = buildEntityLookup(relationshipGraph)
  const firstPathItem = getControlPaths(primaryRelationship)[0] || null
  const target = targetStep({ company, relationshipGraph, pathItem: firstPathItem })
  const context = {
    entityLookup,
    target,
  }
  const primaryPath = relationshipPath(primaryRelationship, context, 0)
  const mainPathIds = new Set(primaryPath.steps.map((step) => toKey(step.id)).filter(Boolean))
  const supportSelection = selectSupportRelationships({
    relationships,
    primaryRelationship,
    mainPathIds,
    config,
  })
  const nodeMap = new Map()
  const edgeMap = new Map()

  primaryPath.steps.forEach((step, index) => {
    const isTarget = sameId(step.id, target.id) || index === primaryPath.steps.length - 1
    const isActual = actualController && sameId(step.id, actualController.controller_entity_id)
    const isFocused =
      !isActual && focusedRelationship && sameId(step.id, focusedRelationship.controller_entity_id)
    const role = isTarget
      ? 'target'
      : isActual
        ? 'actualController'
        : isFocused
          ? 'focused'
          : 'intermediate'

    addNode(
      nodeMap,
      makeNode({
        step: isTarget ? { ...step, entityType: 'company' } : step,
        role,
        relationship: role === 'actualController' ? actualController : null,
        isMainPath: true,
      }),
    )
  })

  primaryPath.steps.forEach((step, index) => {
    const nextStep = primaryPath.steps[index + 1]
    if (!nextStep) {
      return
    }
    addEdge(
      edgeMap,
      makeEdge({
        source: step.id,
        target: nextStep.id,
        relationship: primaryRelationship,
        isKeyPath: true,
        isPrimary: true,
        idPrefix: 'primary',
      }),
    )
  })

  supportSelection.relationships.forEach((relationship, index) => {
    const supportPath = relationshipPath(relationship, context, index + 1)
    const controller = supportPath.steps[0]
    const attachmentId = attachmentForSupportPath(supportPath.steps, mainPathIds, target.id)
    const semantic = isSemanticRelationship(relationship)
    const bridge = semantic
      ? supportPath.steps
          .slice(1, -1)
          .find((step) => !mainPathIds.has(toKey(step.id)))
      : null

    addNode(
      nodeMap,
      makeNode({
        step: controller,
        role:
          focusedRelationship && sameId(controller.id, focusedRelationship.controller_entity_id)
            ? 'focused'
            : 'support',
        relationship,
      }),
    )

    if (bridge) {
      addNode(
        nodeMap,
        makeNode({
          step: bridge,
          role: 'intermediate',
          relationship,
        }),
      )
      addEdge(
        edgeMap,
        makeEdge({
          source: controller.id,
          target: bridge.id,
          relationship,
          isKeyPath: semantic,
          idPrefix: 'support',
        }),
      )
      addEdge(
        edgeMap,
        makeEdge({
          source: bridge.id,
          target: attachmentId,
          relationship,
          isKeyPath: semantic,
          idPrefix: 'support',
        }),
      )
      return
    }

    addEdge(
      edgeMap,
      makeEdge({
        source: controller.id,
        target: attachmentId,
        relationship,
        isKeyPath: semantic,
        idPrefix: 'support',
      }),
    )
  })

  return {
    hasDiagram: true,
    viewMode: 'Control Structure Diagram',
    sourceMode: 'summary-first',
    targetName: target.name,
    actualControllerName: safeText(actualController?.controller_name, EMPTY_TEXT),
    focusedControllerName: safeText(focusedRelationship?.controller_name, EMPTY_TEXT),
    actualControlCountry: safeText(countryAttribution?.actual_control_country, '未识别'),
    attributionType: safeText(countryAttribution?.attribution_type, EMPTY_TEXT),
    nodes: Array.from(nodeMap.values()),
    edges: Array.from(edgeMap.values()),
    mainPathNodeIds: primaryPath.steps.map((step) => toKey(step.id)).filter(Boolean),
    omittedRelationshipCount: supportSelection.omittedCount,
    displayMode: supportSelection.mode,
    legend: {
      entityTypes: ENTITY_TYPES,
      roles: ['target', 'focused', 'actualController'],
      edgeTypes: ['equity', 'agreement', 'board_control', 'voting_right', 'nominee', 'vie', 'key_path'],
    },
  }
}
