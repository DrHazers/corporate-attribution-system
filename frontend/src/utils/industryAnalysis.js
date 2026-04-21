const STATUS_LABELS = {
  confirmed: '规则确认',
  pending: '保守保留',
  needs_llm_review: '待模型补判',
  needs_manual_review: '待人工确认',
  conflicted: '候选冲突',
  unmapped: '未映射',
}

const STATUS_TAG_TYPES = {
  confirmed: 'success',
  pending: 'warning',
  needs_llm_review: 'danger',
  needs_manual_review: 'info',
  conflicted: 'danger',
  unmapped: '',
}

const CLASSIFIER_LABELS = {
  rule_based: '规则结果',
  llm_assisted: '模型建议',
  manual: '人工结果',
  hybrid: '融合结果',
}

const SEGMENT_TYPE_LABELS = {
  primary: '主营',
  secondary: '补充',
  emerging: '新兴',
  other: '其他',
}

const SEGMENT_TYPE_TAGS = {
  primary: 'success',
  secondary: 'info',
  emerging: 'warning',
  other: '',
}

const REVIEW_REASON_LABELS = {
  rule_not_matched: '规则暂未覆盖',
  multi_candidate_conflict: '多候选冲突',
  low_confidence: '证据不足',
  cross_domain_segment: '跨领域边界业务',
  emerging_business: '新兴业务',
  insufficient_description: '披露信息过泛',
  llm_suggested: '模型建议待确认',
  manual_override: '人工覆盖',
}

const WORKBENCH_RULES = [
  {
    key: 'application_software',
    family: 'software',
    phrases: ['saas', 'erp', 'crm', 'cloud', 'software', 'workflow', 'developer tools'],
    levels: [
      'Information Technology',
      'Software & Services',
      'Software',
      'Application Software',
    ],
  },
  {
    key: 'transaction_and_payment_processing',
    family: 'fintech',
    phrases: ['payment', 'wallet', 'merchant', 'acquiring', 'checkout', 'fintech'],
    levels: [
      'Financials',
      'Financial Services',
      'Financial Services',
      'Transaction & Payment Processing Services',
    ],
  },
  {
    key: 'interactive_media_and_advertising',
    family: 'media',
    phrases: ['advertising', 'adtech', 'content', 'streaming', 'media', 'creator'],
    levels: [
      'Communication Services',
      'Media & Entertainment',
      'Interactive Media & Services',
      'Interactive Media & Services',
    ],
  },
  {
    key: 'semiconductor_manufacturing',
    family: 'semiconductors',
    phrases: ['semiconductor', 'chip', 'foundry', 'wafer', 'fabless'],
    levels: [
      'Information Technology',
      'Semiconductors & Semiconductor Equipment',
      'Semiconductors & Semiconductor Equipment',
      'Semiconductors',
    ],
  },
  {
    key: 'technology_hardware_devices',
    family: 'hardware',
    phrases: ['wearables', 'device', 'devices', 'phone', 'tablet', 'hardware'],
    levels: [
      'Information Technology',
      'Technology Hardware & Equipment',
      'Technology Hardware, Storage & Peripherals',
      'Technology Hardware, Storage & Peripherals',
    ],
  },
  {
    key: 'renewable_power_producers',
    family: 'energy',
    phrases: ['battery', 'storage', 'renewable', 'solar', 'wind', 'power'],
    levels: [
      'Utilities',
      'Utilities',
      'Independent Power and Renewable Electricity Producers',
      'Renewable Electricity',
    ],
  },
]

