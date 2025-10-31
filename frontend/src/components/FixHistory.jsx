"use client"

import { useState, useEffect } from "react"
import axios from "axios"

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

export default function FixHistory({ scanId, refreshToken }) {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isCollapsed, setIsCollapsed] = useState(true)

  useEffect(() => {
    fetchFixHistory()
  }, [scanId, refreshToken])

  const fetchFixHistory = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`/api/fix-history/${scanId}`)
      setHistory(response.data.history || [])
      setError(null)
    } catch (err) {
      console.error("Error fetching fix history:", err)
      setError("Failed to load fix history")
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = async (filename) => {
    try {
      const response = await axios.get(`/api/download-fixed/${filename}`, {
        responseType: "blob",
      })

      const downloadName = filename.endsWith(".pdf") ? filename : `${filename}.pdf`
      const blob = new Blob([response.data], {
        type: response.headers["content-type"] || "application/pdf",
      })

      const url = window.URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.setAttribute("download", downloadName)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error("Error downloading file:", error)
      alert("Failed to download file")
    }
  }

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-3">Fix History</h3>
        <div className="text-sm text-gray-500 dark:text-gray-400">Loading history...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-3">Fix History</h3>
        <div className="text-sm text-red-600 dark:text-red-400">{error}</div>
      </div>
    )
  }

  if (history.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-3">Fix History</h3>
        <div className="text-sm text-gray-500 dark:text-gray-400">No fixes have been applied to this document yet.</div>
      </div>
    )
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="w-full flex items-center justify-between text-left mb-3 hover:opacity-80 transition-opacity"
      >
        <h3 className="text-base font-semibold text-gray-900 dark:text-white">
          Fix History {history.length > 0 && `(${history.length})`}
        </h3>
        <svg
          className={`w-5 h-5 text-gray-500 dark:text-gray-400 transition-transform ${isCollapsed ? "" : "rotate-180"}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {!isCollapsed && (
        <div className="space-y-3">
          {history.map((item, index) => (
            <div
              key={item.id}
              className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 hover:border-blue-400 dark:hover:border-blue-600 transition-colors"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-medium text-blue-600 dark:text-blue-400">
                      Version {history.length - index}
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {new Date(item.timestamp).toLocaleString()}
                    </span>
                  </div>
                  <div className="text-sm text-gray-700 dark:text-gray-300 mb-1">
                    <span className="font-medium">{item.successCount}</span> fix(es) applied successfully
                  </div>
                </div>

                <button
                  onClick={() => handleDownload(item.fixedFile)}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                  Download
                </button>
              </div>

              {item.fixesApplied && item.fixesApplied.length > 0 && (
                <div className="mt-2 pt-2 border-t border-gray-100 dark:border-gray-700">
                  <div className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Applied Fixes:</div>
                  <div className="flex flex-wrap gap-1">
                    {item.fixesApplied.map((fix, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400"
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
