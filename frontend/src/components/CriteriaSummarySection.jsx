import { useMemo, useState } from "react"
import { getIssuePrimaryText, getIssuePagesText } from "../utils/exportUtils"

const STATUS_META = {
  supports: {
    label: "Supports",
    badgeClass: "border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-900/20 dark:text-emerald-200",
    dotClass: "bg-emerald-500",
    meaning: "Fully meets requirement",
    usage: "No issues",
  },
  partiallySupports: {
    label: "Partially Supports",
    badgeClass:
      "border border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/40 dark:bg-amber-900/20 dark:text-amber-200",
    dotClass: "bg-amber-500",
    meaning: "Some parts supported, some fail",
    usage: "Minor or partial issues",
  },
  doesNotSupport: {
    label: "Does Not Support",
    badgeClass:
      "border border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/40 dark:bg-rose-900/20 dark:text-rose-200",
    dotClass: "bg-rose-500",
    meaning: "Fails requirement",
    usage: "Major accessibility barriers",
  },
  notApplicable: {
    label: "Not Applicable",
    badgeClass:
      "border border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-600 dark:bg-slate-900/40 dark:text-slate-200",
    dotClass: "bg-slate-500",
    meaning: "Requirement doesn’t apply",
    usage: "Feature not present",
  },
  notEvaluated: {
    label: "Not Evaluated",
    badgeClass:
      "border border-slate-200 bg-white text-slate-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-400",
    dotClass: "bg-slate-500",
    meaning: "Criterion was not tested",
    usage: "Rarely used, discouraged",
  },
}

const DEFAULT_STATUS_ORDER = ["supports", "partiallySupports", "doesNotSupport", "notApplicable", "notEvaluated"]

const SEVERITY_LABEL = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
}

const SEVERITY_CLASSES = {
  critical:
    "border border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/40 dark:bg-rose-900/20 dark:text-rose-200",
  high: "border border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/40 dark:bg-rose-900/20 dark:text-rose-200",
  medium:
    "border border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/40 dark:bg-amber-900/20 dark:text-amber-200",
  low: "border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-900/20 dark:text-emerald-200",
  default:
    "border border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700/60 dark:bg-slate-900/40 dark:text-slate-200",
}

const formatSeverity = (severity) => {
  if (!severity) return null
  const normalized = String(severity).toLowerCase()
  return SEVERITY_LABEL[normalized] || severity
}

const getSeverityClass = (severity) => {
  if (!severity) return SEVERITY_CLASSES.default
  const normalized = String(severity).toLowerCase()
  return SEVERITY_CLASSES[normalized] || SEVERITY_CLASSES.default
}

