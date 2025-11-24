import { useState, useEffect, useRef } from "react"
import axios from "axios"
import { useNotification } from "../contexts/NotificationContext"
import GroupTreeSidebar from "./GroupTreeSidebar"
import { BatchInsightPanel, GroupInsightPanel } from "./DashboardInsights"
import UploadArea from "./UploadArea"
import ReportViewer from "./ReportViewer"
import API_BASE_URL from "../config/api"
import { parseBackendDate } from "../utils/dates"

const normalizeId = (id) => (id === null || id === undefined ? "" : String(id))
const getCacheKey = (node) => (node ? `${node.type}:${normalizeId(node.id)}` : "")
const SCANNABLE_STATUSES = new Set(["uploaded", "unprocessed"])
const isScannableStatus = (status) => SCANNABLE_STATUSES.has((status || "unprocessed").toLowerCase())

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

  const isFolderSelected = selectedNode?.type === "batch"

  const latestRequestRef = useRef(0)
  const cacheRef = useRef(new Map())

  useEffect(() => {
    loadInitialData()
  }, [])

  useEffect(() => {
    if (!isFolderSelected && uploadSectionOpen) {
      onCloseUploadSection()
    }
  }, [isFolderSelected, uploadSectionOpen, onCloseUploadSection])

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

    const projectLabel = uploadContext.groupName || "selected project"
    const folderLabel = uploadContext.folderName || "selected folder"

    return (
      <div className="rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-xl dark:border-slate-700 dark:bg-slate-900/80 space-y-8">
        <div className="flex items-center gap-4">
          <button
            onClick={onCloseUploadSection}
            className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-violet-600 to-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-500/20 transition hover:opacity-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-500"
            aria-label="Back to dashboard"
          >
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 4L4 10l6 6" />
            </svg>
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
              Upload documents to{" "}
              <span className="text-indigo-600 dark:text-indigo-400">{folderLabel}</span>
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">Folder: {projectLabel}</p>
          </div>
        </div>

        <UploadArea
          onScanComplete={onScanComplete}
          onUploadDeferred={onUploadDeferred}
          autoSelectGroupId={uploadContext.groupId}
          autoSelectFolderId={uploadContext.folderId}
        />

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold text-slate-900 dark:text-white">
                Uploaded documents for this folder
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Recent scans tied to the folder you're uploading into.
              </p>
            </div>
          </div>
          <div className="mt-5 space-y-3">
            {folderUploads.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                No uploads yet. Start by selecting PDFs on the upload panel above.
              </p>
            ) : (
              folderUploads.slice(0, 6).map((scan) => {
                const scanDate = parseBackendDate(scan.uploadDate || scan.created_at || scan.timestamp)
                return (
                  <article
                    key={scan.scanId || scan.id || scan.batchId || scan.filename}
                    className="flex items-center justify-between gap-4 rounded-2xl border border-slate-100 px-4 py-3 transition-colors hover:border-slate-200 dark:border-slate-800 dark:hover:border-slate-700"
                  >
                    <div>
                      <p className="text-sm font-medium text-slate-900 dark:text-white truncate">
                        {scan.filename || scan.fileName || "Untitled PDF"}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {(scan.groupName || scan.group_name || "Unknown project") +
                          (scanDate ? ` · ${scanDate.toLocaleDateString()}` : "")}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="px-2 py-1 text-xs font-semibold uppercase tracking-wide text-indigo-600 bg-indigo-50 rounded-full dark:text-indigo-300 dark:bg-indigo-900/30">
                        {scan.status || "Uploaded"}
                      </span>
                      <button
                        onClick={() => onSelectScan(scan)}
                        className="text-xs font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
                      >
                        View
                      </button>
                    </div>
                  </article>
                )
              })
            )}
          </div>
        </div>
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

        cacheAndUpdate({
          nodeData: {
            type: "file",
            ...response.data,
          },
          selectedNode: {
            ...node,
            data: {
              ...(node.data || {}),
              filename: response.data.fileName || response.data.filename || node.data?.filename,
              fileName: response.data.fileName || response.data.filename || node.data?.fileName,
              status: response.data.status || node.data?.status,
            },
          },
        })
      } else if (node.type === "batch") {
        const response = await axios.get(`${API_BASE_URL}/api/batch/${node.id}`)

        cacheAndUpdate({
          nodeData: {
            type: "batch",
            ...response.data,
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

        if (node.type === "group" && statusCode === 404) {
          cacheRef.current.delete(cacheKey)
          setSelectedNode(null)
          setNodeData(null)
          showError("Selected group is no longer available.")
          return {
            removedGroupId: node.id,
            removedGroupName: node.data?.name,
          }
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

    const cacheKey = getCacheKey(selectedNode)
    cacheRef.current.delete(cacheKey)
    await handleNodeSelect(selectedNode)
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
      nodeData.scans?.filter((scan) => isScannableStatus(scan.status)) || []

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
      setNodeData({
        type: "batch",
        ...refreshed.data,
      })
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

    try {
      setRemediatingFolder(true)
      const response = await axios.post(`${API_BASE_URL}/api/batch/${folderId}/fix-all`)
      const payload = response.data || {}
      if (payload.success) {
        const successCount = payload.successCount || 0
        const total = payload.totalFiles || 0
        showSuccess(
          successCount > 0
            ? `Started remediation on ${successCount} of ${total} file${total === 1 ? "" : "s"} in this folder.`
            : "Remediation request accepted. Awaiting results."
        )
      } else {
        showError(payload.error || "Failed to remediate the folder.")
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
      setNodeData({
        type: "batch",
        ...refreshed.data,
      })
    } catch (refreshError) {
      console.error("[v0] Error refreshing folder after remediation:", refreshError)
    }
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
  const folderReadyToScan =
    nodeData?.type === "batch" &&
    ((nodeData?.scans?.length || 0) === 0 ||
      nodeData?.scans?.every((scan) => isScannableStatus(scan.status)))
  const folderBatchId = nodeData?.type === "batch" ? nodeData.batchId || selectedNode?.id : null
  const activeDashboardName =
    nodeData?.type === "group"
      ? nodeData?.name || selectedNode?.data?.name || "Selected project"
      : nodeData?.type === "batch"
        ? nodeData?.name || selectedNode?.data?.name || "Selected folder"
        : nodeData?.type === "file"
          ? targetFileName
          : selectedNode?.data?.name || "Project dashboard"
  const canUploadNew = isFolderSelected && !uploadSectionOpen
  const shouldShowDashboardActions = nodeData?.type === "batch" && !uploadSectionOpen
  const canShowUploadButton = canUploadNew && nodeData?.type === "batch"
  const canScanFolder = nodeData?.type === "batch" && folderReadyToScan
  const scanFolderLabel = startingFolderScan ? "Starting..." : "Scan Folder"
  const remediateFolderLabel = remediatingFolder ? "Remediating..." : "Remediate Folder"
  const folderHasIssues = nodeData?.type === "batch" && (nodeData?.totalIssues || 0) > 0

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-gradient-to-br dark:from-[#040714] dark:via-[#080f24] dark:to-[#0d1a3a] dark:text-slate-100">
      <div className="w-full flex h-full flex-col gap-6 px-4 py-6 lg:flex-row lg:items-start">
        <div className="w-full lg:max-w-sm flex-shrink-0">
          <GroupTreeSidebar
            onNodeSelect={handleNodeSelect}
            selectedNode={selectedNode}
            onRefresh={loadInitialData}
            initialGroupId={initialGroupId}
            latestUploadContext={latestUploadContext}
            onUploadContextAcknowledged={onUploadContextAcknowledged}
            folderNavigationContext={folderNavigationContext}
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
                  {shouldShowDashboardActions && (
                    <div className="flex-shrink-0 flex items-center gap-2">
                      {nodeData?.type === "batch" && (
                        <>
                          {folderBatchId && (
                            <button
                              type="button"
                              onClick={() => onSelectBatch(folderBatchId)}
                              className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-indigo-600 transition hover:border-slate-300 hover:bg-indigo-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:border-indigo-500/30 dark:bg-indigo-900/40 dark:text-indigo-200 dark:hover:border-indigo-400 dark:hover:bg-indigo-800/60"
                            >
                              View Full Report
                            </button>
                          )}
                          {folderBatchId && (
                            <button
                              type="button"
                              onClick={handleBeginFolderScan}
                              disabled={startingFolderScan}
                              aria-disabled={startingFolderScan}
                              aria-busy={startingFolderScan}
                              className="inline-flex items-center justify-center rounded-lg border border-transparent bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
                            >
                              {scanFolderLabel}
                            </button>
                          )}
                          {folderHasIssues && (
                            <button
                              type="button"
                              onClick={handleRemediateFolder}
                              disabled={remediatingFolder}
                              aria-disabled={remediatingFolder}
                              aria-busy={remediatingFolder}
                              className="inline-flex items-center justify-center rounded-lg border border-transparent bg-purple-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-purple-700 disabled:opacity-60 disabled:cursor-not-allowed"
                            >
                              {remediateFolderLabel}
                            </button>
                          )}
                        </>
                      )}
                      {canShowUploadButton && (
                        <button
                          type="button"
                          onClick={onUploadRequest}
                          className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-violet-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-500/20 transition hover:opacity-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-500"
                        >
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
                          Upload Files
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600"></div>
            </div>
          ) : uploadSectionOpen && isFolderSelected ? (
            renderUploadView()
          ) : nodeData ? (
            <>
              {nodeData.type === "group" && (
                <div className="space-y-6">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-[#111b36]">
                      <div className="text-3xl font-bold text-indigo-600 dark:text-indigo-400">
                        {nodeData.avg_compliance || 0}%
                      </div>
                      <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">Avg Compliance</div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-[#111b36]">
                      <div className="text-3xl font-bold text-rose-600 dark:text-rose-400">
                        {nodeData.total_issues || 0}
                      </div>
                      <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">Total Issues</div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-[#111b36]">
                      <div className="text-3xl font-bold text-emerald-600 dark:text-emerald-400">
                        {nodeData.issues_fixed || 0}
                      </div>
                      <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">Fixed Issues</div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-[#111b36]">
                      <div className="text-3xl font-bold text-slate-900 dark:text-white">
                        {nodeData.file_count || 0}
                      </div>
                      <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">Total Files</div>
                    </div>
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
                />
              )}

              {nodeData.type === "batch" && (
                <div className="space-y-6">
                  <div className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-[#111b36]">
                    <div className="grid grid-cols-4 gap-4">
                      <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0c162c]">
                        <div className="text-2xl font-bold text-slate-900 dark:text-white">
                          {nodeData.totalIssues || 0}
                        </div>
                        <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">Total Issues</div>
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0c162c]">
                        <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                          {nodeData.fixedIssues || 0}
                        </div>
                        <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">Fixed</div>
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0c162c]">
                        <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                          {nodeData.remainingIssues || 0}
                        </div>
                        <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">Remaining</div>
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
              <svg className="w-20 h-20 text-slate-300 dark:text-slate-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
        </div>
      </div>
    </div>
  </div>
</div>
  )
}
