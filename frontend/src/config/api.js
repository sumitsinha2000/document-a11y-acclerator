// API configuration
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:5000"

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
}

export default API_BASE_URL
