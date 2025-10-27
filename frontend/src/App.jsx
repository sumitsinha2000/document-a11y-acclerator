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
      <header className="bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700 sticky top-0 z-50 h-14">
        <div className="h-full px-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {currentView === "report" && (
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                aria-label="Toggle sidebar"
              >
                <svg
                  className="w-5 h-5 text-gray-600 dark:text-gray-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
            )}
            <h1 className="text-base font-semibold text-gray-900 dark:text-white">Doc A11y Accelerator</h1>
          </div>

          <div className="flex items-center gap-3">
            <button
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                currentView === "upload"
                  ? "bg-blue-600 text-white"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
              }`}
              onClick={handleBackToUpload}
            >
              Upload
            </button>
            <button
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                currentView === "generator"
                  ? "bg-blue-600 text-white"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
              }`}
              onClick={handleViewGenerator}
            >
              Generator
            </button>
            <button
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                currentView === "history"
                  ? "bg-blue-600 text-white"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
              }`}
              onClick={handleViewHistory}
            >
              History
            </button>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="pt-0">
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
