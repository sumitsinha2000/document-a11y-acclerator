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

export const resolveEntityStatus = (entity, fallback = "uploaded") => {
  if (!entity) {
    const code = normalizeStatusCode(fallback)
    return { code, label: FILE_STATUS_LABELS[code] || FILE_STATUS_LABELS.uploaded }
  }
  const code = normalizeStatusCode(entity.statusCode || entity.status || fallback)
  return {
    code,
    label: FILE_STATUS_LABELS[code] || entity.status || FILE_STATUS_LABELS.uploaded,
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
