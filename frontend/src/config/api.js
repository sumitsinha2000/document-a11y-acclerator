// API configuration
const DEFAULT_API_BASE_URL = "http://localhost:5000"
const sanitize = (value) => {
  if (!value) return null
  return value.replace(/\/+$/, "")
}
const rawBaseUrl = (() => {
  if (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL
  }
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL
  }
  return null
})()
const API_BASE_URL = sanitize(rawBaseUrl) || sanitize(DEFAULT_API_BASE_URL)

export const API_ENDPOINTS = {
  upload: `${API_BASE_URL}/api/upload`,
  groups: `${API_BASE_URL}/api/groups`,
  health: `${API_BASE_URL}/api/health`,
  scan: `${API_BASE_URL}/api/scan`,
  scanBatch: `${API_BASE_URL}/api/scan-batch`,
  scans: `${API_BASE_URL}/api/scans`,
  history: `${API_BASE_URL}/api/history`,
  scanDetails: (scanId) => `${API_BASE_URL}/api/scan/${scanId}`,
  startScan: (scanId) => `${API_BASE_URL}/api/scan/${scanId}/start`,
  batchDetails: (batchId) => `${API_BASE_URL}/api/batch/${batchId}`,
  batchFixAll: (batchId) => `${API_BASE_URL}/api/batch/${batchId}/fix-all`,
  batchFixFile: (batchId, scanId) => `${API_BASE_URL}/api/batch/${batchId}/fix-file/${scanId}`,
  batchExport: (batchId) => `${API_BASE_URL}/api/batch/${batchId}/export`,
  applyFixes: (scanId) => `${API_BASE_URL}/api/apply-fixes/${scanId}`,
  fixHistory: (scanId) => `${API_BASE_URL}/api/fix-history/${scanId}`,
  downloadFixed: (filename) => `${API_BASE_URL}/api/download-fixed/${filename}`,
  previewPdf: (scanId) => `${API_BASE_URL}/api/scans/${scanId}/pdf`,
  export: (scanId) => `${API_BASE_URL}/api/export/${scanId}`,
  aiAnalyze: (scanId) => `${API_BASE_URL}/api/ai-analyze/${scanId}`,
  aiFixStrategy: (scanId) => `${API_BASE_URL}/api/ai-fix-strategy/${scanId}`,
  aiManualGuide: `${API_BASE_URL}/api/ai-manual-guide`,
  aiGenerateAltText: `${API_BASE_URL}/api/ai-generate-alt-text`,
  aiSuggestStructure: (scanId) => `${API_BASE_URL}/api/ai-suggest-structure/${scanId}`,
  aiApplyFixes: (scanId) => `${API_BASE_URL}/api/ai-apply-fixes/${scanId}`,
  applySemiAutomatedFixes: (scanId) =>
    `${API_BASE_URL}/api/apply-semi-automated-fixes/${scanId}`,
  fixProgress: (scanId) => `${API_BASE_URL}/api/fix-progress/${scanId}`,
}

export default API_BASE_URL
