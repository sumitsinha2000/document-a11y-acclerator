"use client"

import { formatCategoryLabel, getIssueWcagCriteria } from "../utils/exportUtils"

export default function IssuesList({ results, selectedCategory, onSelectCategory }) {
  console.log("[v0] IssuesList received results:", results)
  console.log("[v0] Results type:", typeof results)
  console.log("[v0] Results keys:", Object.keys(results || {}))

  if (!results || typeof results !== "object") {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6">
        <p className="text-gray-500 dark:text-gray-400">No issues data available</p>
      </div>
    )
  }

  const categories = Object.keys(results || {})

  if (categories.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6">
        <p className="text-gray-500 dark:text-gray-400">No accessibility issues found</p>
      </div>
    )
  }

  const getSeverityStyles = (severity) => {
    switch (severity) {
      case "high":
        return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 border-l-red-500"
      case "medium":
        return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200 border-l-yellow-500"
      case "low":
        return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 border-l-green-500"
      default:
        return "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200 border-l-gray-500"
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        {categories.map((category) => {
          const issues = results[category] || []
          const count = issues.length

          return (
            <button
              key={category}
              className={`px-4 py-2 rounded-lg font-medium transition-all ${
                selectedCategory === category
                  ? "bg-blue-600 text-white shadow-lg"
                  : "bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700"
              }`}
              onClick={() => onSelectCategory(selectedCategory === category ? null : category)}
            >
              <span className="mr-2">{formatCategoryLabel(category)}</span>
              <span
                className={`px-2 py-0.5 rounded-full text-xs ${
                  selectedCategory === category
                    ? "bg-blue-500 text-white"
                    : "bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                }`}
              >
                {count}
              </span>
            </button>
          )
        })}
      </div>

      {selectedCategory && results[selectedCategory] && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-xl font-bold text-gray-900 dark:text-white">
              {formatCategoryLabel(selectedCategory)}
            </h4>
            <button
              className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 text-2xl leading-none"
              onClick={() => onSelectCategory(null)}
            >
              ✕
            </button>
          </div>

          <div className="space-y-4">
            {results[selectedCategory].map((issue, idx) => {
              const description =
                issue.description ||
                issue.message ||
                issue.title ||
                (issue.clause ? `Checkpoint: ${issue.clause}` : "Issue details unavailable")
              const wcagCriteria = getIssueWcagCriteria(issue)

              return (
                <div key={idx} className={`p-4 rounded-lg border-l-4 ${getSeverityStyles(issue.severity)}`}>
                  <div className="flex items-start gap-3 mb-2">
                    <span className="px-2 py-1 rounded text-xs font-bold uppercase">{issue.severity}</span>
                    <span className="font-semibold flex-1">{description}</span>
                  </div>
                  {issue.clause && (
                    <p className="text-sm opacity-75 ml-16">
                      <strong>Clause:</strong> {issue.clause}
                    </p>
                  )}
                  {issue.page && <p className="text-sm opacity-75 ml-16">Page: {issue.page}</p>}
                  {issue.pages && <p className="text-sm opacity-75 ml-16">Pages: {issue.pages.join(", ")}</p>}
                  {issue.count && <p className="text-sm opacity-75 ml-16">Count: {issue.count}</p>}
                  {wcagCriteria && (
                    <p className="text-sm opacity-75 ml-16">
                      <strong>WCAG:</strong> {wcagCriteria}
                    </p>
                  )}
                  {issue.remediation && !issue.recommendation && (
                    <div className="mt-3 ml-16 p-3 bg-blue-50 dark:bg-blue-900/20 rounded border-l-2 border-blue-500">
                      <p className="text-sm">
                        <strong className="text-blue-700 dark:text-blue-300">Remediation:</strong>{" "}
                        <span className="text-gray-700 dark:text-gray-300">{issue.remediation}</span>
                      </p>
                    </div>
                  )}
                  {issue.recommendation && (
                    <div className="mt-3 ml-16 p-3 bg-blue-50 dark:bg-blue-900/20 rounded border-l-2 border-blue-500">
                      <p className="text-sm">
                        <strong className="text-blue-700 dark:text-blue-300">Recommendation:</strong>{" "}
                        <span className="text-gray-700 dark:text-gray-300">{issue.recommendation}</span>
                      </p>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