export default function CriteriaSummarySection({
  title,
  subtitle,
  data,
  emptyMessage = "No criteria data available.",
  sectionId,
}) {
  const [isCollapsed, setIsCollapsed] = useState(true)
  const [expanded, setExpanded] = useState([])

  const items = data?.items || []
  const totalIssues = items.reduce((sum, criterion) => {
    if (Array.isArray(criterion.issues)) {
      return sum + criterion.issues.length
    }
    if (typeof criterion.issueCount === "number") {
      return sum + criterion.issueCount
    }
    return sum
  }, 0)

  const expandedSet = useMemo(() => new Set(expanded), [expanded])

  if (!data || items.length === 0) {
    return (
      <section className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm p-6">
        <header className="flex items-center justify-between gap-3">
          <div>
            <p className="text-lg font-semibold text-slate-900 dark:text-white">{title}</p>
            {subtitle && <p className="text-sm text-slate-500 dark:text-slate-300">{subtitle}</p>}
          </div>
        </header>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-4">{emptyMessage}</p>
      </section>
    )
  }

  const toggleCriterion = (code) => {
    setExpanded((prev) => (expandedSet.has(code) ? prev.filter((item) => item !== code) : [...prev, code]))
  }

  return (
    <section
      id={sectionId}
      className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm p-6 space-y-6"
    >
      <header className="flex items-center justify-between gap-3">
        <div>
          <p className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            {title}
            <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 dark:bg-slate-700/50 dark:text-slate-300 text-xs font-semibold">
              {totalIssues}
            </span>
          </p>
          {subtitle && <p className="text-sm text-slate-500 dark:text-slate-300">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={() => setIsCollapsed((prev) => !prev)}
          aria-expanded={!isCollapsed}
          className={`inline-flex items-center justify-center w-10 h-10 rounded-full transition-colors ${
            isCollapsed
              ? "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300"
              : "bg-slate-100 text-slate-500 dark:bg-slate-800/60 dark:text-slate-400"
          } focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-500`}
          style={{ alignSelf: "flex-start" }}
        >
          <span className="sr-only">{isCollapsed ? "Expand criteria summary" : "Collapse criteria summary"}</span>
          <svg
            className={`w-5 h-5 transition-transform ${isCollapsed ? "" : "rotate-180"}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </header>

      {!isCollapsed && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-[11px]">
            {DEFAULT_STATUS_ORDER.map((statusKey) => {
              const meta = STATUS_META[statusKey]
              if (!meta) return null
              return (
                <div
                  key={statusKey}
                  className="flex flex-col gap-1 rounded-xl border border-slate-100 dark:border-slate-700/60 bg-slate-50/60 dark:bg-slate-900/60 p-3"
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${meta.dotClass}`}></span>
                    <p className="text-xs font-semibold uppercase text-slate-700 dark:text-slate-200">{meta.label}</p>
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{meta.meaning}</p>
                  <p className="text-[11px] text-slate-400 dark:text-slate-500">{meta.usage}</p>
                </div>
              )
            })}
          </div>

          <div className="space-y-3">
            {items.map((criterion) => {
              const { code, name, level, summary: description, issues = [], infoTooltip } = criterion
              const statusMeta = STATUS_META[criterion.status] || STATUS_META.supports
              const showIssueCount = issues.length > 0 && criterion.status !== "supports"
              const isExpanded = expandedSet.has(code)

              return (
                <div key={code} className="rounded-2xl border border-slate-200 dark:border-slate-700/60 bg-slate-50 dark:bg-slate-900/60 shadow-sm">
                  <button
                    type="button"
                    onClick={() => toggleCriterion(code)}
                    aria-expanded={isExpanded}
                    className="w-full px-5 py-4 flex items-start gap-4 text-left"
                  >
                    <div className="flex-1 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-base font-semibold text-slate-900 dark:text-white">
                          {code} {name || "Criterion"}
                        </p>
                        {level && (
                          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                            Level {level}
                          </span>
                        )}
                      </div>
                      {description && (
                        <p className="text-sm text-slate-500 dark:text-slate-400 flex items-center gap-1">
                          <span>{description}</span>
                          {infoTooltip && (
                            <span
                              role="img"
                              aria-label={infoTooltip}
                              title={infoTooltip}
                              className="flex items-center justify-center w-5 h-5 rounded-full border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-300 text-[10px] font-semibold cursor-help"
                            >
                              <svg
                                className="w-3 h-3"
                                viewBox="0 0 16 16"
                                fill="none"
                                xmlns="http://www.w3.org/2000/svg"
                                aria-hidden="true"
                              >
                                <path
                                  d="M8 1.333a6.667 6.667 0 100 13.334A6.667 6.667 0 008 1.333zm0 1.333a5.334 5.334 0 110 10.668A5.334 5.334 0 018 2.667zM8.667 5.333h-1.334v1.334h1.334V5.333zm0 2.667h-1.334v4h1.334v-4z"
                                  fill="currentColor"
                                />
                              </svg>
                            </span>
                          )}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <span className={`text-xs font-semibold rounded-full px-3 py-1 ${statusMeta.badgeClass}`}>
                        {statusMeta.label}
                      </span>
                      {showIssueCount && (
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          {issues.length} issue{issues.length === 1 ? "" : "s"}
                        </p>
                      )}
                      <svg
                        className={`w-4 h-4 text-slate-400 dark:text-slate-500 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                        viewBox="0 0 20 20"
                        fill="none"
                        stroke="currentColor"
                        aria-hidden="true"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 8l4 4 4-4" />
                      </svg>
                    </div>
                  </button>

                  {isExpanded && (
                    <div className="border-t border-slate-200 dark:border-slate-700/60 px-5 pb-4 pt-2 space-y-3">
                      {issues.length === 0 ? (
                        <p className="text-sm text-slate-500 dark:text-slate-400">No issues were detected for this criterion.</p>
                      ) : (
                        <ul className="space-y-3">
                          {issues.map((issue, index) => {
                            const severityLabel = formatSeverity(issue.severity)
                            const pagesText = getIssuePagesText(issue)
                            const hasPages = pagesText && pagesText !== "N/A"
                            const clauseText = issue.clause || issue.criterion
                            const actionText = issue.recommendation || issue.remediation
                            const severityClasses = getSeverityClass(issue.severity)
                            const detailText =
                              issue.details ||
                              (Array.isArray(issue.cyclePath) && issue.cyclePath.length > 0
                                ? `Path: ${issue.cyclePath.join(" -> ")}`
                                : null)

                            return (
                              <li
                                key={`${code}-${issue.id || index}-${index}`}
                                className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700/60 p-4 space-y-2"
                              >
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                  <p className="text-sm font-semibold text-slate-900 dark:text-white">
                                    {getIssuePrimaryText(issue)}
                                  </p>
                                  {severityLabel && (
                                    <span className={`text-[11px] font-semibold uppercase tracking-widest rounded-full px-2 py-1 ${severityClasses}`}>
                                      {severityLabel}
                                    </span>
                                  )}
                                </div>
                                {issue.wcagCriteria && (
                                  <p className="text-xs text-slate-500 dark:text-slate-400">{issue.wcagCriteria}</p>
                                )}
                                <div className="flex flex-wrap gap-3 text-xs text-slate-500 dark:text-slate-400">
                                  {clauseText && (
                                    <p>
                                      <span className="font-semibold text-slate-600 dark:text-slate-300">Clause:</span> {clauseText}
                                    </p>
                                  )}
                                  {hasPages && (
                                    <p>
                                      <span className="font-semibold text-slate-600 dark:text-slate-300">Page(s):</span> {pagesText}
                                    </p>
                                  )}
                                  {issue.count && (
                                    <p>
                                      <span className="font-semibold text-slate-600 dark:text-slate-300">Instances:</span> {issue.count}
                                    </p>
                                  )}
                                </div>
                                {detailText && (
                                  <p className="text-xs text-slate-500 dark:text-slate-400">
                                    <span className="font-semibold text-slate-600 dark:text-slate-300">Details:</span> {detailText}
                                  </p>
                                )}
                                {actionText && (
                                  <p className="text-xs text-slate-500 dark:text-slate-400 border-l border-slate-200 dark:border-slate-700/60 pl-3">
                                    {actionText}
                                  </p>
                                )}
                              </li>
                            )}
                          )}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}
    </section>
  )
}

export { STATUS_META }
