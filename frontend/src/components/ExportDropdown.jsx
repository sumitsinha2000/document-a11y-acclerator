"use client"

import { useState, useRef, useEffect } from "react"
import axios from "axios"

export default function ExportDropdown({ scanId, filename }) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef(null)

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const handleExport = async (format) => {
    setIsOpen(false)

    try {
      const response = await axios.get(`/api/export/${scanId}`)
      const data = response.data

      if (format === "json") {
        const dataStr = JSON.stringify(data, null, 2)
        const dataBlob = new Blob([dataStr], { type: "application/json" })
        downloadFile(dataBlob, `accessibility-report-${scanId}.json`)
      } else if (format === "csv") {
        let csv = "Issue Category,Severity,Description,Pages,Recommendation\n"
        Object.entries(data.results).forEach(([category, issues]) => {
          issues.forEach((issue) => {
            const pages = issue.pages ? issue.pages.join(";") : issue.page || "N/A"
            const row = [category, issue.severity, `"${issue.description}"`, pages, `"${issue.recommendation}"`].join(
              ",",
            )
            csv += row + "\n"
          })
        })
        const dataBlob = new Blob([csv], { type: "text/csv" })
        downloadFile(dataBlob, `accessibility-report-${scanId}.csv`)
      } else if (format === "html") {
        const html = generateHTMLReport(data, filename)
        const dataBlob = new Blob([html], { type: "text/html" })
        downloadFile(dataBlob, `accessibility-report-${scanId}.html`)
      }
    } catch (error) {
      console.error(`Error exporting ${format}:`, error)
      alert(`Failed to export report: ${error.response?.data?.error || error.message}`)
    }
  }

  const downloadFile = (blob, filename) => {
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  }

  const generateHTMLReport = (data, filename) => {
    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Accessibility Report - ${filename}</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
    .container { max-width: 900px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; }
    h1 { color: #333; border-bottom: 2px solid #3b82f6; padding-bottom: 10px; }
    .summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }
    .summary-card { background-color: #f0f4f8; padding: 15px; border-radius: 5px; text-align: center; }
    .issue-item { background-color: #f9f9f9; border-left: 4px solid #3b82f6; padding: 10px; margin: 10px 0; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Accessibility Compliance Report</h1>
    <p><strong>Document:</strong> ${filename}</p>
    <p><strong>Scan Date:</strong> ${new Date(data.uploadDate).toLocaleString()}</p>
  </div>
</body>
</html>`
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-sm font-medium text-gray-700 dark:text-gray-300"
        aria-label="Export options"
      >
        <span>Export</span>
        <svg
          className={`w-4 h-4 transition-transform ${isOpen ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-2 z-50">
          <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-700">
            <div className="text-sm font-semibold text-gray-900 dark:text-white">Export Report</div>
          </div>

          <button
            onClick={() => handleExport("json")}
            className="w-full px-4 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-3"
          >
            <span className="text-lg">📄</span>
            <span className="text-sm text-gray-700 dark:text-gray-300">Export as JSON</span>
          </button>

          <button
            onClick={() => handleExport("csv")}
            className="w-full px-4 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-3"
          >
            <span className="text-lg">📊</span>
            <span className="text-sm text-gray-700 dark:text-gray-300">Export as CSV</span>
          </button>

          <button
            onClick={() => handleExport("html")}
            className="w-full px-4 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-3"
          >
            <span className="text-lg">🌐</span>
            <span className="text-sm text-gray-700 dark:text-gray-300">Export as HTML</span>
          </button>
        </div>
      )}
    </div>
  )
}
