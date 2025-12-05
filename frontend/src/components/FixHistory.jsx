import { useState, useEffect, useCallback } from "react"
import axios from "axios"
import { API_ENDPOINTS } from "../config/api"
import { useNotification } from "../contexts/NotificationContext"
import { parseBackendDate } from "../utils/dates"

const safeRenderFix = (fix) => {
  // If it's already a string, return it
  if (typeof fix === "string") {
    return fix
  }

  // If it's an object, try to extract meaningful text
  if (typeof fix === "object" && fix !== null) {
    // Try common properties that might contain displayable text
    if (fix.title) return fix.title
    if (fix.action) return fix.action
    if (fix.description) return fix.description
    if (fix.type) return fix.type
    if (fix.category) return fix.category
    if (fix.issueType) return fix.issueType

    // If it has a 'type' property from manual fixes
    if (fix.type && fix.data) {
      return `${fix.type} (Page ${fix.page || "N/A"})`
    }

    // Last resort: stringify the object
    return JSON.stringify(fix)
  }

  // Fallback
  return "Unknown fix"
}

const parseFixesApplied = (item) => {
  const raw = item.fixesApplied ?? item.fixes_applied ?? item.fixes ?? []
  if (Array.isArray(raw)) return raw
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}

const formatTimestamp = (item) => {
  const timestampValue = item.timestamp || item.appliedAt || item.applied_at || item.applied_at_iso
  return parseBackendDate(timestampValue)
}

const countSuccessfulFixes = (fixes) => {
  if (!Array.isArray(fixes)) return 0
  return fixes.reduce((total, fix) => {
    if (typeof fix === "object" && fix !== null) {
      return total + (fix.success === false ? 0 : 1)
    }
    return total + 1
  }, 0)
}

