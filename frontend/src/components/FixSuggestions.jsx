"use client"

import { useState } from "react"
import axios from "axios"
import PDFEditor from "./PDFEditor"
import { API_ENDPOINTS } from "../config/api"

export default function FixSuggestions({ scanId, fixes, filename, onRefresh }) {
  const [applying, setApplying] = useState(false)
  const [fixedFile, setFixedFile] = useState(null)
  const [showEditor, setShowEditor] = useState(false)

  const safeRender = (value, fallback = "N/A") => {
    if (value === null || value === undefined) return fallback
    if (typeof value === "string") return value
    if (typeof value === "number") return value.toString()
    if (typeof value === "object") {
      // If it's an object, try to extract meaningful text
      if (value.description) return value.description
      if (value.text) return value.text
      if (value.message) return value.message
      // Otherwise return a generic message
      return fallback
    }
    return String(value)
  }

  const cleanFix = (fix) => {
    if (!fix || typeof fix !== "object") return null

    return {
      title: safeRender(fix.title || fix.action, "Fix Required"),
      description: safeRender(fix.description || fix.instructions, "No description available"),
      severity: safeRender(fix.severity, "medium"),
      estimatedTime: safeRender(fix.estimatedTime || fix.timeEstimate, ""),
    }
  }

  const handleApplyFixes = async () => {
    setApplying(true)
    try {
      const response = await axios.post(API_ENDPOINTS.applyFixes(scanId))
      if (response.data.success) {
        setFixedFile({
          filename: response.data.fixedFile,
          message: response.data.message,
        })
        alert(response.data.message)

        if (onRefresh) {
          console.log("[v0] FixSuggestions - Refreshing data after automated fixes")
          await onRefresh()
        }
      } else {
        alert(response.data.message || "Failed to apply fixes")
      }
    } catch (error) {
      console.error("Error applying fixes:", error)
      alert("Error applying fixes: " + (error.response?.data?.message || error.message))
    } finally {
      setApplying(false)
    }
  }

  const handleDownloadFixed = () => {
    if (fixedFile) {
      window.open(API_ENDPOINTS.downloadFixed(fixedFile.filename), "_blank")
    }
  }

  const handleFixApplied = async (appliedFix, newSummary, newResults) => {
    console.log("[v0] FixSuggestions - Fix applied in editor:", appliedFix)
    console.log("[v0] FixSuggestions - New summary received:", newSummary)
    console.log("[v0] FixSuggestions - New results received:", newResults)
    console.log("[v0] FixSuggestions - Current fixes before refresh:", fixes)

    if (onRefresh) {
      console.log("[v0] FixSuggestions - Calling onRefresh with new data...")
      try {
        await new Promise((resolve) => setTimeout(resolve, 200))
        await onRefresh(newSummary, newResults)
        console.log("[v0] FixSuggestions - onRefresh completed successfully")
      } catch (error) {
        console.error("[v0] FixSuggestions - Error during refresh:", error)
      }
    } else {
      console.warn("[v0] FixSuggestions - No onRefresh callback provided")
    }
  }

  const handleEditorClose = async () => {
    console.log("[v0] FixSuggestions - Editor closing, refreshing data...")
    setShowEditor(false)

    if (onRefresh) {
      try {
        await new Promise((resolve) => setTimeout(resolve, 500))
        await onRefresh()
        console.log("[v0] FixSuggestions - Data refreshed after editor close")
      } catch (error) {
        console.error("[v0] FixSuggestions - Error refreshing after editor close:", error)
      }
    }
  }

  const validAutomated = Array.isArray(fixes?.automated) ? fixes.automated.map(cleanFix).filter(Boolean) : []
  const validSemiAutomated = Array.isArray(fixes?.semiAutomated)
    ? fixes.semiAutomated.map(cleanFix).filter(Boolean)
    : []
  const validManual = Array.isArray(fixes?.manual) ? fixes.manual.map(cleanFix).filter(Boolean) : []

  const hasAutomated = validAutomated.length > 0
  const hasSemiAutomated = validSemiAutomated.length > 0
  const hasManual = validManual.length > 0
  const hasAnyFixes = hasAutomated || hasSemiAutomated || hasManual

  if (!fixes) {
    return (
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-6 text-center border border-gray-200 dark:border-gray-700">
        <p className="text-sm text-gray-600 dark:text-gray-400">No fix suggestions available.</p>
      </div>
    )
  }

  if (!hasAnyFixes) {
    return (
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-6 text-center border border-gray-200 dark:border-gray-700">
        <p className="text-sm text-gray-600 dark:text-gray-400">No fix suggestions available for this document.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-gray-900 dark:text-white">Remediation Suggestions</h3>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Est. Time: {safeRender(fixes.estimatedTime, "N/A")} minutes
          </span>
          {(hasSemiAutomated || hasManual) && (
            <button
              onClick={() => setShowEditor(true)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                />
              </svg>
              Open PDF Editor
            </button>
          )}
        </div>
      </div>

      {showEditor && (
        <PDFEditor
          key={`editor-${scanId}-${JSON.stringify(fixes)}`}
          scanId={scanId}
          filename={filename}
          fixes={fixes}
          onClose={handleEditorClose}
          onFixApplied={handleFixApplied}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Automated Fixes Card */}
        {hasAutomated && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-4 border border-gray-200 dark:border-gray-700">
            <h4 className="text-sm font-semibold text-green-600 dark:text-green-400 mb-1">Automated Fixes</h4>
            <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">Can be applied automatically</p>
            <div className="space-y-2 mb-3">
              {validAutomated.map((fix, idx) => (
                <div
                  key={idx}
                  className="flex gap-2 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800"
                >
                  <div className="text-lg">⚙️</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 dark:text-white truncate">{fix.title}</div>
                    <div className="text-xs text-gray-600 dark:text-gray-400 mt-0.5 line-clamp-2">
                      {fix.description}
                    </div>
                    <div className="flex gap-2 mt-1 text-xs text-gray-500 dark:text-gray-400">
                      <span className="font-medium capitalize">{fix.severity}</span>
                      {fix.estimatedTime && (
                        <>
                          <span>•</span>
                          <span>{fix.estimatedTime} min</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <button
              className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white text-sm font-medium rounded-lg transition-colors"
              onClick={handleApplyFixes}
              disabled={applying}
            >
              {applying ? "Applying..." : "Apply Fixes"}
            </button>
          </div>
        )}

        {/* Semi-Automated Fixes Card */}
        {hasSemiAutomated && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-4 border border-gray-200 dark:border-gray-700">
            <h4 className="text-sm font-semibold text-yellow-600 dark:text-yellow-400 mb-1">Semi-Automated Fixes</h4>
            <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">Require review & confirmation</p>
            <div className="space-y-2">
              {validSemiAutomated.map((fix, idx) => (
                <div
                  key={idx}
                  className="flex gap-2 p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800"
                >
                  <div className="text-lg">🔍</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 dark:text-white truncate">{fix.title}</div>
                    <div className="text-xs text-gray-600 dark:text-gray-400 mt-0.5 line-clamp-2">
                      {fix.description}
                    </div>
                    <div className="flex gap-2 mt-1 text-xs text-gray-500 dark:text-gray-400">
                      <span className="font-medium capitalize">{fix.severity}</span>
                      {fix.estimatedTime && (
                        <>
                          <span>•</span>
                          <span>{fix.estimatedTime} min</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Manual Fixes Card */}
        {hasManual && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-4 border border-gray-200 dark:border-gray-700">
            <h4 className="text-sm font-semibold text-blue-600 dark:text-blue-400 mb-1">Manual Fixes</h4>
            <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">Require manual intervention</p>
            <div className="space-y-2">
              {validManual.map((fix, idx) => (
                <div
                  key={idx}
                  className="flex gap-2 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800"
                >
                  <div className="text-lg">👤</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 dark:text-white truncate">{fix.title}</div>
                    <div className="text-xs text-gray-600 dark:text-gray-400 mt-0.5 line-clamp-2">
                      {fix.description}
                    </div>
                    <div className="flex gap-2 mt-1 text-xs text-gray-500 dark:text-gray-400">
                      <span className="font-medium capitalize">{fix.severity}</span>
                      {fix.estimatedTime && (
                        <>
                          <span>•</span>
                          <span>{fix.estimatedTime} min</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {fixedFile && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-green-800 dark:text-green-200">Fixes Applied Successfully!</p>
              <p className="text-xs text-green-600 dark:text-green-400 mt-1">{fixedFile.message}</p>
            </div>
            <button
              onClick={handleDownloadFixed}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                />
              </svg>
              Download Fixed PDF
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
