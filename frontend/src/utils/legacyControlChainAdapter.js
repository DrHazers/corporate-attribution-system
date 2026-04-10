const EMPTY_TEXT = '暂无'

export const ADAPTIVE_CONTROL_GRAPH_FILTER_CONFIG = {
  smallGraphMaxUpstream: 6,
  smallGraphMaxCandidateNodes: 8,
  mediumGraphMaxUpstream: 12,
  mediumGraphMaxCandidateNodes: 15,
  equityRatioThreshold: 0.02,
  maxDirectUpstreamNodes: 10,
}

const ROLE_LABELS = {
  actualController: 'actual controller',
  focused: 'focused controller / candidate',
  intermediate: 'key intermediate node',
  target: 'target company',
  support: 'supporting upstream entity',
}

const ENTITY_TYPE_LABELS = {
  company: '公司主体',
  person: '自然人',
  fund: '基金/公众持股',
  government: '政府/主权主体',
  other: '其他主体',
}

const NON_EQUITY_RELATION_TYPES = new Set([
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

function firstNonEmpty(...values) {
  return values.find((value) => emptyText(value) !== '') ?? null
}

function normalizeEntityType(value) {
  const normalized = emptyText(value).toLowerCase()
  return ENTITY_TYPE_LABELS[normalized] ? normalized : 'other'
}

function normalizeRelationType(value) {
  const normalized = emptyText(value).toLowerCase()
  if (!normalized) {
    return 'other'
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
  if (NON_EQUITY_RELATION_TYPES.has(normalized)) {
    return normalized
  }
  return normalized
}

function edgeRelationType(edge) {
  return normalizeRelationType(firstNonEmpty(edge?.relation_type, edge?.control_type, edge?.relationRole))
}

function isNonEquityType(type) {
  return NON_EQUITY_RELATION_TYPES.has(normalizeRelationType(type))
}

function getEdgeId(edge) {
  return toKey(edge?.structure_id ?? edge?.id ?? edge?.edge_id)
}

function pairKey(sourceId, targetId) {
  return `${toKey(sourceId)}->${toKey(targetId)}`
}

function getEdgePairKey(edge) {
  return pairKey(edge?.from_entity_id, edge?.to_entity_id)
}

function getRatioValue(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return null
  }
  return numeric > 1 ? numeric / 100 : numeric
}

function getEdgeRatio(edge) {
  return getRatioValue(firstNonEmpty(edge?.holding_ratio, edge?.control_ratio, edge?.numeric_factor))
}

function formatPercent(value) {
  if (value === null || value === undefined || value === '') {
    return EMPTY_TEXT
  }

  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return String(value)
  }

  const normalized = numeric <= 1 ? numeric * 100 : numeric
  return `${normalized.toFixed(2)}%`
}

function formatRatioDecimal(value) {
  return Number(value).toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 4,
  })
}

