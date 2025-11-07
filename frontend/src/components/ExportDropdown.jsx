"use client"

import { useState, useRef, useEffect, useId } from "react"
import axios from "axios"
import jsPDF from "jspdf"
import autoTable from "jspdf-autotable"
import { useNotification } from "../contexts/NotificationContext"
import {
  getIssuePrimaryText,
  getIssuePagesText,
  getIssueRecommendation,
  getIssueClause,
  getRecommendationLabel,
  getIssueWcagCriteria,
  formatCategoryLabel,
  prepareExportContext,
  buildCsvContent,
  generateLegacyHtmlReport,
  buildJsonExportPayload,
  REPORT_GENERATOR,
  DEFAULT_REPORT_LANGUAGE,
} from "../utils/exportUtils"

export default function ExportDropdown({ scanId, filename }) {
  const { showError } = useNotification()

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
      const response = await axios.get(`/api/export/${scanId}`)
      const data = response.data || {}
      const { resolvedFilename, metadata, categoryLabels, results } = prepareExportContext(
        data,
        filename,
        scanId,
      )

      if (format === "json") {
        const enhancedJson = buildJsonExportPayload(data, metadata, categoryLabels)
        const dataStr = JSON.stringify(enhancedJson, null, 2)
        const dataBlob = new Blob([dataStr], { type: "application/json" })
        downloadFile(dataBlob, `accessibility-report-${scanId}.json`)
      } else if (format === "csv") {
        const csv = buildCsvContent({ results, metadata })
        const dataBlob = new Blob([csv], { type: "text/csv" })
        downloadFile(dataBlob, `accessibility-report-${scanId}.csv`)
      } else if (format === "html") {
        const html = generateLegacyHtmlReport(data, resolvedFilename)
        const dataBlob = new Blob([html], { type: "text/html" })
        downloadFile(dataBlob, `accessibility-report-${scanId}.html`)
      } else if (format === "pdf") {
        generatePDFReport({
          data,
          filename: resolvedFilename,
          scanId,
          metadata,
          categoryLabels,
        })
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

  const generatePDFReport = ({ data, filename, scanId, metadata, categoryLabels = {} }) => {
    const doc = new jsPDF()
    const summary = data.summary || {}
    const results = data.results || {}
    const reportTitle = metadata?.reportTitle || `Accessibility Report - ${filename}`
    const generatorName = metadata?.generator || REPORT_GENERATOR
    const documentName = metadata?.document || filename
    const generatedOn = metadata?.generatedAtDisplay || new Date().toLocaleString()
    const scanIdentifier = metadata?.scanId || scanId || "N/A"
    const docLanguage = metadata?.language || DEFAULT_REPORT_LANGUAGE

    // Set document properties
    doc.setProperties({
      title: reportTitle,
      subject: "WCAG & PDF/UA accessibility compliance summary",
      author: generatorName,
      keywords: "accessibility, compliance, WCAG, PDF/UA",
      creator: generatorName,
    })
    if (typeof doc.setLanguage === "function") {
      doc.setLanguage(docLanguage)
    }

    // Header with gradient effect (simulated with colored rectangle)
    doc.setFillColor(102, 126, 234)
    doc.rect(0, 0, 210, 60, "F")

    // Title
    doc.setTextColor(255, 255, 255)
    doc.setFontSize(24)
    doc.setFont("helvetica", "bold")
    doc.text("Accessibility Compliance Report", 105, 28, { align: "center" })

    // Document details
    doc.setFontSize(11)
    doc.setFont("helvetica", "normal")
    doc.text(`Document: ${documentName}`, 105, 40, { align: "center" })
    doc.text(`Generated: ${generatedOn}`, 105, 48, { align: "center" })
    doc.text(`Scan ID: ${scanIdentifier}`, 105, 56, { align: "center" })

    // Reset text color for body
    doc.setTextColor(0, 0, 0)

    // Report metadata section
    let yPos = 72
    doc.setFontSize(16)
    doc.setFont("helvetica", "bold")
    doc.text("Report Metadata", 14, yPos)

    yPos += 6
    doc.setFontSize(10)
    doc.setFont("helvetica", "normal")

    const metadataRows = [
      ["Report Title", reportTitle],
      ["Document", documentName],
      ["Scan ID", scanIdentifier],
      ["Generated On", generatedOn],
      ["Generator", generatorName],
    ]

    autoTable(doc, {
      startY: yPos,
      head: [["Field", "Value"]],
      body: metadataRows,
      theme: "grid",
      headStyles: { fillColor: [102, 126, 234], textColor: 255, fontStyle: "bold" },
      styles: { fontSize: 10, cellPadding: 4 },
      columnStyles: {
        0: { fontStyle: "bold", cellWidth: 55 },
        1: { cellWidth: 120 },
      },
    })

    yPos = (doc.lastAutoTable?.finalY || yPos) + 10

    // Summary section
    doc.setFontSize(16)
    doc.setFont("helvetica", "bold")
    doc.text("Summary", 14, yPos)

    yPos += 8
    doc.setFontSize(11)
    doc.setFont("helvetica", "normal")

    // Summary boxes
    const summaryData = [
      [
        "Overall Compliance Score",
        typeof summary.complianceScore === "number" ? `${summary.complianceScore}%` : "N/A",
      ],
      [
        "WCAG Compliance",
        typeof summary.wcagCompliance === "number" ? `${summary.wcagCompliance}%` : "N/A",
      ],
      [
        "PDF/UA Compliance",
        typeof summary.pdfuaCompliance === "number" ? `${summary.pdfuaCompliance}%` : "N/A",
      ],
      [
        "PDF/A Compliance",
        typeof summary.pdfaCompliance === "number" ? `${summary.pdfaCompliance}%` : "N/A",
      ],
      ["Total Issues", `${summary.totalIssues || 0}`],
      ["High Severity Issues", `${summary.highSeverity || 0}`],
    ]

    autoTable(doc, {
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

    yPos = (doc.lastAutoTable?.finalY || yPos) + 15

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
        const readableCategory = categoryLabels[category] || formatCategoryLabel(category)
        doc.text(readableCategory, 14, yPos)
        doc.setTextColor(0, 0, 0)

        yPos += 8

        // Issues table
        const issuesData = issues.map((issue) => {
          const severityValue = (issue.severity || "medium").toString().toLowerCase()
          const severityDisplay = severityValue.charAt(0).toUpperCase() + severityValue.slice(1)
          const description = getIssuePrimaryText(issue)
          const clause = getIssueClause(issue)
          const descriptionWithClause = clause ? `${description} (Clause: ${clause})` : description
          const pages = getIssuePagesText(issue)
          const recommendation = getIssueRecommendation(issue)
          const recommendationLabel = getRecommendationLabel(issue)
          const wcagCriteria = getIssueWcagCriteria(issue) || "N/A"
          const recommendationCell = recommendation
            ? `${recommendationLabel || "Recommendation"}: ${recommendation}`
            : "N/A"

          return [severityDisplay, descriptionWithClause, wcagCriteria, pages, recommendationCell]
        })

        autoTable(doc, {
          startY: yPos,
          head: [["Severity", "Description", "WCAG Criteria", "Pages", "Recommendation"]],
          body: issuesData,
          theme: "striped",
          headStyles: { fillColor: [102, 126, 234], textColor: 255, fontStyle: "bold" },
          styles: { fontSize: 9, cellPadding: 4 },
          columnStyles: {
            0: { cellWidth: 22, fontStyle: "bold" },
            1: { cellWidth: 55 },
            2: { cellWidth: 38 },
            3: { cellWidth: 22 },
            4: { cellWidth: 53 },
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

        yPos = (doc.lastAutoTable?.finalY || yPos) + 12
      }
    })

    // Footer on last page
    const pageCount = doc.internal.getNumberOfPages()
    for (let i = 1; i <= pageCount; i++) {
      doc.setPage(i)
      doc.setFontSize(8)
      doc.setTextColor(128, 128, 128)
      doc.text(`Page ${i} of ${pageCount}`, 105, 285, { align: "center" })
      doc.text(`Generated by ${generatorName}`, 105, 290, { align: "center" })
    }

    // Save the PDF
    doc.save(`accessibility-report-${scanId}.pdf`)
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
          aria-hidden="true"
          focusable="false"
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
