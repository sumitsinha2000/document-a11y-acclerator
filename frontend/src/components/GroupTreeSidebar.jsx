import { useState, useEffect } from "react";
import axios from "axios";
import API_BASE_URL from "../config/api";
const normalizeId = (id) => (id === null || id === undefined ? "" : String(id));
const FILE_STATUS_STYLES = {
  fixed: "bg-emerald-100 text-emerald-800",
  processed: "bg-indigo-100 text-indigo-800",
  compliant: "bg-green-100 text-green-700",
  uploaded: "bg-gray-100 text-gray-700",
  default: "bg-amber-100 text-amber-800",
};

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
  const [newProjectName, setNewProjectName] = useState("");
  const [newFolderNames, setNewFolderNames] = useState({});
  const [editingGroupId, setEditingGroupId] = useState(null);
  const [editingGroupName, setEditingGroupName] = useState("");
  const [deletingGroupId, setDeletingGroupId] = useState(null);
  const [editingBatchId, setEditingBatchId] = useState(null);
  const [editingBatchGroupId, setEditingBatchGroupId] = useState(null);
  const [editingBatchName, setEditingBatchName] = useState("");
  const [deletingBatchInfo, setDeletingBatchInfo] = useState({ id: null, groupId: null });
  const [groupDeleteInProgress, setGroupDeleteInProgress] = useState(false);
  const [batchDeleteInProgress, setBatchDeleteInProgress] = useState(false);
  const [sidebarView, setSidebarView] = useState("projects");
  const [activeFolderView, setActiveFolderView] = useState(null);
  const [folderFiles, setFolderFiles] = useState([]);
  const [folderFilesLoading, setFolderFilesLoading] = useState(false);
  const [folderFilesError, setFolderFilesError] = useState(null);

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

    setGroupBatches((prev) => {
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

    setStatusMessage(groupName ? `${groupName} removed` : "Group removed");
    return true;
  };

  const fetchGroups = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await axios.get(`${API_BASE_URL}/api/groups`);
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
        if (onNodeSelect) {
          onNodeSelect(null);
        }
        return;
      }

      let batchesByGroup = normalizedGroups.reduce((acc, group) => {
        const key = normalizeId(group.id);
        acc[key] = [];
        return acc;
      }, {});

      try {
        const historyResponse = await axios.get(`${API_BASE_URL}/api/history`);
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
            batches: false,
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

  const fetchGroupData = async (groupId, prefetchedBatches = null) => {
    const normalizedId = normalizeId(groupId);

    try {
      const filesResponse = await axios.get(`${API_BASE_URL}/api/groups/${groupId}/files`);
      const files = filesResponse.data.files || [];

      setGroupFiles((prev) => ({
        ...prev,
        [normalizedId]: files,
      }));

      let batchesForGroup = Array.isArray(prefetchedBatches) ? prefetchedBatches : null;

      if (!batchesForGroup) {
        const historyResponse = await axios.get(`${API_BASE_URL}/api/history`);
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

    ensureProjectView();

    const normalizedId = normalizeId(group.id);
    const isAlreadyExpanded = expandedGroups.has(normalizedId);

    setExpandedGroups((prev) => {
      if (isAlreadyExpanded) {
        const next = new Set(prev);
        next.delete(normalizedId);
        return next;
      }
      return new Set([normalizedId]);
    });

    setSectionStates((prev) => {
      const next = { ...prev };
      if (isAlreadyExpanded) {
        next[normalizedId] = {
          batches: false,
          files: false,
        };
        return next;
      }
      Object.keys(next).forEach((key) => {
        if (key !== normalizedId) {
          next[key] = {
            batches: false,
            files: false,
          };
        }
      });
      if (!next[normalizedId]) {
        next[normalizedId] = {
          batches: false,
          files: false,
        };
      }
      return next;
    });

    const fetchPromise = !isAlreadyExpanded
      ? fetchGroupData(group.id, groupBatches[normalizedId] || null)
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

    if (group.name) {
      setStatusMessage(`${group.name} ${isAlreadyExpanded ? "collapsed" : "expanded"}`);
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

  const handleMockCreateProject = (event) => {
    if (event) {
      event.preventDefault();
    }
    if (!newProjectName.trim()) {
      setStatusMessage("Enter a project name first");
      return;
    }
    setStatusMessage(`Creating "${newProjectName.trim()}" is coming soon`);
    setNewProjectName("");
  };

  const ensureProjectView = () => {
    setSidebarView("projects");
    setActiveFolderView(null);
    setFolderFiles([]);
    setFolderFilesError(null);
    setFolderFilesLoading(false);
  };

  const closeFolderView = () => {
    ensureProjectView();
  };

  const openFolderView = async (group, batch) => {
    const normalizedBatchId = normalizeId(batch.batchId || batch.id);
    if (!normalizedBatchId) {
      return;
    }
    setSidebarView("folder");
    const folderMeta = {
      groupId: group.id,
      groupName: group.name,
      folderId: batch.batchId || batch.id,
      folderName: batch.name || `Folder ${batch.batchId || batch.id}`,
    };
    setActiveFolderView(folderMeta);
    setFolderFiles([]);
    setFolderFilesError(null);
    setFolderFilesLoading(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/api/batch/${batch.batchId || batch.id}`);
      const folderDetails = response.data || {};
      const scans = folderDetails.scans || [];
      setFolderFiles(scans);
      setActiveFolderView((prev) => ({
        ...(prev || folderMeta),
        folderName: folderDetails.batchName || folderDetails.folderName || folderMeta.folderName,
        groupName: folderDetails.groupName || folderMeta.groupName,
        totalFiles: folderDetails.total_files ?? folderDetails.totalFiles,
        summary: {
          issues: folderDetails.total_issues ?? folderDetails.totalIssues,
          fixed: folderDetails.fixed_issues ?? folderDetails.fixedIssues,
        },
      }));
    } catch (folderError) {
      console.error("[GroupTreeSidebar] Failed to load folder files:", folderError);
      setFolderFilesError(folderError?.response?.data?.error || "Failed to load folder files");
    } finally {
      setFolderFilesLoading(false);
    }
  };

  const handleFolderButtonClick = (group, batch) => {
    const batchId = batch.batchId || batch.id;
    if (!batchId) {
      return;
    }
    const batchData = {
      ...batch,
      batchId,
    };
    void openFolderView(group, batchData);
    void handleNodeClick(
      {
        type: "batch",
        id: batchId,
        data: batchData,
      },
      { moveFocus: true }
    );
  };

  const handleFolderNameChange = (groupId, value) => {
    const key = normalizeId(groupId);
    setNewFolderNames((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const handleCreateFolder = async (event, group) => {
    if (event) {
      event.preventDefault();
    }
    if (!group?.id) {
      return;
    }
    const key = normalizeId(group.id);
    const folderName = (newFolderNames[key] || "").trim();
    if (!folderName) {
      setStatusMessage("Enter a folder name first");
      return;
    }
    try {
      const response = await axios.post(`${API_BASE_URL}/api/folders`, {
        name: folderName,
        groupId: group.id,
      });
      const folderPayload = response.data?.folder || {};
      const mappedFolder = {
        batchId: folderPayload.folderId || folderPayload.batchId || folderPayload.id,
        name: folderPayload.name || folderName,
        groupId: folderPayload.groupId || folderPayload.group_id || group.id,
        fileCount: folderPayload.totalFiles ?? folderPayload.total_files ?? 0,
        status: folderPayload.status || "uploaded",
        createdAt: folderPayload.createdAt || folderPayload.created_at,
      };
      setGroupBatches((prev) => {
        const list = prev[key] || [];
        return {
          ...prev,
          [key]: [...list, mappedFolder],
        };
      });
      setGroups((prev) =>
        prev.map((existingGroup) =>
          normalizeId(existingGroup.id) === key
            ? {
                ...existingGroup,
                batchCount: (existingGroup.batchCount || 0) + 1,
                folderCount: (existingGroup.folderCount || existingGroup.batchCount || 0) + 1,
              }
            : existingGroup
        )
      );
      setStatusMessage(`${folderName} folder created`);
      setNewFolderNames((prev) => ({
        ...prev,
        [key]: "",
      }));
    } catch (folderError) {
      console.error("[GroupTreeSidebar] Failed to create folder:", folderError);
      setStatusMessage(folderError?.response?.data?.error || "Failed to create folder");
    }
  };

  const startGroupEdit = (group) => {
    setEditingGroupId(group.id);
    setEditingGroupName(group.name || "");
    setDeletingGroupId(null);
  };

  const cancelGroupEdit = () => {
    setEditingGroupId(null);
    setEditingGroupName("");
  };

  const saveGroupEdit = async (event) => {
    if (event) {
      event.preventDefault();
    }
    if (!editingGroupId) {
      return;
    }
    const trimmedName = editingGroupName.trim();
    if (!trimmedName) {
      setStatusMessage("Project name is required");
      return;
    }

    const normalizedId = normalizeId(editingGroupId);
    const currentGroup = groups.find((group) => normalizeId(group.id) === normalizedId);
    try {
      const response = await axios.put(`${API_BASE_URL}/api/groups/${editingGroupId}`, {
        name: trimmedName,
        description: currentGroup?.description || "",
      });
      const updatedGroup = response.data?.group;
      setGroups((prev) =>
        prev.map((group) =>
          normalizeId(group.id) === normalizedId
            ? {
                ...group,
                ...(updatedGroup || {}),
                name: trimmedName,
              }
            : group
        )
      );
      setStatusMessage(`${trimmedName} updated`);
      cancelGroupEdit();
    } catch (error) {
      console.error("[GroupTreeSidebar] Failed to update group:", error);
      setStatusMessage(error?.response?.data?.error || "Failed to update project");
    }
  };

  const requestGroupDelete = (group) => {
    setDeletingGroupId(group.id);
    setEditingGroupId(null);
    setGroupDeleteInProgress(false);
  };

  const cancelGroupDelete = () => {
    setDeletingGroupId(null);
    setGroupDeleteInProgress(false);
  };

  const confirmGroupDelete = async () => {
    if (!deletingGroupId) {
      return;
    }
    const normalizedId = normalizeId(deletingGroupId);
    const targetGroup = groups.find((group) => normalizeId(group.id) === normalizedId);
    setGroupDeleteInProgress(true);
    try {
      await axios.delete(`${API_BASE_URL}/api/groups/${deletingGroupId}`);
      removeGroupById(deletingGroupId, targetGroup?.name);
      setStatusMessage(`${targetGroup?.name || "Project"} deleted`);
    } catch (error) {
      console.error("[GroupTreeSidebar] Failed to delete group:", error);
      setStatusMessage(error?.response?.data?.error || "Failed to delete project");
    } finally {
      cancelGroupDelete();
    }
  };

  const startBatchEdit = (batch, groupId) => {
    setEditingBatchId(batch.batchId);
    setEditingBatchGroupId(groupId);
    setEditingBatchName(batch.name || "");
    setDeletingBatchInfo({ id: null, groupId: null });
  };

  const cancelBatchEdit = () => {
    setEditingBatchId(null);
    setEditingBatchGroupId(null);
    setEditingBatchName("");
  };

  const saveBatchEdit = async (event) => {
    if (event) {
      event.preventDefault();
    }
    if (!editingBatchId) {
      return;
    }
    const trimmedName = editingBatchName.trim();
    if (!trimmedName) {
      setStatusMessage("Folder name is required");
      return;
    }
    const normalizedBatchId = normalizeId(editingBatchId);
    const normalizedGroupId = normalizeId(editingBatchGroupId);
    try {
      await axios.patch(`${API_BASE_URL}/api/folders/${editingBatchId}/rename`, {
        folderName: trimmedName,
      });
      setGroupBatches((prev) => {
        const next = { ...prev };
        const list = (next[normalizedGroupId] || []).map((batch) =>
          normalizeId(batch.batchId) === normalizedBatchId ? { ...batch, name: trimmedName } : batch
        );
        next[normalizedGroupId] = list;
        return next;
      });
      setStatusMessage(`${trimmedName} renamed`);
      cancelBatchEdit();
    } catch (error) {
      console.error("[GroupTreeSidebar] Failed to rename folder:", error);
      setStatusMessage(error?.response?.data?.error || "Failed to rename folder");
    }
  };

  const requestBatchDelete = (batch, groupId) => {
    setDeletingBatchInfo({ id: batch.batchId, groupId });
    setBatchDeleteInProgress(false);
    cancelBatchEdit();
  };

  const cancelBatchDelete = () => {
    setDeletingBatchInfo({ id: null, groupId: null });
    setBatchDeleteInProgress(false);
  };

  const confirmBatchDelete = async () => {
    if (!deletingBatchInfo.id) {
      return;
    }
    const { id, groupId } = deletingBatchInfo;
    const normalizedBatchId = normalizeId(id);
    const normalizedGroupId = normalizeId(groupId);
    const existingList = groupBatches[normalizedGroupId] || [];
    const batchName =
      existingList.find((batch) => normalizeId(batch.batchId) === normalizedBatchId)?.name || "Folder";
    setBatchDeleteInProgress(true);
    try {
      await axios.delete(`${API_BASE_URL}/api/folders/${id}`);
      const updatedList = existingList.filter(
        (batch) => normalizeId(batch.batchId) !== normalizedBatchId
      );
      setGroupBatches((prev) => ({
        ...prev,
        [normalizedGroupId]: updatedList,
      }));
      setGroups((prev) =>
        prev.map((group) =>
          normalizeId(group.id) === normalizedGroupId
            ? {
                ...group,
                batchCount: updatedList.length,
                folderCount: updatedList.length,
              }
            : group
        )
      );
      setStatusMessage(`${batchName} deleted`);
    } catch (error) {
      console.error("[GroupTreeSidebar] Failed to delete folder:", error);
      setStatusMessage(error?.response?.data?.error || "Failed to delete folder");
    } finally {
      cancelBatchDelete();
    }
  };

  const handleRefresh = async () => {
    ensureProjectView();
    await fetchGroups();
    if (onRefresh) {
      onRefresh();
    }
  };

  if (loading) {
    return (
      <aside className="w-full max-w-sm flex-shrink-0 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="space-y-4 animate-pulse">
          <div className="h-5 w-32 rounded bg-gray-200 dark:bg-gray-700" />
          <div className="flex gap-2">
            <div className="h-10 flex-1 rounded-md bg-gray-100 dark:bg-gray-700" />
            <div className="h-10 w-24 rounded-md bg-gray-200 dark:bg-gray-600" />
          </div>
          <div className="space-y-2">
            <div className="h-12 rounded-md bg-gray-100 dark:bg-gray-700" />
            <div className="h-12 rounded-md bg-gray-100 dark:bg-gray-700" />
            <div className="h-12 rounded-md bg-gray-100 dark:bg-gray-700" />
          </div>
        </div>
      </aside>
    );
  }

  if (error) {
    return (
      <aside className="w-full max-w-sm flex-shrink-0 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 text-center space-y-4">
        <svg
          className="mx-auto h-12 w-12 text-rose-500"
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
        <p className="text-sm text-gray-600 dark:text-gray-300">{error}</p>
        <button
          onClick={handleRefresh}
          className="inline-flex items-center justify-center rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700"
          type="button"
        >
          Retry
        </button>
      </aside>
    );
  }

  if (sidebarView === "folder" && activeFolderView) {
    const isFileSelected = (fileId) =>
      selectedNode?.type === "file" && normalizeId(selectedNode?.id) === normalizeId(fileId);

    return (
      <aside className="w-full max-w-sm flex-shrink-0 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 flex flex-col space-y-4">
        <div className="flex items-center gap-3 border-b border-gray-200 pb-3 dark:border-gray-700">
          <button
            type="button"
            onClick={closeFolderView}
            className="rounded-full bg-gray-100 p-2 text-gray-700 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
            aria-label="Back to projects"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
              {activeFolderView.groupName || "Selected project"}
            </p>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Files in {activeFolderView.folderName}
            </h2>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto space-y-2">
          {folderFilesLoading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4].map((item) => (
                <div
                  key={item}
                  className="h-12 rounded-lg bg-gray-100 animate-pulse dark:bg-gray-700"
                ></div>
              ))}
            </div>
          ) : folderFilesError ? (
            <div className="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-100">
              {folderFilesError}
            </div>
          ) : folderFiles.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-gray-200 px-4 py-6 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-300">
              No files in this folder yet.
            </div>
          ) : (
            folderFiles.map((file) => {
              const fileId = file.scanId || file.id || file.fileId;
              const selected = isFileSelected(fileId);
              return (
                <button
                  key={fileId || file.filename}
                  type="button"
                  className={`w-full rounded-xl border px-4 py-3 text-left transition ${
                    selected
                      ? "border-indigo-500 bg-indigo-50 text-indigo-900 dark:border-indigo-500/60 dark:bg-indigo-900/30 dark:text-indigo-100"
                      : "border-gray-200 bg-white text-gray-800 hover:border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
                  }`}
                  onClick={() => {
                    if (!fileId) {
                      return;
                    }
                    void handleNodeClick(
                      {
                        type: "file",
                        id: fileId,
                        data: {
                          ...file,
                          filename: file.filename || file.fileName,
                        },
                      },
                      { moveFocus: true }
                    );
                  }}
                >
                  <p className="text-sm font-semibold truncate">{file.filename || file.fileName || "Untitled file"}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {(file.status || "uploaded").toUpperCase()}
                  </p>
                </button>
              );
            })
          )}
        </div>
        <div role="status" aria-live="polite" className="sr-only">
          {statusMessage}
        </div>
      </aside>
    );
  }

  return (
    <aside
      className="w-full max-w-sm flex-shrink-0 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 flex flex-col space-y-4"
      aria-label="Group navigation"
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
            Projects
          </p>
          <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100">Project Library</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">{groups.length} projects</p>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          className="rounded-md border border-transparent bg-gray-100 dark:bg-gray-700 p-2 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600"
          title="Refresh"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>

      <form onSubmit={handleMockCreateProject} className="flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          value={newProjectName}
          onChange={(event) => setNewProjectName(event.target.value)}
          placeholder="New project name..."
          className="flex-grow bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
          aria-label="New project name"
        />
        <button
          type="submit"
          disabled={!newProjectName.trim()}
          className="flex items-center justify-center gap-2 bg-indigo-600 text-white font-semibold px-4 py-2 rounded-md hover:bg-indigo-700 disabled:bg-gray-400 dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-sm"
        >
          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              fillRule="evenodd"
              d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z"
              clipRule="evenodd"
            />
          </svg>
          <span>Create</span>
        </button>
      </form>

      <div className="flex-1 overflow-y-auto space-y-1 pr-1 -mr-1">
        {groups.length === 0 ? (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400 text-sm">
            <p>No groups yet. Create one to get started!</p>
          </div>
        ) : (
          groups.map((group) => {
            const normalizedGroupId = normalizeId(group.id);
            const isExpanded = expandedGroups.has(normalizedGroupId);
            const files = groupFiles[normalizedGroupId] || [];
            const batches = groupBatches[normalizedGroupId] || [];
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
              ? "Folders: no folders available"
              : `Folders: ${batchCount} ${batchCount === 1 ? "folder" : "folders"} available`;
            const fileAriaLabel = fileToggleDisabled
              ? "Files: no files available"
              : `Files: ${fileCount} ${fileCount === 1 ? "file" : "files"} available`;
            const isSelected =
              selectedNode?.type === "group" && normalizeId(selectedNode?.id) === normalizedGroupId;
            const isEditingGroup =
              editingGroupId && normalizeId(editingGroupId) === normalizedGroupId;
            const isDeletingGroup =
              deletingGroupId && normalizeId(deletingGroupId) === normalizedGroupId;

            return (
              <div key={group.id} className="space-y-2">
                <div className="relative group/project">
                  {isEditingGroup ? (
                    <form
                      onSubmit={saveGroupEdit}
                      className="flex items-center gap-2 rounded-md bg-indigo-50 p-2.5 dark:bg-indigo-900/30"
                    >
                      <input
                        type="text"
                        value={editingGroupName}
                        onChange={(event) => setEditingGroupName(event.target.value)}
                        className="flex-1 rounded-md border border-indigo-200 bg-white px-2 py-1 text-sm text-gray-800 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-indigo-500/40 dark:bg-gray-950 dark:text-gray-100"
                        autoFocus
                        aria-label="Edit project name"
                      />
                      <button
                        type="submit"
                        className="rounded-md bg-indigo-600 p-1.5 text-white shadow-sm shadow-indigo-200 hover:bg-indigo-700"
                        title="Save project name"
                      >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      </button>
                      <button
                        type="button"
                        onClick={cancelGroupEdit}
                        className="rounded-md bg-gray-200 p-1.5 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-100"
                        title="Cancel edit"
                      >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </form>
                  ) : isDeletingGroup ? (
                    <div className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:bg-rose-950/40 dark:text-rose-100">
                      <p className="mb-2">
                        {groupDeleteInProgress ? "Deleting project..." : "Delete this project?"}
                      </p>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={confirmGroupDelete}
                          disabled={groupDeleteInProgress}
                          className="flex-1 rounded-md bg-rose-600 px-3 py-1 text-white shadow-sm shadow-rose-200 transition hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {groupDeleteInProgress ? "Deleting..." : "Delete"}
                        </button>
                        <button
                          type="button"
                          onClick={cancelGroupDelete}
                          disabled={groupDeleteInProgress}
                          className="flex-1 rounded-md bg-gray-200 px-3 py-1 text-gray-700 hover:bg-gray-300 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-gray-700 dark:text-gray-200"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                <button
                  type="button"
                  className={`w-full text-left p-2.5 rounded-md transition group flex items-center gap-3 ${isSelected
                      ? "bg-gray-200 dark:bg-gray-700"
                      : "hover:bg-gray-100 dark:hover:bg-gray-700/50"
                    }`}
                  onClick={() => {
                    void handleGroupSelection(group);
                  }}
                  aria-expanded={isExpanded}
                  aria-controls={`group-${group.id}-panel`}
                  aria-current={isSelected ? "true" : undefined}
                >
                  <span
                    className={`w-4 h-4 flex-shrink-0 transition-transform text-gray-400 ${
                      isExpanded ? "rotate-90" : ""
                    }`}
                    aria-hidden="true"
                  >
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </span>
                  <span
                    className={`w-5 h-5 flex-shrink-0 ${isSelected ? "text-indigo-600" : "text-gray-400 group-hover:text-gray-500"}`}
                  >
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                      />
                    </svg>
                  </span>
                  <div className="flex-1 overflow-hidden">
                    <h3 className={`text-sm font-semibold truncate ${isSelected ? "text-gray-900 dark:text-white" : "text-gray-800 dark:text-gray-200"}`}>
                      {group.name}
                    </h3>
                    {/* <p className="text-xs text-gray-500 dark:text-gray-400">
                      {group.fileCount || 0} files · {group.batchCount || 0} folders
                    </p> */}
                  </div>
                </button>
                      <div className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-0 transition-opacity group-hover/project:opacity-100">
                        <button
                          type="button"
                          onClick={() => startGroupEdit(group)}
                          className="pointer-events-auto rounded-md bg-indigo-50 p-1 text-indigo-600 shadow-sm hover:bg-indigo-100 hover:text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300 dark:hover:bg-indigo-900/60"
                          title="Edit project"
                        >
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L7.5 21H3v-4.5L16.732 3.732z"
                            />
                          </svg>
                        </button>
                        <button
                          type="button"
                          onClick={() => requestGroupDelete(group)}
                          className="pointer-events-auto rounded-md bg-rose-50 p-1 text-rose-500 shadow-sm hover:bg-rose-100 hover:text-rose-700 dark:bg-rose-950/40 dark:text-rose-200 dark:hover:bg-rose-950/60"
                          title="Delete project"
                        >
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M6 18L18 6M6 6l12 12"
                            />
                          </svg>
                        </button>
                      </div>
                    </>
                  )}
                </div>

                {isExpanded && (
                  <div
                    id={`group-${group.id}-panel`}
                    className="pl-6 pt-1 pb-2 space-y-3"
                  >
                    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/30 p-3">
                      <button
                        type="button"
                        className={`flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm font-semibold transition ${batchToggleDisabled
                            ? "cursor-not-allowed text-gray-400"
                            : batchesExpanded
                              ? "bg-indigo-50 text-indigo-700"
                              : "text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800/50"
                          }`}
                        onClick={() => {
                          if (batchToggleDisabled) {
                            return;
                          }
                          toggleSection(group.id, "batches", group.name, "Folders");
                        }}
                        aria-expanded={batchToggleDisabled ? undefined : batchesExpanded}
                        aria-controls={batchToggleDisabled ? undefined : `group-${group.id}-batches`}
                        aria-disabled={batchToggleDisabled || undefined}
                        disabled={batchToggleDisabled}
                        aria-label={batchAriaLabel}
                      >
                        <span className="flex items-center gap-2">
                          <span className="rounded-md bg-indigo-100 text-indigo-700 p-1" aria-hidden="true">
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                              />
                            </svg>
                          </span>
                          <span>Folders</span>
                        </span>
                        {!batchToggleDisabled && (
                          <span className="flex items-center gap-2 text-xs font-semibold text-gray-500">
                            {batchCount}
                            <svg
                              className={`h-3.5 w-3.5 transition-transform ${batchesExpanded ? "rotate-180" : ""}`}
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
                          </span>
                        )}
                      </button>
                      {batchesExpanded && (
                        <ul id={`group-${group.id}-batches`} className="mt-2 space-y-1" role="group">
                          {batches.map((batch) => {
                            const normalizedBatchId = normalizeId(batch.batchId);
                            const isBatchSelected =
                              selectedNode?.type === "batch" &&
                              normalizeId(selectedNode?.id) === normalizedBatchId;
                            const isEditingBatch =
                              editingBatchId && normalizeId(editingBatchId) === normalizedBatchId;
                            const isDeletingBatch =
                              deletingBatchInfo.id &&
                              normalizeId(deletingBatchInfo.id) === normalizedBatchId;

                            return (
                              <li key={batch.batchId} className="relative group/folder">
                                {isEditingBatch ? (
                                  <form
                                    onSubmit={saveBatchEdit}
                                    className="flex items-center gap-2 rounded-md bg-blue-50 p-2 dark:bg-blue-900/40"
                                  >
                                    <input
                                      type="text"
                                      value={editingBatchName}
                                      onChange={(event) => setEditingBatchName(event.target.value)}
                                      className="flex-1 rounded-md border border-blue-200 bg-white px-2 py-1 text-sm text-gray-800 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-blue-500/40 dark:bg-gray-950 dark:text-gray-100"
                                      autoFocus
                                      aria-label="Edit folder name"
                                    />
                                    <button
                                      type="submit"
                                      className="rounded-md bg-blue-600 p-1.5 text-white shadow-sm shadow-blue-200 hover:bg-blue-700"
                                      title="Save folder name"
                                    >
                                      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                      </svg>
                                    </button>
                                    <button
                                      type="button"
                                      onClick={cancelBatchEdit}
                                      className="rounded-md bg-gray-200 p-1.5 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-100"
                                      title="Cancel edit"
                                    >
                                      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                      </svg>
                                    </button>
                                  </form>
                                ) : isDeletingBatch ? (
                                  <div className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-950/40 dark:text-rose-100">
                                    <p className="mb-1">
                                      {batchDeleteInProgress ? "Deleting folder..." : "Delete this folder?"}
                                    </p>
                                    <div className="flex gap-2">
                                      <button
                                        type="button"
                                        onClick={confirmBatchDelete}
                                        disabled={batchDeleteInProgress}
                                        className="flex-1 rounded-md bg-rose-600 px-2 py-1 text-white shadow-sm shadow-rose-200 hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                                      >
                                        {batchDeleteInProgress ? "Deleting..." : "Delete"}
                                      </button>
                                      <button
                                        type="button"
                                        onClick={cancelBatchDelete}
                                        disabled={batchDeleteInProgress}
                                        className="flex-1 rounded-md bg-gray-200 px-2 py-1 text-gray-700 hover:bg-gray-300 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-gray-700 dark:text-gray-200"
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <>
                                    <button
                                      type="button"
                                      className={`w-full text-left p-2 rounded-md transition flex items-center gap-3 ${isBatchSelected
                                          ? "bg-indigo-600 text-white"
                                          : "hover:bg-gray-100 dark:hover:bg-gray-800/60 text-gray-700 dark:text-gray-200"
                                        }`}
                                      onClick={() => handleFolderButtonClick(group, batch)}
                                      aria-current={isBatchSelected ? "true" : undefined}
                                    >
                                  <span
                                    className={`flex-shrink-0 rounded-md p-1 ${isBatchSelected ? "bg-white/20" : "bg-gray-200 dark:bg-gray-700"}`}
                                  >
                                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth={2}
                                        d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                                      />
                                    </svg>
                                  </span>
                                  <span className="flex-1 min-w-0">
                                    <span className="block truncate text-sm font-medium">
                                      {batch.name || `Batch ${batch.batchId}`}
                                    </span>
                                    <span className="text-xs text-gray-500 dark:text-gray-400">
                                      {batch.fileCount} files
                                    </span>
                                  </span>
                                </button>
                                    <div className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 flex gap-1 opacity-0 transition-opacity group-hover/folder:opacity-100">
                                      <button
                                        type="button"
                                        onClick={() => startBatchEdit(batch, group.id)}
                                        className="pointer-events-auto rounded-md bg-blue-50 p-1 text-blue-600 shadow-sm hover:bg-blue-100 hover:text-blue-800 dark:bg-blue-900/40 dark:text-blue-200 dark:hover:bg-blue-900/60"
                                        title="Edit folder"
                                      >
                                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                          <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L7.5 21H3v-4.5L16.732 3.732z"
                                          />
                                        </svg>
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => requestBatchDelete(batch, group.id)}
                                        className="pointer-events-auto rounded-md bg-rose-50 p-1 text-rose-500 shadow-sm hover:bg-rose-100 hover:text-rose-700 dark:bg-rose-950/40 dark:text-rose-200 dark:hover:bg-rose-950/60"
                                        title="Delete folder"
                                      >
                                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                          <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M6 18L18 6M6 6l12 12"
                                          />
                                        </svg>
                                      </button>
                                    </div>
                                  </>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      )}
                      {batchToggleDisabled && (
                        <p className="mt-2 text-xs text-gray-500" role="status" aria-live="polite">
                          No folders available
                        </p>
                      )}
                    </div>

                    <form
                      onSubmit={(event) => handleCreateFolder(event, group)}
                      className="rounded-2xl border border-dashed border-gray-200 bg-white/70 px-3 py-3 text-sm flex items-center gap-2 shadow-sm dark:border-gray-700 dark:bg-gray-900/40"
                    >
                      <input
                        type="text"
                        value={newFolderNames[normalizedGroupId] || ""}
                        onChange={(event) => handleFolderNameChange(group.id, event.target.value)}
                        placeholder="New folder name..."
                        className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-950 dark:text-gray-100"
                        aria-label={`New folder for ${group.name}`}
                      />
                      <button
                        type="submit"
                        disabled={!(newFolderNames[normalizedGroupId] || "").trim()}
                        className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm shadow-indigo-200 transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-indigo-500 dark:hover:bg-indigo-400"
                      >
                        + Add
                      </button>
                    </form>

                    {false && (
                      <>
                        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/30 p-3">
                          <button
                            type="button"
                            className={`flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm font-semibold transition ${fileToggleDisabled
                                ? "cursor-not-allowed text-gray-400"
                                : filesExpanded
                                  ? "bg-indigo-50 text-indigo-700"
                                  : "text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800/50"
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
                          >
                            <span className="flex items-center gap-2">
                              <span className="rounded-md bg-indigo-100 text-indigo-700 p-1" aria-hidden="true">
                                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                                  />
                                </svg>
                              </span>
                              <span>Files</span>
                            </span>
                            {!fileToggleDisabled && (
                              <span className="flex items-center gap-2 text-xs font-semibold text-gray-500">
                                {fileCount}
                                <svg
                                  className={`h-3.5 w-3.5 transition-transform ${filesExpanded ? "rotate-180" : ""}`}
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
                              </span>
                            )}
                          </button>
                          {filesExpanded && (
                            <ul id={`group-${group.id}-files`} className="mt-2 space-y-1" role="group">
                              {files.map((file) => {
                                const isFileSelected =
                                  selectedNode?.type === "file" &&
                                  normalizeId(selectedNode?.id) === normalizeId(file.id);
                                const normalizedStatus =
                                  typeof file.status === "string" ? file.status.toLowerCase() : "";
                                const statusClasses =
                                  FILE_STATUS_STYLES[normalizedStatus] || FILE_STATUS_STYLES.default;
                                const statusLabel =
                                  normalizedStatus === "uploaded" ? "Uploaded" : file.status;

                                return (
                                  <li key={file.id}>
                                    <button
                                      type="button"
                                      className={`w-full text-left p-2 rounded-md transition flex items-center gap-3 ${isFileSelected
                                          ? "bg-indigo-600 text-white"
                                          : "hover:bg-gray-100 dark:hover:bg-gray-800/60 text-gray-700 dark:text-gray-200"
                                        }`}
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
                                        className={`flex-shrink-0 rounded-md p-1 ${isFileSelected ? "bg-white/20" : "bg-gray-200 dark:bg-gray-700"}`}
                                      >
                                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                          <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                                          />
                                        </svg>
                                      </span>
                                      <span className="flex-1 min-w-0">
                                        <span className="block truncate text-sm font-medium">
                                          {file.filename}
                                        </span>
                                        {file.status && (
                                          <span
                                            className={`mt-0.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${statusClasses}`}
                                          >
                                            <span className="h-1.5 w-1.5 rounded-full bg-current" />
                                            {statusLabel}
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
                            <p className="mt-2 text-xs text-gray-500" role="status" aria-live="polite">
                              No files available
                            </p>
                          )}
                        </div>

                        {files.length === 0 && batches.length === 0 && (
                          <div className="rounded-md border border-dashed border-gray-300 px-3 py-2 text-xs text-gray-500">
                            No files or folders
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      <div role="status" aria-live="polite" className="sr-only">
        {statusMessage}
      </div>
    </aside>
  );
}
