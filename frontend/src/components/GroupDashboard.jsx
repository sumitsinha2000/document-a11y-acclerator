import { useState, useEffect, useRef } from "react"
import axios from "axios"
import { useNotification } from "../contexts/NotificationContext"
import GroupTreeSidebar from "./GroupTreeSidebar"
import API_BASE_URL from "../config/api"
import { parseBackendDate } from "../utils/dates"
import UploadArea from "./UploadArea"

const normalizeId = (id) => (id === null || id === undefined ? "" : String(id))
const getCacheKey = (node) => (node ? `${node.type}:${normalizeId(node.id)}` : "")

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
}) {
  const { showError, showSuccess } = useNotification()

  const [selectedNode, setSelectedNode] = useState(null)
  const [nodeData, setNodeData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [uploadContext, setUploadContext] = useState({
    groupId: null,
    groupName: null,
    folderId: null,
    folderName: null,
  })

  const latestRequestRef = useRef(0)
  const cacheRef = useRef(new Map())

  useEffect(() => {
    loadInitialData()
  }, [])

  const loadInitialData = async () => {
    try {
      setInitialLoading(true)
      await axios.get(`${API_BASE_URL}/api/groups`) // no need to handleNodeSelect here
    } catch (error) {
      console.error("[v0] Error loading initial data:", error)
      showError("Failed to load initial data")
    } finally {
      setInitialLoading(false)
    }
  }

  const deriveUploadContext = (node, nodeDataPayload = null) => {
    if (!node && !nodeDataPayload) {
      return {
        groupId: null,
        groupName: null,
        folderId: null,
        folderName: null,
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
      nodeDataPayload?.name ??
      node?.data?.groupName ??
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

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-slate-900">

      <GroupTreeSidebar
        onNodeSelect={handleNodeSelect}
        selectedNode={selectedNode}
        onRefresh={loadInitialData}
        initialGroupId={initialGroupId}
      />

      <div
        className="flex-1 overflow-y-auto"
        id="group-dashboard-details"
        data-group-dashboard-details="true"
      >
        <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Project Dashboard</h1>
                {isRefreshing && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 dark:bg-slate-800/80 dark:text-slate-300">
                    <svg
                      className="h-3.5 w-3.5 animate-spin text-violet-600 dark:text-violet-400"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                    >
                      <circle cx="12" cy="12" r="10" strokeWidth="4" className="opacity-25"></circle>
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
              <p className="text-base text-slate-600 dark:text-slate-400 mt-1">
                {selectedNode
                  ? `Viewing ${
                      selectedNode.type === "group"
                        ? "project"
                        : selectedNode.type === "batch"
                          ? "folder"
                          : selectedNode.type
                    }: ${selectedNode.data?.name || selectedNode.data?.filename || ""}`
                  : "Select a project or file from the sidebar"}
              </p>
            </div>
            <button
              onClick={onUploadRequest}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-700 hover:to-indigo-700 rounded-lg shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-500 transition-colors"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v12m0 0l-3-3m3 3 3-3" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 19h14" />
              </svg>
              Upload Files
            </button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600"></div>
            </div>
          ) : (
            <>
              {uploadSectionOpen && (
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                  <div className="flex items-center justify-between gap-2 pb-4 border-b border-slate-100 dark:border-slate-800">
                    <div>
                      <p className="text-sm font-semibold text-slate-900 dark:text-white">Upload PDF documents</p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        Drop files directly into the dashboard without navigating away.
                      </p>
                      {uploadContext.groupId && (
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                          {uploadContext.groupName || "Selected project"} automatically selected{uploadContext.folderName ? ` · Folder: ${uploadContext.folderName}` : ""}
                        </p>
                      )}
                    </div>
                    <button
                      onClick={onCloseUploadSection}
                      className="rounded-full border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 transition-colors hover:border-slate-400 hover:text-slate-900 dark:border-slate-600 dark:text-slate-200 dark:hover:border-slate-500 dark:hover:text-white"
                    >
                      Close upload
                    </button>
                  </div>
                  <div className="mt-4">
                    <UploadArea
                      onScanComplete={onScanComplete}
                      onUploadDeferred={onUploadDeferred}
                      autoSelectGroupId={uploadContext.groupId}
                      autoSelectFolderId={uploadContext.folderId}
                      autoSelectFolderName={uploadContext.folderName}
                    />
                  </div>
                </div>
              )}

              <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Uploaded documents</h2>
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                      Recent scans tied to the project you are viewing. Click to open the report.
                    </p>
                  </div>
                  <button
                    onClick={onUploadRequest}
                    className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600 rounded-full border border-slate-300 hover:border-slate-400 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-600 transition-colors"
                  >
                    Upload more
                  </button>
                </div>
                <div className="mt-5 space-y-3">
                  {scanHistory.length === 0 ? (
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                      No uploads yet. Use the upload panel above to add your first document.
                    </p>
                  ) : (
                    scanHistory.slice(0, 6).map((scan) => {
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
            </>
          )}
        </div>
      </div>
    </div>
  )
}
