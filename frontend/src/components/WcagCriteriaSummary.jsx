import { useMemo, useState } from "react"
import { getIssuePrimaryText, getIssuePagesText } from "../utils/exportUtils"

const CRITERIA_DETAILS = {
  "1.1.1": {
    name: "Non-text Content",
    level: "A",
    summary: "Provide text alternatives for non-text content.",
  },
  "1.3.1": {
    name: "Info and Relationships",
    level: "A",
    summary: "Preserve semantics so assistive technology can convey relationships.",
  },
  "1.3.2": {
    name: "Meaningful Sequence",
    level: "A",
    summary: "Ensure the reading order preserves the intended meaning.",
  },
  "1.4.3": {
    name: "Contrast (Minimum)",
    level: "AA",
    summary: "Text and images of text must have a contrast ratio of at least 4.5:1.",
  },
  "1.4.6": {
    name: "Contrast (Enhanced)",
    level: "AAA",
    summary: "Enhanced contrast helps people with very low vision.",
  },
  "2.4.2": {
    name: "Page Titled",
    level: "A",
    summary: "Provide descriptive titles so users can identify each page.",
  },
  "2.4.6": {
    name: "Headings and Labels",
    level: "AA",
    summary: "Use clear hierarchies and labels for navigation and orientation.",
  },
  "3.1.1": {
    name: "Language of Page",
    level: "A",
    summary: "Declare the primary language so screen readers can pronounce correctly.",
  },
  "3.3.2": {
    name: "Labels or Instructions",
    level: "A",
    summary: "Provide instructions so users understand required input.",
  },
  "4.1.2": {
    name: "Name, Role, Value",
    level: "A",
    summary: "Expose semantics and state to assistive technologies.",
  },
}

const CRITERIA_ORDER = [
  "1.1.1",
  "1.3.1",
  "1.3.2",
  "1.4.3",
  "1.4.6",
  "2.4.2",
  "2.4.6",
  "3.1.1",
  "3.3.2",
  "4.1.2",
]

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

const CRITERIA_REGEX = /\b\d+\.\d+\.\d+\b/g
const SEVERITY_RANK = {
  critical: 3,
  high: 3,
  medium: 2,
  low: 1,
}

const buildIssuesByCriterion = (results) => {
  const map = new Map()
  if (!results || typeof results !== "object") {
    return map
  }

  Object.values(results).forEach((value) => {
    if (!Array.isArray(value)) {
      return
    }

    value.forEach((issue) => {
      if (!issue || typeof issue !== "object") {
        return
      }

      const sourceText = [issue.wcagCriteria, issue.criterion].filter(Boolean).join(" ")
      const matches = sourceText.match(CRITERIA_REGEX)
      if (!matches) {
        return
      }

      const uniqueCodes = Array.from(new Set(matches.map((code) => code.trim())))
      uniqueCodes.forEach((code) => {
        if (!code) {
          return
        }
        if (!map.has(code)) {
          map.set(code, [])
        }
        map.get(code).push(issue)
      })
    })
  })

  return map
}

const getSeverityRank = (issue) => {
  if (!issue) {
    return 0
  }
  const severity = String(issue.severity || "").toLowerCase().trim()
  if (severity && SEVERITY_RANK[severity] !== undefined) {
    return SEVERITY_RANK[severity]
  }
  return 2
}

const determineStatusKey = (issues = []) => {
  if (!issues.length) {
    return "supports"
  }
  const highest = issues.reduce((current, issue) => Math.max(current, getSeverityRank(issue)), 0)
  if (highest >= 3) {
    return "doesNotSupport"
  }
  return "partiallySupports"
}

const formatSeverityLabel = (severity) => {
  if (!severity) {
    return null
  }
  return severity.charAt(0).toUpperCase() + severity.slice(1)
}

const getSeverityClasses = (severity) => {
  if (!severity) {
    return "bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-200 border border-slate-200 dark:border-slate-700"
  }

  const normalized = severity.toLowerCase()
  if (normalized === "high" || normalized === "critical") {
    return "border border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/40 dark:bg-rose-900/20 dark:text-rose-200"
  }
  if (normalized === "medium") {
    return "border border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/40 dark:bg-amber-900/20 dark:text-amber-200"
  }
  if (normalized === "low") {
    return "border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-900/20 dark:text-emerald-200"
  }
  return "border border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700/60 dark:bg-slate-900/40 dark:text-slate-200"
}

