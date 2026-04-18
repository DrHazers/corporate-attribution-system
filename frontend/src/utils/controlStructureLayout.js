export const CONTROL_STRUCTURE_LAYOUT_CONFIG = {
  direction: 'vertical_top_to_bottom',
  targetAnchor: 'main_axis_center',
  minWidth: 920,
  minHeight: 620,
  paddingX: 118,
  paddingY: 84,
  rowGap: 154,
  rootGap: 76,
  branchGap: 42,
  branchPadding: 16,
  mainAxisCorridorHalfWidth: 188,
  sideBranchGap: 88,
  nodeSize: {
    actualSummary: { width: 176, height: 72, radius: 36 },
    target: { width: 186, height: 72, radius: 10 },
    direct: { width: 166, height: 64, radius: 10 },
    focused: { width: 162, height: 62, radius: 10 },
    intermediate: { width: 154, height: 58, radius: 10 },
    support: { width: 146, height: 54, radius: 10 },
  },
}

function toKey(value) {
  return value === null || value === undefined ? '' : String(value)
}

function sameId(left, right) {
  return toKey(left) !== '' && toKey(left) === toKey(right)
}

function safeText(value, fallback = '') {
  if (value === null || value === undefined) {
    return fallback
  }
  const rendered = String(value).trim()
  return rendered || fallback
}

function normalizedRatioForComparison(value) {
  if (value === null || value === undefined || value === '') {
    return -1
  }
  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return -1
  }
  return numeric > 1 ? numeric / 100 : numeric
}

function isSemanticRelationType(value) {
  return new Set([
    'agreement',
    'agreement_control',
    'board_control',
    'voting_right',
    'nominee',
    'vie',
    'vie_control',
    'mixed_control',
    'joint_control',
  ]).has(String(value || '').toLowerCase())
}

function getNodeSize(role) {
  return (
    CONTROL_STRUCTURE_LAYOUT_CONFIG.nodeSize[role] ||
    CONTROL_STRUCTURE_LAYOUT_CONFIG.nodeSize.support
  )
}

function buildNodeMap(nodes = []) {
  return new Map((Array.isArray(nodes) ? nodes : []).map((node) => [toKey(node.id), node]))
}

function buildEdgeMap(edges = []) {
  return new Map((Array.isArray(edges) ? edges : []).map((edge) => [`${toKey(edge.source)}->${toKey(edge.target)}`, edge]))
}

function buildIncomingMap(edges = []) {
  const incoming = new Map()
  ;(Array.isArray(edges) ? edges : []).forEach((edge) => {
    const targetId = toKey(edge.target)
    if (!targetId) {
      return
    }
    if (!incoming.has(targetId)) {
      incoming.set(targetId, [])
    }
    incoming.get(targetId).push(edge)
  })
  return incoming
}

function buildKeyParentMap(model = {}) {
  const raw = model?.keyParentByNodeId || {}
  return new Map(Object.entries(raw).map(([key, value]) => [toKey(key), toKey(value)]))
}

function uniqueIds(ids = []) {
  return Array.from(new Set((Array.isArray(ids) ? ids : []).map((id) => toKey(id)).filter(Boolean)))
}

function buildMainPathContext(model = {}) {
  const targetId = toKey(model?.targetId)
  const summaryControllerId = toKey(model?.summaryControllerId)
  const keyPathIds = uniqueIds(model?.keyPathNodeIds)
  const nodeIds =
    keyPathIds.length >= 2 && (!targetId || keyPathIds[keyPathIds.length - 1] === targetId)
      ? keyPathIds
      : uniqueIds([summaryControllerId, targetId])
  const renderKeyById = new Map()
  const rowById = new Map()
  const indexById = new Map()
  const lastIndex = Math.max(0, nodeIds.length - 1)

  nodeIds.forEach((nodeId, index) => {
    indexById.set(nodeId, index)
    rowById.set(nodeId, index - lastIndex)
    renderKeyById.set(
      nodeId,
      nodeId === targetId ? 'target-node' : index === 0 ? 'summary-controller' : `main-path:${index}:${nodeId}`,
    )
  })

  return {
    nodeIds,
    nodeIdSet: new Set(nodeIds),
    renderKeyById,
    rowById,
    indexById,
    targetId,
    summaryControllerId,
  }
}

