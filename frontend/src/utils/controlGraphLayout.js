export const CONTROL_GRAPH_LAYOUT_CONFIG = {
  direction: 'vertical_top_to_bottom',
  targetAnchor: 'center_bottom',
  mainPathColumn: 'center',
  mainPathColumnIndex: 0,
  smallGraphMaxNodes: 10,
  mediumGraphMaxNodes: 32,
  mainPathPriorityWeight: 100,
  sideGroupWeight: 1,
  targetNodeSize: [104, 58],
  actualControllerNodeSize: [74, 74],
  focusedNodeSize: [62, 62],
  defaultNodeSize: [48, 48],
  densityStrategies: {
    small: {
      key: 'small',
      smallGraphCompactMode: true,
      maxNodesPerVisualRow: 5,
      maxSideColumnsPerRow: 2,
      maxMainRowSideNodes: 4,
      subRowGap: 76,
      levelGap: 198,
      minLevelGap: 176,
      maxLevelGap: 230,
      columnGap: 128,
      sideStartColumn: 1,
      minPathRows: 3,
      minCanvasHeight: 500,
      viewportPaddingX: 340,
      viewportPaddingY: 220,
      referenceWidth: 1280,
      referenceHeight: 740,
      fitZoomBias: 1.08,
      minZoom: 0.82,
      maxZoom: 1.18,
    },
    medium: {
      key: 'medium',
      smallGraphCompactMode: false,
      maxNodesPerVisualRow: 7,
      maxSideColumnsPerRow: 3,
      maxMainRowSideNodes: 2,
      subRowGap: 86,
      levelGap: 224,
      minLevelGap: 204,
      maxLevelGap: 270,
      columnGap: 146,
      sideStartColumn: 2,
      minPathRows: 4,
      minCanvasHeight: 680,
      viewportPaddingX: 430,
      viewportPaddingY: 260,
      referenceWidth: 1280,
      referenceHeight: 740,
      fitZoomBias: 1,
      minZoom: 0.48,
      maxZoom: 0.98,
    },
    large: {
      key: 'large',
      smallGraphCompactMode: false,
      maxNodesPerVisualRow: 9,
      maxSideColumnsPerRow: 4,
      maxMainRowSideNodes: 2,
      subRowGap: 84,
      levelGap: 246,
      minLevelGap: 224,
      maxLevelGap: 320,
      columnGap: 138,
      sideStartColumn: 2,
      minPathRows: 5,
      minCanvasHeight: 860,
      viewportPaddingX: 520,
      viewportPaddingY: 300,
      referenceWidth: 1280,
      referenceHeight: 740,
      fitZoomBias: 0.96,
      minZoom: 0.24,
      maxZoom: 0.82,
    },
  },
}

export const CONTROL_GRAPH_NODE_SIZES = {
  target: CONTROL_GRAPH_LAYOUT_CONFIG.targetNodeSize,
  actualController: CONTROL_GRAPH_LAYOUT_CONFIG.actualControllerNodeSize,
  focused: CONTROL_GRAPH_LAYOUT_CONFIG.focusedNodeSize,
  default: CONTROL_GRAPH_LAYOUT_CONFIG.defaultNodeSize,
}

function toKey(value) {
  return value === null || value === undefined ? '' : String(value)
}

