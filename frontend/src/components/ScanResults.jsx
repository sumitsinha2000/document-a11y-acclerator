"use client"

import { useCallback, useState } from "react"
import axios from "axios"
import FixSuggestions from "./FixSuggestions" // Ensure this path is correct

const ScanResults = ({ scanId, filename }) => {
  const [summary, setSummary] = useState(null)
  const [results, setResults] = useState(null)
  const [fixes, setFixes] = useState(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const handleRefresh = useCallback(
    async (updates, legacyResults) => {
      console.log("[v0] ScanResults - handleRefresh called")
      console.log("[v0] ScanResults - updates:", updates)
      console.log("[v0] ScanResults - legacyResults:", legacyResults)

      let providedSummary
      let providedResults
      let providedFixes

      if (legacyResults !== undefined) {
        providedSummary = updates
        providedResults = legacyResults
      } else if (updates && typeof updates === "object" && !Array.isArray(updates)) {
        providedSummary = updates.summary ?? updates.newSummary
        providedResults = updates.results ?? updates.newResults ?? updates.newScanResults
        providedFixes = updates.fixes ?? updates.newFixes
      }

      if (providedSummary || providedResults || providedFixes) {
        console.log("[v0] ScanResults - Using provided data directly")
        if (providedSummary !== undefined) setSummary(providedSummary)
        if (providedResults !== undefined) {
          if (typeof providedResults === "object" && !Array.isArray(providedResults)) {
            setResults(providedResults)
          } else {
            setResults(providedResults)
          }
        }
        if (providedFixes !== undefined) setFixes(providedFixes)
        return
      }

      console.log("[v0] ScanResults - Fetching fresh data from server")
      setIsRefreshing(true)
      try {
        const response = await axios.get(`/api/scan-results/${scanId}`)
        console.log("[v0] ScanResults - Fresh data received:", response.data)

        if (response.data.success) {
          setSummary(response.data.summary)
          setResults(response.data.results)
          setFixes(response.data.fixes || null)
          console.log("[v0] ScanResults - State updated with fresh data")
        } else {
          console.error("[v0] ScanResults - Failed to fetch fresh data:", response.data.message)
        }
      } catch (error) {
        console.error("[v0] ScanResults - Error fetching fresh data:", error)
      } finally {
        setIsRefreshing(false)
      }
    },
    [scanId],
  )

  return (
    <div>
      {/* Fix Suggestions Section */}
      {fixes && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6 border border-gray-200 dark:border-gray-700">
          {isRefreshing && (
            <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
              <p className="text-sm text-blue-800 dark:text-blue-200 flex items-center gap-2">
                <svg
                  className="animate-spin h-4 w-4"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  ></path>
                </svg>
                Refreshing data...
              </p>
            </div>
          )}
          <FixSuggestions scanId={scanId} fixes={fixes} filename={filename} onRefresh={handleRefresh} />
        </div>
      )}
    </div>
  )
}

export default ScanResults