function isExpanded(expandedByNodeId = {}, nodeId) {
  return Boolean(expandedByNodeId?.[toKey(nodeId)])
}

function resolveTreeNodeRole(node, instance) {
  if (node?.isFocused) {
    return 'focused'
  }
  if (instance.depthFromTarget === 1) {
    return 'direct'
  }
  if (instance.onKeyPath) {
    return 'intermediate'
  }
  return 'support'
}

function sortUpstreamEdges(edges = [], nodeMap, downstreamId, keyParentByNodeId) {
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

    return safeText(nodeMap.get(toKey(left.source))?.name).localeCompare(
      safeText(nodeMap.get(toKey(right.source))?.name),
    )
  })
}

function rebuildInstanceTree({
  canonicalId,
  downstreamId,
  depthFromTarget,
  branchDirection = 'down',
  rootId,
  nodeMap,
  incomingMap,
  expandedByNodeId,
  keyParentByNodeId,
  excludedNodeIds = new Set(),
  lineage,
}) {
  const nodeId = toKey(canonicalId)
  const node = nodeMap.get(nodeId)
  if (!node) {
    return null
  }

  const eligibleEdges = sortUpstreamEdges(
    (incomingMap.get(nodeId) || []).filter((edge) => {
      const sourceId = toKey(edge.source)
      return sourceId && !lineage.has(sourceId) && !excludedNodeIds.has(sourceId)
    }),
    nodeMap,
    nodeId,
    keyParentByNodeId,
  )

  const nextLineage = new Set(lineage)
  nextLineage.add(nodeId)

  const onKeyPath = keyParentByNodeId.get(toKey(downstreamId)) === nodeId
  const expanded = isExpanded(expandedByNodeId, nodeId)
  const children = expanded
    ? eligibleEdges
        .map((edge) =>
          rebuildInstanceTree({
            canonicalId: edge.source,
            downstreamId: nodeId,
            depthFromTarget:
              branchDirection === 'up' ? depthFromTarget - 1 : depthFromTarget + 1,
            branchDirection,
            rootId,
            nodeMap,
            incomingMap,
            expandedByNodeId,
            keyParentByNodeId,
            excludedNodeIds,
            lineage: nextLineage,
          }),
        )
        .filter(Boolean)
    : []

  return {
    renderKey: `${branchDirection}:${rootId}:${depthFromTarget}:${nodeId}:${toKey(downstreamId)}`,
    canonicalId: nodeId,
    downstreamId: toKey(downstreamId),
    rootId: toKey(rootId),
    depthFromTarget,
    branchDirection,
    onKeyPath,
    expanded,
    expandable: eligibleEdges.length > 0,
    hiddenUpstreamCount: expanded ? Math.max(0, eligibleEdges.length - children.length) : eligibleEdges.length,
    children,
  }
}

function buildLowerRootInstances({
  model,
  nodeMap,
  incomingMap,
  expandedByNodeId,
  keyParentByNodeId,
  summaryControllerId,
  mainPathNodeIds = [],
  suppressedBranchNodeIds = [],
}) {
  const targetId = toKey(model?.targetId)
  const mainPathNodeIdSet = new Set(uniqueIds(mainPathNodeIds))
  const rootIds = (Array.isArray(model?.directUpstreamIds) ? model.directUpstreamIds : [])
    .map((id) => toKey(id))
    .filter((id) => id && id !== summaryControllerId && !mainPathNodeIdSet.has(id))
  const excludedNodeIds = new Set(
    [summaryControllerId, ...mainPathNodeIdSet, ...suppressedBranchNodeIds].filter(
      (id) => id && id !== targetId,
    ),
  )

  return rootIds
    .map((rootId) =>
      rebuildInstanceTree({
        canonicalId: rootId,
        downstreamId: targetId,
        depthFromTarget: 1,
        branchDirection: 'down',
        rootId,
        nodeMap,
        incomingMap,
        expandedByNodeId,
        keyParentByNodeId,
        excludedNodeIds,
        lineage: new Set([targetId]),
      }),
    )
    .filter(Boolean)
}

