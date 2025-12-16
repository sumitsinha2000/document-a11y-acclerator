import { useState, useEffect, useRef, useCallback } from "react"
import axios from "axios"
import { useNotification } from "../contexts/NotificationContext"
import GroupTreeSidebar from "./GroupTreeSidebar"
import { BatchInsightPanel, GroupInsightPanel } from "./DashboardInsights"
import UploadArea from "./UploadArea"
import ReportViewer from "./ReportViewer"
import API_BASE_URL from "../config/api"
import { parseBackendDate } from "../utils/dates"
import { normalizeScanSummary, normalizeScans } from "../utils/compliance"
import { getScanStatus, isScannedStatus } from "../utils/statuses"

function StatCard({ value, label, valueClass = "text-slate-900 dark:text-white", description }) {
  const displayValue = value ?? 0
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0c162c]">
      <div className={`text-3xl font-bold ${valueClass}`}>{displayValue}</div>
      <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">{label}</div>
      {description && (
        <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5" aria-hidden="true">
          {description}
        </p>
      )}
    </div>
  )
}

const normalizeId = (id) => (id === null || id === undefined ? "" : String(id))
const getCacheKey = (node) => (node ? `${node.type}:${normalizeId(node.id)}` : "")
const SCANNABLE_STATUSES = new Set(["uploaded", "unknown", "error"])
const getStatusCode = (value) => {
  const target = typeof value === "object" ? value : { status: value }
  return getScanStatus(target)
}
const isScannableStatus = (entity) => SCANNABLE_STATUSES.has(getStatusCode(entity))
const isRemediableStatus = (entity) => isScannedStatus(entity)
const UPLOAD_PANEL_ID = "group-dashboard-upload-panel"
const UPLOAD_PANEL_HEADING_ID = "group-dashboard-upload-heading"

const deriveGroupSummary = (data) => {
  if (!data || data.type !== "group") {
    return null
  }

  const totalIssues = data.total_issues ?? 0
  const fixedIssues = data.issues_fixed ?? 0
  const remainingIssues = Math.max(totalIssues - fixedIssues, 0)
  const statusCounts = data.status_counts || {}
  const unprocessedFiles = statusCounts.uploaded ?? 0
  const totalFiles = data.file_count ?? 0
  const fixedFiles = data.fixed_files ?? 0
  const scannedFiles = Math.max(totalFiles - unprocessedFiles, 0)
  const avgCompliance = data.avg_compliance ?? 0
  return {
    totalIssues,
    fixedIssues,
    remainingIssues,
    unprocessedFiles,
    totalFiles,
    fixedFiles,
    scannedFiles,
    avgCompliance,
    avgComplianceLabel:
      typeof avgCompliance === "number" ? `${avgCompliance.toFixed(2)}%` : `${avgCompliance ?? 0}%`,
  }
}