const RULE_SHORT_SUMMARY_LABELS = {
  application_software: '已识别软件方向，但层级证据不足',
  systems_software: '已识别系统软件方向，结果较稳定',
  transaction_and_payment_processing: '已稳定命中支付处理相关分类',
  wealth_and_market_infrastructure: '已识别金融数据相关方向',
  broadline_retail_marketplace: '已匹配零售平台语义，结果较稳定',
  internet_travel_ota: '已识别在线旅游平台相关分类',
  interactive_media_and_advertising: '已命中互动媒体与广告相关方向',
  data_processing_and_outsourced_services: '已识别 IT 服务方向，但层级证据不足',
  it_consulting_and_integration: '已识别 IT 服务与集成方向',
  semiconductor_manufacturing: '已稳定命中半导体相关分类',
  semiconductor_equipment_materials: '已识别半导体设备材料方向',
  technology_hardware_devices: '已识别科技硬件设备方向',
  communications_equipment: '已识别通信设备相关方向',
  automobile_manufacturers: '已识别整车制造方向',
  automotive_parts_and_equipment: '已识别汽车零部件方向',
  renewable_power_producers: '已识别新能源发电相关方向',
  electric_utilities: '已识别电力公用事业方向',
  battery_and_storage_equipment: '已识别储能设备相关方向',
  integrated_oil_and_gas: '已识别油气能源相关方向',
  health_care_technology: '已识别医疗科技方向',
  health_care_equipment: '已识别医疗设备方向',
}

const GENERIC_WORKBENCH_PHRASES = [
  'platform services',
  'digital ecosystem',
  'enterprise solutions',
  'smart mobility',
  'intelligent devices',
  'energy solutions',
  'cloud and ai infrastructure',
  'integrated services',
]

function normalizeText(value) {
  return String(value ?? '')
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[-_/]+/g, ' ')
    .replace(/[(){}\[\],.;:!?]+/g, ' ')
    .replace(/\be[\-\s]?commerce\b/g, 'ecommerce')
    .replace(/\bsoftware[\-\s]?as[\-\s]?a[\-\s]?service\b/g, 'saas')
    .replace(/\bdata\s+centre\b/g, 'data center')
    .replace(/\s+/g, ' ')
    .trim()
}

function joinIndustryLevels(classification = {}) {
  return [classification.level_1, classification.level_2, classification.level_3, classification.level_4]
    .filter(Boolean)
    .join(' > ')
}

const BASIS_DECISION_LABELS = {
  confirmed: '规则已经形成较稳定结论。',
  pending: '系统识别到了方向，但先保守停在较粗层级。',
  needs_llm_review: '当前规则证据不足，建议结合模型补判。',
  needs_manual_review: '当前结果需要人工进一步确认。',
  conflicted: '存在多个接近的候选方向，系统暂不强判。',
  unmapped: '当前规则主干未找到稳定映射。',
}

const BASIS_COMMENT_LABELS = [
  {
    includes: 'text too generic',
    label: '业务线文本过于泛化，需要补充更具体的业务说明。',
  },
  {
    includes: 'generic boundary phrase needs richer business evidence',
    label: '名称偏边界化，建议补充主营业务、客户或商业模式信息。',
  },
  {
    includes: 'no stable family rule matched current text context',
    label: '现有规则没有命中稳定家族，建议补充说明或转人工判断。',
  },
  {
    includes: 'multiple family candidates remained too close',
    label: '多个候选方向分数接近，系统无法稳定区分。',
  },
  {
    includes: 'leaf withheld for safety',
    label: '系统为避免误分，暂时不下钻到最细层级。',
  },
  {
    includes: 'workbench manual override',
    label: '当前结果来自工作台中的人工修订。',
  },
]

export function formatFlexiblePercent(value) {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return String(value)
  }
  const normalized = numeric <= 1 ? numeric * 100 : numeric
  return `${normalized.toFixed(2)}%`
}

export function formatPercentNumber(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return null
  }
  return numeric <= 1 ? numeric * 100 : numeric
}

export function formatConfidence(value) {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return String(value)
  }
  return numeric.toFixed(2)
}

export function reviewStatusLabel(status) {
  return STATUS_LABELS[status] || status || '待生成'
}

export function reviewStatusTagType(status) {
  return STATUS_TAG_TYPES[status] || 'info'
}

export function classifierTypeLabel(value) {
  return CLASSIFIER_LABELS[value] || value || '未标注'
}