function mainPathExtraIncomingEdges({
  anchorId,
  incomingMap,
  nodeMap,
  keyParentByNodeId,
  excludedNodeIds = new Set(),
}) {
  const anchorKey = toKey(anchorId)
  const keyParentId = keyParentByNodeId.get(anchorKey)
  return sortUpstreamEdges(
    (incomingMap.get(anchorKey) || []).filter((edge) => {
      const sourceId = toKey(edge.source)
      return sourceId && sourceId !== keyParentId && !excludedNodeIds.has(sourceId)
    }),
    nodeMap,
    anchorKey,
    keyParentByNodeId,
  )
}

function buildMainPathBranchStats({
  mainPath,
  incomingMap,
  nodeMap,
  keyParentByNodeId,
  expandedByNodeId,
  suppressedBranchNodeIds = [],
}) {
  const stats = new Map()
  const excludedNodeIds = new Set([...mainPath.nodeIds, ...suppressedBranchNodeIds])

  mainPath.nodeIds.slice(0, -1).forEach((anchorId) => {
    const extraEdges = mainPathExtraIncomingEdges({
      anchorId,
      incomingMap,
      nodeMap,
      keyParentByNodeId,
      excludedNodeIds,
    })
    const expanded = isExpanded(expandedByNodeId, anchorId)
    stats.set(anchorId, {
      expandable: extraEdges.length > 0,
      expanded,
      hiddenUpstreamCount: expanded ? 0 : extraEdges.length,
    })
  })

  return stats
}

function buildMainPathBranchGroups({
  mainPath,
  nodeMap,
  incomingMap,
  expandedByNodeId,
  keyParentByNodeId,
  suppressedBranchNodeIds = [],
}) {
  const excludedNodeIds = new Set([...mainPath.nodeIds, ...suppressedBranchNodeIds])

  return mainPath.nodeIds.slice(0, -1).map((anchorId) => {
    const anchorRow = mainPath.rowById.get(anchorId)
    const anchorRenderKey = mainPath.renderKeyById.get(anchorId)
    if (!anchorRenderKey || anchorRow === undefined || !isExpanded(expandedByNodeId, anchorId)) {
      return {
        anchorId,
        anchorRenderKey,
        roots: [],
      }
    }

    const roots = mainPathExtraIncomingEdges({
      anchorId,
      incomingMap,
      nodeMap,
      keyParentByNodeId,
      excludedNodeIds,
    })
      .map((edge) =>
        rebuildInstanceTree({
          canonicalId: edge.source,
          downstreamId: anchorId,
          depthFromTarget: anchorRow - 1,
          branchDirection: 'up',
          rootId: edge.source,
          nodeMap,
          incomingMap,
          expandedByNodeId,
          keyParentByNodeId,
          excludedNodeIds,
          lineage: new Set(mainPath.nodeIds),
        }),
      )
      .filter(Boolean)

    return {
      anchorId,
      anchorRenderKey,
      roots,
    }
  })
}

function measureInstanceTree(instance, nodeMap) {
  const canonicalNode = nodeMap.get(toKey(instance.canonicalId))
  const role = resolveTreeNodeRole(canonicalNode, instance)
  const size = getNodeSize(role)
  const children = instance.children.map((child) => measureInstanceTree(child, nodeMap))
  const childrenWidth =
    children.length > 0
      ? children.reduce((sum, child) => sum + child.bandWidth, 0) +
        CONTROL_STRUCTURE_LAYOUT_CONFIG.branchGap * Math.max(0, children.length - 1)
      : 0

  return {
    ...instance,
    role,
    width: size.width,
    height: size.height,
    radius: size.radius,
    bandWidth: Math.max(size.width, childrenWidth + CONTROL_STRUCTURE_LAYOUT_CONFIG.branchPadding * 2),
    children,
  }
}

function buildRootEdgeLookup(anchorId, incomingMap) {
  const lookup = new Map()
  ;(incomingMap.get(toKey(anchorId)) || []).forEach((edge) => {
    const sourceId = toKey(edge.source)
    if (sourceId && !lookup.has(sourceId)) {
      lookup.set(sourceId, edge)
    }
  })
  return lookup
}

