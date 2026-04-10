import {
  CONTROL_GRAPH_NODE_SIZES,
  computeHierarchicalControlGraphLayout,
} from './controlGraphLayout.js'

const EMPTY_TEXT = '暂无'

const ENTITY_TYPE_STYLES = {
  company: {
    key: 'company',
    name: 'company',
    label: '公司主体',
    color: '#2563eb',
    borderColor: '#1d4ed8',
  },
  person: {
    key: 'person',
    name: 'person',
    label: '自然人',
    color: '#dc2626',
    borderColor: '#991b1b',
  },
  fund: {
    key: 'fund',
    name: 'fund',
    label: '基金/公众持股',
    color: '#16a34a',
    borderColor: '#15803d',
  },
  government: {
    key: 'government',
    name: 'government',
    label: '政府/主权主体',
    color: '#ea580c',
    borderColor: '#c2410c',
  },
  other: {
    key: 'other',
    name: 'other',
    label: '其他主体',
    color: '#64748b',
    borderColor: '#475569',
  },
}

const ROLE_STYLES = {
  target: {
    key: 'target',
    label: 'target company',
    color: '#0f172a',
    description: '目标公司',
  },
  focused: {
    key: 'focused',
    label: 'focused controller / candidate',
    color: '#7c3aed',
    description: '当前关注控制人/候选控制人',
  },
  actualController: {
    key: 'actualController',
    label: 'actual controller',
    color: '#be123c',
    description: '实际控制人',
  },
}

const EDGE_TYPE_STYLES = {
  equity: {
    key: 'equity',
    label: 'equity',
    color: '#111827',
    lineType: 'solid',
    description: '股权控制/持股关系',
  },
  agreement: {
    key: 'agreement',
    label: 'agreement',
    color: '#7c3aed',
    lineType: 'dashed',
    description: '协议控制',
  },
  board_control: {
    key: 'board_control',
    label: 'board_control',
    color: '#ea580c',
    lineType: 'solid',
    description: '董事会/席位控制',
  },
  voting_right: {
    key: 'voting_right',
    label: 'voting_right',
    color: '#0f766e',
    lineType: 'dotted',
    description: '表决权安排',
  },
  nominee: {
    key: 'nominee',
    label: 'nominee',
    color: '#be185d',
    lineType: 'dashed',
    description: '代持/名义持有人',
  },
  vie: {
    key: 'vie',
    label: 'vie',
    color: '#0891b2',
    lineType: 'dashed',
    description: 'VIE 结构',
  },
  other: {
    key: 'other',
    label: 'other',
    color: '#94a3b8',
    lineType: 'dashed',
    description: '其他关系',
  },
}

const EDGE_TYPE_ORDER = [
  'equity',
  'agreement',
  'board_control',
  'voting_right',
  'nominee',
  'vie',
  'other',
]

const ROLE_DISPLAY = {
  target: 'target company',
  focused: 'focused controller / candidate',
  actualController: 'actual controller',
  normal: 'normal',
}

function safeText(value, fallback = EMPTY_TEXT) {
  if (value === null || value === undefined) {
    return fallback
  }
  const rendered = String(value).trim()
  return rendered || fallback
}

function sameEntityId(left, right) {
  if (left === null || left === undefined || right === null || right === undefined) {
    return false
  }
  return String(left) === String(right)
}

function entityKey(value) {
  return value === null || value === undefined ? '' : String(value)
}

function normalizeEntityType(value) {
  const normalized = safeText(value, 'other').trim().toLowerCase()
  return ENTITY_TYPE_STYLES[normalized] ? normalized : 'other'
}

function normalizeEdgeType(edge) {
  const rawType = safeText(edge?.relation_type || edge?.control_type, 'other')
    .trim()
    .toLowerCase()
  return EDGE_TYPE_STYLES[rawType] ? rawType : 'other'
}

