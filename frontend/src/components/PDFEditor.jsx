"use client"

import { useState, useEffect, useRef } from "react"
import { Document, Page, pdfjs } from "react-pdf"
import axios from "axios"
import "react-pdf/dist/esm/Page/AnnotationLayer.css"
import "react-pdf/dist/esm/Page/TextLayer.css"

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`

export default function PDFEditor({ scanId, filename, fixes, onClose, onFixApplied }) {
  const [numPages, setNumPages] = useState(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [pdfUrl, setPdfUrl] = useState(null)
  const [selectedFix, setSelectedFix] = useState(null)
  const [fixData, setFixData] = useState({})
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)
  const [appliedFixes, setAppliedFixes] = useState([])
  const [pageDimensions, setPageDimensions] = useState({ width: 600, height: 800 })
  const pageRef = useRef(null)

  useEffect(() => {
    setPdfUrl(`/api/pdf-file/${scanId}`)
    console.log("[v0] PDFEditor - Received fixes:", fixes)
    console.log("[v0] PDFEditor - Semi-automated fixes:", fixes?.semiAutomated)
    console.log("[v0] PDFEditor - Manual fixes:", fixes?.manual)
  }, [scanId, fixes])

  const onDocumentLoadSuccess = ({ numPages }) => {
    setNumPages(numPages)
  }

  const onPageLoadSuccess = (page) => {
    const { width, height } = page
    setPageDimensions({ width, height })
  }

  const handleFixSelect = (fix) => {
    setSelectedFix(fix)
    setFixData({})
    setMessage(null)

    if (fix.page) {
      setPageNumber(fix.page)
    } else if (fix.pages && fix.pages.length > 0) {
      setPageNumber(fix.pages[0])
    }
  }

  const handleInputChange = (field, value) => {
    setFixData((prev) => ({ ...prev, [field]: value }))
  }

  const getFixType = (fix) => {
    const action = fix.action || fix.title || ""

    if (action.toLowerCase().includes("alt text") || action.toLowerCase().includes("image")) {
      return "addAltText"
    } else if (action.toLowerCase().includes("tag") || action.toLowerCase().includes("structure")) {
      return "tagContent"
    } else if (action.toLowerCase().includes("table")) {
      return "fixTableStructure"
    } else if (action.toLowerCase().includes("form") || action.toLowerCase().includes("label")) {
      return "addFormLabel"
    }

    return fix.type || "unknown"
  }

  const handleApplyFix = async () => {
    if (!selectedFix) return

    setLoading(true)
    setMessage(null)

    const fixType = getFixType(selectedFix)

    console.log("[v0] PDFEditor - Applying fix:", selectedFix)
    console.log("[v0] PDFEditor - Fix type:", fixType)
    console.log("[v0] PDFEditor - Fix data:", fixData)

    try {
      const response = await axios.post(`/api/apply-manual-fix/${scanId}`, {
        fixType: fixType,
        fixData: fixData,
        page: pageNumber,
      })

      console.log("[v0] PDFEditor - Fix applied successfully:", response.data)
      console.log("[v0] PDFEditor - Response summary:", response.data.summary)
      console.log("[v0] PDFEditor - Response results:", response.data.results)

      setMessage({ type: "success", text: response.data.message || "Fix applied successfully!" })

      setAppliedFixes((prev) => [
        ...prev,
        {
          ...selectedFix,
          appliedAt: new Date(),
          page: pageNumber,
          fixType: fixType,
        },
      ])

      setPdfUrl(`/api/pdf-file/${scanId}?t=${Date.now()}`)

      if (onFixApplied) {
        console.log("[v0] PDFEditor - Calling onFixApplied callback with new data...")
        await new Promise((resolve) => setTimeout(resolve, 300))
        await onFixApplied(selectedFix, response.data.summary, response.data.results)
        console.log("[v0] PDFEditor - onFixApplied callback completed")
      } else {
        console.warn("[v0] PDFEditor - No onFixApplied callback provided")
      }

      setFixData({})
      setSelectedFix(null)
    } catch (error) {
      console.error("[v0] PDFEditor - Error applying fix:", error)
      console.error("[v0] PDFEditor - Error response:", error.response?.data)
      setMessage({
        type: "error",
        text: error.response?.data?.error || "Failed to apply fix",
      })
    } finally {
      setLoading(false)
    }
  }

  const renderFixForm = () => {
    if (!selectedFix) {
      return (
        <div className="text-center text-gray-500 dark:text-gray-400 py-8">
          Select a fix from the list to get started
        </div>
      )
    }

    const fixType = getFixType(selectedFix)

    switch (fixType) {
      case "addAltText":
        return (
          <div className="space-y-4">
            <h4 className="font-semibold text-gray-900 dark:text-white">Add Alt Text to Image</h4>
            <p className="text-sm text-gray-600 dark:text-gray-400">{selectedFix.description}</p>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Image Number (on current page)
              </label>
              <input
                type="number"
                min="1"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                value={fixData.imageIndex || ""}
                onChange={(e) => handleInputChange("imageIndex", e.target.value)}
                placeholder="e.g., 1"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Alt Text Description
              </label>
              <textarea
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                rows="3"
                value={fixData.altText || ""}
                onChange={(e) => handleInputChange("altText", e.target.value)}
                placeholder="Describe the image content..."
              />
            </div>
          </div>
        )

      case "tagContent":
        return (
          <div className="space-y-4">
            <h4 className="font-semibold text-gray-900 dark:text-white">Tag Content Structure</h4>
            <p className="text-sm text-gray-600 dark:text-gray-400">{selectedFix.description}</p>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Content Type</label>
              <select
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                value={fixData.tagType || ""}
                onChange={(e) => handleInputChange("tagType", e.target.value)}
              >
                <option value="">Select tag type...</option>
                <option value="H1">Heading 1</option>
                <option value="H2">Heading 2</option>
                <option value="H3">Heading 3</option>
                <option value="P">Paragraph</option>
                <option value="List">List</option>
                <option value="Table">Table</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Text Content (or identifier)
              </label>
              <textarea
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                rows="2"
                value={fixData.content || ""}
                onChange={(e) => handleInputChange("content", e.target.value)}
                placeholder="Enter the text to tag..."
              />
            </div>
          </div>
        )

      case "fixTableStructure":
        return (
          <div className="space-y-4">
            <h4 className="font-semibold text-gray-900 dark:text-white">Fix Table Structure</h4>
            <p className="text-sm text-gray-600 dark:text-gray-400">{selectedFix.description}</p>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Table Number (on current page)
              </label>
              <input
                type="number"
                min="1"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                value={fixData.tableIndex || ""}
                onChange={(e) => handleInputChange("tableIndex", e.target.value)}
                placeholder="e.g., 1"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Number of Header Rows
              </label>
              <input
                type="number"
                min="0"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                value={fixData.headerRows || ""}
                onChange={(e) => handleInputChange("headerRows", e.target.value)}
                placeholder="e.g., 1"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Header Scope</label>
              <select
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                value={fixData.scope || ""}
                onChange={(e) => handleInputChange("scope", e.target.value)}
              >
                <option value="">Select scope...</option>
                <option value="col">Column</option>
                <option value="row">Row</option>
                <option value="both">Both</option>
              </select>
            </div>
          </div>
        )

      case "addFormLabel":
        return (
          <div className="space-y-4">
            <h4 className="font-semibold text-gray-900 dark:text-white">Add Form Field Label</h4>
            <p className="text-sm text-gray-600 dark:text-gray-400">{selectedFix.description}</p>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Field Name/ID</label>
              <input
                type="text"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                value={fixData.fieldName || ""}
                onChange={(e) => handleInputChange("fieldName", e.target.value)}
                placeholder="e.g., email, phone"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Label Text</label>
              <input
                type="text"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                value={fixData.label || ""}
                onChange={(e) => handleInputChange("label", e.target.value)}
                placeholder="e.g., Email Address"
              />
            </div>
          </div>
        )

      default:
        return (
          <div className="text-center text-gray-500 dark:text-gray-400 py-8">
            <p className="mb-2">This fix type is not yet supported in the editor</p>
            <p className="text-xs">Fix type: {fixType}</p>
            <p className="text-xs">Action: {selectedFix.action}</p>
          </div>
        )
    }
  }

  const getHighlightColor = (severity) => {
    switch (severity?.toLowerCase()) {
      case "high":
        return "rgba(239, 68, 68, 0.3)" // red
      case "medium":
        return "rgba(251, 191, 36, 0.3)" // yellow
      case "low":
        return "rgba(59, 130, 246, 0.3)" // blue
      default:
        return "rgba(147, 51, 234, 0.3)" // purple
    }
  }

  const renderHighlight = () => {
    if (!selectedFix || !selectedFix.location) return null

    const { page, pages } = selectedFix.location
    const currentPage = page || (pages && pages[0])

    // Only show highlight if we're on the correct page
    if (currentPage !== pageNumber) return null

    // Full page highlight for issues without specific coordinates
    return (
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: getHighlightColor(selectedFix.severity),
          border: `3px solid ${getHighlightColor(selectedFix.severity).replace("0.3", "0.8")}`,
          pointerEvents: "none",
          zIndex: 10,
          borderRadius: "4px",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: "10px",
            left: "10px",
            backgroundColor: "rgba(0, 0, 0, 0.8)",
            color: "white",
            padding: "8px 12px",
            borderRadius: "4px",
            fontSize: "14px",
            fontWeight: "bold",
            maxWidth: "80%",
          }}
        >
          📍 {selectedFix.title || selectedFix.action}
        </div>
      </div>
    )
  }

  const fixableIssues = [...(fixes?.semiAutomated || []), ...(fixes?.manual || [])].filter(
    (fix) => fix.severity === "medium" || (!fix.severity && fix.action),
  )

  const remainingFixes = fixableIssues.filter((fix) => !appliedFixes.some((applied) => applied.type === fix.type))

  console.log("[v0] PDFEditor - Fixable issues count:", fixableIssues.length)
  console.log("[v0] PDFEditor - Applied fixes count:", appliedFixes.length)
  console.log("[v0] PDFEditor - Remaining fixes count:", remainingFixes.length)

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-7xl h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">PDF Editor</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">{filename}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              title="Close editor"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* PDF Viewer */}
          <div className="flex-1 overflow-auto bg-gray-100 dark:bg-gray-900 p-4">
            <div className="flex flex-col items-center">
              {pdfUrl ? (
                <div style={{ position: "relative" }} ref={pageRef}>
                  <Document file={pdfUrl} onLoadSuccess={onDocumentLoadSuccess} className="shadow-lg">
                    <Page pageNumber={pageNumber} width={600} onLoadSuccess={onPageLoadSuccess} />
                  </Document>
                  {renderHighlight()}
                </div>
              ) : (
                <div className="text-center text-gray-500 dark:text-gray-400 py-8">
                  <p>Loading PDF preview...</p>
                </div>
              )}

              {numPages && (
                <div className="mt-4 flex items-center gap-4 bg-white dark:bg-gray-800 px-4 py-2 rounded-lg shadow">
                  <button
                    onClick={() => setPageNumber((prev) => Math.max(1, prev - 1))}
                    disabled={pageNumber <= 1}
                    className="px-3 py-1 bg-blue-600 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    Page {pageNumber} of {numPages}
                  </span>
                  <button
                    onClick={() => setPageNumber((prev) => Math.min(numPages, prev + 1))}
                    disabled={pageNumber >= numPages}
                    className="px-3 py-1 bg-blue-600 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Fix Panel */}
          <div className="w-96 border-l border-gray-200 dark:border-gray-700 flex flex-col">
            {appliedFixes.length > 0 && (
              <div className="p-4 bg-green-50 dark:bg-green-900/20 border-b border-green-200 dark:border-green-800">
                <h4 className="font-semibold text-green-700 dark:text-green-400 mb-2 flex items-center gap-2">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  {appliedFixes.length} Fix{appliedFixes.length > 1 ? "es" : ""} Applied
                </h4>
                <div className="space-y-1 max-h-32 overflow-auto">
                  {appliedFixes.map((fix, idx) => (
                    <div key={idx} className="text-xs text-green-700 dark:text-green-400 flex items-start gap-1">
                      <span>✓</span>
                      <span>{fix.title || fix.action}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex-1 overflow-auto p-4 border-b border-gray-200 dark:border-gray-700">
              <h4 className="font-semibold text-gray-900 dark:text-white mb-3">
                Fixable Issues ({remainingFixes.length})
              </h4>
              <div className="space-y-2">
                {remainingFixes.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {appliedFixes.length > 0
                      ? "All fixable issues have been addressed!"
                      : "No fixable manual issues available"}
                  </p>
                ) : (
                  remainingFixes.map((fix, index) => (
                    <button
                      key={index}
                      onClick={() => handleFixSelect(fix)}
                      className={`w-full text-left p-3 rounded-lg border transition-all ${
                        selectedFix === fix
                          ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                          : "border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-700"
                      }`}
                    >
                      <div className="font-medium text-sm text-gray-900 dark:text-white">
                        <span className="inline-flex items-center gap-1">
                          {fix.action || fix.title}
                          {(fix.page || (fix.pages && fix.pages.length > 0)) && (
                            <span className="text-xs bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded">
                              Page {fix.page || fix.pages[0]}
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                        {fix.estimatedTime && `${fix.estimatedTime} min`}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>

            {/* Fix Form */}
            <div className="p-4 overflow-auto">
              {renderFixForm()}

              {message && (
                <div
                  className={`mt-4 p-3 rounded-lg text-sm ${
                    message.type === "success"
                      ? "bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400"
                      : "bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400"
                  }`}
                >
                  {message.text}
                </div>
              )}

              {selectedFix && (
                <button
                  onClick={handleApplyFix}
                  disabled={loading}
                  className="w-full mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? "Applying..." : "Apply Fix"}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
