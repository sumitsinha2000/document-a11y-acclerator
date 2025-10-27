"use client"

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
          {scans.map((scan) => (
            <div
              key={scan.id}
              className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 cursor-pointer transition-colors"
              onClick={() => onSelectScan(scan)}
            >
              <div className="flex-1">
                <h3 className="font-semibold text-gray-900 dark:text-white">{scan.filename}</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  {new Date(scan.uploadDate).toLocaleDateString()} at {new Date(scan.uploadDate).toLocaleTimeString()}
                </p>
              </div>
              <div className="flex items-center gap-3">
                {scan.complianceScore !== undefined && (
                  <div className="text-right mr-4">
                    <div className="text-lg font-bold text-gray-900 dark:text-white">{scan.complianceScore}%</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">Score</div>
                  </div>
                )}
                <span
                  className={`px-3 py-1 rounded-full text-xs font-medium ${
                    scan.status === "completed"
                      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                      : scan.status === "failed"
                        ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                        : "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
                  }`}
                >
                  {scan.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
