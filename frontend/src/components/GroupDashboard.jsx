"use client"

import { useState, useEffect } from "react"
import axios from "axios"
import { useNotification } from "../contexts/NotificationContext"
import GroupTreeSidebar from "./GroupTreeSidebar"

export default function GroupDashboard({ onSelectScan, onSelectBatch, onBack, initialGroupId }) {
  const { showError, showSuccess } = useNotification()

  const [selectedNode, setSelectedNode] = useState(null)
  const [nodeData, setNodeData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const [startingScan, setStartingScan] = useState(false)
  const [startingBatchScan, setStartingBatchScan] = useState(false)

  useEffect(() => {
    loadInitialData()
  }, [])

  const loadInitialData = async () => {
    try {
      setInitialLoading(true)
      await axios.get("/api/groups") // no need to handleNodeSelect here
    } catch (error) {
      console.error("[v0] Error loading initial data:", error)
      showError("Failed to load initial data")
    } finally {
      setInitialLoading(false)
    }
  }


  const handleNodeSelect = async (node) => {
    setSelectedNode(node)
    setLoading(true)

    try {
      if (node.type === "group") {
        const response = await axios.get(`/api/groups/${node.id}/details`)
        const groupDetails = response.data

        setNodeData({
          type: "group",
          ...groupDetails,
        })

        setSelectedNode({
          ...node,
          data: {
            ...(node.data || {}),
            name: groupDetails.name,
            description: groupDetails.description,
          },
        })
      } else if (node.type === "file") {
        const response = await axios.get(`/api/scan/${node.id}`)
        setNodeData({
          type: "file",
          ...response.data,
        })
      } else if (node.type === "batch") {
        try {
          const response = await axios.get(`/api/batch/${node.id}`)
          setNodeData({
            type: "batch",
            ...response.data,
          })
        } catch (batchError) {
          console.error("[v0] Error fetching batch data:", batchError)
          const errorMsg = batchError.response?.data?.error || batchError.message
          showError(`Failed to load batch data: ${errorMsg}`)
          setNodeData(null)
        }
      }
    } catch (error) {
      console.error("[v0] Error fetching node data:", error)
      const errorMsg = error.response?.data?.error || error.message
      showError(`Failed to load data: ${errorMsg}`)
      setNodeData(null)
    } finally {
      setLoading(false)
    }
  }

  const handleBeginScan = async () => {
    if (!nodeData || nodeData.type !== "file") {
      return
    }

    const scanId = nodeData.scanId || nodeData.id || selectedNode?.id
    if (!scanId) {
      showError("Unable to determine which file to scan.")
      return
    }

    try {
      setStartingScan(true)
      await axios.post(`/api/scan/${scanId}/start`)
      showSuccess(`Started scanning ${nodeData.fileName || nodeData.filename}.`)

      const refreshed = await axios.get(`/api/scan/${scanId}`)
      setNodeData({
        type: "file",
        ...refreshed.data,
      })
    } catch (error) {
      console.error("[v0] Error starting deferred scan from dashboard:", error)
      const errorMsg = error.response?.data?.error || error.message || "Failed to start scan"
      showError(errorMsg)
    } finally {
      setStartingScan(false)
    }
  }

  const handleBeginBatchScan = async () => {
    if (!nodeData || nodeData.type !== "batch") {
      return
    }

    const batchId = nodeData.batchId || selectedNode?.id
    if (!batchId) {
      showError("Unable to determine which batch to scan.")
      return
    }

    const scansToStart =
      nodeData.scans?.filter((scan) => (scan.status || "").toLowerCase() === "uploaded") || []

    if (scansToStart.length === 0) {
      showError("All files in this batch have already been sent for scanning.")
      return
    }

    try {
      setStartingBatchScan(true)
      const failedScans = []

      for (const scan of scansToStart) {
        try {
          await axios.post(`/api/scan/${scan.scanId}/start`)
        } catch (scanError) {
          console.error("[v0] Error starting deferred scan for batch item:", scanError)
          failedScans.push(scan.filename || scan.scanId)
        }
      }

      if (failedScans.length === scansToStart.length) {
        showError("Failed to start scanning for files in this batch.")
        return
      }

      if (failedScans.length > 0) {
        showError(`Some files failed to start scanning: ${failedScans.join(", ")}`)
      } else {
        showSuccess(
          `Started scanning ${scansToStart.length} file${scansToStart.length === 1 ? "" : "s"} in this batch.`
        )
      }

      const refreshed = await axios.get(`/api/batch/${batchId}`)
      setNodeData({
        type: "batch",
        ...refreshed.data,
      })
    } catch (error) {
      console.error("[v0] Error starting batch scan:", error)
      const errorMsg = error.response?.data?.error || error.message || "Failed to start batch scan"
      showError(errorMsg)
    } finally {
      setStartingBatchScan(false)
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

  const fileIsUploaded = nodeData?.type === "file" && nodeData?.status === "uploaded"
  const fileScanDateLabel = fileIsUploaded ? "Uploaded on" : "Scanned on"
  const fileDateValue = nodeData?.type === "file" ? nodeData?.uploadDate || nodeData?.created_at || nodeData?.timestamp : null
  const targetFileName =
    nodeData?.type === "file" ? nodeData.fileName || nodeData.filename || "selected file" : "selected file"
  const batchHasUploadedFiles =
    nodeData?.type === "batch" && nodeData?.scans?.some((scan) => (scan.status || "").toLowerCase() === "uploaded")

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-slate-900">
      <GroupTreeSidebar
        onNodeSelect={handleNodeSelect}
        selectedNode={selectedNode}
        onRefresh={loadInitialData}
        initialGroupId={initialGroupId}
      />

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Group Dashboard</h1>
              <p className="text-base text-slate-600 dark:text-slate-400 mt-1">
                {selectedNode
                  ? `Viewing ${selectedNode.type}: ${selectedNode.data?.name || selectedNode.data?.filename || ""}`
                  : "Select a group or file from the sidebar"}
              </p>
            </div>
            <button
              onClick={onBack}
              className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
            >
              ← Back to Upload
            </button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600"></div>
            </div>
          ) : nodeData ? (
            <>
              {nodeData.type === "group" && (
                <div className="space-y-6">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-5">
                      <div className="text-3xl font-bold text-slate-900 dark:text-white">
                        {nodeData.file_count || 0}
                      </div>
                      <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">Total Files</div>
                    </div>
                    <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-5">
                      <div className="text-3xl font-bold text-rose-600 dark:text-rose-400">
                        {nodeData.total_issues || 0}
                      </div>
                      <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">Total Issues</div>
                    </div>
                    <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-5">
                      <div className="text-3xl font-bold text-emerald-600 dark:text-emerald-400">
                        {nodeData.issues_fixed || 0}
                      </div>
                      <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">Fixed Issues</div>
                    </div>
                    <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-5">
                      <div className="text-3xl font-bold text-violet-600 dark:text-violet-400">
                        {nodeData.avg_compliance || 0}%
                      </div>
                      <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">Avg Compliance</div>
                    </div>
                  </div>

                  {nodeData.description && (
                    <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-5">
                      <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">Description</h3>
                      <p className="text-slate-600 dark:text-slate-400">{nodeData.description}</p>
                    </div>
                  )}
                </div>
              )}

              {nodeData.type === "file" && (
                <div className="space-y-6">
                  <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-6">
                    <div className="flex items-start justify-between mb-6">
                      <div>
                        <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">
                          {nodeData.fileName || nodeData.filename}
                        </h2>
                        <div className="flex items-center gap-3 text-sm text-slate-600 dark:text-slate-400">
                          <span>
                            {fileScanDateLabel} {fileDateValue ? new Date(fileDateValue).toLocaleDateString() : "N/A"}
                          </span>
                          {nodeData.status && (
                            <span
                              className={`px-2 py-1 rounded-full text-xs font-medium ${
                                nodeData.status === "fixed"
                                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                                  : nodeData.status === "processed"
                                    ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
                                    : nodeData.status === "uploaded"
                                      ? "bg-slate-100 text-slate-700 dark:bg-slate-800/60 dark:text-slate-200"
                                      : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                              }`}
                            >
                              {nodeData.status === "uploaded" ? "Uploaded" : nodeData.status}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => onSelectScan(nodeData)}
                          disabled={fileIsUploaded}
                          className={`px-4 py-2 rounded-lg transition-colors font-medium ${
                            fileIsUploaded
                              ? "bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-400 cursor-not-allowed"
                              : "bg-violet-600 hover:bg-violet-700 text-white"
                          }`}
                        >
                          View Full Report
                        </button>
                        {fileIsUploaded && (
                          <button
                            onClick={handleBeginScan}
                            disabled={startingScan}
                            aria-label={
                              startingScan
                                ? `Starting scan for ${targetFileName}`
                                : `Begin scan for ${targetFileName}`
                            }
                            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {startingScan ? "Starting..." : "Begin Scan"}
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-4">
                      <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4">
                        <div className="text-2xl font-bold text-slate-900 dark:text-white">
                          {fileIsUploaded ? "—" : `${(nodeData.summary?.complianceScore ?? 0).toLocaleString()}%`}
                        </div>
                        <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">Compliance Score</div>
                      </div>
                      <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4">
                        <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                          {fileIsUploaded ? "—" : (nodeData.summary?.totalIssues ?? 0)}
                        </div>
                        <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">Total Issues</div>
                      </div>
                      <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4">
                        <div className="text-2xl font-bold text-rose-600 dark:text-rose-400">
                          {fileIsUploaded ? "—" : (nodeData.summary?.highSeverity ?? 0)}
                        </div>
                        <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">High Severity</div>
                      </div>
                    </div>

                    {fileIsUploaded && (
                      <div className="mt-4 p-4 bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-600 dark:text-slate-400">
                        This file is ready to scan. Use the "Begin Scan" button to generate accessibility results.
                      </div>
                    )}
                  </div>
                </div>
              )}

              {nodeData.type === "batch" && (
                <div className="space-y-6">
                  <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-6">
                    <div className="flex items-start justify-between mb-6">
                      <div>
                        <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">
                          {nodeData.name || "Batch"}
                        </h2>
                        <div className="flex items-center gap-3 text-sm text-slate-600 dark:text-slate-400">
                          <span>
                            Created on{" "}
                            {nodeData.uploadDate ? new Date(nodeData.uploadDate).toLocaleDateString() : "Unknown"}
                          </span>
                          <span>{nodeData.fileCount || 0} files</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2" role="group" aria-label="Batch actions">
                        <button
                          type="button"
                          onClick={() => onSelectBatch(nodeData.batchId)}
                          className="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg transition-colors font-medium"
                        >
                          View Batch Report
                        </button>
                        {batchHasUploadedFiles && (
                          <button
                            type="button"
                            onClick={handleBeginBatchScan}
                            disabled={startingBatchScan}
                            aria-disabled={startingBatchScan}
                            aria-busy={startingBatchScan}
                            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {startingBatchScan ? "Starting..." : "Begin Scan"}
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-4 gap-4">
                      <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4">
                        <div className="text-2xl font-bold text-slate-900 dark:text-white">
                          {nodeData.totalIssues || 0}
                        </div>
                        <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">Total Issues</div>
                      </div>
                      <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4">
                        <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                          {nodeData.fixedIssues || 0}
                        </div>
                        <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">Fixed</div>
                      </div>
                      <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4">
                        <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                          {nodeData.remainingIssues || 0}
                        </div>
                        <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">Remaining</div>
                      </div>
                      <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-4">
                        <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                          {nodeData.unprocessedFiles || 0}
                        </div>
                        <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">Unprocessed</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <svg
                className="w-20 h-20 text-slate-300 dark:text-slate-600 mb-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                />
              </svg>
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">No Selection</h3>
              <p className="text-slate-600 dark:text-slate-400">
                Select a group or file from the sidebar to view details
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