function sameId(left, right) {
  return toKey(left) !== '' && toKey(left) === toKey(right)
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function getNodeKey(node) {
  return toKey(node?.raw?.entity_id ?? node?.id)
}

function getNodeRoles(node) {
  return Array.isArray(node?.raw?.roles) ? node.raw.roles : []
}

function hasRole(node, role) {
  return getNodeRoles(node).includes(role)
}

function findNodeKeyByRole(nodes, role) {
  return getNodeKey(nodes.find((node) => hasRole(node, role)))
}

function resolveTargetKey(nodes, targetEntityId) {
  return toKey(targetEntityId) || findNodeKeyByRole(nodes, 'target')
}

function removeAdjacentDuplicates(keys) {
  return keys.filter((key, index) => key && (index === 0 || key !== keys[index - 1]))
}

function normalizePathEntityIds(path) {
  return removeAdjacentDuplicates(
    (Array.isArray(path?.entityIds) ? path.entityIds : []).map((entityId) => toKey(entityId)),
  )
}

function normalizePathDirection(pathKeys, { targetKey, actualKey, focusedKey }) {
  let keys = removeAdjacentDuplicates(pathKeys)
  if (!keys.length) {
    return []
  }

  if (targetKey && sameId(keys[0], targetKey) && !sameId(keys[keys.length - 1], targetKey)) {
    keys = [...keys].reverse()
  }

  if (actualKey && sameId(keys[keys.length - 1], actualKey) && !sameId(keys[0], actualKey)) {
    keys = [...keys].reverse()
  }

  const anchorKey = actualKey || focusedKey
  const anchorIndex = anchorKey ? keys.findIndex((key) => sameId(key, anchorKey)) : -1
  if (anchorIndex > 0) {
    keys = keys.slice(anchorIndex)
  }

  if (targetKey) {
    const targetIndex = keys.findIndex((key) => sameId(key, targetKey))
    if (targetIndex >= 0 && targetIndex < keys.length - 1) {
      keys = keys.slice(0, targetIndex + 1)
    }
    if (!sameId(keys[keys.length - 1], targetKey)) {
      keys = [...keys, targetKey]
    }
  }

  return removeAdjacentDuplicates(keys)
}

function buildOutgoingMap(edges = []) {
  const outgoingMap = new Map()

  edges.forEach((edge) => {
    const sourceKey = toKey(edge.from_entity_id)
    if (!sourceKey) {
      return
    }
    if (!outgoingMap.has(sourceKey)) {
      outgoingMap.set(sourceKey, [])
    }
    outgoingMap.get(sourceKey).push(edge)
  })

  return outgoingMap
}

function buildIncomingMap(edges = []) {
  const incomingMap = new Map()

  edges.forEach((edge) => {
    const targetKey = toKey(edge.to_entity_id)
    if (!targetKey) {
      return
    }
    if (!incomingMap.has(targetKey)) {
      incomingMap.set(targetKey, [])
    }
    incomingMap.get(targetKey).push(edge)
  })

  return incomingMap
}

function findDirectedPath(edges, startKey, targetKey) {
  if (!startKey || !targetKey) {
    return []
  }
  if (sameId(startKey, targetKey)) {
    return [startKey]
  }

  const outgoingMap = buildOutgoingMap(edges)
  const queue = [[startKey]]
  const visited = new Set([startKey])

  while (queue.length) {
    const path = queue.shift()
    const currentKey = path[path.length - 1]

    for (const edge of outgoingMap.get(currentKey) || []) {
      const nextKey = toKey(edge.to_entity_id)
      if (!nextKey || visited.has(nextKey)) {
        continue
      }

      const nextPath = [...path, nextKey]
      if (sameId(nextKey, targetKey)) {
        return nextPath
      }

      visited.add(nextKey)
      queue.push(nextPath)
    }
  }

  return []
}

function buildPathOrderMap(keyPaths = []) {
  const orderMap = new Map()

  keyPaths.forEach((pathKeys, pathIndex) => {
    pathKeys.forEach((key, index) => {
      if (!key || orderMap.has(key)) {
        return
      }
      orderMap.set(key, pathIndex * 100 + index)
    })
  })

  return orderMap
}

function buildTargetDepthMap({ nodes, edges, targetKey, normalizedKeyPaths }) {
  const incomingMap = buildIncomingMap(edges)
  const depthMap = new Map()

  if (targetKey) {
    depthMap.set(targetKey, 0)
    const queue = [targetKey]

    while (queue.length) {
      const currentKey = queue.shift()
      const currentDepth = depthMap.get(currentKey) || 0

      ;(incomingMap.get(currentKey) || []).forEach((edge) => {
        const sourceKey = toKey(edge.from_entity_id)
        if (!sourceKey || depthMap.has(sourceKey)) {
          return
        }
        depthMap.set(sourceKey, currentDepth + 1)
        queue.push(sourceKey)
      })
    }
  }

  normalizedKeyPaths.forEach((pathKeys) => {
    pathKeys.forEach((key, index) => {
      const impliedDepth = Math.max(0, pathKeys.length - 1 - index)
      depthMap.set(key, Math.max(depthMap.get(key) ?? 0, impliedDepth))
    })
  })

  nodes.forEach((node) => {
    const key = getNodeKey(node)
    if (!key || depthMap.has(key)) {
      return
    }

    const neighborDepths = []
    edges.forEach((edge) => {
      const sourceKey = toKey(edge.from_entity_id)
      const targetEdgeKey = toKey(edge.to_entity_id)
      if (sameId(sourceKey, key) && depthMap.has(targetEdgeKey)) {
        neighborDepths.push((depthMap.get(targetEdgeKey) || 0) + 1)
      }
      if (sameId(targetEdgeKey, key) && depthMap.has(sourceKey)) {
        neighborDepths.push(Math.max(0, (depthMap.get(sourceKey) || 0) - 1))
      }
    })

    if (neighborDepths.length) {
      depthMap.set(key, Math.max(...neighborDepths))
    }
  })

  return depthMap
}

function buildPrimaryPath({ edges, targetKey, actualKey, focusedKey, normalizedKeyPaths, primaryPathEntityIds }) {
  const baseContext = { targetKey, actualKey, focusedKey }
  let primaryPathKeys = normalizePathDirection(
    (Array.isArray(primaryPathEntityIds) ? primaryPathEntityIds : []).map((entityId) => toKey(entityId)),
    baseContext,
  )

  if (primaryPathKeys.length <= 1) {
    primaryPathKeys =
      normalizedKeyPaths.find((pathKeys) => actualKey && pathKeys.includes(actualKey)) ||
      normalizedKeyPaths.find((pathKeys) => focusedKey && pathKeys.includes(focusedKey)) ||
      normalizedKeyPaths[0] ||
      []
  }

  if (primaryPathKeys.length <= 1) {
    const startKey = actualKey || focusedKey
    primaryPathKeys = findDirectedPath(edges, startKey, targetKey)
    if (primaryPathKeys.length <= 1 && startKey && targetKey) {
      primaryPathKeys = [startKey, targetKey]
    }
  }

  if (targetKey && primaryPathKeys.length && !sameId(primaryPathKeys[primaryPathKeys.length - 1], targetKey)) {
    primaryPathKeys = [...primaryPathKeys, targetKey]
  }

  return removeAdjacentDuplicates(primaryPathKeys)
}

function recognizeStructure({ nodes, edges, targetEntityId, keyPaths, keyEntityIds, primaryPathEntityIds }) {
  const targetKey = resolveTargetKey(nodes, targetEntityId)
  const actualKey = findNodeKeyByRole(nodes, 'actualController')
  const focusedKey = findNodeKeyByRole(nodes, 'focused')
  const baseContext = { targetKey, actualKey, focusedKey }
  const normalizedKeyPaths = keyPaths
    .map((path) => normalizePathDirection(normalizePathEntityIds(path), baseContext))
    .filter((pathKeys) => pathKeys.length > 1)
  const primaryPathKeys = buildPrimaryPath({
    edges,
    targetKey,
    actualKey,
    focusedKey,
    normalizedKeyPaths,
    primaryPathEntityIds,
  })
  const primaryPathKeySet = new Set(primaryPathKeys)
  const targetDepthMap = buildTargetDepthMap({ nodes, edges, targetKey, normalizedKeyPaths })
  const maxTargetDepth = Math.max(1, ...Array.from(targetDepthMap.values()), primaryPathKeys.length - 1)
  const levelCount = Math.max(2, primaryPathKeys.length || 0, maxTargetDepth + 1)
  const targetLevel = levelCount - 1
  const primaryLevelByKey = new Map()

  if (primaryPathKeys.length > 1) {
    primaryPathKeys.forEach((key, index) => {
      primaryLevelByKey.set(key, clamp(index, 0, targetLevel))
    })
  }

  if (actualKey && !primaryLevelByKey.has(actualKey)) {
    primaryLevelByKey.set(actualKey, 0)
  }
  if (targetKey) {
    primaryLevelByKey.set(targetKey, targetLevel)
  }

  const pathOrderMap = buildPathOrderMap(normalizedKeyPaths)
  const assignments = new Map()

  nodes.forEach((node) => {
    const key = getNodeKey(node)
    if (!key) {
      return
    }

    let logicalLevel = primaryLevelByKey.get(key)
    if (logicalLevel === undefined) {
      const depth = targetDepthMap.get(key)
      if (depth !== undefined) {
        logicalLevel = clamp(targetLevel - depth, 0, Math.max(0, targetLevel - 1))
      } else if (hasRole(node, 'actualController') || hasRole(node, 'focused')) {
        logicalLevel = 0
      } else {
        logicalLevel = Math.max(0, targetLevel - 1)
      }
    }

    if (!sameId(key, targetKey)) {
      logicalLevel = Math.min(logicalLevel, Math.max(0, targetLevel - 1))
    }

    const isMainPath = primaryPathKeySet.has(key) || primaryLevelByKey.has(key)
    const isKeyPath = keyEntityIds.has(key) || isMainPath
    assignments.set(key, {
      key,
      logicalLevel,
      isMainPath,
      isKeyPath,
      pathOrder: pathOrderMap.get(key) ?? 9999,
      targetDepth: targetDepthMap.get(key) ?? null,
    })
  })

  return {
    targetKey,
    actualKey,
    focusedKey,
    normalizedKeyPaths,
    primaryPathKeys,
    primaryPathKeySet,
    primaryLevelByKey,
    targetLevel,
    levelCount,
    assignments,
  }
}

function selectDensityStrategy(nodeCount) {
  if (nodeCount <= CONTROL_GRAPH_LAYOUT_CONFIG.smallGraphMaxNodes) {
    return CONTROL_GRAPH_LAYOUT_CONFIG.densityStrategies.small
  }
  if (nodeCount <= CONTROL_GRAPH_LAYOUT_CONFIG.mediumGraphMaxNodes) {
    return CONTROL_GRAPH_LAYOUT_CONFIG.densityStrategies.medium
  }
  return CONTROL_GRAPH_LAYOUT_CONFIG.densityStrategies.large
}

function nodeRank(node, assignment) {
  if (hasRole(node, 'actualController')) {
    return 0
  }
  if (hasRole(node, 'target')) {
    return 1
  }
  if (assignment?.isMainPath) {
    return 2
  }
  if (hasRole(node, 'focused')) {
    return 3
  }
  if (assignment?.isKeyPath) {
    return 4
  }
  return 10
}

function sortNodesForGrid(nodes, assignments) {
  return [...nodes].sort((left, right) => {
    const leftAssignment = assignments.get(getNodeKey(left))
    const rightAssignment = assignments.get(getNodeKey(right))
    const rankDelta = nodeRank(left, leftAssignment) - nodeRank(right, rightAssignment)
    if (rankDelta !== 0) {
      return rankDelta
    }

    const pathDelta = (leftAssignment?.pathOrder ?? 9999) - (rightAssignment?.pathOrder ?? 9999)
    if (pathDelta !== 0) {
      return pathDelta
    }

    const degreeDelta = (right.raw?.degree || 0) - (left.raw?.degree || 0)
    if (degreeDelta !== 0) {
      return degreeDelta
    }

    return String(left.name || '').localeCompare(String(right.name || ''))
  })
}

function groupNodesByLevel(nodes, structure) {
  const levels = Array.from({ length: structure.levelCount }, (_, levelIndex) => ({
    levelIndex,
    nodes: [],
  }))

  nodes.forEach((node) => {
    const key = getNodeKey(node)
    const assignment = structure.assignments.get(key)
    const levelIndex = clamp(assignment?.logicalLevel ?? 0, 0, structure.targetLevel)
    levels[levelIndex].nodes.push(node)
    node.raw = {
      ...node.raw,
      layoutLevel: levelIndex,
      layoutDepth: structure.targetLevel - levelIndex,
    }
  })

  return levels
}

function splitBalanced(nodes) {
  const left = []
  const right = []

  nodes.forEach((node, index) => {
    if (index % 2 === 0) {
      left.push(node)
    } else {
      right.push(node)
    }
  })

  return { left, right }
}

function nearCenterColumns(count) {
  const columns = []
  for (let index = 1; columns.length < count; index += 1) {
    columns.push(-index)
    if (columns.length < count) {
      columns.push(index)
    }
  }
  return columns
}

function sideColumn(side, offset, strategy) {
  const direction = side === 'left' ? -1 : 1
  return direction * (strategy.sideStartColumn + offset)
}

function makePlacement(node, column, lane) {
  return {
    node,
    column,
    lane,
  }
}

function pickMainNode(level, structure) {
  const primaryKey = structure.primaryPathKeys[level.levelIndex]
  if (primaryKey) {
    const primaryNode = level.nodes.find((node) => sameId(getNodeKey(node), primaryKey))
    if (primaryNode) {
      return primaryNode
    }
  }

  if (level.levelIndex === 0 && structure.actualKey) {
    const actualNode = level.nodes.find((node) => sameId(getNodeKey(node), structure.actualKey))
    if (actualNode) {
      return actualNode
    }
  }

  if (level.levelIndex === structure.targetLevel && structure.targetKey) {
    const targetNode = level.nodes.find((node) => sameId(getNodeKey(node), structure.targetKey))
    if (targetNode) {
      return targetNode
    }
  }

  return null
}

function assignSideRows(nodes, strategy) {
  const { left, right } = splitBalanced(nodes)
  const rowCount = Math.max(
    Math.ceil(left.length / strategy.maxSideColumnsPerRow),
    Math.ceil(right.length / strategy.maxSideColumnsPerRow),
  )
  const rows = []

  for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
    const placements = []
    const leftSlice = left.slice(
      rowIndex * strategy.maxSideColumnsPerRow,
      (rowIndex + 1) * strategy.maxSideColumnsPerRow,
    )
    const rightSlice = right.slice(
      rowIndex * strategy.maxSideColumnsPerRow,
      (rowIndex + 1) * strategy.maxSideColumnsPerRow,
    )

    leftSlice.forEach((node, index) => {
      placements.push(makePlacement(node, sideColumn('left', index, strategy), 'side-left'))
    })
    rightSlice.forEach((node, index) => {
      placements.push(makePlacement(node, sideColumn('right', index, strategy), 'side-right'))
    })

    if (placements.length) {
      rows.push({
        type: 'side',
        subRowIndex: rowIndex + 1,
        placements,
      })
    }
  }

  return rows
}

