"use client"

import { useState, useRef, useEffect } from "react"
import axios from "axios"
import jsPDF from "jspdf"
import "jspdf-autotable"
import { useNotification } from "../contexts/NotificationContext"

export default function ExportDropdown({ scanId, filename }) {
  const { showError } = useNotification()

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
      } else if (format === "pdf") {
        generatePDFReport(data, filename, scanId)
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

  const generatePDFReport = (data, filename, scanId) => {
    const doc = new jsPDF()
    const summary = data.summary || {}
    const results = data.results || {}

    // Set document properties
    doc.setProperties({
      title: `Accessibility Report - ${filename}`,
      subject: "Document Accessibility Compliance Report",
      author: "Document Accessibility Accelerator",
      keywords: "accessibility, compliance, WCAG",
      creator: "Document Accessibility Accelerator",
    })

    // Header with gradient effect (simulated with colored rectangle)
    doc.setFillColor(102, 126, 234)
    doc.rect(0, 0, 210, 45, "F")

    // Title
    doc.setTextColor(255, 255, 255)
    doc.setFontSize(24)
    doc.setFont("helvetica", "bold")
    doc.text("Accessibility Compliance Report", 105, 20, { align: "center" })

    // Document name
    doc.setFontSize(12)
    doc.setFont("helvetica", "normal")
    doc.text(`Document: ${filename}`, 105, 30, { align: "center" })
    doc.text(`Generated: ${new Date().toLocaleString()}`, 105, 37, { align: "center" })

    // Reset text color for body
    doc.setTextColor(0, 0, 0)

    // Summary section
    let yPos = 55
    doc.setFontSize(16)
    doc.setFont("helvetica", "bold")
    doc.text("Summary", 14, yPos)

    yPos += 10
    doc.setFontSize(11)
    doc.setFont("helvetica", "normal")

    // Summary boxes
    const summaryData = [
      ["Compliance Score", `${summary.complianceScore || 0}%`],
      ["Total Issues", `${summary.totalIssues || 0}`],
      ["High Severity Issues", `${summary.highSeverity || 0}`],
    ]

    doc.autoTable({
      startY: yPos,
      head: [["Metric", "Value"]],
      body: summaryData,
      theme: "grid",
      headStyles: { fillColor: [102, 126, 234], textColor: 255, fontStyle: "bold" },
      styles: { fontSize: 10, cellPadding: 5 },
      columnStyles: {
        0: { fontStyle: "bold", cellWidth: 100 },
        1: { halign: "center", cellWidth: 80 },
      },
    })

    yPos = doc.lastAutoTable.finalY + 15

    // Issues by category
    Object.entries(results).forEach(([category, issues]) => {
      if (Array.isArray(issues) && issues.length > 0) {
        // Check if we need a new page
        if (yPos > 250) {
          doc.addPage()
          yPos = 20
        }

        // Category header
        doc.setFontSize(14)
        doc.setFont("helvetica", "bold")
        doc.setTextColor(102, 126, 234)
        doc.text(category.replace(/([A-Z])/g, " $1").trim(), 14, yPos)
        doc.setTextColor(0, 0, 0)

        yPos += 8

        // Issues table
        const issuesData = issues.map((issue) => {
          const pages = issue.pages ? issue.pages.join(", ") : issue.page || "N/A"
          return [
            issue.severity || "Medium",
            issue.description || issue.title || "Issue",
            pages,
            issue.recommendation || "N/A",
          ]
        })

        doc.autoTable({
          startY: yPos,
          head: [["Severity", "Description", "Pages", "Recommendation"]],
          body: issuesData,
          theme: "striped",
          headStyles: { fillColor: [102, 126, 234], textColor: 255, fontStyle: "bold" },
          styles: { fontSize: 9, cellPadding: 4 },
          columnStyles: {
            0: { cellWidth: 25, fontStyle: "bold" },
            1: { cellWidth: 60 },
            2: { cellWidth: 30 },
            3: { cellWidth: 65 },
          },
          didDrawCell: (data) => {
            // Color code severity
            if (data.column.index === 0 && data.section === "body") {
              const severity = data.cell.raw.toLowerCase()
              let color = [255, 193, 7] // medium - yellow
              if (severity === "critical") color = [220, 53, 69]
              else if (severity === "high") color = [253, 126, 20]
              else if (severity === "low") color = [40, 167, 69]

              doc.setFillColor(...color)
              doc.rect(data.cell.x, data.cell.y, data.cell.width, data.cell.height, "F")
              doc.setTextColor(severity === "medium" ? 0 : 255)
              doc.setFontSize(9)
              doc.setFont("helvetica", "bold")
              doc.text(data.cell.raw, data.cell.x + data.cell.width / 2, data.cell.y + data.cell.height / 2, {
                align: "center",
                baseline: "middle",
              })
              doc.setTextColor(0, 0, 0)
            }
          },
        })

        yPos = doc.lastAutoTable.finalY + 12
      }
    })

    // Footer on last page
    const pageCount = doc.internal.getNumberOfPages()
    for (let i = 1; i <= pageCount; i++) {
      doc.setPage(i)
      doc.setFontSize(8)
      doc.setTextColor(128, 128, 128)
      doc.text(`Page ${i} of ${pageCount}`, 105, 285, { align: "center" })
      doc.text("Generated by Document Accessibility Accelerator", 105, 290, { align: "center" })
    }

    // Save the PDF
    doc.save(`accessibility-report-${scanId}.pdf`)
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
              .map(
                (issue) => `
              <div class="issue-item ${issue.severity || "medium"}">
                <div class="issue-header">
                  <span class="severity-badge ${issue.severity || "medium"}">${issue.severity || "Medium"}</span>
                  <span class="issue-title">${issue.description || issue.title || "Issue"}</span>
                </div>
                <div class="issue-details">
                  ${issue.page ? `<p><strong>Page:</strong> ${issue.page}</p>` : ""}
                  ${issue.pages ? `<p><strong>Pages:</strong> ${issue.pages.join(", ")}</p>` : ""}
                  ${issue.recommendation ? `<p><strong>Recommendation:</strong> ${issue.recommendation}</p>` : ""}
                  ${issue.wcagCriteria ? `<p><strong>WCAG Criteria:</strong> ${issue.wcagCriteria}</p>` : ""}
                </div>
              </div>
            `,
              )
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
    }
    .container { 
      max-width: 1200px;
      margin: 0 auto;
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
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 20px;
      padding: 40px;
      background: #f8f9fa;
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
  <div class="container">
    <div class="header">
      <h1>📄 Accessibility Compliance Report</h1>
      <p><strong>Document:</strong> ${filename}</p>
      <p><strong>Generated:</strong> ${new Date().toLocaleString()}</p>
    </div>

    <div class="summary">
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

    <div class="content">
      ${issuesHTML || '<p style="text-align: center; color: #28a745; font-size: 1.2em;">✅ No issues found! This document is fully compliant.</p>'}
    </div>

    <div class="footer">
      <p>Generated by Document Accessibility Accelerator</p>
      <p>Report Date: ${new Date().toLocaleDateString()}</p>
    </div>
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

          <button
            onClick={() => handleExport("pdf")}
            className="w-full px-4 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-3"
          >
            <span className="text-lg">📕</span>
            <span className="text-sm text-gray-700 dark:text-gray-300">Export as PDF</span>
          </button>
        </div>
      )}
    </div>
  )
}
