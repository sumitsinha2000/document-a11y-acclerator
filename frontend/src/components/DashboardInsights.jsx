import { FILE_STATUS_LABELS_MAP, normalizeStatusCode, resolveEntityStatus } from "../utils/statuses"

const CATEGORY_LABELS = {
  metadata: "Metadata",
  missingMetadata: "Metadata",
  language: "Language",
  missingLanguage: "Language",
  "alt-text": "Alt Text",
  missingAltText: "Alt Text",
  contrast: "Contrast",
  poorContrast: "Contrast",
  tagging: "Tagging",
  untaggedContent: "Tagging",
  table: "Tables",
  tableIssues: "Tables",
  forms: "Forms",
  formIssues: "Forms",
  links: "Link Purpose",
  linkIssues: "Link Purpose",
  structure: "Structure",
  structureIssues: "Structure",
  "reading-order": "Reading Order",
  readingOrderIssues: "Reading Order",
  pdfua: "PDF/UA",
  wcag: "WCAG",
  other: "Other",
}

const STATUS_LABELS = {
  ...FILE_STATUS_LABELS_MAP,
  failed: "Failed",
}

const severityPalette = {
  high: "bg-rose-500",
  medium: "bg-amber-500",
  low: "bg-emerald-500",
}

const DEFAULT_CATEGORY_KEY = "other"

const normalizeCategoryKey = (value) => {
  if (value === null || value === undefined) {
    return DEFAULT_CATEGORY_KEY
  }
  const text = String(value).trim()
  if (!text) {
    return DEFAULT_CATEGORY_KEY
  }
  if (CATEGORY_LABELS[text]) {
    return text
  }
  const lowered = text.toLowerCase()
  if (CATEGORY_LABELS[lowered]) {
    return lowered
  }
  return text
}

const normalizeSeverityKey = (severity) => {
  const normalized = String(severity || "").trim().toLowerCase()
  if (normalized === "medium") {
    return "medium"
  }
  if (normalized === "low") {
    return "low"
  }
  if (normalized) {
    return "high"
  }
  return "low"
}

const normalizeIssueCount = (value, fallback = 0) => {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : fallback
  }
  if (value === null || value === undefined) {
    return fallback
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

const incrementCategoryTotal = (categoryTotals, key, amount = 1) => {
  const normalized = normalizeCategoryKey(key)
  categoryTotals[normalized] = (categoryTotals[normalized] || 0) + amount
}

const toTitleCase = (value) =>
  value
    .split(/\s+/)
    .map((word) => (word ? `${word[0].toUpperCase()}${word.slice(1)}` : ""))
    .join(" ")
    .trim()

const formatCategoryLabel = (key) => {
  const normalized = normalizeCategoryKey(key)
  if (CATEGORY_LABELS[normalized]) {
    return CATEGORY_LABELS[normalized]
  }
  const spaced = normalized
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[-_]/g, " ")
    .trim()
  if (!spaced) {
    return CATEGORY_LABELS[DEFAULT_CATEGORY_KEY]
  }
  return toTitleCase(spaced)
}

const buildIssueIdentity = (issue, index) => {
  if (!issue || typeof issue !== "object") {
    return `issue-${index}`
  }
  if (issue.issueId) {
    return issue.issueId
  }
  const parts = []
  const fields = ["category", "criterion", "clause", "description"]
  fields.forEach((field) => {
    if (issue[field]) {
      parts.push(String(issue[field]).trim().toLowerCase())
    }
  })
  if (Array.isArray(issue.pages) && issue.pages.length) {
    parts.push(issue.pages.map((page) => String(page)).join(","))
  } else if (issue.page) {
    parts.push(`p${issue.page}`)
  }
  return parts.length ? parts.join("|") : `issue-${index}`
}

