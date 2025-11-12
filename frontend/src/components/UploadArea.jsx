"use client"

import { useState, useRef, useEffect } from "react"
import axios from "axios"
import GroupSelector from "./GroupSelector"
import UploadProgressToast from "./UploadProgressToast"
import { API_ENDPOINTS } from "../config/api";

export default function UploadArea({ onScanComplete, onUploadDeferred }) {
  const [isDragging, setIsDragging] = useState(false)
  const [isScanning, setIsScanning] = useState(false)
  const [error, setError] = useState(null)
  const [uploadProgress, setUploadProgress] = useState([])
  const [srAnnouncement, setSrAnnouncement] = useState("")
  const fileInputRef = useRef(null)
  const uploadAreaRef = useRef(null)
  const [selectedGroup, setSelectedGroup] = useState(null)
  const [selectedFiles, setSelectedFiles] = useState([])
  const [scanMode, setScanMode] = useState("scan-now")

  useEffect(() => {
    if (uploadProgress.length > 0) {
      const completed = uploadProgress.filter((p) => p.status === "completed").length
      const failed = uploadProgress.filter((p) => p.status === "error").length
      const scanning = uploadProgress.filter((p) => p.status === "uploading" || p.status === "processing").length

      if (scanning > 0) {
        setSrAnnouncement(`Scanning ${scanning} of ${uploadProgress.length} files`)
      } else if (completed === uploadProgress.length) {
        setSrAnnouncement(`All ${completed} tasks finished successfully`)
      } else if (completed + failed === uploadProgress.length) {
        setSrAnnouncement(`Process complete. ${completed} succeeded, ${failed} failed`)
      }
    }
  }, [uploadProgress])

  const handleScanModeChange = (mode) => {
    setScanMode(mode)
    setSrAnnouncement(
      mode === "upload-only"
        ? "Uploads will complete without scanning. You can begin scanning later from the dashboard."
        : "Uploads will be scanned immediately after they finish uploading.",
    )
  }

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
      handleFileSelection(files)
    }
  }

  const handleFileInput = (e) => {
    const files = Array.from(e.target.files)
    if (files.length > 0) {
      handleFileSelection(files)
    }
  }

  const handleClick = () => {
    if (!isScanning && fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  const handleFileSelection = (files) => {
    const pdfFiles = files.filter((file) => file.name.toLowerCase().endsWith(".pdf"))

    if (pdfFiles.length === 0) {
      setError("Please select at least one PDF file")
      setSrAnnouncement("Error: Please select at least one PDF file")
      return
    }

    if (pdfFiles.length < files.length) {
      const skippedCount = files.length - pdfFiles.length
      setError(`${skippedCount} non-PDF file(s) were skipped`)
      setSrAnnouncement(`Warning: ${skippedCount} non-PDF files were skipped. ${pdfFiles.length} PDF files selected.`)
    } else {
      setError(null)
    }

    setSelectedFiles(pdfFiles)
    setSrAnnouncement(
      `${pdfFiles.length} PDF ${pdfFiles.length === 1 ? "file" : "files"} selected. Please select a group before uploading.`,
    )
  }

  const handleUploadWithGroup = async () => {
    if (!selectedGroup) {
      setError("Please select a group before uploading")
      setSrAnnouncement("Error: Please select a group before uploading")
      return
    }

    if (selectedFiles.length === 0) {
      setError("No files selected")
      return
    }

    await handleMultipleFileUpload(selectedFiles)
  }

  const resolveGroupId = () => {
    if (!selectedGroup) return null
    if (typeof selectedGroup === 'object') {
      return selectedGroup.id || selectedGroup.group_id || selectedGroup.value || null
    }
    return selectedGroup
  }

  const handleMultipleFileUpload = async (files) => {
    if (!files || files.length === 0) {
      return
    }
    setError(null)
    setIsScanning(true)

    const isDeferred = scanMode === 'upload-only'
    const isBatch = files.length > 1
    const groupId = resolveGroupId()
    setSrAnnouncement(
      isDeferred
        ? `Uploading ${files.length} PDF file${files.length === 1 ? '' : 's'} without scanning`
        : `Uploading and scanning ${files.length} PDF file${files.length === 1 ? '' : 's'}`,
    )

    const initialProgress = files.map((file, index) => ({
      id: `upload-${Date.now()}-${index}`,
      filename: file.name,
      status: 'uploading',
      progress: 0,
    }))
    setUploadProgress(initialProgress)

    const finalize = () => {
      setIsScanning(false)
      setSelectedFiles([])
      setTimeout(() => setUploadProgress([]), 3000)
    }

    const handleError = (message) => {
      setError(message)
      setSrAnnouncement(`Error: ${message}`)
      setUploadProgress((prev) =>
        prev.map((item) => ({
          ...item,
          status: 'error',
          progress: 0,
          error: message,
        })),
      )
    }

    if (isBatch) {
      try {
        const formData = new FormData()
        files.forEach((file) => formData.append('files', file))
        if (groupId) {
          formData.append('group_id', groupId)
        }
        formData.append('scan_mode', isDeferred ? 'upload_only' : 'scan_now')

        setUploadProgress((prev) =>
          prev.map((item) => ({
            ...item,
            status: isDeferred ? 'uploading' : 'processing',
            progress: isDeferred ? 80 : 50,
          })),
        )

        const response = await axios.post(API_ENDPOINTS.scanBatch, formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
          timeout: 120000,
          withCredentials: true,
        })

        setUploadProgress((prev) =>
          prev.map((item) => ({ ...item, status: 'completed', progress: 100 })),
        )

        const scans = Array.isArray(response.data?.scans) ? response.data.scans : []
        const scanIds = scans.map((scan) => scan.scanId || scan.id).filter(Boolean)

        if (response.data?.scanDeferred) {
          const uploadedCount = scanIds.length
          setError(null)
          setSrAnnouncement(
            `Uploaded ${uploadedCount} file${uploadedCount === 1 ? '' : 's'}. Start scanning later from the dashboard.`,
          )
          onUploadDeferred?.({
            batchId: response.data.batchId,
            scanIds,
            groupId,
          })
        } else {
          setError(null)
          setSrAnnouncement(`Processed ${scans.length} file${scans.length === 1 ? '' : 's'}.`)
          onScanComplete(scans)
        }
      } catch (err) {
        const errorMsg = err.response?.data?.error || err.message || 'Batch upload failed'
        console.error('[UploadArea] Batch upload error:', err)
        handleError(errorMsg)
      } finally {
        finalize()
      }
      return
    }

    const file = files[0]
    const endpoint = isDeferred ? API_ENDPOINTS.upload : API_ENDPOINTS.scan
    const timeout = isDeferred ? 120000 : 60000

    try {
      const formData = new FormData()
      formData.append('file', file)
      if (groupId) {
        formData.append('group_id', groupId)
      }
      if (!isDeferred) {
        formData.append('scan_mode', 'scan_now')
      }

      setUploadProgress((prev) =>
        prev.map((item, idx) =>
          idx === 0
            ? {
                ...item,
                status: isDeferred ? 'uploading' : 'processing',
                progress: isDeferred ? 80 : 50,
              }
            : item,
        ),
      )

      const response = await axios.post(endpoint, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout,
        withCredentials: true,
        onUploadProgress: (progressEvent) => {
          if (!progressEvent.total) return
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          setUploadProgress((prev) =>
            prev.map((item, idx) =>
              idx === 0 ? { ...item, progress: percent } : item,
            ),
          )
        },
      })

      setUploadProgress((prev) =>
        prev.map((item, idx) =>
          idx === 0 ? { ...item, status: 'completed', progress: 100 } : item,
        ),
      )

      if (isDeferred) {
        const deferredId = response.data?.scanId || response.data?.result?.scanId
        const scanIds = deferredId ? [deferredId] : []
        setError(null)
        setSrAnnouncement(`Uploaded ${scanIds.length || 1} file${scanIds.length === 1 ? '' : 's'} successfully.`)
        onUploadDeferred?.({
          scanIds,
          groupId,
        })
      } else {
        const payload = {
          ...response.data,
          fileName: response.data?.filename || file.name,
          groupId,
        }
        setError(null)
        setSrAnnouncement(`${file.name} scanned successfully.`)
        onScanComplete([payload])
      }
    } catch (err) {
      const errorMsg = err.response?.data?.error || err.message || 'Upload failed'
      console.error('[UploadArea] File upload error:', err)
      handleError(errorMsg)
    } finally {
      finalize()
    }
  }

  const handleRemoveUpload = (uploadId) => {
    setUploadProgress((prev) => prev.filter((upload) => upload.id !== uploadId))
  }
  return (
    <>
      <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {srAnnouncement}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8">
          {/* Left Column: Group Selection */}
          <aside className="lg:col-span-4 space-y-4" aria-label="Group selection">
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 transition-colors">
              <div className="mb-4">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                  <svg
                    className="w-5 h-5 text-primary-600 dark:text-primary-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                    />
                  </svg>
                  Select Group
                </h2>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                  Choose an existing group or create a new one to organize your files
                </p>
              </div>

              <GroupSelector selectedGroup={selectedGroup} onGroupChange={setSelectedGroup} required={true} />

              {selectedGroup && (
                <div
                  className="mt-4 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg"
                  role="status"
                  aria-live="polite"
                >
                  <p className="text-sm font-medium text-green-800 dark:text-green-200 flex items-center gap-2">
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                        clipRule="evenodd"
                      />
                    </svg>
                    Group selected
                  </p>
                </div>
              )}

              {!selectedGroup && selectedFiles.length > 0 && (
                <div
                  className="mt-4 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg"
                  role="alert"
                  aria-live="polite"
                >
                  <p className="text-sm font-medium text-amber-800 dark:text-amber-200 flex items-center gap-2">
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                      <path
                        fillRule="evenodd"
                        d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                        clipRule="evenodd"
                      />
                    </svg>
                    Please select a group to continue
                  </p>
                </div>
              )}
            </div>
          </aside>

          {/* Right Column: Upload Interface */}
          <div className="lg:col-span-8" aria-label="File upload">
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 lg:p-8 transition-colors">
              <div
                ref={uploadAreaRef}
                className={`relative border-2 border-dashed rounded-xl p-12 lg:p-16 text-center transition-all cursor-pointer focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-2 dark:focus-within:ring-offset-gray-800 ${isDragging
                    ? "border-primary-500 bg-primary-50 dark:bg-primary-900/20 scale-[1.02]"
                    : "border-gray-300 dark:border-gray-600 hover:border-primary-400 dark:hover:border-primary-500 hover:bg-gray-50 dark:hover:bg-gray-700/50"
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
                aria-label="Upload PDF documents for accessibility scanning. Drag and drop files here or press Enter or Space to browse files. Multiple files can be selected."
                aria-busy={isScanning}
                aria-disabled={isScanning}
                aria-describedby="upload-instructions"
              >
                {isScanning ? (
                  <div className="space-y-4">
                    <div
                      className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-primary-500 border-t-transparent"
                      role="status"
                      aria-label="Scanning in progress"
                    ></div>
                    <p className="text-base font-medium text-gray-700 dark:text-gray-300">
                      Scanning {selectedFiles.length} PDF file(s)...
                    </p>
                  </div>
                ) : (
                  <>
                    <svg
                      className="mx-auto h-16 w-16 text-gray-400 dark:text-gray-500"
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
                    <h2 className="mt-4 text-2xl font-semibold text-gray-900 dark:text-white">Upload PDF Documents</h2>
                    <p className="mt-2 text-base text-gray-600 dark:text-gray-400" id="upload-instructions">
                      Drag and drop your PDFs here or click to browse
                    </p>
                    <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                      You can select multiple files at once
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf"
                      multiple
                      onChange={handleFileInput}
                      className="hidden"
                      disabled={isScanning}
                      aria-label="Choose PDF files to upload for accessibility scanning"
                    />
                  </>
                )}
              </div>

              {selectedFiles.length > 0 && !isScanning && (
                <div className="mt-6 space-y-4">
                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                    <p className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-3 flex items-center gap-2">
                      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                        <path
                          fillRule="evenodd"
                          d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
                          clipRule="evenodd"
                        />
                      </svg>
                      {selectedFiles.length} file{selectedFiles.length > 1 ? "s" : ""} selected
                    </p>
                    <ul className="text-xs text-blue-800 dark:text-blue-200 space-y-1.5 max-h-40 overflow-y-auto">
                      {selectedFiles.map((file, idx) => (
                        <li key={idx} className="truncate flex items-center gap-2">
                          <span className="w-1 h-1 bg-blue-600 dark:bg-blue-400 rounded-full flex-shrink-0"></span>
                          {file.name}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <fieldset className="bg-white dark:bg-gray-900/30 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                    <legend className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
                      Scanning preference
                    </legend>
                    <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">
                      Choose whether to scan your uploads right away or start the scan later.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-3" role="radiogroup" aria-label="Scanning preference">
                      <label
                        className={`flex-1 relative flex items-start gap-3 rounded-lg border px-4 py-3 cursor-pointer transition-colors ${
                          scanMode === "scan-now"
                            ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30"
                            : "border-gray-300 dark:border-gray-600 hover:border-indigo-400 dark:hover:border-indigo-500"
                        }`}
                      >
                        <input
                          type="radio"
                          name="scan-mode"
                          value="scan-now"
                          checked={scanMode === "scan-now"}
                          onChange={() => handleScanModeChange("scan-now")}
                          className="mt-1 h-4 w-4 text-indigo-600 border-gray-300 focus:ring-indigo-500"
                        />
                        <div className="text-left">
                          <span className="block text-sm font-semibold text-gray-900 dark:text-gray-100">
                            Upload and scan now
                          </span>
                          <span className="block text-xs text-gray-600 dark:text-gray-400">
                            Recommended for quick accessibility insights.
                          </span>
                        </div>
                      </label>

                      <label
                        className={`flex-1 relative flex items-start gap-3 rounded-lg border px-4 py-3 cursor-pointer transition-colors ${
                          scanMode === "upload-only"
                            ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30"
                            : "border-gray-300 dark:border-gray-600 hover:border-indigo-400 dark:hover:border-indigo-500"
                        }`}
                      >
                        <input
                          type="radio"
                          name="scan-mode"
                          value="upload-only"
                          checked={scanMode === "upload-only"}
                          onChange={() => handleScanModeChange("upload-only")}
                          className="mt-1 h-4 w-4 text-indigo-600 border-gray-300 focus:ring-indigo-500"
                        />
                        <div className="text-left">
                          <span className="block text-sm font-semibold text-gray-900 dark:text-gray-100">
                            Upload only
                          </span>
                          <span className="block text-xs text-gray-600 dark:text-gray-400">
                            Files will be available in your dashboard with an option to begin scanning later.
                          </span>
                        </div>
                      </label>
                    </div>
                  </fieldset>

                  <button
                    onClick={handleUploadWithGroup}
                    disabled={!selectedGroup}
                    className="w-full px-6 py-3.5 text-base font-semibold text-white bg-gradient-indigo rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:shadow-lg disabled:hover:shadow-none focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
                    aria-label={
                      !selectedGroup
                        ? "Select a group before uploading"
                        : `Upload ${selectedFiles.length} file${selectedFiles.length > 1 ? "s" : ""} to selected group`
                    }
                  >
                    {!selectedGroup ? (
                      <span className="flex items-center justify-center gap-2">
                        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                          <path
                            fillRule="evenodd"
                            d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                            clipRule="evenodd"
                          />
                        </svg>
                        Select a group to upload
                      </span>
                    ) : (
                      <span className="flex items-center justify-center gap-2">
                        <svg
                          className="w-5 h-5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                          aria-hidden="true"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                          />
                        </svg>
                        Upload {selectedFiles.length} file{selectedFiles.length > 1 ? "s" : ""}
                      </span>
                    )}
                  </button>
                </div>
              )}

              {error && (
                <div
                  className="mt-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg"
                  role="alert"
                  aria-live="assertive"
                  aria-atomic="true"
                >
                  <p className="text-sm text-red-800 dark:text-red-200 flex items-start gap-2">
                    <svg
                      className="w-5 h-5 flex-shrink-0 mt-0.5"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                      aria-hidden="true"
                    >
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm8.707-7.293a1 1 0 00-1.414-1.414L11 12.586l-1.293-1.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                        clipRule="evenodd"
                      />
                    </svg>
                    <span>
                      <span className="font-semibold">Error: </span>
                      {error}
                    </span>
                  </p>
                </div>
              )}

              {/* What we scan for section */}
              <div className="mt-8 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-6">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                  <svg
                    className="w-5 h-5 text-primary-600 dark:text-primary-400"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                    aria-hidden="true"
                  >
                    <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                    <path
                      fillRule="evenodd"
                      d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm9.707 5.707a1 1 0 00-1.414-1.414L9 12.586l-1.293-1.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  What we scan for
                </h3>
                <ul
                  className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs text-gray-600 dark:text-gray-400"
                  role="list"
                >
                  <li className="flex items-start gap-2">
                    <svg
                      className="w-4 h-4 text-primary-500 mt-0.5 flex-shrink-0"
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
                    <span>Missing document metadata and title</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <svg
                      className="w-4 h-4 text-primary-500 mt-0.5 flex-shrink-0"
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
                    <span>Untagged content and improper structure</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <svg
                      className="w-4 h-4 text-primary-500 mt-0.5 flex-shrink-0"
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
                    <span>Missing alternative text for images</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <svg
                      className="w-4 h-4 text-primary-500 mt-0.5 flex-shrink-0"
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
                    <span>Poor text contrast ratios</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <svg
                      className="w-4 h-4 text-primary-500 mt-0.5 flex-shrink-0"
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
                    <span>Missing language declarations</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <svg
                      className="w-4 h-4 text-primary-500 mt-0.5 flex-shrink-0"
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
                    <span>Form field accessibility issues</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <svg
                      className="w-4 h-4 text-primary-500 mt-0.5 flex-shrink-0"
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
                    <span>Table structure and header problems</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>

      <UploadProgressToast uploads={uploadProgress} onRemove={handleRemoveUpload} />
    </>
  )
}
