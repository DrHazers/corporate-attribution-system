const SAME_RATIO_TOLERANCE = 0.1

function normalizeKey(value) {
  return String(value ?? '').trim().toLowerCase()
}

function normalizeText(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim().toLowerCase()
}

function parseMaybeJson(value) {
  if (typeof value !== 'string') {
    return value
  }
  const trimmed = value.trim()
  if (!trimmed || !['{', '['].includes(trimmed[0])) {
    return value
  }
  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function parsedBasis(row = {}) {
  const parsed = parseMaybeJson(row?.basis)
  return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
}

function firstAvailable(row, ...keys) {
  const basis = parsedBasis(row)
  for (const key of keys) {
    const value = row?.[key] ?? basis?.[key]
    if (value !== null && value !== undefined && value !== '') {
      return value
    }
  }
  return null
}

function isTruthy(value) {
  if (typeof value === 'boolean') {
    return value
  }
  if (typeof value === 'number') {
    return value !== 0
  }
  if (typeof value === 'string') {
    return ['1', 'true', 'yes', 'y'].includes(normalizeKey(value))
  }
  return false
}

function toPercentNumber(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const normalized = typeof value === 'string' ? value.replace('%', '').trim() : value
  const numeric = Number(normalized)
  if (Number.isNaN(numeric)) {
    return null
  }
  return numeric <= 1 ? numeric * 100 : numeric
}

function getControlPaths(row = {}) {
  const parsed = parseMaybeJson(row.control_path)
  return Array.isArray(parsed) ? parsed : []
}

function pathIds(path = {}) {
  return Array.isArray(path.path_entity_ids)
    ? path.path_entity_ids.map((id) => String(id ?? '')).filter(Boolean)
    : []
}

function pathNames(path = {}) {
  return Array.isArray(path.path_entity_names)
    ? path.path_entity_names.map((name) => normalizeText(name)).filter(Boolean)
    : []
}

function sameList(left = [], right = []) {
  return left.length > 0 && left.length === right.length && left.every((item, index) => item === right[index])
}

function primaryPathText(row = {}) {
  const path = getControlPaths(row)[0]
  if (!path) {
    return ''
  }
  const names = Array.isArray(path.path_entity_names)
    ? path.path_entity_names.map((name) => String(name ?? '').trim()).filter(Boolean)
    : []
  if (names.length) {
    return names.join(' → ')
  }
  return pathIds(path).map((id) => `主体 ${id}`).join(' → ')
}

function relationSource(row = {}) {
  return normalizeKey(
    firstAvailable(row, 'source_type', 'result_source', 'manual_result_source'),
  )
}

function isManualJudgmentCurrentRow(row = {}) {
  return (
    relationSource(row) === 'manual_judgment' &&
    !isTruthy(row?.automatic_result_superseded) &&
    (
      isTruthy(firstAvailable(row, 'is_manual_effective')) ||
      isTruthy(row?.is_current_effective)
    )
  )
}

function isAutomaticReferenceRow(row = {}) {
  return (
    isTruthy(firstAvailable(row, 'automatic_result_superseded')) &&
    !relationSource(row).startsWith('manual')
  )
}

function sameSubject(left = {}, right = {}) {
  const leftId = String(left?.controller_entity_id ?? '').trim()
  const rightId = String(right?.controller_entity_id ?? '').trim()
  if (leftId && rightId && leftId === rightId) {
    const leftName = normalizeText(left?.controller_name)
    const rightName = normalizeText(right?.controller_name)
    return !leftName || !rightName || leftName === rightName
  }

  const leftName = normalizeText(left?.controller_name)
  const rightName = normalizeText(right?.controller_name)
  if (!leftName || !rightName || leftName !== rightName) {
    return false
  }

  const leftType = normalizeKey(left?.controller_type)
  const rightType = normalizeKey(right?.controller_type)
  return !leftType || !rightType || leftType === rightType
}

function typeCandidates(row = {}) {
  const basis = parsedBasis(row)
  const snapshot = basis.selected_relationship_snapshot || {}
  return [
    row.control_type,
    basis.classification,
    basis.manual_control_type,
    snapshot.control_type,
  ]
    .map((value) => normalizeKey(value))
    .filter(Boolean)
}

function controlTypeGroup(value) {
  const normalized = normalizeKey(value)
  if (!normalized || normalized === 'manual_judgment') {
    return ''
  }
  if (
    normalized.includes('equity') ||
    normalized === 'significant_influence' ||
    normalized === 'manual_override'
  ) {
    return 'equity_like'
  }
  if (normalized.includes('agreement') || normalized.includes('vie')) {
    return 'agreement_like'
  }
  if (normalized.includes('board')) {
    return 'board_like'
  }
  if (normalized.includes('voting')) {
    return 'voting_like'
  }
  if (normalized.includes('nominee')) {
    return 'nominee_like'
  }
  if (normalized.includes('mixed')) {
    return 'mixed_like'
  }
  if (normalized.includes('joint')) {
    return 'joint_like'
  }
  return normalized
}

function hasCompatibleControlType(manualRow = {}, autoRow = {}) {
  const manualGroups = typeCandidates(manualRow).map(controlTypeGroup).filter(Boolean)
  const autoGroups = typeCandidates(autoRow).map(controlTypeGroup).filter(Boolean)
  if (!manualGroups.length || !autoGroups.length) {
    return true
  }
  return manualGroups.some((group) => autoGroups.includes(group))
}

function sameEndpoint(manualPath = {}, autoPath = {}) {
  const manualIds = pathIds(manualPath)
  const autoIds = pathIds(autoPath)
  if (manualIds.length && autoIds.length) {
    return manualIds[manualIds.length - 1] === autoIds[autoIds.length - 1]
  }
  const manualNames = pathNames(manualPath)
  const autoNames = pathNames(autoPath)
  if (manualNames.length && autoNames.length) {
    return manualNames[manualNames.length - 1] === autoNames[autoNames.length - 1]
  }
  return true
}

function pathCompatibility(manualRow = {}, autoRow = {}) {
  const manualPath = getControlPaths(manualRow)[0]
  const autoPath = getControlPaths(autoRow)[0]
  if (!manualPath || !autoPath) {
    return { compatible: true, samePath: false, reason: 'missing_path' }
  }

  if (sameList(pathIds(manualPath), pathIds(autoPath)) || sameList(pathNames(manualPath), pathNames(autoPath))) {
    return { compatible: true, samePath: true, reason: 'same_path' }
  }

  if (sameEndpoint(manualPath, autoPath)) {
    return { compatible: true, samePath: false, reason: 'auto_reference_path' }
  }

  return { compatible: false, samePath: false, reason: 'path_conflict' }
}

function rowRatio(row = {}) {
  const path = getControlPaths(row)[0] || {}
  return toPercentNumber(
    row.control_ratio ??
      row.manual_display_control_strength ??
      row.manual_control_ratio ??
      path.path_ratio ??
      path.control_ratio ??
      path.ratio,
  )
}

function hasCompatibleRatio(manualRow = {}, autoRow = {}) {
  const manualRatio = rowRatio(manualRow)
  const autoRatio = rowRatio(autoRow)
  if (manualRatio === null || autoRatio === null) {
    return true
  }
  return Math.abs(manualRatio - autoRatio) <= SAME_RATIO_TOLERANCE
}

function canMergeManualJudgmentWithAutoReference(manualRow = {}, autoRow = {}) {
  if (!isManualJudgmentCurrentRow(manualRow) || !isAutomaticReferenceRow(autoRow)) {
    return { merge: false, reason: 'role_mismatch' }
  }
  if (!sameSubject(manualRow, autoRow)) {
    return { merge: false, reason: 'subject_mismatch' }
  }
  if (!hasCompatibleControlType(manualRow, autoRow)) {
    return { merge: false, reason: 'control_type_conflict' }
  }
  const pathResult = pathCompatibility(manualRow, autoRow)
  if (!pathResult.compatible) {
    return { merge: false, reason: pathResult.reason }
  }
  if (!hasCompatibleRatio(manualRow, autoRow)) {
    return { merge: false, reason: 'ratio_conflict' }
  }

  return {
    merge: true,
    reason: pathResult.samePath ? 'same_subject_same_path' : pathResult.reason,
  }
}

function mergeRows(manualRow = {}, autoRow = {}, reason = '') {
  const autoPathText = primaryPathText(autoRow)
  const manualPathText = primaryPathText(manualRow)
  return {
    ...manualRow,
    _hasMergedAutoReference: true,
    _autoReferenceRelationship: autoRow,
    _autoReferenceMergeReason: reason,
    _autoReferenceControlType: autoRow.control_type,
    _autoReferenceControlRatio: autoRow.control_ratio,
    _autoReferencePathText: autoPathText,
    _manualEffectivePathText: manualPathText,
    _autoReferenceIsSamePath: Boolean(
      autoPathText && manualPathText && normalizeText(autoPathText) === normalizeText(manualPathText),
    ),
  }
}

export function mergeControlRelationRows(relationships = []) {
  const rows = Array.isArray(relationships) ? relationships : []
  const usedIndexes = new Set()

  return rows.map((row, index) => {
    if (usedIndexes.has(index)) {
      return null
    }
    if (!isManualJudgmentCurrentRow(row)) {
      return row
    }

    const autoIndex = rows.findIndex((candidate, candidateIndex) => {
      if (candidateIndex === index || usedIndexes.has(candidateIndex)) {
        return false
      }
      return canMergeManualJudgmentWithAutoReference(row, candidate).merge
    })

    if (autoIndex < 0) {
      return row
    }

    usedIndexes.add(autoIndex)
    const mergeDecision = canMergeManualJudgmentWithAutoReference(row, rows[autoIndex])
    return mergeRows(row, rows[autoIndex], mergeDecision.reason)
  }).filter(Boolean)
}

export const __controlRelationsMergeTestUtils = {
  canMergeManualJudgmentWithAutoReference,
}
