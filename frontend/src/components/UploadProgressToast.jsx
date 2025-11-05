export default function UploadProgressToast({ uploads, onRemove }) {
  if (!uploads || uploads.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2 max-w-sm">
      {uploads.map((upload) => (
        <div
          key={upload.id}
          className="bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-4 min-w-[320px] animate-slide-up"
        >
          <div className="flex items-start justify-between mb-2">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <svg
                className={`w-5 h-5 flex-shrink-0 ${
                  upload.status === "completed"
                    ? "text-green-600"
                    : upload.status === "error"
                      ? "text-red-600"
                      : "text-blue-600"
                }`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                {upload.status === "completed" ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                ) : upload.status === "error" ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                  />
                )}
              </svg>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white truncate" title={upload.filename}>
                  {upload.filename}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {upload.status === "uploading"
                    ? "Uploading..."
                    : upload.status === "processing"
                      ? "Processing..."
                      : upload.status === "completed"
                        ? "Upload complete"
                        : "Upload failed"}
                </p>
              </div>
            </div>
            {(upload.status === "completed" || upload.status === "error") && (
              <button
                onClick={() => onRemove(upload.id)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 ml-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {/* Progress Bar */}
          {upload.status === "uploading" && (
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-blue-600 h-full transition-all duration-300 ease-out"
                style={{ width: `${upload.progress || 0}%` }}
              />
            </div>
          )}

          {/* Processing Spinner */}
          {upload.status === "processing" && (
            <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
              <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span>Analyzing document...</span>
            </div>
          )}

          {/* Error Message */}
          {upload.status === "error" && upload.error && (
            <p className="text-xs text-red-600 dark:text-red-400 mt-1">{upload.error}</p>
          )}
        </div>
      ))}
    </div>
  )
}