function assignLevelRows(level, structure, strategy) {
  const mainNode = pickMainNode(level, structure)
  const mainKey = getNodeKey(mainNode)
  const sortedNodes = sortNodesForGrid(level.nodes, structure.assignments)
  const nonMainNodes = sortedNodes.filter((node) => getNodeKey(node) !== mainKey)
  const nearCenterCandidates = []
  const ordinaryCandidates = []

  nonMainNodes.forEach((node) => {
    const assignment = structure.assignments.get(getNodeKey(node))
    if (
      assignment?.isKeyPath ||
      hasRole(node, 'actualController') ||
      hasRole(node, 'focused') ||
      hasRole(node, 'target')
    ) {
      nearCenterCandidates.push(node)
      return
    }

    ordinaryCandidates.push(node)
  })

  const canUseCompactMainRow =
    strategy.smallGraphCompactMode || nonMainNodes.length <= strategy.maxMainRowSideNodes
  const mainRowSideCapacity = canUseCompactMainRow ? strategy.maxMainRowSideNodes : Math.min(2, nearCenterCandidates.length)
  const mainRowSideNodes = [
    ...nearCenterCandidates,
    ...(canUseCompactMainRow ? ordinaryCandidates : []),
  ].slice(0, mainRowSideCapacity)
  const mainRowSideKeys = new Set(mainRowSideNodes.map((node) => getNodeKey(node)))
  const remainingNodes = nonMainNodes.filter((node) => !mainRowSideKeys.has(getNodeKey(node)))
  const rows = []
  const mainPlacements = []

  if (mainNode) {
    mainPlacements.push(makePlacement(mainNode, CONTROL_GRAPH_LAYOUT_CONFIG.mainPathColumnIndex, 'main-path'))
  }

  nearCenterColumns(mainRowSideNodes.length).forEach((column, index) => {
    mainPlacements.push(makePlacement(mainRowSideNodes[index], column, 'near-center'))
  })

  if (mainPlacements.length) {
    rows.push({
      type: 'main',
      subRowIndex: 0,
      placements: mainPlacements,
    })
  }

  const sideRows = assignSideRows(remainingNodes, strategy)
  if (!rows.length && sideRows.length) {
    const firstSideRow = sideRows.shift()
    rows.push({
      ...firstSideRow,
      type: 'main',
      subRowIndex: 0,
    })
    sideRows.forEach((row, index) => {
      row.subRowIndex = index + 1
    })
  }

  return {
    levelIndex: level.levelIndex,
    rows: [...rows, ...sideRows],
  }
}