export function reviewReasonLabel(value) {
  return REVIEW_REASON_LABELS[value] || value || '—'
}

export function segmentTypeLabel(value) {
  return SEGMENT_TYPE_LABELS[value] || value || '未标注'
}

export function segmentTypeTagType(value) {
  return SEGMENT_TYPE_TAGS[value] || 'info'
}

export function primaryClassification(segment) {
  const classifications = Array.isArray(segment?.classifications) ? segment.classifications : []
  return classifications.find((item) => item?.is_primary) || classifications[0] || null
}

export function classificationSummary(segment) {
  const current = primaryClassification(segment)
  if (!current) {
    return '待建立产业分类'
  }
  return current.industry_label || joinIndustryLevels(current) || '待补充层级'
}

export function classificationLabelFromLevels(level_1, level_2, level_3, level_4) {
  return joinIndustryLevels({ level_1, level_2, level_3, level_4 }) || '待补充层级'
}

export function classificationLabel(classification) {
  if (!classification) {
    return '待补充层级'
  }
  return classification.industry_label || joinIndustryLevels(classification) || '待补充层级'
}

function parseMappingBasis(value) {
  if (!value) {
    return {}
  }
  return value
    .split('|')
    .map((part) => part.trim())
    .filter(Boolean)
    .reduce((accumulator, part) => {
      const index = part.indexOf('=')
      if (index === -1) {
        return accumulator
      }
      const key = part.slice(0, index).trim()
      const content = part.slice(index + 1).trim()
      accumulator[key] = content
      return accumulator
    }, {})
}

export function readableMappingBasis(mappingBasis, reviewReason, reviewStatus) {
  const parsed = parseMappingBasis(mappingBasis)
  const fragments = []

  if (BASIS_DECISION_LABELS[parsed.decision || reviewStatus]) {
    fragments.push(BASIS_DECISION_LABELS[parsed.decision || reviewStatus])
  }
  if (parsed.rules && parsed.rules !== 'none_stable') {
    const normalizedRules = parsed.rules
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => item.replace(/_/g, ' '))
      .join('、')
    if (normalizedRules) {
      fragments.push(`主要命中方向：${normalizedRules}。`)
    }
  }
  if (reviewReason && reviewReasonLabel(reviewReason)) {
    fragments.push(`当前原因：${reviewReasonLabel(reviewReason)}。`)
  }

  const comment = String(parsed.comment || '').toLowerCase()
  const matchedComment = BASIS_COMMENT_LABELS.find((item) => comment.includes(item.includes))
  if (matchedComment) {
    fragments.push(matchedComment.label)
  }

  if (!fragments.length && mappingBasis) {
    return '已记录规则依据，可展开查看原始 basis。'
  }
  return fragments.join(' ') || '当前暂无可读规则依据。'
}

export function compactRuleExplanation(mappingBasis, reviewReason, reviewStatus) {
  const parsed = parseMappingBasis(mappingBasis)
  const firstRule = String(parsed.rules || '')
    .split(',')
    .map((item) => item.trim())
    .find(Boolean)

  if (reviewStatus === 'confirmed') {
    return RULE_SHORT_SUMMARY_LABELS[firstRule] || '已命中稳定规则，当前结果较稳定'
  }
  if (reviewStatus === 'pending') {
    return RULE_SHORT_SUMMARY_LABELS[firstRule] || '已识别主要方向，暂作保守保留'
  }
  if (reviewStatus === 'unmapped' || reviewReason === 'rule_not_matched') {
    return '未命中稳定规则，建议补充业务说明'
  }
  if (reviewStatus === 'conflicted' || reviewReason === 'multi_candidate_conflict') {
    return '候选方向冲突，建议人工补判'
  }
  if (reviewReason === 'insufficient_description') {
    return '当前信息不足，建议补充业务说明'
  }
  if (reviewReason === 'low_confidence') {
    return RULE_SHORT_SUMMARY_LABELS[firstRule] || '已识别业务方向，但层级证据不足'
  }
  if (reviewReason === 'cross_domain_segment') {
    return '业务边界较宽，建议人工补判'
  }
  if (reviewReason === 'emerging_business') {
    return '当前信息偏新兴，建议进一步补判'
  }

  return RULE_SHORT_SUMMARY_LABELS[firstRule] || '已记录规则依据，详情可在明细中查看'
}

