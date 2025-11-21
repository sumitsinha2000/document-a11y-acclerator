import { useState, useEffect, useRef } from "react"
import axios from "axios"
import IssuesList from "./IssuesList"
import FixSuggestions from "./FixSuggestions"
import SidebarNav from "./SidebarNav"
import Breadcrumb from "./Breadcrumb"
import ExportDropdown from "./ExportDropdown"
import FixHistory from "./FixHistory"
import AIFixStrategyModal from "./AIFixStrategyModal"
import API_BASE_URL, { API_ENDPOINTS } from "../config/api"
import { useNotification } from "../contexts/NotificationContext"
import { parseBackendDate } from "../utils/dates"
import { resolveSummary, calculateComplianceSnapshot } from "../utils/compliance"

export default function ReportViewer({ scans, onBack, onBackToFolder, sidebarOpen = true }) {
  const [selectedFileIndex, setSelectedFileIndex] = useState(0)
  const [reportData, setReportData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedCategory, setSelectedCategory] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [aiLoading, setAiLoading] = useState(false)
  const [showAiModal, setShowAiModal] = useState(false)
  const [aiStrategy, setAiStrategy] = useState(null)
  const [aiIssueType, setAiIssueType] = useState("")
  const [aiFixCategory, setAiFixCategory] = useState("")
  const tabRefs = useRef([])
  const tabContainerRef = useRef(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)

  const { showSuccess, showError, showWarning, showInfo } = useNotification()

  useEffect(() => {
    const currentScan = scans[selectedFileIndex]
    console.log("[v0] ReportViewer - Current scan data:", currentScan)
    console.log("[v0] ReportViewer - Scan has fixes:", currentScan.fixes)
    console.log("[v0] ReportViewer - Number of fixes:", currentScan.fixes?.length)
    console.log("[v0] ReportViewer - Applied fixes:", currentScan.appliedFixes)

    if (currentScan.results) {
      console.log("[v0] Scan has results:", currentScan.results)
      console.log("[v0] Results keys:", Object.keys(currentScan.results || {}))
      setReportData(currentScan)
      setLoading(false)
    } else if (currentScan.id) {
      fetchReportDetails(currentScan.id)
    }
  }, [selectedFileIndex, scans])

  useEffect(() => {
    if (tabRefs.current[selectedFileIndex]) {
      tabRefs.current[selectedFileIndex].scrollIntoView({
        behavior: "smooth",
        block: "nearest",
        inline: "center",
      })
    }
  }, [selectedFileIndex])

  const fetchReportDetails = async (scanId, { showSpinner = true } = {}) => {
    try {
      if (showSpinner) {
        setLoading(true)
      }
      console.log("[v0] Fetching report details for:", scanId)
      const response = await axios.get(`${API_BASE_URL}/api/scan/${scanId}`)
      console.log("[v0] Received report data:", response.data)
      console.log("[v0] Results structure:", response.data.results)
      console.log("[v0] Results keys:", Object.keys(response.data.results || {}))
      console.log("[v0] Applied fixes from backend:", response.data.appliedFixes)
      setReportData(response.data)
    } catch (error) {
      console.error("[v0] Error fetching report:", error)
    } finally {
      if (showSpinner) {
        setLoading(false)
      }
    }
  }

  const checkScrollPosition = () => {
    if (tabContainerRef.current) {
      const { scrollLeft, scrollWidth, clientWidth } = tabContainerRef.current
      setCanScrollLeft(scrollLeft > 0)
      setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 1)
    }
  }

  useEffect(() => {
    checkScrollPosition()
    const container = tabContainerRef.current
    if (container) {
      container.addEventListener("scroll", checkScrollPosition)
      return () => container.removeEventListener("scroll", checkScrollPosition)
    }
  }, [scans])

  const scrollTabs = (direction) => {
    if (tabContainerRef.current) {
      const scrollAmount = 300
      tabContainerRef.current.scrollBy({
        left: direction === "left" ? -scrollAmount : scrollAmount,
        behavior: "smooth",
      })
    }
  }

  const handleRefresh = async (
    updatedSummary = undefined,
    updatedResults = undefined,
    updatedVerapdfStatus = undefined,
    updatedFixes = undefined,
  ) => {
    setIsRefreshing(true)
    try {
      const currentScan = scans[selectedFileIndex]
      const targetScanId =
        currentScan?.scanId || currentScan?.id || reportData?.scanId || reportData?.id

      const hasFreshData =
        updatedSummary !== undefined ||
        updatedResults !== undefined ||
        updatedVerapdfStatus !== undefined ||
        updatedFixes !== undefined

      if (hasFreshData && reportData) {
        setReportData((prev) => {
          if (!prev) return prev
          return {
            ...prev,
            summary: updatedSummary !== undefined ? updatedSummary : prev.summary,
            results: updatedResults !== undefined ? updatedResults : prev.results,
            verapdfStatus:
              updatedVerapdfStatus !== undefined ? updatedVerapdfStatus : prev.verapdfStatus,
            fixes: updatedFixes !== undefined ? updatedFixes : prev.fixes,
          }
        })
        setRefreshKey((prev) => prev + 1)
        showSuccess("Report updated with the latest scan data")
        return
      }

      if (targetScanId) {
        console.log("[v0] ReportViewer - Refreshing data for scan:", targetScanId)
        await fetchReportDetails(targetScanId, { showSpinner: false })
        setRefreshKey((prev) => prev + 1)
        showSuccess("Report refreshed successfully")
      } else {
        console.warn("[v0] ReportViewer - No scan ID available for refresh")
      }
    } catch (error) {
      console.error("[v0] ReportViewer - Error refreshing:", error)
      showError("Failed to refresh report")
    } finally {
      setIsRefreshing(false)
    }
  }

  const handleAiRemediation = async (issueType, fixCategory) => {
    setAiLoading(true)
    try {
      const currentScan = scans[selectedFileIndex]
      const scanId = currentScan.scanId || currentScan.id

      const issues = reportData.results[issueType] || []

      console.log(`[v0] Requesting AI ${fixCategory} strategy for ${issueType}:`, issues.length, "issues")

      const response = await axios.post(API_ENDPOINTS.aiFixStrategy(scanId), {
        issueType,
        fixCategory,
        issues,
      })

      if (response.data.success) {
        setAiStrategy(response.data.strategy)
        setAiIssueType(issueType)
        setAiFixCategory(fixCategory)
        setShowAiModal(true)
        console.log("[v0] AI strategy received:", response.data.strategy)
      }
    } catch (error) {
      console.error("[v0] Error getting AI strategy:", error)
      showError("Failed to get AI remediation strategy. Please try again.")
    } finally {
      setAiLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50 dark:bg-slate-900">
        <div className="text-lg text-gray-600 dark:text-gray-400">Loading report...</div>
      </div>
    )
  }

  if (!reportData) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50 dark:bg-slate-900">
        <div className="text-lg text-red-600 dark:text-red-400">Failed to load report</div>
      </div>
    )
  }

  const verapdfStatus = calculateComplianceSnapshot(
    reportData.results,
    reportData?.verapdfStatus || {
      isActive: false,
      wcagCompliance: null,
      pdfuaCompliance: null,
      pdfaCompliance: null,
      totalVeraPDFIssues: 0,
    },
  )

  const summary = resolveSummary({
    summary: reportData.summary,
    results: reportData.results,
    verapdfStatus,
  })

  const scanStatus = (reportData.status || "").toLowerCase()
  const isUploaded = scanStatus === "uploaded"
  const scanDateLabel = isUploaded ? "Uploaded on" : "Scanned on"
  const parsedReportDate = parseBackendDate(reportData.uploadDate || reportData.timestamp || reportData.created_at)

  const breadcrumbItems = [{ label: "Home", onClick: onBack }, { label: "Report" }]
  const folderIdentifier = reportData.batchId || reportData.folderId
  const folderLabel = reportData.batchName || reportData.folderName || "folder"
  const canReturnToFolder = Boolean(onBackToFolder && folderIdentifier)

  return (
    <div className="flex overflow-x-hidden bg-slate-50 dark:bg-slate-900">
      <SidebarNav isOpen={sidebarOpen} />

      {/* Collapsible batch files sidebar */}
      {scans.length > 1 && (
        <div
          className={`fixed left-[240px] top-0 h-full bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 transition-all duration-300 z-40 ${
            isSidebarCollapsed ? "w-0" : "w-64"
          } overflow-hidden`}
        >
          <div className="h-full flex flex-col">
            {/* Sidebar Header */}
            <div className="px-4 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Folder Files</h2>
              <span className="text-xs text-slate-500 dark:text-slate-400">{scans.length} files</span>
            </div>

            {/* Files List */}
            <div className="flex-1 overflow-y-auto p-2">
              {scans.map((scan, index) => (
                <button
                  key={index}
                  onClick={() => setSelectedFileIndex(index)}
                  className={`w-full text-left px-3 py-3 rounded-lg mb-2 transition-all ${
                    selectedFileIndex === index
                      ? "bg-violet-50 dark:bg-violet-900/20 border-2 border-violet-500"
                      : "bg-slate-50 dark:bg-slate-700/50 border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700"
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <svg
                      className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
                        selectedFileIndex === index
                          ? "text-violet-600 dark:text-violet-400"
                          : "text-slate-400 dark:text-slate-500"
                      }`}
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
                    <div className="flex-1 min-w-0">
                      <p
                        className={`text-sm font-medium truncate ${
                          selectedFileIndex === index
                            ? "text-violet-900 dark:text-violet-100"
                            : "text-slate-700 dark:text-slate-300"
                        }`}
                      >
                        {scan.fileName || scan.filename}
                      </p>
                      {scan.summary && scan.status !== "uploaded" && typeof scan.summary.complianceScore === "number" && (
                        <div className="flex items-center gap-2 mt-1">
                          <span
                            className={`text-xs font-semibold ${
                              scan.summary.complianceScore >= 70
                                ? "text-emerald-600 dark:text-emerald-400"
                                : "text-rose-600 dark:text-rose-400"
                            }`}
                          >
                            {scan.summary.complianceScore}%
                          </span>
                          <span className="text-xs text-slate-500 dark:text-slate-400">
                            {scan.summary.totalIssues} issues
                          </span>
                        </div>
                      )}
                      {/* Status badge */}
                      {scan.status && (
                        <span
                          className={`inline-block mt-1 px-2 py-0.5 text-xs font-medium rounded-full ${
                            scan.status === "fixed"
                              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                              : scan.status === "processed"
                                ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
                                : scan.status === "compliant"
                                  ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                                  : scan.status === "uploaded"
                                    ? "bg-slate-100 text-slate-700 dark:bg-slate-800/60 dark:text-slate-200"
                                    : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                          }`}
                        >
                          {scan.status === "fixed"
                            ? "Fixed"
                            : scan.status === "processed"
                              ? "Processed"
                              : scan.status === "compliant"
                                ? "Compliant"
                                : scan.status === "uploaded"
                                  ? "Uploaded"
                                  : "Unprocessed"}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {scans.length > 1 && (
        <button
          onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          className={`fixed top-20 z-50 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-r-lg p-2 shadow-lg hover:bg-slate-50 dark:hover:bg-slate-700 transition-all ${
            isSidebarCollapsed ? "left-[240px]" : "left-[496px]"
          }`}
          aria-label={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <svg
            className={`w-5 h-5 text-slate-600 dark:text-slate-400 transition-transform ${
              isSidebarCollapsed ? "" : "rotate-180"
            }`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
      )}

      <div
        className={`flex-1 transition-all duration-300 ${
          sidebarOpen ? "ml-[240px]" : "ml-0"
        } ${scans.length > 1 && !isSidebarCollapsed ? "ml-[504px]" : ""} ${
          sidebarOpen ? "min-h-screen" : "min-h-0"
        } bg-white dark:bg-slate-800 border-r border-b border-slate-200 dark:border-slate-700 flex flex-col`}
      >
        <div className="px-8 py-8">
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <div className="flex flex-wrap items-center gap-3">
              {canReturnToFolder && (
                <button
                  type="button"
                  onClick={onBackToFolder}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 hover:text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-white"
                >
                  <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 4L4 10l6 6" />
                  </svg>
                  <span>{`Back to ${folderLabel} files`}</span>
                </button>
              )}
            </div>
            <div className="flex items-center gap-2 ml-auto">
              <button
                onClick={handleRefresh}
                className="px-3 py-2 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-900 dark:text-white rounded-lg transition-colors flex items-center gap-1 font-semibold text-sm border border-slate-200 dark:border-slate-600"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                <span>Refresh</span>
              </button>
              <ExportDropdown scanId={reportData.scanId} filename={reportData.fileName || reportData.filename} />
            </div>
          </div>

          <div className="flex items-start justify-between">
            <div>
              {reportData.groupName && (
                <div className="flex items-center gap-2 mb-3">
                  <svg
                    className="w-6 h-6 text-violet-600 dark:text-violet-400"
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
                  <span className="text-violet-700 dark:text-violet-300 font-bold text-xl">{reportData.groupName}</span>
                </div>
              )}
              {/* <h1 className="text-3xl font-bold text-slate-900 dark:text-white mb-3">
                {reportData.fileName || reportData.filename}
              </h1> */}
              <div className="flex items-center gap-4 text-base text-slate-600 dark:text-slate-400 font-medium">
                {/* <span>
                  {scanDateLabel}{" "}
                  {parsedReportDate ? parsedReportDate.toLocaleDateString() : "Date unavailable"}
                </span> */}
                {reportData.appliedFixes && (
                  <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-semibold">
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                        clipRule="evenodd"
                      />
                    </svg>
                    {reportData.appliedFixes.successCount} fixes applied
                  </span>
                )}
              </div>
          </div>

          {/* {verapdfStatus.isActive && (
            <div className="flex items-center gap-2 px-5 py-3 bg-blue-50 dark:bg-blue-500/20 border-2 border-blue-200 dark:border-blue-400/30 rounded-lg">
              <svg className="w-6 h-6 text-blue-600 dark:text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-.723-.725 3.066 3.066 0 01-2.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                    clipRule="evenodd"
                  />
                </svg>
                <span className="font-bold text-blue-700 dark:text-blue-300 text-base">veraPDF Validated</span>
              </div>
          )} */}
        </div>

        {isUploaded && (
          <div className="mt-4 px-4 py-3 bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg flex items-start gap-3">
            <svg className="w-5 h-5 text-slate-600 dark:text-slate-300 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M12 6a9 9 0 110 12 9 9 0 010-12z" />
            </svg>
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">Scan not started</p>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                This file has been uploaded but not analyzed yet. Use the "Begin Scan" option from the dashboard or batch view to generate accessibility results.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="pt-4 px-8 pb-8 space-y-6">
          {scans.length > 1 && (
            <div className="flex items-center gap-3 bg-white dark:bg-slate-800 rounded-xl p-3 shadow-sm border border-slate-200 dark:border-slate-700">
              {scans.map((scan, index) => (
                <button
                  key={index}
                  ref={(el) => (tabRefs.current[index] = el)}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm transition-all whitespace-nowrap flex-shrink-0 font-medium ${
                    selectedFileIndex === index
                      ? "bg-gradient-to-r from-violet-600 to-purple-600 text-white shadow-lg"
                      : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600"
                  }`}
                  onClick={() => setSelectedFileIndex(index)}
                >
                  <span>📄</span>
                  <span>{scan.fileName || scan.filename}</span>
                  {scan.summary && scan.status !== "uploaded" && typeof scan.summary.complianceScore === "number" && (
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                        scan.summary.complianceScore >= 70
                          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                          : "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400"
                      }`}
                    >
                      {scan.summary.complianceScore}%
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}

          {!isUploaded ? (
            <>
              <div id="overview" key={`overview-${refreshKey}`}>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-7">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <p className="text-base font-semibold text-slate-600 dark:text-slate-400 mb-3">Compliance Score</p>
                        <div className="flex items-baseline">
                          <p className="text-4xl font-bold text-slate-900 dark:text-white">{summary.complianceScore}%</p>
                        </div>
                      </div>
                      <div
                        className={`w-16 h-16 rounded-full flex items-center justify-center ${summary.complianceScore >= 70 ? "bg-emerald-100 dark:bg-emerald-900/30" : "bg-rose-100 dark:bg-rose-900/30"}`}
                      >
                        <svg
                          className={`w-8 h-8 ${summary.complianceScore >= 70 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                          />
                        </svg>
                      </div>
                    </div>

                    {verapdfStatus.isActive && (
                      <div className="flex flex-wrap gap-2 pt-4 border-t border-slate-200 dark:border-slate-700">
                        {typeof verapdfStatus.wcagCompliance === "number" && (
                          <div className="flex items-center gap-1.5 px-3.5 py-2 bg-blue-50 dark:bg-blue-900/20 rounded-full border border-blue-200 dark:border-blue-800">
                            <svg className="w-4 h-4 text-blue-600 dark:text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                              <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                              <path
                                fillRule="evenodd"
                                d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z"
                                clipRule="evenodd"
                              />
                            </svg>
                            <span className="text-sm font-bold text-blue-700 dark:text-blue-300">
                              WCAG {verapdfStatus.wcagCompliance}%
                            </span>
                          </div>
                        )}
                        {typeof verapdfStatus.pdfuaCompliance === "number" && (
                          <div className="flex items-center gap-1.5 px-3.5 py-2 bg-purple-50 dark:bg-purple-900/20 rounded-full border border-purple-200 dark:border-purple-800">
                            <svg
                              className="w-4 h-4 text-purple-600 dark:text-purple-400"
                              fill="currentColor"
                              viewBox="0 0 20 20"
                            >
                              <path
                                fillRule="evenodd"
                                d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
                                clipRule="evenodd"
                              />
                            </svg>
                            <span className="text-sm font-bold text-purple-700 dark:text-purple-300">
                              PDF/UA {verapdfStatus.pdfuaCompliance}%
                            </span>
                          </div>
                        )}
                        {typeof verapdfStatus.pdfaCompliance === "number" && (
                          <div className="flex items-center gap-1.5 px-3.5 py-2 bg-emerald-50 dark:bg-emerald-900/20 rounded-full border border-emerald-200 dark:border-emerald-800">
                            <svg
                              className="w-4 h-4 text-emerald-600 dark:text-emerald-400"
                              fill="currentColor"
                              viewBox="0 0 20 20"
                            >
                              <path d="M4 3a2 2 0 012-2h6.586A2 2 0 0114 1.586L18.414 6A2 2 0 0120 7.414V17a2 2 0 01-2 2H6a2 2 0 01-2-2V3z" />
                              <path
                                fillRule="evenodd"
                                d="M8 11a1 1 0 011-1h6a1 1 0 110 2H9a1 1 0 01-1-1z"
                                clipRule="evenodd"
                              />
                            </svg>
                            <span className="text-sm font-bold text-emerald-700 dark:text-emerald-300">
                              PDF/A {verapdfStatus.pdfaCompliance}%
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-7">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-base font-semibold text-slate-600 dark:text-slate-400 mb-3">Total Issues</p>
                        <div className="flex items-baseline">
                          <p className="text-4xl font-bold text-slate-900 dark:text-white">{summary.totalIssues}</p>
                        </div>
                      </div>
                      <div className="w-16 h-16 bg-amber-100 dark:bg-amber-900/30 rounded-full flex items-center justify-center">
                        <svg
                          className="w-8 h-8 text-amber-600 dark:text-amber-400"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                          />
                        </svg>
                      </div>
                    </div>
                  </div>

                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-7">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-base font-semibold text-slate-600 dark:text-slate-400 mb-3">High Severity</p>
                        <div className="flex items-baseline">
                          <p className="text-4xl font-bold text-slate-900 dark:text-white">{summary.highSeverity}</p>
                        </div>
                      </div>
                      <div className="w-16 h-16 bg-rose-100 dark:bg-rose-900/30 rounded-full flex items-center justify-center">
                        <svg
                          className="w-8 h-8 text-rose-600 dark:text-rose-400"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                          />
                        </svg>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700">
                <FixHistory key={`fix-history-${refreshKey}`} scanId={reportData.scanId} onRefresh={handleRefresh} />
              </div>

              <div id="issues" key={`issues-${refreshKey}`}>
                <IssuesList
                  results={reportData.results}
                  selectedCategory={selectedCategory}
                  onSelectCategory={setSelectedCategory}
                />
              </div>

              <div id="fixes" key={`fixes-${refreshKey}`}>
                <FixSuggestions
                  scanId={reportData.scanId}
                  fixes={reportData.fixes}
                  filename={reportData.fileName || reportData.filename}
                  onRefresh={handleRefresh}
                />
              </div>
            </>
          ) : (
            <div
              id="overview"
              className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-8"
            >
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">Ready to Scan</h2>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                Start the scan from the dashboard, history, or batch views to generate accessibility results for this
                file. Once the scan finishes, you will see detailed issue breakdowns, automated fix options, and export
                actions here.
              </p>
            </div>
          )}
        </div>

        {showAiModal && (
          <AIFixStrategyModal
            strategy={aiStrategy}
            issueType={aiIssueType}
            fixCategory={aiFixCategory}
            onClose={() => setShowAiModal(false)}
          />
        )}
      </div>
    </div>
  )
}
