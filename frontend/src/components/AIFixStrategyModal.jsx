"use client"

import { useState } from "react"

export default function AIFixStrategyModal({ isOpen, onClose, strategy, issueType, fixCategory }) {
  const [activeTab, setActiveTab] = useState("overview")

  if (!isOpen) return null

  const getCategoryColor = (category) => {
    switch (category) {
      case "automated":
        return "from-green-500 to-emerald-600"
      case "semi-automated":
        return "from-blue-500 to-indigo-600"
      case "manual":
        return "from-purple-500 to-pink-600"
      default:
        return "from-gray-500 to-gray-600"
    }
  }

  const getComplexityBadge = (complexity) => {
    const colors = {
      Low: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300",
      Medium: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300",
      High: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
    }
    return colors[complexity] || colors["Medium"]
  }

  return (
    <div
      className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="ai-strategy-title"
    >
      <div
        className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header with gradient */}
        <div className={`bg-gradient-to-r ${getCategoryColor(fixCategory)} p-6 text-white`}>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2">
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                  />
                </svg>
                <div>
                  <h2 id="ai-strategy-title" className="text-2xl font-bold">
                    AI Fix Strategy
                  </h2>
                  <p className="text-white/90 text-sm mt-1">
                    {issueType.toUpperCase()} • {fixCategory.charAt(0).toUpperCase() + fixCategory.slice(1)} Fixes
                  </p>
                </div>
              </div>
              {strategy.total_issues && (
                <div className="flex items-center gap-4 mt-3">
                  <span className="px-3 py-1 bg-white/20 rounded-full text-sm font-medium">
                    {strategy.total_issues} {strategy.total_issues === 1 ? "Issue" : "Issues"}
                  </span>
                  {strategy.estimated_time && (
                    <span className="px-3 py-1 bg-white/20 rounded-full text-sm font-medium">
                      ⏱ {strategy.estimated_time}
                    </span>
                  )}
                  {strategy.complexity && (
                    <span
                      className={`px-3 py-1 rounded-full text-sm font-medium ${getComplexityBadge(strategy.complexity)}`}
                    >
                      {strategy.complexity} Complexity
                    </span>
                  )}
                </div>
              )}
            </div>
            <button
              onClick={onClose}
              className="text-white/80 hover:text-white transition-colors p-2 hover:bg-white/10 rounded-lg"
              aria-label="Close modal"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
          <div className="flex gap-1 p-2">
            {["overview", "strategy", "steps"].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 rounded-lg font-medium transition-all ${
                  activeTab === tab
                    ? "bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-400 shadow-sm"
                    : "text-gray-600 dark:text-gray-400 hover:bg-white/50 dark:hover:bg-gray-800/50"
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === "overview" && (
            <div className="space-y-4">
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <h3 className="font-semibold text-blue-900 dark:text-blue-100 mb-2 flex items-center gap-2">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path
                      fillRule="evenodd"
                      d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
                      clipRule="evenodd"
                    />
                  </svg>
                  About This Strategy
                </h3>
                <p className="text-sm text-blue-800 dark:text-blue-200">
                  This AI-generated strategy provides {fixCategory} remediation guidance for {strategy.total_issues}{" "}
                  {issueType} accessibility {strategy.total_issues === 1 ? "issue" : "issues"}.
                </p>
              </div>

              {strategy.strategy && (
                <div className="prose dark:prose-invert max-w-none">
                  <div className="whitespace-pre-wrap text-gray-700 dark:text-gray-300 leading-relaxed">
                    {strategy.strategy.split("\n").slice(0, 10).join("\n")}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "strategy" && strategy.strategy && (
            <div className="prose dark:prose-invert max-w-none">
              <div className="whitespace-pre-wrap text-gray-700 dark:text-gray-300 leading-relaxed font-mono text-sm bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                {strategy.strategy}
              </div>
            </div>
          )}

          {activeTab === "steps" && (
            <div className="space-y-4">
              <p className="text-gray-600 dark:text-gray-400 text-sm">
                Follow these steps to implement the {fixCategory} fixes:
              </p>
              <div className="space-y-3">
                {strategy.strategy &&
                  strategy.strategy
                    .split("\n")
                    .filter(
                      (line) =>
                        line.trim().match(/^\d+\./) || line.trim().startsWith("-") || line.trim().startsWith("*"),
                    )
                    .map((step, idx) => (
                      <div key={idx} className="flex gap-3 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                        <div className="flex-shrink-0 w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-bold">
                          {idx + 1}
                        </div>
                        <p className="text-gray-700 dark:text-gray-300 flex-1">
                          {step.replace(/^\d+\.\s*|-\s*|\*\s*/, "")}
                        </p>
                      </div>
                    ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-900/50 flex justify-between items-center">
          <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z"
                clipRule="evenodd"
              />
            </svg>
            <span>Powered by SambaNova AI</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
