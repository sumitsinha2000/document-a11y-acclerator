import { useState, useRef, useEffect, useId } from "react"
import axios from "axios"
import { useNotification } from "../contexts/NotificationContext"
import API_BASE_URL from "../config/api"
import {
  buildDescriptionWithClause,
  escapeCsvValue,
  getIssuePagesText,
  getIssueRecommendation,
  getIssueWcagCriteria,
  UTF8_BOM,
} from "../utils/exportUtils"

export default function ExportDropdown({ scanId, filename, disabled = false }) {
  const { showError } = useNotification()
  const CSV_MIME = "text/csv;charset=UTF-8"

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

  useEffect(() => {
    if (disabled) {
      setIsOpen(false)
    }
  }, [disabled])

  const handleExport = async (format) => {
    if (disabled) {
      return
    }

    setIsOpen(false)

    try {
      if (format === "pdf") {
        const tzOffset = new Date().getTimezoneOffset()
        const response = await axios.get(
          `${API_BASE_URL}/api/export/${scanId}?format=pdf&tzOffset=${tzOffset}`,
          { responseType: "blob" }
        )
        const blob = new Blob([response.data], { type: "application/pdf" })
        const downloadName = `accessibility-report-${scanId}.pdf`
        downloadFile(blob, downloadName)
        return
      }

      const response = await axios.get(`${API_BASE_URL}/api/export/${scanId}`)
      const data = response.data || {}

      if (format === "csv") {
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

  const baseButtonClasses =
    "flex items-center gap-2 px-3 py-2 text-sm font-semibold rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-violet-500 focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-slate-900"
  const enabledClasses =
    "text-white bg-violet-600 hover:bg-violet-700 dark:bg-violet-500 dark:hover:bg-violet-400"
  const disabledClasses = "text-slate-500 bg-slate-200 cursor-not-allowed dark:bg-slate-700 dark:text-slate-400"

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        id={buttonId}
        onClick={() => {
          if (!disabled) {
            setIsOpen((prev) => !prev)
          }
        }}
        disabled={disabled}
        aria-disabled={disabled}
        type="button"
        className={`${baseButtonClasses} ${disabled ? disabledClasses : enabledClasses}`}
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
            onClick={() => handleExport("csv")}
            role="menuitem"
            className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700 dark:focus:bg-slate-700"
          >
            <span className="text-lg">📊</span>
            <span>Export as CSV</span>
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