function truncateLabel(value, maxLength = 24) {
  const rendered = safeText(value, '未命名主体')
  return rendered.length > maxLength ? `${rendered.slice(0, maxLength - 1)}…` : rendered
}

export function formatGraphPercent(value) {
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

function firstNonEmpty(...values) {
  return values.find((value) => safeText(value, '') !== '') ?? null
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

function extractControlPaths(relationship) {
  const paths = Array.isArray(relationship?.control_path) ? relationship.control_path : []
  return paths.slice(0, 3).map((path, index) => {
    const names = Array.isArray(path?.path_entity_names) ? path.path_entity_names : []
    const entityIds = Array.isArray(path?.path_entity_ids) ? path.path_entity_ids : []
    const edgeIds = Array.isArray(path?.edge_ids) ? path.edge_ids : []
    const edgeIdsFromEdges = Array.isArray(path?.edges)
      ? path.edges.map((edge) => edge?.structure_id ?? edge?.id).filter(Boolean)
      : []

    return {
      id: `path-${index}`,
      label: names.length ? names.join(' → ') : `关键路径 ${index + 1}`,
      entityIds,
      edgeIds: [...new Set([...edgeIds, ...edgeIdsFromEdges])],
      pathScore: path?.path_score_pct || path?.path_score || null,
    }
  })
}

function normalizePathDirection(entityIds, { actualControllerEntityId, focusedControllerEntityId, targetEntityId }) {
  let keys = entityIds.map((entityId) => entityKey(entityId)).filter(Boolean)

  if (!keys.length) {
    return []
  }

  if (
    targetEntityId !== null &&
    targetEntityId !== undefined &&
    sameEntityId(keys[0], targetEntityId) &&
    !sameEntityId(keys[keys.length - 1], targetEntityId)
  ) {
    keys = [...keys].reverse()
  }

  const anchorKey = actualControllerEntityId ?? focusedControllerEntityId ?? null
  const anchorIndex = anchorKey !== null ? keys.findIndex((key) => sameEntityId(key, anchorKey)) : -1
  if (anchorIndex > 0) {
    keys = keys.slice(anchorIndex)
  }

  if (targetEntityId !== null && targetEntityId !== undefined) {
    const targetIndex = keys.findIndex((key) => sameEntityId(key, targetEntityId))
    if (targetIndex >= 0 && targetIndex < keys.length - 1) {
      keys = keys.slice(0, targetIndex + 1)
    }
    if (!sameEntityId(keys[keys.length - 1], targetEntityId)) {
      keys = [...keys, entityKey(targetEntityId)]
    }
  }

  return keys.filter((key, index) => key && (index === 0 || key !== keys[index - 1]))
}

function findDirectedEntityPath(edges = [], startEntityId, targetEntityId) {
  const startKey = entityKey(startEntityId)
  const targetKey = entityKey(targetEntityId)
  if (!startKey || !targetKey) {
    return []
  }

  const outgoingMap = new Map()
  edges.forEach((edge) => {
    const sourceKey = entityKey(edge.from_entity_id)
    if (!sourceKey) {
      return
    }
    if (!outgoingMap.has(sourceKey)) {
      outgoingMap.set(sourceKey, [])
    }
    outgoingMap.get(sourceKey).push(edge)
  })

  const queue = [[startKey]]
  const visited = new Set([startKey])

  while (queue.length) {
    const path = queue.shift()
    const currentKey = path[path.length - 1]

    for (const edge of outgoingMap.get(currentKey) || []) {
      const nextKey = entityKey(edge.to_entity_id)
      if (!nextKey || visited.has(nextKey)) {
        continue
      }

      const nextPath = [...path, nextKey]
      if (sameEntityId(nextKey, targetKey)) {
        return nextPath
      }

      visited.add(nextKey)
      queue.push(nextPath)
    }
  }

  return []
}

function pickPrimaryControlPath(paths, context) {
  const normalizedPaths = paths
    .map((path) => ({
      ...path,
      normalizedEntityIds: normalizePathDirection(path.entityIds, context),
    }))
    .filter((path) => path.normalizedEntityIds.length > 1)

  const primaryPath =
    normalizedPaths.find((path) =>
      path.normalizedEntityIds.some((entityId) => sameEntityId(entityId, context.actualControllerEntityId)),
    ) ||
    normalizedPaths.find((path) =>
      path.normalizedEntityIds.some((entityId) => sameEntityId(entityId, context.focusedControllerEntityId)),
    ) ||
    normalizedPaths[0] ||
    null

  if (primaryPath) {
    return primaryPath
  }

  const fallbackStart = context.actualControllerEntityId ?? context.focusedControllerEntityId
  const fallbackPath = findDirectedEntityPath(context.edges, fallbackStart, context.targetEntityId)
  if (fallbackPath.length > 1) {
    return {
      id: 'fallback-primary-path',
      entityIds: fallbackPath,
      normalizedEntityIds: fallbackPath,
      edgeIds: [],
    }
  }

  if (fallbackStart !== null && fallbackStart !== undefined && context.targetEntityId !== null && context.targetEntityId !== undefined) {
    const directFallbackPath = [entityKey(fallbackStart), entityKey(context.targetEntityId)]
    return {
      id: 'fallback-primary-path',
      entityIds: directFallbackPath,
      normalizedEntityIds: directFallbackPath,
      edgeIds: [],
      visualOnly: true,
    }
  }

  return null
}

function addPathPairs(pairs, entityIds) {
  for (let index = 0; index < entityIds.length - 1; index += 1) {
    pairs.add(`${entityIds[index]}->${entityIds[index + 1]}`)
  }
}

function buildKeyPathSets(paths, context) {
  const edgeIds = new Set()
  const entityIds = new Set()
  const pairs = new Set()
  const primaryEdgeIds = new Set()
  const primaryEntityIds = new Set()
  const primaryPairs = new Set()
  const primaryPath = pickPrimaryControlPath(paths, context)
  const primaryPathEntityIds = primaryPath?.normalizedEntityIds || []

  paths.forEach((path) => {
    path.edgeIds.forEach((edgeId) => edgeIds.add(String(edgeId)))
    const normalizedEntityIds = normalizePathDirection(path.entityIds, context)
    normalizedEntityIds.forEach((entityId) => entityIds.add(String(entityId)))
    addPathPairs(pairs, normalizedEntityIds)
  })

  if (primaryPath) {
    ;(primaryPath.edgeIds || []).forEach((edgeId) => primaryEdgeIds.add(String(edgeId)))
    primaryPathEntityIds.forEach((entityId) => primaryEntityIds.add(String(entityId)))
    if (!primaryPath.visualOnly) {
      addPathPairs(primaryPairs, primaryPathEntityIds)
    }
    primaryPathEntityIds.forEach((entityId) => entityIds.add(String(entityId)))
    primaryPairs.forEach((pair) => pairs.add(pair))
  }

  return {
    edgeIds,
    entityIds,
    pairs,
    primaryEdgeIds,
    primaryEntityIds,
    primaryPairs,
    primaryPathEntityIds,
  }
}

function buildBasisSummary(relationship) {
  const basis = relationship?.basis
  if (!basis) {
    return ''
  }

  if (typeof basis === 'string') {
    return basis
  }

  if (typeof basis !== 'object') {
    return String(basis)
  }

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

function buildDegreeMap(nodes = [], edges = []) {
  const degreeMap = new Map(nodes.map((node) => [entityKey(node.entity_id), 0]))

  edges.forEach((edge) => {
    const fromKey = entityKey(edge.from_entity_id)
    const toKey = entityKey(edge.to_entity_id)
    degreeMap.set(fromKey, (degreeMap.get(fromKey) || 0) + 1)
    degreeMap.set(toKey, (degreeMap.get(toKey) || 0) + 1)
  })

  return degreeMap
}

function getNodeRoles(node, { targetEntityId, actualControllerEntityId, focusedControllerEntityId, keyEntityIds }) {
  const roles = []
  const nodeEntityId = node?.entity_id

  if (node?.is_root || sameEntityId(nodeEntityId, targetEntityId)) {
    roles.push('target')
  }
  if (sameEntityId(nodeEntityId, focusedControllerEntityId)) {
    roles.push('focused')
  }
  if (sameEntityId(nodeEntityId, actualControllerEntityId)) {
    roles.push('actualController')
  }
  if (
    keyEntityIds?.has(entityKey(nodeEntityId)) &&
    !roles.includes('target') &&
    !roles.includes('actualController') &&
    !roles.includes('focused')
  ) {
    roles.push('focused')
  }

  return [...new Set(roles)]
}

function cloneNodeSize(size) {
  return Array.isArray(size) ? [...size] : [size, size]
}

function getFixedNodeSize(roles) {
  if (roles.includes('target')) {
    return cloneNodeSize(CONTROL_GRAPH_NODE_SIZES.target)
  }
  if (roles.includes('actualController')) {
    return cloneNodeSize(CONTROL_GRAPH_NODE_SIZES.actualController)
  }
  if (roles.includes('focused')) {
    return cloneNodeSize(CONTROL_GRAPH_NODE_SIZES.focused)
  }
  return cloneNodeSize(CONTROL_GRAPH_NODE_SIZES.default)
}

function buildNodeStyle(node, roles, degree) {
  const entityType = normalizeEntityType(node?.entity_type)
  const entityStyle = ENTITY_TYPE_STYLES[entityType]
  const isTarget = roles.includes('target')
  const isActualController = roles.includes('actualController')
  const isFocused = roles.includes('focused')
  const isKeyNode = isFocused || isActualController || isTarget

  let borderColor = entityStyle.borderColor
  let borderWidth = 1.8
  const symbolSize = getFixedNodeSize(roles)

  if (isFocused) {
    borderColor = ROLE_STYLES.focused.color
    borderWidth = 4
  }
  if (isActualController) {
    borderColor = ROLE_STYLES.actualController.color
    borderWidth = 6
  }
  if (isTarget) {
    borderColor = ROLE_STYLES.target.color
    borderWidth = 4
  }

  return {
    entityType,
    symbolSize,
    symbol: isTarget ? 'roundRect' : 'circle',
    itemStyle: {
      color: entityStyle.color,
      borderColor,
      borderWidth,
      shadowBlur: isKeyNode ? 24 : 8,
      shadowColor: isActualController
        ? 'rgba(190, 18, 60, 0.32)'
        : isFocused
          ? 'rgba(124, 58, 237, 0.24)'
          : isTarget
            ? 'rgba(15, 23, 42, 0.22)'
            : 'rgba(71, 85, 105, 0.14)',
    },
  }
}

function buildSyntheticActualController(actualController, countryAttribution) {
  if (!actualController?.controller_entity_id) {
    return null
  }

  return {
    id: actualController.controller_entity_id,
    entity_id: actualController.controller_entity_id,
    entity_name: actualController.controller_name || `Entity ${actualController.controller_entity_id}`,
    name: actualController.controller_name || `Entity ${actualController.controller_entity_id}`,
    entity_type: actualController.controller_type || 'other',
    country: countryAttribution?.actual_control_country || null,
    company_id: null,
    identifier_code: null,
    is_listed: false,
    notes: 'synthetic_actual_controller_from_summary',
    is_root: false,
    is_synthetic_actual_controller: true,
  }
}

function buildSummaryItems({
  actualController,
  focusedRelationship,
  countryAttribution,
  controllerCount,
  nodeCount,
  edgeCount,
  relationTypes,
}) {
  return [
    {
      label: 'actual controller',
      value: safeText(actualController?.controller_name),
      highlight: true,
    },
    {
      label: 'focused controller / candidate',
      value: safeText(focusedRelationship?.controller_name),
    },
    {
      label: 'control type',
      value: safeText(
        firstNonEmpty(actualController?.control_type, focusedRelationship?.control_type),
      ),
    },
    {
      label: 'attribution type',
      value: safeText(countryAttribution?.attribution_type),
    },
    {
      label: 'actual control country',
      value: safeText(countryAttribution?.actual_control_country, '未识别'),
      highlight: true,
    },
    {
      label: 'controllers in result set',
      value: controllerCount,
    },
    {
      label: 'nodes / edges',
      value: `${nodeCount} / ${edgeCount}`,
    },
    {
      label: 'relation types present',
      value: relationTypes.length ? relationTypes.join(', ') : EMPTY_TEXT,
    },
  ]
}

function buildLegend() {
  return {
    entityTypes: Object.values(ENTITY_TYPE_STYLES),
    roles: [ROLE_STYLES.target, ROLE_STYLES.focused, ROLE_STYLES.actualController],
    edgeTypes: EDGE_TYPE_ORDER.filter((key) => key !== 'other').map((key) => EDGE_TYPE_STYLES[key]),
  }
}

export function buildRelationshipGraphModel(graphData, options = {}) {
  const controlAnalysis = options.controlAnalysis || {}
  const countryAttribution = options.countryAttribution || {}
  const rawNodes = Array.isArray(graphData?.nodes) ? graphData.nodes : []
  const rawEdges = Array.isArray(graphData?.edges) ? graphData.edges : []
  const actualController = pickActualController(controlAnalysis) || {}
  const focusedRelationship = pickFocusedRelationship(controlAnalysis, actualController)
  const actualControllerEntityId =
    options.actualControllerEntityId ?? actualController?.controller_entity_id ?? null
  const focusedControllerEntityId =
    options.focusedControllerEntityId ?? focusedRelationship?.controller_entity_id ?? actualControllerEntityId
  const targetEntityId =
    graphData?.target_entity_id ?? rawNodes.find((node) => node?.is_root)?.entity_id ?? null
  const keyControlPaths = extractControlPaths(focusedRelationship || actualController)
  const keyPathSets = buildKeyPathSets(keyControlPaths, {
    actualControllerEntityId,
    focusedControllerEntityId,
    targetEntityId,
    edges: rawEdges,
  })
  const dataWarnings = []

  const actualControllerMatched =
    actualControllerEntityId !== null &&
    actualControllerEntityId !== undefined &&
    rawNodes.some((node) => sameEntityId(node?.entity_id, actualControllerEntityId))

  let nodes = rawNodes
  if (
    actualControllerEntityId !== null &&
    actualControllerEntityId !== undefined &&
    safeText(actualController?.controller_name, '') &&
    !actualControllerMatched
  ) {
    const syntheticNode = buildSyntheticActualController(actualController, countryAttribution)
    if (syntheticNode) {
      nodes = [...rawNodes, syntheticNode]
      dataWarnings.push('图数据中未匹配到 actual controller 节点，已使用 summary 结果降级展示。')
    }
  }

  if (
    safeText(actualController?.controller_name, '') &&
    (actualControllerEntityId === null || actualControllerEntityId === undefined)
  ) {
    dataWarnings.push('summary 中存在 actual controller 名称，但缺少 controller_entity_id，无法在图中稳定匹配节点。')
  }

  const degreeMap = buildDegreeMap(nodes, rawEdges)

  const adaptedNodes = nodes.map((node) => {
    const roles = getNodeRoles(node, {
      targetEntityId,
      actualControllerEntityId,
      focusedControllerEntityId,
      keyEntityIds: keyPathSets.entityIds,
    })
    const degree = degreeMap.get(entityKey(node.entity_id)) || 0
    const style = buildNodeStyle(node, roles, degree)
    const fullName = node.name || node.entity_name || `Entity ${node.entity_id}`
    const maxLabelLength = roles.includes('actualController') || roles.includes('target') ? 24 : 18
    const isMajorNode = roles.includes('actualController') || roles.includes('target')

    return {
      id: entityKey(node.entity_id),
      name: fullName,
      displayLabel: truncateLabel(fullName, maxLabelLength),
      categoryKey: style.entityType,
      category: Object.keys(ENTITY_TYPE_STYLES).indexOf(style.entityType),
      symbol: style.symbol,
      symbolSize: style.symbolSize,
      value: degree,
      draggable: false,
      itemStyle: style.itemStyle,
      label: {
        show: true,
        position: roles.includes('target') ? 'bottom' : 'top',
        distance: isMajorNode ? 11 : 8,
        width: isMajorNode ? 166 : 124,
        overflow: 'truncate',
        fontSize: isMajorNode ? 12 : 10.5,
        fontWeight: isMajorNode ? 700 : 500,
      },
      raw: {
        ...node,
        roles: roles.length ? roles : ['normal'],
        role: roles[0] || 'normal',
        entityType: style.entityType,
        degree,
      },
    }
  })

  const layoutResult = computeHierarchicalControlGraphLayout({
    nodes: adaptedNodes,
    edges: rawEdges,
    targetEntityId,
    keyPaths: keyControlPaths,
    keyEntityIds: keyPathSets.entityIds,
    primaryPathEntityIds: keyPathSets.primaryPathEntityIds,
  })

  const relationTypes = [
    ...new Set(rawEdges.map((edge) => normalizeEdgeType(edge)).filter(Boolean)),
  ].sort((left, right) => EDGE_TYPE_ORDER.indexOf(left) - EDGE_TYPE_ORDER.indexOf(right))

  const positionedNodeMap = new Map(layoutResult.nodes.map((node) => [entityKey(node.id), node]))
  const hasKeyPaths = keyPathSets.edgeIds.size > 0 || keyPathSets.pairs.size > 0
  const adaptedLinks = rawEdges.map((edge) => {
    const edgeType = normalizeEdgeType(edge)
    const edgeStyle = EDGE_TYPE_STYLES[edgeType] || EDGE_TYPE_STYLES.other
    const edgeId = String(edge.structure_id ?? edge.id)
    const pairKey = `${edge.from_entity_id}->${edge.to_entity_id}`
    const isKeyPath = keyPathSets.edgeIds.has(edgeId) || keyPathSets.pairs.has(pairKey)
    const isPrimaryPath = keyPathSets.primaryEdgeIds.has(edgeId) || keyPathSets.primaryPairs.has(pairKey)
    const isConnectedToActual =
      sameEntityId(edge.from_entity_id, actualControllerEntityId) ||
      sameEntityId(edge.to_entity_id, actualControllerEntityId)
    const sourceNode = positionedNodeMap.get(entityKey(edge.from_entity_id))
    const targetNode = positionedNodeMap.get(entityKey(edge.to_entity_id))
    const sourceColumn = sourceNode?.raw?.gridColumn ?? 0
    const targetColumn = targetNode?.raw?.gridColumn ?? 0
    const isSameVisualRow = sourceNode?.raw?.visualRow === targetNode?.raw?.visualRow
    const isMainColumnEdge = sourceColumn === 0 && targetColumn === 0
    const curveness = isPrimaryPath || isMainColumnEdge ? 0 : isSameVisualRow ? 0.18 : 0.06

    return {
      source: entityKey(edge.from_entity_id),
      target: entityKey(edge.to_entity_id),
      value: edgeType,
      lineStyle: {
        color: isPrimaryPath ? '#be123c' : isKeyPath ? '#e11d48' : edgeStyle.color,
        type: edgeStyle.lineType,
        width: isPrimaryPath ? 5 : isKeyPath ? 3.4 : isConnectedToActual ? 2.2 : edge.has_numeric_ratio ? 1.8 : 1.2,
        curveness,
        opacity: isPrimaryPath ? 0.96 : hasKeyPaths && !isKeyPath ? 0.3 : 0.68,
      },
      emphasis: {
        lineStyle: {
          width: isPrimaryPath ? 6 : isKeyPath ? 4.4 : 3,
          opacity: 1,
        },
      },
      raw: {
        ...edge,
        relationType: edgeType,
        isKeyPath,
        isPrimaryPath,
        isConnectedToActual,
      },
    }
  })

  const controllerCount =
    controlAnalysis?.controller_count ??
    (Array.isArray(controlAnalysis?.control_relationships)
      ? controlAnalysis.control_relationships.length
      : 0)
  const nodeCount = adaptedNodes.length
  const edgeCount = adaptedLinks.length
  const basisSummary = buildBasisSummary(focusedRelationship || actualController)

  return {
    companyId: graphData?.company_id ?? null,
    targetEntityId,
    targetCompanyName:
      graphData?.target_company?.name ||
      nodes.find((node) => node.is_root)?.name ||
      nodes.find((node) => sameEntityId(node.entity_id, targetEntityId))?.name ||
      EMPTY_TEXT,
    nodeCount,
    edgeCount,
    hasData: adaptedNodes.length > 0,
    hasKeyPaths,
    actualControllerMatched:
      !actualControllerEntityId || actualControllerMatched || nodes.some((node) => node.is_synthetic_actual_controller),
    message: graphData?.message || '',
    dataWarnings,
    summaryItems: buildSummaryItems({
      actualController,
      focusedRelationship,
      countryAttribution,
      controllerCount,
      nodeCount,
      edgeCount,
      relationTypes,
    }),
    keyControlPaths,
    basisSummary,
    legend: buildLegend(),
    categories: Object.values(ENTITY_TYPE_STYLES).map((style) => ({ name: style.name })),
    layoutMeta: layoutResult.layoutMeta,
    nodes: layoutResult.nodes,
    links: adaptedLinks,
  }
}

export function formatNodeTooltip(node) {
  const raw = node?.raw || {}
  const roles = Array.isArray(raw.roles) && raw.roles.length ? raw.roles : ['normal']
  const lines = [
    `<strong>${safeText(node?.name || raw.entity_name, '未命名主体')}</strong>`,
    `entity_id：${safeText(raw.entity_id)}`,
    `entity_type：${safeText(raw.entity_type || raw.entityType)}`,
    `role：${roles.map((role) => ROLE_DISPLAY[role] || role).join(' / ')}`,
    `country：${safeText(raw.country)}`,
    `mapped company_id：${safeText(raw.company_id)}`,
    `identifier_code：${safeText(raw.identifier_code)}`,
    `相邻边数量：${raw.degree ?? 0}`,
  ]

  if (raw.is_synthetic_actual_controller) {
    lines.push('说明：该节点由 summary.actual_controller 降级补充。')
  }

  return lines.join('<br/>')
}

export function formatEdgeTooltip(edge) {
  const raw = edge?.raw || {}
  const ratio = firstNonEmpty(raw.holding_ratio, raw.control_ratio)
  const lines = [
    `<strong>${safeText(raw.from_entity_name || raw.from_entity_id)} → ${safeText(
      raw.to_entity_name || raw.to_entity_id,
    )}</strong>`,
    `relation type：${safeText(raw.relation_type || raw.relationType)}`,
    `control type：${safeText(raw.control_type)}`,
    `holding/control ratio：${formatGraphPercent(ratio)}`,
    `relation role：${safeText(raw.relation_role)}`,
    `control basis：${safeText(raw.control_basis)}`,
    `confidence：${safeText(raw.confidence_level)}`,
    `reporting period：${safeText(raw.reporting_period)}`,
    `key control path：${raw.isKeyPath ? 'yes' : 'no'}`,
  ]

  return lines.join('<br/>')
}
