const DEFAULT_API_BASE_URL = 'http://localhost:5000';

const sanitize = (value?: string | null) => {
  if (!value) return null;
  return value.replace(/\/+$/, '');
};

const resolveEnvBaseUrl = () => {
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL as string;
  }

  if (typeof process !== 'undefined' && process.env?.VITE_API_BASE_URL) {
    return process.env.VITE_API_BASE_URL;
  }

  return null;
};

const resolvedBase = sanitize(resolveEnvBaseUrl()) ?? sanitize(DEFAULT_API_BASE_URL) ?? DEFAULT_API_BASE_URL;

export const API_BASE_URL = resolvedBase;

export const API_ENDPOINTS = {
  upload: `${API_BASE_URL}/api/upload`,
  groups: `${API_BASE_URL}/api/groups`,
  projects: `${API_BASE_URL}/api/groups`,
  projectDetails: (projectId: string) => `${API_BASE_URL}/api/groups/${projectId}`,
  health: `${API_BASE_URL}/api/health`,
  scan: `${API_BASE_URL}/api/scan`,
  scanBatch: `${API_BASE_URL}/api/scan-batch`,
  scans: `${API_BASE_URL}/api/scans`,
  history: `${API_BASE_URL}/api/history`,
  scanDetails: (scanId: string) => `${API_BASE_URL}/api/scan/${scanId}`,
  startScan: (scanId: string) => `${API_BASE_URL}/api/scan/${scanId}/start`,
  batchDetails: (batchId: string) => `${API_BASE_URL}/api/batch/${batchId}`,
  renameBatch: (batchId: string) => `${API_BASE_URL}/api/batch/${batchId}/rename`,
  deleteBatch: (batchId: string) => `${API_BASE_URL}/api/batch/${batchId}`,
  batchFixAll: (batchId: string) => `${API_BASE_URL}/api/batch/${batchId}/fix-all`,
  batchFixFile: (batchId: string, scanId: string) => `${API_BASE_URL}/api/batch/${batchId}/fix-file/${scanId}`,
  batchExport: (batchId: string) => `${API_BASE_URL}/api/batch/${batchId}/export`,
  applyFixes: (scanId: string) => `${API_BASE_URL}/api/apply-fixes/${scanId}`,
  fixHistory: (scanId: string) => `${API_BASE_URL}/api/fix-history/${scanId}`,
  downloadFixed: (filename: string) => `${API_BASE_URL}/api/download-fixed/${filename}`,
  previewPdf: (scanId: string, version?: string | number) => {
    const base = `${API_BASE_URL}/api/pdf-file/${scanId}`;
    if (version || version === 0) {
      return `${base}?version=${encodeURIComponent(version)}`;
    }
    return base;
  },
  export: (scanId: string) => `${API_BASE_URL}/api/export/${scanId}`,
  aiAnalyze: (scanId: string) => `${API_BASE_URL}/api/ai-analyze/${scanId}`,
  aiFixStrategy: (scanId: string) => `${API_BASE_URL}/api/ai-fix-strategy/${scanId}`,
  aiManualGuide: `${API_BASE_URL}/api/ai-manual-guide`,
  aiGenerateAltText: `${API_BASE_URL}/api/ai-generate-alt-text`,
  aiSuggestStructure: (scanId: string) => `${API_BASE_URL}/api/ai-suggest-structure/${scanId}`,
  aiApplyFixes: (scanId: string) => `${API_BASE_URL}/api/ai-apply-fixes/${scanId}`,
  applySemiAutomatedFixes: (scanId: string) => `${API_BASE_URL}/api/apply-semi-automated-fixes/${scanId}`,
  fixProgress: (scanId: string) => `${API_BASE_URL}/api/fix-progress/${scanId}`,
} as const;

export type ApiEndpointKey = keyof typeof API_ENDPOINTS;

export default API_BASE_URL;
