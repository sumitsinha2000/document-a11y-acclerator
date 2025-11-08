"use client"

import { useState, useEffect, useRef, useId } from "react"
import axios from "axios"
import ReportViewer from "./ReportViewer"
import { ChevronDown, ChevronRight, AlertCircle, AlertTriangle, Info } from "lucide-react"
import { useNotification } from "../contexts/NotificationContext"
import API_BASE_URL from "../config/api"

export default function BatchReportViewer({ batchId, scans, onBack, onBatchUpdate }) {
  const [fixing, setFixing] = useState(false)
  const [fixResults, setFixResults] = useState(null)
  const [exporting, setExporting] = useState(false)
  const [selectedScan, setSelectedScan] = useState(null)
  const [searchTerm, setSearchTerm] = useState("")
  const [sortField, setSortField] = useState("filename")
  const [sortDirection, setSortDirection] = useState("asc")
  const [filterSeverity, setFilterSeverity] = useState("all")
  const [currentPage, setCurrentPage] = useState(1)
  const [fixingIndividual, setFixingIndividual] = useState({})
  const [startingScan, setStartingScan] = useState({})
  const [expandedCategories, setExpandedCategories] = useState({})
  const [itemsPerPage, setItemsPerPage] = useState(10)
  const [batchData, setBatchData] = useState(null)
  const [scansState, setScansState] = useState(scans || [])
  const { showSuccess, showError, showWarning, showInfo, confirm } = useNotification()
  const fetchedScanIdsRef = useRef(new Set())
  const searchInputId = useId()
  const itemsPerPageId = useId()

  useEffect(() => {
    const fetchBatchData = async () => {
      try {
        console.log("[v0] Fetching batch details:", batchId)
        const response = await axios.get(`${API_BASE_URL}/api/batch/${batchId}`)
        setBatchData(response.data)
        setScansState(response.data.scans || [])
        console.log("[v0] Batch data loaded:", response.data)
      } catch (error) {
        console.error("[v0] Error fetching batch data:", error)
        showError(`Failed to load batch details: ${error.message}`)
      }
    }

    if (batchId && (!scans || scans.length === 0)) {
      fetchBatchData()
    } else if (scans && scans.length > 0) {
      setScansState(scans)
    }
  }, [batchId, scans])

  useEffect(() => {
    if (scans && scans.length > 0) {
      setScansState(scans)
    }
  }, [scans])

  useEffect(() => {
    if (!Array.isArray(scansState) || scansState.length === 0) return

    const missingDetails = scansState.filter((scan) => {
      const scanId = scan.scanId || scan.id
      if (!scanId) return false
      if (fetchedScanIdsRef.current.has(scanId)) return false
      if (scan.status === "uploaded") return false
      const issues = scan.results || {}
      return !issues || Object.keys(issues).length === 0
    })

    if (missingDetails.length === 0) {
      return
    }

    let cancelled = false
    const fetchDetails = async () => {
      try {
        const responses = await Promise.all(
          missingDetails.map((scan) => {
            const scanId = scan.scanId || scan.id
            return axios.get(`${API_BASE_URL}/api/scan/${scanId}`)
          }),
        )

        if (cancelled) return

        const enrichedById = responses.reduce((acc, response, index) => {
          const data = response?.data
          const original = missingDetails[index]
          const scanId = original.scanId || original.id
          if (scanId && data?.results && Object.keys(data.results).length > 0) {
            acc[scanId] = {
              ...original,
              ...data,
              results: data.results,
              summary: data.summary || original.summary,
            }
          }
          return acc
        }, {})

        if (Object.keys(enrichedById).length === 0) {
          return
        }

        setScansState((prev) =>
          prev.map((scan) => {
            const scanId = scan.scanId || scan.id
            if (scanId && enrichedById[scanId]) {
              return {
                ...scan,
                ...enrichedById[scanId],
              }
            }
            return scan
          }),
        )
      } catch (error) {
        console.error("[v0] Error enriching scan data with full results:", error)
      }
    }

    missingDetails.forEach((scan) => {
      const scanId = scan.scanId || scan.id
      if (scanId) {
        fetchedScanIdsRef.current.add(scanId)
      }
    })

    fetchDetails()

    return () => {
      cancelled = true
    }
  }, [scansState])

  const aggregateIssuesByCategory = () => {
    const categories = {
      missingMetadata: { label: "Missing Metadata", severity: "high", issues: [], icon: AlertCircle },
      missingLanguage: { label: "Missing Language", severity: "high", issues: [], icon: AlertCircle },
      missingAltText: { label: "Missing Alt Text", severity: "high", issues: [], icon: AlertCircle },
      untaggedContent: { label: "Untagged Content", severity: "medium", issues: [], icon: AlertTriangle },
      poorContrast: { label: "Poor Contrast", severity: "medium", issues: [], icon: AlertTriangle },
      tableIssues: { label: "Table Issues", severity: "medium", issues: [], icon: AlertTriangle },
      formIssues: { label: "Form Issues", severity: "medium", issues: [], icon: AlertTriangle },
      structureIssues: { label: "Structure Issues", severity: "low", issues: [], icon: Info },
      readingOrderIssues: { label: "Reading Order Issues", severity: "low", issues: [], icon: Info },
    }

    scansState.forEach((scan) => {
      const results = scan.results || {}
      Object.keys(categories).forEach((key) => {
        if (results[key] && Array.isArray(results[key])) {
          categories[key].issues.push(
            ...results[key].map((issue) => ({
              ...issue,
              filename: scan.filename,
              scanId: scan.scanId,
            })),
          )
        }
      })
    })

    return categories
  }

  const toggleCategory = (categoryKey) => {
    setExpandedCategories((prev) => ({
      ...prev,
      [categoryKey]: !prev[categoryKey],
    }))
  }

  const handleFixIndividual = async (scanId, filename) => {
    console.log("[v0] handleFixIndividual called:", { scanId, filename, batchId })

    const confirmed = await confirm({
      title: "Apply Automated Fixes",
      message: `Are you sure you want to apply automated fixes to ${filename}?`,
      confirmText: "Apply Fixes",
      cancelText: "Cancel",
      type: "info",
    })

    if (!confirmed) {
      return
    }

    try {
      setFixingIndividual((prev) => ({ ...prev, [scanId]: true }))
      console.log("[v0] Calling API:", `${API_BASE_URL}/api/batch/${batchId}/fix-file/${scanId}`)

      const response = await axios.post(`${API_BASE_URL}/api/batch/${batchId}/fix-file/${scanId}`)
      console.log("[v0] Fix response:", response.data)

      if (response.data.success) {
        showSuccess(`Successfully applied ${response.data.successCount} fixes to ${filename}`)
        if (onBatchUpdate) {
          await onBatchUpdate(batchId)
        }
      } else {
        showError(`Failed to fix ${filename}: ${response.data.error || "Unknown error"}`)
      }
    } catch (error) {
      console.error("[v0] Error fixing file:", error)
      showError(`Failed to fix file: ${error.response?.data?.error || error.message}`)
    } finally {
      setFixingIndividual((prev) => ({ ...prev, [scanId]: false }))
    }
  }

  const handleStartDeferredScan = async (scanId, filename) => {
    if (!scanId) {
      return
    }

    try {
      setStartingScan((prev) => ({ ...prev, [scanId]: true }))
      const response = await axios.post(`${API_BASE_URL}/api/scan/${scanId}/start`)
      const data = response.data
      showSuccess(`Started scan for ${filename}`)

      setScansState((prev) =>
        prev.map((scan) => {
          const currentId = scan.scanId || scan.id
          if (currentId === scanId) {
            return {
              ...scan,
              ...data,
              scanId: currentId,
              status: data.status || "unprocessed",
              summary: data.summary || scan.summary || {},
              results: data.results || scan.results || {},
              verapdfStatus: data.verapdfStatus || scan.verapdfStatus,
              fixes: data.fixes || scan.fixes || [],
            }
          }
          return scan
        }),
      )

      if (onBatchUpdate) {
        await onBatchUpdate(batchId)
      }
    } catch (error) {
      console.error("[v0] Error starting deferred scan:", error)
      const message = error.response?.data?.error || error.message || "Failed to start scan"
      showError(message)
    } finally {
      setStartingScan((prev) => {
        const next = { ...prev }
        delete next[scanId]
        return next
      })
    }
  }

  const handleFixAll = async () => {
    console.log("[v0] handleFixAll called:", { batchId, scanCount: scansState.length })

    const confirmed = await confirm({
      title: "Apply Automated Fixes",
      message: `Apply automated fixes to all ${scansState.length} files in this batch?`,
      confirmText: "Apply Automated Fixes",
      cancelText: "Cancel",
      type: "warning",
    })

    if (!confirmed) {
      return
    }

    try {
      setFixing(true)
      console.log("[v0] Calling API:", `${API_BASE_URL}/api/batch/${batchId}/fix-all`)

      const response = await axios.post(`${API_BASE_URL}/api/batch/${batchId}/fix-all`)
      console.log("[v0] Fix all response:", response.data)

      setFixResults(response.data)
      showSuccess(`Successfully fixed ${response.data.successCount} out of ${response.data.totalFiles} files`, 6000)

      if (onBatchUpdate) {
        await onBatchUpdate(batchId)
      }
    } catch (error) {
      console.error("[v0] Error fixing batch:", error)
      showError(`Failed to fix batch: ${error.response?.data?.error || error.message}`)
    } finally {
      setFixing(false)
    }
  }

  const handleExportBatch = async () => {
    try {
      setExporting(true)
      const response = await axios.get(`${API_BASE_URL}/api/batch/${batchId}/export`, {
        responseType: "blob",
      })

      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement("a")
      link.href = url
      link.setAttribute("download", `${batchId}.zip`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)

      showSuccess("Batch exported successfully")
    } catch (error) {
      console.error("Error exporting batch:", error)
      const errorMessage = error.response?.data?.message || error.response?.data?.error || error.message
      showError(`Failed to export batch: ${errorMessage}`)
    } finally {
      setExporting(false)
    }
  }

  const handleViewDetails = async (scan) => {
    const scanId = scan.scanId || scan.id
    console.log("[v0] handleViewDetails called:", { scanId, filename: scan.filename })

    if (!scanId) {
      console.error("[v0] No scan ID found:", scan)
      showError("Error: Scan ID is missing")
      return
    }

    try {
      console.log("[v0] Calling API:", `${API_BASE_URL}/api/scan/${scanId}`)
      const response = await axios.get(`${API_BASE_URL}/api/scan/${scanId}`)
      console.log("[v0] Scan details loaded:", response.data)
      setSelectedScan(response.data)
    } catch (error) {
      console.error("[v0] Error loading scan details:", error)
      showError(`Failed to load details: ${error.response?.data?.error || error.message}`)
    }
  }

  const filteredAndSortedScans = scansState
    .filter((scan) => {
      const matchesSearch = scan.filename.toLowerCase().includes(searchTerm.toLowerCase())
      const summary = scan.summary || {}

      if (filterSeverity === "all") return matchesSearch
      if (filterSeverity === "high") return matchesSearch && (summary.highSeverity || 0) > 0
      if (filterSeverity === "medium") return matchesSearch && (summary.mediumSeverity || 0) > 0
      if (filterSeverity === "low") return matchesSearch && (summary.lowSeverity || 0) > 0

      return matchesSearch
    })
    .sort((a, b) => {
      const aVal = a.summary?.[sortField] || a[sortField] || 0
      const bVal = b.summary?.[sortField] || b[sortField] || 0

      if (sortField === "filename") {
        return sortDirection === "asc" ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal)
      }

      return sortDirection === "asc" ? aVal - bVal : bVal - aVal
    })

  const totalPages = Math.ceil(filteredAndSortedScans.length / itemsPerPage)
  const paginatedScans = filteredAndSortedScans.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage)

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc")
    } else {
      setSortField(field)
      setSortDirection("asc")
    }
  }

  const totalIssues = scansState.reduce((sum, scan) => {
    const summary = scan.summary || {}
    return sum + (summary.totalIssues || 0)
  }, 0)

  const avgCompliance =
    scansState.length > 0
      ? Math.round(
          scansState.reduce((sum, scan) => {
            const summary = scan.summary || {}
            return sum + (summary.complianceScore || 0)
          }, 0) / scansState.length,
        )
      : 0

  const highSeverity = scansState.reduce((sum, scan) => {
    const summary = scan.summary || {}
    return sum + (summary.highSeverity || 0)
  }, 0)

  const issueCategories = aggregateIssuesByCategory()

  if (!scansState || scansState.length === 0) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <p className="text-slate-600 dark:text-slate-400 text-lg">Loading batch data...</p>
        </div>
      </div>
    )
  }

  if (selectedScan) {
    return (
      <div className="flex min-h-[calc(100vh-3.5rem)] bg-slate-50 dark:bg-slate-900">
        <div className="flex w-64 flex-col bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <button
              onClick={() => setSelectedScan(null)}
              className="text-base font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 flex items-center gap-2 mb-3 transition-colors"
            >
              ← Back to Batch
            </button>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Batch Files</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{scansState.length} files</p>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {scansState.map((scan) => (
              <button
                key={scan.scanId}
                onClick={() => handleViewDetails(scan)}
                className={`w-full text-left px-3 py-2 rounded-md text-sm mb-1 transition-colors ${
                  selectedScan.scanId === scan.scanId
                    ? "bg-indigo-100 dark:bg-indigo-900/30 text-indigo-900 dark:text-indigo-100"
                    : "hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
                }`}
              >
                <div className="font-semibold truncate text-base">{scan.filename}</div>
                {scan.scanId && (
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate" title={scan.scanId}>
                    {scan.scanId}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1">
          <ReportViewer scans={[selectedScan]} onBack={() => setSelectedScan(null)} sidebarOpen={false} />
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 ">
      <div className="bg-white dark:bg-slate-800 border-b-2 border-slate-200 dark:border-slate-700 rounded-xl py-8 px-8">
        <div className="flex items-center justify-between">
          <div>
            <button
              onClick={onBack}
              className="mb-4 text-base text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 flex items-center gap-2 font-semibold transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Back to Upload
            </button>
            {scansState[0]?.groupName && (
              <div className="flex items-center gap-2 mb-3">
                <svg
                  className="w-6 h-6 text-indigo-600 dark:text-indigo-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                  />
                </svg>
                <span className="text-indigo-700 dark:text-indigo-300 font-bold text-xl tracking-wide">
                  {scansState[0].groupName}
                </span>
              </div>
            )}
            <h1 className="text-3xl font-bold text-slate-900 dark:text-white mb-3 tracking-tight">
              {batchData?.batchName || "Batch Report"}
            </h1>
            <p className="text-base text-slate-600 dark:text-slate-300 font-medium">
              {scansState.length} files uploaded
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={async () => {
                if (onBatchUpdate) {
                  await onBatchUpdate(batchId)
                }
              }}
              className="px-6 py-3.5 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-900 dark:text-white rounded-lg transition-colors flex items-center gap-2 font-semibold text-base shadow-sm border border-slate-200 dark:border-slate-600"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              Refresh
            </button>
            <button
              onClick={handleFixAll}
              disabled={fixing}
              className="px-6 py-3.5 bg-indigo-700 hover:bg-indigo-800 focus-visible:bg-indigo-800 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 font-semibold text-base shadow-lg transition-colors"
              aria-label={`Apply automated fixes to all ${scansState.length} files in this batch`}
              aria-busy={fixing}
            >
              {fixing ? (
                <>
                  <div
                    className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"
                    role="status"
                    aria-label="Applying automated fixes"
                  ></div>
                  Applying...
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Apply Automated Fixes
                </>
              )}
            </button>
            <button
              onClick={handleExportBatch}
              disabled={exporting}
              className="px-6 py-3.5 bg-emerald-700 hover:bg-emerald-800 focus-visible:bg-emerald-800 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 font-semibold text-base shadow-lg transition-colors"
            >
              {exporting ? (
                <>
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  Exporting...
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                  Export as ZIP
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[4fr_320px] gap-4 py-8 px-0">
        {/* Left Column - Main Content */}
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-7 border border-gray-200 dark:border-gray-700">
              <div className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-3">
                Avg Compliance
              </div>
              <div className="text-4xl font-bold text-slate-900 dark:text-white">{avgCompliance}%</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-7 border border-gray-200 dark:border-gray-700">
              <div className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-3">
                Total Issues
              </div>
              <div className="text-4xl font-bold text-slate-900 dark:text-white">{totalIssues}</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-7 border border-gray-200 dark:border-gray-700">
              <div className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-3">
                High Severity
              </div>
              <div className="text-4xl font-bold text-red-600 dark:text-red-400">{highSeverity}</div>
            </div>
          </div>

          {/* Fix Results */}
          {fixResults && (
            <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-xl p-6">
              <h3 className="text-xl font-bold text-emerald-900 dark:text-emerald-100 mb-2">Fix Results</h3>
              <p className="text-base text-emerald-800 dark:text-emerald-200">
                Successfully fixed {fixResults.successCount} out of {fixResults.totalFiles} files
              </p>
            </div>
          )}

          {/* Table Controls */}
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <label
                htmlFor={itemsPerPageId}
                className="text-base font-semibold text-gray-700 dark:text-gray-300"
              >
                Show
              </label>
              <select
                id={itemsPerPageId}
                name="itemsPerPage"
                value={itemsPerPage}
                onChange={(e) => {
                  setItemsPerPage(Number(e.target.value))
                  setCurrentPage(1)
                }}
                autoComplete="off"
                className="px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-base font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
              </select>
              <span className="text-base font-semibold text-gray-700 dark:text-gray-300">entries</span>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex flex-col">
                <label
                  htmlFor={searchInputId}
                  className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1"
                >
                  Search files
                </label>
                <div className="relative">
                  <input
                    id={searchInputId}
                    type="text"
                    value={searchTerm}
                    onChange={(e) => {
                      setSearchTerm(e.target.value)
                      setCurrentPage(1)
                    }}
                    placeholder="Search files"
                    autoComplete="off"
                    className="pl-11 pr-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-300 text-base focus:outline-none focus:ring-2 focus:ring-indigo-500 w-64"
                  />
                  <svg
                    className="pointer-events-none absolute left-3 top-3.5 w-5 h-5 text-gray-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                    />
                  </svg>
                </div>
              </div>

              <button
                onClick={handleExportBatch}
                disabled={exporting}
                className="px-6 py-3 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 text-base font-semibold flex items-center gap-2 shadow-sm"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
          </div>

          {/* Files Table */}
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 dark:bg-gray-700/50">
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="px-7 py-5">
                      <div className="flex items-center gap-2">
                        <input type="checkbox" className="w-4 h-4 rounded border-gray-300" />
                        <button
                          onClick={() => handleSort("filename")}
                          className="flex items-center gap-1 text-sm font-bold text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white uppercase tracking-wider"
                        >
                          Filename
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"
                            />
                          </svg>
                        </button>
                      </div>
                    </th>
                    <th className="px-7 py-5 text-left">
                      <button
                        onClick={() => handleSort("complianceScore")}
                        className="flex items-center gap-1 text-sm font-bold text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white uppercase tracking-wider"
                      >
                        Compliance
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"
                          />
                        </svg>
                      </button>
                    </th>
                    <th className="px-7 py-5 text-left">
                      <button
                        onClick={() => handleSort("totalIssues")}
                        className="flex items-center gap-1 text-sm font-bold text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white uppercase tracking-wider"
                      >
                        Total Issues
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"
                          />
                        </svg>
                      </button>
                    </th>
                    <th className="px-7 py-5 text-left">
                      <button
                        onClick={() => handleSort("highSeverity")}
                        className="flex items-center gap-1 text-sm font-bold text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white uppercase tracking-wider"
                      >
                        High Severity
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"
                          />
                        </svg>
                      </button>
                    </th>
                    <th className="px-7 py-5 text-left text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-7 py-5 text-left text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {paginatedScans.map((scan, idx) => {
                    const summary = scan.summary || {
                      complianceScore: 0,
                      totalIssues: 0,
                      highSeverity: 0,
                    }
                    const fixResult = fixResults?.results?.find((r) => r.scanId === (scan.scanId || scan.id))
                    const statusValue = (scan.status || "").toLowerCase()
                    const isUploaded = statusValue === "uploaded"
                    const complianceScore =
                      typeof summary.complianceScore === "number" ? summary.complianceScore : 0
                    const totalIssues =
                      typeof summary.totalIssues === "number" ? summary.totalIssues : 0
                    const highSeverity =
                      typeof summary.highSeverity === "number" ? summary.highSeverity : 0
                    const scanKey = scan.scanId || scan.id

                    return (
                      <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                        <td className="px-7 py-5">
                          <div className="flex items-center gap-3">
                            <input type="checkbox" className="w-4 h-4 rounded border-gray-300" />
                            <div>
                              <div className="text-base font-semibold text-gray-900 dark:text-white">
                                {scan.filename}
                              </div>
                              <div className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                                {(scan.scanId || scan.id)?.slice(0, 30)}...
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="px-7 py-5">
                          {isUploaded ? (
                            <span className="text-sm italic text-gray-500 dark:text-gray-400">—</span>
                          ) : (
                            <span className="text-base font-semibold text-gray-900 dark:text-white">
                              {complianceScore}%
                            </span>
                          )}
                        </td>
                        <td className="px-7 py-5">
                          {isUploaded ? (
                            <span className="text-sm italic text-gray-500 dark:text-gray-400">—</span>
                          ) : (
                            <span className="text-base font-medium text-gray-900 dark:text-white">
                              {totalIssues}
                            </span>
                          )}
                        </td>
                        <td className="px-7 py-5">
                          {isUploaded ? (
                            <span className="text-sm italic text-gray-500 dark:text-gray-400">—</span>
                          ) : (
                            <span className="text-base text-red-600 dark:text-red-400 font-bold">{highSeverity}</span>
                          )}
                        </td>
                        <td className="px-7 py-5">
                          {isUploaded ? (
                            <span className="inline-flex items-center px-3.5 py-2 rounded-full text-sm font-semibold bg-slate-100 text-slate-800 dark:bg-slate-800/60 dark:text-slate-200">
                              Not Scanned
                            </span>
                          ) : fixResult ? (
                            fixResult.success ? (
                              <span className="inline-flex items-center px-3.5 py-2 rounded-full text-sm font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400">
                                Fixed
                              </span>
                            ) : (
                              <span className="inline-flex items-center px-3.5 py-2 rounded-full text-sm font-semibold bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400">
                                Failed
                              </span>
                            )
                          ) : (
                            <span className="inline-flex items-center px-3.5 py-2 rounded-full text-sm font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">
                              Pending
                            </span>
                          )}
                        </td>
                        <td className="px-7 py-5">
                          <div className="flex flex-wrap items-center gap-2">
                            <button
                              onClick={() => handleViewDetails(scan)}
                              disabled={isUploaded}
                              className={`px-5 py-2.5 text-base font-semibold rounded-lg transition-colors ${
                                isUploaded
                                  ? "text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-800 cursor-not-allowed"
                                  : "text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/20"
                              }`}
                              title="View Details"
                            >
                              View Details
                            </button>
                            {isUploaded ? (
                              <button
                                onClick={() => handleStartDeferredScan(scanKey, scan.filename)}
                                disabled={startingScan[scanKey]}
                                className="px-5 py-2.5 text-base font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                title="Begin Scan"
                              >
                                {startingScan[scanKey] ? "Starting..." : "Begin Scan"}
                              </button>
                            ) : (
                              <button
                                onClick={() => handleFixIndividual(scanKey, scan.filename)}
                                disabled={fixingIndividual[scanKey]}
                                className="px-5 py-2.5 text-base font-semibold text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                title="Fix Issues"
                              >
                                {fixingIndividual[scanKey] ? "Fixing..." : "Fix Issues"}
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="px-7 py-5 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between bg-gray-50 dark:bg-gray-700/50">
                <div className="text-base font-medium text-gray-700 dark:text-gray-300">
                  Showing {(currentPage - 1) * itemsPerPage + 1} to{" "}
                  {Math.min(currentPage * itemsPerPage, filteredAndSortedScans.length)} of{" "}
                  {filteredAndSortedScans.length} entries
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="px-6 py-3 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed text-base font-semibold text-gray-700 dark:text-gray-300"
                  >
                    Previous
                  </button>
                  <span className="px-6 py-3 text-base font-medium text-gray-700 dark:text-gray-300">
                    Page {currentPage} of {totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="px-6 py-3 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed text-base font-semibold text-gray-700 dark:text-gray-300"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="h-fit">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden  h-full">
            {/* Header */}
            <div className="px-6 py-5 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">Issues Overview</h2>
                <span className="px-3.5 py-1.5 rounded-full text-base font-bold bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400">
                  {totalIssues} total
                </span>
              </div>
              <p className="text-base text-gray-600 dark:text-gray-400 mt-1.5">Across all {scansState.length} files</p>
            </div>

            {/* Issue Categories */}
            <div className="divide-y divide-gray-100 dark:divide-gray-700/50 max-h-[calc(100vh-12rem)] h-full overflow-y-auto">
              {Object.entries(issueCategories).map(([key, category]) => {
                if (category.issues.length === 0) return null

                const isExpanded = expandedCategories[key]
                const Icon = category.icon

                // Severity styling
                const severityStyles = {
                  high: {
                    badge: "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400",
                    icon: "text-red-500 dark:text-red-400",
                    border: "border-red-100 dark:border-red-900/30",
                  },
                  medium: {
                    badge: "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
                    icon: "text-amber-500 dark:text-amber-400",
                    border: "border-amber-100 dark:border-amber-900/30",
                  },
                  low: {
                    badge: "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400",
                    icon: "text-blue-500 dark:text-blue-400",
                    border: "border-blue-100 dark:border-blue-900/30",
                  },
                }

                const styles = severityStyles[category.severity]

                return (
                  <div key={key} className="bg-white dark:bg-gray-800">
                    {/* Category Header */}
                    <button
                      onClick={() => toggleCategory(key)}
                      className="w-full px-6 py-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-all duration-200 group"
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={`p-1.5 rounded-lg ${styles.badge} transition-transform duration-200 ${isExpanded ? "rotate-0" : ""}`}
                        >
                          {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                        </div>
                        <Icon className={`w-5 h-5 ${styles.icon}`} />
                        <div className="text-left">
                          <h3 className="font-semibold text-gray-900 dark:text-white text-base">{category.label}</h3>
                          <p className="text-sm text-gray-500 dark:text-gray-400 capitalize mt-0.5">
                            {category.severity} severity
                          </p>
                        </div>
                      </div>
                      <span className={`px-3.5 py-1.5 rounded-full text-base font-bold ${styles.badge}`}>
                        {category.issues.length}
                      </span>
                    </button>

                    {/* Expanded Issues */}
                    {isExpanded && (
                      <div className="px-6 pb-4 space-y-2 bg-gray-50 dark:bg-gray-900/30">
                        {category.issues.slice(0, 10).map((issue, idx) => (
                          <div
                            key={idx}
                            className={`bg-white dark:bg-gray-800 p-4 rounded-lg border ${styles.border} shadow-sm hover:shadow-md transition-shadow duration-200`}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-2">
                                  <span className="font-semibold text-gray-900 dark:text-white text-base truncate">
                                    {issue.filename}
                                  </span>
                                  {issue.page && (
                                    <span className="flex-shrink-0 text-sm px-2.5 py-1 rounded-md bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 font-semibold">
                                      Page {issue.page}
                                    </span>
                                  )}
                                </div>
                                {issue.description && (
                                  <p className="text-base text-gray-600 dark:text-gray-400 leading-relaxed">
                                    {issue.description}
                                  </p>
                                )}
                              </div>
                              <button
                                onClick={() => {
                                  const scan = scansState.find((s) => s.scanId === issue.scanId)
                                  if (scan) handleViewDetails(scan)
                                }}
                                className="flex-shrink-0 text-base text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 font-semibold hover:underline transition-colors"
                              >
                                View
                              </button>
                            </div>
                          </div>
                        ))}
                        {category.issues.length > 10 && (
                          <div className="text-center pt-2">
                            <p className="text-base text-gray-600 dark:text-gray-400 font-medium">
                              + {category.issues.length - 10} more issues
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}

              {/* Empty State */}
              {Object.values(issueCategories).every((cat) => cat.issues.length === 0) && (
                <div className="px-6 py-12 text-center">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-900/20 mb-4">
                    <svg
                      className="w-8 h-8 text-emerald-600 dark:text-emerald-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">No Issues Found</h3>
                  <p className="text-base text-gray-600 dark:text-gray-400">
                    All files are fully compliant with accessibility standards.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
