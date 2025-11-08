import { useState, useEffect, lazy, Suspense, useCallback } from "react"
import axios from "axios"
import "./App.css"
import LoadingScreen from "./components/LoadingScreen"
import UploadArea from "./components/UploadArea"
import ThemeToggle from "./components/ThemeToggle"
import { NotificationProvider, useNotification } from "./contexts/NotificationContext"
import NotificationContainer from "./components/NotificationContainer"
import API_BASE_URL from "../config/api"
import ErrorBoundary from "./components/ErrorBoundary"

const History = lazy(() => import("./components/History"))
const ReportViewer = lazy(() => import("./components/ReportViewer"))
const PDFGenerator = lazy(() => import("./components/PDFGenerator"))
const BatchReportViewer = lazy(() => import("./components/BatchReportViewer"))
const GroupDashboard = lazy(() => import("./components/GroupDashboard"))
const GroupMaster = lazy(() => import("./components/GroupMaster"))

const ComponentLoader = () => (
  <div className="flex items-center justify-center h-64">
    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
  </div>
)

function AppContent() {
  const { showError, showSuccess } = useNotification()

  console.log("[v0] AppContent rendering")

  const [isLoading, setIsLoading] = useState(true)
  const [currentView, setCurrentView] = useState("upload")
  const [scanHistory, setScanHistory] = useState([])
  const [scanResults, setScanResults] = useState([])
  const [currentBatch, setCurrentBatch] = useState(null)
  const [loading, setLoading] = useState(false)
  const [selectedGroupId, setSelectedGroupId] = useState(null)
  
  const fetchScanHistory = useCallback(async () => {
    try {
      console.log("[v0] Fetching scan history...")
      const response = await axios.get(`${API_BASE_URL}/api/scans`)
      setScanHistory(response.data.scans)
    } catch (error) {
      console.error("[v0] Error fetching scan history:", error)
    }
  }, [])

  useEffect(() => {
    console.log("[v0] AppContent mounted, fetching scan history")
    fetchScanHistory()
  }, [fetchScanHistory])

  const handleLoadingComplete = () => {
    console.log("[v0] Loading complete")
    setIsLoading(false)
  }

  if (isLoading) {
    return <LoadingScreen onComplete={handleLoadingComplete} />
  }

  const handleScanComplete = (scanDataArray) => {
    if (!scanDataArray || scanDataArray.length === 0) {
      console.error("ERROR: scanDataArray is empty or invalid")
      showError("No scan results received. Please check the console for errors.")
      return
    }

    setScanResults(scanDataArray)

    if (scanDataArray.length > 1 && scanDataArray[0].batchId) {
      setCurrentBatch({
        batchId: scanDataArray[0].batchId,
        scans: scanDataArray,
      })
      setCurrentView("batch")
    } else if (scanDataArray.length > 1) {
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
      setCurrentView("report")
    }

    fetchScanHistory()
  }

  const handleUploadDeferred = (details) => {
    const count = details?.scanIds?.length ?? 0
    const hasBatch = Boolean(details?.batchId)
    const message =
      count > 1
        ? `${count} files uploaded${hasBatch ? " in the batch" : ""}. Begin scanning whenever you're ready from the dashboard or history view.`
        : count === 1
          ? "File uploaded successfully. Start the scan when you're ready from the dashboard or history view."
          : "Upload completed. Start scanning whenever you're ready from the dashboard or history view."
    showSuccess(message)
    fetchScanHistory()
  }

  const handleViewHistory = () => {
    setCurrentView("history")
  }

  const handleSelectScan = async (scan) => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_BASE_URL}/api/scan/${scan.id}`)
      setScanResults([response.data])
      setCurrentView("report")
    } catch (error) {
      console.error("Error loading scan details:", error)
      showError("Failed to load scan details: " + (error.response?.data?.error || error.message))
    } finally {
      setLoading(false)
    }
  }

  const handleSelectBatch = async (batchId) => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_BASE_URL}/api/batch/${batchId}`)
      setCurrentBatch({
        batchId: batchId,
        scans: response.data.scans || [],
      })
      setCurrentView("batch")
    } catch (error) {
      console.error("Error loading batch details:", error)
      showError("Failed to load batch details: " + (error.response?.data?.error || error.message))
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
      const response = await axios.get(`${API_BASE_URL}/api/batch/${batchId}`)
      setCurrentBatch({
        batchId: batchId,
        scans: response.data.scans || [],
      })
    } catch (error) {
      console.error("Error refreshing batch data:", error)
    }
  }

  const handleOpenGroupDashboard = (groupId) => {
    setSelectedGroupId(groupId)
    setCurrentView("dashboard")
  }

  return (
    <div className="flex flex-col h-screen bg-slate-50 dark:bg-slate-900 overflow-x-hidden max-w-full">
      {/* Top Navigation Bar */}
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm flex-shrink-0">
        <div className="px-4 sm:px-6 lg:px-8 max-w-full">
          <div className="flex items-center justify-between h-16">
            {/* Logo and Brand */}
            <div className="flex items-center gap-8 min-w-0">
              <div className="flex items-center gap-3 min-w-0">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-indigo shadow-md flex-shrink-0">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-6 w-6 text-white"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                    aria-hidden="true"
                  >
                    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
                    <path d="M14 2v4a2 2 0 0 0 2 2h4" />
                  </svg>
                </div>
                <div className="min-w-0">
                  <p className="text-xl font-bold text-slate-900 dark:text-white truncate">Doc A11y Accelerator</p>
                  <p className="text-sm text-slate-600 dark:text-slate-400 truncate">PDF Accessibility Scanner</p>
                </div>
              </div>

              {/* Navigation Links */}
              <nav className="hidden md:flex items-center gap-1 flex-shrink-0">
                <button
                  onClick={handleBackToUpload}
                  className={`px-4 py-2.5 rounded-lg text-base font-semibold transition-all ${
                    currentView === "upload"
                      ? "bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400"
                      : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700/50 hover:text-slate-900 dark:hover:text-white"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                        aria-hidden="true"
                      />
                    </svg>
                    Upload
                  </span>
                </button>

                <button
                  onClick={() => setCurrentView("dashboard")}
                  className={`px-4 py-2.5 rounded-lg text-base font-semibold transition-all ${
                    currentView === "dashboard"
                      ? "bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400"
                      : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700/50 hover:text-slate-900 dark:hover:text-white"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                      />
                    </svg>
                    Dashboard
                  </span>
                </button>

                <button
                  onClick={() => setCurrentView("groups")}
                  className={`px-4 py-2.5 rounded-lg text-base font-semibold transition-all ${
                    currentView === "groups"
                      ? "bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400"
                      : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700/50 hover:text-slate-900 dark:hover:text-white"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                      />
                    </svg>
                    Groups
                  </span>
                </button>

                <button
                  onClick={handleViewHistory}
                  className={`px-4 py-2.5 rounded-lg text-base font-semibold transition-all ${
                    currentView === "history"
                      ? "bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400"
                      : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700/50 hover:text-slate-900 dark:hover:text-white"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    History
                  </span>
                </button>

                <button
                  onClick={handleViewGenerator}
                  className={`px-4 py-2.5 rounded-lg text-base font-semibold transition-all ${
                    currentView === "generator"
                      ? "bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400"
                      : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700/50 hover:text-slate-900 dark:hover:text-white"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                      />
                    </svg>
                    Generator
                  </span>
                </button>
              </nav>
            </div>

            {/* Right Side Actions */}
            <div className="flex items-center gap-3 flex-shrink-0">
              {/* Beta Badge */}
              <div className="hidden sm:flex items-center gap-2 px-3 py-2 bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-200 dark:border-indigo-800 rounded-lg">

                <svg className="w-5 h-5 text-indigo-600 dark:text-indigo-400" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M21.6,9.84A4.57,4.57,0,0,1,21.18,9,4,4,0,0,1,21,8.07a4.21,4.21,0,0,0-.64-2.16,4.25,4.25,0,0,0-1.87-1.28,4.77,4.77,0,0,1-.85-.43A5.11,5.11,0,0,1,17,3.54a4.2,4.2,0,0,0-1.8-1.4A4.22,4.22,0,0,0,13,2.07,4.2,4.2,0,0,0,11,2.14,4.2,4.2,0,0,0,9,2.07,4.22,4.22,0,0,0,6.76,2.14,4.2,4.2,0,0,0,4.96,3.54a5.11,5.11,0,0,1-.66.66,4.77,4.77,0,0,1-.85.43A4.25,4.25,0,0,0,1.58,5.91,4.21,4.21,0,0,0,.94,8.07,4,4,0,0,1,.76,9a4.57,4.57,0,0,1-.42.82A4.3,4.3,0,0,0,.57,12a4.3,4.3,0,0,0,.77,2.16,4,4,0,0,1,.42.82,4.11,4.11,0,0,1,.15.95,4.19,4.19,0,0,0,.64,2.16,4.25,4.25,0,0,0,1.87,1.28,4.77,4.77,0,0,1,.85.43,5.11,5.11,0,0,1,.66.66,4.12,4.12,0,0,0,1.8,1.4,3,3,0,0,0,.87.13A6.66,6.66,0,0,0,9.94,21.81a4,4,0,0,1,1.94,0,4.33,4.33,0,0,0,2.24.06,4.12,4.12,0,0,0,1.8-1.4,5.11,5.11,0,0,1,.66-.66,4.77,4.77,0,0,1,.85-.43,4.25,4.25,0,0,0,1.87-1.28A4.19,4.19,0,0,0,19.94,15.94a4.11,4.11,0,0,1,.15-.95,4.57,4.57,0,0,1,.42-.82A4.3,4.3,0,0,0,21.28,12,4.3,4.3,0,0,0,21.6,9.84Zm-4.89.87-5,5a1,1,0,0,1-1.42,0l-3-3a1,1,0,1,1,1.42-1.42L11,13.59l4.29-4.3a1,1,0,0,1,1.42,1.42Z" />
                </svg>
                <span className="text-sm font-bold text-indigo-600 dark:text-indigo-400">Beta 1.0</span>
              </div>

              {/* Theme Toggle */}
              <ThemeToggle />

              {/* User Menu */}
              <div className="hidden sm:flex items-center gap-2 px-3 py-2 bg-slate-100 dark:bg-slate-700 rounded-lg">
                <div className="w-9 h-9 rounded-full bg-indigo-700 text-white flex items-center justify-center">
                  <span className="text-base font-bold">U</span>
                </div>
                <span className="text-base font-semibold text-slate-800 dark:text-slate-200">User</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto overflow-x-hidden bg-slate-50 dark:bg-slate-900 max-w-full">
        <div className="py-6 px-4 sm:px-6 lg:px-8 max-w-full">

          {currentView === "upload" && (
            <UploadArea onScanComplete={handleScanComplete} onUploadDeferred={handleUploadDeferred} />
          )}
          {currentView === "groups" && <GroupMaster onBack={handleBackToUpload} onOpenGroupDashboard={handleOpenGroupDashboard} />}
          {currentView === "dashboard" && (
            <GroupDashboard
              onSelectScan={handleSelectScan}
              onSelectBatch={handleSelectBatch}
              onBack={handleBackToUpload}
              initialGroupId={selectedGroupId}
            />

          )}
          {currentView === "history" && (
            <Suspense fallback={<ComponentLoader />}>
              <History
                scans={scanHistory}
                onSelectScan={handleSelectScan}
                onSelectBatch={handleSelectBatch}
                onBack={handleBackToUpload}
              />
            </Suspense>
          )}
          {currentView === "batch" && currentBatch && (
            <Suspense fallback={<ComponentLoader />}>
              <BatchReportViewer
                batchId={currentBatch.batchId}
                scans={currentBatch.scans}
                onBack={handleBackToUpload}
                onBatchUpdate={handleBatchUpdate}
              />
            </Suspense>
          )}
          {currentView === "report" && scanResults.length > 0 && (
            <ReportViewer scans={scanResults} onBack={handleBackToUpload} sidebarOpen={false} />
          )}
        </div>
      </main>
    </div>
  )
}

function App() {
  console.log("[v0] App component rendering")

  return (
    <ErrorBoundary>
      <NotificationProvider>
        <AppContent />
        <NotificationContainer />
      </NotificationProvider>
    </ErrorBoundary>
  )
}

export default App
