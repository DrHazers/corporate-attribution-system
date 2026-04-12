export const CONTROL_STRUCTURE_LAYOUT_CONFIG = {
  direction: 'vertical_top_to_bottom',
  targetAnchor: 'bottom_center',
  minWidth: 920,
  minHeight: 560,
  paddingX: 118,
  paddingY: 84,
  rowGap: 138,
  rootGap: 56,
  branchGap: 34,
  branchPadding: 16,
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
  rootId,
  nodeMap,
  incomingMap,
  expandedByNodeId,
  keyParentByNodeId,
  summaryControllerId,
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
      return sourceId && !lineage.has(sourceId) && sourceId !== summaryControllerId
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
            depthFromTarget: depthFromTarget + 1,
            rootId,
            nodeMap,
            incomingMap,
            expandedByNodeId,
            keyParentByNodeId,
            summaryControllerId,
            lineage: nextLineage,
          }),
        )
        .filter(Boolean)
    : []

  return {
    renderKey: `${rootId}:${depthFromTarget}:${nodeId}:${toKey(downstreamId)}`,
    canonicalId: nodeId,
    downstreamId: toKey(downstreamId),
    rootId: toKey(rootId),
    depthFromTarget,
    onKeyPath,
    expanded,
    expandable: eligibleEdges.length > 0,
    hiddenUpstreamCount: expanded ? Math.max(0, eligibleEdges.length - children.length) : eligibleEdges.length,
    children,
  }
}

function buildRootInstances({
  model,
  nodeMap,
  incomingMap,
  expandedByNodeId,
  keyParentByNodeId,
  summaryControllerId,
}) {
  const targetId = toKey(model?.targetId)
  const rootIds = (Array.isArray(model?.directUpstreamIds) ? model.directUpstreamIds : [])
    .map((id) => toKey(id))
    .filter((id) => id && id !== summaryControllerId)

  return rootIds
    .map((rootId) =>
      rebuildInstanceTree({
        canonicalId: rootId,
        downstreamId: targetId,
        depthFromTarget: 1,
        rootId,
        nodeMap,
        incomingMap,
        expandedByNodeId,
        keyParentByNodeId,
        summaryControllerId,
        lineage: new Set([targetId]),
      }),
    )
    .filter(Boolean)
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

function rootPriority(instance, model, nodeMap, incomingMap) {
  const canonicalId = toKey(instance.canonicalId)
  const keyRoot = toKey(model?.keyPathFirstLayerId)
  if (canonicalId === keyRoot) {
    return -1000
  }

  const edge = (incomingMap.get(toKey(model?.targetId)) || []).find((item) => toKey(item.source) === canonicalId)
  return -normalizedRatioForComparison(edge?.controlRatio)
}

function orderRoots(roots, model, nodeMap, incomingMap) {
  const ordered = [...roots].sort((left, right) => {
    const priorityDelta =
      rootPriority(left, model, nodeMap, incomingMap) - rootPriority(right, model, nodeMap, incomingMap)
    if (priorityDelta !== 0) {
      return priorityDelta
    }
    return safeText(nodeMap.get(toKey(left.canonicalId))?.name).localeCompare(
      safeText(nodeMap.get(toKey(right.canonicalId))?.name),
    )
  })

  if (!ordered.length) {
    return []
  }

  const centerRoot =
    ordered.find((root) => toKey(root.canonicalId) === toKey(model?.keyPathFirstLayerId)) || ordered[0]
  const others = ordered.filter((root) => root !== centerRoot)
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

function placeRootBands(roots, model, nodeMap, incomingMap) {
  const arrangement = orderRoots(roots, model, nodeMap, incomingMap)
  if (!arrangement?.centerRoot) {
    return []
  }

  const placements = []
  const { centerRoot, left, right } = arrangement
  placements.push({
    instance: centerRoot,
    centerX: 0,
  })

  let leftCursor = -centerRoot.bandWidth / 2 - CONTROL_STRUCTURE_LAYOUT_CONFIG.rootGap
  left.forEach((root) => {
    const centerX = leftCursor - root.bandWidth / 2
    placements.push({ instance: root, centerX })
    leftCursor = centerX - root.bandWidth / 2 - CONTROL_STRUCTURE_LAYOUT_CONFIG.rootGap
  })

  let rightCursor = centerRoot.bandWidth / 2 + CONTROL_STRUCTURE_LAYOUT_CONFIG.rootGap
  right.forEach((root) => {
    const centerX = rightCursor + root.bandWidth / 2
    placements.push({ instance: root, centerX })
    rightCursor = centerX + root.bandWidth / 2 + CONTROL_STRUCTURE_LAYOUT_CONFIG.rootGap
  })

  return placements
}

function collectPlacedTreeNodes(rootPlacements = []) {
  const placed = []
  rootPlacements.forEach(({ instance, centerX }) => {
    assignInstancePositions(
      instance,
      centerX - instance.bandWidth / 2,
      centerX + instance.bandWidth / 2,
      placed,
    )
  })
  return placed
}

function buildRenderNodes({
  model,
  nodeMap,
  placedTreeNodes,
}) {
  const renderNodes = []
  const treeMaxRow = placedTreeNodes.reduce((max, node) => Math.max(max, node.depthFromTarget), 1)
  const summaryControllerId = toKey(model?.summaryControllerId)
  const summaryControllerNode = summaryControllerId
    ? nodeMap.get(summaryControllerId) || {
        id: summaryControllerId,
        name: model?.summaryControllerName || 'Controller',
        entityType: model?.summaryControllerType || 'other',
      }
    : null

  if (summaryControllerNode) {
    const size = getNodeSize('actualSummary')
    renderNodes.push({
      renderKey: 'summary-controller',
      id: summaryControllerId,
      name: summaryControllerNode.name || model?.summaryControllerName || 'Controller',
      entityType: summaryControllerNode.entityType || model?.summaryControllerType || 'other',
      country: summaryControllerNode.country || null,
      role: 'actualSummary',
      width: size.width,
      height: size.height,
      radius: size.radius,
      row: treeMaxRow + 1,
      x: 0,
      expandable: false,
      expanded: false,
      hiddenUpstreamCount: 0,
      isKeyPath: true,
      depthFromTarget: treeMaxRow + 1,
    })
  }

  renderNodes.push({
    renderKey: 'target-node',
    id: toKey(model?.targetId),
    name: model?.targetName || 'Target Company',
    entityType: 'company',
    country: null,
    role: 'target',
    ...getNodeSize('target'),
    row: 0,
    x: 0,
    expandable: false,
    expanded: false,
    hiddenUpstreamCount: 0,
    isKeyPath: Array.isArray(model?.keyPathNodeIds) && model.keyPathNodeIds.includes(toKey(model?.targetId)),
    depthFromTarget: 0,
  })

  placedTreeNodes.forEach((instance) => {
    const canonical = nodeMap.get(toKey(instance.canonicalId))
    if (!canonical) {
      return
    }

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
      expandable: instance.expandable,
      expanded: instance.expanded,
      hiddenUpstreamCount: instance.hiddenUpstreamCount,
      isKeyPath: instance.onKeyPath,
      depthFromTarget: instance.depthFromTarget,
      downstreamId: instance.downstreamId,
      rootId: instance.rootId,
    })
  })

  const maxRow = renderNodes.reduce((max, node) => Math.max(max, node.row), 0)
  return renderNodes.map((node) => ({
    ...node,
    y: CONTROL_STRUCTURE_LAYOUT_CONFIG.paddingY + (maxRow - node.row) * CONTROL_STRUCTURE_LAYOUT_CONFIG.rowGap,
  }))
}

