import { useState, useEffect, useRef, useCallback, useMemo } from "react"
import axios from "axios"
import FixSuggestions from "./FixSuggestions"
import SidebarNav from "./SidebarNav"
import Breadcrumb from "./Breadcrumb"
import ExportDropdown from "./ExportDropdown"
import FixHistory from "./FixHistory"
import WcagCriteriaSummary from "./WcagCriteriaSummary"
import PdfUaCriteriaSummary from "./PdfUaCriteriaSummary"
import AIFixStrategyModal from "./AIFixStrategyModal"
import API_BASE_URL, { API_ENDPOINTS } from "../config/api"
import { useNotification } from "../contexts/NotificationContext"
import { parseBackendDate } from "../utils/dates"
import { resolveSummary, calculateComplianceSnapshot } from "../utils/compliance"
import { getScanErrorMessage, getScanStatus, resolveEntityStatus } from "../utils/statuses"

const STATUS_BADGE_STYLES = {
  uploaded: "bg-slate-100 text-slate-700 dark:bg-slate-800/60 dark:text-slate-200",
  scanned: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  partially_fixed: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  fixed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  error: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400",
  default: "bg-gray-100 text-gray-700 dark:bg-gray-800/60 dark:text-gray-200",
}

const isNumeric = (value) => typeof value === "number" && Number.isFinite(value)

const filterDefinedFields = (payload) => {
  if (!payload || typeof payload !== "object") {
    return {}
  }

  return Object.entries(payload).reduce((acc, [key, value]) => {
    if (value !== undefined) {
      acc[key] = value
    }
    return acc
  }, {})
}