function assignGridLayout({ nodes, structure, strategy }) {
  const levels = groupNodesByLevel(nodes, structure)
  const levelPlans = levels.map((level) => assignLevelRows(level, structure, strategy))
  const visualRows = []

  levelPlans.forEach((levelPlan) => {
    levelPlan.rows.forEach((row) => {
      visualRows.push({
        levelIndex: levelPlan.levelIndex,
        subRowIndex: row.subRowIndex,
        type: row.type,
        placements: row.placements,
      })
    })
  })

  return {
    levels: levelPlans,
    visualRows,
  }
}

function resolveLevelGap(strategy, layoutPlan) {
  const widestRow = Math.max(
    1,
    ...layoutPlan.visualRows.map((row) => row.placements.length),
  )
  const rowPressure = Math.max(0, widestRow - strategy.maxNodesPerVisualRow) * 8
  const sideRowPressure = Math.max(0, layoutPlan.visualRows.length - strategy.minPathRows) * 1.4

  return clamp(
    strategy.levelGap + rowPressure + sideRowPressure,
    strategy.minLevelGap,
    strategy.maxLevelGap,
  )
}

function updateExtents(node, extents) {
  extents.maxAbsX = Math.max(extents.maxAbsX, Math.abs(node.x || 0))
  extents.maxAbsY = Math.max(extents.maxAbsY, Math.abs(node.y || 0))
}