function buildPrimaryKeyEdge({
  model,
  renderNodes,
  edgeMap,
}) {
  const summaryControllerId = toKey(model?.summaryControllerId)
  const targetId = toKey(model?.targetId)
  if (!summaryControllerId) {
    return null
  }

  const keyPathNodeIds = Array.isArray(model?.keyPathNodeIds) ? model.keyPathNodeIds.map((id) => toKey(id)) : []
  const visibleKeyNodeById = new Map(
    renderNodes
      .filter((node) => node.role !== 'actualSummary' && node.role !== 'target' && node.isKeyPath)
      .map((node) => [toKey(node.id), node]),
  )

  const visibleAnchorId =
    keyPathNodeIds.slice(1, -1).find((nodeId) => visibleKeyNodeById.has(nodeId)) || targetId
  const anchorNode =
    visibleAnchorId === targetId
      ? renderNodes.find((node) => node.role === 'target')
      : visibleKeyNodeById.get(visibleAnchorId)
  const summaryNode = renderNodes.find((node) => node.role === 'actualSummary')

  if (!summaryNode || !anchorNode) {
    return null
  }

  const immediateDownstreamId = keyPathNodeIds[1] || targetId
  const pair = `${summaryControllerId}->${visibleAnchorId}`
  const directEdge = edgeMap.get(pair)
  const collapsed = visibleAnchorId !== immediateDownstreamId

  return {
    id: `summary-key:${summaryControllerId}->${visibleAnchorId}`,
    sourceRenderKey: summaryNode.renderKey,
    targetRenderKey: anchorNode.renderKey,
    relationType: directEdge?.relationType || 'equity',
    controlRatio: directEdge?.controlRatio ?? null,
    isKeyPath: true,
    isPrimary: true,
    isCollapsed: collapsed,
  }
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
    })
  })

  return edges
}

function edgeAnchor(node, side) {
  if (side === 'source') {
    return {
      x: node.x,
      y: node.y + node.height / 2,
    }
  }
  return {
    x: node.x,
    y: node.y - node.height / 2,
  }
}

function buildEdgePath(sourceNode, targetNode) {
  const start = edgeAnchor(sourceNode, 'source')
  const end = edgeAnchor(targetNode, 'target')
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

  const rootInstances = buildRootInstances({
    model,
    nodeMap,
    incomingMap,
    expandedByNodeId,
    keyParentByNodeId,
    summaryControllerId,
  }).map((root) => measureInstanceTree(root, nodeMap))

  const rootPlacements = placeRootBands(rootInstances, model, nodeMap, incomingMap)
  const placedTreeNodes = collectPlacedTreeNodes(rootPlacements)
  const renderNodes = buildRenderNodes({
    model,
    nodeMap,
    placedTreeNodes,
  })

  const treeEdges = buildTreeEdges({
    placedTreeNodes,
    renderNodes,
    edgeMap,
  })

  const primaryKeyEdge = buildPrimaryKeyEdge({
    model,
    renderNodes,
    edgeMap,
  })

  const viewport = translateToViewport(
    renderNodes,
    primaryKeyEdge ? [primaryKeyEdge, ...treeEdges] : treeEdges,
  )

  return {
    width: viewport.width,
    height: viewport.height,
    canvasHeight: viewport.canvasHeight,
    direction: CONTROL_STRUCTURE_LAYOUT_CONFIG.direction,
    targetAnchor: CONTROL_STRUCTURE_LAYOUT_CONFIG.targetAnchor,
    layerCount: renderNodes.reduce((max, node) => Math.max(max, node.row), 0) + 1,
    expandedNodeCount: Object.keys(expandedByNodeId || {}).filter((key) => expandedByNodeId[key]).length,
    nodes: viewport.nodes,
    edges: viewport.edges,
  }
}
