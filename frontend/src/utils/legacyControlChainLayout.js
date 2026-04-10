export const CONTROL_CHAIN_LAYOUT_CONFIG = {
  direction: 'vertical_top_to_bottom',
  targetAnchor: 'center_bottom',
  mainPathColumn: 'center',
  mainPathPriorityWeight: 100,
  sideGroupWeight: 1,
  smallGraphCompactMode: true,
  maxDirectBranchesShown: 4,
  maxNodesPerSidePerRow: 2,
  viewBoxPaddingX: 124,
  viewBoxPaddingY: 92,
  columnGapSmallGraph: 172,
  columnGapMediumGraph: 196,
  columnGapLargeGraph: 216,
  levelGapSmallGraph: 192,
  levelGapMediumGraph: 216,
  levelGapLargeGraph: 238,
  strategies: {
    small: {
      key: 'small',
      columnGap: 172,
      levelGap: 192,
      canvasHeight: 520,
      maxSideNodesPerVisualRow: 6,
      sideSubRowGap: 70,
    },
    medium: {
      key: 'medium',
      columnGap: 196,
      levelGap: 216,
      canvasHeight: 620,
      maxSideNodesPerVisualRow: 5,
      sideSubRowGap: 78,
    },
    large: {
      key: 'large',
      columnGap: 216,
      levelGap: 238,
      canvasHeight: 720,
      maxSideNodesPerVisualRow: 4,
      sideSubRowGap: 84,
    },
  },
  nodeGeometry: {
    target: {
      shape: 'roundRect',
      width: 152,
      height: 66,
      radius: 12,
    },
    actualController: {
      shape: 'circle',
      radius: 39,
      ringRadius: 50,
    },
    focused: {
      shape: 'circle',
      radius: 35,
    },
    intermediate: {
      shape: 'circle',
      radius: 33,
    },
    support: {
      shape: 'circle',
      radius: 30,
    },
  },
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function toKey(value) {
  return value === null || value === undefined ? '' : String(value)
}

function getNodeById(nodeMap, nodeId) {
  return nodeMap.get(toKey(nodeId)) || null
}

function selectStrategy(nodeCount, mode = '') {
  if (CONTROL_CHAIN_LAYOUT_CONFIG.strategies[mode]) {
    return CONTROL_CHAIN_LAYOUT_CONFIG.strategies[mode]
  }
  if (nodeCount <= 5) {
    return CONTROL_CHAIN_LAYOUT_CONFIG.strategies.small
  }
  if (nodeCount <= 8) {
    return CONTROL_CHAIN_LAYOUT_CONFIG.strategies.medium
  }
  return CONTROL_CHAIN_LAYOUT_CONFIG.strategies.large
}

function getNodeGeometry(role) {
  return (
    CONTROL_CHAIN_LAYOUT_CONFIG.nodeGeometry[role] ||
    CONTROL_CHAIN_LAYOUT_CONFIG.nodeGeometry.intermediate
  )
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

function buildBranchPlacements(branches) {
  const branchesByAttachment = new Map()

  branches.forEach((branch) => {
    const attachmentId = toKey(branch.attachmentNodeId)
    if (!attachmentId) {
      return
    }
    if (!branchesByAttachment.has(attachmentId)) {
      branchesByAttachment.set(attachmentId, [])
    }
    branchesByAttachment.get(attachmentId).push(branch)
  })

  const placements = new Map()

  branchesByAttachment.forEach((items, attachmentId) => {
    const balanced = splitBalanced(items)

    balanced.left.forEach((branch, index) => {
      placements.set(toKey(branch.nodeId), {
        column: -(index + 1),
        lane: 'side-left',
        attachmentId,
      })
    })

    balanced.right.forEach((branch, index) => {
      placements.set(toKey(branch.nodeId), {
        column: index + 1,
        lane: 'side-right',
        attachmentId,
      })
    })
  })

  return placements
}

function buildMainPathRowById(mainPathNodeIds) {
  const rowById = new Map()
  mainPathNodeIds.forEach((nodeId, index) => {
    rowById.set(toKey(nodeId), index)
  })
  return rowById
}

function buildEdgeAdjacency(edges) {
  const incoming = new Map()
  const outgoing = new Map()

  edges.forEach((edge) => {
    const source = toKey(edge.source)
    const target = toKey(edge.target)
    if (!source || !target) {
      return
    }
    if (!incoming.has(target)) {
      incoming.set(target, [])
    }
    if (!outgoing.has(source)) {
      outgoing.set(source, [])
    }
    incoming.get(target).push(edge)
    outgoing.get(source).push(edge)
  })

  return { incoming, outgoing }
}

function resolveNodeRows({ nodes, edges, mainPathNodeIds }) {
  const mainPathRowById = buildMainPathRowById(mainPathNodeIds)
  const maxMainRow = Math.max(0, mainPathNodeIds.length - 1)
  const rowById = new Map(mainPathRowById)

  for (let pass = 0; pass < nodes.length + edges.length + 2; pass += 1) {
    let changed = false

    edges.forEach((edge) => {
      const source = toKey(edge.source)
      const target = toKey(edge.target)
      if (!source || !target) {
        return
      }

      const sourceRow = rowById.get(source)
      const targetRow = rowById.get(target)
      if (targetRow !== undefined && sourceRow === undefined) {
        rowById.set(source, clamp(targetRow - 1, 0, maxMainRow))
        changed = true
      } else if (sourceRow !== undefined && targetRow === undefined) {
        rowById.set(target, clamp(sourceRow + 1, 0, maxMainRow))
        changed = true
      }
    })

    if (!changed) {
      break
    }
  }

  const fallbackRow = Math.max(0, maxMainRow - 1)
  nodes.forEach((node) => {
    const nodeId = toKey(node.id)
    if (nodeId && !rowById.has(nodeId)) {
      rowById.set(nodeId, fallbackRow)
    }
  })

  return {
    rowById,
    mainPathRowById,
    maxMainRow,
  }
}

function nodePlacementRank(node) {
  if (node.role === 'actualController') {
    return 0
  }
  if (node.role === 'target') {
    return 1
  }
  if (node.role === 'focused') {
    return 2
  }
  if (node.role === 'intermediate') {
    return 3
  }
  return 10
}

function sortNodesForPlacement(nodes) {
  return [...nodes].sort((left, right) => {
    const rankDelta = nodePlacementRank(left) - nodePlacementRank(right)
    if (rankDelta !== 0) {
      return rankDelta
    }
    return String(left.name || '').localeCompare(String(right.name || ''))
  })
}

function balancedColumns(count) {
  const columns = []
  for (let index = 1; columns.length < count; index += 1) {
    columns.push(-index)
    if (columns.length < count) {
      columns.push(index)
    }
  }
  return columns
}

function chunkNodes(nodes, chunkSize) {
  const chunks = []
  for (let index = 0; index < nodes.length; index += chunkSize) {
    chunks.push(nodes.slice(index, index + chunkSize))
  }
  return chunks
}

function resolveSubRowGap({ strategy, subRowCount }) {
  if (subRowCount <= 1) {
    return 0
  }

  const reservedMainRowSpace = 92
  const availableSpace = Math.max(48, strategy.levelGap - reservedMainRowSpace)
  return Math.min(strategy.sideSubRowGap, availableSpace / Math.max(1, subRowCount - 1))
}

function assignSideNodeChunks({ sideNodes, row, strategy }) {
  const sortedSideNodes = sortNodesForPlacement(sideNodes)
  const rowCapacity = Math.max(2, strategy.maxSideNodesPerVisualRow || 4)
  const chunks = chunkNodes(sortedSideNodes, rowCapacity)
  const subRowGap = resolveSubRowGap({
    strategy,
    subRowCount: chunks.length,
  })
  const placements = []
  let maxColumnSpan = 0
  let maxSubRowOffset = 0

  chunks.forEach((chunk, subRowIndex) => {
    const columns = balancedColumns(chunk.length)
    const subRowOffset = Number((subRowIndex * subRowGap).toFixed(2))
    maxSubRowOffset = Math.max(maxSubRowOffset, subRowOffset)

    chunk.forEach((node, index) => {
      const column = columns[index] ?? index + 1
      maxColumnSpan = Math.max(maxColumnSpan, Math.abs(column))
      placements.push({
        ...node,
        row,
        column,
        subRowIndex,
        subRowOffset,
        lane: column < 0 ? 'side-left' : 'side-right',
      })
    })
  })

  return {
    placements,
    maxColumnSpan,
    maxSubRowOffset,
    subRowCount: chunks.length,
  }
}

function assignNodeGrid({ nodes, edges, mainPathNodeIds, strategy }) {
  const { rowById, mainPathRowById, maxMainRow } = resolveNodeRows({
    nodes,
    edges,
    mainPathNodeIds,
  })
  const rows = new Map()

  nodes.forEach((node) => {
    const row = rowById.get(toKey(node.id)) ?? 0
    if (!rows.has(row)) {
      rows.set(row, [])
    }
    rows.get(row).push(node)
  })

  const positionedNodes = []
  let maxColumnSpan = 0
  let maxSubRowCount = 1
  let maxLogicalY = Math.max(0, maxMainRow) * strategy.levelGap

  Array.from(rows.keys())
    .sort((left, right) => left - right)
    .forEach((row) => {
      const rowNodes = sortNodesForPlacement(rows.get(row) || [])
      const mainNode = rowNodes.find((node) => mainPathRowById.get(toKey(node.id)) === row)
      const sideNodes = rowNodes.filter((node) => toKey(node.id) !== toKey(mainNode?.id))

      if (mainNode) {
        positionedNodes.push({
          ...mainNode,
          row,
          column: 0,
          subRowIndex: 0,
          subRowOffset: 0,
          lane: 'main-path',
        })
      }

      const sideLayout = assignSideNodeChunks({
        sideNodes,
        row,
        strategy,
      })

      positionedNodes.push(...sideLayout.placements)
      maxColumnSpan = Math.max(maxColumnSpan, sideLayout.maxColumnSpan)
      maxSubRowCount = Math.max(maxSubRowCount, sideLayout.subRowCount)
      maxLogicalY = Math.max(maxLogicalY, row * strategy.levelGap + sideLayout.maxSubRowOffset)
    })

  return {
    positionedNodes,
    maxColumnSpan,
    maxSubRowCount,
    maxLogicalY,
    mainPathLength: Math.max(1, maxMainRow + 1),
  }
}

function getNodeTopOffset(node) {
  const geometry = getNodeGeometry(node.role)
  if (geometry.shape === 'roundRect') {
    return geometry.height / 2
  }
  return geometry.radius
}

function getNodeBottomOffset(node) {
  return getNodeTopOffset(node)
}

function getNodeLeftOffset(node) {
  const geometry = getNodeGeometry(node.role)
  if (geometry.shape === 'roundRect') {
    return geometry.width / 2
  }
  return geometry.radius
}

function getNodeRightOffset(node) {
  return getNodeLeftOffset(node)
}

function buildPrimaryEdgePath(sourceNode, targetNode) {
  const startX = sourceNode.x
  const startY = sourceNode.y + getNodeBottomOffset(sourceNode)
  const endX = targetNode.x
  const endY = targetNode.y - getNodeTopOffset(targetNode)
  const midY = (startY + endY) / 2

  return `M ${startX} ${startY} C ${startX} ${midY} ${endX} ${midY} ${endX} ${endY}`
}

function buildSupportEdgePath(sourceNode, targetNode) {
  const direction = sourceNode.x < targetNode.x ? 1 : -1
  const startX =
    sourceNode.x + (direction > 0 ? getNodeRightOffset(sourceNode) : -getNodeLeftOffset(sourceNode))
  const startY = sourceNode.y
  const endX =
    targetNode.x + (direction > 0 ? -getNodeLeftOffset(targetNode) : getNodeRightOffset(targetNode))
  const endY = targetNode.y
  const curveOffset = Math.max(64, Math.abs(endX - startX) * 0.42)

  return `M ${startX} ${startY} C ${startX + direction * curveOffset} ${startY} ${
    endX - direction * curveOffset
  } ${endY} ${endX} ${endY}`
}

function buildEdgeRenderModel(edge, nodeMap) {
  const sourceNode = getNodeById(nodeMap, edge.source)
  const targetNode = getNodeById(nodeMap, edge.target)
  if (!sourceNode || !targetNode) {
    return null
  }

  return {
    ...edge,
    path: edge.kind === 'primary' ? buildPrimaryEdgePath(sourceNode, targetNode) : buildSupportEdgePath(sourceNode, targetNode),
  }
}

function splitLabel(value, maxChars = 13, maxLines = 2) {
  const text = String(value || '').trim()
  if (!text) {
    return ['未命名主体']
  }

  const lines = []
  for (let index = 0; index < text.length && lines.length < maxLines; index += maxChars) {
    lines.push(text.slice(index, index + maxChars))
  }

  if (text.length > maxChars * maxLines) {
    lines[maxLines - 1] = `${lines[maxLines - 1].slice(0, Math.max(1, maxChars - 1))}…`
  }

  return lines
}

function buildRenderNode(node, position) {
  const geometry = getNodeGeometry(node.role)

  return {
    ...node,
    ...geometry,
    x: position.x,
    y: position.y,
    column: position.column,
    row: position.row,
    subRowIndex: position.subRowIndex,
    subRowOffset: position.subRowOffset,
    lane: position.lane,
    labelLines: splitLabel(node.displayLabel || node.name),
  }
}

export function computeControlChainDiagramLayout(model = {}) {
  const nodes = Array.isArray(model.nodes) ? model.nodes : []
  const edges = Array.isArray(model.edges) ? model.edges : []
  const mainPathNodeIds = Array.isArray(model.mainPathNodeIds) ? model.mainPathNodeIds : []
  const strategy = selectStrategy(nodes.length, model.filterSummary?.mode)
  const { positionedNodes, maxColumnSpan, maxSubRowCount, maxLogicalY, mainPathLength } = assignNodeGrid({
    nodes,
    edges,
    mainPathNodeIds,
    strategy,
  })
  const width =
    CONTROL_CHAIN_LAYOUT_CONFIG.viewBoxPaddingX * 2 +
    (maxColumnSpan * 2 + 1) * strategy.columnGap
  const height = Math.max(
    strategy.canvasHeight,
    CONTROL_CHAIN_LAYOUT_CONFIG.viewBoxPaddingY * 2 + maxLogicalY,
  )
  const centerX = width / 2
  const topY = CONTROL_CHAIN_LAYOUT_CONFIG.viewBoxPaddingY

  const renderNodes = positionedNodes.map((node) => {
    const x = centerX + node.column * strategy.columnGap
    const y = topY + node.row * strategy.levelGap + (node.subRowOffset || 0)
    return buildRenderNode(node, {
      x,
      y,
      column: node.column,
      row: node.row,
      subRowIndex: node.subRowIndex || 0,
      subRowOffset: node.subRowOffset || 0,
      lane: node.lane,
    })
  })

  const renderNodeMap = new Map(renderNodes.map((node) => [toKey(node.id), node]))
  const renderEdges = edges
    .map((edge) => buildEdgeRenderModel(edge, renderNodeMap))
    .filter(Boolean)

  return {
    width: Math.round(width),
    height: Math.round(height),
    canvasHeight: clamp(height * 0.72, 480, 760),
    density: strategy.key,
    direction: CONTROL_CHAIN_LAYOUT_CONFIG.direction,
    mainPathColumn: CONTROL_CHAIN_LAYOUT_CONFIG.mainPathColumn,
    targetAnchor: CONTROL_CHAIN_LAYOUT_CONFIG.targetAnchor,
    filterMode: model.filterSummary?.mode || strategy.key,
    maxSideNodesPerVisualRow: strategy.maxSideNodesPerVisualRow,
    maxSubRowCount,
    mainPathLength,
    nodes: renderNodes,
    edges: renderEdges,
  }
}