function rootPriority(instance, rootEdgeBySourceId, centerRootId = '') {
  const canonicalId = toKey(instance.canonicalId)
  if (canonicalId && canonicalId === toKey(centerRootId)) {
    return -1000
  }

  const edge = rootEdgeBySourceId.get(canonicalId)
  return -normalizedRatioForComparison(edge?.controlRatio)
}

function orderRoots(roots, nodeMap, rootEdgeBySourceId, centerRootId = '') {
  const ordered = [...roots].sort((left, right) => {
    const priorityDelta =
      rootPriority(left, rootEdgeBySourceId, centerRootId) -
      rootPriority(right, rootEdgeBySourceId, centerRootId)
    if (priorityDelta !== 0) {
      return priorityDelta
    }
    return safeText(nodeMap.get(toKey(left.canonicalId))?.name).localeCompare(
      safeText(nodeMap.get(toKey(right.canonicalId))?.name),
    )
  })

  if (!ordered.length) {
    return null
  }

  const centerRoot =
    ordered.find((root) => toKey(root.canonicalId) === toKey(centerRootId)) || ordered[0] || null
  const others = centerRoot ? ordered.filter((root) => root !== centerRoot) : []
  const left = []
  const right = []

  others.forEach((root, index) => {
    if (index % 2 === 0) {
      left.push(root)
    } else {
      right.push(root)
    }
  })

  return { centerRoot, left, right }
}

function assignInstancePositions(instance, bandLeft, bandRight, placed = [], downstreamRenderKey = 'target-node') {
  const x = (bandLeft + bandRight) / 2
  placed.push({
    ...instance,
    x,
    downstreamRenderKey,
  })

  if (!instance.children.length) {
    return placed
  }

  const totalChildrenWidth =
    instance.children.reduce((sum, child) => sum + child.bandWidth, 0) +
    CONTROL_STRUCTURE_LAYOUT_CONFIG.branchGap * Math.max(0, instance.children.length - 1)
  let cursor = x - totalChildrenWidth / 2

  instance.children.forEach((child) => {
    const childLeft = cursor
    const childRight = cursor + child.bandWidth
    assignInstancePositions(child, childLeft, childRight, placed, instance.renderKey)
    cursor = childRight + CONTROL_STRUCTURE_LAYOUT_CONFIG.branchGap
  })

  return placed
}

function placeRootBands(roots, nodeMap, rootEdgeBySourceId, centerRootId = '') {
  const arrangement = orderRoots(roots, nodeMap, rootEdgeBySourceId, centerRootId)
  if (!arrangement) {
    return []
  }

  const placements = []
  const { centerRoot, left, right } = arrangement
  const centerWidth = centerRoot?.bandWidth || 0

  if (centerRoot) {
    placements.push({
      instance: centerRoot,
      centerX: 0,
    })
  }

  let leftCursor =
    -(centerWidth / 2) -
    (centerRoot ? CONTROL_STRUCTURE_LAYOUT_CONFIG.rootGap : CONTROL_STRUCTURE_LAYOUT_CONFIG.rootGap / 2)
  left.forEach((root) => {
    const centerX = leftCursor - root.bandWidth / 2
    placements.push({ instance: root, centerX })
    leftCursor = centerX - root.bandWidth / 2 - CONTROL_STRUCTURE_LAYOUT_CONFIG.rootGap
  })

  let rightCursor =
    centerWidth / 2 +
    (centerRoot ? CONTROL_STRUCTURE_LAYOUT_CONFIG.rootGap : CONTROL_STRUCTURE_LAYOUT_CONFIG.rootGap / 2)
  right.forEach((root) => {
    const centerX = rightCursor + root.bandWidth / 2
    placements.push({ instance: root, centerX })
    rightCursor = centerX + root.bandWidth / 2 + CONTROL_STRUCTURE_LAYOUT_CONFIG.rootGap
  })

  return placements
}

