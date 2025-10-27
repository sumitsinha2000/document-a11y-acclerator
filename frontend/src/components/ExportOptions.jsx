"use client"

import axios from "axios"

export default function ExportOptions({ scanId, filename }) {
  const handleExportJSON = async () => {
    try {
      const response = await axios.get(`/api/export/${scanId}`)
      const dataStr = JSON.stringify(response.data, null, 2)
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
      const data = response.data
      let csv = "Issue Category,Severity,Description,Pages,Recommendation\n"

      Object.entries(data.results).forEach(([category, issues]) => {
        issues.forEach((issue) => {
          const pages = issue.pages ? issue.pages.join(";") : issue.page || "N/A"
          const row = [category, issue.severity, `"${issue.description}"`, pages, `"${issue.recommendation}"`].join(",")
          csv += row + "\n"
        })
      })

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
      const data = response.data

      let html = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Accessibility Report - ${filename}</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
    .container { max-width: 900px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; }
    h1 { color: #333; border-bottom: 2px solid #3b82f6; padding-bottom: 10px; }
    h2 { color: #555; margin-top: 20px; }
    .summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }
    .summary-card { background-color: #f0f4f8; padding: 15px; border-radius: 5px; text-align: center; }
    .summary-card .value { font-size: 24px; font-weight: bold; color: #3b82f6; }
    .summary-card .label { color: #666; font-size: 12px; }
    .issue-category { margin: 20px 0; }
    .issue-item { background-color: #f9f9f9; border-left: 4px solid #3b82f6; padding: 10px; margin: 10px 0; }
    .issue-item.high { border-left-color: #ef4444; }
    .issue-item.medium { border-left-color: #f59e0b; }
    .issue-item.low { border-left-color: #10b981; }
    .severity { display: inline-block; padding: 3px 8px; border-radius: 3px; font-size: 12px; font-weight: bold; }
    .severity.high { background-color: #fee2e2; color: #991b1b; }
    .severity.medium { background-color: #fef3c7; color: #92400e; }
    .severity.low { background-color: #dcfce7; color: #166534; }
    .recommendation { margin-top: 10px; padding: 10px; background-color: #eff6ff; border-left: 3px solid #3b82f6; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Accessibility Compliance Report</h1>
    <p><strong>Document:</strong> ${filename}</p>
    <p><strong>Scan Date:</strong> ${new Date(data.uploadDate).toLocaleString()}</p>
    
    <div class="summary">
      <div class="summary-card">
        <div class="value">${data.results ? Object.values(data.results).reduce((sum, arr) => sum + arr.length, 0) : 0}</div>
        <div class="label">Total Issues</div>
      </div>
      <div class="summary-card">
        <div class="value">${data.results ? Object.values(data.results).reduce((sum, arr) => sum + arr.filter((i) => i.severity === "high").length, 0) : 0}</div>
        <div class="label">High Severity</div>
      </div>
      <div class="summary-card">
        <div class="value">N/A</div>
        <div class="label">Compliance Score</div>
      </div>
    </div>
`

      Object.entries(data.results).forEach(([category, issues]) => {
        html += `<div class="issue-category"><h2>${category}</h2>`
        issues.forEach((issue) => {
          const pages = issue.pages ? issue.pages.join(", ") : issue.page || "N/A"
          html += `
    <div class="issue-item ${issue.severity}">
      <span class="severity ${issue.severity}">${issue.severity.toUpperCase()}</span>
      <p><strong>${issue.description}</strong></p>
      <p>Pages: ${pages}</p>
      <div class="recommendation">
        <strong>Recommendation:</strong> ${issue.recommendation}
      </div>
    </div>
`
        })
        html += `</div>`
      })

      html += `
  </div>
</body>
</html>
`

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