export default function ReportViewer({
  scans,
  onBack,
  onBackToFolder,
  sidebarOpen = true,
  onScanComplete,
  onScanUpdate,
}) {
  const [selectedFileIndex, setSelectedFileIndex] = useState(0)
  const [reportData, setReportData] = useState(null)
  const [loading, setLoading] = useState(true)
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
  const [isScanningFile, setIsScanningFile] = useState(false)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)
  const [isContrastPanelOpen, setIsContrastPanelOpen] = useState(false)

  const { showSuccess, showError, showWarning, showInfo } = useNotification()

  const notifyScanUpdate = useCallback(
    (data) => {
      if (onScanUpdate && data) {
        onScanUpdate(data)
      }
    },
    [onScanUpdate],
  )

  const applyUpdatesFromPayload = (payload) => {
    const definedPayload = filterDefinedFields(payload)
    if (Object.keys(definedPayload).length === 0) {
      return null
    }

    const referenceScan = reportData || scans[selectedFileIndex] || {}
    const updatedData = {
      ...referenceScan,
      ...definedPayload,
    }

    setReportData(updatedData)
    setRefreshKey((prev) => prev + 1)
    notifyScanUpdate(updatedData)
    return updatedData
  }

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

  const resolveScanIdentifier = (scan) =>
    scan?.scanId ||
    scan?.id ||
    scan?.scan_id ||
    scan?.filename ||
    scan?.fileName ||
    null

  const fetchReportDetails = async (scanId, { showSpinner = true } = {}) => {
    try {
      if (showSpinner) {
        setLoading(true)
      }
      console.log("[v0] Fetching report details for:", scanId)
      const response = await axios.get(API_ENDPOINTS.scanDetails(scanId))
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
    updatedCriteriaSummary = undefined,
  ) => {
    setIsRefreshing(true)
    try {
      const currentScan = scans[selectedFileIndex]
      const targetScanId =
        resolveScanIdentifier(reportData) || resolveScanIdentifier(currentScan)

      const hasFreshData =
        updatedSummary !== undefined ||
        updatedResults !== undefined ||
        updatedVerapdfStatus !== undefined ||
        updatedFixes !== undefined ||
        updatedCriteriaSummary !== undefined

      if (hasFreshData) {
        const merged = applyUpdatesFromPayload({
          summary: updatedSummary,
          results: updatedResults,
          verapdfStatus: updatedVerapdfStatus,
          fixes: updatedFixes,
          criteriaSummary: updatedCriteriaSummary,
        })
        if (merged) {
          showSuccess("Report updated with the latest scan data")
        }
        return
      }

      if (targetScanId) {
        console.log("[v0] ReportViewer - Refreshing data for scan:", targetScanId)
        const response = await axios.get(API_ENDPOINTS.scanDetails(targetScanId))
        if (response?.data) {
          setReportData(response.data)
          setRefreshKey((prev) => prev + 1)
          notifyScanUpdate(response.data)
          showSuccess("Report refreshed successfully")
        }
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

  const handleScanFile = async () => {
    const targetScanId = reportData?.scanId || reportData?.id
    if (!targetScanId) {
      showWarning("Unable to start a scan for this file at the moment.")
      return
    }

    setIsScanningFile(true)
    try {
      const response = await axios.post(API_ENDPOINTS.startScan(targetScanId))
      const payload = response?.data

        if (payload) {
          setReportData((prev) => {
            if (!prev) {
              return payload
            }
            return {
              ...prev,
              ...payload,
              scanId: payload.scanId || prev.scanId,
              filename: payload.filename || prev.filename,
              fileName: payload.fileName || prev.fileName,
              groupName: payload.groupName || prev.groupName,
              summary: payload.summary || prev.summary,
              results: payload.results || prev.results,
              verapdfStatus: payload.verapdfStatus || prev.verapdfStatus,
              fixes: payload.fixes || prev.fixes,
              status: payload.status || prev.status,
            }
          })
          setRefreshKey((prev) => prev + 1)
          showSuccess("Scan completed for this file.")
          if (onScanComplete) {
            onScanComplete({ scanId: targetScanId, payload })
          }
        }
    } catch (error) {
      console.error("[v0] ReportViewer - Failed to scan file:", error)
      showError("Failed to scan this file. Please try again.")
    } finally {
      setIsScanningFile(false)
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

  const contrastSamples = useMemo(() => {
    const issues = reportData?.results?.poorContrast
    if (!Array.isArray(issues)) {
      return []
    }

    const seenTexts = new Set()
    const samples = []

    for (const issue of issues) {
      if (!issue || typeof issue !== "object") {
        continue
      }
      const snippet = typeof issue.textSample === "string" ? issue.textSample.trim() : ""
      if (!snippet || seenTexts.has(snippet)) {
        continue
      }
      seenTexts.add(snippet)

      const pages = Array.isArray(issue.pages) ? issue.pages.filter((page) => page !== null && page !== undefined) : []
      const pageLabel = pages.length > 0 ? pages.join(", ") : issue.page || null
      const ratioValue = Number(issue.contrastRatio)

      samples.push({
        text: snippet,
        pageLabel,
        ratio: Number.isFinite(ratioValue) ? ratioValue.toFixed(1) : null,
      })

      if (samples.length >= 3) {
        break
      }
    }

    return samples
  }, [reportData?.results?.poorContrast])

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
      totalVeraPDFIssues: 0,
    },
  )

  const summary = resolveSummary({
    summary: reportData.summary,
    results: reportData.results,
    verapdfStatus,
  })

  const wcagComplianceDisplay = isNumeric(summary.wcagCompliance)
    ? summary.wcagCompliance
    : verapdfStatus.wcagCompliance
  const pdfuaComplianceDisplay = isNumeric(summary.pdfuaCompliance)
    ? summary.pdfuaCompliance
    : verapdfStatus.pdfuaCompliance
  const showComplianceBadges =
    verapdfStatus.isActive &&
    (isNumeric(wcagComplianceDisplay) || isNumeric(pdfuaComplianceDisplay))

  const totalIssuesValue = isNumeric(reportData.totalIssues)
    ? reportData.totalIssues
    : isNumeric(summary.totalIssues)
      ? summary.totalIssues
      : 0
  const remainingIssuesValue = isNumeric(reportData.remainingIssues)
    ? reportData.remainingIssues
    : isNumeric(summary.remainingIssues)
      ? summary.remainingIssues
      : isNumeric(summary.issuesRemaining)
        ? summary.issuesRemaining
        : 0
  const fixesAppliedCount = isNumeric(reportData.appliedFixes?.successCount)
    ? reportData.appliedFixes.successCount
    : isNumeric(reportData.issuesFixed)
      ? reportData.issuesFixed
      : isNumeric(summary.issuesFixed)
        ? summary.issuesFixed
        : 0
  const reportedIssuesFixed = isNumeric(reportData.issuesFixed)
    ? reportData.issuesFixed
    : isNumeric(summary.issuesFixed)
      ? summary.issuesFixed
      : 0
  const issueDelta = totalIssuesValue - remainingIssuesValue
  const hasIssueDelta = typeof issueDelta === "number" && issueDelta !== 0
  const hasReportedIssuesFixed = reportedIssuesFixed > 0

  const scanStatus = getScanStatus(reportData)
  const isScanError = scanStatus === "error"
  const scanErrorMessage = isScanError ? getScanErrorMessage(reportData) : null
  const isUploaded = scanStatus === "uploaded"
  const isCompletedScan = !isUploaded && !isScanError
  const canExportReport = isCompletedScan
  const scanDateLabel = isUploaded ? "Uploaded on" : isScanError ? "Attempted scan on" : "Scanned on"
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
              {scans.map((scan, index) => {
                const statusInfo = resolveEntityStatus(scan)
                const showSummary =
                  scan.summary &&
                  statusInfo.code !== "uploaded" &&
                  statusInfo.code !== "error" &&
                  typeof scan.summary.complianceScore === "number"

                return (
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
                        {showSummary && (
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
                        {statusInfo.label && (
                          <span
                            className={`inline-block mt-1 px-2 py-0.5 text-xs font-medium rounded-full ${
                              STATUS_BADGE_STYLES[statusInfo.code] || STATUS_BADGE_STYLES.default
                            }`}
                          >
                            {statusInfo.label}
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                )
              })}
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
                  <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 4L4 10l6 6" />
                  </svg>
                  <span>{`Back to ${folderLabel} dashboard`}</span>
                </button>
              )}
            </div>
          <div className="flex items-center gap-2 ml-auto">
            <button
              onClick={() => handleRefresh()}
              disabled={isRefreshing}
              aria-busy={isRefreshing}
              className={`px-3 py-2 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-900 dark:text-white rounded-lg transition-colors flex items-center gap-1 font-semibold text-sm border border-slate-200 dark:border-slate-600 ${
                isRefreshing ? "cursor-wait opacity-80" : ""
              }`}
            >
              {isRefreshing ? (
                <svg
                  className="w-4 h-4 animate-spin text-slate-500 dark:text-slate-200"
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden="true"
                >
                  <circle className="opacity-25" cx="12" cy="12" r="10" strokeWidth="3" stroke="currentColor" />
                  <path
                    className="opacity-75"
                    d="M4 12a8 8 0 018-8"
                    strokeWidth="3"
                    strokeLinecap="round"
                    stroke="currentColor"
                  />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
              )}
              <span>{isRefreshing ? "Refreshing…" : "Refresh"}</span>
            </button>
            {isUploaded && (
              <button
                type="button"
                onClick={handleScanFile}
                disabled={isScanningFile}
                className={`px-3 py-2 rounded-lg border border-violet-500 flex items-center gap-2 text-sm font-semibold transition ${
                  isScanningFile
                    ? "bg-violet-100 text-violet-600 cursor-wait"
                    : "bg-gradient-to-r from-violet-600 to-purple-600 text-white hover:from-violet-500 hover:to-purple-500"
                }`}
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 7h16M4 12h10M4 17h14"
                  />
                </svg>
                <span>{isScanningFile ? "Scanning…" : "Scan file"}</span>
              </button>
            )}
            <ExportDropdown
              scanId={reportData.scanId}
              filename={reportData.fileName || reportData.filename}
              disabled={!canExportReport}
            />
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
          <div className="mt-4 px-4 py-3 bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg flex items-center gap-3">
            <svg
              className="w-5 h-5 text-slate-600 dark:text-slate-300"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 2a10 10 0 100 20 10 10 0 000-20z"
              />
            </svg>
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">Scan not started</p>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                This file has been uploaded but not analyzed yet. Use the "Scan File" option to generate accessibility results.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="px-8 pb-8 space-y-6">
          {scans.length > 1 && (
            <div className="flex items-center gap-3 bg-white dark:bg-slate-800 rounded-xl p-3 shadow-sm border border-slate-200 dark:border-slate-700">
              {scans.map((scan, index) => {
                const statusInfo = resolveEntityStatus(scan)
                const showCompliance =
                  scan.summary &&
                  statusInfo.code !== "uploaded" &&
                  statusInfo.code !== "error" &&
                  typeof scan.summary.complianceScore === "number"

                return (
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
                    {showCompliance && (
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
                )
              })}
            </div>
          )}

          {isScanError && (
            <div
              className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-700 dark:border-rose-800/60 dark:bg-rose-900/20 dark:text-rose-300"
              role="status"
              aria-live="polite"
            >
              <span aria-hidden="true">⚠️</span>
              <div>
                <p className="font-semibold">Scan failed</p>
                <p className="text-sm mt-1">
                  {scanErrorMessage || "We were unable to analyze this file."}
                </p>
              </div>
            </div>
          )}

          {isCompletedScan ? (
            <>
              <div id="overview" key={`overview-${refreshKey}`}>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
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
                          aria-hidden="true"
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

                    {showComplianceBadges && (
                      <div className="flex flex-wrap gap-2 pt-4 border-t border-slate-200 dark:border-slate-700">
                        {isNumeric(wcagComplianceDisplay) && (
                          <div className="flex items-center gap-1.5 px-3.5 py-2 bg-blue-50 dark:bg-blue-900/20 rounded-full border border-blue-200 dark:border-blue-800">
                            <svg className="w-4 h-4 text-blue-600 dark:text-blue-400" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                              <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                              <path
                                fillRule="evenodd"
                                d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z"
                                clipRule="evenodd"
                              />
                            </svg>
                            <span className="text-sm font-bold text-blue-700 dark:text-blue-300">
                              WCAG {wcagComplianceDisplay}%
                            </span>
                          </div>
                        )}
                        {isNumeric(pdfuaComplianceDisplay) && (
                          <div className="flex items-center gap-1.5 px-3.5 py-2 bg-purple-50 dark:bg-purple-900/20 rounded-full border border-purple-200 dark:border-purple-800">
                            <svg
                              className="w-4 h-4 text-purple-600 dark:text-purple-400"
                              fill="currentColor"
                              viewBox="0 0 20 20"
                              aria-hidden="true"
                            >
                              <path
                                fillRule="evenodd"
                                d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
                                clipRule="evenodd"
                              />
                            </svg>
                            <span className="text-sm font-bold text-purple-700 dark:text-purple-300">
                              PDF/UA {pdfuaComplianceDisplay}%
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-7">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-base font-semibold text-slate-600 dark:text-slate-400 mb-3">
                          {issueDelta === 0 ? "Issues" : "Remaining Issues"}
                        </p>
                        <div className="flex items-baseline">
                          <p className="text-4xl font-bold text-slate-900 dark:text-white">{remainingIssuesValue}</p>
                        </div>
                        {hasIssueDelta && (
                          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                            Issues still reported on the latest scan
                          </p>
                        )}
                        {hasIssueDelta && (
                          <div className="mt-2 flex items-center gap-1 text-xs font-semibold">
                            {issueDelta > 0 ? (
                              <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                                <span aria-hidden="true" className="text-base leading-none">↓</span>
                                <span>{issueDelta} resolved</span>
                              </span>
                            ) : (
                              <span className="text-rose-600 dark:text-rose-400 flex items-center gap-1">
                                <span aria-hidden="true" className="text-base leading-none">↑</span>
                                <span>{Math.abs(issueDelta)} new</span>
                              </span>
                            )}
                          </div>
                        )}
                        {!hasIssueDelta && hasReportedIssuesFixed && (
                          <div className="mt-2 flex items-center gap-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                            <span aria-hidden="true" className="text-base leading-none">↓</span>
                            <span>
                              {reportedIssuesFixed} issue{reportedIssuesFixed === 1 ? "" : "s"} fixed since last scan
                            </span>
                          </div>
                        )}
                      </div>
                      <div className="w-16 h-16 bg-amber-50 dark:bg-amber-900/10 rounded-full flex items-center justify-center">
                        <svg
                          className="w-8 h-8 text-amber-500 dark:text-amber-300"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                          aria-hidden="true"
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
                        <p className="text-base font-semibold text-slate-600 dark:text-slate-400 mb-3">Fixes Applied</p>
                        <div className="flex items-baseline">
                          <p className="text-4xl font-bold text-slate-900 dark:text-white">{fixesAppliedCount}</p>
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                          Fixes recorded for this scan
                        </p>
                      </div>
                      <div className="w-16 h-16 bg-emerald-100 dark:bg-emerald-900/30 rounded-full flex items-center justify-center">
                        <svg
                          className="w-8 h-8 text-emerald-600 dark:text-emerald-400"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                          aria-hidden="true"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M5 13l4 4L19 7"
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
                          aria-hidden="true"
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
                <FixHistory
                  scanId={reportData.scanId}
                  onRefresh={handleRefresh}
                  refreshSignal={refreshKey}
                />
              </div>

              <div id="criteria" key={`criteria-${refreshKey}`} className="space-y-6">
                <WcagCriteriaSummary
                  criteriaSummary={reportData.criteriaSummary?.wcag}
                  results={reportData.results}
                />
                <PdfUaCriteriaSummary
                  criteriaSummary={reportData.criteriaSummary?.pdfua}
                  results={reportData.results}
                />
              </div>

              {contrastSamples.length > 0 && (
                <section
                  className="bg-white dark:bg-slate-800 rounded-2xl border border-amber-200/70 dark:border-amber-500/30 shadow-sm p-6"
                  aria-labelledby="contrast-sample-title"
                >
                  <header className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <p id="contrast-sample-title" className="text-base font-semibold text-slate-900 dark:text-white">
                        Sample contrast text
                      </p>
                      <p className="text-sm text-slate-500 dark:text-slate-400">
                        Use these snippets to pinpoint low-contrast passages flagged in this scan.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setIsContrastPanelOpen((prev) => !prev)}
                      aria-expanded={isContrastPanelOpen}
                      aria-controls="contrast-sample-panel"
                      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold uppercase tracking-wide bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-500"
                    >
                      <span>Contrast details</span>
                      <svg
                        className={`w-4 h-4 transition-transform ${isContrastPanelOpen ? "rotate-180" : ""}`}
                        viewBox="0 0 20 20"
                        fill="none"
                        stroke="currentColor"
                        aria-hidden="true"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 8l4 4 4-4" />
                      </svg>
                    </button>
                  </header>

                  {isContrastPanelOpen && (
                    <div
                      id="contrast-sample-panel"
                      role="region"
                      aria-live="polite"
                      className="mt-4 space-y-3"
                    >
                      {contrastSamples.map((sample, index) => (
                        <div
                          key={`${sample.text}-${sample.pageLabel || index}`}
                          className="rounded-xl border border-amber-100 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-900/20 p-4"
                        >
                          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold text-amber-800 dark:text-amber-200">
                            {sample.pageLabel && (
                              <span className="inline-flex items-center gap-1">
                                <span className="text-[11px] uppercase tracking-wide text-amber-600 dark:text-amber-300">Page</span>
                                {sample.pageLabel}
                              </span>
                            )}
                            {sample.ratio && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/80 text-amber-700 border border-amber-200 dark:bg-slate-900/40 dark:text-amber-200 dark:border-amber-500/40">
                                ~{sample.ratio}:1
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-slate-900 dark:text-slate-100 mt-2 leading-snug">
                            &quot;{sample.text}&quot;
                          </p>
                        </div>
                      ))}
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        Based on extracted text; snippets are truncated to keep this summary scannable.
                      </p>
                    </div>
                  )}
                </section>
              )}

              <div id="fixes">
                <FixSuggestions
                  scanId={reportData.scanId}
                  fixes={reportData.fixes}
                  filename={reportData.fileName || reportData.filename}
                  onRefresh={handleRefresh}
                />
              </div>
            </>
          ) : isUploaded ? (
            <div
              id="overview"
              className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-8"
            >
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">Ready to Scan</h2>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                Start the scan from the folder dashboard or from the scan button above in this dashboard to generate
                accessibility results.
              </p>
            </div>
          ) : (
            <div
              id="overview"
              className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-rose-200 dark:border-rose-800/60 p-8"
            >
              <h2 className="text-2xl font-bold text-rose-700 dark:text-rose-300 mb-2">Scan failed</h2>
              <p className="text-sm text-rose-700/90 dark:text-rose-200">
                {scanErrorMessage || "We were unable to analyze this file."}
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