function placeSideBranchBands(roots, nodeMap, rootEdgeBySourceId) {
  const corridorHalfWidth = CONTROL_STRUCTURE_LAYOUT_CONFIG.mainAxisCorridorHalfWidth
  const sideGap = CONTROL_STRUCTURE_LAYOUT_CONFIG.sideBranchGap
  const ordered = [...roots].sort((left, right) => {
    const priorityDelta =
      rootPriority(left, rootEdgeBySourceId) - rootPriority(right, rootEdgeBySourceId)
    if (priorityDelta !== 0) {
      return priorityDelta
    }
    return safeText(nodeMap.get(toKey(left.canonicalId))?.name).localeCompare(
      safeText(nodeMap.get(toKey(right.canonicalId))?.name),
    )
  })
  const placements = []
  let rightCursor = corridorHalfWidth
  let leftCursor = -corridorHalfWidth

  ordered.forEach((root, index) => {
    if (index % 2 === 0) {
      const centerX = rightCursor + root.bandWidth / 2
      placements.push({ instance: root, centerX })
      rightCursor = centerX + root.bandWidth / 2 + sideGap
      return
    }

    const centerX = leftCursor - root.bandWidth / 2
    placements.push({ instance: root, centerX })
    leftCursor = centerX - root.bandWidth / 2 - sideGap
  })

  return placements
}

function collectPlacedTreeNodes(rootPlacements = [], rootDownstreamRenderKey = 'target-node') {
  const placed = []
  rootPlacements.forEach(({ instance, centerX }) => {
    assignInstancePositions(
      instance,
      centerX - instance.bandWidth / 2,
      centerX + instance.bandWidth / 2,
      placed,
      rootDownstreamRenderKey,
    )
  })
  return placed
}

function buildRenderNodes({
  model,
  nodeMap,
  edgeMap,
  placedTreeNodes,
  expandedByNodeId,
  mainPath,
  mainPathBranchStats,
}) {
  const renderNodes = []
  const summaryControllerId = toKey(model?.summaryControllerId)
  const targetId = toKey(model?.targetId)
  const mainPathIds =
    mainPath?.nodeIds?.length >= 2 ? mainPath.nodeIds : uniqueIds([summaryControllerId, targetId])
  const parentOfTargetId = mainPathIds[mainPathIds.length - 2] || summaryControllerId

  mainPathIds.slice(0, -1).forEach((nodeId, index) => {
    const isTopController = index === 0
    const role = isTopController
      ? 'actualSummary'
      : index === mainPathIds.length - 2
        ? 'direct'
        : 'intermediate'
    const canonical =
      nodeMap.get(nodeId) ||
      (sameId(nodeId, summaryControllerId)
        ? {
            id: nodeId,
            name: model?.summaryControllerName || '控制主体',
            entityType: model?.summaryControllerType || 'other',
          }
        : null)

    if (!canonical) {
      return
    }

    const size = getNodeSize(role)
    const nextId = mainPathIds[index + 1] || targetId
    const relationEdge = edgeMap.get(`${nodeId}->${nextId}`)
    const branchStats = mainPathBranchStats?.get(nodeId) || {}
    renderNodes.push({
      renderKey: mainPath.renderKeyById.get(nodeId) || `main-path:${index}:${nodeId}`,
      id: nodeId,
      name: canonical.name || model?.summaryControllerName || 'Controller',
      entityType: canonical.entityType || model?.summaryControllerType || 'other',
      country: canonical.country || null,
      role,
      width: size.width,
      height: size.height,
      radius: size.radius,
      row: mainPath.rowById.get(nodeId) ?? index - Math.max(1, mainPathIds.length - 1),
      x: 0,
      branchDirection: 'up',
      expandable: Boolean(branchStats.expandable),
      expanded: Boolean(branchStats.expanded),
      hiddenUpstreamCount: branchStats.hiddenUpstreamCount || 0,
      isKeyPath: true,
      isMainPath: true,
      keyPathIndex: index,
      depthFromTarget: mainPath.rowById.get(nodeId) ?? index - Math.max(1, mainPathIds.length - 1),
      relationType: relationEdge?.relationType || null,
      controlRatio: relationEdge?.controlRatio ?? null,
      multiPathConvergence: canonical.multiPathConvergence || null,
      relatedEntityId: nextId,
      relatedEntityName:
        nextId === targetId
          ? model?.targetName || '目标公司'
          : nodeMap.get(nextId)?.name || `Entity ${nextId}`,
      relationDirection: 'controls',
    })
  })

  const targetRelationEdge = parentOfTargetId ? edgeMap.get(`${parentOfTargetId}->${targetId}`) : null
  renderNodes.push({
    renderKey: 'target-node',
    id: targetId,
    name: model?.targetName || '目标公司',
    entityType: 'company',
    country: null,
    role: 'target',
    ...getNodeSize('target'),
    row: 0,
    x: 0,
    branchDirection: 'center',
    expandable: false,
    expanded: false,
    hiddenUpstreamCount: 0,
    isKeyPath: Array.isArray(model?.keyPathNodeIds) && model.keyPathNodeIds.includes(targetId),
    isMainPath: mainPath?.nodeIdSet?.has(targetId) || false,
    depthFromTarget: 0,
    relationType: targetRelationEdge?.relationType || null,
    controlRatio: targetRelationEdge?.controlRatio ?? null,
    multiPathConvergence: null,
    relatedEntityId: parentOfTargetId || null,
    relatedEntityName: nodeMap.get(parentOfTargetId)?.name || model?.summaryControllerName || null,
    relationDirection: 'controlledBy',
  })

  placedTreeNodes.forEach((instance) => {
    const canonical = nodeMap.get(toKey(instance.canonicalId))
    if (!canonical) {
      return
    }

    const relationEdge = edgeMap.get(`${toKey(instance.canonicalId)}->${toKey(instance.downstreamId)}`)
    const relatedEntity = nodeMap.get(toKey(instance.downstreamId))
    renderNodes.push({
      renderKey: instance.renderKey,
      id: toKey(instance.canonicalId),
      name: canonical.name,
      entityType: canonical.entityType,
      country: canonical.country || null,
      role: instance.role,
      width: instance.width,
      height: instance.height,
      radius: instance.radius,
      row: instance.depthFromTarget,
      x: instance.x,
      branchDirection: instance.branchDirection,
      expandable: instance.expandable,
      expanded: instance.expanded,
      hiddenUpstreamCount: instance.hiddenUpstreamCount,
      isKeyPath: instance.onKeyPath,
      depthFromTarget: instance.depthFromTarget,
      downstreamId: instance.downstreamId,
      rootId: instance.rootId,
      relationType: relationEdge?.relationType || null,
      controlRatio: relationEdge?.controlRatio ?? null,
      multiPathConvergence: canonical.multiPathConvergence || null,
      relatedEntityId: toKey(instance.downstreamId),
      relatedEntityName:
        toKey(instance.downstreamId) === targetId
          ? model?.targetName || relatedEntity?.name || null
          : relatedEntity?.name || null,
      relationDirection: 'controls',
    })
  })

  return renderNodes.map((node) => ({
    ...node,
    y: CONTROL_STRUCTURE_LAYOUT_CONFIG.paddingY + node.row * CONTROL_STRUCTURE_LAYOUT_CONFIG.rowGap,
  }))
}