export default function GroupDashboard({
  onSelectScan,
  onSelectBatch,
  initialGroupId,
  uploadSectionOpen = false,
  onUploadRequest = () => {},
  onCloseUploadSection = () => {},
  onScanComplete = () => {},
  onUploadDeferred = () => {},
  scanHistory = [],
  latestUploadContext = null,
  onUploadContextAcknowledged = () => {},
  folderNavigationContext = null,
  folderStatusSignal = null,
  onFolderStatusUpdate = () => {},
}) {
  const { showError, showSuccess } = useNotification()

  const [selectedNode, setSelectedNode] = useState(null)
  const [nodeData, setNodeData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const [startingFolderScan, setStartingFolderScan] = useState(false)
  const [remediatingFolder, setRemediatingFolder] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [uploadContext, setUploadContext] = useState({
    groupId: null,
    groupName: "",
    folderId: null,
    folderName: "",
  })
  const [isUploadAreaScanning, setUploadAreaScanning] = useState(false)
  const [shouldAutoOpenFileDialog, setShouldAutoOpenFileDialog] = useState(false)
  const [ariaLiveMessage, setAriaLiveMessage] = useState("")
  const [autoOpenedBatchId, setAutoOpenedBatchId] = useState(null)

  const isFolderSelected = selectedNode?.type === "batch"
  const groupSummary = deriveGroupSummary(nodeData)

  const latestRequestRef = useRef(0)
  const cacheRef = useRef(new Map())
  const uploadAreaRef = useRef(null)
  const prevUploadSectionOpenRef = useRef(uploadSectionOpen)
  const sidebarRef = useRef(null)

  const refreshSidebarTree = useCallback(async () => {
    const refreshFn = sidebarRef.current?.refresh
    if (refreshFn) {
      await refreshFn()
    }
  }, [])

  const describeStaleNode = useCallback((node) => {
    if (!node) {
      return "Selection"
    }
    const name =
      node.data?.name ??
      node.data?.folderName ??
      node.data?.batchName ??
      node.data?.groupName ??
      node.data?.fileName ??
      node.data?.filename ??
      node.id ??
      "Selection"
    if (node.type === "group") {
      return `Project "${name}"`
    }
    if (node.type === "batch") {
      return `Folder "${name}"`
    }
    if (node.type === "file") {
      return `File "${name}"`
    }
    return name
  }, [])

  const handleStaleSelection = useCallback(
    async (node, statusCode) => {
      if (!node || ![404, 410].includes(statusCode)) {
        return false
      }
      const cacheKey = getCacheKey(node)
      cacheRef.current.delete(cacheKey)
      setSelectedNode(null)
      setNodeData(null)
      sidebarRef.current?.closeFolderView?.()
      await refreshSidebarTree()
      const label = describeStaleNode(node)
      const reason = statusCode === 404 ? "was not found" : "is unavailable"
      showSuccess(`${label} ${reason}; refreshed with the latest data.`)
      return true
    },
    [refreshSidebarTree, describeStaleNode, showSuccess]
  )

  const notifyFolderStatusUpdate = useCallback(
    (folderIdOverride, groupIdOverride) => {
      const resolvedFolderId =
        folderIdOverride ??
        nodeData?.batchId ??
        selectedNode?.id ??
        uploadContext.folderId ??
        null
      const resolvedGroupId =
        groupIdOverride ??
        nodeData?.groupId ??
        selectedNode?.data?.groupId ??
        selectedNode?.data?.group_id ??
        uploadContext.groupId ??
        null

      if (!resolvedFolderId || !resolvedGroupId) {
        return
      }

      onFolderStatusUpdate({
        folderId: resolvedFolderId,
        groupId: resolvedGroupId,
      })
    },
    [nodeData, onFolderStatusUpdate, selectedNode, uploadContext],
  )

  useEffect(() => {
    loadInitialData()
  }, [])

  useEffect(() => {
    if (!isFolderSelected && uploadSectionOpen) {
      onCloseUploadSection()
    }
  }, [isFolderSelected, uploadSectionOpen, onCloseUploadSection])

  useEffect(() => {
    if (!uploadSectionOpen) {
      setUploadAreaScanning(false)
      setShouldAutoOpenFileDialog(false)
      return
    }
  }, [uploadSectionOpen])

  useEffect(() => {
    if (prevUploadSectionOpenRef.current && !uploadSectionOpen && !isUploadAreaScanning) {
      uploadAreaRef.current?.resetUploads?.()
    }
    prevUploadSectionOpenRef.current = uploadSectionOpen
  }, [uploadSectionOpen, isUploadAreaScanning])

  useEffect(() => {
    const type = nodeData?.type || selectedNode?.type
    const name =
      nodeData?.name ||
      nodeData?.folderName ||
      nodeData?.groupName ||
      selectedNode?.data?.name ||
      selectedNode?.data?.folderName ||
      selectedNode?.data?.groupName ||
      selectedNode?.data?.filename ||
      selectedNode?.data?.fileName ||
      "Selected view"

    let message = ""
    if (type === "batch") {
      message = `Folder metrics dashboard now shown for ${name}`
    } else if (type === "group") {
      message = `Project dashboard now shown for ${name}`
    } else if (type === "file") {
      message = `File report now shown for ${name}`
    } else {
      message = "Project dashboard now shown"
    }
    setAriaLiveMessage((prev) => (prev === message ? prev : message))
  }, [nodeData, selectedNode])

  const focusUploadPanelHeading = useCallback(() => {
    const schedule =
      typeof window !== "undefined" && typeof window.requestAnimationFrame === "function"
        ? window.requestAnimationFrame
        : (cb) => setTimeout(cb, 0)
    const cancel =
      typeof window !== "undefined" && typeof window.cancelAnimationFrame === "function"
        ? window.cancelAnimationFrame
        : (id) => clearTimeout(id)
    let frameId = null
    let attempts = 0
    const tryFocus = () => {
      if (attempts > 5) {
        if (frameId) {
          cancel(frameId)
        }
        return
      }
      attempts += 1
      const heading =
        typeof document !== "undefined" ? document.getElementById(UPLOAD_PANEL_HEADING_ID) : null
      if (heading && typeof heading.focus === "function") {
        heading.focus()
        if (frameId) {
          cancel(frameId)
        }
        return
      }
      frameId = schedule(tryFocus)
    }
    frameId = schedule(tryFocus)
  }, [])

  const handleUploadAreaDeferred = useCallback(
    (payload = {}) => {
      const failedCount = Array.isArray(payload?.failedFiles) ? payload.failedFiles.length : 0
      const successCount = Array.isArray(payload?.successFiles) ? payload.successFiles.length : 0
      if (successCount > 0) {
        notifyFolderStatusUpdate(payload.batchId ?? uploadContext.folderId, payload.groupId ?? uploadContext.groupId)
      }
      onUploadDeferred?.(payload)
      if (failedCount > 0) {
        focusUploadPanelHeading()
      }
    },
    [focusUploadPanelHeading, notifyFolderStatusUpdate, onUploadDeferred, uploadContext.folderId, uploadContext.groupId],
  )

  useEffect(() => {
    if (!shouldAutoOpenFileDialog || !uploadSectionOpen) {
      return
    }
    const schedule = typeof window !== "undefined" && typeof window.requestAnimationFrame === "function"
      ? window.requestAnimationFrame
      : (cb) => setTimeout(cb, 0)
    const cancelSchedule = typeof window !== "undefined" && typeof window.cancelAnimationFrame === "function"
      ? window.cancelAnimationFrame
      : (id) => clearTimeout(id)
    let cancelled = false
    let frameId = null
    const tryOpenDialog = () => {
      if (cancelled) {
        return
      }
      if (uploadAreaRef.current) {
        uploadAreaRef.current.openFileDialog()
        setShouldAutoOpenFileDialog(false)
        return
      }
      frameId = schedule(tryOpenDialog)
    }
    frameId = schedule(tryOpenDialog)
    return () => {
      cancelled = true
      if (frameId) {
        cancelSchedule(frameId)
      }
    }
  }, [shouldAutoOpenFileDialog, uploadSectionOpen])

  useEffect(() => {
    if (!nodeData || nodeData.type !== "batch") {
      setAutoOpenedBatchId(null)
      return
    }
    const batchId = nodeData.batchId ?? nodeData.folderId ?? selectedNode?.id
    if (!batchId) {
      setAutoOpenedBatchId(null)
      return
    }
    const filesCount =
      nodeData.file_count ??
      nodeData.totalFiles ??
      nodeData.total_files ??
      (Array.isArray(nodeData.scans) ? nodeData.scans.length : 0)
    const isEmpty = filesCount === 0

    if (!isEmpty) {
      setAutoOpenedBatchId(null)
      return
    }

    if (uploadSectionOpen || isUploadAreaScanning) {
      return
    }

    if (autoOpenedBatchId === batchId) {
      return
    }

    setAutoOpenedBatchId(batchId)
    onUploadRequest()
    setShouldAutoOpenFileDialog(true)
  }, [
    nodeData,
    selectedNode,
    uploadSectionOpen,
    isUploadAreaScanning,
    autoOpenedBatchId,
    onUploadRequest,
  ])

  useEffect(() => {
    if (!folderNavigationContext?.folderId || !folderNavigationContext?.groupId) {
      return
    }

    const node = {
      type: "batch",
      id: folderNavigationContext.folderId,
      data: {
        batchId: folderNavigationContext.folderId,
        name: folderNavigationContext.folderName || `Folder ${folderNavigationContext.folderId}`,
        groupId: folderNavigationContext.groupId,
      },
    }

    handleNodeSelect(node)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folderNavigationContext])

  const loadInitialData = async () => {
    try {
      setInitialLoading(true)
      await axios.get(`${API_BASE_URL}/api/groups`)
    } catch (error) {
      console.error("[v0] Error loading initial data:", error)
      showError("Failed to load initial data")
    } finally {
      setInitialLoading(false)
    }
  }

  const handleCloseUploadSectionRequest = useCallback(() => {
    if (isUploadAreaScanning) {
      return
    }
    uploadAreaRef.current?.resetUploads?.()
    onCloseUploadSection()
  }, [isUploadAreaScanning, onCloseUploadSection])

  const renderUploadView = () => {
    const normalizedFolderId = normalizeId(uploadContext.folderId)
    const normalizedGroupId = normalizeId(uploadContext.groupId)
    const folderUploads = scanHistory.filter((scan) => {
      const scanFolderId = normalizeId(scan.batchId ?? scan.folder_id ?? scan.folderId)
      const scanGroupId = normalizeId(scan.groupId ?? scan.group_id)
      if (normalizedFolderId && scanFolderId === normalizedFolderId) {
        return true
      }
      if (!normalizedFolderId && normalizedGroupId && scanGroupId === normalizedGroupId) {
        return true
      }
      return false
    })

    const folderLabel = uploadContext.folderName || "selected folder"

    return (
      <div
        id={UPLOAD_PANEL_ID}
        role="region"
        aria-labelledby={UPLOAD_PANEL_HEADING_ID}
        aria-busy={isUploadAreaScanning || undefined}
        className="rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-xl dark:border-slate-700 dark:bg-slate-900/80 space-y-8"
      >
        <div className="flex items-center gap-4">
          <button
            onClick={handleCloseUploadSectionRequest}
            disabled={isUploadAreaScanning}
            aria-disabled={isUploadAreaScanning}
            className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-violet-600 to-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-500/20 transition hover:opacity-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-500 disabled:opacity-60 disabled:cursor-not-allowed"
            aria-label="Back to dashboard"
          >
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 4L4 10l6 6" />
            </svg>
          </button>
          <div>
            <h2
              id={UPLOAD_PANEL_HEADING_ID}
              tabIndex={-1}
              className="text-2xl font-bold text-slate-900 dark:text-white"
            >
              Upload documents
              {/* <span className="text-indigo-600 dark:text-indigo-400">{folderLabel}</span> */}
            </h2>
          </div>
        </div>

        <UploadArea
          ref={uploadAreaRef}
          onUploadDeferred={handleUploadAreaDeferred}
          autoSelectGroupId={uploadContext.groupId}
          autoSelectFolderId={uploadContext.folderId}
          onScanningChange={setUploadAreaScanning}
        />

      </div>
    )
  }

  const deriveUploadContext = (node, nodeDataPayload = null) => {
    if (!node && !nodeDataPayload) {
      return {
        groupId: null,
        groupName: "",
        folderId: null,
        folderName: "",
      }
    }

    const groupId =
      nodeDataPayload?.groupId ??
      nodeDataPayload?.group_id ??
      node?.data?.groupId ??
      node?.data?.group_id ??
      (node?.type === "group" ? node.id : null)
    const groupName =
      nodeDataPayload?.groupName ??
      nodeDataPayload?.group_name ??
      nodeDataPayload?.name ??
      node?.data?.groupName ??
      node?.data?.group_name ??
      node?.data?.name ??
      ""

    let folderId =
      nodeDataPayload?.batchId ??
      nodeDataPayload?.folderId ??
      (node?.type === "batch" ? node.id : null)
    let folderName =
      nodeDataPayload?.name ??
      nodeDataPayload?.folderName ??
      (node?.type === "batch" ? node.data?.name ?? "" : "")

    if (!folderId && node?.type === "file") {
      folderId = node.data?.batchId ?? node.data?.folderId ?? null
      folderName = folderName || node.data?.batchName || node.data?.folderName || ""
    }

    return {
      groupId,
      groupName,
      folderId,
      folderName,
    }
  }

  const updateUploadContext = (node, nodeDataPayload = null) => {
    const context = deriveUploadContext(node, nodeDataPayload)
    setUploadContext(context)
  }

  const handleNodeSelect = async (node) => {
    if (!node) {
      setSelectedNode(null)
      setNodeData(null)
      setLoading(false)
      setIsRefreshing(false)
      updateUploadContext(null)
      return { cleared: true }
    }

    const cacheKey = getCacheKey(node)
    const cachedEntry = cacheRef.current.get(cacheKey)
    const usedCache = Boolean(cachedEntry)
    const nextRequestId = latestRequestRef.current + 1
    latestRequestRef.current = nextRequestId

    setSelectedNode(node)
    updateUploadContext(node)

    if (usedCache) {
      setNodeData(cachedEntry.nodeData)
      setSelectedNode(cachedEntry.selectedNode)
      setLoading(false)
      setIsRefreshing(true)
    } else {
      setLoading(true)
      setIsRefreshing(false)
    }

    const cacheAndUpdate = (payload) => {
      cacheRef.current.set(cacheKey, payload)
      if (latestRequestRef.current !== nextRequestId) {
        return
      }
      setNodeData(payload.nodeData)
      setSelectedNode(payload.selectedNode)
      updateUploadContext(node, payload.nodeData)
    }

    try {
      if (node.type === "group") {
        const response = await axios.get(`${API_BASE_URL}/api/groups/${node.id}/details`)
        const groupDetails = response.data

        cacheAndUpdate({
          nodeData: {
            type: "group",
            ...groupDetails,
          },
          selectedNode: {
            ...node,
            data: {
              ...(node.data || {}),
              name: groupDetails.name,
              description: groupDetails.description,
            },
          },
        })
      } else if (node.type === "file") {
        const response = await axios.get(`${API_BASE_URL}/api/scan/${node.id}`)
        const normalizedScan = normalizeScanSummary(response.data || {})

        cacheAndUpdate({
          nodeData: {
            type: "file",
            ...normalizedScan,
          },
          selectedNode: {
            ...node,
            data: {
              ...(node.data || {}),
              filename: normalizedScan.fileName || normalizedScan.filename || node.data?.filename,
              fileName: normalizedScan.fileName || normalizedScan.filename || node.data?.fileName,
              status: normalizedScan.status || node.data?.status,
            },
          },
        })
      } else if (node.type === "batch") {
        const response = await axios.get(`${API_BASE_URL}/api/batch/${node.id}`)
        const normalizedScans = normalizeScans(response.data?.scans)

        cacheAndUpdate({
          nodeData: {
            type: "batch",
            ...response.data,
            scans: normalizedScans,
          },
          selectedNode: {
            ...node,
            data: {
              ...(node.data || {}),
              name: response.data.batchName || node.data?.name,
              batchId: response.data.batchId || node.data?.batchId,
            },
          },
        })
      } else {
        console.warn("[v0] Unhandled node type selected:", node.type)
      }
    } catch (error) {
      if (latestRequestRef.current === nextRequestId) {
        console.error("[v0] Error fetching node data:", error)
        const errorMsg = error.response?.data?.error || error.message
        const statusCode = error.response?.status

        if (await handleStaleSelection(node, statusCode)) {
          return
        }

        const errorPrefix =
          node.type === "batch"
            ? "Failed to load folder data"
            : node.type === "file"
              ? "Failed to load file data"
              : "Failed to load data"
        showError(`${errorPrefix}: ${errorMsg}`)
        if (!usedCache) {
          setNodeData(null)
        }
      }
    } finally {
      if (latestRequestRef.current === nextRequestId) {
        setLoading(false)
        setIsRefreshing(false)
      }
    }
  }

  const refreshSelectedNodeData = async () => {
    if (!selectedNode) {
      return
    }

    const { folderId, groupId } = deriveUploadContext(selectedNode, nodeData)
    const cacheKey = getCacheKey(selectedNode)
    cacheRef.current.delete(cacheKey)
    await handleNodeSelect(selectedNode)

    if (folderId && groupId) {
      notifyFolderStatusUpdate(folderId, groupId)
    }
  }

  const handleBeginFolderScan = async () => {
    if (!nodeData || nodeData.type !== "batch") {
      return
    }

    const folderId = nodeData.batchId || selectedNode?.id
    if (!folderId) {
      showError("Unable to determine which folder to scan.")
      return
    }

    const scansToStart =
      nodeData.scans?.filter((scan) => isScannableStatus(scan)) || []

    if (scansToStart.length === 0) {
      showError("All files in this folder have already been sent for scanning.")
      return
    }

    try {
      setStartingFolderScan(true)
      const failedScans = []

      for (const scan of scansToStart) {
        try {
          await axios.post(`${API_BASE_URL}/api/scan/${scan.scanId}/start`)
        } catch (scanError) {
          console.error("[v0] Error starting deferred scan for folder item:", scanError)
          failedScans.push(scan.filename || scan.scanId)
        }
      }

      if (failedScans.length === scansToStart.length) {
        showError("Failed to start scanning for files in this folder.")
        return
      }

      if (failedScans.length > 0) {
        showError(`Some files failed to start scanning: ${failedScans.join(", ")}`)
      } else {
        showSuccess(
          `Started scanning ${scansToStart.length} file${scansToStart.length === 1 ? "" : "s"} in this folder.`
        )
      }

      const refreshed = await axios.get(`${API_BASE_URL}/api/batch/${folderId}`)
      const normalizedScans = normalizeScans(refreshed.data?.scans)
      const refreshedNodeData = {
        type: "batch",
        ...refreshed.data,
        scans: normalizedScans,
      }
      setNodeData(refreshedNodeData)
      notifyFolderStatusUpdate(refreshedNodeData.batchId ?? folderId, refreshedNodeData.groupId)
    } catch (error) {
      console.error("[v0] Error starting folder scan:", error)
      const errorMsg = error.response?.data?.error || error.message || "Failed to start folder scan"
      showError(errorMsg)
    } finally {
      setStartingFolderScan(false)
    }
  }

  const handleRemediateFolder = async () => {
    if (!nodeData || nodeData.type !== "batch") {
      return
    }

    const folderId = nodeData.batchId || selectedNode?.id
    if (!folderId) {
      showError("Unable to determine which folder to remediate.")
      return
    }

    const folderScans = Array.isArray(nodeData?.scans) ? nodeData.scans : []
    const scannedScans = folderScans.filter((scan) => isRemediableStatus(scan))
    if (scannedScans.length === 0) {
      showError("Remediation requires at least one scanned file with issues.")
      return
    }

    try {
      setRemediatingFolder(true)
      const errors = []
      let successCount = 0

      for (const scan of scannedScans) {
        const scanId = scan?.scanId || scan?.id
        if (!scanId) {
          errors.push({
            label: scan?.filename || "Unnamed file",
            reason: "Missing scan identifier",
          })
          continue
        }

        try {
          await axios.post(`${API_BASE_URL}/api/batch/${folderId}/fix-file/${scanId}`)
          successCount += 1
        } catch (scanError) {
          const errorMessage =
            scanError?.response?.data?.error || scanError?.message || "Remediation failed"
          errors.push({
            scanId,
            reason: errorMessage,
          })
        }
      }

      if (successCount > 0) {
        showSuccess(
          `Started remediation on ${successCount} of ${scannedScans.length} scanned file${scannedScans.length === 1 ? "" : "s"} in this folder.`
        )
      }

      if (errors.length > 0) {
        const failureMessage =
          errors.length === scannedScans.length
            ? `Failed to remediate scanned files. ${errors[0]?.reason || ""}`.trim()
            : `Failed to remediate ${errors.length} scanned file${errors.length === 1 ? "" : "s"}. ${errors[0]?.reason || ""}`.trim()
        showError(failureMessage)
      }
    } catch (error) {
      console.error("[v0] Error starting folder remediation:", error)
      const errorMsg = error.response?.data?.error || error.message || "Failed to remediate folder"
      showError(errorMsg)
    } finally {
      setRemediatingFolder(false)
    }

    try {
      const refreshed = await axios.get(`${API_BASE_URL}/api/batch/${folderId}`)
      const normalizedScans = normalizeScans(refreshed.data?.scans)
      const refreshedNodeData = {
        type: "batch",
        ...refreshed.data,
        scans: normalizedScans,
      }
      setNodeData(refreshedNodeData)
      notifyFolderStatusUpdate(refreshedNodeData.batchId ?? folderId, refreshedNodeData.groupId)
    } catch (refreshError) {
      console.error("[v0] Error refreshing folder after remediation:", refreshError)
    }
  }

  const handleToggleUploadSection = () => {
    if (isUploadAreaScanning) {
      return
    }
    if (uploadSectionOpen) {
      handleCloseUploadSectionRequest()
      return
    }
    onUploadRequest()
    setShouldAutoOpenFileDialog(true)
  }

  const handleBackToProjectDashboard = () => {
    sidebarRef.current?.closeFolderView?.()
    const resolvedGroupId =
      nodeData?.groupId ??
      nodeData?.group_id ??
      selectedNode?.data?.groupId ??
      selectedNode?.data?.group_id ??
      uploadContext.groupId ??
      null

    if (!resolvedGroupId) {
      showError("Unable to determine the project to return to.")
      return
    }

    const resolvedGroupName =
      nodeData?.groupName ??
      nodeData?.group_name ??
      selectedNode?.data?.groupName ??
      selectedNode?.data?.group_name ??
      uploadContext.groupName ??
      ""

    void handleNodeSelect({
      type: "group",
      id: resolvedGroupId,
      data: {
        ...(resolvedGroupName ? { name: resolvedGroupName } : {}),
      },
    })
  }

  if (initialLoading) {
    return (
      <div className="flex h-screen bg-slate-50 dark:bg-slate-900 items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-violet-600 mx-auto mb-4"></div>
          <p className="text-slate-600 dark:text-slate-400">Loading dashboard...</p>
        </div>
      </div>
    )
  }

  const targetFileName =
    nodeData?.type === "file" ? nodeData.fileName || nodeData.filename || "selected file" : "selected file"
  const targetScanId = nodeData?.scanId || nodeData?.id || selectedNode?.id
  const fileFixes =
    nodeData?.fixes ??
    (nodeData?.results && nodeData.results.fixes) ??
    nodeData?.results?.fixSuggestions ??
    nodeData?.fixSuggestions
  const folderScans = Array.isArray(nodeData?.scans) ? nodeData.scans : []
  const scannedFileCount = folderScans.filter((scan) => isRemediableStatus(scan)).length
  const folderFileCount = nodeData?.file_count ?? nodeData?.totalFiles ?? folderScans.length ?? 0
  const pendingScanCount = folderScans.filter((scan) => isScannableStatus(scan)).length
  const folderHasUploadedScans = pendingScanCount > 0
  const folderReadyToScan =
    nodeData?.type === "batch" && folderFileCount > 0 && folderHasUploadedScans
  const folderBatchId = nodeData?.type === "batch" ? nodeData.batchId || selectedNode?.id : null
  const activeDashboardName =
    nodeData?.type === "group"
      ? nodeData?.name || selectedNode?.data?.name || "Selected project"
      : nodeData?.type === "batch"
        ? nodeData?.name || selectedNode?.data?.name || "Selected folder"
        : nodeData?.type === "file"
          ? targetFileName
          : selectedNode?.data?.name || "Project dashboard"
  const shouldShowDashboardActions = nodeData?.type === "batch"
  const canShowUploadButton = nodeData?.type === "batch" && isFolderSelected
  const uploadButtonDisabled = isUploadAreaScanning
  const uploadButtonLabel = uploadSectionOpen
    ? uploadButtonDisabled
      ? "Uploading..."
      : "Close uploader"
    : "Upload files"
  const canScanFolder = nodeData?.type === "batch" && folderReadyToScan
  const scanFolderLabel = startingFolderScan ? "Starting..." : "Scan Folder"
  const remediateFolderLabel = remediatingFolder ? "Remediating..." : "Remediate Folder"
  const folderHasScannedFiles = nodeData?.type === "batch" && scannedFileCount > 0
  const canRemediateFolder = folderHasScannedFiles

  return (
    <div className="bg-slate-50 text-slate-900 dark:bg-gradient-to-br dark:from-[#040714] dark:via-[#080f24] dark:to-[#0d1a3a] dark:text-slate-100">
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {ariaLiveMessage}
      </div>
      <div className="w-full flex h-full flex-col gap-6 px-4 py-6 lg:flex-row lg:items-start">
          <div className="w-full lg:max-w-sm flex-shrink-0">
        <GroupTreeSidebar
          ref={sidebarRef}
          onNodeSelect={handleNodeSelect}
          selectedNode={selectedNode}
          onRefresh={loadInitialData}
          onDashboardRefresh={refreshSelectedNodeData}
          onStaleNode={handleStaleSelection}
          initialGroupId={initialGroupId}
          latestUploadContext={latestUploadContext}
          onUploadContextAcknowledged={onUploadContextAcknowledged}
          folderNavigationContext={folderNavigationContext}
          folderStatusUpdateSignal={folderStatusSignal}
        />
        </div>

        <div className="flex-1 lg:min-w-0">
          <div className="dashboard-panel border border-slate-200 bg-white shadow-2xl shadow-slate-200/60 overflow-hidden dark:border-slate-800 dark:bg-[#0b152d]/95 dark:shadow-[0_40px_100px_-50px_rgba(2,6,23,0.9)]">
            <div
              className="flex-1 overflow-y-auto"
              id="group-dashboard-details"
              data-group-dashboard-details="true"
            >
              <div className="px-6 py-6 space-y-6">
                <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4 dark:border-slate-800/70 dark:bg-[#0f1c38]/70">
                  <div>
                    <div className="flex flex-wrap items-center gap-3">
                      <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">
                        Dashboard: <span className="text-indigo-600 dark:text-indigo-400">{activeDashboardName}</span>
                      </h1>
                      {isRefreshing && (
                        <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-600 dark:border-slate-700/80 dark:bg-slate-900/40 dark:text-slate-300">
                          <svg
                            className="h-3.5 w-3.5 animate-spin text-indigo-500 dark:text-indigo-400"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                          >
                            <circle className="opacity-25" cx="12" cy="12" r="10" strokeWidth="4"></circle>
                            <path
                              className="opacity-75"
                              d="M4 12a8 8 0 018-8"
                              strokeWidth="4"
                              strokeLinecap="round"
                            ></path>
                          </svg>
                          Refreshing…
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-slate-500 mt-1 dark:text-slate-300">
                    {selectedNode
                      ? `Viewing ${
                          selectedNode.type === "group"
                            ? "project"
                            : selectedNode.type === "batch"
                              ? "folder"
                              : "file"
                        } details`
                      : "Select a project to start exploring accessibility insights."}
                  </p>
                </div>
              </div>
              {selectedNode?.type === "batch" && (
                <div className="px-6 pb-2">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <button
                      type="button"
                      onClick={handleBackToProjectDashboard}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:border-slate-700/80 dark:bg-slate-900/80 dark:text-slate-100 dark:hover:border-slate-600 dark:hover:bg-slate-900"
                    >
                      <svg
                        className="h-3.5 w-3.5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                      </svg>
                      Back to project dashboard
                    </button>
                    {shouldShowDashboardActions && (
                      <div className="flex flex-wrap items-center gap-2">
                        {nodeData?.type === "batch" && (
                          <>
                            {folderBatchId && folderReadyToScan && (
                              <button
                                type="button"
                                onClick={handleBeginFolderScan}
                                disabled={startingFolderScan || !folderReadyToScan}
                                aria-disabled={startingFolderScan || !folderReadyToScan}
                                aria-busy={startingFolderScan}
                                className="inline-flex items-center justify-center rounded-lg border border-transparent bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
                              >
                                {scanFolderLabel}
                              </button>
                            )}
                            {canRemediateFolder && (
                              <button
                                type="button"
                                onClick={handleRemediateFolder}
                                disabled={remediatingFolder}
                                aria-disabled={remediatingFolder}
                                aria-busy={remediatingFolder}
                                className="inline-flex items-center justify-center rounded-lg border border-transparent bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
                              >
                                {remediateFolderLabel}
                              </button>
                            )}
                          </>
                        )}
                        {canShowUploadButton && (
                          <button
                            type="button"
                            onClick={handleToggleUploadSection}
                            disabled={uploadButtonDisabled}
                            aria-disabled={uploadButtonDisabled}
                            aria-busy={uploadButtonDisabled}
                            aria-pressed={uploadSectionOpen}
                            aria-controls={uploadSectionOpen ? UPLOAD_PANEL_ID : undefined}
                            aria-expanded={uploadSectionOpen}
                            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 transition hover:bg-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed"
                          >
                            {!uploadSectionOpen && (
                              <svg
                                className="h-4 w-4"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth={2}
                                viewBox="0 0 24 24"
                                aria-hidden="true"
                              >
                                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V6m0 0l-3 3m3-3 3 3" />
                              </svg>
                            )}
                            {uploadSectionOpen && (
                              <svg
                                className="h-4 w-4"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth={2}
                                viewBox="0 0 24 24"
                                aria-hidden="true"
                              >
                                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            )}
                            {uploadButtonLabel}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600"></div>
            </div>
          ) : (
            <>
              {uploadSectionOpen && isFolderSelected && (
                <div className="px-6 py-6">
                  {renderUploadView()}
                </div>
              )}
              {nodeData ? (
                <>
                  {nodeData.type === "group" && (
                    <div className="px-6 py-6 space-y-6">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <StatCard value={groupSummary?.totalIssues} label="Total Issues" />
                       
                        <StatCard
                          value={groupSummary?.remainingIssues}
                          label="Remaining"
                          valueClass="text-amber-600 dark:text-amber-400"
                          description="Issues still pending"
                        />
                         <StatCard
                          value={groupSummary?.fixedIssues}
                          label="Fixed Issues"
                          valueClass="text-emerald-600 dark:text-emerald-400"
                        />
                        <StatCard
                          value={groupSummary?.unprocessedFiles}
                          label="Unprocessed"
                          valueClass="text-indigo-600 dark:text-indigo-300"
                        />
                      </div>


                      {nodeData.description && (
                        <div className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-[#111b36]">
                          <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">Description</h3>
                          <p className="text-slate-600 dark:text-slate-400">{nodeData.description}</p>
                        </div>
                      )}

                      <GroupInsightPanel
                        categoryTotals={nodeData.category_totals}
                        severityTotals={nodeData.severity_totals}
                        statusCounts={nodeData.status_counts}
                        totalFiles={nodeData.file_count}
                        totalIssues={nodeData.total_issues}
                        remainingIssues={groupSummary?.remainingIssues}
                      />
                    </div>
                  )}

                  {nodeData.type === "file" && (
                    <ReportViewer
                      scans={[
                        {
                          ...nodeData,
                          scanId: targetScanId,
                          fileName: targetFileName,
                          fixes: fileFixes,
                        },
                      ]}
                      onBack={() => handleNodeSelect(null)}
                      onBackToFolder={
                        nodeData.batchId || selectedNode?.data?.batchId
                          ? () => {
                              const batchId = nodeData.batchId || selectedNode?.data?.batchId
                              handleNodeSelect({
                                type: "batch",
                                id: batchId,
                                data: {
                                  batchId,
                                  name: nodeData.batchName || nodeData.folderName || selectedNode?.data?.name,
                                },
                              })
                            }
                          : undefined
                      }
                      sidebarOpen={false}
                      onScanComplete={refreshSelectedNodeData}
                      onScanUpdate={refreshSelectedNodeData}
                    />
                  )}

                  {nodeData.type === "batch" && (
                    <div className="px-6 py-6 space-y-6">
                      <div className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-[#111b36]">
                        <div className="grid grid-cols-4 gap-4">
                          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0c162c]">
                            <div className="text-2xl font-bold text-slate-900 dark:text-white">
                              {nodeData.totalIssues || 0}
                            </div>
                            <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">Total Issues</div>
                          </div>
                          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0c162c]">
                            <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                              {nodeData.remainingIssues || 0}
                            </div>
                            <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">Remaining</div>
                          </div>
                          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0c162c]">
                            <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                              {nodeData.fixedIssues || 0}
                            </div>
                            <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">Fixed</div>
                          </div>
                          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0c162c]">
                            <div className="text-2xl font-bold text-indigo-600 dark:text-indigo-300">
                              {nodeData.unprocessedFiles || 0}
                            </div>
                            <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">Unprocessed</div>
                          </div>
                        </div>

                        <div className="mt-6">
                          <BatchInsightPanel scans={nodeData.scans} />
                        </div>

                        {folderReadyToScan && (
                          <div className="mt-4 rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-sm text-slate-700 dark:border-indigo-500/30 dark:bg-[#131f3e] dark:text-slate-300">
                            This folder is ready to scan. Use the "Scan Folder" button to generate accessibility results.
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <svg className="w-20 h-20 text-slate-300 dark:text-slate-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                    />
                  </svg>
                  <h3 className="text-lg font-semibold text-slate-800 dark:text-white mb-2">No Selection</h3>
                  <p className="text-slate-500 dark:text-slate-400">Select a project or file from the sidebar to view details</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  </div>
</div>
</div>
  )
}
