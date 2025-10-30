"use client"

import { useState, useEffect, useRef } from "react"
import axios from "axios"
import IssuesList from "./IssuesList"
import FixSuggestions from "./FixSuggestions"
import SidebarNav from "./SidebarNav"
import Breadcrumb from "./Breadcrumb"
import StatCard from "./StatCard"
import ExportDropdown from "./ExportDropdown"
import FixHistory from "./FixHistory"
import AIFixStrategyModal from "./AIFixStrategyModal"
import { API_ENDPOINTS } from "../config/api"

export default function ReportViewer({ scans, onBack, sidebarOpen = true }) {
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
  const [aiDirectFixLoading, setAiDirectFixLoading] = useState(false)
  const tabRefs = useRef([])
  const tabContainerRef = useRef(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)

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

  const fetchReportDetails = async (scanId) => {
    try {
      console.log("[v0] Fetching report details for:", scanId)
      const response = await axios.get(`/api/scan/${scanId}`)
      console.log("[v0] Received report data:", response.data)
      console.log("[v0] Results structure:", response.data.results)
      console.log("[v0] Results keys:", Object.keys(response.data.results || {}))
      console.log("[v0] Applied fixes from backend:", response.data.appliedFixes)
      setReportData(response.data)
    } catch (error) {
      console.error("[v0] Error fetching report:", error)
    } finally {
      setLoading(false)
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

  const refreshScanData = async () => {
    if (isRefreshing) {
      console.log("[v0] ReportViewer - Already refreshing, skipping duplicate call")
      return
    }

    setIsRefreshing(true)
    console.log("[v0] ReportViewer - Starting data refresh...")

    try {
      const currentScan = scans[selectedFileIndex]
      let scanId = currentScan.scanId || currentScan.id

      // Handle fixed file naming
      if (scanId && scanId.includes("_fixed_")) {
        const match = scanId.match(/^(scan_\d+_\d+_[^_]+)/)
        if (match) {
          scanId = match[1] + ".pdf"
        }
      }

      console.log("[v0] ReportViewer - Fetching completely fresh data for scanId:", scanId)

      await new Promise((resolve) => setTimeout(resolve, 2500))

      // Fetch with aggressive cache-busting
      const timestamp = Date.now()
      const response = await axios.get(`/api/scan/${scanId}`, {
        headers: {
          "Cache-Control": "no-cache, no-store, must-revalidate",
          Pragma: "no-cache",
          Expires: "0",
        },
        params: {
          t: timestamp,
          _: Math.random(),
          refresh: "true",
          bustCache: timestamp,
        },
      })

      console.log("[v0] ReportViewer - Received fresh data from backend")
      console.log("[v0] ReportViewer - New total issues:", response.data.summary?.totalIssues)
      console.log("[v0] ReportViewer - New compliance score:", response.data.summary?.complianceScore)
      console.log("[v0] ReportViewer - New fixes:", {
        automated: response.data.fixes?.automated?.length || 0,
        semiAutomated: response.data.fixes?.semiAutomated?.length || 0,
        manual: response.data.fixes?.manual?.length || 0,
      })

      const results = response.data.results || {}
      const totalIssues =
        (results.wcagIssues?.length || 0) +
        (results.pdfuaIssues?.length || 0) +
        (results.pdfaIssues?.length || 0) +
        (results.structureIssues?.length || 0)

      const highSeverity = Object.values(results)
        .flat()
        .filter((issue) => issue?.severity === "high" || issue?.severity === "critical").length

      const complianceScore = totalIssues === 0 ? 100 : Math.max(0, Math.round(100 - totalIssues * 2))

      console.log("[v0] ReportViewer - Recalculated stats:", { totalIssues, highSeverity, complianceScore })

      const newData = {
        ...response.data,
        summary: {
          totalIssues,
          highSeverity,
          complianceScore,
          ...response.data.summary,
        },
        results: results,
        fixes: response.data.fixes || { automated: [], semiAutomated: [], manual: [], estimatedTime: 0 },
        appliedFixes: response.data.appliedFixes || null,
      }

      setReportData(newData)
      setRefreshKey((prev) => prev + 1)

      console.log("[v0] ReportViewer - State updated successfully with fresh data")
      console.log("[v0] ReportViewer - New reportData:", {
        totalIssues: newData.summary.totalIssues,
        complianceScore: newData.summary.complianceScore,
        fixCounts: {
          automated: newData.fixes.automated.length,
          semiAutomated: newData.fixes.semiAutomated.length,
        },
      })
    } catch (error) {
      console.error("[v0] ReportViewer - Error refreshing scan data:", error)
      alert("Failed to refresh data. Please try again.")
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
      alert("Failed to get AI remediation strategy. Please try again.")
    } finally {
      setAiLoading(false)
    }
  }

  const handleAiDirectFix = async () => {
    setAiDirectFixLoading(true)
    try {
      const currentScan = scans[selectedFileIndex]
      const scanId = currentScan.scanId || currentScan.id

      console.log("[v0] Applying AI-powered direct fixes to:", scanId)

      const response = await axios.post(API_ENDPOINTS.aiApplyFixes(scanId))

      if (response.data.success) {
        console.log("[v0] AI fixes applied successfully:", response.data)

        if (response.data.newResults && response.data.newSummary) {
          await refreshScanData(response.data.newResults, response.data.newSummary)
        } else {
          await refreshScanData()
        }

        alert(
          `AI fixes applied successfully!\n\n` +
            `Fixes applied: ${response.data.successCount || 0}\n` +
            `New compliance score: ${response.data.newSummary?.complianceScore || 0}%`,
        )
      } else {
        throw new Error(response.data.error || "Failed to apply AI fixes")
      }
    } catch (error) {
      console.error("[v0] Error applying AI fixes:", error)
      const errorMessage = error.response?.data?.error || error.message || "Failed to apply AI fixes"
      alert(`Error: ${errorMessage}`)
    } finally {
      setAiDirectFixLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-lg text-gray-600 dark:text-gray-400">Loading report...</div>
      </div>
    )
  }

  if (!reportData) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-lg text-red-600 dark:text-red-400">Failed to load report</div>
      </div>
    )
  }

  const summary = reportData.summary || {
    totalIssues: 0,
    highSeverity: 0,
    complianceScore: 0,
  }

  const verapdfStatus = reportData?.verapdfStatus || {
    isActive: false,
    wcagCompliance: null,
    pdfuaCompliance: null,
    totalVeraPDFIssues: 0,
  }

  const breadcrumbItems = [{ label: "Home", onClick: onBack }, { label: "Report" }]

  return (
    <div className="flex overflow-x-hidden">
      <SidebarNav isOpen={sidebarOpen} />

      <div
        className={`flex-1 transition-all duration-300 ${sidebarOpen ? "ml-[240px]" : "ml-0"} p-4 bg-gray-50 dark:bg-gray-900 overflow-x-hidden`}
      >
        <div className="flex items-center justify-between mb-4">
          <Breadcrumb items={breadcrumbItems} />
          <div className="flex items-center gap-2">
            <button
              onClick={handleAiDirectFix}
              disabled={aiDirectFixLoading}
              className="px-3 py-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-lg transition-all flex items-center gap-2 shadow-md hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
              title="Apply AI-powered fixes directly to the PDF"
            >
              {aiDirectFixLoading ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                    />
                  </svg>
                  <span className="text-sm font-medium">Applying AI Fixes...</span>
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                    />
                  </svg>
                  <span className="text-sm font-medium">AI Direct Fix</span>
                </>
              )}
            </button>
            <button
              onClick={() => refreshScanData()}
              className="px-3 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
              title="Refresh report data"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              <span className="text-sm font-medium">Refresh</span>
            </button>
            <ExportDropdown scanId={reportData.scanId} filename={reportData.fileName || reportData.filename} />
          </div>
        </div>

        {scans.length > 1 && (
          <div className="mb-4 flex items-center gap-2">
            <button
              onClick={() => scrollTabs("left")}
              disabled={!canScrollLeft}
              className="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-sm"
              aria-label="Scroll tabs left"
            >
              ←
            </button>

            <div className="flex-1 relative min-w-0">
              <div className="absolute left-0 top-0 bottom-2 w-8 bg-gradient-to-r from-gray-50 dark:from-gray-900 to-transparent pointer-events-none z-10" />
              <div className="absolute right-0 top-0 bottom-2 w-8 bg-gradient-to-l from-gray-50 dark:from-gray-900 to-transparent pointer-events-none z-10" />

              <div ref={tabContainerRef} className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide scroll-smooth">
                {scans.map((scan, index) => (
                  <button
                    key={index}
                    ref={(el) => (tabRefs.current[index] = el)}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all whitespace-nowrap flex-shrink-0 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900 ${
                      selectedFileIndex === index
                        ? "bg-blue-600 text-white shadow-sm"
                        : "bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:border-blue-400"
                    }`}
                    onClick={() => setSelectedFileIndex(index)}
                    aria-label={`View report for ${scan.fileName || scan.filename}`}
                    aria-current={selectedFileIndex === index ? "page" : undefined}
                  >
                    <span className="text-base">📄</span>
                    <span className="font-medium">{scan.fileName || scan.filename}</span>
                    {scan.summary && (
                      <span
                        className={`px-1.5 py-0.5 rounded text-xs font-semibold ${
                          scan.summary.complianceScore >= 70
                            ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                            : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                        }`}
                      >
                        {scan.summary.complianceScore}%
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={() => scrollTabs("right")}
              disabled={!canScrollRight}
              className="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-sm"
              aria-label="Scroll tabs right"
            >
              →
            </button>
          </div>
        )}

        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">
              {reportData.fileName || reportData.filename}
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Scanned on {new Date(reportData.uploadDate || reportData.timestamp).toLocaleDateString()}
            </p>
            {reportData.appliedFixes && (
              <p className="text-xs text-green-600 dark:text-green-400 font-medium mt-1">
                ✓ {reportData.appliedFixes.successCount} fixes applied on{" "}
                {new Date(reportData.appliedFixes.timestamp).toLocaleDateString()}
              </p>
            )}
          </div>

          {verapdfStatus.isActive && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
              <svg className="w-4 h-4 text-blue-600 dark:text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-.723-.725 3.066 3.066 0 01-2.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="text-sm font-medium text-blue-700 dark:text-blue-300">veraPDF Validated</span>
            </div>
          )}
        </div>

        <div id="overview" className="mb-4" key={`overview-${refreshKey}`}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <StatCard
              label="Compliance Score"
              value={`${summary.complianceScore}%`}
              change={summary.complianceScore >= 70 ? 20 : -10}
            />
            <StatCard label="Total Issues" value={summary.totalIssues} change={-5} />
            <StatCard label="High Severity" value={summary.highSeverity} change={-3} />
          </div>

          {verapdfStatus.isActive && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
              <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-lg shadow-sm p-4 border border-blue-200 dark:border-blue-800">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-blue-700 dark:text-blue-300">WCAG 2.1 Compliance</p>
                    <p className="text-2xl font-bold text-blue-900 dark:text-blue-100 mt-1">
                      {verapdfStatus.wcagCompliance}%
                    </p>
                  </div>
                  <div className="w-12 h-12 bg-blue-200 dark:bg-blue-800 rounded-full flex items-center justify-center">
                    <svg
                      className="w-6 h-6 text-blue-600 dark:text-blue-300"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                      />
                    </svg>
                  </div>
                </div>
              </div>

              <div className="bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20 rounded-lg shadow-sm p-4 border border-purple-200 dark:border-purple-800">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-purple-700 dark:text-purple-300">PDF/UA Compliance</p>
                    <p className="text-2xl font-bold text-purple-900 dark:text-purple-100 mt-1">
                      {verapdfStatus.pdfuaCompliance}%
                    </p>
                  </div>
                  <div className="w-12 h-12 bg-purple-200 dark:bg-purple-800 rounded-full flex items-center justify-center">
                    <svg
                      className="w-6 h-6 text-purple-600 dark:text-purple-300"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                      />
                    </svg>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="mb-6">
          <FixHistory scanId={reportData.scanId} onRefresh={refreshScanData} />
        </div>

        <div id="fixes" className="mb-6" key={`fixes-${refreshKey}`}>
          <FixSuggestions
            scanId={reportData.scanId}
            fixes={reportData.fixes}
            filename={reportData.fileName || reportData.filename}
            onRefresh={refreshScanData}
          />
        </div>

        <div id="issues" className="mb-6" key={`issues-${refreshKey}`}>
          <IssuesList
            results={reportData.results}
            selectedCategory={selectedCategory}
            onCategorySelect={setSelectedCategory}
          />
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
