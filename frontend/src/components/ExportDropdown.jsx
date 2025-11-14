import { useState, useRef, useEffect, useId } from "react"
import axios from "axios"
import { useNotification } from "../contexts/NotificationContext"
import API_BASE_URL from "../config/api"
import {
  buildDescriptionWithClause,
  escapeCsvValue,
  getIssuePrimaryText,
  getIssuePagesText,
  getIssueRecommendation,
  getIssueClause,
  getRecommendationLabel,
  getIssueWcagCriteria,
  UTF8_BOM,
} from "../utils/exportUtils"

export default function ExportDropdown({ scanId, filename }) {
  const { showError } = useNotification()
  const JSON_MIME = "application/json;charset=UTF-8"
  const CSV_MIME = "text/csv;charset=UTF-8"
  const HTML_MIME = "text/html;charset=UTF-8"

  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef(null)
  const dropdownId = useId()
  const menuId = `${dropdownId}-menu`
  const buttonId = `${dropdownId}-button`

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === "Escape") {
        setIsOpen(false)
      }
    }

    document.addEventListener("keydown", handleEscape)
    return () => document.removeEventListener("keydown", handleEscape)
  }, [])

  const handleExport = async (format) => {
    setIsOpen(false)

    try {
      if (format === "pdf") {
        const response = await axios.get(
          `${API_BASE_URL}/api/export/${scanId}?format=pdf`,
          { responseType: "blob" }
        )
        const blob = new Blob([response.data], { type: "application/pdf" })
        const downloadName = `accessibility-report-${scanId}.pdf`
        downloadFile(blob, downloadName)
        return
      }

      const response = await axios.get(`${API_BASE_URL}/api/export/${scanId}`)
      const data = response.data || {}

      if (format === "json") {
        const dataStr = JSON.stringify(data, null, 2)
        const dataBlob = new Blob([dataStr], { type: JSON_MIME })
        downloadFile(dataBlob, `accessibility-report-${scanId}.json`)
      } else if (format === "csv") {
        let csv = `${UTF8_BOM}Issue Category,Severity,Description,Pages,Recommendation,WCAG Criteria\n`
        const results = data.results || {}
        Object.entries(results).forEach(([category, issues]) => {
          issues.forEach((issue) => {
            const severity = (issue.severity || "medium").toString()
            const description = buildDescriptionWithClause(issue)
            const pages = getIssuePagesText(issue)
            const recommendation = getIssueRecommendation(issue)
            const wcagCriteria = getIssueWcagCriteria(issue)

            const row = [
              escapeCsvValue(category),
              escapeCsvValue(severity),
              escapeCsvValue(description),
              escapeCsvValue(pages),
              escapeCsvValue(recommendation),
              escapeCsvValue(wcagCriteria),
            ].join(",")

            csv += row + "\n"
          })
        })
        const dataBlob = new Blob([csv], { type: CSV_MIME })
        downloadFile(dataBlob, `accessibility-report-${scanId}.csv`)
      } else if (format === "html") {
        const html = generateHTMLReport(data, filename)
        const dataBlob = new Blob([html], { type: HTML_MIME })
        downloadFile(dataBlob, `accessibility-report-${scanId}.html`)
      }
    } catch (error) {
      console.error(`Error exporting ${format}:`, error)
      showError(`Failed to export report: ${error.response?.data?.error || error.message}`)
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
    const summary = data.summary || {}
    const results = data.results || {}

    let issuesHTML = ""
    Object.entries(results).forEach(([category, issues]) => {
      if (Array.isArray(issues) && issues.length > 0) {
        issuesHTML += `
          <div class="category-section">
            <h2>${category.replace(/([A-Z])/g, " $1").trim()}</h2>
            ${issues
              .map((issue) => {
                const severityValue = (issue.severity || "medium").toString().toLowerCase()
                const severityDisplay = severityValue.charAt(0).toUpperCase() + severityValue.slice(1)
                const description = getIssuePrimaryText(issue)
                const clause = getIssueClause(issue)
                const pages = getIssuePagesText(issue)
                const showPages = pages && pages !== "N/A"
                const recommendation = getIssueRecommendation(issue)
                const recommendationLabel = getRecommendationLabel(issue) || "Recommendation"
                const wcagCriteria = getIssueWcagCriteria(issue)

                return `
              <div class="issue-item ${severityValue}">
                <div class="issue-header">
                  <span class="severity-badge ${severityValue}">${severityDisplay}</span>
                  <span class="issue-title">${description}</span>
                </div>
                <div class="issue-details">
                  ${showPages ? `<p><strong>Pages:</strong> ${pages}</p>` : ""}
                  ${clause ? `<p><strong>Clause:</strong> ${clause}</p>` : ""}
                  ${recommendation ? `<p><strong>${recommendationLabel}:</strong> ${recommendation}</p>` : ""}
                  ${wcagCriteria ? `<p><strong>WCAG Criteria:</strong> ${wcagCriteria}</p>` : ""}
                </div>
              </div>
            `
              })
              .join("")}
          </div>
        `
      }
    })

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Accessibility Report - ${filename}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      line-height: 1.6;
      color: #333;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      padding: 20px;
      min-height: 100vh;
      display: flex;
      justify-content: center;
    }
    .report-main {
      width: 100%;
      max-width: 1200px;
    }
    .report-card { 
      background: white;
      border-radius: 12px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3);
      overflow: hidden;
    }
    .header {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 40px;
      text-align: center;
    }
    .header h1 { font-size: 2.5em; margin-bottom: 10px; }
    .header p { font-size: 1.1em; opacity: 0.9; }
    .summary {
      padding: 40px;
      background: #f8f9fa;
    }
    .summary-heading {
      font-size: 2em;
      font-weight: 700;
      color: #4c51bf;
      margin-bottom: 25px;
      text-align: center;
    }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 20px;
    }
    .summary-card {
      background: white;
      padding: 25px;
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
      text-align: center;
      transition: transform 0.2s;
    }
    .summary-card:hover { transform: translateY(-5px); }
    .summary-card h3 { color: #666; font-size: 0.9em; text-transform: uppercase; margin-bottom: 10px; }
    .summary-card .value { font-size: 2.5em; font-weight: bold; color: #667eea; }
    .content { padding: 40px; }
    .category-section { margin-bottom: 40px; }
    .category-section h2 {
      color: #667eea;
      font-size: 1.8em;
      margin-bottom: 20px;
      padding-bottom: 10px;
      border-bottom: 3px solid #667eea;
    }
    .issue-item {
      background: #f8f9fa;
      border-left: 4px solid #667eea;
      padding: 20px;
      margin: 15px 0;
      border-radius: 4px;
      transition: all 0.2s;
    }
    .issue-item:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
    .issue-item.critical { border-left-color: #dc3545; }
    .issue-item.high { border-left-color: #fd7e14; }
    .issue-item.medium { border-left-color: #ffc107; }
    .issue-item.low { border-left-color: #28a745; }
    .issue-header {
      display: flex;
      align-items: center;
      gap: 15px;
      margin-bottom: 10px;
    }
    .severity-badge {
      display: inline-block;
      padding: 4px 12px;
      border-radius: 12px;
      font-size: 0.75em;
      font-weight: bold;
      text-transform: uppercase;
      color: white;
    }
    .severity-badge.critical { background: #dc3545; }
    .severity-badge.high { background: #fd7e14; }
    .severity-badge.medium { background: #ffc107; color: #333; }
    .severity-badge.low { background: #28a745; }
    .issue-title { font-weight: 600; font-size: 1.1em; color: #333; }
    .issue-details { margin-top: 10px; color: #666; }
    .issue-details p { margin: 5px 0; }
    .footer {
      background: #f8f9fa;
      padding: 30px;
      text-align: center;
      color: #666;
      border-top: 1px solid #dee2e6;
    }
    @media print {
      body { background: white; padding: 0; }
      .container { box-shadow: none; }
      .summary-card:hover, .issue-item:hover { transform: none; }
    }
  </style>
</head>
<body>
  <main class="report-main" role="main">
    <div class="report-card">
      <div class="header">
        <h1>Accessibility Compliance Report</h1>
        <p><strong>Document:</strong> ${filename}</p>
        <p><strong>Generated:</strong> ${new Date().toLocaleString()}</p>
      </div>

      <div class="summary">
        <h2 class="summary-heading">Core Metrics</h2>
        <div class="summary-grid">
          <div class="summary-card">
            <h3>Compliance Score</h3>
            <div class="value">${summary.complianceScore || 0}%</div>
          </div>
          <div class="summary-card">
            <h3>Total Issues</h3>
            <div class="value">${summary.totalIssues || 0}</div>
          </div>
          <div class="summary-card">
            <h3>High Severity</h3>
            <div class="value">${summary.highSeverity || 0}</div>
          </div>
        </div>
      </div>

      <div class="content">
        ${issuesHTML || '<p style="text-align: center; color: #28a745; font-size: 1.2em;">✅ No issues found! This document is fully compliant.</p>'}
      </div>

      <div class="footer">
        <p>Generated by Document Accessibility Accelerator</p>
        <p>Report Date: ${new Date().toLocaleDateString()}</p>
      </div>
    </div>
  </main>
</body>
</html>`
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        id={buttonId}
        onClick={() => setIsOpen(!isOpen)}
        type="button"
        className="flex items-center gap-2 px-5 py-3 text-base font-semibold text-white bg-violet-600 rounded-lg shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-violet-500 focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-slate-900 hover:bg-violet-700 dark:bg-violet-500 dark:hover:bg-violet-400"
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls={isOpen ? menuId : undefined}
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
        <div
          id={menuId}
          role="menu"
          aria-labelledby={buttonId}
          className="absolute right-0 z-50 mt-2 w-56 rounded-lg border border-slate-200 bg-white py-2 shadow-xl dark:border-slate-700 dark:bg-slate-800"
        >
          <div className="px-4 py-2 border-b border-slate-200 dark:border-slate-700">
            <div className="text-sm font-semibold text-slate-900 dark:text-white">Export Report</div>
          </div>

          <button
            onClick={() => handleExport("json")}
            role="menuitem"
            className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700 dark:focus:bg-slate-700"
          >
            <span className="text-lg">📄</span>
            <span>Export as JSON</span>
          </button>

          <button
            onClick={() => handleExport("csv")}
            role="menuitem"
            className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700 dark:focus:bg-slate-700"
          >
            <span className="text-lg">📊</span>
            <span>Export as CSV</span>
          </button>

          <button
            onClick={() => handleExport("html")}
            role="menuitem"
            className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700 dark:focus:bg-slate-700"
          >
            <span className="text-lg">🌐</span>
            <span>Export as HTML</span>
          </button>

          <button
            onClick={() => handleExport("pdf")}
            role="menuitem"
            className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700 dark:focus:bg-slate-700"
          >
            <span className="text-lg">📕</span>
            <span>Export as PDF</span>
          </button>
        </div>
      )}
    </div>
  )
}