function buildMainPathEdges({
  mainPath,
  renderNodes,
  edgeMap,
}) {
  const renderNodeByKey = new Map(renderNodes.map((node) => [node.renderKey, node]))
  const edges = []
  const mainPathIds = Array.isArray(mainPath?.nodeIds) ? mainPath.nodeIds : []

  mainPathIds.forEach((nodeId, index) => {
    const nextId = mainPathIds[index + 1]
    if (!nextId) {
      return
    }

    const sourceRenderKey = mainPath.renderKeyById.get(nodeId)
    const targetRenderKey = mainPath.renderKeyById.get(nextId)
    const sourceNode = renderNodeByKey.get(sourceRenderKey)
    const targetNode = renderNodeByKey.get(targetRenderKey)
    if (!sourceNode || !targetNode) {
      return
    }

    const edge = edgeMap.get(`${nodeId}->${nextId}`)
    edges.push({
      id: `main-path:${sourceRenderKey}->${targetRenderKey}`,
      sourceRenderKey,
      targetRenderKey,
      relationType: edge?.relationType || 'equity',
      controlRatio: edge?.controlRatio ?? null,
      isKeyPath: true,
      isPrimary: true,
      isCollapsed: false,
      controlSubjectId: nodeId,
      controlSubjectName: sourceNode.name,
      controlObjectId: nextId,
      controlObjectName: targetNode.name,
    })
  })

  return edges
}