function applyPlacement({ placement, y, rowIndex, levelIndex, subRowIndex, strategy, extents }) {
  const { node, column, lane } = placement
  node.x = Number((column * strategy.columnGap).toFixed(2))
  node.y = Number(y.toFixed(2))
  node.fixed = true
  node.raw = {
    ...node.raw,
    layoutLane: lane,
    layoutLevel: levelIndex,
    visualRow: rowIndex,
    visualSubRow: subRowIndex,
    gridColumn: column,
  }
  updateExtents(node, extents)
}

function mapGridToCoordinates({ layoutPlan, structure, strategy }) {
  const levelGap = resolveLevelGap(strategy, layoutPlan)
  const rowY = []
  let cursorY = 0
  let previousLevel = null

  layoutPlan.visualRows.forEach((row, rowIndex) => {
    if (rowIndex === 0) {
      cursorY = 0
    } else if (row.levelIndex !== previousLevel) {
      cursorY += levelGap
    } else {
      cursorY += strategy.subRowGap
    }

    rowY[rowIndex] = cursorY
    previousLevel = row.levelIndex
  })

  const totalHeight = Math.max(strategy.minCanvasHeight, rowY[rowY.length - 1] || 0)
  const yOffset = totalHeight / 2
  const extents = { maxAbsX: 0, maxAbsY: totalHeight / 2 }

  layoutPlan.visualRows.forEach((row, rowIndex) => {
    const y = rowY[rowIndex] - yOffset
    row.placements.forEach((placement) => {
      applyPlacement({
        placement,
        y,
        rowIndex,
        levelIndex: row.levelIndex,
        subRowIndex: row.subRowIndex,
        strategy,
        extents,
      })
    })
  })

  return {
    extents,
    levelGap,
    visualRowCount: layoutPlan.visualRows.length,
    totalHeight,
  }
}

