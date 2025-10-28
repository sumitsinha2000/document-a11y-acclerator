"use client"

import { useState, useEffect } from "react"
import axios from "axios"
import "./App.css"
import UploadArea from "./components/UploadArea"
import History from "./components/History"
import ReportViewer from "./components/ReportViewer"
import ThemeToggle from "./components/ThemeToggle"
import PDFGenerator from "./components/PDFGenerator"
import BatchReportViewer from "./components/BatchReportViewer"

function App() {
  const [currentView, setCurrentView] = useState("upload")
  const [scanHistory, setScanHistory] = useState([])
  const [scanResults, setScanResults] = useState([])
  const [currentBatch, setCurrentBatch] = useState(null)
  const [loading, setLoading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  useEffect(() => {
    fetchScanHistory()
  }, [])

  const fetchScanHistory = async () => {
    try {
      const response = await axios.get("/api/scans")
      setScanHistory(response.data.scans)
    } catch (error) {
      console.error("Error fetching scan history:", error)
    }
  }

  const handleScanComplete = (scanDataArray) => {
    console.log("[v0] handleScanComplete called with:", scanDataArray)
    console.log("[v0] scanDataArray length:", scanDataArray.length)
    console.log("[v0] scanDataArray[0]:", scanDataArray[0])

    if (!scanDataArray || scanDataArray.length === 0) {
      console.error("[v0] ERROR: scanDataArray is empty or invalid")
      alert("No scan results received. Please check the console for errors.")
      return
    }

    setScanResults(scanDataArray)

    if (scanDataArray.length > 1 && scanDataArray[0].batchId) {
      console.log("[v0] Multiple files with batchId detected, switching to batch view")
      setCurrentBatch({
        batchId: scanDataArray[0].batchId,
        scans: scanDataArray,
      })
      setCurrentView("batch")
    } else if (scanDataArray.length > 1) {
      console.log("[v0] Multiple files without batchId, creating temporary batch")
      const tempBatchId = `temp_batch_${Date.now()}`
      const scansWithBatchId = scanDataArray.map((scan) => ({
        ...scan,
        batchId: tempBatchId,
      }))
      setCurrentBatch({
        batchId: tempBatchId,
        scans: scansWithBatchId,
      })
      setScanResults(scansWithBatchId)
      setCurrentView("batch")
    } else {
      console.log("[v0] Single file, switching to report view")
      setCurrentView("report")
    }

    fetchScanHistory()
  }

  const handleViewHistory = () => {
    setCurrentView("history")
  }

  const handleSelectScan = async (scan) => {
    console.log("[v0] Selected scan from history:", scan)

    try {
      setLoading(true)
      console.log("[v0] Fetching scan details from:", `/api/scan/${scan.id}`)
      const response = await axios.get(`/api/scan/${scan.id}`)
      console.log("[v0] API Response received:", response)
      console.log("[v0] Response data:", response.data)

      setScanResults([response.data])
      setCurrentView("report")
    } catch (error) {
      console.error("[v0] Error loading scan details:", error)
      console.error("[v0] Error response:", error.response)
      alert("Failed to load scan details: " + (error.response?.data?.error || error.message))
    } finally {
      setLoading(false)
    }
  }

  const handleSelectBatch = async (batchId) => {
    console.log("[v0] Selected batch from history:", batchId)

    try {
      setLoading(true)
      console.log("[v0] Fetching batch details from:", `/api/batch/${batchId}`)
      const response = await axios.get(`/api/batch/${batchId}`)
      console.log("[v0] Batch data received:", response.data)

      setCurrentBatch({
        batchId: batchId,
        scans: response.data.scans || [],
      })
      setCurrentView("batch")
    } catch (error) {
      console.error("[v0] Error loading batch details:", error)
      alert("Failed to load batch details: " + (error.response?.data?.error || error.message))
    } finally {
      setLoading(false)
    }
  }

  const handleBackToUpload = () => {
    setCurrentView("upload")
    setScanResults([])
    setCurrentBatch(null)
  }

  const handleViewGenerator = () => {
    setCurrentView("generator")
  }

  const handleBatchUpdate = async (batchId) => {
    try {
      console.log("[v0] Refreshing batch data:", batchId)
      const response = await axios.get(`/api/batch/${batchId}`)
      console.log("[v0] Updated batch data received:", response.data)

      setCurrentBatch({
        batchId: batchId,
        scans: response.data.scans || [],
      })
    } catch (error) {
      console.error("[v0] Error refreshing batch data:", error)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header
        role="banner"
        className="bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700 sticky top-0 z-50 h-14"
      >
        <div className="h-full px-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {currentView === "report" && (
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
                aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
                aria-expanded={sidebarOpen}
              >
                <svg
                  className="w-5 h-5 text-gray-600 dark:text-gray-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
            )}
            <h1 className="text-base font-semibold text-gray-900 dark:text-white inline-flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary" aria-hidden="true">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="lucide lucide-file-text h-5 w-5 text-primary-foreground"
                  aria-hidden="true"
                >
                  <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
                  <path d="M14 2v4a2 2 0 0 0 2 2h4" />
                  <path d="M10 9H8" />
                  <path d="M16 13H8" />
                  <path d="M16 17H8" />
                </svg>
              </div>
              Doc A11y Accelerator
            </h1>
            <div
              className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg"
              role="status"
              aria-label="Version Beta 1.0"
            >
              <svg
                className="w-4 h-4 text-blue-600 dark:text-blue-400"
                viewBox="0 0 24 24"
                width="16"
                xmlns="http://www.w3.org/2000/svg"
                aria-hidden="true"
              >
                <path
                  d="M21.6,9.84A4.57,4.57,0,0,1,21.18,9,4,4,0,0,1,21,8.07a4.21,4.21,0,0,0-.64-2.16,4.25,4.25,0,0,0-1.87-1.28,4.77,4.77,0,0,1-.85-.43A5.11,5.11,0,0,1,17,3.54a4.2,4.2,0,0,0-1.8-1.4A4.22,4.22,0,0,0,13,2.21a4.24,4.24,0,0,1-1.94,0,4.22,4.22,0,0,0-2.24-.07A4.2,4.2,0,0,0,7,3.54a5.11,5.11,0,0,1-.66.66,4.77,4.77,0,0,1-.85.43A4.25,4.25,0,0,0,3.61,5.91,4.21,4.21,0,0,0,3,8.07,4,4,0,0,1,2.82,9a4.57,4.57,0,0,1-.42.82A4.3,4.3,0,0,0,1.63,12a4.3,4.3,0,0,0,.77,2.16,4,4,0,0,1,.42.82,4.11,4.11,0,0,1,.15.95,4.19,4.19,0,0,0,.64,2.16,4.25,4.25,0,0,0,1.87,1.28,4.77,4.77,0,0,1,.85.43,5.11,5.11,0,0,1,.66.66,4.12,4.12,0,0,0,1.8,1.4,3,3,0,0,0,.87.13A6.66,6.66,0,0,0,11,21.81a4,4,0,0,1,1.94,0,4.33,4.33,0,0,0,2.24.06,4.12,4.12,0,0,0,1.8-1.4,5.11,5.11,0,0,1,.66-.66,4.77,4.77,0,0,1,.85-.43,4.25,4.25,0,0,0,1.87-1.28A4.19,4.19,0,0,0,21,15.94a4.11,4.11,0,0,1,.15-.95,4.57,4.57,0,0,1,.42-.82A4.3,4.3,0,0,0,22.37,12,4.3,4.3,0,0,0,21.6,9.84Zm-4.89.87-5,5a1,1,0,0,1-1.42,0l-3-3a1,1,0,1,1,1.42-1.42L11,13.59l4.29-4.3a1,1,0,0,1,1.42,1.42Z"
                  style={{ fill: "#1d4ed8" }}
                  clipRule="evenodd"
                />
              </svg>
              <span className="text-sm font-medium text-blue-700 dark:text-blue-300">Beta 1.0</span>
            </div>
          </div>

          <nav className="flex items-center gap-3" role="navigation" aria-label="Main navigation">
            <button
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900 ${
                currentView === "upload"
                  ? "bg-blue-600 text-white"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
              }`}
              onClick={handleBackToUpload}
              aria-current={currentView === "upload" ? "page" : undefined}
            >
              Upload
            </button>
            <button
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900 ${
                currentView === "generator"
                  ? "bg-blue-600 text-white"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
              }`}
              onClick={handleViewGenerator}
              aria-current={currentView === "generator" ? "page" : undefined}
            >
              Generator
            </button>
            <button
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900 ${
                currentView === "history"
                  ? "bg-blue-600 text-white"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
              }`}
              onClick={handleViewHistory}
              aria-current={currentView === "history" ? "page" : undefined}
            >
              History
            </button>
            <ThemeToggle />
          </nav>
        </div>
      </header>

      <main className="pt-0" role="main">
        {currentView === "upload" && <UploadArea onScanComplete={handleScanComplete} />}
        {currentView === "generator" && <PDFGenerator />}
        {currentView === "history" && (
          <History
            scans={scanHistory}
            onSelectScan={handleSelectScan}
            onSelectBatch={handleSelectBatch}
            onBack={handleBackToUpload}
          />
        )}
        {currentView === "batch" && currentBatch && (
          <BatchReportViewer
            batchId={currentBatch.batchId}
            scans={currentBatch.scans}
            onBack={handleBackToUpload}
            onBatchUpdate={handleBatchUpdate}
          />
        )}
        {currentView === "report" && scanResults.length > 0 && (
          <ReportViewer scans={scanResults} onBack={handleBackToUpload} sidebarOpen={sidebarOpen} />
        )}
      </main>
    </div>
  )
}

export default App
