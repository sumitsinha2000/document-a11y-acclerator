"use client"

import axios from "axios"
import {
  prepareExportContext,
  buildJsonExportPayload,
  buildCsvContent,
  generateLegacyHtmlReport,
} from "../utils/exportUtils"

export default function ExportOptions({ scanId, filename }) {
  const handleExportJSON = async () => {
    try {
      const response = await axios.get(`/api/export/${scanId}`)
      const data = response.data || {}
      const { metadata, categoryLabels } = prepareExportContext(data, filename, scanId)
      const enhancedJson = buildJsonExportPayload(data, metadata, categoryLabels)
      const dataStr = JSON.stringify(enhancedJson, null, 2)
      const dataBlob = new Blob([dataStr], { type: "application/json" })
      const url = URL.createObjectURL(dataBlob)
      const link = document.createElement("a")
      link.href = url
      link.download = `accessibility-report-${scanId}.json`
      link.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error("Error exporting JSON:", error)
    }
  }

  const handleExportCSV = async () => {
    try {
      const response = await axios.get(`/api/export/${scanId}`)
      const data = response.data || {}
      const { metadata, results } = prepareExportContext(data, filename, scanId)
      const csv = buildCsvContent({ results, metadata })

      const dataBlob = new Blob([csv], { type: "text/csv" })
      const url = URL.createObjectURL(dataBlob)
      const link = document.createElement("a")
      link.href = url
      link.download = `accessibility-report-${scanId}.csv`
      link.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error("Error exporting CSV:", error)
    }
  }

  const handleExportHTML = async () => {
    try {
      const response = await axios.get(`/api/export/${scanId}`)
      const data = response.data || {}
      const { resolvedFilename } = prepareExportContext(data, filename, scanId)
      const html = generateLegacyHtmlReport(data, resolvedFilename)

      const dataBlob = new Blob([html], { type: "text/html" })
      const url = URL.createObjectURL(dataBlob)
      const link = document.createElement("a")
      link.href = url
      link.download = `accessibility-report-${scanId}.html`
      link.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error("Error exporting HTML:", error)
    }
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6">
      <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Export Report</h3>
      <div className="flex flex-wrap gap-3">
        <button
          className="flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors shadow-sm"
          onClick={handleExportJSON}
        >
          <span className="text-xl">📄</span>
          <span>JSON</span>
        </button>
        <button
          className="flex items-center gap-2 px-6 py-3 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors shadow-sm"
          onClick={handleExportCSV}
        >
          <span className="text-xl">📊</span>
          <span>CSV</span>
        </button>
        <button
          className="flex items-center gap-2 px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg transition-colors shadow-sm"
          onClick={handleExportHTML}
        >
          <span className="text-xl">🌐</span>
          <span>HTML</span>
        </button>
      </div>
    </div>
  )
}
