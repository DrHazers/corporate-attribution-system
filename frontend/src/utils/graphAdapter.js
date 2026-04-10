const NODE_CATEGORY_STYLES = {
  target: {
    name: '目标公司',
    color: '#23577a',
    borderColor: '#16384f',
  },
  actualController: {
    name: '实际控制人',
    color: '#b14d3f',
    borderColor: '#7d342a',
  },
  other: {
    name: '其他主体',
    color: '#8d9cab',
    borderColor: '#5f7081',
  },
}

const EDGE_TYPE_COLORS = {
  equity: '#6c8fb1',
  agreement: '#a9823a',
  board_control: '#bd5b4b',
  voting_right: '#3b7f78',
  nominee: '#8e6a46',
  vie: '#738646',
  other: '#7a8794',
}

export function formatGraphPercent(value) {
  if (value === null || value === undefined || value === '') {
    return '暂无'
  }

  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return String(value)
  }

  const normalized = numeric <= 1 ? numeric * 100 : numeric
  return `${normalized.toFixed(2)}%`
}

function truncateLabel(value, maxLength = 20) {
  if (!value) {
    return '未命名主体'
  }
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}…` : value
}

function getNodeRole(node, actualControllerEntityId) {
  if (node?.is_root) {
    return 'target'
  }

  if (
    actualControllerEntityId !== null &&
    actualControllerEntityId !== undefined &&
    Number(node?.entity_id) === Number(actualControllerEntityId)
  ) {
    return 'actualController'
  }

  return 'other'
}

function buildDegreeMap(nodes = [], edges = []) {
  const degreeMap = new Map(nodes.map((node) => [String(node.entity_id), 0]))

  edges.forEach((edge) => {
    const fromKey = String(edge.from_entity_id)
    const toKey = String(edge.to_entity_id)
    degreeMap.set(fromKey, (degreeMap.get(fromKey) || 0) + 1)
    degreeMap.set(toKey, (degreeMap.get(toKey) || 0) + 1)
  })

  return degreeMap
}

export function buildRelationshipGraphModel(graphData, options = {}) {
  const nodes = Array.isArray(graphData?.nodes) ? graphData.nodes : []
  const edges = Array.isArray(graphData?.edges) ? graphData.edges : []
  const actualControllerEntityId = options.actualControllerEntityId ?? null
  const degreeMap = buildDegreeMap(nodes, edges)

  const adaptedNodes = nodes.map((node) => {
    const role = getNodeRole(node, actualControllerEntityId)
    const style = NODE_CATEGORY_STYLES[role]
    const degree = degreeMap.get(String(node.entity_id)) || 0
    const baseSize = role === 'target' ? 70 : role === 'actualController' ? 62 : 38

    return {
      id: String(node.entity_id),
      name: node.name || node.entity_name || `Entity ${node.entity_id}`,
      displayLabel: truncateLabel(node.name || node.entity_name || ''),
      categoryKey: role,
      category: ['target', 'actualController', 'other'].indexOf(role),
      symbolSize: Math.min(baseSize + degree * 2.2, 86),
      value: degree,
      draggable: true,
      itemStyle: {
        color: style.color,
        borderColor: style.borderColor,
        borderWidth: role === 'other' ? 1.5 : 2.4,
        shadowBlur: role === 'other' ? 8 : 18,
        shadowColor:
          role === 'other' ? 'rgba(70, 86, 101, 0.18)' : 'rgba(31, 59, 87, 0.24)',
      },
      label: {
        show: true,
      },
      raw: {
        ...node,
        role,
        degree,
      },
    }
  })

  const adaptedLinks = edges.map((edge) => {
    const edgeType = edge.relation_type || edge.control_type || 'other'
    const lineColor = EDGE_TYPE_COLORS[edgeType] || EDGE_TYPE_COLORS.other
    const ratioLabel =
      edge.holding_ratio !== null && edge.holding_ratio !== undefined
        ? formatGraphPercent(edge.holding_ratio)
        : null

    return {
      source: String(edge.from_entity_id),
      target: String(edge.to_entity_id),
      value: ratioLabel || edge.control_type || edge.relation_type || '未标注',
      lineStyle: {
        color: lineColor,
        width: edge.has_numeric_ratio ? 2.2 : 1.6,
        curveness: 0.14,
        opacity: 0.86,
      },
      emphasis: {
        lineStyle: {
          width: edge.has_numeric_ratio ? 3.4 : 2.6,
          opacity: 1,
        },
      },
      raw: edge,
    }
  })

  return {
    companyId: graphData?.company_id ?? null,
    targetEntityId: graphData?.target_entity_id ?? null,
    targetCompanyName:
      graphData?.target_company?.name ||
      nodes.find((node) => node.is_root)?.name ||
      '暂无',
    nodeCount: graphData?.node_count ?? adaptedNodes.length,
    edgeCount: graphData?.edge_count ?? adaptedLinks.length,
    hasData: adaptedNodes.length > 0,
    message: graphData?.message || '',
    categories: [
      { name: NODE_CATEGORY_STYLES.target.name },
      { name: NODE_CATEGORY_STYLES.actualController.name },
      { name: NODE_CATEGORY_STYLES.other.name },
    ],
    nodes: adaptedNodes,
    links: adaptedLinks,
  }
}

export function formatNodeTooltip(node) {
  const raw = node?.raw || {}
  const lines = [
    `<strong>${node?.name || '未命名主体'}</strong>`,
    `角色：${
      raw.role === 'target'
        ? '目标公司'
        : raw.role === 'actualController'
          ? '实际控制人'
          : '普通主体'
    }`,
    `主体类型：${raw.entity_type || '暂无'}`,
    `国家/地区：${raw.country || '暂无'}`,
    `关联 company_id：${raw.company_id ?? '暂无'}`,
    `标识码：${raw.identifier_code || '暂无'}`,
    `相邻边数量：${raw.degree ?? 0}`,
  ]

  return lines.join('<br/>')
}

export function formatEdgeTooltip(edge) {
  const raw = edge?.raw || {}
  const lines = [
    `<strong>${raw.from_entity_name || raw.from_entity_id} → ${
      raw.to_entity_name || raw.to_entity_id
    }</strong>`,
    `关系类型：${raw.relation_type || '暂无'}`,
    `控制类型：${raw.control_type || '暂无'}`,
    `持股/控制比例：${formatGraphPercent(raw.holding_ratio)}`,
    `关系角色：${raw.relation_role || '暂无'}`,
    `控制依据：${raw.control_basis || '暂无'}`,
    `置信度：${raw.confidence_level || '暂无'}`,
    `报告期：${raw.reporting_period || '暂无'}`,
  ]

  return lines.join('<br/>')
}
