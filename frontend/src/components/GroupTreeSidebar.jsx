import { useState, useEffect, useRef, useMemo, useCallback, forwardRef, useImperativeHandle } from "react";
import axios from "axios";
import API_BASE_URL, { API_ENDPOINTS } from "../config/api";
import { resolveEntityStatus } from "../utils/statuses";
import { useNotification } from "../contexts/NotificationContext";
const normalizeId = (id) => (id === null || id === undefined ? "" : String(id));
const buildTreeItemId = (type, identifier) => `${type}-${normalizeId(identifier)}`;
const FILE_STATUS_STYLES = {
  uploaded: "bg-gray-100 text-gray-700",
  scanned: "bg-blue-100 text-blue-800",
  partially_fixed: "bg-amber-100 text-amber-800",
  fixed: "bg-emerald-100 text-emerald-800",
  error: "bg-rose-100 text-rose-800",
  default: "bg-slate-100 text-slate-600",
};
const STATUS_BADGE_STYLES = {
  uploaded:
    "border-slate-100 bg-slate-50 text-slate-900 dark:border-slate-700/60 dark:bg-slate-900/40 dark:text-slate-100",
  scanned:
    "border-indigo-100 bg-indigo-50 text-indigo-900 dark:border-indigo-700/60 dark:bg-indigo-900/20 dark:text-indigo-100",
  partially_fixed:
    "border-purple-100 bg-purple-50 text-purple-900 dark:border-purple-700/60 dark:bg-purple-900/20 dark:text-purple-100",
  fixed:
    "border-emerald-100 bg-emerald-50 text-emerald-900 dark:border-emerald-700/60 dark:bg-emerald-900/20 dark:text-emerald-100",
  error:
    "border-rose-100 bg-rose-50 text-rose-900 dark:border-rose-700/60 dark:bg-rose-900/20 dark:text-rose-100",
};
const SELECTED_STATUS_BADGE_CLASSES =
  "border-white/90 bg-white text-slate-800 dark:border-slate-200/80 dark:bg-slate-800 dark:text-white";
const TREE_ITEM_FOCUS_CLASSES =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-950";
const FOCUSABLE_ELEMENTS_SELECTOR = "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

const ENTITY_NAME_MIN_LENGTH = 2;
const ENTITY_NAME_MAX_LENGTH = 50;
const ENTITY_NAME_PATTERN = /^[A-Za-z0-9 ()_.-]+$/;
const sanitizeInputValue = (value) => {
  return (value ?? "").replace(/[^A-Za-z0-9 ()_.-]+/g, "");
};