const extractCanonicalIssues = (results) => {
  if (!results || typeof results !== "object") {
    return []
  }
  const canonical = results.issues
  if (!Array.isArray(canonical) || canonical.length === 0) {
    return []
  }
  const seen = new Set()
  const deduped = []
  canonical.forEach((issue, index) => {
    if (!issue || typeof issue !== "object") {
      return
    }
    const identity = buildIssueIdentity(issue, index)
    if (seen.has(identity)) {
      return
    }
    seen.add(identity)
    deduped.push(issue)
  })
  return deduped
}

const accumulateIssueStats = (issues, severityTotals, categoryTotals) => {
  issues.forEach((issue) => {
    if (!issue || typeof issue !== "object") {
      severityTotals.low += 1
      incrementCategoryTotal(categoryTotals, DEFAULT_CATEGORY_KEY)
      return
    }
    incrementCategoryTotal(
      categoryTotals,
      issue.category || issue.rawSource || issue.bucket || DEFAULT_CATEGORY_KEY,
    )
    const severity = normalizeSeverityKey(issue.severity)
    severityTotals[severity] = (severityTotals[severity] || 0) + 1
  })
}

function collectBatchIssueData(scans = []) {
  const severityTotals = { high: 0, medium: 0, low: 0 }
  const categoryTotals = {}
  let remainingIssues = 0

  scans.forEach((scan) => {
    const scanResults = scan?.results
    const canonicalIssues = extractCanonicalIssues(scanResults)
    if (canonicalIssues.length > 0) {
      accumulateIssueStats(canonicalIssues, severityTotals, categoryTotals)
    } else if (scanResults && typeof scanResults === "object") {
      Object.entries(scanResults).forEach(([key, issues]) => {
        if (key === "issues" || !Array.isArray(issues) || issues.length === 0) {
          return
        }
        incrementCategoryTotal(categoryTotals, key, issues.length)
        issues.forEach((issue) => {
          const severity = normalizeSeverityKey(issue?.severity)
          severityTotals[severity] = (severityTotals[severity] || 0) + 1
        })
      })
    }

    const summary = scan?.summary || {}
    const initialSummary = scan?.initialSummary || {}
    const remainingValue =
      summary.remainingIssues ??
      summary.issuesRemaining ??
      summary.totalIssues ??
      initialSummary.remainingIssues ??
      initialSummary.issuesRemaining ??
      initialSummary.totalIssues ??
      0
    remainingIssues += normalizeIssueCount(remainingValue)
  })

  return { severityTotals, categoryTotals, remainingIssues }
}

function ProgressItem({ label, value, total, colorClass, srLabel }) {
  const percent = total > 0 ? Math.round((value / total) * 100) : 0

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm text-slate-600 dark:text-slate-400">
        <span>{label}</span>
        <span>{value}</span>
      </div>
      <div
        className="h-2.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden relative"
        role="progressbar"
        aria-label={srLabel || `${label}: ${value} of ${total} (${percent}%)`}
        aria-valuemin={0}
        aria-valuemax={total || 0}
        aria-valuenow={value}
      >
        <span className="sr-only">
          {srLabel || `${label}: ${value} of ${total} (${percent}%)`}
        </span>
        <div className={`h-full ${colorClass}`} style={{ width: `${percent}%` }}></div>
      </div>
    </div>
  )
}

