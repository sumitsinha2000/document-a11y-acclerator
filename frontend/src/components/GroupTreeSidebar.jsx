"use client";

import { useState, useEffect } from "react";
import axios from "axios";

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
  const [groupBatches, setGroupBatches] = useState({});
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

  const fetchGroups = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await axios.get("/api/groups");
      const fetchedGroupsRaw = response.data.groups || [];

      const normalizedGroups = fetchedGroupsRaw.map((group) => ({
        ...group,
        fileCount: group.fileCount ?? group.file_count ?? 0,
        batchCount: group.batchCount ?? group.batch_count ?? 0,
      }));

      setGroupFiles({});

      if (normalizedGroups.length === 0) {
        setGroups([]);
        setGroupBatches({});
        setExpandedGroups(new Set());
        setSectionStates({});
        return;
      }

      let batchesByGroup = normalizedGroups.reduce((acc, group) => {
        const key = normalizeId(group.id);
        acc[key] = [];
        return acc;
      }, {});

      try {
        const historyResponse = await axios.get("/api/history");
        const allBatches = historyResponse.data.batches || [];

        batchesByGroup = allBatches.reduce((acc, batch) => {
          const groupKey = normalizeId(batch.groupId);
          if (!groupKey) {
            return acc;
          }
          if (!acc[groupKey]) {
            acc[groupKey] = [];
          }
          acc[groupKey].push(batch);
          return acc;
        }, batchesByGroup);
      } catch (historyError) {
        console.error("[v0] Error fetching batch history:", historyError);
      }

      setGroupBatches(batchesByGroup);

      const groupsWithCounts = normalizedGroups.map((group) => {
        const key = normalizeId(group.id);
        return {
          ...group,
          batchCount: batchesByGroup[key]?.length || group.batchCount || 0,
        };
      });

      setGroups(groupsWithCounts);
      setSectionStates((prev) => {
        const next = { ...prev };
        groupsWithCounts.forEach((group) => {
          const key = normalizeId(group.id);
          if (!next[key]) {
            next[key] = {
              batches: false,
              files: false,
            };
          }
        });
        return next;
      });

      const preferredGroup =
        (initialGroupId &&
          groupsWithCounts.find((group) => normalizeId(group.id) === normalizeId(initialGroupId))) ||
        groupsWithCounts[0];
      const preferredGroupId = normalizeId(preferredGroup.id);

      setExpandedGroups(new Set([preferredGroupId]));

      await fetchGroupData(preferredGroup.id, batchesByGroup[preferredGroupId]);

      if (onNodeSelect) {
        onNodeSelect({
          type: "group",
          id: preferredGroup.id,
          data: preferredGroup,
        });
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

    setExpandedGroups((prev) => {
      if (prev.has(normalizedInitialId)) {
        return prev;
      }
      const updated = new Set(prev);
      updated.add(normalizedInitialId);
      return updated;
    });

    const targetKey = normalizeId(targetGroup.id);
    fetchGroupData(targetGroup.id, groupBatches[targetKey] || null);

    void handleNodeClick({
      type: "group",
      id: targetGroup.id,
      data: targetGroup,
    });
  }, [initialGroupId, groups]);

  const fetchGroupData = async (groupId, prefetchedBatches = null) => {
    try {
      const filesResponse = await axios.get(`/api/groups/${groupId}/files`);
      const files = filesResponse.data.files || [];
      const normalizedId = normalizeId(groupId);
      setGroupFiles((prev) => ({
        ...prev,
        [normalizedId]: files,
      }));

      let batchesForGroup = Array.isArray(prefetchedBatches)
        ? prefetchedBatches
        : null;

      if (!batchesForGroup) {
        const historyResponse = await axios.get(`/api/history`);
        const allBatches = historyResponse.data.batches || [];
        batchesForGroup = allBatches.filter(
          (batch) => normalizeId(batch.groupId) === normalizedId
        );
      }

      setGroupBatches((prev) => ({
        ...prev,
        [normalizedId]: batchesForGroup,
      }));
      setGroups((prev) =>
        prev.map((g) =>
          normalizeId(g.id) === normalizedId
            ? {
              ...g,
              fileCount: files.length,
              batchCount: batchesForGroup.length,
            }
            : g
        )
      );
      setSectionStates((prev) => {
        const current = prev[normalizedId] || {
          batches: false,
          files: false,
        };
        return {
          ...prev,
          [normalizedId]: current,
        };
      });
    } catch (error) {
      console.error(`[v0] Error fetching data for group ${groupId}:`, error);
    }
  };

  const toggleGroup = async (groupId, groupName) => {
    const normalizedId = normalizeId(groupId);
    const newExpanded = new Set(expandedGroups);
    let nextState;
    if (newExpanded.has(normalizedId)) {
      newExpanded.delete(normalizedId);
      nextState = "collapsed";
      setSectionStates((prev) => ({
        ...prev,
        [normalizedId]: {
          batches: false,
          files: false,
        },
      }));
    } else {
      newExpanded.add(normalizedId);
      await fetchGroupData(groupId, groupBatches[normalizedId] || null);
      nextState = "expanded";
    }
    setExpandedGroups(newExpanded);
    if (groupName) {
      setStatusMessage(`${groupName} ${nextState}`);
    }
  };

  const handleNodeClick = async (node, { moveFocus = false } = {}) => {
    if (!onNodeSelect) {
      return;
    }

    try {
      const result = onNodeSelect(node);
      if (result && typeof result.then === "function") {
        await result;
      }
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
        batches: false,
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
      aria-label="Group navigation"
    >
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
              const normalizedGroupId = normalizeId(group.id);
              const isExpanded = expandedGroups.has(normalizedGroupId);
              const files = groupFiles[normalizeId(group.id)] || [];
              const batches = groupBatches[normalizeId(group.id)] || [];
              const sectionState = sectionStates[normalizedGroupId] || {
                batches: false,
                files: false,
              };
              const batchCount = batches.length;
              const fileCount = files.length;
              const batchesExpanded = sectionState.batches;
              const filesExpanded = sectionState.files;
              const batchToggleDisabled = batchCount === 0;
              const fileToggleDisabled = fileCount === 0;
              const batchAriaLabel = batchToggleDisabled
                ? "Batches: no batches available"
                : `Batches: ${batchCount} ${batchCount === 1 ? "batch" : "batches"} available`;
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
                      toggleGroup(group.id, group.name);
                      void handleNodeClick({
                        type: "group",
                        id: group.id,
                        data: group,
                      });
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
                        {group.fileCount || 0} files, {group.batchCount || 0} batches
                      </span>
                    </span>
                  </button>

                  {isExpanded && (
                    <div id={`group-${group.id}-panel`} className="ml-6 space-y-2">
                      {/* Batches Section */}
                      <div className="space-y-1">
                        <button
                          type="button"
                          className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-semibold uppercase transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-purple-500 ${batchToggleDisabled
                              ? "cursor-not-allowed text-slate-400 dark:text-slate-500"
                              : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700/40"
                            }`}
                          onClick={() => {
                            if (batchToggleDisabled) {
                              return;
                            }
                            toggleSection(group.id, "batches", group.name, "Batches");
                          }}
                          aria-expanded={batchToggleDisabled ? undefined : batchesExpanded}
                          aria-controls={batchToggleDisabled ? undefined : `group-${group.id}-batches`}
                          aria-disabled={batchToggleDisabled || undefined}
                          disabled={batchToggleDisabled}
                          aria-label={batchAriaLabel}
                          title={`${batchCount} ${batchCount === 1 ? "batch" : "batches"}`}
                        >
                          <span className="flex items-center gap-2">
                            <span>Batches</span>
                            <span
                              aria-hidden="true"
                              className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:bg-slate-700/60 dark:text-slate-300"
                            >
                              {batchCount}
                            </span>
                          </span>
                          {!batchToggleDisabled && (
                            <svg
                              className={`h-3.5 w-3.5 transition-transform ${batchesExpanded ? "rotate-180" : ""
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
                        {batchesExpanded && (
                          <ul id={`group-${group.id}-batches`} className="space-y-1" role="group">
                            {batches.map((batch) => {
                              const isBatchSelected =
                                selectedNode?.type === "batch" &&
                                normalizeId(selectedNode?.id) === normalizeId(batch.batchId);

                              return (
                                <li key={batch.batchId}>
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
                                          id: batch.batchId,
                                          data: batch,
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
                                        {batch.name}
                                      </span>
                                      <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">
                                        {batch.fileCount} files
                                      </span>
                                    </span>
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                        {batchToggleDisabled && (
                          <div className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500" aria-live="polite">
                            No batches available
                          </div>
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
                          <div className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500" aria-live="polite">
                            No files available
                          </div>
                        )}
                      </div>

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
      <div role="status" aria-live="polite" className="sr-only">
        {statusMessage}
      </div>
    </aside>
  );
}
