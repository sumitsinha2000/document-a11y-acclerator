"use client"

import { useState, useEffect, useRef } from "react"
import axios from "axios"
import IssuesList from "./IssuesList"
import IssueStats from "./IssueStats"
import FixSuggestions from "./FixSuggestions"
import SidebarNav from "./SidebarNav"
import Breadcrumb from "./Breadcrumb"
import StatCard from "./StatCard"
import ExportDropdown from "./ExportDropdown"
import FixHistory from "./FixHistory"

export default function ReportViewer({ scans, onBack, sidebarOpen = true }) {
  const [selectedFileIndex, setSelectedFileIndex] = useState(0)
  const [reportData, setReportData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedCategory, setSelectedCategory] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const tabRefs = useRef([])
  const tabContainerRef = useRef(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)

  useEffect(() => {
    const currentScan = scans[selectedFileIndex]
    console.log("[v0] ReportViewer - Current scan data:", currentScan)
    console.log("[v0] ReportViewer - Scan has fixes:", currentScan.fixes)
    console.log("[v0] ReportViewer - Number of fixes:", currentScan.fixes?.length)

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

  const refreshScanData = async (newSummary = null, newResults = null) => {
    const currentScan = scans[selectedFileIndex]
    let scanId = currentScan.scanId || currentScan.id

    if (scanId && scanId.includes("_fixed_")) {
      const match = scanId.match(/^(scan_\d+_\d+_[^_]+)/)
      if (match) {
        scanId = match[1] + ".pdf"
      }
    }

    console.log("[v0] ReportViewer - Starting refresh for scanId:", scanId)
    console.log("[v0] ReportViewer - New summary provided:", newSummary)
    console.log("[v0] ReportViewer - New results provided:", newResults)
    console.log("[v0] ReportViewer - Current reportData before refresh:", reportData)

    if (newSummary && newResults) {
      console.log("[v0] ReportViewer - Using provided data directly (no fetch needed)")

      const newData = {
        ...reportData,
        summary: newSummary,
        results: newResults,
        // Regenerate fixes based on new results
        fixes: reportData.fixes || { automated: [], semiAutomated: [], manual: [], estimatedTime: 0 },
      }

      setReportData(newData)
      setRefreshKey((prev) => {
        const newKey = prev + 1
        console.log("[v0] ReportViewer - Refresh key updated:", prev, "->", newKey)
        return newKey
      })

      console.log("[v0] ReportViewer - State updated successfully with provided data")
      return
    }

    if (scanId) {
      try {
        console.log("[v0] ReportViewer - Fetching updated scan data from backend...")
        await new Promise((resolve) => setTimeout(resolve, 800))

        const timestamp = Date.now()
        const response = await axios.get(`/api/scan/${scanId}`, {
          headers: {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            Pragma: "no-cache",
            Expires: "0",
          },
          params: {
            t: timestamp,
            _: Math.random(), // Additional cache buster
          },
        })

        console.log("[v0] ReportViewer - Received updated data:", response.data)
        console.log("[v0] ReportViewer - New summary:", response.data.summary)
        console.log("[v0] ReportViewer - New fixes:", response.data.fixes)
        console.log("[v0] ReportViewer - New results:", response.data.results)

        const newData = {
          ...response.data,
          summary: response.data.summary || { totalIssues: 0, highSeverity: 0, complianceScore: 0 },
          results: response.data.results || {},
          fixes: response.data.fixes || { automated: [], semiAutomated: [], manual: [], estimatedTime: 0 },
        }

        setReportData(newData)
        setRefreshKey((prev) => {
          const newKey = prev + 1
          console.log("[v0] ReportViewer - Refresh key updated:", prev, "->", newKey)
          return newKey
        })

        console.log("[v0] ReportViewer - State updated successfully from fetch")

        await new Promise((resolve) => setTimeout(resolve, 100))

        console.log("[v0] ReportViewer - Refresh complete")
      } catch (error) {
        console.error("[v0] ReportViewer - Error refreshing scan data:", error)
        console.error("[v0] ReportViewer - Failed scanId:", scanId)
        console.error("[v0] ReportViewer - Error response:", error.response?.data)
      }
    } else {
      console.error("[v0] ReportViewer - No valid scan ID found for refresh")
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

  const breadcrumbItems = [{ label: "Home", onClick: onBack }, { label: "Report" }]

  return (
    <div className="flex overflow-x-hidden">
      <SidebarNav isOpen={sidebarOpen} />

      <div
        className={`flex-1 transition-all duration-300 ${sidebarOpen ? "ml-[240px]" : "ml-0"} p-4 bg-gray-50 dark:bg-gray-900 overflow-x-hidden`}
      >
        <div className="flex items-center justify-between mb-4">
          <Breadcrumb items={breadcrumbItems} />
          <ExportDropdown scanId={reportData.scanId} filename={reportData.fileName || reportData.filename} />
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

        <div className="mb-3">
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">
            {reportData.fileName || reportData.filename}
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Scanned on {new Date(reportData.uploadDate || reportData.timestamp).toLocaleDateString()}
          </p>
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
        </div>

        <div className="mb-6">
          <FixHistory scanId={reportData.scanId} onRefresh={refreshScanData} />
        </div>

        <div id="stats" className="mb-6" key={`stats-${refreshKey}`}>
          <IssueStats results={reportData.results} />
        </div>

        <div id="issues" className="mb-6" key={`issues-${refreshKey}`}>
          <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-3">Accessibility Issues</h3>
          <IssuesList
            results={reportData.results}
            selectedCategory={selectedCategory}
            onSelectCategory={setSelectedCategory}
          />
        </div>

        <div id="fixes" className="mb-6" key={`fixes-${refreshKey}`}>
          <FixSuggestions
            scanId={reportData.scanId}
            fixes={reportData.fixes}
            filename={reportData.fileName || reportData.filename}
            onRefresh={refreshScanData}
          />
        </div>
      </div>
    </div>
  )
}
