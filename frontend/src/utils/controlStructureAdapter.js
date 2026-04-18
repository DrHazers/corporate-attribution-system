const EMPTY_TEXT = 'N/A'

export const CONTROL_STRUCTURE_DISPLAY_CONFIG = {
  maxAutoExpandedKeyPathDepth: 8,
}

const ENTITY_TYPES = ['company', 'person', 'fund', 'government', 'other']
const SEMANTIC_RELATION_TYPES = new Set([
  'agreement',
  'agreement_control',
  'board_control',
  'voting_right',
  'nominee',
  'vie',
  'vie_control',
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

function isSemanticRelationType(value) {
  return SEMANTIC_RELATION_TYPES.has(normalizeRelationType(value))
}

function ratioFromValue(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const numeric = Number(value)
  return Number.isNaN(numeric) ? null : numeric
}

function normalizedRatioForComparison(value) {
  const numeric = ratioFromValue(value)
  if (numeric === null) {
    return -1
  }
  return numeric > 1 ? numeric / 100 : numeric
}

function ratioFromEdge(edge = {}) {
  return (
    ratioFromValue(edge?.holding_ratio) ??
    ratioFromValue(edge?.control_ratio) ??
    ratioFromValue(edge?.numeric_factor)
  )
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
      name: safeText(node?.name || node?.entity_name, `Entity ${key}`),
      entityType: normalizeEntityType(node?.entity_type),
      country: node?.country || null,
      raw: node,
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

function pickSummaryRelationship(controlAnalysis = {}, actualController = null) {
  return actualController || pickFocusedRelationship(controlAnalysis, actualController)
}

function getControlPaths(relationship) {
  return Array.isArray(relationship?.control_path) ? relationship.control_path : []
}

function controllerStep(relationship, fallbackIndex = 0) {
  const id =
    toKey(relationship?.controller_entity_id) ||
    `controller:${fallbackIndex}:${relationship?.controller_name || 'unknown'}`

  return {
    id,
    name: safeText(relationship?.controller_name, `Controller ${fallbackIndex + 1}`),
    entityType: normalizeEntityType(relationship?.controller_type),
    country: relationship?.country || null,
  }
}

function targetStep({ company = {}, relationshipGraph = {}, pathItem = null }) {
  const pathIds = Array.isArray(pathItem?.path_entity_ids) ? pathItem.path_entity_ids : []
  const pathNames = Array.isArray(pathItem?.path_entity_names) ? pathItem.path_entity_names : []

  const id =
    toKey(relationshipGraph?.target_entity_id) ||
    toKey(pathIds[pathIds.length - 1]) ||
    toKey(company?.target_entity_id) ||
    toKey(company?.id) ||
    'target-company'

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

function relationshipPaths(relationship, context, fallbackIndex = 0) {
  const controller = controllerStep(relationship, fallbackIndex)
  const paths = getControlPaths(relationship)

  if (!paths.length) {
    return [relationshipPath(relationship, context, fallbackIndex)]
  }

  return paths.map((pathItem) => ({
    relationship,
    pathItem,
    steps: normalizePathDirection(
      buildPathSteps(pathItem, {
        entityLookup: context.entityLookup,
        controller,
        target: context.target,
      }),
      {
        controller,
        target: context.target,
      },
    ),
  }))
}

function pathScore(pathItem = {}) {
  return (
    ratioFromValue(pathItem?.path_score_pct) ??
    ratioFromValue(pathItem?.path_score) ??
    null
  )
}

function buildPathTextFromSteps(steps = []) {
  return steps.map((step) => safeText(step?.name, `Entity ${step?.id}`)).filter(Boolean).join(' → ')
}

function pathKind(path = {}) {
  return path.steps.length <= 2 ? 'direct' : 'indirect'
}

function buildPathDescriptor(path = {}, index = 0) {
  const kind = pathKind(path)
  return {
    index,
    kind,
    kindLabel: kind === 'direct' ? '直接路径' : '间接路径',
    text: buildPathTextFromSteps(path.steps),
    score: pathScore(path.pathItem),
    nodeCount: path.steps.length,
  }
}

function buildMultiPathConvergenceMetadata(relationships = [], context) {
  return relationships
    .map((relationship, index) => {
      const controllerId = toKey(relationship?.controller_entity_id)
      if (!controllerId) {
        return null
      }

      const paths = relationshipPaths(relationship, context, index).filter(
        (path) => path.steps.length >= 2,
      )
      if (paths.length < 2) {
        return null
      }

      const directPaths = paths.filter((path) => pathKind(path) === 'direct')
      const indirectPaths = paths.filter((path) => pathKind(path) === 'indirect')
      if (!directPaths.length || !indirectPaths.length) {
        return null
      }

      const descriptors = paths.map((path, pathIndex) => buildPathDescriptor(path, pathIndex))
      const primaryPath = descriptors[0]
      const supplementalPaths = descriptors.slice(1)

      return {
        nodeId: controllerId,
        controllerName: safeText(relationship?.controller_name, `Entity ${controllerId}`),
        pathCount: descriptors.length,
        directPathCount: directPaths.length,
        indirectPathCount: indirectPaths.length,
        supplementalPathCount: supplementalPaths.length,
        hasDirectAndIndirect: true,
        primaryPath,
        supplementalPaths,
        summary: '同一主体同时存在直接路径与间接路径，图中仅突出主解释路径。',
      }
    })
    .filter(Boolean)
}

function fallbackPathFromCountryAttribution(countryAttribution = {}, entityLookup, target) {
  const basis = countryAttribution?.basis || {}
  const topPaths = Array.isArray(basis?.top_paths) ? basis.top_paths : []
  const pathItem = topPaths[0]
  const controllerId = toKey(basis?.actual_controller_entity_id)

  if (!pathItem || !controllerId) {
    return []
  }

  const lookup = entityLookup.get(controllerId)
  const controller = {
    id: controllerId,
    name: basis?.top_candidates?.[0]?.controller_name || lookup?.name || `Entity ${controllerId}`,
    entityType: lookup?.entityType || 'other',
    country: lookup?.country || null,
  }

  return normalizePathDirection(
    buildPathSteps(pathItem, {
      entityLookup,
      controller,
      target,
    }),
    { controller, target },
  )
}

function pairKey(sourceId, targetId) {
  return `${toKey(sourceId)}->${toKey(targetId)}`
}

function edgePriority(edge = {}) {
  let score = 0
  if (edge.isPrimary) {
    score += 100
  }
  if (edge.isKeyPath) {
    score += 30
  }
  if (isSemanticRelationType(edge.relationType)) {
    score += 10
  }
  if (!edge.isVirtual) {
    score += 2
  }
  score += normalizedRatioForComparison(edge.controlRatio)
  return score
}

function mergeUniqueStrings(left = [], right = []) {
  return Array.from(new Set([...left, ...right].filter(Boolean)))
}

function addCanonicalNode(nodeMap, nodeLike, extra = {}) {
  const id = toKey(nodeLike?.id)
  if (!id) {
    return
  }

  const existing = nodeMap.get(id)
  const next = {
    id,
    name: safeText(nodeLike?.name, existing?.name || `Entity ${id}`),
    entityType: normalizeEntityType(nodeLike?.entityType || existing?.entityType),
    country: nodeLike?.country || existing?.country || null,
    isActualController: Boolean(extra.isActualController || existing?.isActualController),
    isFocused: Boolean(extra.isFocused || existing?.isFocused),
    isDirectUpstream: Boolean(extra.isDirectUpstream || existing?.isDirectUpstream),
    isSecondLayerCandidate: Boolean(extra.isSecondLayerCandidate || existing?.isSecondLayerCandidate),
    isKeyPath: Boolean(extra.isKeyPath || existing?.isKeyPath),
    keyPathIndex:
      extra.keyPathIndex ?? existing?.keyPathIndex ?? (extra.isKeyPath ? Number.MAX_SAFE_INTEGER : null),
    bestDownstreamRatio:
      extra.bestDownstreamRatio ?? existing?.bestDownstreamRatio ?? null,
    role: extra.role || existing?.role || 'support',
  }

  if (existing) {
    if (
      existing.keyPathIndex !== null &&
      next.keyPathIndex !== null &&
      existing.keyPathIndex < next.keyPathIndex
    ) {
      next.keyPathIndex = existing.keyPathIndex
    }

    if (normalizedRatioForComparison(existing.bestDownstreamRatio) > normalizedRatioForComparison(next.bestDownstreamRatio)) {
      next.bestDownstreamRatio = existing.bestDownstreamRatio
    }

    if (existing.role === 'target' || existing.role === 'actualController') {
      next.role = existing.role
    }
    if (extra.role === 'target' || extra.role === 'actualController') {
      next.role = extra.role
    }
  }

  if (next.isActualController) {
    next.role = 'actualController'
  } else if (next.role !== 'target' && next.isFocused) {
    next.role = 'focused'
  } else if (next.role !== 'target' && next.role !== 'actualController' && next.isDirectUpstream) {
    next.role = 'direct'
  }

  nodeMap.set(id, next)
}

function addCanonicalEdge(edgeMap, edgeLike = {}) {
  const source = toKey(edgeLike?.source)
  const target = toKey(edgeLike?.target)
  if (!source || !target) {
    return
  }

  const key = pairKey(source, target)
  const candidate = {
    id: edgeLike?.id || key,
    source,
    target,
    relationType: normalizeRelationType(edgeLike?.relationType),
    relationTypes: Array.isArray(edgeLike?.relationTypes)
      ? edgeLike.relationTypes.map((item) => normalizeRelationType(item))
      : [normalizeRelationType(edgeLike?.relationType)],
    controlRatio: edgeLike?.controlRatio ?? null,
    isKeyPath: Boolean(edgeLike?.isKeyPath),
    isPrimary: Boolean(edgeLike?.isPrimary),
    isVirtual: Boolean(edgeLike?.isVirtual),
    origin: edgeLike?.origin || 'graph',
  }

  const existing = edgeMap.get(key)
  if (!existing) {
    edgeMap.set(key, candidate)
    return
  }

  const merged = edgePriority(candidate) > edgePriority(existing) ? { ...existing, ...candidate } : { ...candidate, ...existing }
  merged.id = existing.id || candidate.id || key
  merged.isKeyPath = existing.isKeyPath || candidate.isKeyPath
  merged.isPrimary = existing.isPrimary || candidate.isPrimary
  merged.isVirtual = existing.isVirtual && candidate.isVirtual
  merged.relationTypes = mergeUniqueStrings(existing.relationTypes, candidate.relationTypes)
  merged.relationType =
    edgePriority(candidate) > edgePriority(existing) ? candidate.relationType : existing.relationType

  if (
    normalizedRatioForComparison(candidate.controlRatio) >
    normalizedRatioForComparison(existing.controlRatio)
  ) {
    merged.controlRatio = candidate.controlRatio
  } else {
    merged.controlRatio = existing.controlRatio
  }

  edgeMap.set(key, merged)
}

function addGraphNodes(nodeMap, entityLookup) {
  entityLookup.forEach((entity) => {
    addCanonicalNode(nodeMap, entity)
  })
}

function addGraphEdges(edgeMap, relationshipGraph = {}) {
  const edges = Array.isArray(relationshipGraph?.edges) ? relationshipGraph.edges : []

  edges.forEach((edge, index) => {
    addCanonicalEdge(edgeMap, {
      id: toKey(edge?.structure_id) || toKey(edge?.id) || `graph:${index}`,
      source: edge?.from_entity_id,
      target: edge?.to_entity_id,
      relationType: edge?.relation_type || edge?.control_type,
      controlRatio: ratioFromEdge(edge),
      isVirtual: false,
      origin: 'graph',
    })
  })
}

function applyRelationshipPaths({
  relationships,
  context,
  nodeMap,
  edgeMap,
  actualControllerId,
  focusedControllerId,
  keyPathPairKeys,
  keyPathNodeIndex,
}) {
  relationships.forEach((relationship, index) => {
    const path = relationshipPath(relationship, context, index)
    const relationshipControllerId = toKey(relationship?.controller_entity_id)
    const isActualRelationship = actualControllerId && sameId(relationshipControllerId, actualControllerId)
    const isFocusedRelationship = focusedControllerId && sameId(relationshipControllerId, focusedControllerId)
    const pathEdges = Array.isArray(path?.pathItem?.edges) ? path.pathItem.edges : []

    path.steps.forEach((step, stepIndex) => {
      addCanonicalNode(nodeMap, step, {
        isActualController: isActualRelationship && stepIndex === 0,
        isFocused: isFocusedRelationship && stepIndex === 0,
        isKeyPath: keyPathNodeIndex.has(toKey(step.id)),
        keyPathIndex: keyPathNodeIndex.get(toKey(step.id)) ?? null,
      })
    })

    path.steps.forEach((step, stepIndex) => {
      const nextStep = path.steps[stepIndex + 1]
      if (!nextStep) {
        return
      }

      const edgePayload = pathEdges[stepIndex] || null
      const source = toKey(step.id)
      const target = toKey(nextStep.id)
      addCanonicalEdge(edgeMap, {
        id: pairKey(source, target),
        source,
        target,
        relationType: edgePayload?.relation_type || edgePayload?.control_type || relationship?.control_type,
        controlRatio:
          ratioFromEdge(edgePayload) ??
          ratioFromValue(relationship?.control_ratio),
        isKeyPath: keyPathPairKeys.has(pairKey(source, target)),
        isPrimary: isActualRelationship && keyPathPairKeys.has(pairKey(source, target)),
        isVirtual: !edgePayload,
        origin: edgePayload ? 'control-path-edge' : 'control-path-virtual',
      })
    })
  })
}

function buildIncomingEdgeMap(edges = []) {
  const incoming = new Map()
  edges.forEach((edge) => {
    const target = toKey(edge.target)
    if (!target) {
      return
    }
    if (!incoming.has(target)) {
      incoming.set(target, [])
    }
    incoming.get(target).push(edge)
  })
  return incoming
}

function sortIncomingEdgesForNode(edges = [], nodeMap, downstreamId, keyParentByNodeId) {
  return [...edges].sort((left, right) => {
    const leftKey = keyParentByNodeId.get(downstreamId) === toKey(left.source)
    const rightKey = keyParentByNodeId.get(downstreamId) === toKey(right.source)
    if (leftKey !== rightKey) {
      return leftKey ? -1 : 1
    }

    if (left.isKeyPath !== right.isKeyPath) {
      return left.isKeyPath ? -1 : 1
    }

    const leftSemantic = isSemanticRelationType(left.relationType)
    const rightSemantic = isSemanticRelationType(right.relationType)
    if (leftSemantic !== rightSemantic) {
      return leftSemantic ? -1 : 1
    }

    const ratioDelta =
      normalizedRatioForComparison(right.controlRatio) -
      normalizedRatioForComparison(left.controlRatio)
    if (ratioDelta !== 0) {
      return ratioDelta
    }

    const leftName = safeText(nodeMap.get(toKey(left.source))?.name, '')
    const rightName = safeText(nodeMap.get(toKey(right.source))?.name, '')
    return leftName.localeCompare(rightName)
  })
}

function annotateStructuralHints({
  nodeMap,
  edgeMap,
  targetId,
  actualControllerId,
  keyPathNodeIds,
}) {
  const edges = Array.from(edgeMap.values())
  const incoming = buildIncomingEdgeMap(edges)
  const directUpstreamEdges = incoming.get(targetId) || []
  const directUpstreamIds = directUpstreamEdges.map((edge) => toKey(edge.source)).filter(Boolean)
  const directSet = new Set(directUpstreamIds)
  const secondLayerSet = new Set()

  directUpstreamEdges.forEach((edge) => {
    const sourceId = toKey(edge.source)
    const ratio = edge.controlRatio
    addCanonicalNode(nodeMap, nodeMap.get(sourceId), {
      isDirectUpstream: true,
      bestDownstreamRatio: ratio,
      role: sameId(sourceId, actualControllerId) ? 'actualController' : 'direct',
    })

    const parents = incoming.get(sourceId) || []
    parents.forEach((parentEdge) => {
      secondLayerSet.add(toKey(parentEdge.source))
    })
  })

  secondLayerSet.forEach((nodeId) => {
    addCanonicalNode(nodeMap, nodeMap.get(nodeId), {
      isSecondLayerCandidate: true,
    })
  })

  keyPathNodeIds.forEach((nodeId, index) => {
    addCanonicalNode(nodeMap, nodeMap.get(nodeId), {
      isKeyPath: true,
      keyPathIndex: index,
      role: sameId(nodeId, targetId)
        ? 'target'
        : sameId(nodeId, actualControllerId)
          ? 'actualController'
          : directSet.has(nodeId)
            ? 'direct'
            : 'intermediate',
    })
  })

  return {
    incoming,
    directUpstreamIds,
    secondLayerIds: Array.from(secondLayerSet).filter(Boolean),
  }
}

function sortDirectUpstreamIds({
  ids,
  nodeMap,
  incoming,
  targetId,
  keyPathFirstLayerId,
  actualControllerId,
}) {
  return [...new Set(ids.map((id) => toKey(id)).filter(Boolean))].sort((leftId, rightId) => {
    const leftKey = sameId(leftId, keyPathFirstLayerId)
    const rightKey = sameId(rightId, keyPathFirstLayerId)
    if (leftKey !== rightKey) {
      return leftKey ? -1 : 1
    }

    const leftActual = sameId(leftId, actualControllerId)
    const rightActual = sameId(rightId, actualControllerId)
    if (leftActual !== rightActual) {
      return leftActual ? -1 : 1
    }

    const targetIncoming = incoming.get(targetId) || []
    const leftEdge = targetIncoming.find((edge) => sameId(edge.source, leftId))
    const rightEdge = targetIncoming.find((edge) => sameId(edge.source, rightId))
    const ratioDelta =
      normalizedRatioForComparison(rightEdge?.controlRatio) -
      normalizedRatioForComparison(leftEdge?.controlRatio)
    if (ratioDelta !== 0) {
      return ratioDelta
    }

    const leftSemantic = isSemanticRelationType(leftEdge?.relationType)
    const rightSemantic = isSemanticRelationType(rightEdge?.relationType)
    if (leftSemantic !== rightSemantic) {
      return leftSemantic ? -1 : 1
    }

    return safeText(nodeMap.get(leftId)?.name, '').localeCompare(safeText(nodeMap.get(rightId)?.name, ''))
  })
}

function buildKeyPathMetadata(pathSteps = []) {
  const nodeIds = pathSteps.map((step) => toKey(step.id)).filter(Boolean)
  const nodeIndex = new Map(nodeIds.map((id, index) => [id, index]))
  const pairKeys = new Set()
  const keyParentByNodeId = new Map()

  nodeIds.forEach((nodeId, index) => {
    const nextId = nodeIds[index + 1]
    if (!nextId) {
      return
    }

    pairKeys.add(pairKey(nodeId, nextId))
    keyParentByNodeId.set(nextId, nodeId)
  })

  return {
    nodeIds,
    nodeIndex,
    pairKeys,
    keyParentByNodeId,
    firstLayerId: nodeIds.length >= 2 ? nodeIds[nodeIds.length - 2] : '',
  }
}

function buildDefaultExpandedNodeIds(keyPathNodeIds = [], config = {}) {
  const maxDepth = config.maxAutoExpandedKeyPathDepth ?? CONTROL_STRUCTURE_DISPLAY_CONFIG.maxAutoExpandedKeyPathDepth
  return keyPathNodeIds.slice(2, Math.max(2, keyPathNodeIds.length - 1)).slice(0, maxDepth)
}

function buildExpansionSeed({
  targetId,
  actualControllerId,
  keyPathNodeIds,
  summaryControllerUpstreamIds = [],
  edgeCount,
  nodeCount,
}) {
  return [
    targetId,
    actualControllerId,
    keyPathNodeIds.join('>'),
    summaryControllerUpstreamIds.join('>'),
    nodeCount,
    edgeCount,
  ].join('|')
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
  const entityLookup = buildEntityLookup(relationshipGraph)
  const actualController = pickActualController(controlAnalysis)
  const focusedRelationship = pickFocusedRelationship(controlAnalysis, actualController)
  const summaryRelationship = pickSummaryRelationship(controlAnalysis, actualController)
  const firstPathItem = getControlPaths(summaryRelationship)[0] || null
  const target = targetStep({ company, relationshipGraph, pathItem: firstPathItem })

  if (!target.id) {
    return {
      hasDiagram: false,
      placeholderTitle: 'No renderable control structure',
      placeholderDescription: 'Target company information is missing.',
      nodes: [],
      edges: [],
      keyPathNodeIds: [],
      directUpstreamIds: [],
    }
  }

  const context = {
    entityLookup,
    target,
  }
  const multiPathConvergences = buildMultiPathConvergenceMetadata(relationships, context)
  const multiPathConvergenceByNodeId = Object.fromEntries(
    multiPathConvergences.map((item) => [item.nodeId, item]),
  )
  const multiPathConvergenceNodeIds = multiPathConvergences.map((item) => item.nodeId)

  const primaryPath =
    summaryRelationship ? relationshipPath(summaryRelationship, context, 0) : { steps: [] }
  const fallbackCountryPath =
    primaryPath.steps.length >= 2
      ? []
      : fallbackPathFromCountryAttribution(countryAttribution, entityLookup, target)
  const keyPathSteps = primaryPath.steps.length >= 2 ? primaryPath.steps : fallbackCountryPath
  const keyPath = buildKeyPathMetadata(keyPathSteps)

  const nodeMap = new Map()
  const edgeMap = new Map()

  addGraphNodes(nodeMap, entityLookup)
  addGraphEdges(edgeMap, relationshipGraph)

  addCanonicalNode(nodeMap, target, { role: 'target' })

  if (summaryRelationship) {
    const actualControllerId = toKey(actualController?.controller_entity_id)
    const focusedControllerId = toKey(focusedRelationship?.controller_entity_id)
    applyRelationshipPaths({
      relationships,
      context,
      nodeMap,
      edgeMap,
      actualControllerId,
      focusedControllerId,
      keyPathPairKeys: keyPath.pairKeys,
      keyPathNodeIndex: keyPath.nodeIndex,
    })
  } else if (keyPath.nodeIds.length >= 2) {
    keyPathSteps.forEach((step, index) => {
      addCanonicalNode(nodeMap, step, {
        isKeyPath: true,
        keyPathIndex: index,
      })
    })

    keyPath.nodeIds.forEach((nodeId, index) => {
      const nextId = keyPath.nodeIds[index + 1]
      if (!nextId) {
        return
      }
      addCanonicalEdge(edgeMap, {
        id: pairKey(nodeId, nextId),
        source: nodeId,
        target: nextId,
        relationType: 'equity',
        isKeyPath: true,
        isPrimary: true,
        isVirtual: true,
        origin: 'country-attribution-fallback',
      })
    })
  }

  const actualControllerId =
    toKey(actualController?.controller_entity_id) ||
    toKey(countryAttribution?.basis?.actual_controller_entity_id)
  const focusedControllerId = toKey(focusedRelationship?.controller_entity_id)
  const summaryControllerId = actualControllerId || focusedControllerId || keyPath.nodeIds[0] || ''

  if (actualControllerId) {
    const actualNode = nodeMap.get(actualControllerId) || entityLookup.get(actualControllerId)
    if (actualNode) {
      addCanonicalNode(nodeMap, actualNode, {
        isActualController: true,
        role: 'actualController',
        isKeyPath: keyPath.nodeIndex.has(actualControllerId),
        keyPathIndex: keyPath.nodeIndex.get(actualControllerId) ?? 0,
      })
    }
  }

  if (focusedControllerId && !sameId(focusedControllerId, actualControllerId)) {
    const focusedNode = nodeMap.get(focusedControllerId) || entityLookup.get(focusedControllerId)
    if (focusedNode) {
      addCanonicalNode(nodeMap, focusedNode, {
        isFocused: true,
        role: 'focused',
      })
    }
  }

  const structural = annotateStructuralHints({
    nodeMap,
    edgeMap,
    targetId: target.id,
    actualControllerId,
    keyPathNodeIds: keyPath.nodeIds,
  })

  const directUpstreamIds = sortDirectUpstreamIds({
    ids: structural.directUpstreamIds,
    nodeMap,
    incoming: structural.incoming,
    targetId: target.id,
    keyPathFirstLayerId: keyPath.firstLayerId,
    actualControllerId,
  })

  const summaryControllerUpstreamIds = summaryControllerId
    ? sortIncomingEdgesForNode(
        structural.incoming.get(summaryControllerId) || [],
        nodeMap,
        summaryControllerId,
        keyPath.keyParentByNodeId,
      )
        .map((edge) => toKey(edge.source))
        .filter((nodeId) => nodeId && !sameId(nodeId, target.id))
    : []

  const nodes = Array.from(nodeMap.values()).map((node) => {
    const incomingEdges = sortIncomingEdgesForNode(
      structural.incoming.get(node.id) || [],
      nodeMap,
      node.id,
      keyPath.keyParentByNodeId,
    )

    return {
      ...node,
      incomingEdgeIds: incomingEdges.map((edge) => edge.id),
      hasUpstream: incomingEdges.length > 0,
      upstreamCount: incomingEdges.length,
      isSummaryController: sameId(node.id, summaryControllerId),
      multiPathConvergence: multiPathConvergenceByNodeId[node.id] || null,
    }
  })

  const edges = Array.from(edgeMap.values()).map((edge) => ({
    ...edge,
    sourceName: nodeMap.get(toKey(edge.source))?.name || `Entity ${edge.source}`,
    targetName: nodeMap.get(toKey(edge.target))?.name || `Entity ${edge.target}`,
  }))

  const summaryControllerNode = nodeMap.get(summaryControllerId) || null
  const defaultExpandedNodeIds = buildDefaultExpandedNodeIds(keyPath.nodeIds, config)

  if (!edges.length && !directUpstreamIds.length && !summaryControllerId) {
    return {
      hasDiagram: false,
      placeholderTitle: 'No renderable control structure',
      placeholderDescription: 'Neither direct upstream relationships nor controller paths were found.',
      nodes: [],
      edges: [],
      keyPathNodeIds: [],
      directUpstreamIds: [],
    }
  }

  return {
    hasDiagram: true,
    viewMode: 'Control Structure Diagram',
    sourceMode: 'progressive-expand',
    displayMode: 'progressive-expand',
    targetId: target.id,
    targetName: target.name,
    actualControllerId,
    actualControllerName: safeText(actualController?.controller_name, summaryControllerNode?.name || EMPTY_TEXT),
    focusedControllerId,
    focusedControllerName: safeText(focusedRelationship?.controller_name, EMPTY_TEXT),
    summaryControllerId,
    summaryControllerName: safeText(summaryControllerNode?.name || actualController?.controller_name || focusedRelationship?.controller_name, EMPTY_TEXT),
    summaryControllerType: summaryControllerNode?.entityType || normalizeEntityType(actualController?.controller_type),
    summaryControllerUpstreamIds,
    summaryControllerHasUpstream: summaryControllerUpstreamIds.length > 0,
    actualControlCountry: safeText(countryAttribution?.actual_control_country, 'Unknown'),
    attributionType: safeText(countryAttribution?.attribution_type, EMPTY_TEXT),
    nodes,
    edges,
    directUpstreamIds,
    secondLayerCandidateIds: structural.secondLayerIds,
    keyPathNodeIds: keyPath.nodeIds,
    keyPathEdgeIds: Array.from(keyPath.pairKeys),
    keyPathFirstLayerId: keyPath.firstLayerId,
    keyParentByNodeId: Object.fromEntries(keyPath.keyParentByNodeId.entries()),
    multiPathConvergences,
    multiPathConvergenceByNodeId,
    multiPathConvergenceNodeIds,
    defaultExpandedNodeIds,
    omittedRelationshipCount: 0,
    expansionSeed: buildExpansionSeed({
      targetId: target.id,
      actualControllerId,
      keyPathNodeIds: keyPath.nodeIds,
      summaryControllerUpstreamIds,
      edgeCount: edges.length,
      nodeCount: nodes.length,
    }),
    selectionSummary: {
      canonicalNodeCount: nodes.length,
      canonicalEdgeCount: edges.length,
      directUpstreamCount: directUpstreamIds.length,
      secondLayerCandidateCount: structural.secondLayerIds.length,
      keyPathLength: keyPath.nodeIds.length,
      defaultExpandedCount: defaultExpandedNodeIds.length,
      summaryControllerUpstreamCount: summaryControllerUpstreamIds.length,
      controlRelationshipCount: relationships.length,
    },
    legend: {
      entityTypes: ENTITY_TYPES,
      roles: ['target', 'direct', 'focused', 'actualController'],
      edgeTypes: ['equity', 'agreement', 'board_control', 'voting_right', 'nominee', 'vie', 'key_path'],
    },
  }
}