export function buildMockLlmClassification(segment) {
  const current = primaryClassification(segment)
  const baseLabel = classificationSummary(segment)
  const nextLevel4 = current?.level_4 || '待模型细化'
  return {
    id: `${segment.id || segment.localId}-llm-placeholder`,
    business_segment_id: segment.id || segment.localId,
    standard_system: 'GICS',
    level_1: current?.level_1 || null,
    level_2: current?.level_2 || null,
    level_3: current?.level_3 || null,
    level_4: nextLevel4,
    industry_label: classificationLabelFromLevels(
      current?.level_1 || null,
      current?.level_2 || null,
      current?.level_3 || null,
      nextLevel4,
    ),
    is_primary: segment?.segment_type === 'primary',
    mapping_basis: 'TODO: replace mock LLM result with backend llm analysis API',
    review_status: current ? 'needs_manual_review' : 'needs_llm_review',
    classifier_type: 'llm_assisted',
    confidence: current?.confidence ?? 0.55,
    review_reason: current?.review_reason || 'llm_suggested',
    readable_mapping_basis: current
      ? `占位结果：基于当前规则结果“${baseLabel}”生成了一个可供比较的 LLM 建议，后续接入真实接口后替换。`
      : '占位结果：当前尚无稳定规则结论，后续可由 LLM 结合更多上下文补判。',
    is_placeholder: true,
  }
}

export function deriveIndustryStatusCounts(industryAnalysis = {}) {
  const counts = {
    confirmed: 0,
    pending: 0,
    needs_llm_review: 0,
    needs_manual_review: 0,
    conflicted: 0,
    unmapped: 0,
  }
  const segments = Array.isArray(industryAnalysis?.segments) ? industryAnalysis.segments : []
  segments.forEach((segment) => {
    const current = primaryClassification(segment)
    if (!current?.review_status) {
      return
    }
    if (!(current.review_status in counts)) {
      counts[current.review_status] = 0
    }
    counts[current.review_status] += 1
  })
  return counts
}

export function needsFurtherAnalysis(industryAnalysis = {}) {
  const counts = deriveIndustryStatusCounts(industryAnalysis)
  return (
    counts.pending +
    counts.needs_llm_review +
    counts.needs_manual_review +
    counts.conflicted +
    counts.unmapped
  ) > 0
}

export function llmRecommended(segment) {
  const current = primaryClassification(segment)
  return ['needs_llm_review', 'conflicted', 'unmapped'].includes(current?.review_status)
}

export function pieChartRows(segments = [], metric = 'revenue_ratio', maxItems = 6) {
  const normalized = segments
    .map((segment) => {
      const current = primaryClassification(segment)
      return {
        id: segment.id,
        name: segment.segment_alias || segment.segment_name,
        rawName: segment.segment_name,
        value: formatPercentNumber(segment?.[metric]),
        segmentType: segmentTypeLabel(segment.segment_type),
        classificationSummary: current?.industry_label || classificationSummary(segment),
      }
    })
    .filter((item) => item.value !== null && item.value > 0)
    .sort((left, right) => right.value - left.value)

  if (!normalized.length) {
    return []
  }

  const head = normalized.slice(0, maxItems)
  const rest = normalized.slice(maxItems)
  if (!rest.length) {
    return head
  }

  return [
    ...head,
    {
      id: 'others',
      name: 'Others',
      rawName: 'Others',
      value: rest.reduce((sum, item) => sum + item.value, 0),
      segmentType: '合并项',
      classificationSummary: `${rest.length} 条长尾业务线合并展示`,
    },
  ]
}