function formatBasis(basis) {
  if (!basis) {
    return ''
  }

  if (typeof basis === 'string') {
    return basis
  }

  if (typeof basis === 'object') {
    return [
      basis.classification,
      basis.control_mode,
      basis.aggregator,
      basis.path_count !== undefined ? `${basis.path_count} 条路径` : null,
      basis.as_of,
    ]
      .filter(Boolean)
      .join(' | ')
  }

  return String(basis)
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
      companyId: node.company_id ?? null,
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

function getRelationshipKey(relationship) {
  return [
    relationship?.controller_entity_id ?? relationship?.controller_name ?? '',
    relationship?.control_type ?? '',
    relationship?.control_ratio ?? '',
    relationship?.is_actual_controller ? 'actual' : 'candidate',
  ].join('|')
}

function getControllerStep(relationship, fallbackIndex = 0) {
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

function getControlPaths(relationship) {
  return Array.isArray(relationship?.control_path) ? relationship.control_path : []
}

function resolveTargetInfo({ company = {}, relationshipGraph = {}, primaryPathItem = null }) {
  const pathIds = Array.isArray(primaryPathItem?.path_entity_ids) ? primaryPathItem.path_entity_ids : []
  const pathNames = Array.isArray(primaryPathItem?.path_entity_names) ? primaryPathItem.path_entity_names : []
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

function buildPathSteps(pathItem, { entityLookup, targetInfo, controllerStep }) {
  const ids = Array.isArray(pathItem?.path_entity_ids) ? pathItem.path_entity_ids : []
  const names = Array.isArray(pathItem?.path_entity_names) ? pathItem.path_entity_names : []
  const itemCount = Math.max(ids.length, names.length)

  if (!itemCount) {
    return [controllerStep, targetInfo]
  }

  return Array.from({ length: itemCount }, (_, index) => {
    const rawId = toKey(ids[index])
    const lookup = rawId ? entityLookup.get(rawId) : null
    const name = names[index] || lookup?.name || (rawId ? `Entity ${rawId}` : `Path Node ${index + 1}`)

    return {
      id: rawId || `path:${index}:${name}`,
      name,
      entityType: lookup?.entityType || (index === itemCount - 1 ? 'company' : 'other'),
      country: lookup?.country || null,
    }
  })
}

function normalizePathDirection(steps, { targetInfo, controllerStep }) {
  let normalized = [...steps]

  if (normalized.length > 1 && sameId(normalized[0].id, targetInfo.id)) {
    normalized = normalized.reverse()
  }

  if (normalized.length > 1 && sameId(normalized[normalized.length - 1].id, controllerStep.id)) {
    normalized = normalized.reverse()
  }

  const controllerIndex = normalized.findIndex((step) => sameId(step.id, controllerStep.id))
  if (controllerIndex > 0) {
    normalized = normalized.slice(controllerIndex)
  }

  if (!normalized.some((step) => sameId(step.id, controllerStep.id))) {
    normalized.unshift(controllerStep)
  }

  const targetIndex = normalized.findIndex((step) => sameId(step.id, targetInfo.id))
  if (targetIndex >= 0 && targetIndex < normalized.length - 1) {
    normalized = normalized.slice(0, targetIndex + 1)
  }

  if (!normalized.some((step) => sameId(step.id, targetInfo.id))) {
    normalized.push(targetInfo)
  }

  return normalized.filter(
    (step, index) => step.id && (index === 0 || !sameId(step.id, normalized[index - 1].id)),
  )
}

function normalizeRelationshipPath(relationship, context, fallbackIndex = 0) {
  const controllerStep = getControllerStep(relationship, fallbackIndex)
  const controlPaths = getControlPaths(relationship)
  const primaryPathItem = controlPaths[0] || null
  const rawSteps = buildPathSteps(primaryPathItem, {
    entityLookup: context.entityLookup,
    targetInfo: context.targetInfo,
    controllerStep,
  })

  return {
    relationship,
    pathItem: primaryPathItem,
    steps: normalizePathDirection(rawSteps, {
      targetInfo: context.targetInfo,
      controllerStep,
    }),
  }
}

function getPathEdgeIds(pathItem) {
  const explicitEdgeIds = Array.isArray(pathItem?.edge_ids) ? pathItem.edge_ids : []
  const edgeIdsFromEdges = Array.isArray(pathItem?.edges)
    ? pathItem.edges.map((edge) => edge?.structure_id ?? edge?.id ?? edge?.edge_id)
    : []

  return [...explicitEdgeIds, ...edgeIdsFromEdges].map((edgeId) => toKey(edgeId)).filter(Boolean)
}

function getPathPairs(steps) {
  const pairs = []
  for (let index = 0; index < steps.length - 1; index += 1) {
    pairs.push(pairKey(steps[index].id, steps[index + 1].id))
  }
  return pairs
}

function addStepNames(nameLookup, steps) {
  steps.forEach((step) => {
    const key = toKey(step.id)
    if (key && emptyText(step.name) && !nameLookup.has(key)) {
      nameLookup.set(key, step.name)
    }
  })
}

function buildKeyControlContext({ relationships, primaryRelationship, context }) {
  const forcedNodeIds = new Set([context.targetInfo.id].filter(Boolean))
  const forcedEdgeIds = new Set()
  const forcedPairs = new Set()
  const primaryEdgeIds = new Set()
  const primaryPairs = new Set()
  const keyPathNodeIds = new Set()
  const summaryNodeIds = new Set()
  const pathNameLookup = new Map()
  const normalizedPaths = []

  relationships.forEach((relationship, index) => {
    const normalizedPath = normalizeRelationshipPath(relationship, context, index)
    const steps = normalizedPath.steps
    const stepIds = steps.map((step) => toKey(step.id)).filter(Boolean)
    const relationshipEdgeIds = getPathEdgeIds(normalizedPath.pathItem)
    const relationshipPairs = getPathPairs(steps)
    const relationshipIsPrimary = getRelationshipKey(relationship) === getRelationshipKey(primaryRelationship)

    stepIds.forEach((stepId) => {
      forcedNodeIds.add(stepId)
      keyPathNodeIds.add(stepId)
      summaryNodeIds.add(stepId)
    })
    if (relationship?.controller_entity_id) {
      summaryNodeIds.add(toKey(relationship.controller_entity_id))
      forcedNodeIds.add(toKey(relationship.controller_entity_id))
    }
    relationshipEdgeIds.forEach((edgeId) => {
      forcedEdgeIds.add(edgeId)
      if (relationshipIsPrimary) {
        primaryEdgeIds.add(edgeId)
      }
    })
    relationshipPairs.forEach((pathPair) => {
      forcedPairs.add(pathPair)
      if (relationshipIsPrimary) {
        primaryPairs.add(pathPair)
      }
    })
    addStepNames(pathNameLookup, steps)

    normalizedPaths.push({
      relationship,
      isPrimary: relationshipIsPrimary,
      steps,
      edgeIds: relationshipEdgeIds,
      pairs: relationshipPairs,
    })
  })

  return {
    forcedNodeIds,
    forcedEdgeIds,
    forcedPairs,
    primaryEdgeIds,
    primaryPairs,
    keyPathNodeIds,
    summaryNodeIds,
    pathNameLookup,
    normalizedPaths,
  }
}

function isEdgeInKeyContext(edge, keyContext) {
  const edgeId = getEdgeId(edge)
  return (
    (edgeId && keyContext.forcedEdgeIds.has(edgeId)) ||
    keyContext.forcedPairs.has(getEdgePairKey(edge))
  )
}

function isEdgePrimary(edge, keyContext) {
  const edgeId = getEdgeId(edge)
  return (
    (edgeId && keyContext.primaryEdgeIds.has(edgeId)) ||
    keyContext.primaryPairs.has(getEdgePairKey(edge))
  )
}

function hasExplanationFields(edge) {
  return [
    edge?.control_basis,
    edge?.agreement_scope,
    edge?.nomination_rights,
    edge?.relation_metadata,
    edge?.semantic_flags,
    edge?.confidence_level,
    edge?.relation_role,
    edge?.basis,
  ].some((value) => emptyText(value) !== '')
}

function isImportantNonEquityEdge(edge, keyContext) {
  const relationType = edgeRelationType(edge)
  if (!isNonEquityType(relationType)) {
    return false
  }

  return (
    isEdgeInKeyContext(edge, keyContext) ||
    keyContext.summaryNodeIds.has(toKey(edge?.from_entity_id)) ||
    keyContext.summaryNodeIds.has(toKey(edge?.to_entity_id)) ||
    hasExplanationFields(edge)
  )
}

function groupDirectUpstreamEdges(edges, targetId, keyContext) {
  const groups = new Map()

  edges
    .filter((edge) => sameId(edge?.to_entity_id, targetId))
    .forEach((edge) => {
      const sourceId = toKey(edge?.from_entity_id)
      if (!sourceId) {
        return
      }
      if (!groups.has(sourceId)) {
        groups.set(sourceId, {
          sourceId,
          edges: [],
          ratio: -1,
          bestEdge: null,
          hasKeyEdge: false,
          hasImportantNonEquity: false,
          hasEquity: false,
        })
      }

      const group = groups.get(sourceId)
      const ratio = getEdgeRatio(edge)
      group.edges.push(edge)
      group.hasEquity = group.hasEquity || edgeRelationType(edge) === 'equity'
      group.hasKeyEdge = group.hasKeyEdge || isEdgeInKeyContext(edge, keyContext)
      group.hasImportantNonEquity =
        group.hasImportantNonEquity || isImportantNonEquityEdge(edge, keyContext)

      if (ratio !== null && ratio > group.ratio) {
        group.ratio = ratio
        group.bestEdge = edge
      } else if (!group.bestEdge) {
        group.bestEdge = edge
      }
    })

  return Array.from(groups.values())
}

function sortDirectUpstreamGroups(groups, entityLookup) {
  return [...groups].sort((left, right) => {
    if (left.hasKeyEdge !== right.hasKeyEdge) {
      return left.hasKeyEdge ? -1 : 1
    }
    if (left.hasImportantNonEquity !== right.hasImportantNonEquity) {
      return left.hasImportantNonEquity ? -1 : 1
    }
    if (left.ratio !== right.ratio) {
      return right.ratio - left.ratio
    }
    return safeText(entityLookup.get(left.sourceId)?.name, '').localeCompare(
      safeText(entityLookup.get(right.sourceId)?.name, ''),
    )
  })
}

function classifyDisplayMode({ directUpstreamCount, candidateNodeCount, config }) {
  if (
    directUpstreamCount <= config.smallGraphMaxUpstream ||
    candidateNodeCount <= config.smallGraphMaxCandidateNodes
  ) {
    return 'small'
  }

  if (
    directUpstreamCount <= config.mediumGraphMaxUpstream ||
    candidateNodeCount <= config.mediumGraphMaxCandidateNodes
  ) {
    return 'medium'
  }

  return 'large'
}

function selectDirectUpstreamGroups({ groups, mode, config, forcedNodeIds }) {
  if (mode === 'small') {
    return groups
  }

  const forcedGroups = groups.filter(
    (group) =>
      forcedNodeIds.has(group.sourceId) || group.hasKeyEdge || group.hasImportantNonEquity,
  )
  const forcedGroupIds = new Set(forcedGroups.map((group) => group.sourceId))
  const ordinaryGroups = groups.filter(
    (group) => !forcedGroupIds.has(group.sourceId) && group.hasEquity,
  )

  if (mode === 'medium') {
    const mediumGroups = ordinaryGroups.filter((group, index) => {
      const aboveThreshold = group.ratio >= config.equityRatioThreshold
      return aboveThreshold || index < config.maxDirectUpstreamNodes
    })
    return [...forcedGroups, ...mediumGroups]
  }

  const aboveThreshold = ordinaryGroups.filter(
    (group) => group.ratio >= config.equityRatioThreshold,
  )
  const capped = aboveThreshold.slice(0, config.maxDirectUpstreamNodes)
  const selectedIds = new Set(capped.map((group) => group.sourceId))

  for (const group of ordinaryGroups) {
    if (selectedIds.size >= config.maxDirectUpstreamNodes) {
      break
    }
    if (!selectedIds.has(group.sourceId)) {
      capped.push(group)
      selectedIds.add(group.sourceId)
    }
  }

  return [...forcedGroups, ...capped]
}

function chooseGroupEdges(group, mode, keyContext) {
  if (mode === 'small') {
    return group.edges
  }

  const selected = new Map()
  const remember = (edge) => {
    const key = getEdgeId(edge) || getEdgePairKey(edge)
    if (key) {
      selected.set(key, edge)
    }
  }

  if (group.bestEdge) {
    remember(group.bestEdge)
  }
  group.edges.forEach((edge) => {
    if (isEdgeInKeyContext(edge, keyContext) || isImportantNonEquityEdge(edge, keyContext)) {
      remember(edge)
    }
  })

  return Array.from(selected.values())
}

function collectSelectedGraph({
  rawEdges,
  directGroups,
  selectedDirectGroups,
  keyContext,
  mode,
}) {
  const selectedNodeIds = new Set(keyContext.forcedNodeIds)
  const selectedEdgeKeys = new Set()
  const selectedEdges = []
  const selectedDirectGroupIds = new Set(selectedDirectGroups.map((group) => group.sourceId))

  const addEdge = (edge) => {
    const sourceId = toKey(edge?.from_entity_id)
    const targetId = toKey(edge?.to_entity_id)
    if (!sourceId || !targetId) {
      return
    }

    const edgeKey = getEdgeId(edge) || `${sourceId}->${targetId}:${edgeRelationType(edge)}`
    if (selectedEdgeKeys.has(edgeKey)) {
      return
    }
    selectedEdgeKeys.add(edgeKey)
    selectedNodeIds.add(sourceId)
    selectedNodeIds.add(targetId)
    selectedEdges.push(edge)
  }

  selectedDirectGroups.forEach((group) => {
    selectedNodeIds.add(group.sourceId)
    chooseGroupEdges(group, mode, keyContext).forEach(addEdge)
  })

  rawEdges.forEach((edge) => {
    if (isEdgeInKeyContext(edge, keyContext) || isImportantNonEquityEdge(edge, keyContext)) {
      addEdge(edge)
      return
    }

    if (mode === 'small') {
      const sourceId = toKey(edge?.from_entity_id)
      const targetId = toKey(edge?.to_entity_id)
      if (selectedNodeIds.has(sourceId) && selectedNodeIds.has(targetId)) {
        addEdge(edge)
      }
    }
  })

  keyContext.normalizedPaths.forEach((path) => {
    path.steps.forEach((step) => {
      selectedNodeIds.add(toKey(step.id))
    })
  })

  const selectedDirectUpstreamCount = selectedDirectGroupIds.size
  const omittedDirectUpstreamCount = Math.max(0, directGroups.length - selectedDirectUpstreamCount)

  return {
    selectedNodeIds,
    selectedEdges,
    selectedEdgeKeys,
    selectedDirectUpstreamCount,
    omittedDirectUpstreamCount,
  }
}

function findRawEdgeForPair(edges, sourceId, targetId) {
  return edges.find((edge) => sameId(edge?.from_entity_id, sourceId) && sameId(edge?.to_entity_id, targetId))
}

function buildNodeDetails({ node, relationship, countryAttribution, filterReason }) {
  const lines = [
    `${ROLE_LABELS[node.role] || node.role}`,
    `主体类型：${ENTITY_TYPE_LABELS[node.entityType] || ENTITY_TYPE_LABELS.other}`,
  ]

  if (relationship?.control_type) {
    lines.push(`控制类型：${relationship.control_type}`)
  }

  if (relationship?.control_ratio !== undefined && relationship?.control_ratio !== null) {
    lines.push(`控制比例：${formatPercent(relationship.control_ratio)}`)
  }

  if (node.role === 'actualController' && countryAttribution?.actual_control_country) {
    lines.push(`实际控制地：${countryAttribution.actual_control_country}`)
  }

  if (node.country) {
    lines.push(`国家/地区：${node.country}`)
  }

  if (filterReason) {
    lines.push(`展示原因：${filterReason}`)
  }

  return lines
}

function makeDiagramNode({
  step,
  role,
  relationship = null,
  countryAttribution = {},
  filterReason = '',
}) {
  const name = safeText(step.name, '未命名主体')
  const entityType = normalizeEntityType(step.entityType)

  return {
    id: toKey(step.id),
    name,
    displayLabel: name,
    role,
    entityType,
    country: step.country || null,
    relationshipKey: relationship ? getRelationshipKey(relationship) : null,
    filterReason,
    tooltipTitle: name,
    tooltipLines: buildNodeDetails({
      node: {
        role,
        entityType,
        country: step.country || null,
      },
      relationship,
      countryAttribution,
      filterReason,
    }),
  }
}

function resolveNodeStep({
  nodeId,
  targetInfo,
  entityLookup,
  pathNameLookup,
  actualController,
  focusedRelationship,
}) {
  if (sameId(nodeId, targetInfo.id)) {
    return targetInfo
  }

  if (actualController && sameId(nodeId, actualController.controller_entity_id)) {
    const lookup = entityLookup.get(toKey(nodeId))
    return {
      id: toKey(nodeId),
      name: actualController.controller_name || lookup?.name || `Entity ${nodeId}`,
      entityType: actualController.controller_type || lookup?.entityType || 'other',
      country: lookup?.country || null,
    }
  }

  if (focusedRelationship && sameId(nodeId, focusedRelationship.controller_entity_id)) {
    const lookup = entityLookup.get(toKey(nodeId))
    return {
      id: toKey(nodeId),
      name: focusedRelationship.controller_name || lookup?.name || `Entity ${nodeId}`,
      entityType: focusedRelationship.controller_type || lookup?.entityType || 'other',
      country: lookup?.country || null,
    }
  }

  const lookup = entityLookup.get(toKey(nodeId))
  return {
    id: toKey(nodeId),
    name: pathNameLookup.get(toKey(nodeId)) || lookup?.name || `Entity ${nodeId}`,
    entityType: lookup?.entityType || 'other',
    country: lookup?.country || null,
  }
}

function resolveNodeRole({
  nodeId,
  targetInfo,
  actualController,
  focusedRelationship,
  primaryPathSet,
  keyPathNodeIds,
}) {
  if (sameId(nodeId, targetInfo.id)) {
    return 'target'
  }
  if (actualController && sameId(nodeId, actualController.controller_entity_id)) {
    return 'actualController'
  }
  if (focusedRelationship && sameId(nodeId, focusedRelationship.controller_entity_id)) {
    return 'focused'
  }
  if (primaryPathSet.has(toKey(nodeId)) || keyPathNodeIds.has(toKey(nodeId))) {
    return 'intermediate'
  }
  return 'support'
}

function getNodeFilterReason(nodeId, keyContext, selectedDirectGroupsById) {
  const key = toKey(nodeId)
  if (keyContext.forcedNodeIds.has(key)) {
    return '关键控制链/summary 强制保留'
  }
  if (selectedDirectGroupsById.has(key)) {
    return '主要直接上游主体'
  }
  return '重要非 equity 控制关系'
}

function buildNodes({
  selectedNodeIds,
  targetInfo,
  entityLookup,
  keyContext,
  primaryPathSet,
  actualController,
  focusedRelationship,
  countryAttribution,
  selectedDirectGroups,
}) {
  const selectedDirectGroupsById = new Set(selectedDirectGroups.map((group) => group.sourceId))

  return Array.from(selectedNodeIds)
    .filter(Boolean)
    .map((nodeId) => {
      const role = resolveNodeRole({
        nodeId,
        targetInfo,
        actualController,
        focusedRelationship,
        primaryPathSet,
        keyPathNodeIds: keyContext.keyPathNodeIds,
      })
      const step = resolveNodeStep({
        nodeId,
        targetInfo,
        entityLookup,
        pathNameLookup: keyContext.pathNameLookup,
        actualController,
        focusedRelationship,
      })
      const relationship =
        role === 'actualController'
          ? actualController
          : role === 'focused'
            ? focusedRelationship
            : null

      return makeDiagramNode({
        step,
        role,
        relationship,
        countryAttribution,
        filterReason: getNodeFilterReason(nodeId, keyContext, selectedDirectGroupsById),
      })
    })
}

function buildRawEdgeTooltip(edge, { isKeyPath, isPrimaryPath }) {
  const relationType = edgeRelationType(edge)
  const ratio = firstNonEmpty(edge?.holding_ratio, edge?.control_ratio, edge?.numeric_factor)
  return [
    `${safeText(edge?.from_entity_name || edge?.from_entity_id)} → ${safeText(
      edge?.to_entity_name || edge?.to_entity_id,
    )}`,
    isPrimaryPath ? '主关键控制路径' : isKeyPath ? '关键控制路径/summary 强制保留' : '默认展示关系',
    `关系类型：${relationType}`,
    ratio !== null ? `持股/控制比例：${formatPercent(ratio)}` : null,
    edge?.control_basis ? `控制依据：${edge.control_basis}` : null,
    edge?.relation_role ? `关系角色：${edge.relation_role}` : null,
    edge?.confidence_level ? `置信度：${edge.confidence_level}` : null,
  ].filter(Boolean)
}

function buildSyntheticEdgeTooltip(sourceNode, targetNode, isPrimaryPath) {
  return [
    `${safeText(sourceNode?.name || sourceNode?.id)} → ${safeText(targetNode?.name || targetNode?.id)}`,
    isPrimaryPath ? '主关键控制路径' : 'summary/control_path 强制保留',
    '关系类型：summary path',
  ]
}

function buildEdges({ selectedEdges, keyContext, nodes, rawEdges }) {
  const nodeMap = new Map(nodes.map((node) => [toKey(node.id), node]))
  const edgeMap = new Map()

  const addEdgeModel = (edgeModel) => {
    const key = edgeModel.id || `${edgeModel.source}->${edgeModel.target}:${edgeModel.kind}`
    if (!edgeMap.has(key) && nodeMap.has(toKey(edgeModel.source)) && nodeMap.has(toKey(edgeModel.target))) {
      edgeMap.set(key, edgeModel)
    }
  }

  selectedEdges.forEach((edge) => {
    const source = toKey(edge?.from_entity_id)
    const target = toKey(edge?.to_entity_id)
    const relationType = edgeRelationType(edge)
    const isKeyPath = isEdgeInKeyContext(edge, keyContext)
    const isPrimaryPath = isEdgePrimary(edge, keyContext)

    addEdgeModel({
      id: getEdgeId(edge) || `${source}->${target}:${relationType}`,
      source,
      target,
      kind: isPrimaryPath ? 'primary' : 'support',
      relationType,
      isKeyPath,
      isPrimaryPath,
      ratio: getEdgeRatio(edge),
      tooltipTitle: isPrimaryPath
        ? '主关键控制路径'
        : isKeyPath
          ? '关键控制关系'
          : '控制结构关系',
      tooltipLines: buildRawEdgeTooltip(edge, { isKeyPath, isPrimaryPath }),
    })
  })

  keyContext.normalizedPaths.forEach((path) => {
    path.steps.forEach((step, index) => {
      const nextStep = path.steps[index + 1]
      if (!nextStep) {
        return
      }
      const existingRawEdge = findRawEdgeForPair(rawEdges, step.id, nextStep.id)
      const pathIsPrimary = path.isPrimary
      const edgeKey = existingRawEdge
        ? getEdgeId(existingRawEdge) || `${toKey(step.id)}->${toKey(nextStep.id)}:${edgeRelationType(existingRawEdge)}`
        : `summary:${toKey(step.id)}->${toKey(nextStep.id)}`

      if (edgeMap.has(edgeKey)) {
        return
      }

      const sourceNode = nodeMap.get(toKey(step.id))
      const targetNode = nodeMap.get(toKey(nextStep.id))
      addEdgeModel({
        id: edgeKey,
        source: toKey(step.id),
        target: toKey(nextStep.id),
        kind: pathIsPrimary ? 'primary' : 'support',
        relationType: existingRawEdge ? edgeRelationType(existingRawEdge) : 'summary_path',
        isKeyPath: true,
        isPrimaryPath: pathIsPrimary,
        ratio: existingRawEdge ? getEdgeRatio(existingRawEdge) : null,
        tooltipTitle: pathIsPrimary ? '主关键控制路径' : 'summary 控制路径',
        tooltipLines: buildSyntheticEdgeTooltip(sourceNode, targetNode, pathIsPrimary),
      })
    })
  })

  return Array.from(edgeMap.values())
}

function buildBranches(edges, mainPathNodeIds) {
  const mainPathSet = new Set(mainPathNodeIds.map((id) => toKey(id)))
  const branches = new Map()

  edges.forEach((edge) => {
    const source = toKey(edge.source)
    const target = toKey(edge.target)
    if (!source || !target || mainPathSet.has(source)) {
      return
    }
    if (!branches.has(source) || mainPathSet.has(target)) {
      branches.set(source, {
        nodeId: source,
        attachmentNodeId: target,
      })
    }
  })

  return Array.from(branches.values())
}

function buildPlaceholder({ controlAnalysis = {} }) {
  const relationshipCount = Array.isArray(controlAnalysis?.control_relationships)
    ? controlAnalysis.control_relationships.length
    : 0

  return {
    hasDiagram: false,
    viewMode: 'Adaptive Control Structure',
    placeholderTitle: '暂无可展示的控制结构图',
    placeholderDescription:
      relationshipCount > 0
        ? '已识别控制关系，但缺少可稳定生成图形的路径或实体标识。'
        : '当前 summary 中尚无可用于生成控制结构图的控制关系。',
    nodes: [],
    edges: [],
    branches: [],
    mainPathNodeIds: [],
    omittedRelationshipCount: relationshipCount,
    filterSummary: {
      mode: 'empty',
      directUpstreamCount: 0,
      candidateNodeCount: 0,
      selectedDirectUpstreamCount: 0,
      omittedDirectUpstreamCount: 0,
      equityRatioThreshold: ADAPTIVE_CONTROL_GRAPH_FILTER_CONFIG.equityRatioThreshold,
      maxDirectUpstreamNodes: ADAPTIVE_CONTROL_GRAPH_FILTER_CONFIG.maxDirectUpstreamNodes,
    },
  }
}

export function buildControlChainDiagramModel({
  company = {},
  controlAnalysis = {},
  countryAttribution = {},
  relationshipGraph = {},
  filterConfig = {},
} = {}) {
  const config = {
    ...ADAPTIVE_CONTROL_GRAPH_FILTER_CONFIG,
    ...filterConfig,
  }
  const relationships = Array.isArray(controlAnalysis?.control_relationships)
    ? controlAnalysis.control_relationships
    : []
  const actualController = pickActualController(controlAnalysis)
  const focusedRelationship = pickFocusedRelationship(controlAnalysis, actualController)
  const primaryRelationship = actualController || focusedRelationship

  if (!primaryRelationship) {
    return buildPlaceholder({ controlAnalysis })
  }

  const rawEdges = Array.isArray(relationshipGraph?.edges) ? relationshipGraph.edges : []
  const entityLookup = buildEntityLookup(relationshipGraph)
  const firstPath = getControlPaths(primaryRelationship)[0] || null
  const targetInfo = resolveTargetInfo({ company, relationshipGraph, primaryPathItem: firstPath })
  const context = {
    entityLookup,
    targetInfo,
  }
  const primaryPath = normalizeRelationshipPath(primaryRelationship, context, 0)
  const primarySteps = primaryPath.steps

  if (primarySteps.length < 2) {
    return buildPlaceholder({ controlAnalysis })
  }

  const primaryRelationshipKey = getRelationshipKey(primaryRelationship)
  const keyRelationships = relationships.some(
    (relationship) => getRelationshipKey(relationship) === primaryRelationshipKey,
  )
    ? relationships
    : [primaryRelationship, ...relationships]
  const keyContext = buildKeyControlContext({
    relationships: keyRelationships,
    primaryRelationship,
    context,
  })
  const mainPathNodeIds = primarySteps.map((step) => toKey(step.id)).filter(Boolean)
  const primaryPathSet = new Set(mainPathNodeIds)
  const directGroups = sortDirectUpstreamGroups(
    groupDirectUpstreamEdges(rawEdges, targetInfo.id, keyContext),
    entityLookup,
  )
  const candidateNodeIds = new Set([...keyContext.forcedNodeIds, ...directGroups.map((group) => group.sourceId)])
  const mode = classifyDisplayMode({
    directUpstreamCount: directGroups.length,
    candidateNodeCount: candidateNodeIds.size,
    config,
  })
  const selectedDirectGroups = selectDirectUpstreamGroups({
    groups: directGroups,
    mode,
    config,
    forcedNodeIds: keyContext.forcedNodeIds,
  })
  const selectedGraph = collectSelectedGraph({
    rawEdges,
    directGroups,
    selectedDirectGroups,
    keyContext,
    mode,
  })
  const nodes = buildNodes({
    selectedNodeIds: selectedGraph.selectedNodeIds,
    targetInfo,
    entityLookup,
    keyContext,
    primaryPathSet,
    actualController,
    focusedRelationship,
    countryAttribution,
    selectedDirectGroups,
  })
  const edges = buildEdges({
    selectedEdges: selectedGraph.selectedEdges,
    keyContext,
    nodes,
    rawEdges,
  })
  const branches = buildBranches(edges, mainPathNodeIds)
  const basisSummary = formatBasis(primaryRelationship?.basis)
  const filterSummary = {
    mode,
    directUpstreamCount: directGroups.length,
    candidateNodeCount: candidateNodeIds.size,
    selectedDirectUpstreamCount: selectedGraph.selectedDirectUpstreamCount,
    omittedDirectUpstreamCount: selectedGraph.omittedDirectUpstreamCount,
    equityRatioThreshold: config.equityRatioThreshold,
    maxDirectUpstreamNodes: config.maxDirectUpstreamNodes,
    smallGraphMaxUpstream: config.smallGraphMaxUpstream,
    smallGraphMaxCandidateNodes: config.smallGraphMaxCandidateNodes,
    mediumGraphMaxUpstream: config.mediumGraphMaxUpstream,
    mediumGraphMaxCandidateNodes: config.mediumGraphMaxCandidateNodes,
    forcedNodeCount: keyContext.forcedNodeIds.size,
    forcedEdgeCount: keyContext.forcedEdgeIds.size + keyContext.forcedPairs.size,
    nonEquityPolicy:
      'non-equity relations are retained when they are on key paths, referenced by summary/control_relationships, or carry explicit control-basis metadata',
  }

  return {
    hasDiagram: true,
    viewMode: `Adaptive Control Structure: ${mode}`,
    sourceMode: 'adaptive-relationship-graph',
    primaryDataSource: 'relationship-graph + summary/control_relationships',
    supplementaryDataSource: 'summary/control_path forced retention',
    targetName: targetInfo.name,
    actualControllerName: safeText(actualController?.controller_name, EMPTY_TEXT),
    focusedControllerName: safeText(focusedRelationship?.controller_name, EMPTY_TEXT),
    actualControlCountry: safeText(countryAttribution?.actual_control_country, '未识别'),
    attributionType: safeText(countryAttribution?.attribution_type, EMPTY_TEXT),
    basisSummary,
    nodes,
    edges,
    branches,
    mainPathNodeIds,
    omittedRelationshipCount: selectedGraph.omittedDirectUpstreamCount,
    supportCandidateCount: directGroups.length,
    filterSummary,
    notes: [
      '简单结构默认尽量全展示主要直接上游主体。',
      `普通 equity 默认阈值为 ${formatRatioDecimal(config.equityRatioThreshold)}，仅用于普通股权关系筛选。`,
      'actual controller、target、focused candidate、summary/control_path 节点和边始终强制保留。',
      'agreement / board_control / voting_right / nominee / vie 不按股权比例机械删除。',
    ],
    legend: [
      { key: 'actualController', label: ROLE_LABELS.actualController },
      { key: 'intermediate', label: ROLE_LABELS.intermediate },
      { key: 'target', label: ROLE_LABELS.target },
      { key: 'support', label: ROLE_LABELS.support },
    ],
  }
}
