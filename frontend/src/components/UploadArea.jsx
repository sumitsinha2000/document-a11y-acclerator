"use client"

import { useState, useRef } from "react"
import axios from "axios"
// import "./UploadArea.css"

export default function UploadArea({ onScanComplete }) {
  const [isDragging, setIsDragging] = useState(false)
  const [isScanning, setIsScanning] = useState(false)
  const [error, setError] = useState(null)
  const [uploadProgress, setUploadProgress] = useState([])
  const fileInputRef = useRef(null)

  const handleDragOver = (e) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = () => {
    setIsDragging(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragging(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) {
      handleMultipleFileUpload(files)
    }
  }

  const handleFileInput = (e) => {
    const files = Array.from(e.target.files)
    if (files.length > 0) {
      handleMultipleFileUpload(files)
    }
  }

  const handleClick = () => {
    if (!isScanning && fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  const handleMultipleFileUpload = async (files) => {
    const pdfFiles = files.filter((file) => file.name.toLowerCase().endsWith(".pdf"))

    if (pdfFiles.length === 0) {
      setError("Please upload at least one PDF file")
      return
    }

    if (pdfFiles.length < files.length) {
      setError(`${files.length - pdfFiles.length} non-PDF file(s) were skipped`)
    } else {
      setError(null)
    }

    setIsScanning(true)

    const initialProgress = pdfFiles.map((file) => ({
      name: file.name,
      status: "pending",
      progress: 0,
    }))
    setUploadProgress(initialProgress)

    if (pdfFiles.length > 1) {
      try {
        console.log("[v0] Uploading batch of", pdfFiles.length, "files")

        const formData = new FormData()
        pdfFiles.forEach((file) => {
          formData.append("files", file)
        })

        setUploadProgress((prev) => prev.map((item) => ({ ...item, status: "scanning", progress: 50 })))

        const response = await axios.post("/api/scan-batch", formData, {
          headers: {
            "Content-Type": "multipart/form-data",
          },
          timeout: 120000, // 2 minute timeout for batch
        })

        console.log("[v0] Batch scan successful:", response.data)

        setUploadProgress((prev) => prev.map((item) => ({ ...item, status: "complete", progress: 100 })))

        // Add batchId to each scan result
        const scanResults = response.data.scans.map((scan) => ({
          ...scan,
          batchId: response.data.batchId,
        }))

        setIsScanning(false)

        setTimeout(() => {
          setUploadProgress([])
        }, 2000)

        onScanComplete(scanResults)
        return
      } catch (err) {
        console.error("[v0] Batch scan error:", err)
        setError("Batch scan failed: " + (err.response?.data?.error || err.message))
        setUploadProgress((prev) => prev.map((item) => ({ ...item, status: "error", progress: 0 })))
        setIsScanning(false)
        return
      }
    }

    const scanResults = []

    console.log("[v0] Starting scan for", pdfFiles.length, "files")

    for (let i = 0; i < pdfFiles.length; i++) {
      const file = pdfFiles[i]

      console.log("[v0] Scanning file:", file.name)

      setUploadProgress((prev) =>
        prev.map((item, idx) => (idx === i ? { ...item, status: "scanning", progress: 50 } : item)),
      )

      try {
        const formData = new FormData()
        formData.append("file", file)

        console.log("[v0] Sending request to /api/scan for", file.name)

        const response = await axios.post("/api/scan", formData, {
          headers: {
            "Content-Type": "multipart/form-data",
          },
          timeout: 60000,
        })

        console.log("[v0] Scan successful for", file.name, response.data)

        setUploadProgress((prev) =>
          prev.map((item, idx) => (idx === i ? { ...item, status: "complete", progress: 100 } : item)),
        )

        scanResults.push({
          ...response.data,
          fileName: file.name,
        })
      } catch (err) {
        console.error("[v0] Error scanning", file.name, ":", err)
        console.error("[v0] Error response:", err.response?.data)
        console.error("[v0] Error status:", err.response?.status)

        const errorMessage = err.response?.data?.error || err.message || "Scan failed"

        setUploadProgress((prev) =>
          prev.map((item, idx) => (idx === i ? { ...item, status: "error", progress: 0, error: errorMessage } : item)),
        )
      }
    }

    console.log("[v0] All scans complete. Results:", scanResults)

    setIsScanning(false)

    setTimeout(() => {
      setUploadProgress([])
    }, 2000)

    if (scanResults.length > 0) {
      onScanComplete(scanResults)
    } else {
      setError("All file scans failed. Please check the console for details and ensure the backend is running.")
    }
  }

  return (
    <div className="w-full max-w-7xl mx-auto">
      <div className="flex flex-col lg:flex-row gap-6 min-h-[60vh] items-center justify-center">
        {/* Upload Area - Left Side */}
        <div className="flex-1 lg:max-w-2xl">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 transition-colors">
            <div
              className={`relative border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-2 dark:focus-within:ring-offset-gray-800 ${
                isDragging
                  ? "border-primary-500 bg-primary-50 dark:bg-primary-900/20"
                  : "border-gray-300 dark:border-gray-600 hover:border-primary-400 dark:hover:border-primary-500"
              } ${isScanning ? "pointer-events-none opacity-75" : ""}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={handleClick}
              role="button"
              tabIndex={isScanning ? -1 : 0}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && !isScanning) {
                  e.preventDefault()
                  handleClick()
                }
              }}
              aria-label="Upload PDF documents. Drag and drop files here or press Enter to browse"
              aria-busy={isScanning}
            >
              {isScanning ? (
                <div className="space-y-4">
                  <div
                    className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-primary-500 border-t-transparent"
                    role="status"
                    aria-label="Scanning in progress"
                  ></div>
                  <p className="text-base font-medium text-gray-700 dark:text-gray-300">
                    Scanning {uploadProgress.length} PDF file(s)...
                  </p>
                </div>
              ) : (
                <>
                  <svg
                    className="mx-auto h-14 w-14 text-gray-400 dark:text-gray-500"
                    stroke="currentColor"
                    fill="none"
                    viewBox="0 0 48 48"
                    aria-hidden="true"
                  >
                    <path
                      d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <h2 className="mt-4 text-lg font-semibold text-gray-900 dark:text-white">Upload PDF Documents</h2>
                  <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                    Drag and drop your PDFs here or click to browse
                  </p>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-500">You can select multiple files at once</p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf"
                    multiple
                    onChange={handleFileInput}
                    className="hidden"
                    disabled={isScanning}
                    aria-label="Choose PDF files to upload"
                  />
                </>
              )}
            </div>

            {error && (
              <div
                className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg"
                role="alert"
                aria-live="assertive"
              >
                <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
              </div>
            )}

            <div className="mt-6 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-5">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">What we scan for:</h3>
              <ul className="space-y-2 text-xs text-gray-600 dark:text-gray-400" role="list">
                <li className="flex items-start">
                  <svg
                    className="w-4 h-4 text-primary-500 mr-2 mt-0.5 flex-shrink-0"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  Missing document metadata and title
                </li>
                <li className="flex items-start">
                  <svg
                    className="w-4 h-4 text-primary-500 mr-2 mt-0.5 flex-shrink-0"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  Untagged content and improper structure
                </li>
                <li className="flex items-start">
                  <svg
                    className="w-4 h-4 text-primary-500 mr-2 mt-0.5 flex-shrink-0"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  Missing alternative text for images
                </li>
                <li className="flex items-start">
                  <svg
                    className="w-4 h-4 text-primary-500 mr-2 mt-0.5 flex-shrink-0"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  Poor text contrast ratios
                </li>
                <li className="flex items-start">
                  <svg
                    className="w-4 h-4 text-primary-500 mr-2 mt-0.5 flex-shrink-0"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  Missing language declarations
                </li>
                <li className="flex items-start">
                  <svg
                    className="w-4 h-4 text-primary-500 mr-2 mt-0.5 flex-shrink-0"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  Form field accessibility issues
                </li>
                <li className="flex items-start">
                  <svg
                    className="w-4 h-4 text-primary-500 mr-2 mt-0.5 flex-shrink-0"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  Table structure and header problems
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* Upload Progress - Right Side */}
        {uploadProgress.length > 0 && (
          <div className="flex-1 lg:max-w-md">
            <div
              className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 transition-colors sticky top-20"
              role="region"
              aria-label="Upload progress"
            >
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4">Upload Status</h3>
              <div
                className="space-y-2 max-h-[600px] overflow-y-auto"
                role="list"
                aria-live="polite"
                aria-atomic="false"
              >
                {uploadProgress.map((item, idx) => (
                  <div
                    key={idx}
                    className={`p-3 rounded-lg border transition-colors ${
                      item.status === "complete"
                        ? "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800"
                        : item.status === "error"
                          ? "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800"
                          : "bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800"
                    }`}
                    role="listitem"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs font-medium text-gray-700 dark:text-gray-300 truncate flex-1">
                        {item.name}
                      </span>
                      <span
                        className={`px-2 py-0.5 text-xs font-semibold rounded-full whitespace-nowrap ${
                          item.status === "complete"
                            ? "bg-green-100 dark:bg-green-800 text-green-800 dark:text-green-100"
                            : item.status === "error"
                              ? "bg-red-100 dark:bg-red-800 text-red-800 dark:text-red-100"
                              : "bg-blue-100 dark:bg-blue-800 text-blue-800 dark:text-blue-100"
                        }`}
                        role="status"
                        aria-label={`Status: ${item.status}`}
                      >
                        {item.status}
                      </span>
                    </div>
                    {item.error && (
                      <p className="mt-1 text-xs text-red-600 dark:text-red-400 break-words" role="alert">
                        {item.error}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