function buildTreeEdges({ placedTreeNodes, renderNodes, edgeMap }) {
  const renderNodeByKey = new Map(renderNodes.map((node) => [node.renderKey, node]))
  const edges = []

  placedTreeNodes.forEach((instance) => {
    const downstreamRenderKey = instance.downstreamRenderKey || null

    if (!downstreamRenderKey) {
      return
    }

    const edge = edgeMap.get(`${toKey(instance.canonicalId)}->${toKey(instance.downstreamId)}`)
    if (!edge) {
      return
    }

    const sourceNode = renderNodeByKey.get(instance.renderKey)
    const targetNode = renderNodeByKey.get(downstreamRenderKey)
    if (!sourceNode || !targetNode) {
      return
    }

    edges.push({
      id: `tree:${instance.renderKey}->${downstreamRenderKey}`,
      sourceRenderKey: instance.renderKey,
      targetRenderKey: downstreamRenderKey,
      relationType: edge.relationType,
      controlRatio: edge.controlRatio,
      isKeyPath: Boolean(instance.onKeyPath && targetNode.isKeyPath),
      isPrimary: false,
      isCollapsed: false,
      isBranch: true,
      branchDepth: Math.abs(instance.depthFromTarget),
      branchDirection: instance.branchDirection,
      controlSubjectId: toKey(instance.canonicalId),
      controlSubjectName: sourceNode.name,
      controlObjectId: toKey(instance.downstreamId),
      controlObjectName: targetNode.name,
    })
  })

  return edges
}

function edgeAnchor(node, side, direction = 'down') {
  const verticalOffset = node.height / 2
  if (side === 'source') {
    return {
      x: node.x,
      y: node.y + (direction === 'down' ? verticalOffset : -verticalOffset),
    }
  }
  return {
    x: node.x,
    y: node.y + (direction === 'down' ? -verticalOffset : verticalOffset),
  }
}

function buildEdgePath(sourceNode, targetNode) {
  const direction = sourceNode.y <= targetNode.y ? 'down' : 'up'
  const start = edgeAnchor(sourceNode, 'source', direction)
  const end = edgeAnchor(targetNode, 'target', direction)
  const midY = Number(((start.y + end.y) / 2).toFixed(2))

  if (Math.abs(start.x - end.x) < 2) {
    return `M ${start.x} ${start.y} L ${end.x} ${end.y}`
  }

  return `M ${start.x} ${start.y} C ${start.x} ${midY} ${end.x} ${midY} ${end.x} ${end.y}`
}

function translateToViewport(renderNodes, renderEdges) {
  if (!renderNodes.length) {
    return {
      width: CONTROL_STRUCTURE_LAYOUT_CONFIG.minWidth,
      height: CONTROL_STRUCTURE_LAYOUT_CONFIG.minHeight,
      canvasHeight: 540,
      nodes: [],
      edges: [],
    }
  }

  const minX = Math.min(...renderNodes.map((node) => node.x - node.width / 2))
  const maxX = Math.max(...renderNodes.map((node) => node.x + node.width / 2))
  const minY = Math.min(...renderNodes.map((node) => node.y - node.height / 2))
  const maxY = Math.max(...renderNodes.map((node) => node.y + node.height / 2))

  const contentWidth = maxX - minX
  const contentHeight = maxY - minY
  const width = Math.max(
    CONTROL_STRUCTURE_LAYOUT_CONFIG.minWidth,
    Math.round(contentWidth + CONTROL_STRUCTURE_LAYOUT_CONFIG.paddingX * 2),
  )
  const height = Math.max(
    CONTROL_STRUCTURE_LAYOUT_CONFIG.minHeight,
    Math.round(contentHeight + CONTROL_STRUCTURE_LAYOUT_CONFIG.paddingY * 2),
  )

  const shiftX = Math.round((width - contentWidth) / 2 - minX)
  const shiftY = Math.round((height - contentHeight) / 2 - minY)

  const shiftedNodes = renderNodes.map((node) => ({
    ...node,
    x: Math.round(node.x + shiftX),
    y: Math.round(node.y + shiftY),
  }))

  const shiftedNodeMap = new Map(shiftedNodes.map((node) => [node.renderKey, node]))
  const shiftedEdges = renderEdges
    .map((edge) => {
      const sourceNode = shiftedNodeMap.get(edge.sourceRenderKey)
      const targetNode = shiftedNodeMap.get(edge.targetRenderKey)
      if (!sourceNode || !targetNode) {
        return null
      }

      return {
        ...edge,
        source: sourceNode.id,
        target: targetNode.id,
        path: buildEdgePath(sourceNode, targetNode),
      }
    })
    .filter(Boolean)

  return {
    width,
    height,
    canvasHeight: Math.min(780, Math.max(540, Math.round(height * 0.76))),
    nodes: shiftedNodes,
    edges: shiftedEdges,
  }
}

