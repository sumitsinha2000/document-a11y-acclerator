"use client"

import { useState, useEffect } from "react"
import { API_ENDPOINTS } from "../config/api"

export default function History({ onSelectScan, onSelectBatch, onBack }) {
  const [batches, setBatches] = useState([])
  const [scans, setScans] = useState([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState("all") // 'all', 'batches', 'individual'
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchHistory()
  }, [])

  const fetchHistory = async () => {
    try {
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
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-lg text-gray-600 dark:text-gray-400">Loading history...</div>
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
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">Upload History</h1>

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
                  <div className="flex items-center gap-2">
                    <svg
                      className="w-5 h-5 text-blue-600 dark:text-blue-400"
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
                  <span className="px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
                    {batch.fileCount} files
                  </span>
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
            {scans.map((scan) => (
              <div
                key={scan.id}
                className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 p-4 hover:shadow-lg transition-shadow cursor-pointer"
                onClick={() => onSelectScan(scan)}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <svg
                      className="w-5 h-5 text-red-600 dark:text-red-400"
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
                    <h3 className="font-semibold text-gray-900 dark:text-white truncate">{scan.filename}</h3>
                  </div>
                  <span className="px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                    {scan.status}
                  </span>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                  {new Date(scan.uploadDate).toLocaleDateString()} at {new Date(scan.uploadDate).toLocaleTimeString()}
                </p>
                {scan.summary && (
                  <div className="flex items-center justify-between text-sm mb-2">
                    <span className="text-gray-600 dark:text-gray-400">Issues:</span>
                    <span className="font-semibold text-gray-900 dark:text-white">{scan.summary.totalIssues || 0}</span>
                  </div>
                )}
                <div className="flex items-center justify-end text-xs">
                  <button className="text-blue-600 dark:text-blue-400 hover:underline">View →</button>
                </div>
              </div>
            ))}
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
