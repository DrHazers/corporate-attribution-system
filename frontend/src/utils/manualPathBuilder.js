export function normalizeManualPathName(value) {
  return String(value ?? '').trim()
}

export function normalizeManualPathRatio(value) {
  return String(value ?? '').trim()
}

export function manualPathIntermediateNames(path) {
  return (path?.intermediate_nodes || [])
    .map((node) => normalizeManualPathName(node?.name))
    .filter(Boolean)
}

export function manualControllerLabel({ controllerEntityId = null, controllerName = '' } = {}) {
  const name = normalizeManualPathName(controllerName)
  if (name) {
    return name
  }
  if (controllerEntityId !== null && controllerEntityId !== undefined && controllerEntityId !== '') {
    return `主体 ${controllerEntityId}`
  }
  return '待填写实际控制人'
}

export function hasManualController({ controllerEntityId = null, controllerName = '' } = {}) {
  return (
    (controllerEntityId !== null && controllerEntityId !== undefined && controllerEntityId !== '') ||
    Boolean(normalizeManualPathName(controllerName))
  )
}

export function deriveManualPathDisplay({
  paths = [],
  controllerEntityId = null,
  controllerName = '',
  targetCompanyName = '当前目标公司',
} = {}) {
  const controllerReady = hasManualController({ controllerEntityId, controllerName })
  const startLabel = manualControllerLabel({ controllerEntityId, controllerName })
  const targetLabel = normalizeManualPathName(targetCompanyName) || '当前目标公司'
  const pathRows = Array.isArray(paths) && paths.length ? paths : [{ intermediate_nodes: [] }]
  const texts = pathRows.map((path) =>
    [startLabel, ...manualPathIntermediateNames(path), targetLabel].join(' → '),
  )
  const ratios = pathRows.map((path) => normalizeManualPathRatio(path?.path_ratio))

  return {
    hasController: controllerReady,
    controllerLabel: startLabel,
    targetCompanyName: targetLabel,
    pathTexts: texts,
    pathRatios: ratios,
    summary: controllerReady ? texts[0] || '' : '',
    pathCount: controllerReady ? pathRows.length : 0,
    pathDepth: controllerReady ? manualPathIntermediateNames(pathRows[0]).length + 1 : null,
  }
}

export function buildManualPathPayloads({
  paths = [],
  controllerEntityId = null,
  controllerName = '',
  targetCompanyId = null,
  targetCompanyName = '当前目标公司',
} = {}) {
  const display = deriveManualPathDisplay({
    paths,
    controllerEntityId,
    controllerName,
    targetCompanyName,
  })
  if (!display.hasController) {
    return []
  }

  return paths.map((path, pathIndex) => {
    const middleNames = manualPathIntermediateNames(path)
    const pathRatio = normalizeManualPathRatio(path?.path_ratio)
    return {
      path_index: pathIndex + 1,
      entity_ids: [
        controllerEntityId,
        ...middleNames.map(() => null),
        targetCompanyId,
      ],
      entity_names: [
        display.controllerLabel,
        ...middleNames,
        display.targetCompanyName,
      ],
      ...(pathRatio ? { path_ratio: pathRatio, control_ratio: pathRatio } : {}),
      is_primary: pathIndex === 0,
    }
  })
}

export function middleNamesFromManualPathRecord(path) {
  const names = Array.isArray(path?.entity_names) ? path.entity_names : []
  return names
    .slice(1, Math.max(1, names.length - 1))
    .map((name) => normalizeManualPathName(name))
    .filter(Boolean)
}

export function pathRatioFromManualPathRecord(path) {
  return normalizeManualPathRatio(
    path?.path_ratio ?? path?.control_ratio ?? path?.ratio ?? path?.path_strength,
  )
}

export function middleNamesFromLegacyPathText(value) {
  const text = normalizeManualPathName(value)
  if (!text) {
    return []
  }
  const names = text
    .replaceAll('=>', '→')
    .replaceAll('->', '→')
    .replaceAll('—>', '→')
    .split('→')
    .map((segment) => segment.trim())
    .filter(Boolean)
  return names.length >= 3 ? names.slice(1, -1) : []
}
