function normalizeKey(value) {
  return String(value ?? '').trim().toLowerCase()
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

function parsedBasis(row) {
  const parsed = parseMaybeJson(row?.basis)
  return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
}

function firstAvailable(row, key) {
  const basis = parsedBasis(row)
  return row?.[key] ?? basis?.[key]
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

function terminalFailureReason(row) {
  return normalizeKey(firstAvailable(row, 'terminal_failure_reason'))
}

export function isStructureSignalRow(row) {
  return (
    isTruthy(firstAvailable(row, 'ownership_pattern_signal')) ||
    normalizeKey(firstAvailable(row, 'terminal_identifiability')) === 'aggregation_like' ||
    normalizeKey(firstAvailable(row, 'terminal_suitability')) === 'pattern_only' ||
    terminalFailureReason(row) === 'ownership_aggregation_pattern' ||
    normalizeKey(firstAvailable(row, 'selection_reason')) ===
      'excluded_from_actual_race_due_to_terminal_profile'
  )
}

export function isManualJudgmentCandidateRow(row, options = {}) {
  if (!row || isStructureSignalRow(row)) {
    return false
  }
  if (options.isCurrentEffective) {
    return false
  }
  if (options.isAutomaticSuperseded) {
    return false
  }
  if (!firstAvailable(row, 'controller_entity_id')) {
    return false
  }
  if (['beneficial_owner_unknown', 'nominee_without_disclosure'].includes(terminalFailureReason(row))) {
    return false
  }
  return true
}
