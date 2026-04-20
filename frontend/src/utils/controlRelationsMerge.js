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
    return names.join(' -> ')
  }
  return pathIds(path).map((id) => `主体 ${id}`).join(' -> ')
}

function relationSource(row = {}) {
  return normalizeKey(
    firstAvailable(row, 'source_type', 'result_source', 'manual_result_source'),
  )
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

function isManualRow(row = {}) {
  return relationSource(row).startsWith('manual')
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

function isManualCurrentRow(row = {}) {
  return (
    isManualRow(row) &&
    !isTruthy(firstAvailable(row, 'automatic_result_superseded')) &&
    (
      isTruthy(firstAvailable(row, 'is_manual_effective')) ||
      isTruthy(firstAvailable(row, 'is_current_effective'))
    )
  )
}

function isAutomaticReferenceRow(row = {}) {
  return (
    isTruthy(firstAvailable(row, 'automatic_result_superseded')) &&
    !isManualRow(row)
  )
}

function isAutomaticActualRow(row = {}) {
  if (isAutomaticReferenceRow(row)) {
    return false
  }
  return (
    !isManualRow(row) &&
    (
      isTruthy(firstAvailable(row, 'is_actual_controller')) ||
      normalizeKey(firstAvailable(row, 'controller_status')) === 'actual_controller'
    )
  )
}

function isDirectRow(row = {}) {
  return (
    isTruthy(firstAvailable(row, 'is_direct_controller')) ||
    normalizeKey(firstAvailable(row, 'control_tier')) === 'direct'
  )
}

function isLeadingRow(row = {}) {
  return (
    isTruthy(firstAvailable(row, 'is_leading_candidate')) ||
    normalizeKey(firstAvailable(row, 'controller_status')) === 'leading_candidate'
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

function subjectKey(row = {}, index = 0) {
  const entityId = String(row?.controller_entity_id ?? '').trim()
  if (entityId) {
    return `entity:${entityId}`
  }
  const name = normalizeText(row?.controller_name)
  const type = normalizeKey(row?.controller_type)
  if (name) {
    return `name:${name}:${type || 'unknown'}`
  }
  return `row:${index}`
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

function hasCompatibleControlType(primaryRow = {}, autoRow = {}) {
  const primaryGroups = typeCandidates(primaryRow).map(controlTypeGroup).filter(Boolean)
  const autoGroups = typeCandidates(autoRow).map(controlTypeGroup).filter(Boolean)
  if (!primaryGroups.length || !autoGroups.length) {
    return true
  }
  return primaryGroups.some((group) => autoGroups.includes(group))
}

function sameEndpoint(primaryPath = {}, autoPath = {}) {
  const primaryIds = pathIds(primaryPath)
  const autoIds = pathIds(autoPath)
  if (primaryIds.length && autoIds.length) {
    return primaryIds[primaryIds.length - 1] === autoIds[autoIds.length - 1]
  }
  const primaryNames = pathNames(primaryPath)
  const autoNames = pathNames(autoPath)
  if (primaryNames.length && autoNames.length) {
    return primaryNames[primaryNames.length - 1] === autoNames[autoNames.length - 1]
  }
  return true
}

function pathCompatibility(primaryRow = {}, autoRow = {}) {
  const primaryPath = getControlPaths(primaryRow)[0]
  const autoPath = getControlPaths(autoRow)[0]
  if (!primaryPath || !autoPath) {
    return { compatible: true, samePath: false, reason: 'missing_path' }
  }

  if (
    sameList(pathIds(primaryPath), pathIds(autoPath)) ||
    sameList(pathNames(primaryPath), pathNames(autoPath))
  ) {
    return { compatible: true, samePath: true, reason: 'same_path' }
  }

  if (sameEndpoint(primaryPath, autoPath)) {
    return { compatible: true, samePath: false, reason: 'auto_reference_path' }
  }

  return { compatible: false, samePath: false, reason: 'path_conflict' }
}

function hasCompatibleRatio(primaryRow = {}, autoRow = {}) {
  const primaryRatio = rowRatio(primaryRow)
  const autoRatio = rowRatio(autoRow)
  if (primaryRatio === null || autoRatio === null) {
    return true
  }
  return Math.abs(primaryRatio - autoRatio) <= SAME_RATIO_TOLERANCE
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

function rowPriority(row = {}) {
  if (isManualCurrentRow(row)) {
    return 0
  }
  if (isAutomaticActualRow(row)) {
    return 1
  }
  if (isAutomaticReferenceRow(row)) {
    return 2
  }
  if (isDirectRow(row)) {
    return 3
  }
  if (isLeadingRow(row)) {
    return 4
  }
  return 5
}

function choosePrimaryRow(rows = []) {
  return [...rows].sort((left, right) => {
    const priorityDelta = rowPriority(left) - rowPriority(right)
    if (priorityDelta !== 0) {
      return priorityDelta
    }
    const ratioDelta = (rowRatio(right) ?? -1) - (rowRatio(left) ?? -1)
    if (ratioDelta !== 0) {
      return ratioDelta
    }
    return (left._mergeOriginalIndex ?? 0) - (right._mergeOriginalIndex ?? 0)
  })[0] || null
}

function firstNonEmpty(...values) {
  return values.find((value) => value !== null && value !== undefined && value !== '') ?? null
}

function mergeSecondaryFlags(primaryRow = {}, secondaryRows = []) {
  const relatedRows = [primaryRow, ...secondaryRows]
  const byPriority = [...relatedRows].sort((left, right) => rowPriority(left) - rowPriority(right))
  const firstDirect = byPriority.find((row) => isDirectRow(row))
  const firstActual = byPriority.find((row) => isAutomaticActualRow(row) || isManualCurrentRow(row))

  return {
    controller_type: firstNonEmpty(
      primaryRow.controller_type,
      firstActual?.controller_type,
      firstDirect?.controller_type,
    ),
    control_tier: firstNonEmpty(
      primaryRow.control_tier,
      firstActual?.control_tier,
      firstDirect?.control_tier,
    ),
    is_direct_controller:
      primaryRow.is_direct_controller || secondaryRows.some((row) => isTruthy(row?.is_direct_controller)),
    is_intermediate_controller:
      primaryRow.is_intermediate_controller ||
      secondaryRows.some((row) => isTruthy(row?.is_intermediate_controller)),
    is_ultimate_controller:
      primaryRow.is_ultimate_controller || secondaryRows.some((row) => isTruthy(row?.is_ultimate_controller)),
    is_actual_controller:
      primaryRow.is_actual_controller || secondaryRows.some((row) => isTruthy(row?.is_actual_controller)),
    is_leading_candidate:
      primaryRow.is_leading_candidate || secondaryRows.some((row) => isTruthy(row?.is_leading_candidate)),
    controller_status: firstNonEmpty(
      primaryRow.controller_status,
      firstActual?.controller_status,
      firstDirect?.controller_status,
    ),
  }
}

function mergeRows(primaryRow = {}, secondaryRows = []) {
  const compatibleAutoReference = secondaryRows.find((row) => {
    if (!isAutomaticReferenceRow(row)) {
      return false
    }
    if (!sameSubject(primaryRow, row)) {
      return false
    }
    if (!hasCompatibleControlType(primaryRow, row)) {
      return false
    }
    const pathResult = pathCompatibility(primaryRow, row)
    if (!pathResult.compatible) {
      return false
    }
    return hasCompatibleRatio(primaryRow, row)
  }) || null

  const merged = {
    ...primaryRow,
    ...mergeSecondaryFlags(primaryRow, secondaryRows),
  }

  if (!secondaryRows.length) {
    return merged
  }

  merged._secondaryRelationships = secondaryRows

  if (!compatibleAutoReference) {
    return merged
  }

  const autoPathText = primaryPathText(compatibleAutoReference)
  const manualPathText = primaryPathText(primaryRow)
  const pathResult = pathCompatibility(primaryRow, compatibleAutoReference)

  return {
    ...merged,
    _hasMergedAutoReference: true,
    _autoReferenceRelationship: compatibleAutoReference,
    _autoReferenceMergeReason: pathResult.reason,
    _autoReferenceControlType: compatibleAutoReference.control_type,
    _autoReferenceControlRatio: compatibleAutoReference.control_ratio,
    _autoReferencePathText: autoPathText,
    _manualEffectivePathText: manualPathText,
    _autoReferenceIsSamePath: Boolean(
      autoPathText && manualPathText && normalizeText(autoPathText) === normalizeText(manualPathText),
    ),
  }
}

export function mergeControlRelationRows(relationships = []) {
  const rows = Array.isArray(relationships) ? relationships : []
  const groups = new Map()

  rows.forEach((row, index) => {
    const normalizedRow = {
      ...row,
      _mergeOriginalIndex: index,
    }
    const key = subjectKey(normalizedRow, index)
    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key).push(normalizedRow)
  })

  return Array.from(groups.values())
    .map((groupRows) => {
      const primary = choosePrimaryRow(groupRows)
      if (!primary) {
        return null
      }
      const secondaryRows = groupRows.filter(
        (row) => row._mergeOriginalIndex !== primary._mergeOriginalIndex,
      )
      return mergeRows(primary, secondaryRows)
    })
    .filter(Boolean)
    .map(({ _mergeOriginalIndex, ...row }) => row)
}

export const __controlRelationsMergeTestUtils = {
  canMergeManualJudgmentWithAutoReference,
}
