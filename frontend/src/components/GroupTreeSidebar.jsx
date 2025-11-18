import { useState, useEffect } from "react";
import axios from "axios";
import API_BASE_URL from "../config/api";
const normalizeId = (id) => (id === null || id === undefined ? "" : String(id));

export default function GroupTreeSidebar({
  onNodeSelect,
  selectedNode,
  onRefresh,
  initialGroupId,
}) {
  const [groups, setGroups] = useState([]);
  const [expandedGroups, setExpandedGroups] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [groupFiles, setGroupFiles] = useState({});
  const [groupFolders, setGroupFolders] = useState({});
  const [error, setError] = useState(null);
  const [sectionStates, setSectionStates] = useState({});
  const [statusMessage, setStatusMessage] = useState("");

  useEffect(() => {
    if (!statusMessage) {
      return undefined;
    }

    const timeout = setTimeout(() => {
      setStatusMessage("");
    }, 3000);

    return () => clearTimeout(timeout);
  }, [statusMessage]);

  const focusDetailsPanel = () => {
    if (typeof document === "undefined") {
      return;
    }

    const focusableSelectors = [
      "[data-group-dashboard-details]",
      "#group-dashboard-details",
      "main[role='main']",
      "main",
      ".flex-1.overflow-y-auto",
    ];

    requestAnimationFrame(() => {
      const detailsElement = focusableSelectors
        .map((selector) => document.querySelector(selector))
        .find((element) => element);

      if (detailsElement) {
        if (!detailsElement.hasAttribute("tabindex")) {
          detailsElement.setAttribute("tabindex", "-1");
        }
        detailsElement.focus({ preventScroll: false });
      }
    });
  };

  useEffect(() => {
    fetchGroups();
  }, []);

  const removeGroupById = (groupId, groupName = "") => {
    const normalizedId = normalizeId(groupId);
    let wasRemoved = false;

    setGroups((prev) => {
      const filtered = prev.filter((group) => {
        const keep = normalizeId(group.id) !== normalizedId;
        if (!keep) {
          wasRemoved = true;
        }
        return keep;
      });
      return wasRemoved ? filtered : prev;
    });

    if (!wasRemoved) {
      return false;
    }

    setGroupFiles((prev) => {
      if (!Object.prototype.hasOwnProperty.call(prev, normalizedId)) {
        return prev;
      }
      const next = { ...prev };
      delete next[normalizedId];
      return next;
    });

    setGroupFolders((prev) => {
      if (!Object.prototype.hasOwnProperty.call(prev, normalizedId)) {
        return prev;
      }
      const next = { ...prev };
      delete next[normalizedId];
      return next;
    });

    setSectionStates((prev) => {
      if (!prev[normalizedId]) {
        return prev;
      }
      const next = { ...prev };
      delete next[normalizedId];
      return next;
    });

    setExpandedGroups((prev) => {
      if (!prev.has(normalizedId)) {
        return prev;
      }
      const next = new Set(prev);
      next.delete(normalizedId);
      return next;
    });

    setStatusMessage(groupName ? `${groupName} removed` : "Project removed");
    return true;
  };

  const fetchGroups = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await axios.get(`${API_BASE_URL}/api/groups`);
      const fetchedGroupsRaw = response.data.groups || [];

      const normalizedGroups = fetchedGroupsRaw.map((group) => {
        const derivedFolders = group.folderCount ?? group.batchCount ?? group.batch_count ?? 0;
        return {
          ...group,
          fileCount: group.fileCount ?? group.file_count ?? 0,
          batchCount: group.batchCount ?? group.batch_count ?? derivedFolders,
          folderCount: derivedFolders,
        };
      });

      setGroupFiles({});

      if (normalizedGroups.length === 0) {
        setGroups([]);
        setGroupFolders({});
        setExpandedGroups(new Set());
        setSectionStates({});
        if (onNodeSelect) {
          onNodeSelect(null);
        }
        return;
      }

      let foldersByGroup = normalizedGroups.reduce((acc, group) => {
        const key = normalizeId(group.id);
        acc[key] = [];
        return acc;
      }, {});

      try {
        const historyResponse = await axios.get(`${API_BASE_URL}/api/history`);
        const allFolders = historyResponse.data.batches || [];

        foldersByGroup = allFolders.reduce((acc, batch) => {
          const groupKey = normalizeId(batch.groupId);
          if (!groupKey) {
            return acc;
          }
          if (!acc[groupKey]) {
            acc[groupKey] = [];
          }
          acc[groupKey].push(batch);
          return acc;
        }, foldersByGroup);
      } catch (historyError) {
        console.error("[v0] Error fetching folder history:", historyError);
      }

      setGroupFolders(foldersByGroup);

      const groupsWithCounts = normalizedGroups.map((group) => {
        const key = normalizeId(group.id);
        const folderTotal = foldersByGroup[key]?.length || group.folderCount || 0;
        return {
          ...group,
          batchCount: folderTotal,
          folderCount: folderTotal,
        };
      });

      setGroups(groupsWithCounts);
      setSectionStates((prev) => {
        const next = { ...prev };
        groupsWithCounts.forEach((group) => {
          const key = normalizeId(group.id);
          if (!next[key]) {
            next[key] = {
              folders: false,
              files: false,
            };
          }
        });
        return next;
      });

      setExpandedGroups(new Set());
      if (onNodeSelect) {
        onNodeSelect(null);
      }
    } catch (error) {
      console.error("[v0] Error fetching groups:", error);
      setError("Failed to load groups");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const normalizedInitialId = normalizeId(initialGroupId);

    if (!normalizedInitialId || groups.length === 0) {
      return;
    }

    if (selectedNode?.type === "group" && normalizeId(selectedNode.id) === normalizedInitialId) {
      return;
    }

    const targetGroup = groups.find((group) => normalizeId(group.id) === normalizedInitialId);

    if (!targetGroup) {
      return;
    }

    const targetKey = normalizeId(targetGroup.id);
    setExpandedGroups(new Set([targetKey]));
    setSectionStates((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((key) => {
        if (key !== targetKey) {
          next[key] = {
            folders: false,
            files: false,
          };
        }
      });
      return next;
    });

    const loadTargetGroup = async () => {
      const fetchResult = await fetchGroupData(targetGroup.id, null);
      if (fetchResult?.removed) {
        return;
      }

      await handleNodeClick({
        type: "group",
        id: targetGroup.id,
        data: targetGroup,
      });
    };

    void loadTargetGroup();
  }, [initialGroupId, groups]);

  const fetchGroupData = async (groupId, prefetchedFolders = null) => {
    const normalizedId = normalizeId(groupId);

    try {
      const filesResponse = await axios.get(`${API_BASE_URL}/api/groups/${groupId}/files`);
      const files = filesResponse.data.files || [];

      setGroupFiles((prev) => ({
        ...prev,
        [normalizedId]: files,
      }));

      let foldersForGroup = Array.isArray(prefetchedFolders) ? prefetchedFolders : null;

      if (!foldersForGroup) {
        const historyResponse = await axios.get(`${API_BASE_URL}/api/history`);
        const allFolders = historyResponse.data.batches || [];
        foldersForGroup = allFolders.filter(
          (batch) => normalizeId(batch.groupId) === normalizedId
        );
      }

      setGroupFolders((prev) => ({
        ...prev,
        [normalizedId]: foldersForGroup,
      }));

      setGroups((prev) =>
        prev.map((g) =>
          normalizeId(g.id) === normalizedId
            ? {
              ...g,
              fileCount: files.length,
              batchCount: foldersForGroup.length,
              folderCount: foldersForGroup.length,
            }
            : g
        )
      );

      setSectionStates((prev) => {
        const current = prev[normalizedId] || {
          folders: false,
          files: false,
        };
        return {
          ...prev,
          [normalizedId]: current,
        };
      });

      return { success: true, removed: false };
    } catch (error) {
      console.error(`[v0] Error fetching data for group ${groupId}:`, error);

      if (error?.response?.status === 404) {
        const missingGroup = groups.find((group) => normalizeId(group.id) === normalizedId);
        removeGroupById(groupId, missingGroup?.name);
        if (onNodeSelect) {
          onNodeSelect(null);
        }
        return { success: false, removed: true };
      }

      return { success: false, removed: false };
    }
  };

  const handleGroupSelection = async (group, { moveFocus = false } = {}) => {
    if (!group) {
      return;
    }

    const normalizedId = normalizeId(group.id);
    const isAlreadyExpanded = expandedGroups.has(normalizedId);

    setExpandedGroups(new Set([normalizedId]));
    setSectionStates((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((key) => {
        if (key !== normalizedId) {
          next[key] = {
            folders: false,
            files: false,
          };
        }
      });
      return next;
    });

    const fetchPromise = !isAlreadyExpanded
      ? fetchGroupData(group.id, groupFolders[normalizedId] || null)
      : Promise.resolve(null);

    const selectionResult = await handleNodeClick(
      {
        type: "group",
        id: group.id,
        data: group,
      },
      { moveFocus }
    );

    if (selectionResult?.removedGroupId) {
      return;
    }

    const fetchResult = await fetchPromise;
    if (fetchResult?.removed) {
      return;
    }

    if (!isAlreadyExpanded && group.name) {
      setStatusMessage(`${group.name} project expanded`);
    }
  };

  const handleNodeClick = async (node, { moveFocus = false } = {}) => {
    if (!onNodeSelect) {
      return null;
    }

    try {
      const result = onNodeSelect(node);
      const resolved = result && typeof result.then === "function" ? await result : result;

      if (resolved?.removedGroupId) {
        removeGroupById(resolved.removedGroupId, resolved.removedGroupName || node?.data?.name);
      }

      return resolved;
    } catch (error) {
      console.error("[v0] Error handling node selection:", error);
      return null;
    } finally {
      if (moveFocus) {
        focusDetailsPanel();
      }
    }
  };

  const toggleSection = (groupId, section, groupName, label) => {
    const normalizedId = normalizeId(groupId);
    setSectionStates((prev) => {
      const current = prev[normalizedId] || {
        folders: false,
        files: false,
      };
      const nextValue = !current[section];
      const updated = {
        ...prev,
        [normalizedId]: {
          ...current,
          [section]: nextValue,
        },
      };
      setStatusMessage(`${label} ${nextValue ? "expanded" : "collapsed"} for ${groupName}`);
      return updated;
    });
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
    <aside
      className="w-80 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 h-full overflow-y-auto"
      aria-label="Project navigation"
    >
      <div className="p-4 border-b border-slate-200 dark:border-slate-700">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
            Projects
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
          {groups.length} projects
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
            <p className="text-sm">No projects yet</p>
          </div>
        ) : (
          <div className="space-y-1">
            {groups.map((group) => {
              const normalizedGroupId = normalizeId(group.id);
              const isExpanded = expandedGroups.has(normalizedGroupId);
              const files = groupFiles[normalizeId(group.id)] || [];
              const folders = groupFolders[normalizeId(group.id)] || [];
              const sectionState = sectionStates[normalizedGroupId] || {
                folders: false,
                files: false,
              };
              const folderCount = folders.length;
              const fileCount = files.length;
              const foldersExpanded = sectionState.folders;
              const filesExpanded = sectionState.files;
              const folderToggleDisabled = folderCount === 0;
              const fileToggleDisabled = fileCount === 0;
              const folderAriaLabel = folderToggleDisabled
                ? "Folders: no folders available"
                : `Folders: ${folderCount} ${folderCount === 1 ? "folder" : "folders"} available`;
              const fileAriaLabel = fileToggleDisabled
                ? "Files: no files available"
                : `Files: ${fileCount} ${fileCount === 1 ? "file" : "files"} available`;
              const isSelected =
                selectedNode?.type === "group" &&
                normalizeId(selectedNode?.id) === normalizedGroupId;

              return (
                <div key={group.id} className="space-y-1">
                  {/* Group Node */}
                  <button
                    type="button"
                    className={`flex w-full items-center gap-2 px-3 py-2 rounded-lg transition-colors text-left ${isSelected
                        ? "bg-violet-50 dark:bg-violet-900/20 border border-violet-500"
                        : "hover:bg-slate-100 dark:hover:bg-slate-700"
                      } focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-500`}
                    onClick={() => {
                      void handleGroupSelection(group);
                    }}
                    aria-expanded={isExpanded}
                    aria-controls={`group-${group.id}-panel`}
                    aria-current={isSelected ? "true" : undefined}
                  >
                    <span
                      className={`flex-shrink-0 text-slate-400 dark:text-slate-500 transition-transform ${isExpanded ? "rotate-90" : ""
                        }`}
                    >
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                        focusable="false"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </span>
                    <span
                      className={`flex-shrink-0 ${isSelected
                          ? "text-violet-600 dark:text-violet-400"
                          : "text-slate-400 dark:text-slate-500"
                        }`}
                    >
                      <svg
                        className="w-5 h-5"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                        focusable="false"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                        />
                      </svg>
                    </span>
                    <span className="flex-1 min-w-0">
                      <span
                        className={`block text-sm font-medium truncate ${isSelected
                            ? "text-violet-900 dark:text-violet-100"
                            : "text-slate-700 dark:text-slate-300"
                          }`}
                      >
                        {group.name}
                      </span>
                      <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">
                        {group.fileCount || 0} files, {group.folderCount || 0} folders
                      </span>
                    </span>
                  </button>

                  {isExpanded && (
                    <div id={`group-${group.id}-panel`} className="ml-6 space-y-2">
                      {/* Folders Section */}
                      <div className="space-y-1">
                        <button
                          type="button"
                          className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-semibold uppercase transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-purple-500 ${folderToggleDisabled
                              ? "cursor-not-allowed text-slate-400 dark:text-slate-500"
                              : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700/40"
                            }`}
                          onClick={() => {
                            if (folderToggleDisabled) {
                              return;
                            }
                            toggleSection(group.id, "folders", group.name, "Folders");
                          }}
                          aria-expanded={folderToggleDisabled ? undefined : foldersExpanded}
                          aria-controls={folderToggleDisabled ? undefined : `group-${group.id}-folders`}
                          aria-disabled={folderToggleDisabled || undefined}
                          disabled={folderToggleDisabled}
                          aria-label={folderAriaLabel}
                          title={`${folderCount} ${folderCount === 1 ? "folder" : "folders"}`}
                        >
                          <span className="flex items-center gap-2">
                            <span>Folders</span>
                            <span
                              aria-hidden="true"
                              className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:bg-slate-700/60 dark:text-slate-300"
                            >
                              {folderCount}
                            </span>
                          </span>
                          {!folderToggleDisabled && (
                            <svg
                              className={`h-3.5 w-3.5 transition-transform ${foldersExpanded ? "rotate-180" : ""
                                }`}
                              viewBox="0 0 20 20"
                              fill="currentColor"
                              aria-hidden="true"
                            >
                              <path
                                fillRule="evenodd"
                                d="M5.23 7.21a.75.75 0 011.06.02L10 11.173l3.71-3.94a.75.75 0 011.08 1.04l-4.24 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                                clipRule="evenodd"
                              />
                            </svg>
                          )}
                        </button>
                        {foldersExpanded && (
                          <ul id={`group-${group.id}-folders`} className="space-y-1" role="group">
                            {folders.map((folder) => {
                              const isBatchSelected =
                                selectedNode?.type === "batch" &&
                                normalizeId(selectedNode?.id) === normalizeId(folder.batchId);

                              return (
                                <li key={folder.batchId}>
                                  <button
                                    type="button"
                                    className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition-colors ${isBatchSelected
                                        ? "border border-purple-500 bg-purple-50 dark:bg-purple-900/20"
                                        : "hover:bg-slate-50 dark:hover:bg-slate-700/50"
                                      } focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-purple-500`}
                                    onClick={() =>
                                      void handleNodeClick(
                                        {
                                          type: "batch",
                                          id: folder.batchId,
                                          data: folder,
                                        },
                                        { moveFocus: true }
                                      )
                                    }
                                    aria-current={isBatchSelected ? "true" : undefined}
                                  >
                                    <span
                                      className={`flex-shrink-0 ${isBatchSelected
                                          ? "text-purple-600 dark:text-purple-400"
                                          : "text-slate-400 dark:text-slate-500"
                                        }`}
                                    >
                                      <svg
                                        className="h-4 w-4"
                                        fill="none"
                                        stroke="currentColor"
                                        viewBox="0 0 24 24"
                                        aria-hidden="true"
                                        focusable="false"
                                      >
                                        <path
                                          strokeLinecap="round"
                                          strokeLinejoin="round"
                                          strokeWidth={2}
                                          d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                                        />
                                      </svg>
                                    </span>
                                    <span className="flex-1 min-w-0">
                                      <span
                                        className={`block truncate text-sm ${isBatchSelected
                                            ? "text-purple-900 dark:text-purple-100"
                                            : "text-slate-600 dark:text-slate-400"
                                          }`}
                                      >
                                        {folder.name}
                                      </span>
                                      <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">
                                        {folder.fileCount} files
                                      </span>
                                    </span>
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                        {folderToggleDisabled && (
                          <p className="sr-only" role="status" aria-live="polite">
                            No folders available
                          </p>
                        )}
                      </div>

                      {/* Files Section */}
                      <div className="space-y-1">
                        <button
                          type="button"
                          className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-semibold uppercase transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 ${fileToggleDisabled
                              ? "cursor-not-allowed text-slate-400 dark:text-slate-500"
                              : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700/40"
                            }`}
                          onClick={() => {
                            if (fileToggleDisabled) {
                              return;
                            }
                            toggleSection(group.id, "files", group.name, "Files");
                          }}
                          aria-expanded={fileToggleDisabled ? undefined : filesExpanded}
                          aria-controls={fileToggleDisabled ? undefined : `group-${group.id}-files`}
                          aria-disabled={fileToggleDisabled || undefined}
                          disabled={fileToggleDisabled}
                          aria-label={fileAriaLabel}
                          title={`${fileCount} ${fileCount === 1 ? "file" : "files"}`}
                        >
                          <span className="flex items-center gap-2">
                            <span>Files</span>
                            <span
                              aria-hidden="true"
                              className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:bg-slate-700/60 dark:text-slate-300"
                            >
                              {fileCount}
                            </span>
                          </span>
                          {!fileToggleDisabled && (
                            <svg
                              className={`h-3.5 w-3.5 transition-transform ${filesExpanded ? "rotate-180" : ""
                                }`}
                              viewBox="0 0 20 20"
                              fill="currentColor"
                              aria-hidden="true"
                            >
                              <path
                                fillRule="evenodd"
                                d="M5.23 7.21a.75.75 0 011.06.02L10 11.173l3.71-3.94a.75.75 0 011.08 1.04l-4.24 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                                clipRule="evenodd"
                              />
                            </svg>
                          )}
                        </button>
                        {filesExpanded && (
                          <ul id={`group-${group.id}-files`} className="space-y-1" role="group">
                            {files.map((file) => {
                              const isFileSelected =
                                selectedNode?.type === "file" &&
                                normalizeId(selectedNode?.id) === normalizeId(file.id);

                              return (
                                <li key={file.id}>
                                  <button
                                    type="button"
                                    className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition-colors ${isFileSelected
                                        ? "border border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                                        : "hover:bg-slate-50 dark:hover:bg-slate-700/50"
                                      } focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500`}
                                    onClick={() =>
                                      void handleNodeClick(
                                        {
                                          type: "file",
                                          id: file.id,
                                          data: file,
                                        },
                                        { moveFocus: true }
                                      )
                                    }
                                    aria-current={isFileSelected ? "true" : undefined}
                                  >
                                    <span
                                      className={`flex-shrink-0 ${isFileSelected
                                          ? "text-blue-600 dark:text-blue-400"
                                          : "text-slate-400 dark:text-slate-500"
                                        }`}
                                    >
                                      <svg
                                        className="h-4 w-4"
                                        fill="none"
                                        stroke="currentColor"
                                        viewBox="0 0 24 24"
                                        aria-hidden="true"
                                        focusable="false"
                                      >
                                        <path
                                          strokeLinecap="round"
                                          strokeLinejoin="round"
                                          strokeWidth={2}
                                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                                        />
                                      </svg>
                                    </span>
                                    <span className="flex-1 min-w-0">
                                      <span
                                        className={`block truncate text-sm ${isFileSelected
                                            ? "text-blue-900 dark:text-blue-100"
                                            : "text-slate-600 dark:text-slate-400"
                                          }`}
                                      >
                                        {file.filename}
                                      </span>
                                      {file.status && (
                                        <span
                                          className={`mt-0.5 inline-block rounded px-1.5 py-0.5 text-xs font-medium ${file.status === "fixed"
                                              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                                              : file.status === "processed"
                                                ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
                                                : file.status === "compliant"
                                                  ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                                                  : file.status === "uploaded"
                                                    ? "bg-slate-100 text-slate-700 dark:bg-slate-800/60 dark:text-slate-200"
                                                    : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                                            }`}
                                        >
                                          {file.status === "uploaded" ? "Uploaded" : file.status}
                                        </span>
                                      )}
                                    </span>
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                        {fileToggleDisabled && (
                          <p className="sr-only" role="status" aria-live="polite">
                            No files available
                          </p>
                        )}
                      </div>

                      {files.length === 0 && folders.length === 0 && (
                        <div className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500">
                          No files or folders
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
      <div role="status" aria-live="polite" className="sr-only">
        {statusMessage}
      </div>
    </aside>
  );
}
