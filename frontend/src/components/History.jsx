import { useState, useEffect } from "react"
import { API_ENDPOINTS } from "../config/api"
import { useNotification } from "../contexts/NotificationContext"
import { parseBackendDate } from "../utils/dates"

export default function History({ onSelectScan, onSelectBatch, onBack }) {
  const [batches, setBatches] = useState([])
  const [scans, setScans] = useState([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState("all") // 'all', 'batches', 'individual'
  const [error, setError] = useState(null)
  const [deletingBatch, setDeletingBatch] = useState(null)
  const [deletingScan, setDeletingScan] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [startingScan, setStartingScan] = useState(null)

  const { showSuccess, showError, confirm } = useNotification()

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
      console.log("[v0] Batches:", data.batches)
      console.log("[v0] Scans:", data.scans)

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
    e.stopPropagation()

    const confirmed = await confirm({
      title: "Delete Folder",
      message: `Delete folder "${batchName}" and permanently remove every file that was uploaded to this project as part of it? This cannot be undone.`,
      confirmText: "Delete",
      cancelText: "Cancel",
      type: "danger",
    })

    if (!confirmed) {
      return
    }

    try {
      setDeletingBatch(batchId)
      console.log("[v0] Deleting folder:", batchId)

      const response = await fetch(`${API_ENDPOINTS.batchDetails(batchId)}`, {
        method: "DELETE",
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || "Failed to delete folder")
      }

      const result = await response.json()
      console.log("[v0] Folder deleted successfully:", result)

      await fetchHistory()

      showSuccess(
        `Deleted folder${
          result.batchName ? ` "${result.batchName}"` : ""
        } with ${result.deletedScans ?? 0} scans (${result.deletedFiles ?? 0} files removed)`,
      )
    } catch (error) {
      console.error("[v0] Error deleting folder:", error)
      showError(`Failed to delete folder: ${error.message}`)
    } finally {
      setDeletingBatch(null)
    }
  }

  const handleDeleteScan = async (scanId, filename, e) => {
    e.stopPropagation()

    const confirmed = await confirm({
      title: "Delete File",
      message: `Delete "${filename}" and remove it from its project history? This permanently deletes the file and cannot be undone.`,
      confirmText: "Delete",
      cancelText: "Cancel",
      type: "danger",
    })

    if (!confirmed) {
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

      showSuccess(`Successfully deleted "${filename}"`)
    } catch (error) {
      console.error("[v0] Error deleting scan:", error)
      showError(`Failed to delete scan: ${error.message}`)
    } finally {
      setDeletingScan(null)
    }
  }

  const getStatusBadge = (status) => {
    const statusConfig = {
      compliant: {
        bg: "bg-green-100 dark:bg-green-900/30",
        text: "text-green-800 dark:text-green-400",
        label: "Compliant",
      },
      fixed: {
        bg: "bg-purple-100 dark:bg-purple-900/30",
        text: "text-purple-800 dark:text-purple-400",
        label: "Fixed",
      },
      processing: {
        bg: "bg-yellow-100 dark:bg-yellow-900/30",
        text: "text-yellow-800 dark:text-yellow-400",
        label: "Processing",
      },
      unprocessed: {
        bg: "bg-gray-100 dark:bg-gray-700",
        text: "text-gray-800 dark:text-gray-300",
        label: "Unprocessed",
      },
      uploaded: {
        bg: "bg-slate-100 dark:bg-slate-800/60",
        text: "text-slate-800 dark:text-slate-200",
        label: "Uploaded",
      },
      completed: {
        bg: "bg-blue-100 dark:bg-blue-900/30",
        text: "text-blue-800 dark:text-blue-400",
        label: "Scanned",
      },
    }

    const config = statusConfig[status] || statusConfig.unprocessed
    return (
      <span className={`px-2 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text}`}>{config.label}</span>
    )
  }

  const filteredBatches = batches.filter((batch) => {
    if (!searchQuery.trim()) return true
    const query = searchQuery.toLowerCase()
    return (
      (batch.name && batch.name.toLowerCase().includes(query)) ||
      (batch.groupName && batch.groupName.toLowerCase().includes(query)) ||
      (batch.batchId && batch.batchId.toLowerCase().includes(query))
    )
  })

  const filteredScans = scans.filter((scan) => {
    if (!searchQuery.trim()) return true
    const query = searchQuery.toLowerCase()
    return (
      (scan.filename && scan.filename.toLowerCase().includes(query)) ||
      (scan.groupName && scan.groupName.toLowerCase().includes(query))
    )
  })

  const handleStartDeferredScan = async (scanId, filename, e) => {
    if (e) {
      e.stopPropagation()
    }

    try {
      setStartingScan(scanId)
      const response = await fetch(API_ENDPOINTS.startScan(scanId), {
        method: "POST",
      })

      if (!response.ok) {
        let errorMessage = "Failed to start scan"
        try {
          const errorData = await response.json()
          errorMessage = errorData.error || errorMessage
        } catch (parseError) {
          console.warn("[v0] Unable to parse error response for start scan:", parseError)
        }
        throw new Error(errorMessage)
      }

      const data = await response.json()
      console.log("[v0] Deferred scan started:", data)
      showSuccess(`Started scanning "${filename}". Reloading history.`)
      await fetchHistory()
    } catch (error) {
      console.error("[v0] Error starting deferred scan:", error)
      showError(`Failed to start scan: ${error.message}`)
    } finally {
      setStartingScan(null)
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
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Upload History</h1>

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
              aria-hidden="true"
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
        <div className="flex gap-2 mb-4">
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
            Folders ({batches.length})
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

        <div className="relative">
          <label htmlFor="history-search" className="sr-only">
            Search scans and folders
          </label>
          <input
            type="text"
            id="history-search"
            autoComplete="on"
            placeholder="Search by filename, folder name, project, or ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-4 py-2 pl-10 pr-10 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <svg
            className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {(view === "all" || view === "batches") && filteredBatches.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Folder Uploads {searchQuery && `(${filteredBatches.length} of ${batches.length})`}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredBatches.map((batch) => {
              const batchDate = parseBackendDate(batch.uploadDate)
              return (
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
                        aria-hidden="true"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                        />
                      </svg>
                      <div className="min-w-0">
                        <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                          {batch.name || "Folder Upload"}
                        </h3>
                        {batch.groupName && (
                          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">Project: {batch.groupName}</p>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={(e) => handleDeleteBatch(batch.batchId, batch.name, e)}
                      disabled={deletingBatch === batch.batchId}
                      className="p-1.5 rounded-md text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                      title="Delete folder"
                    >
                      {deletingBatch === batch.batchId ? (
                        <div className="w-4 h-4 border-2 border-red-600 border-t-transparent rounded-full animate-spin"></div>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
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

                  {/* Batch ID */}
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-2 font-mono truncate">ID: {batch.batchId}</p>

                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                    {batchDate ? batchDate.toLocaleString() : "Date unavailable"}
                  </p>

                  {/* Status Badge */}
                  <div className="mb-3">{getStatusBadge(batch.status)}</div>

                  {/* Aggregate Statistics */}
                  <div className="space-y-2 mb-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600 dark:text-gray-400">Total Files:</span>
                      <span className="font-semibold text-gray-900 dark:text-white">{batch.fileCount || 0}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600 dark:text-gray-400">Unprocessed:</span>
                      <span className="font-semibold text-gray-900 dark:text-white">{batch.unprocessedFiles || 0}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600 dark:text-gray-400">Total Issues:</span>
                      <span className="font-semibold text-gray-900 dark:text-white">{batch.totalIssues || 0}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-green-600 dark:text-green-400">Fixed:</span>
                      <span className="font-semibold text-green-600 dark:text-green-400">{batch.fixedIssues || 0}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-orange-600 dark:text-orange-400">Remaining:</span>
                      <span className="font-semibold text-orange-600 dark:text-orange-400">{batch.remainingIssues || 0}</span>
                    </div>
                  </div>

                  <div className="flex items-center justify-end text-xs">
                    <button className="text-blue-600 dark:text-blue-400 hover:underline">View Details →</button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {(view === "all" || view === "individual") && filteredScans.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Individual Uploads {searchQuery && `(${filteredScans.length} of ${scans.length})`}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredScans.map((scan) => {
              const totalIssues = scan.totalIssues || 0
              const issuesFixed = scan.issuesFixed || 0
              const issuesRemaining = scan.issuesRemaining || totalIssues
              const isUploaded = scan.status === "uploaded"
              const scanDateValue = scan.uploadDate || scan.timestamp || scan.created_at
              const scanDate = parseBackendDate(scanDateValue)

              return (
                <div
                  key={scan.id}
                  className={`bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 p-4 transition-shadow ${
                    isUploaded ? "cursor-default" : "hover:shadow-lg cursor-pointer"
                  }`}
                  onClick={() => {
                    if (!isUploaded) {
                      onSelectScan(scan)
                    }
                  }}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <svg
                        className="w-5 h-5 flex-shrink-0 text-red-600 dark:text-red-400"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                        
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
                        />
                      </svg>
                      <div className="min-w-0">
                        <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                          {scan.filename}
                        </h3>
                        {scan.groupName && (
                          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">Project: {scan.groupName}</p>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={(e) => handleDeleteScan(scan.id, scan.filename, e)}
                      disabled={deletingScan === scan.id}
                      className="p-1.5 rounded-md text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                      title="Delete scan"
                    >
                      {deletingScan === scan.id ? (
                        <div className="w-4 h-4 border-2 border-red-600 border-t-transparent rounded-full animate-spin"></div>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
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

                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                    {scanDate ? scanDate.toLocaleString() : "Date unavailable"}
                  </p>

                  {/* Status Badge */}
                  <div className="mb-3">{getStatusBadge(scan.status)}</div>

                  {/* Issue Statistics */}
                  <div className="space-y-2 mb-3">
                    {isUploaded ? (
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        Scanning has not started yet. Begin the scan to see issue counts.
                      </p>
                    ) : (
                      <>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-600 dark:text-gray-400">Total Issues:</span>
                          <span className="font-semibold text-gray-900 dark:text-white">{totalIssues}</span>
                        </div>
                        {issuesFixed > 0 && (
                          <>
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-green-600 dark:text-green-400">Fixed:</span>
                              <span className="font-semibold text-green-600 dark:text-green-400">{issuesFixed}</span>
                            </div>
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-orange-600 dark:text-orange-400">Remaining:</span>
                              <span className="font-semibold text-orange-600 dark:text-orange-400">{issuesRemaining}</span>
                            </div>
                          </>
                        )}
                      </>
                    )}
                    {!isUploaded && issuesFixed === 0 && (
                      <>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-orange-600 dark:text-orange-400">Remaining:</span>
                          <span className="font-semibold text-orange-600 dark:text-orange-400">{issuesRemaining}</span>
                        </div>
                      </>
                    )}
                  </div>

                  <div className="flex items-center justify-end text-xs">
                    {isUploaded ? (
                      <button
                        onClick={(e) => handleStartDeferredScan(scan.id, scan.filename, e)}
                        disabled={startingScan === scan.id}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        {startingScan === scan.id ? (
                          <>
                            <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                            Starting...
                          </>
                        ) : (
                          <>
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M12 6v6l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                              />
                            </svg>
                            Begin Scan
                          </>
                        )}
                      </button>
                    ) : (
                      <button className="text-blue-600 dark:text-blue-400 hover:underline">View Details →</button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {batches.length === 0 && scans.length === 0 && !searchQuery && (
        <div className="text-center py-12">
          <svg
            className="w-16 h-16 mx-auto text-gray-400 dark:text-gray-600 mb-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
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

      {searchQuery &&
        filteredBatches.length === 0 &&
        filteredScans.length === 0 &&
        (batches.length > 0 || scans.length > 0) && (
          <div className="text-center py-12">
            <svg
              className="w-16 h-16 mx-auto text-gray-400 dark:text-gray-600 mb-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <p className="text-gray-600 dark:text-gray-400 mb-2">No results found for "{searchQuery}"</p>
            <button
              onClick={() => setSearchQuery("")}
              className="text-blue-600 dark:text-blue-400 hover:underline text-sm"
            >
              Clear search
            </button>
          </div>
        )}
    </div>
  )
}
