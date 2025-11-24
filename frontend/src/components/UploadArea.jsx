"use client"

import { useState, useRef, useEffect } from "react"
import axios from "axios"
import UploadProgressToast from "./UploadProgressToast"
import { API_ENDPOINTS } from "../config/api"

const formatFileSize = (bytes) => {
  if (bytes === 0) return "0 Bytes"
  const k = 1024
  const sizes = ["Bytes", "KB", "MB", "GB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
}

export default function UploadArea({
  onUploadDeferred,
  autoSelectGroupId = null,
  autoSelectFolderId = null,
}) {
  const [isDragging, setIsDragging] = useState(false)
  const [isScanning, setIsScanning] = useState(false)
  const [error, setError] = useState(null)
  const [uploadProgress, setUploadProgress] = useState([])
  const [srAnnouncement, setSrAnnouncement] = useState("")
  const fileInputRef = useRef(null)
  const uploadAreaRef = useRef(null)
  const [selectedFiles, setSelectedFiles] = useState([])
  const [previewFile, setPreviewFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl)
      }
    }
  }, [previewUrl])
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
      `${pdfFiles.length} PDF ${pdfFiles.length === 1 ? "file" : "files"} selected. Please select a folder from the dashboard before uploading.`,
    )
  }

  const handleRemoveSelectedFile = (index) => {
    setSelectedFiles((prev) => {
      const updated = prev.filter((_, idx) => idx !== index)
      setSrAnnouncement(
        `${updated.length} PDF ${updated.length === 1 ? "file" : "files"} selected after removing a file.`,
      )
      if (!updated.length) {
        handleClosePreview()
      } else if (previewFile && updated.every((file) => file !== previewFile)) {
        handleClosePreview()
      }
      return updated
    })
  }

  const handleOpenPreview = (file) => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
    }
    const url = URL.createObjectURL(file)
    setPreviewFile(file)
    setPreviewUrl(url)
    setSrAnnouncement(`Previewing ${file.name}`)
  }

  const handleClosePreview = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
    }
    setPreviewFile(null)
    setPreviewUrl(null)
  }

  const resolveGroupId = () => {
    if (!autoSelectGroupId) return null
    if (typeof autoSelectGroupId === "object") {
      return autoSelectGroupId.id || autoSelectGroupId.group_id || autoSelectGroupId.value || null
    }
    return autoSelectGroupId
  }

  const handleUploadWithGroup = async () => {
    const groupId = resolveGroupId()
    if (!groupId) {
      const message = "Select a folder from the dashboard before uploading"
      setError(message)
      setSrAnnouncement(`Error: ${message}`)
      return
    }

    if (selectedFiles.length === 0) {
      setError("No files selected")
      return
    }

    await handleMultipleFileUpload(selectedFiles)
  }

  const handleMultipleFileUpload = async (files) => {
    if (!files || files.length === 0) {
      return
    }
    setError(null)
    setIsScanning(true)

    const isBatch = files.length > 1
    const groupId = resolveGroupId()
    const folderId = autoSelectFolderId
    setSrAnnouncement(
      `Uploading ${files.length} PDF file${files.length === 1 ? '' : 's'} without scanning`,
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
        if (folderId) {
          formData.append('folder_id', folderId)
        }
        formData.append('scan_mode', 'upload_only')

        setUploadProgress((prev) =>
          prev.map((item) => ({
            ...item,
            status: 'uploading',
            progress: 80,
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

        const uploadedCount = scanIds.length || files.length
        setError(null)
        setSrAnnouncement(
          `Uploaded ${uploadedCount} file${uploadedCount === 1 ? '' : 's'}. Start scanning later from the dashboard.`,
        )
        onUploadDeferred?.({
          batchId: response.data.batchId,
          scanIds,
          groupId,
        })
      } catch (err) {
        const errorMsg = err.response?.data?.error || err.message || 'Folder upload failed'
        console.error('[UploadArea] Folder upload error:', err)
        handleError(errorMsg)
      } finally {
        finalize()
      }
      return
    }

    const file = files[0]
    const endpoint = API_ENDPOINTS.upload
    const timeout = 120000

    try {
      const formData = new FormData()
      formData.append('file', file)
      if (groupId) {
        formData.append('group_id', groupId)
      }
      if (folderId) {
        formData.append('folder_id', folderId)
      }
      formData.append('scan_mode', 'upload_only')

      setUploadProgress((prev) =>
        prev.map((item, idx) =>
          idx === 0
            ? {
                ...item,
                status: 'uploading',
                progress: 80,
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

      const deferredId = response.data?.scanId || response.data?.result?.scanId
      const scanIds = deferredId ? [deferredId] : []
      setError(null)
      setSrAnnouncement(`Uploaded ${scanIds.length || 1} file${scanIds.length === 1 ? '' : 's'} successfully.`)
      onUploadDeferred?.({
        scanIds,
        groupId,
        batchId: response.data?.batchId || response.data?.folderId,
        folderName: response.data?.folderName,
      })
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
  const uploadReady = Boolean(resolveGroupId())
  return (
    <>
      <div className="w-full">
        <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {srAnnouncement}
        </div>

        <div className="space-y-6">
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 lg:p-8 transition-colors">
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
              aria-label="Upload PDF documents. Drag and drop files here or press Enter or Space to browse files. Multiple files can be selected."
              aria-busy={isScanning}
              aria-disabled={isScanning}
              aria-describedby="upload-instructions"
            >
              {isScanning ? (
                <div className="space-y-4">
                  <div
                    className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-primary-500 border-t-transparent"
                    role="status"
                    aria-label="Uploading in progress"
                  ></div>
                  <p className="text-base font-medium text-gray-700 dark:text-gray-300">
                    Uploading {selectedFiles.length} PDF file(s)...
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
                    Drag and drop or <span className="text-indigo-600 dark:text-indigo-400">click to browse</span>
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
          </div>

          {selectedFiles.length > 0 && !isScanning && (
            <div className="space-y-4">
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <p className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-3 flex items-center gap-2">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                    <path
                      fillRule="evenodd"
                      d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  {selectedFiles.length} file{selectedFiles.length > 1 ? "s" : ""} ready for upload
                </p>
                <div className="space-y-3">
                  {selectedFiles.map((file, idx) => (
                    <div
                      key={`${file.name}-${file.size}-${file.lastModified}-${idx}`}
                      className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 px-3 py-2 rounded-lg border border-blue-100 bg-white/70 dark:bg-slate-900/60 dark:border-slate-700"
                    >
                      <div className="truncate">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{file.name}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          {formatFileSize(file.size)}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => handleOpenPreview(file)}
                          className="text-xs font-semibold px-3 py-1.5 rounded-full border border-indigo-500 text-indigo-600 hover:bg-indigo-500 hover:text-white transition"
                        >
                          Preview
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRemoveSelectedFile(idx)}
                          className="text-xs font-semibold px-3 py-1.5 rounded-full border border-red-400 text-red-600 hover:bg-red-500 hover:text-white transition"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="text-center">
                <button
                  onClick={handleUploadWithGroup}
                  disabled={!uploadReady}
                  className="w-full max-w-md mx-auto px-6 py-3.5 text-base font-semibold text-white bg-gradient-indigo rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:shadow-lg disabled:hover:shadow-none focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
                  aria-label={
                    !uploadReady
                      ? "Select a folder before uploading"
                      : `Upload ${selectedFiles.length} file${selectedFiles.length > 1 ? "s" : ""}`
                  }
                >
                  {!uploadReady ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                        <path
                          fillRule="evenodd"
                          d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                          clipRule="evenodd"
                        />
                      </svg>
                      Select a folder to upload
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
        </div>
      </div>
      {previewFile && previewUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 px-4 py-6"
          role="dialog"
          aria-modal="true"
          aria-labelledby="preview-dialog-title"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation()
              handleClosePreview()
            }
          }}
        >
          <div className="relative w-full max-w-4xl rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
            <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-slate-200 dark:border-slate-800">
              <div>
                <p id="preview-dialog-title" className="text-sm font-semibold text-slate-900 dark:text-white truncate">
                  Previewing {previewFile.name}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">{formatFileSize(previewFile.size)}</p>
              </div>
              <button
                type="button"
                className="text-sm font-semibold text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
                onClick={handleClosePreview}
              >
                Close
              </button>
            </div>
            <div className="relative h-[60vh] min-h-[300px]">
              <iframe
                src={previewUrl}
                className="h-full w-full border-none"
                title={`Preview of ${previewFile.name}`}
              />
            </div>
          </div>
        </div>
      )}
      <UploadProgressToast uploads={uploadProgress} onRemove={handleRemoveUpload} />
    </>
  )
}
