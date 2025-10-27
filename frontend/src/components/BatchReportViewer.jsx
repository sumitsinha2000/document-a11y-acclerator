"use client"

import { useState } from "react"
import axios from "axios"
import ReportViewer from "./ReportViewer"
import { ChevronDown, ChevronRight, AlertCircle, AlertTriangle, Info } from "lucide-react"

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
  const [expandedCategories, setExpandedCategories] = useState({})
  const [itemsPerPage, setItemsPerPage] = useState(10)

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

    scans.forEach((scan) => {
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

    if (!confirm(`Apply automated fixes to ${filename}?`)) {
      return
    }

    try {
      setFixingIndividual((prev) => ({ ...prev, [scanId]: true }))
      console.log("[v0] Calling API:", `/api/batch/${batchId}/fix-file/${scanId}`)

      const response = await axios.post(`/api/batch/${batchId}/fix-file/${scanId}`)
      console.log("[v0] Fix response:", response.data)

      if (response.data.success) {
        alert(`Successfully applied ${response.data.successCount} fixes to ${filename}`)
        if (onBatchUpdate) {
          await onBatchUpdate(batchId)
        }
      } else {
        alert(`Failed to fix ${filename}: ${response.data.error || "Unknown error"}`)
      }
    } catch (error) {
      console.error("[v0] Error fixing file:", error)
      alert("Failed to fix file: " + (error.response?.data?.error || error.message))
    } finally {
      setFixingIndividual((prev) => ({ ...prev, [scanId]: false }))
    }
  }

  const handleFixAll = async () => {
    console.log("[v0] handleFixAll called:", { batchId, scanCount: scans.length })

    if (!confirm(`Apply automated fixes to all ${scans.length} files in this batch?`)) {
      return
    }

    try {
      setFixing(true)
      console.log("[v0] Calling API:", `/api/batch/${batchId}/fix-all`)

      const response = await axios.post(`/api/batch/${batchId}/fix-all`)
      console.log("[v0] Fix all response:", response.data)

      setFixResults(response.data)
      alert(`Successfully fixed ${response.data.successCount} out of ${response.data.totalFiles} files`)

      if (onBatchUpdate) {
        await onBatchUpdate(batchId)
      }
    } catch (error) {
      console.error("[v0] Error fixing batch:", error)
      alert("Failed to fix batch: " + (error.response?.data?.error || error.message))
    } finally {
      setFixing(false)
    }
  }

  const handleExportBatch = async () => {
    try {
      setExporting(true)
      const response = await axios.get(`/api/batch/${batchId}/export`, {
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
    } catch (error) {
      console.error("Error exporting batch:", error)
      alert("Failed to export batch: " + (error.response?.data?.error || error.message))
    } finally {
      setExporting(false)
    }
  }

  const handleViewDetails = async (scan) => {
    console.log("[v0] handleViewDetails called:", { scanId: scan.scanId, filename: scan.filename })

    try {
      console.log("[v0] Calling API:", `/api/scan/${scan.scanId}`)
      const response = await axios.get(`/api/scan/${scan.scanId}`)
      console.log("[v0] Scan details loaded:", response.data)
      setSelectedScan(response.data)
    } catch (error) {
      console.error("[v0] Error loading scan details:", error)
      alert("Failed to load details: " + (error.response?.data?.error || error.message))
    }
  }

  const filteredAndSortedScans = scans
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

  const totalIssues = scans.reduce((sum, scan) => sum + (scan.summary?.totalIssues || 0), 0)
  const avgCompliance = Math.round(
    scans.reduce((sum, scan) => sum + (scan.summary?.complianceScore || 0), 0) / scans.length,
  )
  const highSeverity = scans.reduce((sum, scan) => sum + (scan.summary?.highSeverity || 0), 0)

  const issueCategories = aggregateIssuesByCategory()

  if (selectedScan) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)]">
        <div className="w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 overflow-y-auto">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <button
              onClick={() => setSelectedScan(null)}
              className="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 mb-2"
            >
              ← Back to Batch
            </button>
            <h2 className="font-semibold text-gray-900 dark:text-white">Batch Files</h2>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">{scans.length} files</p>
          </div>
          <div className="p-2">
            {scans.map((scan) => (
              <button
                key={scan.scanId}
                onClick={() => handleViewDetails(scan)}
                className={`w-full text-left px-3 py-2 rounded-md text-sm mb-1 transition-colors ${
                  selectedScan.scanId === scan.scanId
                    ? "bg-blue-100 dark:bg-blue-900/30 text-blue-900 dark:text-blue-100"
                    : "hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
                }`}
              >
                <div className="font-medium truncate">{scan.filename}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{scan.scanId?.slice(0, 30)}...</div>
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          <ReportViewer scans={[selectedScan]} onBack={() => setSelectedScan(null)} sidebarOpen={false} />
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header - Full Width */}
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <button
              onClick={onBack}
              className="mb-2 text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
            >
              ← Back to Upload
            </button>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Batch Report</h1>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{scans.length} files uploaded</p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleFixAll}
              disabled={fixing}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {fixing ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  Fixing...
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Fix All Issues
                </>
              )}
            </button>
            <button
              onClick={handleExportBatch}
              disabled={exporting}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {exporting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
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

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-6 p-6">
        {/* Left Column - Main Content */}
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Avg Compliance</div>
              <div className="text-3xl font-bold text-gray-900 dark:text-white mt-2">{avgCompliance}%</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Total Issues</div>
              <div className="text-3xl font-bold text-gray-900 dark:text-white mt-2">{totalIssues}</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400">High Severity</div>
              <div className="text-3xl font-bold text-red-600 dark:text-red-400 mt-2">{highSeverity}</div>
            </div>
          </div>

          {/* Fix Results */}
          {fixResults && (
            <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
              <h3 className="font-semibold text-green-900 dark:text-green-100 mb-2">Fix Results</h3>
              <p className="text-sm text-green-800 dark:text-green-200">
                Successfully fixed {fixResults.successCount} out of {fixResults.totalFiles} files
              </p>
            </div>
          )}

          {/* Table Controls */}
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-700 dark:text-gray-300">Show</span>
              <select
                value={itemsPerPage}
                onChange={(e) => {
                  setItemsPerPage(Number(e.target.value))
                  setCurrentPage(1)
                }}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
              </select>
              <span className="text-sm text-gray-700 dark:text-gray-300">entries</span>
            </div>

            <div className="flex items-center gap-3">
              <div className="relative">
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => {
                    setSearchTerm(e.target.value)
                    setCurrentPage(1)
                  }}
                  placeholder="Search..."
                  className="pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <svg
                  className="absolute left-3 top-2.5 w-4 h-4 text-gray-400"
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

              <button
                onClick={handleExportBatch}
                disabled={exporting}
                className="px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 text-sm font-medium flex items-center gap-2"
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
          </div>

          {/* Files Table */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 dark:bg-gray-700/50">
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="px-6 py-3 text-left">
                      <div className="flex items-center gap-2">
                        <input type="checkbox" className="w-4 h-4 rounded border-gray-300" />
                        <button
                          onClick={() => handleSort("filename")}
                          className="flex items-center gap-1 text-xs font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white uppercase tracking-wider"
                        >
                          Filename
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                    <th className="px-6 py-3 text-left">
                      <button
                        onClick={() => handleSort("complianceScore")}
                        className="flex items-center gap-1 text-xs font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white uppercase tracking-wider"
                      >
                        Compliance
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"
                          />
                        </svg>
                      </button>
                    </th>
                    <th className="px-6 py-3 text-left">
                      <button
                        onClick={() => handleSort("totalIssues")}
                        className="flex items-center gap-1 text-xs font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white uppercase tracking-wider"
                      >
                        Total Issues
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"
                          />
                        </svg>
                      </button>
                    </th>
                    <th className="px-6 py-3 text-left">
                      <button
                        onClick={() => handleSort("highSeverity")}
                        className="flex items-center gap-1 text-xs font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white uppercase tracking-wider"
                      >
                        High Severity
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"
                          />
                        </svg>
                      </button>
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {paginatedScans.map((scan, idx) => {
                    const summary = scan.summary || {}
                    const fixResult = fixResults?.results?.find((r) => r.scanId === scan.scanId)

                    return (
                      <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-3">
                            <input type="checkbox" className="w-4 h-4 rounded border-gray-300" />
                            <div>
                              <div className="text-sm font-medium text-gray-900 dark:text-white">{scan.filename}</div>
                              <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                {scan.scanId?.slice(0, 30)}...
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <span className="text-sm font-medium text-gray-900 dark:text-white">
                            {summary.complianceScore || 0}%
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <span className="text-sm text-gray-900 dark:text-white">{summary.totalIssues || 0}</span>
                        </td>
                        <td className="px-6 py-4">
                          <span className="text-sm text-red-600 dark:text-red-400 font-medium">
                            {summary.highSeverity || 0}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          {fixResult ? (
                            fixResult.success ? (
                              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                                Fixed
                              </span>
                            ) : (
                              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400">
                                Failed
                              </span>
                            )
                          ) : (
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                              Pending
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleViewDetails(scan)}
                              className="px-3 py-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-md transition-colors"
                              title="View Details"
                            >
                              View Details
                            </button>
                            <button
                              onClick={() => handleFixIndividual(scan.scanId, scan.filename)}
                              disabled={fixingIndividual[scan.scanId]}
                              className="px-3 py-1.5 text-xs font-medium text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/20 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                              title="Fix Issues"
                            >
                              {fixingIndividual[scan.scanId] ? "Fixing..." : "Fix Issues"}
                            </button>
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
              <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between bg-gray-50 dark:bg-gray-700/50">
                <div className="text-sm text-gray-700 dark:text-gray-300">
                  Showing {(currentPage - 1) * itemsPerPage + 1} to{" "}
                  {Math.min(currentPage * itemsPerPage, filteredAndSortedScans.length)} of{" "}
                  {filteredAndSortedScans.length} entries
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium text-gray-700 dark:text-gray-300"
                  >
                    Previous
                  </button>
                  <span className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300">
                    Page {currentPage} of {totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium text-gray-700 dark:text-gray-300"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="lg:sticky lg:top-6 h-fit">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
            {/* Header */}
            <div className="px-6 py-5 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Issues Overview</h2>
                <span className="px-3 py-1 rounded-full text-sm font-medium bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400">
                  {totalIssues} total
                </span>
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Across all {scans.length} files</p>
            </div>

            {/* Issue Categories */}
            <div className="divide-y divide-gray-100 dark:divide-gray-700/50 max-h-[calc(100vh-12rem)] overflow-y-auto">
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
                          <h3 className="font-medium text-gray-900 dark:text-white text-sm">{category.label}</h3>
                          <p className="text-xs text-gray-500 dark:text-gray-400 capitalize mt-0.5">
                            {category.severity} severity
                          </p>
                        </div>
                      </div>
                      <span className={`px-3 py-1 rounded-full text-sm font-semibold ${styles.badge}`}>
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
                                  <span className="font-medium text-gray-900 dark:text-white text-sm truncate">
                                    {issue.filename}
                                  </span>
                                  {issue.page && (
                                    <span className="flex-shrink-0 text-xs px-2 py-1 rounded-md bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 font-medium">
                                      Page {issue.page}
                                    </span>
                                  )}
                                </div>
                                {issue.description && (
                                  <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                                    {issue.description}
                                  </p>
                                )}
                              </div>
                              <button
                                onClick={() => {
                                  const scan = scans.find((s) => s.scanId === issue.scanId)
                                  if (scan) handleViewDetails(scan)
                                }}
                                className="flex-shrink-0 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium hover:underline transition-colors"
                              >
                                View
                              </button>
                            </div>
                          </div>
                        ))}
                        {category.issues.length > 10 && (
                          <div className="text-center pt-2">
                            <p className="text-sm text-gray-500 dark:text-gray-400">
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
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/20 mb-4">
                    <svg
                      className="w-8 h-8 text-green-600 dark:text-green-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">No Issues Found</h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
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