export function profitPieChartRows(segments = [], maxItems = 6) {
  const rows = pieChartRows(segments, 'profit_ratio', maxItems)
  const missingCount = segments.filter(
    (segment) => segment?.profit_ratio === null || segment?.profit_ratio === undefined || segment?.profit_ratio === '',
  ).length
  if (!missingCount) {
    return rows
  }

  return [
    ...rows,
    {
      id: 'profit-missing-placeholder',
      name: '未披露利润数据',
      rawName: '未披露利润数据',
      value: Math.max(4, missingCount * 2),
      segmentType: '占位提示',
      classificationSummary: `${missingCount} 条业务线未填写利润占比，仅用于提示缺失情况。`,
      itemStyle: {
        color: '#cfd6df',
      },
      note: '利润数据缺失',
      isPlaceholder: true,
    },
  ]
}

export function statusSnapshotItems(industryAnalysis = {}) {
  const counts = deriveIndustryStatusCounts(industryAnalysis)
  return [
    { key: 'confirmed', label: '规则确认', value: counts.confirmed },
    { key: 'pending', label: '保守保留', value: counts.pending },
    { key: 'needs_llm_review', label: '待模型补判', value: counts.needs_llm_review },
    { key: 'conflicted', label: '候选冲突', value: counts.conflicted },
    { key: 'unmapped', label: '未映射', value: counts.unmapped },
  ]
}

export function createWorkbenchSegment(seed = 1) {
  return {
    localId: `workbench-segment-${seed}`,
    segment_name: '',
    segment_alias: '',
    description: '',
    revenue_ratio: '',
    profit_ratio: '',
    reporting_period: '2025A',
    segment_type: seed === 1 ? 'primary' : 'secondary',
  }
}

function workbenchProposal(segment, decision) {
  return {
    id: `${segment.localId}-classification`,
    business_segment_id: segment.localId,
    standard_system: 'GICS',
    level_1: decision.levels?.[0] || null,
    level_2: decision.levels?.[1] || null,
    level_3: decision.levels?.[2] || null,
    level_4: decision.levels?.[3] || null,
    industry_label: joinIndustryLevels({
      level_1: decision.levels?.[0],
      level_2: decision.levels?.[1],
      level_3: decision.levels?.[2],
      level_4: decision.levels?.[3],
    }),
    is_primary: segment.segment_type === 'primary',
    mapping_basis: decision.mapping_basis,
    review_status: decision.review_status,
    classifier_type: decision.classifier_type,
    confidence: decision.confidence,
    review_reason: decision.review_reason,
  }
}