export function FileInsightPanel({ results, summary }) {
  const severityTotals = { high: 0, medium: 0, low: 0 }
  const categoryTotals = {}
  const canonicalIssues = extractCanonicalIssues(results)

  if (canonicalIssues.length > 0) {
    accumulateIssueStats(canonicalIssues, severityTotals, categoryTotals)
  } else {
    Object.entries(results || {}).forEach(([key, issues]) => {
      if (key === "issues" || !Array.isArray(issues) || issues.length === 0) {
        return
      }

      incrementCategoryTotal(categoryTotals, key, issues.length)

      issues.forEach((issue) => {
        const severity = normalizeSeverityKey(issue?.severity)
        severityTotals[severity] = (severityTotals[severity] || 0) + 1
      })
    })
  }

  const categoryEntries = Object.entries(categoryTotals).map(([key, count]) => ({
    key,
    label: formatCategoryLabel(key),
    count,
  }))

  const summaryTotalIssues =
    typeof summary?.totalIssues === "number" ? summary.totalIssues : null
  const baseSeveritySum =
    severityTotals.high + severityTotals.medium + severityTotals.low
  let normalizedSeveritySum = baseSeveritySum

  if (summaryTotalIssues !== null && summaryTotalIssues > normalizedSeveritySum) {
    severityTotals.low += summaryTotalIssues - normalizedSeveritySum
    normalizedSeveritySum = summaryTotalIssues
  }

  const totalIssues = summaryTotalIssues ?? normalizedSeveritySum
  const hasDetailedSeverity = normalizedSeveritySum > 0

  const sortedCategories = categoryEntries.sort((a, b) => b.count - a.count).slice(0, 3)

  const showSeverity = totalIssues > 0 && hasDetailedSeverity
  const showCategories = sortedCategories.length > 0

  if (!showSeverity && !showCategories) {
    return null
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {showSeverity && (
        <section className="bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white uppercase tracking-wide">
            Severity Breakdown
          </h3>
          <p className="sr-only">
            High severity: {severityTotals.high}, Medium severity: {severityTotals.medium}, Low severity:{" "}
            {severityTotals.low}.
          </p>
          <div className="mt-4 space-y-3">
            {["high", "medium", "low"].map((severity) => (
              <ProgressItem
                key={severity}
                label={`${severity[0].toUpperCase()}${severity.slice(1)}`}
                value={severityTotals[severity]}
                total={totalIssues}
                colorClass={severityPalette[severity]}
                srLabel={`Severity ${severity}: ${severityTotals[severity]} of ${totalIssues}`}
              />
            ))}
          </div>
        </section>
      )}

      {showCategories && (
        <section className="bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white uppercase tracking-wide">
            Top Issue Categories
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Showing up to three categories with the highest number of issues.
          </p>
          <dl className="mt-4 space-y-3">
            {sortedCategories.map((category) => {
              const percent =
                totalIssues > 0 ? Math.round((category.count / totalIssues) * 100) : 0
              return (
                <div key={category.key} className="flex items-center justify-between text-sm">
                  <dt className="text-slate-600 dark:text-slate-300">{category.label}</dt>
                  <dd className="text-slate-900 dark:text-white font-medium">
                    {category.count} issues
                    <span className="ml-2 text-xs text-slate-500 dark:text-slate-400">
                      ({percent}%)
                    </span>
                  </dd>
                </div>
              )
            })}
          </dl>
        </section>
      )}
    </div>
  )
}