const validateEntityName = (value, options = {}) => {
  const { label = "Name", minLength = ENTITY_NAME_MIN_LENGTH, maxLength = ENTITY_NAME_MAX_LENGTH } = options;
  const trimmed = (value ?? "").trim();
  if (!trimmed) {
    return {
      isValid: false,
      trimmed: "",
      message: `${label} is required.`,
    };
  }
  if (trimmed.length < minLength) {
    return {
      isValid: false,
      trimmed,
      message: `${label} must be at least ${minLength} characters.`,
    };
  }
  if (trimmed.length > maxLength) {
    return {
      isValid: false,
      trimmed,
      message: `${label} must be ${maxLength} characters or fewer.`,
    };
  }
  if (!ENTITY_NAME_PATTERN.test(trimmed)) {
    return {
      isValid: false,
      trimmed,
      message: `${label} may only include letters, numbers, spaces, parentheses, periods, underscores, and hyphens.`,
    };
  }
  return {
    isValid: true,
    trimmed,
    message: "",
  };
};

  const GroupTreeSidebar = forwardRef(function GroupTreeSidebar(
    {
      onNodeSelect,
      selectedNode,
      onRefresh,
      onDashboardRefresh,
      onStaleNode,
      initialGroupId,
      latestUploadContext = null,
      onUploadContextAcknowledged = () => {},
      folderNavigationContext = null,
      folderStatusUpdateSignal = null,
    },
    ref,
  ) {
  const [groups, setGroups] = useState([]);
  const [expandedGroups, setExpandedGroups] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [groupFiles, setGroupFiles] = useState({});
  const [groupBatches, setGroupBatches] = useState({});
  const [error, setError] = useState(null);
  const [sectionStates, setSectionStates] = useState({});
  const [statusMessage, setStatusMessage] = useState("");
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectError, setNewProjectError] = useState("");
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [newFolderNames, setNewFolderNames] = useState({});
  const [folderErrors, setFolderErrors] = useState({});
  const [editingGroupId, setEditingGroupId] = useState(null);
  const [editingGroupName, setEditingGroupName] = useState("");
  const [deletingGroupId, setDeletingGroupId] = useState(null);
  const [pendingDeleteGroup, setPendingDeleteGroup] = useState(null);
  const [isProjectDeleteLoading, setIsProjectDeleteLoading] = useState(false);
  const [projectDeleteError, setProjectDeleteError] = useState("");
  const [editingBatchId, setEditingBatchId] = useState(null);
  const [editingBatchGroupId, setEditingBatchGroupId] = useState(null);
  const [editingBatchName, setEditingBatchName] = useState("");
  const [deletingBatchId, setDeletingBatchId] = useState(null);
  const [pendingDeleteFolder, setPendingDeleteFolder] = useState(null);
  const [isFolderDeleteLoading, setIsFolderDeleteLoading] = useState(false);
  const [folderDeleteError, setFolderDeleteError] = useState("");
  const [sidebarView, setSidebarView] = useState("projects");
  const [activeFolderView, setActiveFolderView] = useState(null);
  const [folderFiles, setFolderFiles] = useState([]);
  const [folderFilesLoading, setFolderFilesLoading] = useState(false);
  const [folderFilesError, setFolderFilesError] = useState(null);
  const [refreshingGroupId, setRefreshingGroupId] = useState(null);
  const [deletingFileIds, setDeletingFileIds] = useState(() => new Set());
  const [refreshingFolderCounts, setRefreshingFolderCounts] = useState({});
  const editingTreeItemIdRef = useRef(null);
  const focusEditedTreeItem = useCallback(() => {
    const treeId = editingTreeItemIdRef.current;
    if (!treeId) {
      return;
    }
    requestAnimationFrame(() => {
      if (!treeId) {
        return;
      }
      const element = document.querySelector(`[data-tree-id="${treeId}"]`);
      if (element instanceof HTMLElement) {
        focusTreeItem(element);
      }
    });
    editingTreeItemIdRef.current = null;
  }, []);
  const handledFolderNavigationRef = useRef(null);
  const folderStatusRefreshKeyRef = useRef(null);
  const treeContainerRef = useRef(null);
  const treeItemMetadataRef = useRef({});
  const sidebarRootRef = useRef(null);
  const folderBackButtonRef = useRef(null);
  const projectDeleteModalRef = useRef(null);
  const folderDeleteModalRef = useRef(null);
  const [activeTreeItemId, setActiveTreeItemId] = useState(null);
  const { confirm, showError, showSuccess, showDialog } = useNotification();
  const projectNameValidation = validateEntityName(newProjectName, { label: "Project name" });
  const projectCharCount = newProjectName.length;
  const projectCharCountClass = projectNameValidation.isValid
    ? "text-slate-500 dark:text-slate-400"
    : "text-rose-600 dark:text-rose-400";
  const updateDeletingFileState = (fileId, isDeleting) => {
    const normalizedFileId = normalizeId(fileId);
    if (!normalizedFileId) {
      return;
    }

    setDeletingFileIds((prev) => {
      const hasFile = prev.has(normalizedFileId);
      if (isDeleting) {
        if (hasFile) {
          return prev;
        }
        const next = new Set(prev);
        next.add(normalizedFileId);
        return next;
      }

      if (!hasFile) {
        return prev;
      }
      const next = new Set(prev);
      next.delete(normalizedFileId);
      return next;
    });
  };

  const isDeletingFile = (fileId) => {
    const normalizedFileId = normalizeId(fileId);
    return !!normalizedFileId && deletingFileIds.has(normalizedFileId);
  };
  const treeItemsMetadata = useMemo(() => {
    const metadata = {};
    groups.forEach((group, groupIndex) => {
      const normalizedGroupId = normalizeId(group.id);
      if (!normalizedGroupId) {
        return;
      }
      const treeId = buildTreeItemId("group", group.id);
      const groupEntry = {
        type: "group",
        group,
        normalizedGroupId,
        treeId,
        groupIndex,
        childTreeIds: [],
      };
      metadata[treeId] = groupEntry;
      const batches = groupBatches[normalizedGroupId] || [];
      batches.forEach((batch, batchIndex) => {
        const batchIdentifier = batch.batchId ?? batch.id;
        const normalizedBatchId = normalizeId(batchIdentifier);
        if (!normalizedBatchId) {
          return;
        }
        const folderTreeId = buildTreeItemId("folder", batchIdentifier);
        groupEntry.childTreeIds.push(folderTreeId);
        metadata[folderTreeId] = {
          type: "folder",
          batch: {
            ...batch,
            batchId: batchIdentifier,
          },
          group,
          normalizedBatchId,
          treeId: folderTreeId,
          parentTreeId: treeId,
          batchIndex,
          groupIndex,
        };
      });
    });
    return metadata;
  }, [groups, groupBatches]);
  treeItemMetadataRef.current = treeItemsMetadata;
  const handleEscapeBlur = useCallback((event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.currentTarget.blur();
    }
  }, []);
  useEffect(() => {
    if (sidebarView !== "folder" || selectedNode?.type !== "batch") {
      return;
    }
    const schedule =
      typeof window !== "undefined" && typeof window.requestAnimationFrame === "function"
        ? window.requestAnimationFrame
        : (cb) => setTimeout(cb, 0);
    const cancel =
      typeof window !== "undefined" && typeof window.cancelAnimationFrame === "function"
        ? window.cancelAnimationFrame
        : (id) => clearTimeout(id);
    let frameId = null;
    const focusTarget = () => {
      if (folderBackButtonRef.current && typeof folderBackButtonRef.current.focus === "function") {
        folderBackButtonRef.current.focus();
        return;
      }
      const sidebarElement = sidebarRootRef.current;
      if (sidebarElement && typeof sidebarElement.focus === "function") {
        sidebarElement.focus();
      }
    };
    frameId = schedule(focusTarget);
    return () => {
      if (frameId) {
        cancel(frameId);
      }
    };
  }, [sidebarView, selectedNode?.id, selectedNode?.type]);
  const mapFolderToSidebarEntry = (folder) => {
    if (!folder) {
      return null;
    }
    const fileCount = folder.totalFiles ?? folder.total_files ?? folder.fileCount ?? 0;
    return {
      batchId: folder.folderId || folder.batchId || folder.id,
      folderId: folder.folderId || folder.batchId || folder.id,
      name: folder.name || folder.folderName || `Folder ${folder.folderId || folder.id}`,
      groupId: folder.groupId || folder.group_id,
      status: folder.status,
      createdAt: folder.createdAt || folder.created_at,
      fileCount,
      totalFiles: fileCount,
      totalIssues: folder.totalIssues ?? folder.total_issues ?? 0,
      fixedIssues: folder.fixedIssues ?? folder.fixed_issues ?? 0,
      remainingIssues: folder.remainingIssues ?? folder.remaining_issues ?? 0,
      unprocessedFiles: folder.unprocessedFiles ?? folder.unprocessed_files ?? 0,
    };
  };

  const syncFolderCountWithSidebar = (groupId, folderId, fileCount) => {
    const normalizedGroupId = normalizeId(groupId);
    const normalizedFolderId = normalizeId(folderId);
    if (!normalizedGroupId || !normalizedFolderId) {
      return;
    }

    setGroupBatches((prev) => {
      const targetList = prev[normalizedGroupId];
      if (!Array.isArray(targetList) || targetList.length === 0) {
        return prev;
      }

      let changed = false;
      const updatedList = targetList.map((batch) => {
        if (normalizeId(batch.batchId) !== normalizedFolderId) {
          return batch;
        }
        const currentCount = batch.fileCount ?? batch.totalFiles ?? batch.total_files;
        if (currentCount === fileCount) {
          return batch;
        }
        changed = true;
        return {
          ...batch,
          fileCount,
          totalFiles: fileCount,
          total_files: fileCount,
        };
      });

      return changed
        ? {
            ...prev,
            [normalizedGroupId]: updatedList,
          }
        : prev;
    });
  };

  const setFolderCountRefreshingState = (folderId, refreshing) => {
    const normalizedId = normalizeId(folderId);
    if (!normalizedId) {
      return;
    }
    setRefreshingFolderCounts((prev) => {
      if (refreshing) {
        if (prev[normalizedId]) {
          return prev;
        }
        return {
          ...prev,
          [normalizedId]: true,
        };
      }
      if (!prev[normalizedId]) {
        return prev;
      }
      const next = { ...prev };
      delete next[normalizedId];
      return next;
    });
  };

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

  const getFocusableTreeItems = () => {
    const container = treeContainerRef.current;
    if (!container) {
      return [];
    }
    return Array.from(container.querySelectorAll("[data-doca-tree-item]"));
  };

  const focusTreeItem = (item) => {
    if (!item) {
      return;
    }
    item.focus();
    item.scrollIntoView({ block: "nearest" });
  };

  const handleTreeFocusCapture = (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }

    const treeItem = target.closest("[data-doca-tree-item]");
    if (treeItem?.dataset?.treeId) {
      setActiveTreeItemId(treeItem.dataset.treeId);
      return;
    }

    const actionsRegion = target.closest("[data-tree-actions-for]");
    if (actionsRegion?.dataset?.treeActionsFor) {
      setActiveTreeItemId(actionsRegion.dataset.treeActionsFor);
    }
  };

  const handleTreeBlurCapture = (event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      setActiveTreeItemId(null);
    }
  };

  const handleTreeKeyDown = (event) => {
    if (
      event.defaultPrevented ||
      event.altKey ||
      event.ctrlKey ||
      event.metaKey
    ) {
      return;
    }

    const activeElement =
      typeof document !== "undefined" ? document.activeElement : null;
    const editingInputType =
      activeElement instanceof HTMLElement ? activeElement.dataset?.editingType : null;
    const editingInProgress = Boolean(editingGroupId || editingBatchId);
    if (editingInProgress || editingInputType) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (editingInputType === "group" || editingGroupId) {
          cancelGroupEdit();
        } else if (editingInputType === "folder" || editingBatchId) {
          cancelBatchEdit();
        }
      }
      return;
    }

    const navigationKeys = ["ArrowDown", "ArrowUp", "Home", "End", "ArrowLeft", "ArrowRight"];
    if (!navigationKeys.includes(event.key)) {
      return;
    }

    const items = getFocusableTreeItems();
    if (items.length === 0) {
      return;
    }

    event.preventDefault();
    const currentIndex = items.indexOf(activeElement);
    let targetIndex = 0;
    const treeItemElement =
      activeElement instanceof Element
        ? activeElement.closest("[data-doca-tree-item]")
        : null;
    const treeItemId = treeItemElement?.dataset?.treeId || null;
    const treeMetadata =
      treeItemId && treeItemMetadataRef.current
        ? treeItemMetadataRef.current[treeItemId]
        : null;

    switch (event.key) {
      case "ArrowDown":
        targetIndex =
          currentIndex === -1
            ? 0
            : Math.min(items.length - 1, currentIndex + 1);
        break;
      case "ArrowUp":
        targetIndex =
          currentIndex === -1
            ? items.length - 1
            : Math.max(0, currentIndex - 1);
        break;
      case "Home":
        targetIndex = 0;
        break;
      case "End":
        targetIndex = items.length - 1;
        break;
      case "ArrowRight":
        if (!treeMetadata) {
          return;
        }
        if (treeMetadata.type === "group") {
          if (!expandedGroups.has(treeMetadata.normalizedGroupId)) {
            void handleGroupSelection(treeMetadata.group);
            return;
          }
          const firstChildId = treeMetadata.childTreeIds?.[0];
          if (firstChildId) {
            const childElement = items.find(
              (item) => item.dataset.treeId === firstChildId
            );
            if (childElement) {
              focusTreeItem(childElement);
            }
          }
        } else if (treeMetadata.type === "folder") {
          void handleFolderButtonClick(treeMetadata.group, treeMetadata.batch);
        }
        return;
      case "ArrowLeft":
        if (!treeMetadata) {
          return;
        }
        if (treeMetadata.type === "group") {
          if (expandedGroups.has(treeMetadata.normalizedGroupId)) {
            setExpandedGroups((prev) => {
              if (!prev.has(treeMetadata.normalizedGroupId)) {
                return prev;
              }
              const next = new Set(prev);
              next.delete(treeMetadata.normalizedGroupId);
              return next;
            });
          }
          return;
        }
        if (treeMetadata.type === "folder") {
          const parentId = treeMetadata.parentTreeId;
          if (parentId) {
            const parentElement = items.find(
              (item) => item.dataset.treeId === parentId
            );
            if (parentElement) {
              focusTreeItem(parentElement);
            }
          }
        }
        return;
      default:
        return;
    }

    const targetItem = items[targetIndex];
    if (targetItem) {
      focusTreeItem(targetItem);
    }
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

  const fetchFoldersForGroup = async (groupId = null) => {
    const params = groupId ? { groupId } : undefined;
    try {
      const response = await axios.get(`${API_BASE_URL}/api/folders`, {
        params,
      });
      const folders = response.data?.folders || [];
      return folders
        .map((folder) => mapFolderToSidebarEntry(folder))
        .filter((entry) => entry && normalizeId(entry.groupId));
    } catch (error) {
      console.error("[v0] Error fetching folders:", error);
      return [];
    }
  };

  const fetchGroups = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await axios.get(API_ENDPOINTS.projects);
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
        const allFolders = await fetchFoldersForGroup();
        batchesByGroup = allFolders.reduce((acc, folder) => {
          const groupKey = normalizeId(folder.groupId);
          if (!groupKey) {
            return acc;
          }
          if (!acc[groupKey]) {
            acc[groupKey] = [];
          }
          acc[groupKey].push(folder);
          return acc;
        }, batchesByGroup);
      } catch (folderError) {
        console.error("[v0] Error loading folders for groups:", folderError);
      }

      setGroupBatches(batchesByGroup);

      const groupsWithCounts = normalizedGroups.map((group) => {
        const key = normalizeId(group.id);
        return {
          ...group,
          batchCount: batchesByGroup[key]?.length || group.batchCount || 0,
          folderCount: batchesByGroup[key]?.length || group.folderCount || 0,
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

  useEffect(() => {
    if (initialGroupId) {
      return;
    }
    if (groups.length === 0 || selectedNode) {
      return;
    }
    const firstGroup = groups[0];
    if (!firstGroup || !normalizeId(firstGroup.id)) {
      return;
    }
    void handleGroupSelection(firstGroup, { forceExpand: true });
  }, [groups, initialGroupId, selectedNode]);

  const fetchGroupData = async (groupId, prefetchedBatches = null, options = {}) => {
    const { forceBatchRefresh = false } = options;
    const normalizedId = normalizeId(groupId);

    try {
      const filesResponse = await axios.get(API_ENDPOINTS.projectFiles(groupId));
      const files = filesResponse.data.files || [];

      setGroupFiles((prev) => ({
        ...prev,
        [normalizedId]: files,
      }));

      let batchesForGroup = !forceBatchRefresh && Array.isArray(prefetchedBatches)
        ? prefetchedBatches
        : null;

      if (!batchesForGroup) {
        const fetchedFolders = await fetchFoldersForGroup(groupId);
        batchesForGroup = fetchedFolders.filter(
          (folder) => normalizeId(folder.groupId) === normalizedId
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

  const handleGroupSelection = async (
    group,
    { moveFocus = false, forceExpand = false } = {}
  ) => {
    if (!group) {
      return;
    }

    ensureProjectView();

    const normalizedId = normalizeId(group.id);
    const isAlreadyExpanded = expandedGroups.has(normalizedId);
    const shouldExpand = forceExpand || !isAlreadyExpanded;

    setExpandedGroups((prev) => {
      if (shouldExpand) {
        return new Set([normalizedId]);
      }
      if (!prev.has(normalizedId)) {
        return prev;
      }
      const next = new Set(prev);
      next.delete(normalizedId);
      return next;
    });

    setSectionStates((prev) => {
      const next = { ...prev };
      if (!next[normalizedId]) {
        next[normalizedId] = {
          batches: false,
          files: false,
        };
      }
      if (shouldExpand) {
        Object.keys(next).forEach((key) => {
          if (key !== normalizedId) {
            next[key] = {
              batches: false,
              files: false,
            };
          }
        });
        return next;
      }
      next[normalizedId] = {
        batches: false,
        files: false,
      };
      return next;
    });

    const fetchPromise = shouldExpand
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
      setStatusMessage(`${group.name} ${shouldExpand ? "expanded" : "collapsed"}`);
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

  const getSelectedNodeGroupId = () => {
    if (!selectedNode) {
      return "";
    }
    if (selectedNode.type === "group") {
      return normalizeId(selectedNode.id);
    }
    return normalizeId(
      selectedNode.data?.groupId ??
        selectedNode.data?.group_id ??
        ""
    );
  };

  const getSelectedNodeBatchId = () => {
    if (!selectedNode) {
      return "";
    }
    if (selectedNode.type === "batch") {
      return normalizeId(selectedNode.id);
    }
    if (selectedNode.type === "file") {
      return normalizeId(
        selectedNode.data?.batchId ??
          selectedNode.data?.batch_id ??
          selectedNode.data?.folderId ??
          selectedNode.data?.folder_id ??
          ""
      );
    }
    return "";
  };

  const refreshDashboardGroupView = (groupId) => {
    if (!onNodeSelect) {
      return;
    }
    const normalizedGroupId = normalizeId(groupId);
    if (!normalizedGroupId) {
      return;
    }
    const targetGroup = groups.find((group) => normalizeId(group.id) === normalizedGroupId);
    if (!targetGroup) {
      return;
    }
    void handleNodeClick({
      type: "group",
      id: targetGroup.id,
      data: targetGroup,
    });
  };

  const ensureDashboardReflectsGroupDeletion = (groupId) => {
    if (!onNodeSelect || !groupId) {
      return;
    }
    const normalizedGroupId = normalizeId(groupId);
    if (!normalizedGroupId) {
      return;
    }
    const belongsToGroup = getSelectedNodeGroupId() === normalizedGroupId;
    if (belongsToGroup) {
      void onNodeSelect(null);
    }
  };

  const ensureDashboardReflectsFolderDeletion = (groupId, folderId) => {
    if (!onNodeSelect || !groupId || !folderId) {
      return;
    }
    const normalizedGroupId = normalizeId(groupId);
    const normalizedFolderId = normalizeId(folderId);
    if (!normalizedGroupId || !normalizedFolderId) {
      return;
    }
    const targetGroup = groups.find((group) => normalizeId(group.id) === normalizedGroupId);
    const selectedBatchId = getSelectedNodeBatchId();
    const isBatchSelected =
      selectedNode?.type === "batch" && selectedBatchId === normalizedFolderId;
    const isFileSelected =
      selectedNode?.type === "file" && selectedBatchId === normalizedFolderId;
    const isGroupSelected =
      selectedNode?.type === "group" && normalizeId(selectedNode.id) === normalizedGroupId;
    const refreshOrClear = () => {
      if (targetGroup) {
        void refreshDashboardGroupView(normalizedGroupId);
        return;
      }
      void onNodeSelect(null);
    };
    if (isBatchSelected || isFileSelected) {
      refreshOrClear();
      return;
    }
    if (isGroupSelected) {
      refreshOrClear();
    }
  };

  const triggerDashboardRefresh = useCallback(() => {
    if (onDashboardRefresh) {
      onDashboardRefresh();
      return;
    }
    if (onRefresh) {
      onRefresh();
    }
  }, [onDashboardRefresh, onRefresh]);

  const reportStaleNode = useCallback(
    async (node, statusCode) => {
      if (!onStaleNode || ![404, 410].includes(statusCode)) {
        return false;
      }
      await onStaleNode(node, statusCode);
      return true;
    },
    [onStaleNode]
  );

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

  const handleCreateProject = async (event) => {
    event?.preventDefault();

    const validation = validateEntityName(newProjectName, { label: "Project name" });
    if (!validation.isValid) {
      const message = validation.message;
      showDialog({
        title: "Invalid project name",
        message,
        closeText: "Okay",
      });
      setNewProjectError(message);
      setStatusMessage(message);
      return;
    }
    const trimmedName = validation.trimmed;
    const normalizedName = trimmedName.toLowerCase();
    const duplicate = groups.some(
      (group) => (group.name || "").trim().toLowerCase() === normalizedName
    );
    if (duplicate) {
      const message = `Project "${trimmedName}" already exists`;
      showDialog({
        title: "Duplicate project name",
        message,
        closeText: "Got it",
      });
      setNewProjectError(message);
      setStatusMessage(message);
      return;
    }

    setNewProjectError("");
    setIsCreatingProject(true);
    try {
      const response = await axios.post(API_ENDPOINTS.projects, {
        name: trimmedName,
      });

      const successMessage = response?.data?.group
        ? `Project "${trimmedName}" created`
        : "Project created";
      setStatusMessage(successMessage);
      setNewProjectName("");
      await fetchGroups();
      triggerDashboardRefresh();
    } catch (error) {
      const errMessage =
        error?.response?.data?.error ||
        error?.message ||
        "Failed to create project";
      setStatusMessage(errMessage);
      setNewProjectError(errMessage);
    } finally {
      setIsCreatingProject(false);
    }
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

  const refreshSidebarView = async () => {
    await fetchGroups();
  };

  useImperativeHandle(
    ref,
    () => ({
      closeFolderView,
      refresh: refreshSidebarView,
    }),
    [closeFolderView, refreshSidebarView]
  );

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
      const accurateCount =
        folderDetails.total_files ??
        folderDetails.totalFiles ??
        scans.length;
      syncFolderCountWithSidebar(group.id, folderMeta.folderId, accurateCount);
    } catch (folderError) {
      console.error("[GroupTreeSidebar] Failed to load folder files:", folderError);
      const statusCode = folderError?.response?.status;
      const staleNode = {
        type: "batch",
        id: folderMeta.folderId,
        data: {
          batchId: folderMeta.folderId,
          folderId: folderMeta.folderId,
          groupId: folderMeta.groupId,
          groupName: folderMeta.groupName,
          folderName: folderMeta.folderName,
        },
      };
      if (await reportStaleNode(staleNode, statusCode)) {
        setFolderFilesError(null);
        return;
      }
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
    void handleNodeClick({
      type: "batch",
      id: batchId,
      data: batchData,
    });
  };

  const handleDeleteFile = async (file, event) => {
    event?.stopPropagation?.();
    const fileId = file.scanId || file.id || file.fileId;
    const normalizedFileId = normalizeId(fileId);
    const fileName = file.filename || file.fileName || "file";

    if (!fileId) {
      showError("Unable to determine which file to delete.");
      return;
    }

    const confirmed = await confirm({
      title: "Delete file",
      message: `Delete "${fileName}" and permanently remove it from this project? This cannot be undone.`,
      confirmText: "Delete",
      cancelText: "Cancel",
      type: "danger",
    });

    if (!confirmed) {
      return;
    }

    updateDeletingFileState(fileId, true);
    try {
      await axios.delete(`${API_BASE_URL}/api/scan/${fileId}`);
      showSuccess(`Deleted file "${fileName}"`);
      setStatusMessage(`${fileName} deleted`);

      const folderMeta = activeFolderView;
      const normalizedFolderId = normalizeId(folderMeta?.folderId);
      const normalizedGroupId = normalizeId(folderMeta?.groupId);

      const returnToFolderDashboardIfNeeded = async () => {
        const isFileDashboardActive =
          selectedNode?.type === "file" && normalizeId(selectedNode?.id) === normalizedFileId;
        if (!isFileDashboardActive) {
          return;
        }
        if (folderMeta && normalizedFolderId) {
          await handleNodeClick({
            type: "batch",
            id: folderMeta.folderId,
            data: {
              batchId: folderMeta.folderId,
              name: folderMeta.folderName || `Folder ${folderMeta.folderId}`,
              groupId: folderMeta.groupId,
              groupName: folderMeta.groupName,
            },
          });
          return;
        }
        await handleNodeClick(null);
      };

      if (folderMeta && normalizedFolderId) {
        const resolveFileIdentifier = (item) =>
          normalizeId(item?.scanId || item?.id || item?.fileId);

        setFolderFiles((prev) =>
          prev.filter((entry) => resolveFileIdentifier(entry) !== normalizedFileId)
        );

        setActiveFolderView((prev) => {
          if (!prev || normalizeId(prev.folderId) !== normalizedFolderId) {
            return prev;
          }
          const currentTotalRaw = prev.totalFiles;
          const currentTotal =
            typeof currentTotalRaw === "number"
              ? currentTotalRaw
              : parseInt(currentTotalRaw, 10);
          const nextTotal = Math.max(0, (Number.isFinite(currentTotal) ? currentTotal : 0) - 1);
          return {
            ...prev,
            totalFiles: nextTotal,
          };
        });

        if (normalizedGroupId) {
          setGroupBatches((prev) => {
            const existingList = prev[normalizedGroupId];
            if (!Array.isArray(existingList) || existingList.length === 0) {
              return prev;
            }
            let hasChanges = false;
            const updatedList = existingList.map((batch) => {
              if (normalizeId(batch.batchId) !== normalizedFolderId) {
                return batch;
              }
              hasChanges = true;
              const rawCount = batch.fileCount ?? batch.totalFiles ?? batch.total_files ?? 0;
              const numericCount =
                typeof rawCount === "number" ? rawCount : parseInt(rawCount, 10);
              const nextCount = Math.max(
                0,
                (Number.isFinite(numericCount) ? numericCount : 0) - 1
              );
              return {
                ...batch,
                fileCount: nextCount,
              };
            });
            return hasChanges
              ? {
                  ...prev,
                  [normalizedGroupId]: updatedList,
                }
              : prev;
          });
        }

        const targetGroup = normalizedGroupId
          ? groups.find((group) => normalizeId(group.id) === normalizedGroupId)
          : null;

        if (targetGroup) {
          setFolderCountRefreshingState(normalizedFolderId, true);
          void (async () => {
            try {
              await fetchGroupData(targetGroup.id, null, { forceBatchRefresh: true });
              await openFolderView(targetGroup, {
                batchId: folderMeta.folderId,
                id: folderMeta.folderId,
                name: folderMeta.folderName,
              });
            } catch (refreshError) {
              console.error(
                "[GroupTreeSidebar] Failed to refresh group data after file delete:",
                refreshError
              );
            } finally {
              setFolderCountRefreshingState(normalizedFolderId, false);
            }
          })();
        }
      }

      if (
        selectedNode?.type === "batch" &&
        normalizeId(selectedNode.id) === normalizeId(folderMeta?.folderId)
      ) {
        await handleNodeClick(selectedNode);
      }

      await returnToFolderDashboardIfNeeded();
    } catch (error) {
      console.error("[GroupTreeSidebar] Failed to delete file:", error);
      showError(error?.response?.data?.error || "Failed to delete file");
      await handleNodeClick(null);
    } finally {
      updateDeletingFileState(fileId, false);
    }
  };

  useEffect(() => {
    const uploadContext = latestUploadContext;
    if (!uploadContext?.folderId || !activeFolderView) {
      return;
    }
    const targetFolderId = normalizeId(uploadContext.folderId);
    const activeFolderId = normalizeId(activeFolderView.folderId);
    if (!targetFolderId || targetFolderId !== activeFolderId) {
      return;
    }
    const targetGroupId = normalizeId(uploadContext.groupId);
    if (!targetGroupId) {
      return;
    }
    const targetGroup = groups.find((group) => normalizeId(group.id) === targetGroupId);
    if (!targetGroup) {
      return;
    }
    const folderName = uploadContext.folderName;
    onUploadContextAcknowledged?.();

    const refreshFolderData = async () => {
      await fetchGroupData(targetGroup.id, groupBatches[targetGroupId] || null, {
        forceBatchRefresh: true,
      });
      await openFolderView(targetGroup, {
        batchId: uploadContext.folderId,
        id: uploadContext.folderId,
        name: folderName || activeFolderView.folderName,
      });
      await handleNodeClick({
        type: "batch",
        id: uploadContext.folderId,
        data: {
          batchId: uploadContext.folderId,
          name: folderName || activeFolderView.folderName,
          groupId: targetGroup.id,
          groupName: targetGroup.name,
        },
      });
    };

    void refreshFolderData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    latestUploadContext?.folderId,
    latestUploadContext?.groupId,
    latestUploadContext?.folderName,
    activeFolderView?.folderId,
    groups,
    groupBatches,
    onUploadContextAcknowledged,
  ]);

  useEffect(() => {
    const signal = folderStatusUpdateSignal;
    if (!signal?.key) {
      return;
    }
    const normalizedFolderId = normalizeId(signal.folderId);
    const normalizedGroupId = normalizeId(signal.groupId);
    if (!normalizedFolderId || !normalizedGroupId) {
      return;
    }
    if (folderStatusRefreshKeyRef.current === signal.key) {
      return;
    }
    folderStatusRefreshKeyRef.current = signal.key;

    const targetGroup = groups.find((group) => normalizeId(group.id) === normalizedGroupId);
    if (!targetGroup) {
      return;
    }

    const refreshFolderAfterSignal = async () => {
      try {
        await fetchGroupData(targetGroup.id, groupBatches[normalizedGroupId] || null, {
          forceBatchRefresh: true,
        });
        const isActiveFolder =
          normalizeId(activeFolderView?.folderId) === normalizedFolderId;
        if (isActiveFolder) {
          await openFolderView(targetGroup, {
            batchId: signal.folderId,
            id: signal.folderId,
            name: activeFolderView?.folderName || `Folder ${signal.folderId}`,
          });
        }
      } catch (refreshError) {
        console.error(
          "[GroupTreeSidebar] Failed to refresh folder after status update:",
          refreshError
        );
      }
    };

    void refreshFolderAfterSignal();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folderStatusUpdateSignal, activeFolderView, groups, groupBatches]);

  useEffect(() => {
    const context = folderNavigationContext;
    if (!context?.folderId || !context?.groupId) {
      handledFolderNavigationRef.current = null;
      return;
    }

    if (handledFolderNavigationRef.current === context) {
      return;
    }

    const targetFolderId = normalizeId(context.folderId);
    const targetGroupId = normalizeId(context.groupId);
    if (!targetFolderId || !targetGroupId) {
      return;
    }

    if (groups.length === 0) {
      return;
    }

    const targetGroup = groups.find((group) => normalizeId(group.id) === targetGroupId);
    if (!targetGroup) {
      return;
    }

    handledFolderNavigationRef.current = context;

    const batchData = {
      batchId: context.folderId,
      id: context.folderId,
      name: context.folderName || `Folder ${context.folderId}`,
    };
    void handleFolderButtonClick(targetGroup, batchData);
  }, [folderNavigationContext, groups]);

  const handleFolderNameChange = (groupId, value) => {
    const key = normalizeId(groupId);
    const sanitized = sanitizeInputValue(value);
    setNewFolderNames((prev) => ({
      ...prev,
      [key]: sanitized,
    }));
    setFolderErrors((prev) => {
      if (!prev[key]) {
        return prev;
      }
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const handleCreateFolder = async (event, group) => {
    if (event) {
      event.preventDefault();
    }
    if (!group?.id) {
      return;
    }
    const key = normalizeId(group.id);
    const folderNameInput = newFolderNames[key] || "";
    const folderValidation = validateEntityName(folderNameInput, { label: "Folder name" });
    if (!folderValidation.isValid) {
      const message = folderValidation.message;
      showDialog({
        title: "Invalid folder name",
        message,
        closeText: "Okay",
      });
      setFolderErrors((prev) => ({
        ...prev,
        [key]: message,
      }));
      setStatusMessage(message);
      return;
    }
    const folderName = folderValidation.trimmed;
    const normalizedNewFolderName = folderName.toLowerCase();
    const existingFolders = groupBatches[key] || [];
    const folderExists = existingFolders.some((folder) => {
      const name = (folder.name || folder.batchName || "").toLowerCase().trim();
      return name && name === normalizedNewFolderName;
    });
    if (folderExists) {
      const message = `Folder "${folderName}" already exists`;
      showDialog({
        title: "Duplicate folder",
        message,
        closeText: "Got it",
      });
      setFolderErrors((prev) => ({
        ...prev,
        [key]: message,
      }));
      setStatusMessage(message);
      return;
    }
    try {
      const response = await axios.post(`${API_BASE_URL}/api/folders`, {
        name: folderName,
        groupId: group.id,
      });
      const folderPayload = response.data?.folder || {};
      const mappedFolder =
        mapFolderToSidebarEntry({
          ...folderPayload,
          folderId: folderPayload.folderId || folderPayload.batchId || folderPayload.id,
          groupId: folderPayload.groupId || folderPayload.group_id || group.id,
          totalFiles: folderPayload.totalFiles ?? folderPayload.total_files ?? 0,
        }) || {
          batchId: folderPayload.folderId || folderPayload.batchId || folderPayload.id,
          name: folderPayload.name || folderName,
          groupId: folderPayload.groupId || folderPayload.group_id || group.id,
          fileCount: folderPayload.totalFiles ?? folderPayload.total_files ?? 0,
          status: folderPayload.status || "uploaded",
          createdAt: folderPayload.createdAt || folderPayload.created_at,
          totalFiles: folderPayload.totalFiles ?? folderPayload.total_files ?? 0,
          totalIssues: folderPayload.totalIssues ?? folderPayload.total_issues ?? 0,
          fixedIssues: folderPayload.fixedIssues ?? folderPayload.fixed_issues ?? 0,
          remainingIssues: folderPayload.remainingIssues ?? folderPayload.remaining_issues ?? 0,
          unprocessedFiles: folderPayload.unprocessedFiles ?? folderPayload.unprocessed_files ?? 0,
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
      setFolderErrors((prev) => {
        if (!prev[key]) {
          return prev;
        }
        const next = { ...prev };
        delete next[key];
        return next;
      });
      setNewFolderNames((prev) => ({
        ...prev,
        [key]: "",
      }));
      triggerDashboardRefresh();
    } catch (folderError) {
      console.error("[GroupTreeSidebar] Failed to create folder:", folderError);
      setStatusMessage(folderError?.response?.data?.error || "Failed to create folder");
      setFolderErrors((prev) => ({
        ...prev,
        [key]: folderError?.response?.data?.error || "Failed to create folder",
      }));
    }
  };

  const startGroupEdit = (group) => {
    setEditingGroupId(group.id);
    setEditingGroupName(group.name || "");
    setDeletingGroupId(null);
    editingTreeItemIdRef.current = buildTreeItemId("group", group.id);
  };

  const cancelGroupEdit = () => {
    setEditingGroupId(null);
    setEditingGroupName("");
    focusEditedTreeItem();
  };

  const saveGroupEdit = async (event) => {
    if (event) {
      event.preventDefault();
    }
    if (!editingGroupId) {
      return;
    }
    const validation = validateEntityName(editingGroupName, { label: "Project name" });
    if (!validation.isValid) {
      const message = validation.message;
      showDialog({
        title: "Invalid project name",
        message,
        closeText: "Okay",
      });
      setStatusMessage(message);
      return;
    }

    const trimmedName = validation.trimmed;
    const normalizedId = normalizeId(editingGroupId);
    const normalizedName = trimmedName.toLowerCase();
    const currentGroup = groups.find((group) => normalizeId(group.id) === normalizedId);
    const duplicate =
      normalizedName &&
      groups.some(
        (group) =>
          normalizeId(group.id) !== normalizedId &&
          (group.name || "").trim().toLowerCase() === normalizedName
      );
    if (duplicate) {
      const message = `Project "${trimmedName}" already exists`;
      showDialog({
        title: "Duplicate project name",
        message,
        closeText: "Got it",
      });
      setStatusMessage(message);
      return;
    }
    try {
      const response = await axios.put(API_ENDPOINTS.project(editingGroupId), {
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
      triggerDashboardRefresh();
    } catch (error) {
      console.error("[GroupTreeSidebar] Failed to update group:", error);
      setStatusMessage(error?.response?.data?.error || "Failed to update project");
    }
  };

  const startBatchEdit = (batch, groupId) => {
    setEditingBatchId(batch.batchId);
    setEditingBatchGroupId(groupId);
    setEditingBatchName(batch.name || "");
    const identifier = batch.batchId ?? batch.id;
    editingTreeItemIdRef.current = buildTreeItemId("folder", identifier);
  };

  const cancelBatchEdit = () => {
    setEditingBatchId(null);
    setEditingBatchGroupId(null);
    setEditingBatchName("");
    focusEditedTreeItem();
  };

  const saveBatchEdit = async (event) => {
    if (event) {
      event.preventDefault();
    }
    if (!editingBatchId) {
      return;
    }
    const validation = validateEntityName(editingBatchName, { label: "Folder name" });
    if (!validation.isValid) {
      const message = validation.message;
      showDialog({
        title: "Invalid folder name",
        message,
        closeText: "Okay",
      });
      setStatusMessage(message);
      return;
    }

    const folderName = validation.trimmed;
    const normalizedBatchId = normalizeId(editingBatchId);
    const normalizedGroupId = normalizeId(editingBatchGroupId);
    const existingFolders = groupBatches[normalizedGroupId] || [];
    const normalizedNewFolderName = folderName.toLowerCase();
    const folderExists = existingFolders.some((batch) => {
      const batchId = normalizeId(batch.batchId ?? batch.id);
      if (!batchId || batchId === normalizedBatchId) {
        return false;
      }
      const name = (batch.name || batch.folderName || "").toLowerCase().trim();
      return name && name === normalizedNewFolderName;
    });
    if (folderExists) {
      const message = `Folder "${folderName}" already exists`;
      showDialog({
        title: "Duplicate folder",
        message,
        closeText: "Got it",
      });
      setStatusMessage(message);
      return;
    }
    try {
      await axios.patch(`${API_BASE_URL}/api/folders/${editingBatchId}/rename`, {
        folderName,
      });
      setGroupBatches((prev) => {
        const next = { ...prev };
        const list = (next[normalizedGroupId] || []).map((batch) =>
          normalizeId(batch.batchId) === normalizedBatchId ? { ...batch, name: folderName } : batch
        );
        next[normalizedGroupId] = list;
        return next;
      });
      setStatusMessage(`${folderName} renamed`);
      cancelBatchEdit();
      triggerDashboardRefresh();
    } catch (error) {
      console.error("[GroupTreeSidebar] Failed to rename folder:", error);
      setStatusMessage(error?.response?.data?.error || "Failed to rename folder");
    }
  };

  const handleGroupDelete = (group) => {
    setPendingDeleteGroup(group);
    setProjectDeleteError("");
  };

  const closeProjectDeleteModal = () => {
    if (isProjectDeleteLoading) {
      return;
    }
    setPendingDeleteGroup(null);
    setProjectDeleteError("");
  };

  const confirmProjectDeletion = async () => {
    if (!pendingDeleteGroup) {
      return;
    }
    const normalizedGroupId = normalizeId(pendingDeleteGroup.id);
    const projectName = pendingDeleteGroup.name || "Project";

    setProjectDeleteError("");
    setIsProjectDeleteLoading(true);
    setDeletingGroupId(pendingDeleteGroup.id);

    try {
      await axios.delete(API_ENDPOINTS.project(pendingDeleteGroup.id));
      removeGroupById(pendingDeleteGroup.id, pendingDeleteGroup?.name);
      void ensureDashboardReflectsGroupDeletion(pendingDeleteGroup.id);
      setStatusMessage(`${projectName} deleted`);
      showSuccess(`Deleted project "${projectName}"`);
      setPendingDeleteGroup(null);
      triggerDashboardRefresh();
    } catch (error) {
      console.error("[GroupTreeSidebar] Failed to delete group:", error);
      const message = error?.response?.data?.error || "Failed to delete project";
      setProjectDeleteError(message);
      setStatusMessage(message);
      showError(message);
    } finally {
      setIsProjectDeleteLoading(false);
      setDeletingGroupId((current) => {
        if (!current) {
          return null;
        }
        return normalizeId(current) === normalizedGroupId ? null : current;
      });
    }
  };

  const handleFolderDelete = (batch, groupId) => {
    setPendingDeleteFolder({
      batch,
      groupId,
    });
    setFolderDeleteError("");
  };

  const closeFolderDeleteModal = () => {
    if (isFolderDeleteLoading) {
      return;
    }
    setPendingDeleteFolder(null);
    setFolderDeleteError("");
  };

  const confirmFolderDeletion = async () => {
    if (!pendingDeleteFolder) {
      return;
    }

    const { batch, groupId } = pendingDeleteFolder;
    const batchId = batch?.batchId || batch?.id;
    const batchName = batch?.name || batch?.folderName || "Folder";
    const normalizedGroupId = normalizeId(groupId);
    const normalizedBatchId = normalizeId(batchId);

    if (!batchId || !normalizedGroupId) {
      const message = "Unable to delete folder. Missing identifiers.";
      setFolderDeleteError(message);
      showError(message);
      return;
    }

    setFolderDeleteError("");
    setIsFolderDeleteLoading(true);
    setDeletingBatchId(batchId);

    try {
      await axios.delete(`${API_BASE_URL}/api/folders/${batchId}`);

      let updatedList = [];
      setGroupBatches((prev) => {
        const prevList = prev[normalizedGroupId] || [];
        updatedList = prevList.filter(
          (existingBatch) => normalizeId(existingBatch.batchId) !== normalizedBatchId
        );
        return {
          ...prev,
          [normalizedGroupId]: updatedList,
        };
      });

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
      showSuccess(`Deleted folder "${batchName}"`);
      void ensureDashboardReflectsFolderDeletion(groupId, batchId);
      setPendingDeleteFolder(null);
      triggerDashboardRefresh();
    } catch (error) {
      console.error("[GroupTreeSidebar] Failed to delete folder:", error);
      const message = error?.response?.data?.error || "Failed to delete folder";
      setFolderDeleteError(message);
      setStatusMessage(message);
      showError(message);
    } finally {
      setIsFolderDeleteLoading(false);
      setDeletingBatchId((current) => {
        if (!current) {
          return null;
        }
        return normalizeId(current) === normalizedBatchId ? null : current;
      });
    }
  };

  const handleRefresh = async () => {
    ensureProjectView();
    await fetchGroups();
    if (onRefresh) {
      onRefresh();
    }
  };

  const handleRefreshGroupFolders = async (groupId) => {
    const normalizedId = normalizeId(groupId);
    if (!normalizedId) {
      return;
    }
    setRefreshingGroupId(normalizedId);
    try {
      await fetchGroupData(groupId, null);
      setStatusMessage("Folders updated");
    } catch (error) {
      console.error("[GroupTreeSidebar] Failed to refresh folders:", error);
      setStatusMessage("Failed to refresh folders");
    } finally {
      setRefreshingGroupId(null);
    }
  };

  const deleteModalProjectName = pendingDeleteGroup?.name || "project";
  const deleteModalFolderName =
    pendingDeleteFolder?.batch?.name ||
    pendingDeleteFolder?.batch?.folderName ||
    pendingDeleteFolder?.batch?.batchId ||
    "folder";

  useEffect(() => {
    if (!pendingDeleteGroup && !pendingDeleteFolder) {
      return;
    }
    if (typeof document === "undefined") {
      return;
    }
    const modalElement = pendingDeleteGroup ? projectDeleteModalRef.current : folderDeleteModalRef.current;
    if (!modalElement) {
      return;
    }

    const getFocusableElements = () =>
      Array.from(modalElement.querySelectorAll(FOCUSABLE_ELEMENTS_SELECTOR)).filter(
        (element) => !element.hasAttribute("disabled") && element.tabIndex !== -1
      );

    const focusableElements = getFocusableElements();
    if (focusableElements.length > 0) {
      focusableElements[0].focus();
    } else if (typeof modalElement.focus === "function") {
      modalElement.focus();
    }

    const handleKeyDown = (event) => {
      if (event.key !== "Tab") {
        return;
      }
      const updatedFocusable = getFocusableElements();
      if (updatedFocusable.length === 0) {
        event.preventDefault();
        return;
      }
      const firstFocusable = updatedFocusable[0];
      const lastFocusable = updatedFocusable[updatedFocusable.length - 1];
      if (event.shiftKey) {
        if (document.activeElement === firstFocusable || !modalElement.contains(document.activeElement)) {
          event.preventDefault();
          lastFocusable.focus();
        }
      } else if (document.activeElement === lastFocusable || !modalElement.contains(document.activeElement)) {
        event.preventDefault();
        firstFocusable.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [pendingDeleteGroup, pendingDeleteFolder, isProjectDeleteLoading, isFolderDeleteLoading]);

  if (loading) {
    return (
      <aside className="w-full max-w-sm flex-shrink-0 bg-white dark:bg-gray-800 dashboard-panel border border-gray-200 dark:border-gray-700 p-4">
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
      <aside className="w-full max-w-sm flex-shrink-0 bg-white dark:bg-gray-800 dashboard-panel border border-gray-200 dark:border-gray-700 p-6 text-center space-y-4">
        <svg
          className="mx-auto h-12 w-12 text-rose-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
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
      <aside
        ref={sidebarRootRef}
        tabIndex={-1}
        role="navigation"
        aria-label="Folder navigation"
        className="w-full max-w-sm flex-shrink-0 bg-white dark:bg-gray-800 dashboard-panel border border-gray-200 dark:border-gray-700 p-4 flex flex-col space-y-4"
      >
        <div className="flex items-center gap-3 border-b border-gray-200 pb-3 dark:border-gray-700">
          <button
            type="button"
            onClick={closeFolderView}
            ref={folderBackButtonRef}
            className="inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-semibold text-gray-700 transition hover:border-gray-300 hover:bg-gray-50 dark:border-gray-700/80 dark:bg-[#0f172a] dark:text-gray-100 dark:hover:border-gray-600 dark:hover:bg-[#1b1f34]"
            aria-label="Back to projects"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
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

        <div className="flex-1 overflow-y-auto space-y-2 scrollbar-thin scrollbar-thumb-indigo-400 scrollbar-track-transparent max-h-[calc(100vh-200px)] pr-2">
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
            folderFiles.map((file, index) => {
              const fileId = file.scanId || file.id || file.fileId;
              const fileName = file.filename || file.fileName || "Untitled file";
              const fileKey = fileId || fileName || `file-${index}`;
              const selected = isFileSelected(fileId);
              const statusInfo = resolveEntityStatus(file);
              const badgeColorClasses =
                STATUS_BADGE_STYLES[statusInfo.code] || STATUS_BADGE_STYLES.uploaded;
              const isDeletingThisFile = isDeletingFile(fileId);
              return (
                <div key={fileKey} className="relative group/file-entry">
                  <button
                    type="button"
                    className={`group w-full rounded-2xl border px-4 py-4 pr-12 text-left transition focus-visible:border-indigo-500 focus-visible:bg-indigo-600 focus-visible:text-white focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-900 ${
                      selected
                        ? "border-indigo-500 bg-indigo-600 text-white shadow-lg shadow-indigo-500/30 dark:border-indigo-500/60 dark:bg-indigo-600/90 dark:text-white"
                        : "border-indigo-100 bg-white text-gray-800 hover:border-indigo-200 hover:bg-indigo-50 dark:border-slate-700 dark:bg-gray-900 dark:text-gray-200"
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
                    <p
                      className={`text-lg font-semibold truncate ${
                        selected ? "text-white" : "text-gray-800 dark:text-gray-100"
                      } group-focus-within:text-white`}
                    >
                      {fileName}
                    </p>
                    <span
                      className={`mt-2 inline-flex rounded-full border px-3 py-0.5 text-[11px] font-semibold uppercase tracking-wide align-middle transition ${
                        selected ? SELECTED_STATUS_BADGE_CLASSES : badgeColorClasses
                      }`}
                      role="status"
                      aria-label={`File status: ${statusInfo.label}`}
                    >
                      {statusInfo.label.toUpperCase()}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={(event) => handleDeleteFile(file, event)}
                    disabled={isDeletingThisFile}
                    aria-label={`Delete ${fileName}`}
                    className={`absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-full border bg-white text-rose-600 transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-500 dark:bg-slate-900 dark:text-rose-400 ${
                      selected
                        ? "border-white/60 shadow-lg shadow-indigo-500/30"
                        : "border-rose-100 shadow-sm dark:border-rose-800"
                    } ${isDeletingThisFile ? "opacity-60 cursor-wait" : "hover:bg-rose-50 dark:hover:bg-rose-500/10"}`}
                  >
                    {isDeletingThisFile ? (
                      <svg
                        className="h-4 w-4 animate-spin text-rose-500"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        aria-hidden="true"
                      >
                        <circle className="opacity-25" cx="12" cy="12" r="10" strokeWidth="2" />
                        <path
                          className="opacity-75"
                          d="M4 12a8 8 0 018-8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="2"
                        />
                      </svg>
                    ) : (
                      <svg
                        className="h-4 w-4"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        aria-hidden="true"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-1 12a2 2 0 01-2 2H8a2 2 0 01-2-2L5 7m5 0V4h4v3m-6 0h6" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 11h6" />
                      </svg>
                    )}
                  </button>
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

  return (
    <>
      <aside
        ref={sidebarRootRef}
        tabIndex={-1}
        role="navigation"
        className="w-full max-w-sm flex-shrink-0 dashboard-panel border border-slate-200 bg-white p-6 text-slate-900 shadow-2xl shadow-slate-200/60 flex flex-col space-y-6 overflow-hidden dark:border-slate-800 dark:bg-[#0b152d]/95 dark:text-slate-100 dark:shadow-[0_40px_100px_-50px_rgba(2,6,23,0.9)]"
        aria-label="Group navigation"
      >
      <div className="flex items-center justify-between">
        <div>
          {/* <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-slate-500">Projects</p> */}
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Project Library</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">{groups.length} total</p>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          className="rounded-xl border border-indigo-100 bg-indigo-50 p-2 text-indigo-600 transition hover:bg-indigo-100 hover:text-indigo-800 dark:border-indigo-500/40 dark:bg-indigo-500/10 dark:text-indigo-300 dark:hover:bg-indigo-500/20 dark:hover:text-white"
          title="Refresh"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>

      <form onSubmit={handleCreateProject} className="flex flex-col sm:flex-row gap-2">
          <div className="flex-1">
            <input
              type="text"
              value={newProjectName}
              onChange={(event) => {
                const sanitized = sanitizeInputValue(event.target.value);
                setNewProjectName(sanitized);
                if (newProjectError) {
                  setNewProjectError("");
                }
              }}
              onKeyDown={handleEscapeBlur}
              placeholder="New project name..."
              className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-200 dark:border-slate-800/80 dark:bg-[#101735] dark:text-slate-100 dark:placeholder-slate-500 dark:focus:ring-indigo-500/70"
              aria-label="New project name"
              autoComplete="off"
            />
            
            {/* {newProjectError && (
              <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">{newProjectError}</p>
            )} */}
          </div>
        <button
          type="submit"
          disabled={isCreatingProject}
          className="flex items-center justify-center gap-2 rounded-2xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-400 dark:bg-indigo-500 dark:hover:bg-indigo-400 dark:disabled:bg-slate-600"
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

      <div
        className="space-y-3 overflow-y-auto max-h-[calc(100vh-260px)] pr-2 scrollbar-thin scrollbar-thumb-indigo-400 scrollbar-track-transparent"
        ref={treeContainerRef}
        role="tree"
        aria-label="Project navigation tree"
        onKeyDown={handleTreeKeyDown}
        onFocusCapture={handleTreeFocusCapture}
        onBlurCapture={handleTreeBlurCapture}
      >
        {groups.length === 0 ? (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400 text-sm">
            <p>No projects yet. Create one to get started!</p>
          </div>
        ) : (
          groups.map((group, groupIndex) => {
            const normalizedGroupId = normalizeId(group.id);
            const groupTreeId = buildTreeItemId("group", group.id);
            const panelId = `group-${normalizedGroupId}-panel`;
            const isExpanded = expandedGroups.has(normalizedGroupId);
            const files = groupFiles[normalizedGroupId] || [];
            const batches = groupBatches[normalizedGroupId] || [];
            const sectionState = sectionStates[normalizedGroupId] || {
              files: false,
            };
            const fileCount = files.length;
            const filesExpanded = sectionState.files;
            const fileToggleDisabled = fileCount === 0;
            const fileAriaLabel = fileToggleDisabled
              ? "Files: no files available"
              : `Files: ${fileCount} ${fileCount === 1 ? "file" : "files"} available`;
            const isSelected =
              selectedNode?.type === "group" && normalizeId(selectedNode?.id) === normalizedGroupId;
            const isEditingGroup =
              editingGroupId && normalizeId(editingGroupId) === normalizedGroupId;
            const isGroupDeleting =
              deletingGroupId && normalizeId(deletingGroupId) === normalizedGroupId;
            const isRefreshingFolders = refreshingGroupId === normalizedGroupId;
            const groupActionsTabIndex =
              activeTreeItemId === groupTreeId ? 0 : -1;
            const folderInputValue = newFolderNames[normalizedGroupId] || "";
            const folderNameValidation = validateEntityName(folderInputValue, { label: "Folder name" });
            const folderCharCountClass = folderNameValidation.isValid
              ? "text-slate-500 dark:text-slate-400"
              : "text-rose-600 dark:text-rose-400";
            const folderCharCount = folderInputValue.length;

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
                        onChange={(event) => {
                          const sanitized = sanitizeInputValue(event.target.value);
                          setEditingGroupName(sanitized);
                        }}
                        data-editing-type="group"
                        className="flex-1 min-w-0 rounded-md border border-indigo-200 bg-white px-2 py-1 text-sm text-gray-800 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-indigo-500/40 dark:bg-gray-950 dark:text-gray-100"
                        autoFocus
                        aria-label="Edit project name"
                        autoComplete="off"
                      />
                      <button
                        type="submit"
                        className="rounded-md bg-indigo-600 p-1.5 text-white shadow-sm shadow-indigo-200 hover:bg-indigo-700"
                        title="Save project name"
                      >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      </button>
                      <button
                        type="button"
                        onClick={cancelGroupEdit}
                        className="rounded-md bg-gray-200 p-1.5 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-100"
                        title="Cancel edit"
                      >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </form>
                  ) : (
                    <>
                      <button
                        type="button"
                        data-doca-tree-item="true"
                        data-tree-id={groupTreeId}
                        data-tree-type="group"
                        data-tree-level={1}
                        role="treeitem"
                        aria-level={1}
                        aria-setsize={groups.length}
                        aria-posinset={groupIndex + 1}
                        className={`w-full text-left rounded-2xl border transition group flex items-center gap-3 p-3 shadow-sm ${
                          isSelected
                            ? "border-indigo-600 bg-indigo-600 text-white shadow-lg shadow-indigo-500/30 dark:bg-indigo-600/90"
                            : "border-slate-200 bg-white text-slate-800 hover:border-indigo-200 hover:bg-indigo-50 dark:bg-[#121b33] dark:text-slate-100 dark:hover:border-indigo-500/40 dark:hover:bg-[#182248]"
                        } ${TREE_ITEM_FOCUS_CLASSES}`}
                        onClick={() => {
                          void handleGroupSelection(group);
                        }}
                        aria-expanded={isExpanded}
                        aria-controls={panelId}
                        aria-current={isSelected ? "true" : undefined}
                      >
                        <span
                          className={`w-4 h-4 flex-shrink-0 transition-transform ${
                            isExpanded ? "rotate-90 text-indigo-400" : "text-slate-400"
                          }`}
                          aria-hidden="true"
                          tabIndex={-1}
                        >
                          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true" tabIndex={-1}>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </span>
                        <span
                          className={`w-5 h-5 flex-shrink-0 ${
                            isSelected ? "text-white" : "text-slate-400 group-hover:text-slate-600 dark:group-hover:text-slate-200"
                          }`}
                          tabIndex={-1}
                        >
                          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true" tabIndex={-1}>
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                            />
                          </svg>
                        </span>
                        <div className="flex-1 overflow-hidden">
                          <h3
                            className={`text-lg font-semibold truncate ${isSelected ? "text-white" : "text-slate-900 dark:text-slate-100"}`}
                          >
                            {group.name}
                          </h3>
                        </div>
                      </button>
                      <div
                        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-0 transition-opacity group-hover/project:opacity-100 group-focus-within/project:opacity-100"
                        data-tree-actions-for={groupTreeId}
                      >
                        <button
                          type="button"
                          onClick={() => startGroupEdit(group)}
                          className="pointer-events-auto rounded-lg border border-indigo-100 bg-indigo-50 p-1 text-indigo-600 shadow-sm hover:bg-indigo-100 hover:text-indigo-800 dark:border-indigo-500/40 dark:bg-indigo-500/10 dark:text-indigo-200 dark:hover:bg-indigo-500/20 dark:hover:text-white"
                          title="Edit project"
                          tabIndex={groupActionsTabIndex}
                        >
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
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
                          onClick={() => handleGroupDelete(group)}
                          disabled={isGroupDeleting}
                          aria-busy={isGroupDeleting || undefined}
                          className="pointer-events-auto rounded-lg border border-rose-100 bg-rose-50 p-1 text-rose-600 shadow-sm hover:bg-rose-100 hover:text-rose-800 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-200 dark:hover:bg-rose-500/20 dark:hover:text-white"
                          title={isGroupDeleting ? "Deleting project..." : "Delete project"}
                          tabIndex={groupActionsTabIndex}
                        >
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M19 7l-1 12a2 2 0 01-2 2H8a2 2 0 01-2-2L5 7m5 0V4h4v3m-6 0h6"
                            />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 11h6" />
                          </svg>
                        </button>
                      </div>
                    </>
                  )}
                </div>

                <div
                  id={panelId}
                  className={`pl-4 pt-2 pb-3 space-y-3 ${isExpanded ? "" : "hidden"}`}
                  aria-hidden={!isExpanded}
                >
                    <div className="flex items-center justify-between pr-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                      <span>Folders</span>
                      <button
                        type="button"
                        onClick={() => handleRefreshGroupFolders(group.id)}
                        disabled={isRefreshingFolders}
                        className="rounded-xl border border-indigo-100 bg-white px-2 py-1 text-indigo-600 transition hover:bg-indigo-50 hover:text-indigo-800 disabled:opacity-60 disabled:cursor-not-allowed dark:border-indigo-500/40 dark:bg-indigo-500/10 dark:text-indigo-200 dark:hover:bg-indigo-500/20 dark:hover:text-white"
                        title="Refresh folders"
                        aria-label="Refresh folders"
                        aria-busy={isRefreshingFolders || undefined}
                      >
                        <svg
                          className={`h-3.5 w-3.5 ${isRefreshingFolders ? "animate-spin" : ""}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                          aria-hidden="true"
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
                    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-inner shadow-slate-100 dark:border-slate-800 dark:bg-[#0f1a30]">
                      {batches.length === 0 ? (
                        <p className="text-xs text-slate-500 dark:text-slate-400" role="status" aria-live="polite">
                          No folders available
                        </p>
                      ) : (
                          <ul
                            className="mt-1 space-y-2"
                            role="group"
                            aria-label={`Folders for ${group.name}`}
                          >
                        {batches.map((batch, batchIndex) => {
                            const folderIdentifier = batch.batchId ?? batch.id;
                            const normalizedBatchId = normalizeId(folderIdentifier);
                            const isBatchSelected =
                              selectedNode?.type === "batch" &&
                              normalizeId(selectedNode?.id) === normalizedBatchId;
                            const isEditingBatch =
                              editingBatchId && normalizeId(editingBatchId) === normalizedBatchId;
                            const isBatchDeleting =
                              deletingBatchId && normalizeId(deletingBatchId) === normalizedBatchId;
                            const isFolderRefreshing = Boolean(
                              refreshingFolderCounts[normalizedBatchId]
                            );
                            const folderTreeId = buildTreeItemId("folder", folderIdentifier);
                            const folderActionsTabIndex =
                              activeTreeItemId === folderTreeId ? 0 : -1;

                            return (
                              <li key={batch.batchId} className="relative group/folder">
                                {isEditingBatch ? (
                                  <form
                                    onSubmit={saveBatchEdit}
                                    className="flex items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 p-2 dark:border-indigo-500/30 dark:bg-indigo-500/10"
                                  >
                                  <input
                                    type="text"
                                    value={editingBatchName}
                                    onChange={(event) => {
                                      const sanitized = sanitizeInputValue(event.target.value);
                                      setEditingBatchName(sanitized);
                                    }}
                                    data-editing-type="folder"
                                    className="flex-1 min-w-0 rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm text-slate-800 placeholder-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-200 dark:border-indigo-500/30 dark:bg-[#0b1327] dark:text-slate-100 dark:placeholder-slate-500 dark:focus:ring-indigo-400"
                                    autoFocus
                                    aria-label="Edit folder name"
                                    autoComplete="off"
                                  />
                                    <button
                                      type="submit"
                                      className="rounded-lg bg-indigo-500/90 p-1.5 text-white shadow-sm shadow-indigo-500/30 hover:bg-indigo-400"
                                      title="Save folder name"
                                    >
                                      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                      </svg>
                                    </button>
                                    <button
                                      type="button"
                                      onClick={cancelBatchEdit}
                                      className="rounded-lg bg-slate-200 p-1.5 text-slate-700 hover:bg-slate-300 dark:bg-slate-700 dark:text-slate-100"
                                      title="Cancel edit"
                                    >
                                      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                      </svg>
                                    </button>
                                  </form>
                                ) : (
                                  <>
                                  <button
                                    type="button"
                                    data-doca-tree-item="true"
                                    data-tree-id={folderTreeId}
                                    data-tree-parent={groupTreeId}
                                    data-tree-type="folder"
                                    data-tree-level={2}
                                    role="treeitem"
                                    aria-level={2}
                                    aria-setsize={batches.length}
                                    aria-posinset={batchIndex + 1}
                                    className={`group w-full text-left rounded-2xl border transition flex items-center gap-3 p-2.5 shadow-sm ${
                                      isBatchSelected
                                        ? "border-indigo-500 bg-white text-slate-900 shadow-[0_0_0_3px_rgba(99,102,241,0.35)] dark:bg-[#0f172a] dark:text-white"
                                        : "border-slate-200 bg-white text-slate-800 hover:border-indigo-200 hover:bg-indigo-50 dark:bg-[#101a32] dark:text-slate-100 dark:hover:border-indigo-500/40 dark:hover:bg-[#162446]"
                                    } ${TREE_ITEM_FOCUS_CLASSES}`}
                                      onClick={() => handleFolderButtonClick(group, batch)}
                                      aria-current={isBatchSelected ? "true" : undefined}
                                    >
                                  <span
                                    className={`flex-shrink-0 rounded-lg p-1.5 ${isBatchSelected ? "bg-indigo-100 text-indigo-700 dark:bg-white/20 dark:text-white" : "bg-slate-100 text-indigo-500 dark:bg-slate-800/70 dark:text-indigo-200"}`}
                                    tabIndex={-1}
                                  >
                                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true" tabIndex={-1}>
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
                                        className={`block truncate text-lg font-medium ${
                                          isBatchSelected ? "text-slate-900 dark:text-white" : "text-slate-800 dark:text-current"
                                        } group-focus-within:text-slate-900 dark:group-focus-within:text-white`}
                                      >
                                          {batch.name || `Batch ${batch.batchId}`}
                                        </span>
                                        <span
                                          className={`text-sm ${
                                            isBatchSelected
                                              ? "text-slate-500 dark:text-slate-200"
                                              : "text-slate-500 dark:text-slate-400"
                                          }`}
                                        >
                                          <span className="inline-flex items-center gap-1">
                                            {isFolderRefreshing && (
                                              <svg
                                                className={`h-3.5 w-3.5 animate-spin ${
                                                  isBatchSelected
                                                    ? "text-indigo-100"
                                                    : "text-indigo-500 dark:text-indigo-300"
                                                }`}
                                                viewBox="0 0 24 24"
                                                fill="none"
                                                stroke="currentColor"
                                                aria-hidden="true"
                                              >
                                                <circle className="opacity-25" cx="12" cy="12" r="10" strokeWidth="4"></circle>
                                                <path
                                                  className="opacity-75"
                                                  d="M4 12a8 8 0 018-8"
                                                  strokeWidth="4"
                                                  strokeLinecap="round"
                                                ></path>
                                              </svg>
                                            )}
                                            <span>{batch.fileCount} files</span>
                                          </span>
                                        </span>
                                      </span>
                                </button>
                                    <div
                                      className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 flex gap-1 opacity-0 transition-opacity group-hover/folder:opacity-100 group-focus-within/folder:opacity-100"
                                      data-tree-actions-for={folderTreeId}
                                    >
                                      <button
                                        type="button"
                                        onClick={() => startBatchEdit(batch, group.id)}
                                        className="pointer-events-auto rounded-lg border border-indigo-100 bg-indigo-50 p-1 text-indigo-600 shadow-sm hover:bg-indigo-100 hover:text-indigo-800 dark:border-indigo-500/40 dark:bg-indigo-500/10 dark:text-indigo-200 dark:hover:bg-indigo-500/20 dark:hover:text-white"
                                        title="Edit folder"
                                        tabIndex={folderActionsTabIndex}
                                      >
                                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
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
                                        onClick={() => handleFolderDelete(batch, group.id)}
                                        disabled={isBatchDeleting}
                                        aria-busy={isBatchDeleting || undefined}
                                        className="pointer-events-auto rounded-lg border border-rose-100 bg-rose-50 p-1 text-rose-600 shadow-sm hover:bg-rose-100 hover:text-rose-800 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-200 dark:hover:bg-rose-500/20 dark:hover:text-white"
                                        title={isBatchDeleting ? "Deleting folder..." : "Delete folder"}
                                        tabIndex={folderActionsTabIndex}
                                      >
                                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                          <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M19 7l-1 12a2 2 0 01-2 2H8a2 2 0 01-2-2L5 7m5 0V4h4v3m-6 0h6"
                                          />
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 11h6" />
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
                    </div>

                    <form
                      onSubmit={(event) => handleCreateFolder(event, group)}
                      className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-sm flex items-center gap-3 shadow-inner shadow-slate-200 dark:border-slate-700/80 dark:bg-[#0b1327] dark:shadow-black/30"
                    >
                    <input
                      type="text"
                      value={folderInputValue}
                      onChange={(event) => handleFolderNameChange(group.id, event.target.value)}
                      placeholder="New folder name..."
                      className="flex-1 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-200 dark:border-slate-800 dark:bg-transparent dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-indigo-500 dark:focus:ring-indigo-500/60"
                      aria-label={`New folder for ${group.name}`}
                      autoComplete="off"
                      onKeyDown={handleEscapeBlur}
                    />
                    <button
                      type="submit"
                      className="rounded-xl bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-400 dark:bg-indigo-500 dark:hover:bg-indigo-400 dark:disabled:bg-slate-600"
                    >
                      + 
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
                            aria-disabled={fileToggleDisabled || undefined}
                            disabled={fileToggleDisabled}
                            aria-label={fileAriaLabel}
                          >
                            <span className="flex items-center gap-2">
                              <span className="rounded-md bg-indigo-100 text-indigo-700 p-1" aria-hidden="true">
                                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
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
                                const statusInfo = resolveEntityStatus(file);
                                const statusClasses =
                                  FILE_STATUS_STYLES[statusInfo.code] || FILE_STATUS_STYLES.default;

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
                                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
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
                                        {statusInfo.label && (
                                            <span
                                                className={`mt-0.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${statusClasses}`}
                                            >
                                                <span className="h-1.5 w-1.5 rounded-full bg-current" />
                                                {statusInfo.label}
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
              </div>
            );
          })
        )}
      </div>

      <div role="status" aria-live="polite" className="sr-only">
        {statusMessage}
      </div>
    </aside>
      {pendingDeleteGroup && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-project-title"
          aria-describedby="delete-project-description"
          onClick={closeProjectDeleteModal}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
            ref={projectDeleteModalRef}
            tabIndex={-1}
          >
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-full bg-rose-50 dark:bg-rose-500/20 flex items-center justify-center text-rose-600 dark:text-rose-200">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <h3 id="delete-project-title" className="text-lg font-semibold text-slate-900 dark:text-white">
                  Delete project
                </h3>
                <p
                  id="delete-project-description"
                  className="mt-1 text-sm text-slate-600 dark:text-slate-400"
                >{`Deleting "${deleteModalProjectName}" permanently removes all folders and files under it. This action cannot be undone.`}</p>
                {projectDeleteError && (
                  <p className="mt-3 text-sm text-rose-600 dark:text-rose-400">{projectDeleteError}</p>
                )}
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={closeProjectDeleteModal}
                disabled={isProjectDeleteLoading}
                className="px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmProjectDeletion}
                disabled={isProjectDeleteLoading}
                aria-busy={isProjectDeleteLoading || undefined}
                className="px-4 py-2.5 rounded-lg bg-rose-600 text-white font-semibold shadow-sm hover:bg-rose-500 disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center min-w-[11rem]"
              >
                {isProjectDeleteLoading ? (
                  <span className="flex items-center gap-2 text-sm">
                    <span className="h-4 w-4 rounded-full border-2 border-white/60 border-t-transparent animate-spin" />
                    {`Deleting ${deleteModalProjectName}...`}
                  </span>
                ) : (
                  "Delete project"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
      {pendingDeleteFolder && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-folder-title"
          aria-describedby="delete-folder-description"
          onClick={closeFolderDeleteModal}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
            ref={folderDeleteModalRef}
            tabIndex={-1}
          >
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-full bg-rose-50 dark:bg-rose-500/20 flex items-center justify-center text-rose-600 dark:text-rose-200">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <h3 id="delete-folder-title" className="text-lg font-semibold text-slate-900 dark:text-white">
                  Delete folder
                </h3>
                <p
                  id="delete-folder-description"
                  className="mt-1 text-sm text-slate-600 dark:text-slate-400"
                >{`Deleting "${deleteModalFolderName}" will permanently remove all files inside this folder. This action cannot be undone.`}</p>
                {folderDeleteError && (
                  <p className="mt-3 text-sm text-rose-600 dark:text-rose-400">{folderDeleteError}</p>
                )}
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={closeFolderDeleteModal}
                disabled={isFolderDeleteLoading}
                className="px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmFolderDeletion}
                disabled={isFolderDeleteLoading}
                aria-busy={isFolderDeleteLoading || undefined}
                className="px-4 py-2.5 rounded-lg bg-rose-600 text-white font-semibold shadow-sm hover:bg-rose-500 disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center min-w-[11rem]"
              >
                {isFolderDeleteLoading ? (
                  <span className="flex items-center gap-2 text-sm">
                    <span className="h-4 w-4 rounded-full border-2 border-white/60 border-t-transparent animate-spin" />
                    {`Deleting ${deleteModalFolderName}...`}
                  </span>
                ) : (
                  "Delete folder"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
});

export default GroupTreeSidebar;