function mockDecision(segment, companyInfo) {
  const nameText = normalizeText(segment.segment_name)
  const aliasText = normalizeText(segment.segment_alias)
  const descriptionText = normalizeText(segment.description)
  const companyText = normalizeText(`${companyInfo.companyName || ''} ${companyInfo.companyDescription || ''}`)
  const combined = [nameText, aliasText, descriptionText, companyText].filter(Boolean).join(' ')

  if (!combined) {
    return {
      review_status: 'needs_llm_review',
      classifier_type: 'rule_based',
      confidence: 0.12,
      review_reason: 'insufficient_description',
      levels: [null, null, null, null],
      mapping_basis:
        'decision=needs_llm_review | rules=none_stable | hits=name[] alias[] description[] company[] peer[] | negatives=[] | depth=none | comment=text too generic, require richer context',
    }
  }

  if (GENERIC_WORKBENCH_PHRASES.some((phrase) => combined.includes(phrase))) {
    return {
      review_status: 'needs_llm_review',
      classifier_type: 'rule_based',
      confidence: 0.28,
      review_reason: 'insufficient_description',
      levels: [null, null, null, null],
      mapping_basis:
        'decision=needs_llm_review | rules=none_stable | hits=name[generic phrase] alias[] description[] company[] peer[] | negatives=[] | depth=none | comment=generic boundary phrase needs richer business evidence',
    }
  }

  const hits = WORKBENCH_RULES
    .map((rule) => {
      const matched = rule.phrases.filter((phrase) => combined.includes(phrase))
      return {
        ...rule,
        matched,
        score: matched.length,
      }
    })
    .filter((rule) => rule.score > 0)
    .sort((left, right) => right.score - left.score)

  if (!hits.length) {
    return {
      review_status: 'unmapped',
      classifier_type: 'rule_based',
      confidence: 0,
      review_reason: 'rule_not_matched',
      levels: [null, null, null, null],
      mapping_basis:
        'decision=unmapped | rules=none_stable | hits=name[] alias[] description[] company[] peer[] | negatives=[] | depth=none | comment=no stable family rule matched current text context',
    }
  }

  if (hits[1] && hits[1].score >= hits[0].score) {
    return {
      review_status: 'conflicted',
      classifier_type: 'rule_based',
      confidence: 0.24,
      review_reason: 'multi_candidate_conflict',
      levels: [null, null, null, null],
      mapping_basis: `decision=conflicted | rules=${hits[0].key},${hits[1].key} | hits=name[${hits[0].matched.join(', ')}] alias[] description[] company[] peer[] | negatives=[] | depth=none | comment=multiple family candidates remained too close`,
    }
  }

  const top = hits[0]
  if (top.score >= 2) {
    return {
      review_status: 'confirmed',
      classifier_type: 'rule_based',
      confidence: 0.92,
      review_reason: null,
      levels: top.levels,
      mapping_basis: `decision=confirmed | rules=${top.key} | hits=name[${top.matched.join(', ')}] alias[] description[] company[] peer[] | negatives=[] | depth=level_4`,
    }
  }

  return {
    review_status: 'pending',
    classifier_type: 'rule_based',
    confidence: 0.66,
    review_reason: 'low_confidence',
    levels: [top.levels[0], top.levels[1], top.levels[2], null],
    mapping_basis: `decision=pending | rules=${top.key} | hits=name[${top.matched.join(', ')}] alias[] description[] company[] peer[] | negatives=[] | depth=level_3 | comment=leaf withheld for safety`,
  }
}

export function runWorkbenchRuleAnalysis({ companyName, companyDescription, segments }) {
  const companyInfo = { companyName, companyDescription }
  const analyzedSegments = segments.map((segment) => {
    const decision = mockDecision(segment, companyInfo)
    return {
      ...segment,
      id: segment.localId,
      company_id: 'workbench',
      source: 'temporary-workbench',
      is_current: true,
      classifications: [workbenchProposal(segment, decision)],
      classification_labels: decision.levels.filter(Boolean).join(' > ') ? [decision.levels.filter(Boolean).join(' > ')] : [],
      confidence: decision.confidence,
    }
  })

  const counts = deriveIndustryStatusCounts({ segments: analyzedSegments })
  const primaryIndustries = analyzedSegments
    .filter((segment) => segment.segment_type === 'primary')
    .map((segment) => classificationSummary(segment))
    .filter(Boolean)

  return {
    company_id: 'workbench',
    selected_reporting_period: analyzedSegments[0]?.reporting_period || '临时分析',
    business_segment_count: analyzedSegments.length,
    primary_industries: [...new Set(primaryIndustries)],
    all_industry_labels: [...new Set(analyzedSegments.flatMap((segment) => segment.classification_labels || []))],
    quality_warnings: counts.needs_llm_review || counts.conflicted || counts.unmapped
      ? ['当前结果包含待模型补判或冲突业务线，建议结合人工征订继续修订。']
      : [],
    has_manual_adjustment: false,
    primary_segments: analyzedSegments.filter((segment) => segment.segment_type === 'primary'),
    secondary_segments: analyzedSegments.filter((segment) => segment.segment_type === 'secondary'),
    emerging_segments: analyzedSegments.filter((segment) => segment.segment_type === 'emerging'),
    other_segments: analyzedSegments.filter((segment) => segment.segment_type === 'other'),
    segments: analyzedSegments,
  }
}
