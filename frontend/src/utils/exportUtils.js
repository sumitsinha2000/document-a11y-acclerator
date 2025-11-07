const FIRST_NON_EMPTY_FIELDS = ["description", "message", "title", "summary", "detail"]

const isPresent = (value) => {
  if (value === null || value === undefined) {
    return false
  }

  if (Array.isArray(value)) {
    return value.length > 0
  }

  if (typeof value === "string") {
    return value.trim().length > 0
  }

  return true
}

export const getIssuePrimaryText = (issue) => {
  if (!issue) {
    return "Issue details unavailable"
  }

  for (const field of FIRST_NON_EMPTY_FIELDS) {
    if (isPresent(issue[field])) {
      return typeof issue[field] === "string" ? issue[field].trim() : issue[field]
    }
  }

  if (isPresent(issue.clause)) {
    return `Clause: ${issue.clause}`
  }

  return "Issue details unavailable"
}

export const getIssueClause = (issue) => {
  if (!issue || !isPresent(issue.clause)) {
    return ""
  }
  return typeof issue.clause === "string" ? issue.clause.trim() : issue.clause
}

export const getIssueRecommendation = (issue) => {
  if (!issue) {
    return ""
  }

  if (isPresent(issue.recommendation)) {
    return typeof issue.recommendation === "string" ? issue.recommendation.trim() : issue.recommendation
  }

  if (isPresent(issue.remediation)) {
    return typeof issue.remediation === "string" ? issue.remediation.trim() : issue.remediation
  }

  return ""
}

export const getRecommendationLabel = (issue) => {
  if (!issue) {
    return ""
  }

  if (isPresent(issue.recommendation)) {
    return "Recommendation"
  }

  if (isPresent(issue.remediation)) {
    return "Remediation"
  }

  return ""
}

export const getIssuePagesText = (issue) => {
  if (!issue) {
    return "N/A"
  }

  if (Array.isArray(issue.pages) && issue.pages.length > 0) {
    return issue.pages.join(", ")
  }

  if (isPresent(issue.page)) {
    return issue.page
  }

  if (isPresent(issue.location)) {
    return issue.location
  }

  return "N/A"
}

export const buildDescriptionWithClause = (issue) => {
  const parts = [getIssuePrimaryText(issue)]
  const clause = getIssueClause(issue)
  if (clause) {
    parts.push(`Clause: ${clause}`)
  }
  return parts.filter(isPresent).join(" | ")
}

