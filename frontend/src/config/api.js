// API configuration
const API_BASE_URL = import.meta.env.VITE_API_URL || ""

export const API_ENDPOINTS = {
  health: `${API_BASE_URL}/api/health`,
  scan: `${API_BASE_URL}/api/scan`,
  scanBatch: `${API_BASE_URL}/api/scan-batch`,
  scans: `${API_BASE_URL}/api/scans`,
  history: `${API_BASE_URL}/api/history`,
  scanDetails: (scanId) => `${API_BASE_URL}/api/scan/${scanId}`,
  batchDetails: (batchId) => `${API_BASE_URL}/api/batch/${batchId}`,
  batchFixAll: (batchId) => `${API_BASE_URL}/api/batch/${batchId}/fix-all`,
  batchFixFile: (batchId, scanId) => `${API_BASE_URL}/api/batch/${batchId}/fix-file/${scanId}`,
  batchExport: (batchId) => `${API_BASE_URL}/api/batch/${batchId}/export`,
  applyFixes: (scanId) => `${API_BASE_URL}/api/apply-fixes/${scanId}`,
  fixHistory: (scanId) => `${API_BASE_URL}/api/fix-history/${scanId}`,
  downloadFixed: (filename) => `${API_BASE_URL}/api/download-fixed/${filename}`,
  export: (scanId) => `${API_BASE_URL}/api/export/${scanId}`,
  aiAnalyze: (scanId) => `${API_BASE_URL}/api/ai-analyze/${scanId}`,
  aiFixStrategy: (scanId) => `${API_BASE_URL}/api/ai-fix-strategy/${scanId}`,
  aiManualGuide: `${API_BASE_URL}/api/ai-manual-guide`,
  aiGenerateAltText: `${API_BASE_URL}/api/ai-generate-alt-text`,
  aiSuggestStructure: (scanId) => `${API_BASE_URL}/api/ai-suggest-structure/${scanId}`,
  aiApplyFixes: (scanId) => `${API_BASE_URL}/api/ai-apply-fixes/${scanId}`,
}

export default API_BASE_URL
