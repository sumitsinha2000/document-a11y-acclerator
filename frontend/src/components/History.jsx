"use client"

import { useState, useEffect } from "react"
import { API_ENDPOINTS } from "../config/api"

export default function History({ onSelectScan, onSelectBatch, onBack }) {
  const [batches, setBatches] = useState([])
  const [scans, setScans] = useState([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState("all") // 'all', 'batches', 'individual'
  const [error, setError] = useState(null)
  const [deletingBatch, setDeletingBatch] = useState(null)
  const [deletingScan, setDeletingScan] = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    fetchHistory()
  }, [])

  const fetchHistory = async () => {
    try {
      setRefreshing(true)
      console.log("[v0] Fetching history from /api/history")
      const response = await fetch(API_ENDPOINTS.history)

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      console.log("[v0] History data received:", data)

      setBatches(data.batches || [])
      setScans(data.scans || [])
      setError(null)
    } catch (error) {
      console.error("[v0] Error fetching history:", error)
      setError(error.message)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  const handleDeleteBatch = async (batchId, batchName, e) => {
    e.stopPropagation() // Prevent triggering the card click

    if (
      !confirm(
        `Are you sure you want to delete "${batchName}"? This will permanently delete all files and records in this batch.`,
      )
    ) {
      return
    }

    try {
      setDeletingBatch(batchId)
      console.log("[v0] Deleting batch:", batchId)

      const response = await fetch(`${API_ENDPOINTS.batchDetails(batchId)}`, {
        method: "DELETE",
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || "Failed to delete batch")
      }

      const result = await response.json()
      console.log("[v0] Batch deleted successfully:", result)

      // Refresh history
      await fetchHistory()

      alert(`Successfully deleted batch with ${result.deletedFiles} files`)
    } catch (error) {
      console.error("[v0] Error deleting batch:", error)
      alert(`Failed to delete batch: ${error.message}`)
    } finally {
      setDeletingBatch(null)
    }
  }

  const handleDeleteScan = async (scanId, filename, e) => {
    e.stopPropagation()

    if (!confirm(`Are you sure you want to delete "${filename}"? This action cannot be undone.`)) {
      return
    }

    try {
      setDeletingScan(scanId)
      console.log("[v0] Deleting scan:", scanId)

      const response = await fetch(`${API_ENDPOINTS.scan}/${scanId}`, {
        method: "DELETE",
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || "Failed to delete scan")
      }

      const result = await response.json()
      console.log("[v0] Scan deleted successfully:", result)

      await fetchHistory()

      alert(`Successfully deleted "${filename}"`)
    } catch (error) {
      console.error("[v0] Error deleting scan:", error)
      alert(`Failed to delete scan: ${error.message}`)
    } finally {
      setDeletingScan(null)
    }
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto p-6">
        <div className="mb-6">
          <div className="h-8 w-48 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mb-4"></div>
          <div className="flex items-center justify-between mb-4">
            <div className="h-10 w-64 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></div>
            <div className="h-10 w-32 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></div>
          </div>
          <div className="flex gap-2 mb-6">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 w-32 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></div>
            ))}
          </div>
        </div>

        <div className="mb-8">
          <div className="h-6 w-48 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mb-4"></div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 p-4"
              >
                <div className="h-6 w-3/4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mb-3"></div>
                <div className="h-4 w-1/2 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mb-2"></div>
                <div className="h-4 w-full bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></div>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <p className="text-red-600 dark:text-red-400 mb-4">Error loading history: {error}</p>
          <button onClick={fetchHistory} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto p-6">
      <div className="mb-6">
        <button
          onClick={onBack}
          className="mb-4 text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
        >
          ← Back to Upload
        </button>

        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Upload History</h1>

          <button
            onClick={fetchHistory}
            disabled={refreshing}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <svg
              className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        {/* View Toggle */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setView("all")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              view === "all"
                ? "bg-blue-600 text-white"
                : "bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700"
            }`}
          >
            All ({batches.length + scans.length})
          </button>
          <button
            onClick={() => setView("batches")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              view === "batches"
                ? "bg-blue-600 text-white"
                : "bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700"
            }`}
          >
            Batches ({batches.length})
          </button>
          <button
            onClick={() => setView("individual")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              view === "individual"
                ? "bg-blue-600 text-white"
                : "bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700"
            }`}
          >
            Individual ({scans.length})
          </button>
        </div>
      </div>

      {/* Batch Uploads */}
      {(view === "all" || view === "batches") && batches.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Batch Uploads</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {batches.map((batch) => (
              <div
                key={batch.batchId}
                className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 p-4 hover:shadow-lg transition-shadow cursor-pointer"
                onClick={() => onSelectBatch && onSelectBatch(batch.batchId)}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center min-w-0 gap-2">
                    <svg
                      className="w-5 h-5 text-blue-600 flex-shrink-0 dark:text-blue-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                      />
                    </svg>
                    <h3 className="font-semibold text-gray-900 dark:text-white">{batch.name || "Batch Upload"}</h3>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
                      {batch.fileCount} files
                    </span>
                    <button
                      onClick={(e) => handleDeleteBatch(batch.batchId, batch.name, e)}
                      disabled={deletingBatch === batch.batchId}
                      className="p-1.5 rounded-md text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Delete batch"
                    >
                      {deletingBatch === batch.batchId ? (
                        <div className="w-4 h-4 border-2 border-red-600 border-t-transparent rounded-full animate-spin"></div>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                          />
                        </svg>
                      )}
                    </button>
                  </div>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                  {new Date(batch.uploadDate).toLocaleDateString()} at {new Date(batch.uploadDate).toLocaleTimeString()}
                </p>
                <div className="flex items-center justify-between text-sm mb-2">
                  <span className="text-gray-600 dark:text-gray-400">Total Issues:</span>
                  <span className="font-semibold text-gray-900 dark:text-white">{batch.totalIssues}</span>
                </div>
                <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                  <span>Status: {batch.status}</span>
                  <button className="text-blue-600 dark:text-blue-400 hover:underline">View →</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Individual Scans */}
      {(view === "all" || view === "individual") && scans.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Individual Uploads</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {scans.map((scan) => {
              const scanResults =
                typeof scan.scan_results === "string" ? JSON.parse(scan.scan_results) : scan.scan_results || {}

              const results = scanResults.results || scanResults
              const summary = scanResults.summary || {}

              // Calculate total issues from results if summary is missing or incorrect
              const totalIssues =
                summary.totalIssues ||
                Object.values(results).reduce((sum, issues) => {
                  return sum + (Array.isArray(issues) ? issues.length : 0)
                }, 0)

              const displayStatus =
                scan.status === "fixed" ? "fixed" : scan.status === "completed" ? "completed" : scan.status

              return (
                <div
                  key={scan.id}
                  className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 p-4 hover:shadow-lg transition-shadow cursor-pointer"
                  onClick={() => onSelectScan(scan)}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <svg
                        className="w-5 h-5 flex-shrink-0 text-red-600 dark:text-red-400"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
                        />
                      </svg>
                      <h3 className="font-semibold text-gray-900 dark:text-white" title={scan.filename}>
                        {scan.filename}
                      </h3>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-1 rounded-full text-xs font-medium ${
                          displayStatus === "fixed"
                            ? "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400"
                            : displayStatus === "completed"
                              ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                              : "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400"
                        }`}
                      >
                        {displayStatus}
                      </span>
                      <button
                        onClick={(e) => handleDeleteScan(scan.id, scan.filename, e)}
                        disabled={deletingScan === scan.id}
                        className="p-1.5 rounded-md text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Delete scan"
                      >
                        {deletingScan === scan.id ? (
                          <div className="w-4 h-4 border-2 border-red-600 border-t-transparent rounded-full animate-spin"></div>
                        ) : (
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                            />
                          </svg>
                        )}
                      </button>
                    </div>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                    {new Date(scan.uploadDate).toLocaleDateString()} at {new Date(scan.uploadDate).toLocaleTimeString()}
                  </p>
                  <div className="flex items-center justify-between text-sm mb-2">
                    <span className="text-gray-600 dark:text-gray-400">Issues:</span>
                    <span className="font-semibold text-gray-900 dark:text-white">{totalIssues}</span>
                  </div>
                  <div className="flex items-center justify-end text-xs">
                    <button className="text-blue-600 dark:text-blue-400 hover:underline">View →</button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {batches.length === 0 && scans.length === 0 && (
        <div className="text-center py-12">
          <svg
            className="w-16 h-16 mx-auto text-gray-400 dark:text-gray-600 mb-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <p className="text-gray-600 dark:text-gray-400">No scans yet. Upload a PDF to get started!</p>
        </div>
      )}
    </div>
  )
}
