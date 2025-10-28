"use client"

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

  const getCategoryLabel = (key) => {
    const labels = {
      missingMetadata: "Missing Metadata",
      untaggedContent: "Untagged Content",
      missingAltText: "Missing Alt Text",
      poorContrast: "Poor Contrast",
      missingLanguage: "Missing Language",
      formIssues: "Form Issues",
      tableIssues: "Table Issues",
      wcagIssues: "WCAG 2.1 Violations",
      pdfuaIssues: "PDF/UA Issues",
      structureIssues: "Structure Issues",
      readingOrderIssues: "Reading Order Issues",
    }
    return labels[key] || key
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

  const getCategoryIcon = (key) => {
    const icons = {
      wcagIssues: (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
            clipRule="evenodd"
          />
        </svg>
      ),
      pdfuaIssues: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
      ),
    }
    return icons[key] || null
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Issue categories">
        {categories.map((category) => {
          const issues = results[category] || []
          const count = issues.length
          const icon = getCategoryIcon(category)
          const isVeraPDFCategory = category === "wcagIssues" || category === "pdfuaIssues"

          return (
            <button
              key={category}
              className={`px-4 py-2 rounded-lg font-medium transition-all flex items-center gap-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900 ${
                selectedCategory === category
                  ? "bg-blue-600 text-white shadow-lg"
                  : isVeraPDFCategory
                    ? "bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/30 border border-blue-200 dark:border-blue-800"
                    : "bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700"
              }`}
              onClick={() => onSelectCategory(selectedCategory === category ? null : category)}
              aria-pressed={selectedCategory === category}
              aria-label={`${getCategoryLabel(category)}, ${count} ${count === 1 ? "issue" : "issues"}`}
            >
              {icon && (
                <span className={selectedCategory === category ? "text-white" : ""} aria-hidden="true">
                  {icon}
                </span>
              )}
              <span className="mr-2">{getCategoryLabel(category)}</span>
              <span
                className={`px-2 py-0.5 rounded-full text-xs ${
                  selectedCategory === category
                    ? "bg-blue-500 text-white"
                    : "bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                }`}
                aria-hidden="true"
              >
                {count}
              </span>
            </button>
          )
        })}
      </div>

      {selectedCategory && results[selectedCategory] && (
        <div
          className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6"
          role="region"
          aria-label={`${getCategoryLabel(selectedCategory)} details`}
        >
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-xl font-bold text-gray-900 dark:text-white">{getCategoryLabel(selectedCategory)}</h4>
            <button
              className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 text-2xl leading-none focus:outline-none focus:ring-2 focus:ring-blue-500 rounded p-1"
              onClick={() => onSelectCategory(null)}
              aria-label="Close issue details"
            >
              ✕
            </button>
          </div>

          <div className="space-y-4" role="list">
            {results[selectedCategory].map((issue, idx) => (
              <div
                key={idx}
                className={`p-4 rounded-lg border-l-4 ${getSeverityStyles(issue.severity)}`}
                role="listitem"
              >
                <div className="flex items-start gap-3 mb-2">
                  <span
                    className="px-2 py-1 rounded text-xs font-bold uppercase"
                    aria-label={`Severity: ${issue.severity}`}
                  >
                    {issue.severity}
                  </span>
                  <span className="font-semibold flex-1">{issue.description}</span>
                </div>
                {issue.specification && (
                  <p className="text-sm opacity-75 ml-16">
                    <strong>Specification:</strong> {issue.specification}
                    {issue.clause && ` - Clause ${issue.clause}`}
                  </p>
                )}
                {issue.wcagCriterion && (
                  <p className="text-sm opacity-75 ml-16">
                    <strong>WCAG Criterion:</strong> {issue.wcagCriterion} (Level {issue.wcagLevel})
                  </p>
                )}
                {issue.context && <p className="text-sm opacity-75 ml-16">Context: {issue.context}</p>}
                {issue.page && <p className="text-sm opacity-75 ml-16">Page: {issue.page}</p>}
                {issue.pages && <p className="text-sm opacity-75 ml-16">Pages: {issue.pages.join(", ")}</p>}
                {issue.count && <p className="text-sm opacity-75 ml-16">Count: {issue.count}</p>}
                {issue.recommendation && (
                  <div className="mt-3 ml-16 p-3 bg-blue-50 dark:bg-blue-900/20 rounded border-l-2 border-blue-500">
                    <p className="text-sm">
                      <strong className="text-blue-700 dark:text-blue-300">Recommendation:</strong>{" "}
                      <span className="text-gray-700 dark:text-gray-300">{issue.recommendation}</span>
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