export function BatchInsightPanel({ scans }) {
  if (!Array.isArray(scans) || scans.length === 0) {
    return null
  }

  const hasScannedFiles = scans.some((scan) => resolveEntityStatus(scan).code !== "uploaded")
  const statusTotals = new Map()
  const {
    severityTotals,
    categoryTotals,
    remainingIssues: totalRemainingIssues,
  } = collectBatchIssueData(scans)
  const resolvedRemainingIssues = normalizeIssueCount(totalRemainingIssues)

  scans.forEach((scan) => {
    const { code } = resolveEntityStatus(scan)
    statusTotals.set(code, (statusTotals.get(code) || 0) + 1)

  })

  const totalScans = scans.length

  const sortedStatuses = Array.from(statusTotals.entries())
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1])

  const progressHeading = totalScans === 1 ? "File Status" : "Files Status"

  let normalizedSeverityCount =
    severityTotals.high + severityTotals.medium + severityTotals.low
  if (resolvedRemainingIssues > normalizedSeverityCount) {
    severityTotals.low += resolvedRemainingIssues - normalizedSeverityCount
    normalizedSeverityCount =
      severityTotals.high + severityTotals.medium + severityTotals.low
  }
  const severityDisplayTotal =
    resolvedRemainingIssues > 0 ? resolvedRemainingIssues : normalizedSeverityCount
  const severityInsightLabel =
    resolvedRemainingIssues > 0 ? "Remaining issues" : "Issues analysed"
  const hasSeverity = normalizedSeverityCount > 0 || resolvedRemainingIssues > 0
  const categoryEntries = Object.entries(categoryTotals || {}).map(([key, count]) => ({
    key,
    label: formatCategoryLabel(key),
    count,
  }))
  const topCategories = categoryEntries.sort((a, b) => b.count - a.count).slice(0, 3)
  const hasCategories = topCategories.length > 0

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {hasSeverity && (
        <section className="bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white uppercase tracking-wide">
            Severity Overview
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            {severityInsightLabel}: {severityDisplayTotal}. Severity counts are shown below.
          </p>
          <div className="mt-4 space-y-3">
            {["high", "medium", "low"].map((severity) => (
              <ProgressItem
                key={severity}
                label={`${severity[0].toUpperCase()}${severity.slice(1)}`}
                value={severityTotals[severity]}
                total={severityDisplayTotal}
                colorClass={severityPalette[severity]}
                srLabel={`Severity ${severity}: ${severityTotals[severity]} of ${severityDisplayTotal}`}
              />
            ))}
          </div>
        </section>
      )}

      {hasCategories && (
        <section className="bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white uppercase tracking-wide">
            Top Issue Categories
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Showing up to three categories with the highest issue counts across this folder.
          </p>
          <dl className="mt-4 space-y-3">
            {topCategories.map((category) => {
              const percent =
                severityDisplayTotal > 0
                  ? Math.round((category.count / severityDisplayTotal) * 100)
                  : 0
              return (
                <div key={category.key} className="flex items-center justify-between text-sm">
                  <dt className="text-slate-600 dark:text-slate-300">{category.label}</dt>
                  <dd className="text-slate-900 dark:text-white font-medium">
                    {category.count} issues<span className="ml-2 text-xs text-slate-500 dark:text-slate-400">({percent}%)</span>
                  </dd>
                </div>
              )
            })}
          </dl>
        </section>
      )}

      {sortedStatuses.length > 0 && (
        <section className="bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white uppercase tracking-wide">
            {progressHeading}
          </h3>
          <div className="mt-4 space-y-3">
            {sortedStatuses.map(([statusKey, count]) => {
              const label = STATUS_LABELS[statusKey] || "Other"
              return (
                <ProgressItem
                  key={statusKey}
                  label={label}
                  value={count}
                  total={totalScans}
                  colorClass="bg-violet-500"
                  srLabel={`Status ${label}: ${count} of ${totalScans}`}
                />
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}

export function GroupInsightPanel({
  categoryTotals,
  severityTotals,
  statusCounts,
  totalFiles,
  totalIssues,
  remainingIssues,
}) {
  const normalizedSeverity = severityTotals || {}
  let severityBreakdown = {
    high: normalizeIssueCount(normalizedSeverity.high),
    medium: normalizeIssueCount(normalizedSeverity.medium),
    low: normalizeIssueCount(normalizedSeverity.low),
  }
  let severityTotalCount = severityBreakdown.high + severityBreakdown.medium + severityBreakdown.low
  const totalIssuesValue = normalizeIssueCount(totalIssues)
  const resolvedRemainingIssues = normalizeIssueCount(remainingIssues, totalIssuesValue)
  if (resolvedRemainingIssues > 0) {
    if (severityTotalCount === 0) {
      severityBreakdown = { high: 0, medium: 0, low: resolvedRemainingIssues }
      severityTotalCount = resolvedRemainingIssues
    } else if (resolvedRemainingIssues !== severityTotalCount) {
      const scaled = { high: 0, medium: 0, low: 0 }
      let remainingScale = resolvedRemainingIssues
      const severityKeys = ["high", "medium", "low"]
      severityKeys.forEach((key, index) => {
        if (index === severityKeys.length - 1) {
          scaled[key] = Math.max(0, remainingScale)
          return
        }
        const rawValue = severityBreakdown[key]
        if (!rawValue || severityTotalCount === 0) {
          scaled[key] = 0
          return
        }
        const scaledValue = Math.round((rawValue / severityTotalCount) * resolvedRemainingIssues)
        const clampedValue = Math.max(0, Math.min(remainingScale, scaledValue))
        scaled[key] = clampedValue
        remainingScale -= clampedValue
      })
      severityBreakdown = scaled
      severityTotalCount = resolvedRemainingIssues
    }
  } else if (resolvedRemainingIssues === 0 && severityTotalCount === 0) {
    severityBreakdown = { high: 0, medium: 0, low: 0 }
  }
  const severityDisplayTotal =
    resolvedRemainingIssues > 0 ? resolvedRemainingIssues : severityTotalCount
  const severityInsightLabel =
    resolvedRemainingIssues > 0 ? "Remaining issues" : "Issues analysed"

  const categoryEntries = Object.entries(categoryTotals || {}).map(([key, count]) => ({
    key,
    label: formatCategoryLabel(key),
    count,
  }))
  const topCategories = categoryEntries.sort((a, b) => b.count - a.count).slice(0, 3)

  const aggregatedStatusCounts = Object.entries(statusCounts || {}).reduce((acc, [key, count]) => {
    const code = normalizeStatusCode(key)
    acc[code] = (acc[code] || 0) + count
    return acc
  }, {})

  const statusEntries = Object.entries(aggregatedStatusCounts).map(([key, count]) => ({
    key,
    label: STATUS_LABELS[key] || key.replace(/([A-Z])/g, " $1").trim(),
    count,
  }))
  const filteredStatuses = statusEntries.filter((entry) => entry.count > 0).sort((a, b) => b.count - a.count)
  const statusTotal = totalFiles || filteredStatuses.reduce((sum, entry) => sum + entry.count, 0)

  const hasSeverity = severityDisplayTotal > 0
  const hasCategories = topCategories.length > 0
  const hasStatuses = filteredStatuses.length > 0

  if (!hasSeverity && !hasCategories && !hasStatuses) {
    return null
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {hasSeverity && (
        <section className="bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white uppercase tracking-wide">
            Severity Overview
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            {severityInsightLabel}: {severityDisplayTotal}. Severity counts are shown below.
          </p>
          <div className="mt-4 space-y-3">
            {["high", "medium", "low"].map((severity) => (
              <ProgressItem
                key={severity}
                label={`${severity[0].toUpperCase()}${severity.slice(1)}`}
                value={severityBreakdown[severity] || 0}
                total={severityDisplayTotal}
                colorClass={severityPalette[severity]}
                srLabel={`Severity ${severity}: ${severityBreakdown[severity] || 0} of ${severityDisplayTotal}`}
              />
            ))}
          </div>
        </section>
      )}

      {hasCategories && (
        <section className="bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white uppercase tracking-wide">
            Top Issue Categories
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Showing up to three categories with the highest number of issues across the project.
          </p>
          <dl className="mt-4 space-y-3">
            {topCategories.map((category) => {
              const percent =
                totalIssuesValue > 0 ? Math.round((category.count / totalIssuesValue) * 100) : 0
              return (
                <div key={category.key} className="flex items-center justify-between text-sm">
                  <dt className="text-slate-600 dark:text-slate-300">{category.label}</dt>
                  <dd className="text-slate-900 dark:text-white font-medium">
                    {category.count} issues<span className="ml-2 text-xs text-slate-500 dark:text-slate-400">({percent}%)</span>
                  </dd>
                </div>
              )
            })}
          </dl>
        </section>
      )}

      {hasStatuses && (
        <section className="bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white uppercase tracking-wide">
            File Status Overview
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            {totalFiles || 0} files in this project. Status distribution is shown below.
          </p>
          <div className="mt-4 space-y-3">
            {filteredStatuses.map((status) => (
              <ProgressItem
                key={status.key}
                label={status.label}
                value={status.count}
                total={statusTotal}
                colorClass="bg-indigo-500"
                srLabel={`Status ${status.label}: ${status.count} of ${statusTotal}`}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
