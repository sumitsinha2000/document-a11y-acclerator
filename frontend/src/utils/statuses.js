const FILE_STATUS_LABELS = {
  uploaded: "Uploaded",
  scanned: "Scanned",
  partially_fixed: "Partially Fixed",
  fixed: "Fixed",
  error: "Error",
}

const LEGACY_STATUS_MAP = {
  uploading: "uploaded",
  uploaded: "uploaded",
  unprocessed: "uploaded",
  processing: "uploaded",
  queued: "uploaded",
  pending: "uploaded",
  completed: "scanned",
  scanned: "scanned",
  finished: "scanned",
  processed: "partially_fixed",
  partially_fixed: "partially_fixed",
  fixing: "partially_fixed",
  fixed: "fixed",
  compliant: "fixed",
  error: "error",
}

export const normalizeStatusCode = (value, defaultCode = "uploaded") => {
  if (value === undefined || value === null) {
    return defaultCode
  }
  const normalized = String(value).trim().toLowerCase()
  return LEGACY_STATUS_MAP[normalized] || normalized || defaultCode
}

export const getStatusDisplay = (codeOrLabel, fallback = "Uploaded") => {
  const code = normalizeStatusCode(codeOrLabel)
  return FILE_STATUS_LABELS[code] || fallback
}

export const hasAnalysisError = (scan) => {
  if (!scan || typeof scan !== "object") {
    return false
  }
  const hasTopLevelError = Boolean(scan.error || scan.summary?.error)
  if (hasTopLevelError) {
    return true
  }
  const analysisErrors = scan.results?.analysisErrors
  return Array.isArray(analysisErrors) && analysisErrors.length > 0
}

export const getScanStatus = (entity, fallback = "uploaded") => {
  if (!entity || typeof entity !== "object") {
    return normalizeStatusCode(fallback)
  }

  const summaryStatus = entity.summary?.statusCode || entity.summary?.status
  const rawStatus = entity.statusCode || entity.status || summaryStatus || fallback
  const normalized = normalizeStatusCode(rawStatus, fallback)

  if (hasAnalysisError(entity)) {
    return "error"
  }

  return normalized
}

const coerceErrorMessage = (value) => {
  if (!value) {
    return null
  }
  if (typeof value === "string") {
    return value
  }
  if (typeof value?.message === "string") {
    return value.message
  }
  if (typeof value?.error === "string") {
    return value.error
  }
  return null
}

export const getScanErrorMessage = (scan, fallbackMessage = "We were unable to analyze this file.") => {
  if (!scan || typeof scan !== "object") {
    return fallbackMessage
  }

  const analysisErrors = scan.results?.analysisErrors
  if (hasAnalysisError(scan)) {
    const message =
      coerceErrorMessage(scan.error) ||
      coerceErrorMessage(scan.summary?.error) ||
      (Array.isArray(analysisErrors)
        ? analysisErrors.reduce((found, entry) => found || coerceErrorMessage(entry), null)
        : null)
    if (message) {
      return message
    }
  }

  return fallbackMessage
}

export const resolveEntityStatus = (entity, fallback = "uploaded") => {
  const code = getScanStatus(entity, fallback)
  const fallbackCode = normalizeStatusCode(fallback)
  return {
    code,
    label:
      FILE_STATUS_LABELS[code] ||
      (typeof entity?.status === "string" ? entity.status : null) ||
      (typeof entity?.statusCode === "string" ? entity.statusCode : null) ||
      FILE_STATUS_LABELS[fallbackCode] ||
      FILE_STATUS_LABELS.uploaded,
  }
}

export const isUploadedStatus = (entity) => {
  const { code } = resolveEntityStatus(entity)
  return code === "uploaded"
}

export const isScannedStatus = (entity) => {
  const { code } = resolveEntityStatus(entity)
  return code === "scanned"
}

export const isPartiallyFixedStatus = (entity) => {
  const { code } = resolveEntityStatus(entity)
  return code === "partially_fixed"
}

export const isFixedStatus = (entity) => {
  const { code } = resolveEntityStatus(entity)
  return code === "fixed"
}

export const FILE_STATUS_LABELS_MAP = FILE_STATUS_LABELS
