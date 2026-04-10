export const CONTROL_STRUCTURE_LAYOUT_CONFIG = {
  direction: 'vertical_top_to_bottom',
  targetAnchor: 'bottom_center',
  columnGap: 178,
  rowGap: 150,
  layerSubRowGap: 72,
  maxSideNodesPerLayerRow: 5,
  paddingX: 126,
  paddingY: 88,
  minWidth: 900,
  minHeight: 560,
  nodeSize: {
    target: { width: 180, height: 70, radius: 8 },
    actualController: { width: 170, height: 70, radius: 36 },
    focused: { width: 164, height: 64, radius: 8 },
    intermediate: { width: 164, height: 62, radius: 8 },
    support: { width: 154, height: 58, radius: 8 },
  },
}

function toKey(value) {
  return value === null || value === undefined ? '' : String(value)
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function getNodeSize(role) {
  return CONTROL_STRUCTURE_LAYOUT_CONFIG.nodeSize[role] || CONTROL_STRUCTURE_LAYOUT_CONFIG.nodeSize.support
}

function buildMainRowMap(mainPathNodeIds, targetRow) {
  const rowMap = new Map()
  const ids = mainPathNodeIds.map((id) => toKey(id)).filter(Boolean)

  if (ids.length <= 1) {
    ids.forEach((id) => rowMap.set(id, 0))
    return rowMap
  }

  ids.forEach((id, index) => {
    const row = Math.round((index / Math.max(1, ids.length - 1)) * targetRow)
    rowMap.set(id, row)
  })

  return rowMap
}

function buildNodeMap(nodes) {
  return new Map(nodes.map((node) => [toKey(node.id), node]))
}

function resolveRows({ nodes, edges, mainPathNodeIds }) {
  const targetRow = Math.max(2, mainPathNodeIds.length - 1)
  const mainRowMap = buildMainRowMap(mainPathNodeIds, targetRow)
  const rowMap = new Map(mainRowMap)

  nodes.forEach((node) => {
    const id = toKey(node.id)
    if (!id || rowMap.has(id)) {
      return
    }

    if (node.role === 'target') {
      rowMap.set(id, targetRow)
    } else if (node.role === 'actualController') {
      rowMap.set(id, 0)
    }
  })

  for (let pass = 0; pass < nodes.length + edges.length + 2; pass += 1) {
    let changed = false

    edges.forEach((edge) => {
      const source = toKey(edge.source)
      const target = toKey(edge.target)
      const sourceRow = rowMap.get(source)
      const targetRowValue = rowMap.get(target)

      if (targetRowValue !== undefined && sourceRow === undefined) {
        rowMap.set(source, clamp(targetRowValue - 1, 0, targetRow - 1))
        changed = true
      } else if (sourceRow !== undefined && targetRowValue === undefined) {
        rowMap.set(target, clamp(sourceRow + 1, 1, targetRow))
        changed = true
      }
    })

    if (!changed) {
      break
    }
  }

  nodes.forEach((node) => {
    const id = toKey(node.id)
    if (id && !rowMap.has(id)) {
      rowMap.set(id, Math.max(0, targetRow - 1))
    }
  })

  return {
    rowMap,
    mainRowMap,
    targetRow,
  }
}

function nodeRank(node) {
  if (node.role === 'actualController') {
    return 0
  }
  if (node.role === 'focused') {
    return 1
  }
  if (node.role === 'intermediate') {
    return 2
  }
  if (node.role === 'target') {
    return 3
  }
  return 10
}

function sortLayerNodes(nodes) {
  return [...nodes].sort((left, right) => {
    const rankDelta = nodeRank(left) - nodeRank(right)
    if (rankDelta !== 0) {
      return rankDelta
    }
    const leftRatio = Number(left.controlRatio)
    const rightRatio = Number(right.controlRatio)
    const ratioDelta =
      (Number.isNaN(rightRatio) ? -1 : rightRatio) - (Number.isNaN(leftRatio) ? -1 : leftRatio)
    if (ratioDelta !== 0) {
      return ratioDelta
    }
    return String(left.name || '').localeCompare(String(right.name || ''))
  })
}

function chunk(nodes, size) {
  const chunks = []
  for (let index = 0; index < nodes.length; index += size) {
    chunks.push(nodes.slice(index, index + size))
  }
  return chunks
}

function sideColumns(count, reserveCenter = true) {
  const columns = []

  if (!reserveCenter && count % 2 === 1) {
    columns.push(0)
  }

  for (let index = 1; columns.length < count; index += 1) {
    columns.push(-index)
    if (columns.length < count) {
      columns.push(index)
    }
  }

  return columns
}

function groupNodesByRow(nodes, rowMap) {
  const rows = new Map()
  nodes.forEach((node) => {
    const row = rowMap.get(toKey(node.id)) ?? 0
    if (!rows.has(row)) {
      rows.set(row, [])
    }
    rows.get(row).push(node)
  })
  return rows
}

function buildLayerPlans({ nodes, rowMap, mainRowMap, targetRow }) {
  const grouped = groupNodesByRow(nodes, rowMap)
  const plans = []
  let maxColumn = 0

  for (let row = 0; row <= targetRow; row += 1) {
    const layerNodes = sortLayerNodes(grouped.get(row) || [])
    const mainNode = layerNodes.find((node) => mainRowMap.get(toKey(node.id)) === row)
    const sideNodes = layerNodes.filter((node) => toKey(node.id) !== toKey(mainNode?.id))
    const chunks = chunk(sideNodes, CONTROL_STRUCTURE_LAYOUT_CONFIG.maxSideNodesPerLayerRow)
    const placements = []

    if (mainNode) {
      placements.push({
        node: mainNode,
        row,
        column: 0,
        subRow: 0,
        lane: 'main-path',
      })
    }

    chunks.forEach((items, subRow) => {
      const columns = sideColumns(items.length, Boolean(mainNode) || row < targetRow)
      items.forEach((node, index) => {
        const column = columns[index] ?? index + 1
        maxColumn = Math.max(maxColumn, Math.abs(column))
        placements.push({
          node,
          row,
          column,
          subRow,
          lane: column < 0 ? 'side-left' : column > 0 ? 'side-right' : 'center-layer',
        })
      })
    })

    plans.push({
      row,
      placements,
      subRowCount: Math.max(1, chunks.length),
    })
  }

  return {
    plans,
    maxColumn,
  }
}

function computeLayerY(plans) {
  const yByRow = new Map()
  let cursor = CONTROL_STRUCTURE_LAYOUT_CONFIG.paddingY

  plans.forEach((plan, index) => {
    if (index > 0) {
      const previous = plans[index - 1]
      cursor +=
        CONTROL_STRUCTURE_LAYOUT_CONFIG.rowGap +
        Math.max(0, previous.subRowCount - 1) * CONTROL_STRUCTURE_LAYOUT_CONFIG.layerSubRowGap
    }
    yByRow.set(plan.row, cursor)
  })

  const lastPlan = plans[plans.length - 1]
  const bottomY =
    (yByRow.get(lastPlan?.row) || cursor) +
    Math.max(0, (lastPlan?.subRowCount || 1) - 1) * CONTROL_STRUCTURE_LAYOUT_CONFIG.layerSubRowGap

  return {
    yByRow,
    bottomY,
  }
}

function buildRenderNode(placement, centerX, yByRow) {
  const { node, row, column, subRow, lane } = placement
  const size = getNodeSize(node.role)
  return {
    ...node,
    ...size,
    x: centerX + column * CONTROL_STRUCTURE_LAYOUT_CONFIG.columnGap,
    y:
      (yByRow.get(row) || CONTROL_STRUCTURE_LAYOUT_CONFIG.paddingY) +
      subRow * CONTROL_STRUCTURE_LAYOUT_CONFIG.layerSubRowGap,
    row,
    column,
    subRow,
    lane,
  }
}

function edgeAnchor(node, direction) {
  if (direction === 'source') {
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

function buildEdgePath(edge, nodeMap) {
  const source = nodeMap.get(toKey(edge.source))
  const target = nodeMap.get(toKey(edge.target))
  if (!source || !target) {
    return null
  }

  const start = edgeAnchor(source, 'source')
  const end = edgeAnchor(target, 'target')

  if (Math.abs(start.x - end.x) < 2) {
    return `M ${start.x} ${start.y} L ${end.x} ${end.y}`
  }

  const midY = Number(((start.y + end.y) / 2).toFixed(2))
  return `M ${start.x} ${start.y} L ${start.x} ${midY} L ${end.x} ${midY} L ${end.x} ${end.y}`
}

export function computeControlStructureLayout(model = {}) {
  const nodes = Array.isArray(model.nodes) ? model.nodes : []
  const edges = Array.isArray(model.edges) ? model.edges : []
  const mainPathNodeIds = Array.isArray(model.mainPathNodeIds) ? model.mainPathNodeIds : []
  const { rowMap, mainRowMap, targetRow } = resolveRows({ nodes, edges, mainPathNodeIds })
  const { plans, maxColumn } = buildLayerPlans({ nodes, rowMap, mainRowMap, targetRow })
  const { yByRow, bottomY } = computeLayerY(plans)
  const width = Math.max(
    CONTROL_STRUCTURE_LAYOUT_CONFIG.minWidth,
    CONTROL_STRUCTURE_LAYOUT_CONFIG.paddingX * 2 +
      (maxColumn * 2 + 1) * CONTROL_STRUCTURE_LAYOUT_CONFIG.columnGap,
  )
  const height = Math.max(
    CONTROL_STRUCTURE_LAYOUT_CONFIG.minHeight,
    bottomY + CONTROL_STRUCTURE_LAYOUT_CONFIG.paddingY,
  )
  const centerX = width / 2
  const renderNodes = plans.flatMap((plan) =>
    plan.placements.map((placement) => buildRenderNode(placement, centerX, yByRow)),
  )
  const renderNodeMap = buildNodeMap(renderNodes)
  const renderEdges = edges
    .map((edge) => {
      const path = buildEdgePath(edge, renderNodeMap)
      return path ? { ...edge, path } : null
    })
    .filter(Boolean)

  return {
    width: Math.round(width),
    height: Math.round(height),
    canvasHeight: Math.min(760, Math.max(540, Math.round(height * 0.76))),
    direction: CONTROL_STRUCTURE_LAYOUT_CONFIG.direction,
    targetAnchor: CONTROL_STRUCTURE_LAYOUT_CONFIG.targetAnchor,
    layerCount: targetRow + 1,
    maxColumn,
    nodes: renderNodes,
    edges: renderEdges,
  }
}
