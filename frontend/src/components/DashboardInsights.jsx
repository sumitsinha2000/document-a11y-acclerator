const CATEGORY_LABELS = {
  missingMetadata: "Metadata",
  untaggedContent: "Tagging",
  missingAltText: "Alt Text",
  poorContrast: "Contrast",
  missingLanguage: "Language",
  formIssues: "Forms",
  tableIssues: "Tables",
}

const STATUS_LABELS = {
  uploaded: "Waiting",
  unprocessed: "Unprocessed",
  processing: "Processing",
  processed: "Processed",
  completed: "Completed",
  fixed: "Fixed",
  failed: "Failed",
}

const severityPalette = {
  high: "bg-rose-500",
  medium: "bg-amber-500",
  low: "bg-emerald-500",
}

function ProgressItem({ label, value, total, colorClass, srLabel }) {
  const percent = total > 0 ? Math.round((value / total) * 100) : 0

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm text-slate-600 dark:text-slate-400">
        <span>{label}</span>
        <span aria-hidden="true">{value}</span>
      </div>
      <div className="h-2.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden relative">
        <span className="sr-only">
          {srLabel || `${label}: ${value} of ${total} (${percent}%)`}
        </span>
        <div
          className={`h-full ${colorClass}`}
          style={{ width: `${percent}%` }}
          aria-hidden="true"
        ></div>
      </div>
    </div>
  )
}

export function FileInsightPanel({ results, summary }) {
  const severityTotals = { high: 0, medium: 0, low: 0 }
  const categoryTotals = []
  let hasDetailedSeverity = false

  Object.entries(results || {}).forEach(([key, issues]) => {
    const count = Array.isArray(issues) ? issues.length : 0
    if (count === 0) {
      return
    }

    categoryTotals.push({
      key,
      label: CATEGORY_LABELS[key] || key.replace(/([A-Z])/g, " $1").trim(),
      count,
    })

    issues.forEach((issue) => {
      if (!issue || typeof issue !== "object") return
      const severity = (issue.severity || "").toLowerCase()
      if (severityTotals[severity] !== undefined) {
        severityTotals[severity] += 1
        hasDetailedSeverity = true
      }
    })
  })

  const totalIssues =
    typeof summary?.totalIssues === "number"
      ? summary.totalIssues
      : severityTotals.high + severityTotals.medium + severityTotals.low

  const sortedCategories = categoryTotals
    .sort((a, b) => b.count - a.count)
    .slice(0, 3)

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
          <dl className="mt-4 space-y-3" aria-label="Top issue categories with counts and percentages">
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

  const statusTotals = new Map()
  const issuesByFile = []

  scans.forEach((scan) => {
    const rawStatus = (scan?.status || "unknown").toLowerCase()
    const normalizedStatus = STATUS_LABELS[rawStatus] ? rawStatus : "unknown"
    statusTotals.set(normalizedStatus, (statusTotals.get(normalizedStatus) || 0) + 1)

    const totalIssues = scan?.summary?.totalIssues ?? scan?.initialSummary?.totalIssues ?? 0
    issuesByFile.push({
      filename: scan?.filename || scan?.scanId || "Unnamed file",
      totalIssues,
      compliance: scan?.summary?.complianceScore ?? null,
    })
  })

  const totalScans = scans.length

  const sortedStatuses = Array.from(statusTotals.entries())
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1])

  const topAttentionFiles = issuesByFile
    .filter((file) => typeof file.totalIssues === "number")
    .sort((a, b) => b.totalIssues - a.totalIssues)
    .slice(0, 3)

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {sortedStatuses.length > 0 && (
        <section className="bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white uppercase tracking-wide">
            Scan Progress
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

      {topAttentionFiles.length > 0 && (
        <section className="bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white uppercase tracking-wide">
            Highest Issue Files
          </h3>
          <ol className="mt-4 space-y-3 text-sm text-slate-600 dark:text-slate-300">
            {topAttentionFiles.map((file, index) => (
              <li key={`${file.filename}-${index}`} className="flex items-center justify-between">
                <div className="truncate pr-4">
                  <span className="text-slate-400 dark:text-slate-500 mr-2">#{index + 1}</span>
                  <span className="text-slate-900 dark:text-white font-medium truncate">
                    {file.filename}
                  </span>
                </div>
                <span className="text-slate-900 dark:text-white font-semibold">{file.totalIssues}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  )
}

export function GroupInsightPanel({ categoryTotals, severityTotals, statusCounts, totalFiles, totalIssues }) {
  const normalizedSeverity = severityTotals || {}
  const severityTotalCount =
    (normalizedSeverity.high || 0) + (normalizedSeverity.medium || 0) + (normalizedSeverity.low || 0)

  const categoryEntries = Object.entries(categoryTotals || {}).map(([key, count]) => ({
    key,
    label: CATEGORY_LABELS[key] || key.replace(/([A-Z])/g, " $1").trim(),
    count,
  }))
  const topCategories = categoryEntries.sort((a, b) => b.count - a.count).slice(0, 3)

  const statusEntries = Object.entries(statusCounts || {}).map(([key, count]) => ({
    key,
    label: STATUS_LABELS[key] || key.replace(/([A-Z])/g, " $1").trim(),
    count,
  }))
  const filteredStatuses = statusEntries.filter((entry) => entry.count > 0).sort((a, b) => b.count - a.count)
  const statusTotal = totalFiles || filteredStatuses.reduce((sum, entry) => sum + entry.count, 0)

  const hasSeverity = severityTotalCount > 0
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
            Total issues analysed: {totalIssues}. Severity counts are shown below.
          </p>
          <div className="mt-4 space-y-3">
            {["high", "medium", "low"].map((severity) => (
              <ProgressItem
                key={severity}
                label={`${severity[0].toUpperCase()}${severity.slice(1)}`}
                value={normalizedSeverity[severity] || 0}
                total={severityTotalCount}
                colorClass={severityPalette[severity]}
                srLabel={`Severity ${severity}: ${normalizedSeverity[severity] || 0} of ${severityTotalCount}`}
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
            Showing up to three categories with the highest number of issues across the group.
          </p>
          <dl className="mt-4 space-y-3" aria-label="Group top issue categories with counts and percentages">
            {topCategories.map((category) => {
              const percent = totalIssues > 0 ? Math.round((category.count / totalIssues) * 100) : 0
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
            {totalFiles || 0} files in this group. Status distribution is shown below.
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