function getPreferredZoom(extents, strategy) {
  const logicalWidth = extents.maxAbsX * 2 + strategy.viewportPaddingX
  const logicalHeight = extents.maxAbsY * 2 + strategy.viewportPaddingY
  const fitZoom = Math.min(strategy.referenceWidth / logicalWidth, strategy.referenceHeight / logicalHeight)
  const minZoom = Math.min(strategy.minZoom, fitZoom)

  return Number(clamp(fitZoom * strategy.fitZoomBias, minZoom, strategy.maxZoom).toFixed(2))
}

export function computeHierarchicalControlGraphLayout({
  nodes = [],
  edges = [],
  targetEntityId = null,
  keyPaths = [],
  keyEntityIds = new Set(),
  primaryPathEntityIds = [],
} = {}) {
  const strategy = selectDensityStrategy(nodes.length)
  const structure = recognizeStructure({
    nodes,
    edges,
    targetEntityId,
    keyPaths,
    keyEntityIds,
    primaryPathEntityIds,
  })
  const layoutPlan = assignGridLayout({ nodes, structure, strategy })
  const geometry = mapGridToCoordinates({ layoutPlan, structure, strategy })
  const preferredZoom = getPreferredZoom(geometry.extents, strategy)

  nodes.forEach((node) => {
    node.symbolSize = Array.isArray(node.symbolSize)
      ? [...node.symbolSize]
      : [
          node.symbolSize || CONTROL_GRAPH_NODE_SIZES.default[0],
          node.symbolSize || CONTROL_GRAPH_NODE_SIZES.default[1],
        ]
  })

  return {
    nodes,
    layoutMeta: {
      type: 'grid-aligned-hierarchical',
      phases: ['structure-recognition', 'grid-assignment', 'coordinate-mapping'],
      direction: CONTROL_GRAPH_LAYOUT_CONFIG.direction,
      targetPosition: CONTROL_GRAPH_LAYOUT_CONFIG.targetAnchor,
      mainPathColumn: CONTROL_GRAPH_LAYOUT_CONFIG.mainPathColumn,
      density: strategy.key,
      smallGraphCompactMode: strategy.smallGraphCompactMode,
      maxNodesPerVisualRow: strategy.maxNodesPerVisualRow,
      maxSideColumnsPerRow: strategy.maxSideColumnsPerRow,
      subRowGap: strategy.subRowGap,
      columnGap: strategy.columnGap,
      levelGap: Number(geometry.levelGap.toFixed(2)),
      levelCount: structure.levelCount,
      targetLevel: structure.targetLevel,
      visualRowCount: geometry.visualRowCount,
      primaryPathEntityIds: structure.primaryPathKeys,
      preferredZoom,
      scaleMin: Math.min(strategy.minZoom, preferredZoom),
      extents: geometry.extents,
    },
  }
}