export default function WcagCriteriaSummary({ results }) {
  const [expandedCriteria, setExpandedCriteria] = useState([])
  const [isCollapsed, setIsCollapsed] = useState(true)
  const issuesByCriterion = useMemo(() => buildIssuesByCriterion(results), [results])

  const criteriaToRender = useMemo(() => {
    const ordered = []
    const seen = new Set()
    CRITERIA_ORDER.forEach((code) => {
      ordered.push(code)
      seen.add(code)
    })
    Array.from(issuesByCriterion.keys())
      .filter((code) => !seen.has(code))
      .sort()
      .forEach((code) => {
        ordered.push(code)
      })
    return ordered
  }, [issuesByCriterion])

  const toggleCriterion = (code) => {
    setExpandedCriteria((prev) =>
      prev.includes(code) ? prev.filter((item) => item !== code) : [...prev, code]
    )
  }

  if (!results || typeof results !== "object") {
    return null
  }

  const criteriaCount = criteriaToRender.length

  return (
    <section className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm p-6 space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            WCAG Criteria Report
            <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 dark:bg-slate-700/50 dark:text-slate-300 text-xs font-semibold">
              {criteriaCount}
            </span>
          </p>
          <p className="text-sm text-slate-500 dark:text-slate-300">
            Monitor how this file performs against key WCAG success criteria. Expand any card for issue-level details.
          </p>
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
          <svg
            className={`w-5 h-5 transition-transform ${isCollapsed ? "" : "rotate-180"}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {!isCollapsed && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-[11px]">
            {["supports", "partiallySupports", "doesNotSupport", "notApplicable", "notEvaluated"].map(
              (statusKey) => {
                const meta = STATUS_META[statusKey]
                if (!meta) {
                  return null
                }
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
              }
            )}
          </div>

          <div className="space-y-3">
            {criteriaToRender.map((code) => {
              const details = CRITERIA_DETAILS[code]
              const issues = issuesByCriterion.get(code) || []
              const statusKey = determineStatusKey(issues)
              const statusMeta = STATUS_META[statusKey]
              const showIssueCount = statusKey === "partiallySupports" || statusKey === "doesNotSupport"
              const isExpanded = expandedCriteria.includes(code)
              const description = details?.summary || "No description available."

              return (
                <div
                  key={code}
                  className="rounded-2xl border border-slate-200 dark:border-slate-700/60 bg-slate-50 dark:bg-slate-900/60 shadow-sm"
                >
                  <button
                    type="button"
                    onClick={() => toggleCriterion(code)}
                    aria-expanded={isExpanded}
                    className="w-full px-5 py-4 flex items-start gap-4 text-left"
                  >
                    <div className="flex-1 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-base font-semibold text-slate-900 dark:text-white">
                          {code} {details?.name || "WCAG Criterion"}
                        </p>
                        {details?.level && (
                          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                            Level {details.level}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-slate-500 dark:text-slate-400">{description}</p>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <span className={`text-xs font-semibold rounded-full px-3 py-1 ${statusMeta?.badgeClass || ""}`}>
                        {statusMeta?.label || "Supports"}
                      </span>
                      {showIssueCount && issues.length > 0 && (
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          {issues.length} issue{issues.length === 1 ? "" : "s"}
                        </p>
                      )}
                      <svg
                        className={`w-4 h-4 text-slate-400 dark:text-slate-500 transition-transform ${
                          isExpanded ? "rotate-180" : ""
                        }`}
                        viewBox="0 0 20 20"
                        fill="none"
                        stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 8l4 4 4-4" />
                      </svg>
                    </div>
                  </button>

                  {isExpanded && (
                    <div className="border-t border-slate-200 dark:border-slate-700/60 px-5 pb-4 pt-2 space-y-3">
                      {issues.length === 0 ? (
                        <p className="text-sm text-slate-500 dark:text-slate-400">
                          No issues were detected for this criterion.
                        </p>
                      ) : (
                        <ul className="space-y-3">
                          {issues.map((issue, index) => {
                            const severityLabel = formatSeverityLabel(issue.severity)
                            const pagesText = getIssuePagesText(issue)
                            const hasPages = pagesText && pagesText !== "N/A"
                            const clauseText = issue.clause
                            const actionText = issue.recommendation || issue.remediation
                            const severityClasses = getSeverityClasses(issue.severity)

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
                                      <span className="font-semibold text-slate-600 dark:text-slate-300">Clause:</span>{" "}
                                      {clauseText}
                                    </p>
                                  )}
                                  {hasPages && (
                                    <p>
                                      <span className="font-semibold text-slate-600 dark:text-slate-300">Page(s):</span>{" "}
                                      {pagesText}
                                    </p>
                                  )}
                                  {issue.count && (
                                    <p>
                                      <span className="font-semibold text-slate-600 dark:text-slate-300">Instances:</span>{" "}
                                      {issue.count}
                                    </p>
                                  )}
                                </div>
                                {actionText && (
                                  <p className="text-xs text-slate-500 dark:text-slate-400 border-l border-slate-200 dark:border-slate-700/60 pl-3">
                                    {actionText}
                                  </p>
                                )}
                              </li>
                            )
                          })}
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