export function computeControlStructureLayout(model = {}, expandedByNodeId = {}) {
  const nodeMap = buildNodeMap(model?.nodes)
  const edgeMap = buildEdgeMap(model?.edges)
  const incomingMap = buildIncomingMap(model?.edges)
  const keyParentByNodeId = buildKeyParentMap(model)
  const summaryControllerId = toKey(model?.summaryControllerId)
  const suppressedBranchNodeIds = uniqueIds(model?.multiPathConvergenceNodeIds)
  const mainPath = buildMainPathContext(model)
  const mainPathBranchStats = buildMainPathBranchStats({
    mainPath,
    incomingMap,
    nodeMap,
    keyParentByNodeId,
    expandedByNodeId,
    suppressedBranchNodeIds,
  })
  const lowerRootInstances = buildLowerRootInstances({
    model,
    nodeMap,
    incomingMap,
    expandedByNodeId,
    keyParentByNodeId,
    summaryControllerId,
    mainPathNodeIds: mainPath.nodeIds,
    suppressedBranchNodeIds,
  }).map((root) => measureInstanceTree(root, nodeMap))
  const mainPathBranchGroups = buildMainPathBranchGroups({
    mainPath,
    nodeMap,
    incomingMap,
    expandedByNodeId,
    keyParentByNodeId,
    suppressedBranchNodeIds,
  }).map((group) => ({
    ...group,
    roots: group.roots.map((root) => measureInstanceTree(root, nodeMap)),
  }))

  const lowerRootPlacements = placeRootBands(
    lowerRootInstances,
    nodeMap,
    buildRootEdgeLookup(model?.targetId, incomingMap),
    model?.keyPathFirstLayerId,
  )
  const mainPathBranchPlacedNodes = mainPathBranchGroups.flatMap((group) =>
    collectPlacedTreeNodes(
      placeSideBranchBands(group.roots, nodeMap, buildRootEdgeLookup(group.anchorId, incomingMap)),
      group.anchorRenderKey,
    ),
  )
  const placedTreeNodes = [
    ...mainPathBranchPlacedNodes,
    ...collectPlacedTreeNodes(lowerRootPlacements, 'target-node'),
  ]
  const renderNodes = buildRenderNodes({
    model,
    nodeMap,
    edgeMap,
    placedTreeNodes,
    expandedByNodeId,
    mainPath,
    mainPathBranchStats,
  })

  const treeEdges = buildTreeEdges({
    placedTreeNodes,
    renderNodes,
    edgeMap,
  })

  const mainPathEdges = buildMainPathEdges({
    mainPath,
    renderNodes,
    edgeMap,
  })

  const viewport = translateToViewport(
    renderNodes,
    [...mainPathEdges, ...treeEdges],
  )

  return {
    width: viewport.width,
    height: viewport.height,
    canvasHeight: viewport.canvasHeight,
    direction: CONTROL_STRUCTURE_LAYOUT_CONFIG.direction,
    targetAnchor: CONTROL_STRUCTURE_LAYOUT_CONFIG.targetAnchor,
    layerCount: renderNodes.length
      ? Math.max(...renderNodes.map((node) => node.row)) -
        Math.min(...renderNodes.map((node) => node.row)) +
        1
      : 0,
    expandedNodeCount: Object.keys(expandedByNodeId || {}).filter((key) => expandedByNodeId[key]).length,
    nodes: viewport.nodes,
    edges: viewport.edges,
    mainPathNodeIds: mainPath.nodeIds,
  }
}