export default function FixHistory({ scanId, onRefresh, refreshSignal = 0 }) {
  const { showError } = useNotification()

  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isCollapsed, setIsCollapsed] = useState(true)

  const fetchFixHistory = useCallback(async () => {
    try {
      setLoading(true)
      console.log("[v0] Fetching fix history for scan:", scanId)

      const timestamp = Date.now()
      const response = await axios.get(API_ENDPOINTS.fixHistory(scanId), {
        headers: {
          "Cache-Control": "no-cache, no-store, must-revalidate",
          Pragma: "no-cache",
          Expires: "0",
        },
        params: {
          t: timestamp,
          _: Math.random(),
        },
      })

      console.log("[v0] Fix history response:", response.data)

      const historyData = response.data.history || []
      const latestVersion = response.data.latestVersion

      const transformedHistory = historyData.map((item, index) => {
        const fixesApplied = parseFixesApplied(item)
        const parsedTimestamp = formatTimestamp(item)
        const hasExplicitVersion = typeof item.version === "number" && !Number.isNaN(item.version)
        const fallbackFromLatest =
          typeof latestVersion === "number" ? latestVersion - index : null
        const fallbackFromLength = historyData.length - index
        const versionNumber = hasExplicitVersion
          ? item.version
          : fallbackFromLatest !== null
          ? fallbackFromLatest
          : null
        const versionLabel =
          item.versionLabel ||
          (versionNumber !== null ? `V${versionNumber}` : `V${Math.max(fallbackFromLength, 1)}`)
        const isLatestVersion =
          typeof latestVersion === "number" && versionNumber !== null
            ? versionNumber === latestVersion
            : Boolean(item.isLatest)

        const fixedFileReference =
          item.fixedFilePath ?? item.fixedFile ?? item.fixed_filename ?? item.fixed_filename

        const isLatestEntry = index === 0
        const canPreview =
          typeof item.previewable === "boolean"
            ? item.previewable
            : isLatestVersion || isLatestEntry
        const recordedSuccessCount =
          typeof item.successCount === "number"
            ? item.successCount
            : typeof item.success_count === "number"
            ? item.success_count
            : countSuccessfulFixes(fixesApplied)
        return {
          id: item.id || item.scan_id || index,
          timestamp: parsedTimestamp ? parsedTimestamp.toISOString() : null,
          timestampLabel: parsedTimestamp ? parsedTimestamp.toLocaleString() : "Unknown date",
          fixedFile: fixedFileReference,
          originalFile: item.originalFilename || item.original_filename || item.filename,
          fixesApplied,
          successCount: recordedSuccessCount,
          version: versionNumber,
          versionLabel,
          canPreview,
          downloadable:
            typeof item.downloadable === "boolean"
              ? item.downloadable
              : isLatestVersion || isLatestEntry,
        }
      })

      console.log("[v0] Transformed fix history:", transformedHistory)
      setHistory(transformedHistory)
      setError(null)
    } catch (err) {
      console.error("[v0] Error fetching fix history:", err)
      setError("Failed to load fix history")
    } finally {
      setLoading(false)
    }
  }, [scanId])

  useEffect(() => {
    fetchFixHistory()
  }, [fetchFixHistory, refreshSignal])

  const handlePreview = (item) => {
    if (!item || !item.fixedFile || !item.canPreview) {
      return
    }

    const previewUrl = API_ENDPOINTS.previewPdf(scanId)
    window.open(previewUrl, "_blank", "noopener,noreferrer")
  }

  const handleDownload = async (filename) => {
    if (!filename) {
      return
    }

    try {
      const response = await axios.get(API_ENDPOINTS.downloadFixed(filename), {
        responseType: "blob",
      })

      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement("a")
      link.href = url
      const downloadName = filename.split("/").pop() || filename
      link.setAttribute("download", downloadName)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error("[v0] Error downloading file:", error)
      showError("Failed to download file")
    }
  }

  if (loading) {
    return (
      <div className="p-7">
        <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-4">Fix History</h3>
        <div className="flex items-center gap-3 text-slate-600 dark:text-slate-400">
          <svg className="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          <span className="text-base font-medium">Loading fix history...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-7">
        <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-4">Fix History</h3>
        <div className="flex items-center gap-3 px-5 py-4 bg-yellow-50 dark:bg-yellow-900/10 border border-yellow-200 dark:border-yellow-800/30 rounded-lg">
          <svg
            className="w-5 h-5 text-yellow-600 dark:text-yellow-500 flex-shrink-0"
            fill="currentColor"
            viewBox="0 0 20 20"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
          <span className="text-base font-medium text-yellow-800 dark:text-yellow-300">No fix history available</span>
        </div>
      </div>
    )
  }

  if (history.length === 0) {
    return (
      <div className="p-7">
        <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-4">Fix History</h3>
        <div className="flex items-center gap-3 px-5 py-4 bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800/30 rounded-lg">
          <svg
            className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span className="text-base font-medium text-blue-800 dark:text-blue-300">No fixes have been applied yet</span>
        </div>
      </div>
    )
  }

  return (
    <div className="p-7">
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="w-full flex items-center justify-between mb-5 hover:opacity-80 transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-500 group"
        aria-pressed={!isCollapsed}
      >
        <h3 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
          Fix History
          <span className="px-3 py-1.5 bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 rounded-full text-base font-bold">
            {history.length}
          </span>
        </h3>
        <span
          className={`inline-flex items-center justify-center rounded-full w-10 h-10 transition-all ${
            isCollapsed
              ? "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300"
              : "bg-slate-100 text-slate-500 dark:bg-slate-800/60 dark:text-slate-400"
          }`}
        >
          <svg
            className={`w-5 h-5 transition-transform ${isCollapsed ? "" : "rotate-180"}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </span>
      </button>

      {!isCollapsed && (
        <div className="space-y-4">
          {history.map((item, index) => (
            <div
              key={item.id}
              className="border border-slate-200 dark:border-slate-700 rounded-lg p-5 hover:border-violet-400 dark:hover:border-violet-600 hover:shadow-md transition-all bg-white dark:bg-slate-800"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-3">
                    <span className="px-3 py-1.5 bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 rounded-md text-sm font-bold">
                      Version {item.versionLabel || history.length - index}
                    </span>
                    <span className="text-sm font-medium text-slate-600 dark:text-slate-400">
                      {item.timestampLabel || "Unknown date"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <svg
                      className="w-5 h-5 text-emerald-600 dark:text-emerald-400"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                      aria-hidden="true"
                    >
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                        clipRule="evenodd"
                      />
                    </svg>
                    <span className="text-base font-medium text-slate-700 dark:text-slate-300">
                      <span className="font-bold">{item.successCount}</span> fix(es) applied successfully
                    </span>
                  </div>
                </div>

                {item.fixedFile && item.canPreview && (
                  <div className="flex flex-col sm:flex-row gap-2">
                    <button
                      onClick={() => handlePreview(item)}
                      className="flex items-center gap-2 px-4 py-2.5 text-base font-semibold text-slate-600 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700/60 rounded-lg transition-colors"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14m0-4v4m-4 4a4 4 0 110-8 4 4 0 010 8z"
                        />
                      </svg>
                      View PDF
                    </button>

                    {item.downloadable && (
                      <button
                        onClick={() => handleDownload(item.fixedFile)}
                        className="flex items-center gap-2 px-4 py-2.5 text-base font-semibold text-violet-600 dark:text-violet-400 hover:bg-violet-50 dark:hover:bg-violet-900/20 rounded-lg transition-colors"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                          />
                        </svg>
                        Download
                      </button>
                    )}
                  </div>
                )}
              </div>

              {item.fixesApplied && item.fixesApplied.length > 0 && (
                <div className="pt-4 border-t border-slate-200 dark:border-slate-600">
                  <div className="text-sm font-bold text-slate-600 dark:text-slate-400 mb-3">Applied Fixes:</div>
                  <div className="flex flex-wrap gap-2">
                    {item.fixesApplied.map((fix, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center px-3 py-1.5 rounded-md text-sm font-semibold bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800"
                      >
                        {safeRenderFix(fix)}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
