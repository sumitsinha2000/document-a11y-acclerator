import { parseBackendDate } from "../utils/dates"
import { getScanErrorMessage, resolveEntityStatus } from "../utils/statuses"

export default function ScanHistory({ scans, onSelectScan, onBack }) {
  if (scans.length === 0) {
    return (
      <div className="max-w-7xl mx-auto p-6">
        <div className="mb-4">
          <button
            onClick={onBack}
            className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Upload
          </button>
        </div>

        <div className="p-8 bg-white dark:bg-gray-800 rounded-lg shadow-sm">
          <div className="text-center py-12">
            <p className="text-gray-500 dark:text-gray-400">No scans yet. Upload a PDF to get started!</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto p-6">
      <div className="mb-4">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Upload
        </button>
      </div>

      <div className="p-8 bg-white dark:bg-gray-800 rounded-lg shadow-sm">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Scan History</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{scans.length} scans completed</p>
        </div>

        <div className="space-y-3">
          {scans.map((scan) => {
            const scanDate = parseBackendDate(scan.uploadDate || scan.timestamp || scan.created_at)
            const statusInfo = resolveEntityStatus(scan)
            const isError = statusInfo.code === "error"
            const errorMessage = isError ? getScanErrorMessage(scan) : null
            const containerClasses = isError
              ? "bg-rose-50/80 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/40 hover:bg-rose-100 dark:hover:bg-rose-900/30"
              : "bg-gray-50 dark:bg-gray-700 border border-transparent hover:bg-gray-100 dark:hover:bg-gray-600"
            const statusClass =
              isError
                ? "bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-200"
                : statusInfo.code === "fixed"
                ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                : statusInfo.code === "partially_fixed"
                  ? "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200"
                  : statusInfo.code === "scanned"
                    ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                    : statusInfo.code === "uploaded"
                      ? "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200"
                      : "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-200"
            const statusLabel = isError ? "Scan failed" : statusInfo.label || scan.status
            const showComplianceScore =
              typeof scan.complianceScore === "number" && Number.isFinite(scan.complianceScore) && !isError
            return (
              <div
                key={scan.id}
                className={`flex items-center justify-between p-4 rounded-lg cursor-pointer transition-colors ${containerClasses}`}
                onClick={() => onSelectScan(scan)}
              >
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900 dark:text-white">{scan.filename}</h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    {scanDate
                      ? `${scanDate.toLocaleDateString()} at ${scanDate.toLocaleTimeString()}`
                      : "Date unavailable"}
                  </p>
                  {isError && errorMessage && (
                    <div
                      className="mt-1 flex items-center gap-2 text-xs text-rose-700 dark:text-rose-200"
                      role="status"
                      aria-live="polite"
                    >
                      <svg
                        className="w-4 h-4 text-rose-600 dark:text-rose-300"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20 10 10 0 000-20z" />
                      </svg>
                      <p>{errorMessage}</p>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  {showComplianceScore && (
                    <div className="text-right mr-4">
                      <div className="text-lg font-bold text-gray-900 dark:text-white">{scan.complianceScore}%</div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">Score</div>
                    </div>
                  )}
                  <span className={`px-3 py-1 rounded-full text-xs font-medium ${statusClass}`}>
                    {statusLabel}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
