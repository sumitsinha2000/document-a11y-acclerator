import { useState, useEffect, lazy, Suspense, useCallback, startTransition } from "react"
import axios from "axios"
import "./App.css"
import LoadingScreen from "./components/LoadingScreen"
import ThemeToggle from "./components/ThemeToggle"
import { NotificationProvider, useNotification } from "./contexts/NotificationContext"
import NotificationContainer from "./components/NotificationContainer"
import API_BASE_URL from "./config/api"
import ErrorBoundary from "./components/ErrorBoundary"
import amperaLogo from "./assets/ampera_logo_icon.png"

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

  // const [isLoading, setIsLoading] = useState(true)
  const [currentView, setCurrentView] = useState("dashboard")
  const [scanHistory, setScanHistory] = useState([])
  const [scanResults, setScanResults] = useState([])
  const [currentBatch, setCurrentBatch] = useState(null)
  const [loading, setLoading] = useState(false)
  const [selectedGroupId, setSelectedGroupId] = useState(null)
  const [isUploadPanelOpen, setUploadPanelOpen] = useState(false)
  const [latestUploadContext, setLatestUploadContext] = useState(null)
  const [folderNavigationContext, setFolderNavigationContext] = useState(null)
  const [folderStatusSignal, setFolderStatusSignal] = useState({
    key: 0,
    folderId: null,
    groupId: null,
  })
  const handleFolderStatusUpdate = useCallback(({ folderId, groupId }) => {
    if (!folderId || !groupId) {
      return
    }
    setFolderStatusSignal((prev) => ({
      key: prev.key + 1,
      folderId,
      groupId,
    }))
  }, [])
  const transitionToView = useCallback(
    (view) => {
      startTransition(() => {
        setCurrentView(view)
      })
    },
    [setCurrentView],
  )
  
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

  useEffect(() => {
    if (currentView !== "dashboard") {
      setUploadPanelOpen(false)
    }
  }, [currentView])

  // const handleLoadingComplete = () => {
  //   console.log("[v0] Loading complete")
  //   setIsLoading(false)
  // }

  // if (isLoading) {
  //   return <LoadingScreen onComplete={handleLoadingComplete} />
  // }

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
    const hasFolder = Boolean(details?.batchId)
    const message =
      count > 1
        ? `${count} files uploaded${hasFolder ? " in the folder" : ""}. Begin scanning whenever you're ready from the dashboard or history view.`
        : count === 1
          ? "File uploaded successfully. Start the scan when you're ready from the dashboard or history view."
          : "Upload completed. Start scanning whenever you're ready from the dashboard or history view."
    showSuccess(message)
    fetchScanHistory()
  }

  const handleDashboardUploadComplete = (scans) => {
    handleScanComplete(scans)
    setUploadPanelOpen(false)
  }

  const handleDashboardUploadDeferred = (details) => {
    handleUploadDeferred(details)
    setUploadPanelOpen(false)
    const folderId = details?.batchId
    if (folderId) {
      setLatestUploadContext({
        groupId: details?.groupId,
        folderId,
        folderName: details?.folderName,
      })
    } else {
      setLatestUploadContext(null)
    }
  }

  const handleViewHistory = () => {
    transitionToView("history")
  }

  const handleOpenUploadPanel = () => {
    setUploadPanelOpen(true)
    transitionToView("dashboard")
  }

  const handleCloseUploadPanel = () => {
    setUploadPanelOpen(false)
  }

  const handleSelectScan = async (scan) => {
    const scanIdentifier =
      typeof scan === "string"
        ? scan
        : scan?.id || scan?.scanId || scan?.scan_id || scan?.filename || scan?.fileName

    if (!scanIdentifier) {
      console.error("handleSelectScan called without a valid scan identifier", scan)
      showError("Unable to load scan details. Missing scan identifier.")
      return
    }

    try {
      setLoading(true)
      const response = await axios.get(`${API_BASE_URL}/api/scan/${encodeURIComponent(scanIdentifier)}`)
      const scanData = response.data
      setScanResults([scanData])
      const folderId = scanData.batchId || scanData.folderId
      if (folderId) {
        setCurrentBatch((prevBatch) => {
          if (prevBatch?.batchId === folderId) {
            return prevBatch
          }
          return {
            batchId: folderId,
            scans: [],
          }
        })
      } else {
        setCurrentBatch(null)
      }
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
      console.error("Error loading folder details:", error)
      showError("Failed to load folder details: " + (error.response?.data?.error || error.message))
    } finally {
      setLoading(false)
    }
  }

  const handleBackToUpload = () => {
    setScanResults([])
    setCurrentBatch(null)
    handleOpenUploadPanel()
  }

  const handleReturnToBatchFromReport = () => {
    const scan = scanResults[0]
    const folderId = scan?.batchId || scan?.folderId || currentBatch?.batchId
    const folderName = scan?.batchName || scan?.folderName
    const groupId = scan?.groupId
    if (folderId && groupId) {
      setScanResults([])
      setCurrentBatch(null)
      setSelectedGroupId(groupId)
      setFolderNavigationContext({
        groupId,
        folderId,
        folderName,
      })
      transitionToView("dashboard")
    } else {
      handleBackToUpload()
    }
  }

  const handleViewGenerator = () => {
    transitionToView("generator")
  }

  const handleBatchUpdate = async (batchId) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/batch/${batchId}`)
      setCurrentBatch({
        batchId: batchId,
        scans: response.data.scans || [],
      })
    } catch (error) {
      console.error("Error refreshing folder data:", error)
    }
  }

  const handleOpenGroupDashboard = (groupId) => {
    setSelectedGroupId(groupId)
    transitionToView("dashboard")
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
                <div className="flex h-11 w-11 items-center justify-center rounded-xl shadow-md flex-shrink-0 overflow-hidden">
                  <img src={amperaLogo} alt="Ampera logo" className="h-full w-full object-contain p-1" />
                </div>
                <div className="min-w-0">
                  <p className="text-xl font-bold text-slate-900 dark:text-white truncate">Doc A11y Accelerator</p>
                  <p className="text-sm text-slate-600 dark:text-slate-400 truncate">PDF Accessibility Scanner</p>
                </div>
              </div>

              {/* Navigation Links */}
              {/* <nav className="hidden md:flex items-center gap-1 flex-shrink-0">
              <button
                onClick={() => transitionToView("dashboard")}
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
                  onClick={() => transitionToView("groups")}
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
                    Projects
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
              </nav> */}
            </div>

            {/* Right Side Actions */}
            <div className="flex items-center gap-3 flex-shrink-0">
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

          {currentView === "groups" && <GroupMaster onBack={handleBackToUpload} onOpenGroupDashboard={handleOpenGroupDashboard} />}
          {currentView === "dashboard" && (
            <GroupDashboard
              onSelectScan={handleSelectScan}
              onSelectBatch={handleSelectBatch}
              onUploadRequest={handleOpenUploadPanel}
              uploadSectionOpen={isUploadPanelOpen}
              onCloseUploadSection={handleCloseUploadPanel}
              onScanComplete={handleDashboardUploadComplete}
              onUploadDeferred={handleDashboardUploadDeferred}
              initialGroupId={selectedGroupId}
              scanHistory={scanHistory}
              latestUploadContext={latestUploadContext}
              onUploadContextAcknowledged={() => setLatestUploadContext(null)}
              folderNavigationContext={folderNavigationContext}
              folderStatusSignal={folderStatusSignal}
              onFolderStatusUpdate={handleFolderStatusUpdate}
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
            <ReportViewer
              scans={scanResults}
              onBack={handleBackToUpload}
              onBackToFolder={handleReturnToBatchFromReport}
              sidebarOpen={false}
            />
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
