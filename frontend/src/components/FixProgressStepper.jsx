"use client"

import { useState, useEffect } from "react"
import axios from "axios"

export default function FixProgressStepper({ scanId, isOpen, onClose, onComplete }) {
  const [progress, setProgress] = useState(null)
  const [polling, setPolling] = useState(true)
  const [finalResultData, setFinalResultData] = useState(null)

  useEffect(() => {
    if (!isOpen || !scanId) return

    let pollInterval
    let latestResultData = null

    const pollProgress = async () => {
      try {
        const response = await axios.get(`/api/fix-progress/${scanId}`)
        const progressData = response.data

        console.log("[v0] Progress update:", progressData)
        setProgress(progressData)

        // Stop polling if completed or failed
        if (progressData.status === "completed" || progressData.status === "failed") {
          setPolling(false)
          clearInterval(pollInterval)

          if (progressData.status === "completed") {
            console.log(
              "[v0] FixProgressStepper: All steps:",
              progressData.steps.map((s) => ({ name: s.name, status: s.status, hasResultData: !!s.resultData })),
            )

            // Look for the re-scan step to get new results
            const rescanStep = progressData.steps.find(
              (step) => step.name === "Re-scan Fixed PDF" && step.status === "completed",
            )

            console.log("[v0] FixProgressStepper: Re-scan step found:", rescanStep ? "YES" : "NO")
            if (rescanStep) {
              console.log("[v0] FixProgressStepper: Re-scan step full object:", rescanStep)
              console.log("[v0] FixProgressStepper: Re-scan step keys:", Object.keys(rescanStep))
              console.log("[v0] FixProgressStepper: Re-scan step.resultData type:", typeof rescanStep.resultData)
              console.log("[v0] FixProgressStepper: Re-scan step.resultData value:", rescanStep.resultData)

              if (rescanStep.resultData) {
                console.log("[v0] FixProgressStepper: resultData keys:", Object.keys(rescanStep.resultData))
              }
            }

            if (rescanStep && rescanStep.resultData) {
              console.log("[v0] FixProgressStepper: Found new scan results from re-scan:", rescanStep.resultData)
              latestResultData = rescanStep.resultData
              setFinalResultData(rescanStep.resultData)
            } else {
              console.log("[v0] FixProgressStepper: No resultData found in re-scan step")
            }
          }

          // Wait a bit before calling onComplete to show final state
          setTimeout(() => {
            console.log("[v0] FixProgressStepper: Calling onComplete with:", {
              success: progressData.status === "completed",
              resultData: latestResultData,
            })
            if (onComplete) {
              onComplete(progressData.status === "completed", latestResultData)
            }
          }, 2000)
        }
      } catch (error) {
        console.error("[v0] Error polling progress:", error)
        // Continue polling even on error - the fix might still be running
      }
    }

    // Initial poll
    pollProgress()

    // Poll every 500ms for smooth updates
    if (polling) {
      pollInterval = setInterval(pollProgress, 500)
    }

    return () => {
      if (pollInterval) {
        clearInterval(pollInterval)
      }
    }
  }, [scanId, isOpen, polling, onComplete])

  if (!isOpen || !progress) {
    return null
  }

  const getStepIcon = (status) => {
    switch (status) {
      case "completed":
        return (
          <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
        )
      case "in_progress":
        return (
          <svg className="w-5 h-5 text-white animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        )
      case "failed":
        return (
          <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        )
      case "skipped":
        return (
          <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM7 9a1 1 0 000 2h6a1 1 0 100-2H7z"
              clipRule="evenodd"
            />
          </svg>
        )
      default:
        return <div className="w-2 h-2 bg-white rounded-full" />
    }
  }

  const getStepColor = (status) => {
    switch (status) {
      case "completed":
        return "bg-green-600"
      case "in_progress":
        return "bg-blue-600"
      case "failed":
        return "bg-red-600"
      case "skipped":
        return "bg-gray-400"
      default:
        return "bg-gray-300"
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Applying Fixes</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {progress.status === "completed"
                  ? "✅ All fixes applied successfully! Your document has been remediated."
                  : progress.status === "failed"
                    ? "❌ Fix process encountered errors. Please review the details below."
                    : `Processing step ${progress.currentStep} of ${progress.totalSteps}...`}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              aria-label="Close progress dialog"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Progress Bar */}
          <div className="mt-4">
            <div className="flex items-center justify-between text-sm mb-2">
              <span className="text-gray-600 dark:text-gray-400">Overall Progress</span>
              <span className="font-semibold text-gray-900 dark:text-white">{progress.progress}%</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
              <div
                className="bg-gradient-to-r from-blue-600 to-purple-600 h-full transition-all duration-500 ease-out"
                style={{ width: `${progress.progress}%` }}
              />
            </div>
          </div>
        </div>

        {/* Steps List */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div className="space-y-4">
            {progress.steps.map((step, index) => (
              <div key={step.id} className="flex gap-4">
                {/* Step Icon */}
                <div className="flex flex-col items-center">
                  <div
                    className={`w-10 h-10 rounded-full ${getStepColor(step.status)} flex items-center justify-center flex-shrink-0 transition-all duration-300`}
                  >
                    {getStepIcon(step.status)}
                  </div>
                  {index < progress.steps.length - 1 && (
                    <div
                      className={`w-0.5 flex-1 mt-2 transition-colors duration-300 ${
                        step.status === "completed" ? "bg-green-600" : "bg-gray-300 dark:bg-gray-600"
                      }`}
                      style={{ minHeight: "20px" }}
                    />
                  )}
                </div>

                {/* Step Content */}
                <div className="flex-1 pb-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h4 className="text-sm font-semibold text-gray-900 dark:text-white">{step.name}</h4>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{step.description}</p>

                      {/* Step Details */}
                      {step.details && (
                        <p className="text-xs text-gray-500 dark:text-gray-500 mt-2 bg-gray-50 dark:bg-gray-900/20 rounded px-2 py-1">
                          {step.details}
                        </p>
                      )}

                      {/* Error Message */}
                      {step.error && (
                        <div className="mt-2 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded px-2 py-1">
                          <span className="font-semibold">Error:</span> {step.error}
                        </div>
                      )}

                      {/* Duration */}
                      {step.duration && (
                        <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                          Completed in {step.duration.toFixed(2)}s
                        </p>
                      )}
                    </div>

                    {/* Status Badge */}
                    <span
                      className={`ml-3 px-2 py-1 text-xs font-medium rounded-full flex-shrink-0 ${
                        step.status === "completed"
                          ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                          : step.status === "in_progress"
                            ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
                            : step.status === "failed"
                              ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                              : step.status === "skipped"
                                ? "bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400"
                                : "bg-gray-100 text-gray-600 dark:bg-gray-900/30 dark:text-gray-400"
                      }`}
                    >
                      {step.status === "in_progress"
                        ? "In Progress"
                        : step.status.charAt(0).toUpperCase() + step.status.slice(1)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-600 dark:text-gray-400">
              {progress.completedSteps} of {progress.totalSteps} steps completed
              {progress.failedSteps > 0 && (
                <span className="text-red-600 dark:text-red-400 ml-2">({progress.failedSteps} failed)</span>
              )}
            </div>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {progress.status === "completed" ? "Done" : progress.status === "failed" ? "Close" : "Cancel"}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
