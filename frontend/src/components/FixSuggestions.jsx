"use client"

import { useState } from "react"
import axios from "axios"
import PDFEditor from "./PDFEditor"
import { formatTimeEstimate } from "../utils/timeFormat"
import AIRemediationPanel from "./AIRemediationPanel"
import FixProgressStepper from "./FixProgressStepper"
import AlertModal from "./AlertModal"
import { API_ENDPOINTS } from "../config/api"

const showAlert =
  (setAlertModal) =>
  (title, message, type = "info") => {
    setAlertModal({ isOpen: true, title, message, type })
  }

export default function FixSuggestions({ scanId, fixes, filename, onRefresh }) {
  const [applyingTraditional, setApplyingTraditional] = useState(false)
  const [applyingAI, setApplyingAI] = useState(false)
  const [applyingTraditionalSemi, setApplyingTraditionalSemi] = useState(false)
  const [applyingAISemi, setApplyingAISemi] = useState(false)
  const [showEditor, setShowEditor] = useState(false)
  const [showAIPanel, setShowAIPanel] = useState(false)
  const [showProgressStepper, setShowProgressStepper] = useState(false)
  const [currentFixType, setCurrentFixType] = useState("")
  const [pendingProgressResult, setPendingProgressResult] = useState(null)

  const [alertModal, setAlertModal] = useState({ isOpen: false, title: "", message: "", type: "info" })
  const [expandedFixes, setExpandedFixes] = useState({
    automated: new Set(),
    semiAutomated: new Set(),
    manual: new Set(),
  })
  const [showMore, setShowMore] = useState({
    automated: false,
    semiAutomated: false,
    manual: false,
  })

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
      estimatedTime: formatTimeEstimate(fix.estimatedTime || fix.timeEstimate),
    }
  }

  const toggleFixExpansion = (category, index) => {
    setExpandedFixes((prev) => {
      const nextState = {
        automated: new Set(prev.automated),
        semiAutomated: new Set(prev.semiAutomated),
        manual: new Set(prev.manual),
      }
      const categorySet = nextState[category]

      if (categorySet.has(index)) {
        categorySet.delete(index)
      } else {
        categorySet.add(index)
      }

      return nextState
    })
  }

  const toggleViewMore = (category) => {
    setShowMore((prev) => ({
      ...prev,
      [category]: !prev[category],
    }))
  }

  const visibleFixes = (category, fixesArray) => {
    if (showMore[category]) return fixesArray
    return fixesArray.slice(0, 5)
  }

  const listIdFor = (category) => `${category}-fix-list-${scanId}`
  const descriptionIdFor = (category, index) => `${category}-fix-description-${scanId}-${index}`

  const handleApplyTraditionalFixes = async () => {
    setApplyingTraditional(true)
    setShowProgressStepper(true)
    setPendingProgressResult(null)
    setCurrentFixType("Traditional Automated Fixes")

    try {
      const response = await axios.post(API_ENDPOINTS.applyFixes(scanId), {
        useAI: false,
      })

      // Progress stepper will handle the completion
    } catch (error) {
      console.error("Error applying traditional fixes:", error)
      showAlert(setAlertModal)("Error applying fixes", error.response?.data?.message || error.message)
      setShowProgressStepper(false)
    } finally {
      setApplyingTraditional(false)
    }
  }

  const handleApplyAIFixes = async () => {
    setApplyingAI(true)
    setShowProgressStepper(true)
    setPendingProgressResult(null)
    setCurrentFixType("AI-Powered Automated Fixes")

    try {
      const response = await axios.post(API_ENDPOINTS.applyFixes(scanId), {
        useAI: true,
      })

      // Progress stepper will handle the completion
    } catch (error) {
      console.error("Error applying AI fixes:", error)
      showAlert(setAlertModal)("Error applying AI fixes", error.response?.data?.message || error.message)
      setShowProgressStepper(false)
    } finally {
      setApplyingAI(false)
    }
  }

  const handleApplyTraditionalSemiFixes = async () => {
    setApplyingTraditionalSemi(true)
    setShowProgressStepper(true)
    setPendingProgressResult(null)
    setCurrentFixType("Traditional Semi-Automated Fixes")

    try {
      const response = await axios.post(`/api/apply-semi-automated-fixes/${scanId}`, {
        useAI: false,
      })

      // Progress stepper will handle the completion
    } catch (error) {
      console.error("Error applying traditional semi-automated fixes:", error)
      showAlert(setAlertModal)("Error", error.response?.data?.message || error.message)
      setShowProgressStepper(false)
    } finally {
      setApplyingTraditionalSemi(false)
    }
  }

  const handleApplyAISemiFixes = async () => {
    setApplyingAISemi(true)
    setShowProgressStepper(true)
    setPendingProgressResult(null)
    setCurrentFixType("AI-Powered Semi-Automated Fixes")

    try {
      const response = await axios.post(`/api/apply-semi-automated-fixes/${scanId}`, {
        useAI: true,
      })

      // Progress stepper will handle the completion
    } catch (error) {
      console.error("Error applying AI semi-automated fixes:", error)
      showAlert(setAlertModal)("Error", error.response?.data?.message || error.message)
      setShowProgressStepper(false)
    } finally {
      setApplyingAISemi(false)
    }
  }

  const handleFixApplied = async (
    appliedFix,
    newSummary,
    newResults,
    newVerapdfStatus = null,
    newFixSuggestions = null,
  ) => {
    console.log("[v0] FixSuggestions - Fix applied in editor:", appliedFix)
    console.log("[v0] FixSuggestions - New summary received:", newSummary)
    console.log("[v0] FixSuggestions - New results received:", newResults)

    showAlert(setAlertModal)(
      "Manual Fix Applied",
      "Manual fix applied successfully! The PDF has been updated with your changes.",
      "success",
    )

    if (onRefresh) {
      console.log("[v0] FixSuggestions - Calling onRefresh with new data...")
      try {
        await onRefresh(newSummary, newResults, newVerapdfStatus, newFixSuggestions)
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
        await new Promise((resolve) => setTimeout(resolve, 300))
        await onRefresh()
        console.log("[v0] FixSuggestions - Data refreshed after editor close")
      } catch (error) {
        console.error("[v0] FixSuggestions - Error refreshing after editor close:", error)
      }
    }
  }

  const processProgressOutcome = async (outcome) => {
    if (!outcome) {
      return
    }

    const { success, newScanData } = outcome

    if (success) {
      const complianceScore = newScanData?.summary?.complianceScore
      const messageSuffix =
        typeof complianceScore === "number"
          ? ` New compliance score: ${Math.round(complianceScore)}%.`
          : ""

      console.log("[v0] FixSuggestions - Fixes applied successfully, preparing refresh")

      await new Promise((resolve) => setTimeout(resolve, 1500))

      if (onRefresh && newScanData) {
        try {
          console.log("[v0] FixSuggestions - Calling onRefresh with new scan data...")
          await onRefresh(
            newScanData?.summary,
            newScanData?.results || newScanData?.scanResults?.results,
            newScanData?.verapdfStatus,
            newScanData?.suggestions,
          )
          console.log("[v0] FixSuggestions - Refresh completed successfully")

          showAlert(setAlertModal)(
            `${currentFixType} Applied`,
            `${currentFixType} applied successfully! The report has been updated with the latest data.${messageSuffix}`,
            "success",
          )
        } catch (refreshError) {
          console.error("[v0] FixSuggestions - Error during refresh:", refreshError)
          showAlert(setAlertModal)(
            `${currentFixType} Applied`,
            `${currentFixType} applied successfully, but failed to refresh the report automatically. Please click the Refresh button to see the latest data.`,
            "warning",
          )
        }
      } else if (onRefresh) {
        try {
          console.log("[v0] FixSuggestions - Calling onRefresh without new scan payload...")
          await onRefresh()
          console.log("[v0] FixSuggestions - Refresh completed successfully")
          showAlert(setAlertModal)(
            `${currentFixType} Applied`,
            `${currentFixType} applied successfully! The report has been updated with the latest data.${messageSuffix}`,
            "success",
          )
        } catch (refreshError) {
          console.error("[v0] FixSuggestions - Error during refresh:", refreshError)
          showAlert(setAlertModal)(
            `${currentFixType} Applied`,
            `${currentFixType} applied successfully, but failed to refresh the report automatically. Please click the Refresh button to see the latest data.`,
            "warning",
          )
        }
      } else {
        console.warn("[v0] FixSuggestions - No onRefresh callback provided")
        showAlert(setAlertModal)(
          `${currentFixType} Applied`,
          `${currentFixType} applied successfully! Please refresh the page to see the latest data.${messageSuffix}`,
          "success",
        )
      }
    } else {
      console.error("[v0] FixSuggestions - Fix application failed")
      showAlert(setAlertModal)(
        "Fix Application Failed",
        "The fix process encountered errors. Please review the error details and try again.",
        "error",
      )
    }
  }

  const handleProgressComplete = async (success, newScanData) => {
    console.log("[v0] FixSuggestions - Progress complete:", { success, hasNewData: !!newScanData })
    const outcome = { success, newScanData }

    if (showProgressStepper) {
      setPendingProgressResult(outcome)
      return
    }

    setPendingProgressResult(null)
    await processProgressOutcome(outcome)
  }

  const handleProgressModalClose = async () => {
    setShowProgressStepper(false)

    if (!pendingProgressResult) {
      return
    }

    const outcome = pendingProgressResult

    try {
      await processProgressOutcome(outcome)
    } finally {
      setPendingProgressResult(null)
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
      {/* Progress Stepper Modal */}
      <FixProgressStepper
        scanId={scanId}
        isOpen={showProgressStepper}
        onClose={handleProgressModalClose}
        onComplete={handleProgressComplete}
      />

      {/* Alert Modal */}
      <AlertModal
        isOpen={alertModal.isOpen}
        onClose={() => setAlertModal({ ...alertModal, isOpen: false })}
        title={alertModal.title}
        message={alertModal.message}
        type={alertModal.type}
      />

      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-gray-900 dark:text-white">Remediation Suggestions</h3>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Est. Time: {formatTimeEstimate(fixes.estimatedTime)}
          </span>
          <button
            onClick={() => setShowAIPanel(true)}
            className="px-4 py-2 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white text-sm font-medium rounded-lg transition-all flex items-center gap-2 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
              focusable="false"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 01-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
              />
            </svg>
            AI Insights
          </button>
          {(hasSemiAutomated || hasManual) && (
            <button
              onClick={() => setShowEditor(true)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
              aria-label="Open PDF editor to apply manual fixes"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
                focusable="false"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                />
              </svg>
              Open PDF Editor
            </button>
          )}
        </div>
      </div>

      <div className="flex items-start gap-3 px-4 py-3 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 rounded-lg">
        <svg
          className="w-5 h-5 text-blue-600 dark:text-blue-300 mt-0.5"
          viewBox="0 0 24 24"
          fill="currentColor"
          aria-hidden="true"
          focusable="false"
        >
          <path
            fillRule="evenodd"
            d="M12 2.25c-5.385 0-9.75 4.365-9.75 9.75s4.365 9.75 9.75 9.75 9.75-4.365 9.75-9.75S17.385 2.25 12 2.25zm0 6.5a.875.875 0 110-1.75.875.875 0 010 1.75zm-.875 2.5c0-.483.392-.875.875-.875s.875.392.875.875V16.5a.875.875 0 11-1.75 0v-5.25z"
            clipRule="evenodd"
          />
        </svg>
        <p className="text-sm text-blue-900 dark:text-blue-100">
          Automated remediation sets the document <code className="font-mono text-xs bg-white/60 dark:bg-gray-800/60 px-1 py-0.5 rounded">/Lang</code> entry to <span className="font-semibold">en-US</span> whenever it is missing so screen readers always receive a default language.
        </p>
      </div>

      {showAIPanel && <AIRemediationPanel scanId={scanId} onClose={() => setShowAIPanel(false)} />}

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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" role="region" aria-label="Fix suggestions by type">
        {/* Automated Fixes Card */}
        {hasAutomated && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-4 border border-gray-200 dark:border-gray-700 flex flex-col">
            <h4 className="text-sm font-semibold text-green-600 dark:text-green-400 mb-1">Automated Fixes</h4>
            <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">Can be applied automatically</p>
            <div
              id={listIdFor("automated")}
              className="flex-1 space-y-2 mb-3"
              role="list"
              aria-live="polite"
            >
              {visibleFixes("automated", validAutomated).map((fix, idx) => {
                const isExpanded = expandedFixes.automated.has(idx)
                const descriptionId = descriptionIdFor("automated", idx)

                return (
                  <div
                    key={idx}
                    className="rounded-lg border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 focus-within:ring-2 focus-within:ring-green-500 focus-within:ring-offset-2 dark:focus-within:ring-offset-gray-900"
                    role="listitem"
                  >
                    <button
                      type="button"
                      onClick={() => toggleFixExpansion("automated", idx)}
                      className="w-full text-left flex gap-2 p-3 focus:outline-none"
                      aria-expanded={isExpanded}
                      aria-controls={descriptionId}
                    >
                      <div className="text-lg">
                        ⚙️
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-900 dark:text-white">{fix.title}</div>
                        <div
                          id={descriptionId}
                          className={`text-xs text-gray-600 dark:text-gray-400 mt-0.5 ${
                            isExpanded ? "" : "line-clamp-2"
                          }`}
                        >
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
                    </button>
                  </div>
                )
              })}
            </div>
            {validAutomated.length > 5 && (
              <button
                type="button"
                aria-expanded={showMore.automated}
                onClick={() => toggleViewMore("automated")}
                className="w-full mb-3 px-3 py-2 text-sm font-medium rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
              >
                {showMore.automated ? "View less" : `View more (${validAutomated.length - 5})`}
              </button>
            )}
            <div className="space-y-2 mt-auto">
              <button
                className="w-full px-4 py-2 bg-emerald-800 hover:bg-emerald-900 disabled:bg-gray-400 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-600 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
                onClick={handleApplyTraditionalFixes}
                disabled={applyingTraditional}
                aria-busy={applyingTraditional}
              >
                {applyingTraditional ? "Applying..." : "Apply Traditional Fixes"}
              </button>
            </div>
          </div>
        )}

        {/* Semi-Automated Fixes Card */}
        {hasSemiAutomated && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-4 border border-gray-200 dark:border-gray-700 flex flex-col">
            <h4 className="text-sm font-semibold text-yellow-600 dark:text-yellow-400 mb-1">Semi-Automated Fixes</h4>
            <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">Require review & confirmation</p>
            <div
              id={listIdFor("semiAutomated")}
              className="flex-1 space-y-2 mb-3"
              role="list"
              aria-live="polite"
            >
              {visibleFixes("semiAutomated", validSemiAutomated).map((fix, idx) => {
                const isExpanded = expandedFixes.semiAutomated.has(idx)
                const descriptionId = descriptionIdFor("semiAutomated", idx)

                return (
                  <div
                    key={idx}
                    className="rounded-lg border border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/20 focus-within:ring-2 focus-within:ring-yellow-500 focus-within:ring-offset-2 dark:focus-within:ring-offset-gray-900"
                    role="listitem"
                  >
                    <button
                      type="button"
                      onClick={() => toggleFixExpansion("semiAutomated", idx)}
                      className="w-full text-left flex gap-2 p-3 focus:outline-none"
                      aria-expanded={isExpanded}
                      aria-controls={descriptionId}
                    >
                      <div className="text-lg">
                        🔍
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-900 dark:text-white">{fix.title}</div>
                        <div
                          id={descriptionId}
                          className={`text-xs text-gray-600 dark:text-gray-400 mt-0.5 ${
                            isExpanded ? "" : "line-clamp-2"
                          }`}
                        >
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
                    </button>
                  </div>
                )
              })}
            </div>
            {validSemiAutomated.length > 5 && (
              <button
                type="button"
                aria-expanded={showMore.semiAutomated}
                onClick={() => toggleViewMore("semiAutomated")}
                className="w-full mb-3 px-3 py-2 text-sm font-medium rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
              >
                {showMore.semiAutomated ? "View less" : `View more (${validSemiAutomated.length - 5})`}
              </button>
            )}
            <div className="space-y-2 mt-auto">
              <button
                className="w-full px-4 py-2 bg-amber-800 hover:bg-amber-900 disabled:bg-gray-400 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-amber-600 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
                onClick={handleApplyTraditionalSemiFixes}
                disabled={applyingTraditionalSemi}
                aria-busy={applyingTraditionalSemi}
              >
                {applyingTraditionalSemi ? "Applying..." : "Apply Traditional Fixes"}
              </button>
            </div>
          </div>
        )}

        {/* Manual Fixes Card */}
        {hasManual && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-4 border border-gray-200 dark:border-gray-700 flex flex-col">
            <h4 className="text-sm font-semibold text-blue-600 dark:text-blue-400 mb-1">Manual Fixes</h4>
            <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">Require manual intervention</p>
            <div
              id={listIdFor("manual")}
              className="flex-1 space-y-2"
              role="list"
              aria-live="polite"
            >
              {visibleFixes("manual", validManual).map((fix, idx) => {
                const isExpanded = expandedFixes.manual.has(idx)
                const descriptionId = descriptionIdFor("manual", idx)

                return (
                  <div
                    key={idx}
                    className="rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-2 dark:focus-within:ring-offset-gray-900"
                    role="listitem"
                  >
                    <button
                      type="button"
                      onClick={() => toggleFixExpansion("manual", idx)}
                      className="w-full text-left flex gap-2 p-3 focus:outline-none"
                      aria-expanded={isExpanded}
                      aria-controls={descriptionId}
                    >
                      <div className="text-lg">
                        👤
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-900 dark:text-white">{fix.title}</div>
                        <div
                          id={descriptionId}
                          className={`text-xs text-gray-600 dark:text-gray-400 mt-0.5 ${
                            isExpanded ? "" : "line-clamp-2"
                          }`}
                        >
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
                    </button>
                  </div>
                )
              })}
            </div>
            {validManual.length > 5 && (
              <button
                type="button"
                aria-expanded={showMore.manual}
                onClick={() => toggleViewMore("manual")}
                className="w-full mb-3 px-3 py-2 text-sm font-medium rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
              >
                {showMore.manual ? "View less" : `View more (${validManual.length - 5})`}
              </button>
            )}
          </div>
        )}
      </div>

    </div>
  )
}