export const escapeCsvValue = (value) => {
  if (value === null || value === undefined) {
    return '""'
  }
  const stringValue = String(value).replace(/"/g, '""')
  return `"${stringValue}"`
}

export const getIssueWcagCriteria = (issue) => {
  if (!issue) {
    return ""
  }

  if (isPresent(issue.wcagCriteria)) {
    return typeof issue.wcagCriteria === "string" ? issue.wcagCriteria.trim() : issue.wcagCriteria
  }

  if (isPresent(issue.criterion)) {
    const level = isPresent(issue.level) ? ` (Level ${String(issue.level).toUpperCase()})` : ""
    return `WCAG ${issue.criterion}${level}`
  }

  return ""
}

export const REPORT_GENERATOR = "Document A11y MVP"
export const DEFAULT_REPORT_LANGUAGE = "en-US"

const CATEGORY_LABELS = {
  missingMetadata: "Missing Metadata",
  untaggedContent: "Untagged Content",
  missingAltText: "Missing Alt Text",
  poorContrast: "Poor Contrast",
  missingLanguage: "Missing Language",
  formIssues: "Form Issues",
  tableIssues: "Table Issues",
  wcagIssues: "WCAG Issues",
  structureIssues: "Structure Issues",
  readingOrderIssues: "Reading Order Issues",
  pdfaIssues: "PDF/A Issues",
  pdfuaIssues: "PDF/UA Issues",
}

const ACRONYM_TOKENS = {
  wcag: "WCAG",
  pdf: "PDF",
  pdfa: "PDF/A",
  pdfua: "PDF/UA",
  a11y: "A11y",
  ai: "AI",
}

const toTitleCase = (word) => {
  if (!word) {
    return ""
  }

  const normalized = word.toLowerCase()
  if (ACRONYM_TOKENS[normalized]) {
    return ACRONYM_TOKENS[normalized]
  }

  return normalized.charAt(0).toUpperCase() + normalized.slice(1)
}

export const formatCategoryLabel = (key) => {
  if (!key || typeof key !== "string") {
    return ""
  }

  if (CATEGORY_LABELS[key]) {
    return CATEGORY_LABELS[key]
  }

  const withSpaces = key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()

  if (!withSpaces) {
    return key
  }

  return withSpaces
    .split(" ")
    .map((word) => {
      if (/^\d+(\.\d+)*$/.test(word)) {
        return word
      }
      return toTitleCase(word)
    })
    .join(" ")
}

export const getReportTitle = (filename) => {
  const safeName = filename || "Scanned Document"
  return `Accessibility Compliance Report - ${safeName}`
}

export const buildReportMetadata = ({ filename, scanId, summary }) => {
  const generatedAt = new Date()
  return {
    generator: REPORT_GENERATOR,
    generatedAt: generatedAt.toISOString(),
    generatedAtDisplay: generatedAt.toLocaleString(),
    document: filename || "Untitled Document",
    scanId: scanId || "",
    reportTitle: getReportTitle(filename),
    language: DEFAULT_REPORT_LANGUAGE,
    schemaVersion: "2024.05",
    totals: {
      totalIssues: summary?.totalIssues ?? null,
      highSeverity: summary?.highSeverity ?? null,
      complianceScore: summary?.complianceScore ?? null,
      wcagCompliance: summary?.wcagCompliance ?? null,
      pdfuaCompliance: summary?.pdfuaCompliance ?? null,
      pdfaCompliance: summary?.pdfaCompliance ?? null,
    },
  }
}

export const buildCategoryLabelMap = (results) => {
  if (!results || typeof results !== "object") {
    return {}
  }

  return Object.keys(results).reduce((acc, key) => {
    acc[key] = formatCategoryLabel(key)
    return acc
  }, {})
}

export const prepareExportContext = (data, fallbackFilename, fallbackScanId) => {
  const resolvedFilename = data?.filename || fallbackFilename || "Scanned Document"
  const summary = data?.summary || {}
  const metadata = buildReportMetadata({
    filename: resolvedFilename,
    scanId: data?.scanId || fallbackScanId || "",
    summary,
  })

  const results = data?.results && typeof data.results === "object" ? data.results : {}
  const categoryLabels = buildCategoryLabelMap(results)

  return {
    resolvedFilename,
    metadata,
    categoryLabels,
    results,
    summary,
  }
}

const buildMetadataRows = (metadata) => {
  if (!metadata) {
    return []
  }

  return [
    ["Report Title", metadata.reportTitle],
    ["Document", metadata.document],
    ["Scan ID", metadata.scanId || "N/A"],
    ["Generated On", metadata.generatedAtDisplay],
    ["Generator", metadata.generator],
  ]
}

export const buildJsonExportPayload = (data, metadata, categoryLabels) => {
  return {
    ...data,
    exportMetadata: {
      ...metadata,
      categoryLabels,
    },
  }
}

export const buildCsvContent = ({ results, metadata }) => {
  const safeResults = results && typeof results === "object" ? results : {}
  const metadataRows = buildMetadataRows(metadata)
  let csv = "Report Metadata\nField,Value\n"
  metadataRows.forEach((row) => {
    csv += `${row.map(escapeCsvValue).join(",")}\n`
  })
  csv += "\n"
  csv += "Issue Category,Severity,Description,Pages,Recommendation,WCAG Criteria\n"

  Object.entries(safeResults).forEach(([category, issues]) => {
    if (!Array.isArray(issues) || issues.length === 0) {
      return
    }
    const categoryLabel = formatCategoryLabel(category)
    issues.forEach((issue) => {
      const severity = (issue?.severity || "medium").toString()
      const severityDisplay = severity.charAt(0).toUpperCase() + severity.slice(1)
      const description = buildDescriptionWithClause(issue)
      const pages = getIssuePagesText(issue)
      const recommendation = getIssueRecommendation(issue)
      const wcagCriteria = getIssueWcagCriteria(issue)

      const row = [
        escapeCsvValue(categoryLabel),
        escapeCsvValue(severityDisplay),
        escapeCsvValue(description),
        escapeCsvValue(pages),
        escapeCsvValue(recommendation),
        escapeCsvValue(wcagCriteria),
      ].join(",")

      csv += `${row}\n`
    })
  })

  return csv
}

export const generateLegacyHtmlReport = (data, filename) => {
  const summary = data?.summary || {}
  const results = data?.results || {}
  const formatCategoryName = (key) => {
    if (!key) {
      return "Issue Details"
    }
    return key
      .replace(/([A-Z])/g, " $1")
      .replace(/[_-]+/g, " ")
      .replace(/\s+/g, " ")
      .trim()
  }

  let issuesHTML = ""
  Object.entries(results).forEach(([category, issues]) => {
    if (Array.isArray(issues) && issues.length > 0) {
      const readableCategory = formatCategoryName(category)
      const normalizedKey = (category || "issues").toString()
      const sectionId =
        `category-${normalizedKey.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}` || "category-issues"
      issuesHTML += `
          <section class="category-section" role="region" aria-labelledby="${sectionId}">
            <h3 id="${sectionId}">${readableCategory}</h3>
            <div class="issue-list" role="list" aria-label="${readableCategory} issues">
            ${issues
              .map((issue) => {
                const severityValue = (issue?.severity || "medium").toString().toLowerCase()
                const severityDisplay = severityValue.charAt(0).toUpperCase() + severityValue.slice(1)
                const description = getIssuePrimaryText(issue)
                const clause = getIssueClause(issue)
                const pages = getIssuePagesText(issue)
                const showPages = pages && pages !== "N/A"
                const recommendation = getIssueRecommendation(issue)
                const recommendationLabel = getRecommendationLabel(issue) || "Recommendation"
                const wcagCriteria = getIssueWcagCriteria(issue)

                return `
              <article class="issue-item ${severityValue}" role="listitem" aria-label="${severityDisplay} issue in ${readableCategory}">
                <div class="issue-header">
                  <span class="severity-badge ${severityValue}" aria-label="Severity ${severityDisplay}">${severityDisplay}</span>
                  <span class="issue-title">${description}</span>
                </div>
                <div class="issue-details">
                  ${showPages ? `<p><strong>Pages:</strong> ${pages}</p>` : ""}
                  ${clause ? `<p><strong>Clause:</strong> ${clause}</p>` : ""}
                  ${recommendation ? `<p><strong>${recommendationLabel}:</strong> ${recommendation}</p>` : ""}
                  ${wcagCriteria ? `<p><strong>WCAG Criteria:</strong> ${wcagCriteria}</p>` : ""}
                </div>
              </article>
            `
              })
              .join("")}
            </div>
          </section>
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
    .skip-link {
      position: absolute;
      left: -999px;
      top: auto;
      width: 1px;
      height: 1px;
      overflow: hidden;
    }
    .skip-link:focus {
      position: static;
      width: auto;
      height: auto;
      padding: 10px 16px;
      background: #4338ca;
      color: white;
      border-radius: 6px;
      margin-bottom: 10px;
      z-index: 1000;
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
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .summary-section {
      padding: 40px;
      background: #f8f9fa;
    }
    .summary-section h2,
    .issues-section h2 {
      font-size: 1.6em;
      color: #4f46e5;
      margin-bottom: 12px;
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
    .issues-section { padding: 40px; }
    .category-section { margin-bottom: 40px; }
    .category-section h3 {
      color: #4c1d95;
      font-size: 1.4em;
      margin-bottom: 16px;
      padding-bottom: 8px;
      border-bottom: 3px solid #d8b4fe;
    }
    .issue-list { display: flex; flex-direction: column; gap: 16px; }
    .issue-item {
      background: #f8f9fa;
      border-left: 4px solid #667eea;
      padding: 20px;
      margin: 15px 0;
      border-radius: 4px;
      transition: all 0.2s;
    }
    .no-issues {
      text-align: center;
      color: #28a745;
      font-size: 1.2em;
    }
    .issue-item:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
    .issue-item.critical { border-left-color: #dc3545; }
    .issue-item.high { border-left-color: #fd7e14; }
    .issue-item.medium { border-left-color: #ffc107; }
    .issue-item.low { border-left-color: #28a745; }
    .issue-item.error { border-left-color: #b91c1c; }
    .issue-item.warning { border-left-color: #f97316; }
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
    .severity-badge.error { background: #b91c1c; }
    .severity-badge.warning { background: #f97316; }
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
  <a href="#report-summary" class="skip-link">Skip to report content</a>
  <div class="container">
    <div class="header" role="banner">
      <h1>📄 Accessibility Compliance Report</h1>
      <p><strong>Document:</strong> ${filename}</p>
      <p><strong>Generated:</strong> ${new Date().toLocaleString()}</p>
    </div>

    <main id="report-content" role="main">
      <section class="summary-section" aria-labelledby="summary-heading">
        <h2 id="summary-heading">Summary</h2>
        <div class="summary-grid" role="list">
          <article class="summary-card" role="listitem">
            <h3>Compliance Score</h3>
            <div class="value" aria-label="Overall compliance score">${summary.complianceScore || 0}%</div>
          </article>
          <article class="summary-card" role="listitem">
            <h3>Total Issues</h3>
            <div class="value" aria-label="Total number of issues">${summary.totalIssues || 0}</div>
          </article>
          <article class="summary-card" role="listitem">
            <h3>High Severity</h3>
            <div class="value" aria-label="High severity issues">${summary.highSeverity || 0}</div>
          </article>
        </div>
      </section>

      <section class="issues-section" aria-labelledby="issues-heading">
        <h2 id="issues-heading">Issue Details</h2>
        <p class="sr-only">Each issue includes severity, description, and remediation guidance when available.</p>
        ${
          issuesHTML ||
          '<p class="no-issues" role="status" aria-live="polite">✅ No issues found! This document is fully compliant.</p>'
        }
      </section>
    </main>

    <div class="footer">
      <p>Generated by Document Accessibility Accelerator</p>
      <p>Report Date: ${new Date().toLocaleDateString()}</p>
    </div>
  </div>
</body>
</html>`
}
