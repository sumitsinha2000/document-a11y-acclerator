"use client";

import { useState, useEffect } from "react";
import axios from "axios";

export default function GroupTreeSidebar({
  onNodeSelect,
  selectedNode,
  onRefresh,
}) {
  const [groups, setGroups] = useState([]);
  const [expandedGroups, setExpandedGroups] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [groupFiles, setGroupFiles] = useState({});
  const [groupBatches, setGroupBatches] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchGroups();
  }, []);

  const fetchGroups = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await axios.get("/api/groups");
      const fetchedGroups = response.data.groups || [];
      setGroups(fetchedGroups);

  if (fetchedGroups.length > 0) {
  const firstGroup = fetchedGroups[0]
  const firstGroupId = firstGroup.id

  // Expand the first group by default
  setExpandedGroups(new Set([firstGroupId]))

  // Fetch its files and batches
  await fetchGroupData(firstGroupId)

  // 🆕 Notify parent dashboard so it shows group data immediately
  if (onNodeSelect) {
    onNodeSelect({
      type: "group",
      id: firstGroupId,
      data: firstGroup,
    })
  }
}

    } catch (error) {
      console.error("[v0] Error fetching groups:", error);
      setError("Failed to load groups");
    } finally {
      setLoading(false);
    }
  };

  const fetchGroupData = async (groupId) => {
    try {
      const filesResponse = await axios.get(`/api/groups/${groupId}/files`);
      setGroupFiles((prev) => ({
        ...prev,
        [groupId]: filesResponse.data.files || [],
      }));

      const historyResponse = await axios.get(`/api/history`);
      const allBatches = historyResponse.data.batches || [];

      const groupBatchesData = allBatches.filter(
        (batch) => batch.groupId === groupId
      );
    setGroupBatches((prev) => ({
        ...prev,
        [groupId]: groupBatchesData,
      }));
      setGroups((prev) =>
        prev.map((g) =>
            g.id === groupId
            ? { ...g, fileCount: (filesResponse.data.files || []).length, batchCount: groupBatchesData.length }
            : g
        )
        )
    } catch (error) {
      console.error(`[v0] Error fetching data for group ${groupId}:`, error);
    }
  };

  const toggleGroup = async (groupId) => {
    const newExpanded = new Set(expandedGroups);
    if (newExpanded.has(groupId)) {
      newExpanded.delete(groupId);
    } else {
      newExpanded.add(groupId);
      await fetchGroupData(groupId);
    }
    setExpandedGroups(newExpanded);
  };

  const handleNodeClick = (node) => {
    if (onNodeSelect) {
      onNodeSelect(node);
    }
  };

  const handleRefresh = async () => {
    await fetchGroups();
    if (onRefresh) {
      onRefresh();
    }
  };

  if (loading) {
    return (
      <div className="w-80 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-3/4"></div>
          <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-1/2"></div>
          <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-2/3"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-80 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 p-4">
        <div className="text-center py-8">
          <svg
            className="w-12 h-12 mx-auto mb-2 text-rose-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <p className="text-sm text-slate-600 dark:text-slate-400 mb-3">
            {error}
          </p>
          <button
            onClick={handleRefresh}
            className="px-3 py-1.5 text-sm bg-violet-600 hover:bg-violet-700 text-white rounded-lg transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="w-80 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 h-full overflow-y-auto">
      <div className="p-4 border-b border-slate-200 dark:border-slate-700">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
            Groups
          </h2>
          <button
            onClick={handleRefresh}
            className="p-1.5 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
            title="Refresh"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </button>
        </div>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {groups.length} groups
        </p>
      </div>

      <div className="p-2">
        {groups.length === 0 ? (
          <div className="text-center py-8 text-slate-500 dark:text-slate-400">
            <svg
              className="w-12 h-12 mx-auto mb-2 text-slate-300 dark:text-slate-600"
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
            <p className="text-sm">No groups yet</p>
          </div>
        ) : (
          <div className="space-y-1">
            {groups.map((group) => {
              const isExpanded = expandedGroups.has(group.id);
              const files = groupFiles[group.id] || [];
              const batches = groupBatches[group.id] || [];
              const isSelected =
                selectedNode?.type === "group" && selectedNode?.id === group.id;

              return (
                <div key={group.id} className="space-y-1">
                  {/* Group Node */}
                  <div
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
                      isSelected
                        ? "bg-violet-50 dark:bg-violet-900/20 border border-violet-500"
                        : "hover:bg-slate-100 dark:hover:bg-slate-700"
                    }`}
                    onClick={() => {
                      toggleGroup(group.id);
                      handleNodeClick({
                        type: "group",
                        id: group.id,
                        data: group,
                      });
                    }}
                  >
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleGroup(group.id);
                      }}
                      className="flex-shrink-0"
                    >
                      <svg
                        className={`w-4 h-4 text-slate-400 dark:text-slate-500 transition-transform ${
                          isExpanded ? "rotate-90" : ""
                        }`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M9 5l7 7-7 7"
                        />
                      </svg>
                    </button>
                    <svg
                      className={`w-5 h-5 flex-shrink-0 ${
                        isSelected
                          ? "text-violet-600 dark:text-violet-400"
                          : "text-slate-400 dark:text-slate-500"
                      }`}
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
                    <div className="flex-1 min-w-0">
                      <p
                        className={`text-sm font-medium truncate ${
                          isSelected
                            ? "text-violet-900 dark:text-violet-100"
                            : "text-slate-700 dark:text-slate-300"
                        }`}
                      >
                        {group.name}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {group.fileCount || 0} files, {group.batchCount || 0} batches
                      </p>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="ml-6 space-y-1">
                      {/* Batches Section */}
                      {batches.length > 0 && (
                        <div className="space-y-1">
                          <div className="px-3 py-1 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase">
                            Batches
                          </div>
                          {batches.map((batch) => {
                            const isBatchSelected =
                              selectedNode?.type === "batch" &&
                              selectedNode?.id === batch.batchId;

                            return (
                              <div
                                key={batch.batchId}
                                className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
                                  isBatchSelected
                                    ? "bg-purple-50 dark:bg-purple-900/20 border border-purple-500"
                                    : "hover:bg-slate-50 dark:hover:bg-slate-700/50"
                                }`}
                                onClick={() =>
                                  handleNodeClick({
                                    type: "batch",
                                    id: batch.batchId,
                                    data: batch,
                                  })
                                }
                              >
                                <svg
                                  className={`w-4 h-4 flex-shrink-0 ${
                                    isBatchSelected
                                      ? "text-purple-600 dark:text-purple-400"
                                      : "text-slate-400 dark:text-slate-500"
                                  }`}
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                                  />
                                </svg>
                                <div className="flex-1 min-w-0">
                                  <p
                                    className={`text-sm truncate ${
                                      isBatchSelected
                                        ? "text-purple-900 dark:text-purple-100"
                                        : "text-slate-600 dark:text-slate-400"
                                    }`}
                                  >
                                    {batch.name}
                                  </p>
                                  <p className="text-xs text-slate-500 dark:text-slate-400">
                                    {batch.fileCount} files
                                  </p>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* Files Section */}
                      {files.length > 0 && (
                        <div className="space-y-1">
                          <div className="px-3 py-1 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase">
                            Files
                          </div>
                          {files.map((file) => {
                            const isFileSelected =
                              selectedNode?.type === "file" &&
                              selectedNode?.id === file.id;

                            return (
                              <div
                                key={file.id}
                                className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
                                  isFileSelected
                                    ? "bg-blue-50 dark:bg-blue-900/20 border border-blue-500"
                                    : "hover:bg-slate-50 dark:hover:bg-slate-700/50"
                                }`}
                                onClick={() =>
                                  handleNodeClick({
                                    type: "file",
                                    id: file.id,
                                    data: file,
                                  })
                                }
                              >
                                <svg
                                  className={`w-4 h-4 flex-shrink-0 ${
                                    isFileSelected
                                      ? "text-blue-600 dark:text-blue-400"
                                      : "text-slate-400 dark:text-slate-500"
                                  }`}
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                                  />
                                </svg>
                                <div className="flex-1 min-w-0">
                                  <p
                                    className={`text-sm truncate ${
                                      isFileSelected
                                        ? "text-blue-900 dark:text-blue-100"
                                        : "text-slate-600 dark:text-slate-400"
                                    }`}
                                  >
                                    {file.filename}
                                  </p>
                                  {file.status && (
                                    <span
                                      className={`inline-block mt-0.5 px-1.5 py-0.5 text-xs font-medium rounded ${
                                        file.status === "fixed"
                                          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                                          : file.status === "processed"
                                          ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
                                          : file.status === "compliant"
                                          ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                                          : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                                      }`}
                                    >
                                      {file.status}
                                    </span>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {files.length === 0 && batches.length === 0 && (
                        <div className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500">
                          No files or batches
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
