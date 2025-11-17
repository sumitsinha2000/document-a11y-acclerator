import { useState, useCallback, useEffect, useRef } from 'react';
import { Project, Document, Folder, AccessibilityReport, Issue } from './types';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import DocumentsColumn from './components/DocumentsColumn';
import { useNotification } from './contexts/NotificationContext';
import http from './lib/http';
import { API_ENDPOINTS } from './config/api';
import {
  fallbackId,
  mapProjectFromApi,
  mapFolderDocumentEntry,
  partitionBatchesByProject,
  mergeFoldersWithExisting,
  mergeProjectsWithAssignments,
  serializeDocuments,
  deserializeDocuments,
  readFolderCacheFromStorage,
  persistFolderCache,
  SerializedDocument,
  CachedFolderDetails,
} from './lib/workspaceHelpers';

const App: React.FC = () => {
  const { showError, showSuccess, showInfo } = useNotification();
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [currentFolder, setCurrentFolder] = useState<Folder | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncingFolderId, setSyncingFolderId] = useState<string | null>(null);

interface UploadMetadata {
  scanId?: string;
}

  const currentProjectRef = useRef<Project | null>(null);
  const currentFolderRef = useRef<Folder | null>(null);

  useEffect(() => {
    currentProjectRef.current = currentProject;
  }, [currentProject]);

  useEffect(() => {
    currentFolderRef.current = currentFolder;
  }, [currentFolder]);

  const folderCacheRef = useRef<Record<string, CachedFolderDetails>>({});
  useEffect(() => {
    folderCacheRef.current = readFolderCacheFromStorage();
  }, []);

  const updateProjectFolder = useCallback(
    (projectId: string, folderId: string, updater: (folder: Folder) => Folder) => {
      let updatedProjectState: Project | null = null;
      let updatedFolderState: Folder | null = null;
      setProjects((prevProjects) =>
        prevProjects.map((project) => {
          if (project.id !== projectId) return project;
          const updatedFolders = project.folders.map((folder) => {
            if (folder.id !== folderId) return folder;
            const nextFolder = updater(folder);
            updatedFolderState = nextFolder;
            return nextFolder;
          });
          updatedProjectState = { ...project, folders: updatedFolders };
          return updatedProjectState;
        }),
      );
      if (updatedProjectState) {
        setCurrentProject((prev) =>
          prev?.id === updatedProjectState.id ? updatedProjectState : prev ?? updatedProjectState,
        );
      }
      if (updatedFolderState && currentFolder?.id === folderId) {
        setCurrentFolder(updatedFolderState);
      }
      return { updatedProjectState, updatedFolderState };
    },
    [currentFolder],
  );

  const applyFolderDocuments = useCallback(
    (projectId: string, folderId: string, documents: Document[], metadata?: { name?: string; syncedAt?: Date }) => {
      updateProjectFolder(projectId, folderId, (folder) => ({
        ...folder,
        name: metadata?.name ?? folder.name,
        documents,
        lastSyncedAt: metadata?.syncedAt ?? new Date(),
        isRemote: true,
      }));
    },
    [updateProjectFolder],
  );

  const refreshProjectFolderCount = useCallback(async (projectId: string) => {
    if (!projectId || projectId === '__unassigned') return;
    try {
      const response = await http.get(API_ENDPOINTS.projectFolderCount(projectId));
      const folderCount = Number(response.data?.folderCount ?? 0);
      setProjects((prev) =>
        prev.map((project) =>
          project.id === projectId ? { ...project, folderCount } : project,
        ),
      );
      setCurrentProject((prev) =>
        prev && prev.id === projectId ? { ...prev, folderCount } : prev,
      );
    } catch (error) {
      console.error('[App] Failed to load folder count', error);
    }
  }, []);

const ensureFolderDocuments = useCallback(
  async (projectId: string, folderId: string) => {
      const cachedEntry = folderCacheRef.current[folderId];
      if (cachedEntry) {
        const cachedDocuments = deserializeDocuments(cachedEntry.documents);
        applyFolderDocuments(projectId, folderId, cachedDocuments, {
          name: cachedEntry.folderName,
          syncedAt: new Date(cachedEntry.fetchedAt),
        });
      }

      setSyncingFolderId(folderId);
      try {
        const response = await http.get(API_ENDPOINTS.folderDetails(folderId));
        const remoteFolderMeta = response.data?.folder;
        const remoteDocs = Array.isArray(response.data?.documents) ? response.data.documents : [];
        const documents = remoteDocs.map((entry: Record<string, any>) => mapFolderDocumentEntry(entry, folderId));
        applyFolderDocuments(projectId, folderId, documents, {
          name: remoteFolderMeta?.name ?? cachedEntry?.folderName,
          syncedAt: new Date(),
        });
        folderCacheRef.current[folderId] = {
          documents: serializeDocuments(documents),
          folderName: remoteFolderMeta?.name ?? cachedEntry?.folderName,
          fetchedAt: Date.now(),
        };
        persistFolderCache(folderCacheRef.current);
      } catch (error) {
        console.error('[App] Failed to hydrate folder', error);
        showError('Unable to load folder details from the server.');
      } finally {
        setSyncingFolderId(null);
      }
  },
  [applyFolderDocuments, showError],
);

const refreshHistoryBatches = useCallback(
  async () => {
    try {
      const response = await http.get(API_ENDPOINTS.history);
      const historyBatches = Array.isArray(response.data?.batches) ? response.data.batches : [];
      if (!historyBatches.length) {
        return;
      }
      const { assignments, unattached } = partitionBatchesByProject(historyBatches);
      setProjects((prev) => mergeProjectsWithAssignments(prev, assignments, unattached));
    } catch (error) {
      console.error('[App] Failed to refresh history', error);
    }
  },
  [mergeProjectsWithAssignments],
);

const syncFolderWithBackend = useCallback(
  async (folder: Folder, project: Project) => {
    if (folder.isRemote) {
      return folder;
    }
    try {
      await http.post(API_ENDPOINTS.folders, {
        folderId: folder.id,
        name: folder.name,
        projectId: project.id,
      });
      const syncedFolder: Folder = {
        ...folder,
        isRemote: true,
        lastSyncedAt: new Date(),
      };
      setProjects((prevProjects) =>
        prevProjects.map((proj) =>
          proj.id === project.id
            ? {
                ...proj,
                folders: proj.folders.map((existingFolder) =>
                  existingFolder.id === folder.id ? syncedFolder : existingFolder,
                ),
              }
            : proj,
        ),
      );
      setCurrentProject((prev) =>
        prev && prev.id === project.id
          ? {
              ...prev,
              folders: prev.folders.map((existingFolder) =>
                existingFolder.id === folder.id ? syncedFolder : existingFolder,
              ),
            }
          : prev,
      );
      if (currentFolder?.id === folder.id) {
        setCurrentFolder(syncedFolder);
      }
      showSuccess('Folder synced with backend.');
      return syncedFolder;
    } catch (error) {
      console.error('[App] Failed to sync folder with backend', error);
      showError('Unable to sync folder with the backend.');
      return folder;
    }
  },
  [currentFolder, showError, showSuccess],
);

const assignDocumentToFolder = useCallback(
  async (folderId: string, documentId: string) => {
    try {
      await http.post(API_ENDPOINTS.folderDocuments(folderId), { documentIds: [documentId] });
    } catch (error) {
      console.error('[App] Failed to assign document to folder', error);
      showError('Document uploaded but could not be attached to the folder.');
    }
  },
  [showError],
);

  const loadProjectsFromBackend = useCallback(async () => {
    setIsBootstrapping(true);
    setSyncError(null);
    try {
      const [projectNamesResponse, foldersResponse] = await Promise.all([
        http.get(API_ENDPOINTS.projectNames),
        http.get(API_ENDPOINTS.folders),
      ]);

      const remoteProjects = Array.isArray(projectNamesResponse.data?.projects)
        ? projectNamesResponse.data.projects.map((project: Record<string, any>) => mapProjectFromApi(project))
        : [];

      const folderPayload = Array.isArray(foldersResponse.data?.folders) ? foldersResponse.data.folders : [];
      let batchSource = folderPayload;
      if (batchSource.length === 0) {
        try {
          const historyResponse = await http.get(API_ENDPOINTS.history);
          const historyBatches = Array.isArray(historyResponse.data?.batches) ? historyResponse.data.batches : [];
          batchSource = historyBatches;
        } catch (historyError) {
          console.error('[App] Failed to load history fallback', historyError);
        }
      }
      const { assignments, unattached } = partitionBatchesByProject(batchSource);

      const merged = mergeProjectsWithAssignments(remoteProjects, assignments, unattached);

      setProjects(merged);

      const previousProject = currentProjectRef.current;
      const previousFolder = currentFolderRef.current;

      const nextProject = previousProject
        ? merged.find((project) => project.id === previousProject.id) ?? merged[0] ?? null
        : merged[0] ?? null;
      setCurrentProject(nextProject ?? null);

      const nextFolder =
        nextProject && previousFolder
          ? nextProject.folders.find((folder) => folder.id === previousFolder.id) ??
            nextProject.folders[0] ??
            null
          : nextProject?.folders[0] ?? null;
      setCurrentFolder(nextFolder ?? null);

      if (nextProject && nextFolder && nextFolder.isRemote && nextFolder.documents.length === 0) {
        void ensureFolderDocuments(nextProject.id, nextFolder.id);
      }
      void refreshHistoryBatches();
    } catch (error) {
      console.error('[App] Failed to load projects', error);
      setSyncError('Unable to load projects from the backend.');
      showError('Unable to load projects from the backend.');
    } finally {
      setIsBootstrapping(false);
    }
  }, [ensureFolderDocuments, showError, refreshHistoryBatches]);

  useEffect(() => {
    void loadProjectsFromBackend();
  }, [loadProjectsFromBackend]);

  // Effect to set initial project and folder as a fallback when data changes locally
  useEffect(() => {
    if (projects.length > 0 && !currentProject) {
      const firstProject = projects[0];
      setCurrentProject(firstProject);
      if (firstProject.folders.length > 0) {
        setCurrentFolder(firstProject.folders[0]);
      } else {
        setCurrentFolder(null);
      }
    } else if (projects.length === 0) {
      setCurrentProject(null);
      setCurrentFolder(null);
    }
  }, [projects, currentProject]);


  const handleCreateProject = useCallback(async (projectName: string) => {
    const trimmed = projectName.trim();
    if (!trimmed) return;
    try {
      const response = await http.post(API_ENDPOINTS.projects, { name: trimmed });
      const payload = response.data?.group ?? response.data ?? { id: fallbackId('project'), name: trimmed };
      const newProject = mapProjectFromApi(payload);
      setProjects((prevProjects) => [newProject, ...prevProjects]);
      setCurrentProject(newProject);
      setCurrentFolder(newProject.folders[0] ?? null);
      showSuccess('Project created.');
    } catch (error) {
      console.error('[App] Failed to create project', error);
      showError('Failed to create project.');
    }
  }, [showError, showSuccess]);

  const handleSelectProject = useCallback((projectId: string) => {
    const project = projects.find((p) => p.id === projectId);
    if (!project) return;
    setCurrentProject(project);
    const folderExistsInProject = project.folders.some((f) => f.id === currentFolder?.id);
    const nextFolder = folderExistsInProject ? currentFolder : project.folders[0] ?? null;
    setCurrentFolder(nextFolder ?? null);

    if (project && nextFolder && nextFolder.isRemote && nextFolder.documents.length === 0) {
      void ensureFolderDocuments(project.id, nextFolder.id);
    }

    void refreshProjectFolderCount(project.id);
  }, [projects, currentFolder, ensureFolderDocuments, refreshProjectFolderCount]);

  const handleUpdateProject = useCallback(async (projectId: string, newName: string) => {
    const trimmed = newName.trim();
    if (!trimmed) return;
    try {
      const response = await http.put(API_ENDPOINTS.projectDetails(projectId), { name: trimmed });
      const updatedName = response.data?.group?.name ?? response.data?.name ?? trimmed;
      setProjects((prevProjects) =>
        prevProjects.map((project) =>
          project.id === projectId ? { ...project, name: updatedName } : project,
        ),
      );
      if (currentProject?.id === projectId) {
        setCurrentProject((prev) => (prev ? { ...prev, name: updatedName } : prev));
      }
    } catch (error) {
      console.error('[App] Failed to update project', error);
      showError('Unable to update project.');
    }
  }, [currentProject, showError]);

  const handleDeleteProject = useCallback(async (projectId: string) => {
    try {
      await http.delete(API_ENDPOINTS.projectDetails(projectId));
      setProjects((prevProjects) => prevProjects.filter((project) => project.id !== projectId));

      if (currentProject?.id === projectId) {
        setCurrentProject(null);
        setCurrentFolder(null);
      }
    } catch (error) {
      console.error('[App] Failed to delete project', error);
      showError('Unable to delete project.');
    }
  }, [currentProject, showError]);

  const handleCreateFolder = useCallback((folderName: string) => {
    if (!currentProject || folderName.trim() === '') return;
    const newFolder: Folder = {
      id: fallbackId('folder'),
      name: folderName.trim(),
      documents: [],
      projectId: currentProject.id,
      isRemote: false,
      lastSyncedAt: null,
    };
    setProjects((prevProjects) =>
      prevProjects.map((project) => {
        if (project.id === currentProject.id) {
          return { ...project, folders: [newFolder, ...project.folders] };
        }
        return project;
      }),
    );
    setCurrentFolder(newFolder);
    showInfo('Folder created locally. Upload a batch to sync it with the backend.');
  }, [currentProject, showInfo]);

  const handleSelectFolder = useCallback((folderId: string) => {
    if (!currentProject) return;
    const folder = currentProject.folders.find((f) => f.id === folderId);
    if (!folder) return;
    setCurrentFolder(folder);
    if (folder.isRemote && folder.documents.length === 0) {
      void ensureFolderDocuments(currentProject.id, folder.id);
    }
  }, [currentProject, ensureFolderDocuments]);

  const handleUpdateFolder = useCallback(async (folderId: string, newName: string) => {
    if (!currentProject || newName.trim() === '') return;
    const trimmed = newName.trim();
    const targetFolder = currentProject.folders.find((folder) => folder.id === folderId);
    if (!targetFolder) return;

    if (targetFolder.isRemote) {
      try {
        await http.patch(API_ENDPOINTS.renameBatch(folderId), { batchName: trimmed });
      } catch (error) {
        console.error('[App] Failed to rename folder', error);
        showError('Unable to rename folder.');
        return;
      }
    }

    let updatedProjectState: Project | null = null;
    let updatedFolderState: Folder | null = null;
    setProjects((prevProjects) =>
      prevProjects.map((project) => {
        if (project.id !== currentProject.id) return project;
        const updatedFolders = project.folders.map((folder) => {
          if (folder.id !== folderId) return folder;
          const renamedFolder = { ...folder, name: trimmed };
          updatedFolderState = renamedFolder;
          return renamedFolder;
        });
        updatedProjectState = { ...project, folders: updatedFolders };
        return updatedProjectState;
      }),
    );

    if (updatedProjectState) {
      setCurrentProject(updatedProjectState);
    }
    if (currentFolder?.id === folderId && updatedFolderState) {
      setCurrentFolder(updatedFolderState);
    }
  }, [currentProject, currentFolder, showError]);

  const handleDeleteFolder = useCallback(async (folderId: string) => {
    if (!currentProject) return;
    const targetFolder = currentProject.folders.find((folder) => folder.id === folderId);
    if (!targetFolder) return;

    if (targetFolder.isRemote) {
      try {
        await http.delete(API_ENDPOINTS.deleteBatch(folderId));
      } catch (error) {
        console.error('[App] Failed to delete folder', error);
        showError('Unable to delete folder.');
        return;
      }
    }

    let updatedProjectState: Project | null = null;
    let targetFolderIndex = -1;
    setProjects((prevProjects) =>
      prevProjects.map((project) => {
        if (project.id !== currentProject.id) return project;
        const originalFolders = project.folders;
        targetFolderIndex = originalFolders.findIndex((folder) => folder.id === folderId);
        updatedProjectState = { ...project, folders: project.folders.filter((folder) => folder.id !== folderId) };
        return updatedProjectState;
      }),
    );

    if (updatedProjectState) {
      setCurrentProject(updatedProjectState);
      if (currentFolder?.id === folderId) {
        if (updatedProjectState.folders.length > 0) {
          const newIndex = Math.max(0, Math.min(targetFolderIndex, updatedProjectState.folders.length - 1));
          setCurrentFolder(updatedProjectState.folders[newIndex]);
        } else {
          setCurrentFolder(null);
        }
      }
    }
  }, [currentProject, currentFolder, showError]);

  const handleUploadDocuments = useCallback(
    async (files: FileList, metadata?: UploadMetadata) => {
      if (!currentProject || !currentFolder) return;

      const projectSnapshot = currentProject;
      const folderSnapshot = currentFolder;

      const newDocuments: Document[] = Array.from(files).map((file) => ({
        id: `doc-${Date.now()}-${Math.random()}`,
        name: file.name,
        size: file.size,
        uploadDate: new Date(),
        status: 'Not Scanned',
      }));

      updateProjectFolder(projectSnapshot.id, folderSnapshot.id, (folder) => ({
        ...folder,
        documents: [...folder.documents, ...newDocuments],
      }));

      const syncedFolder = await syncFolderWithBackend(folderSnapshot, projectSnapshot);

      if (!syncedFolder.isRemote) return;

      if (metadata?.scanId) {
        await assignDocumentToFolder(syncedFolder.id, metadata.scanId);
      }

      await ensureFolderDocuments(projectSnapshot.id, syncedFolder.id);
    },
    [currentProject, currentFolder, ensureFolderDocuments, syncFolderWithBackend, assignDocumentToFolder],
  );
  
  const simulateLocalFolderScan = useCallback(() => {
    if (!currentProject || !currentFolder) return;

    let updatedProjectState: Project | null = null;
    let updatedFolderState: Folder | null = null;

    updateProjectFolder(currentProject.id, currentFolder.id, (folder) => ({
      ...folder,
      documents: folder.documents.map((doc) =>
        doc.status === 'Not Scanned' ? { ...doc, status: 'Scanning' } : doc,
      ),
    }));

    setTimeout(() => {
      updateProjectFolder(currentProject.id, currentFolder.id, (folder) => ({
        ...folder,
        documents: folder.documents.map((doc) => {
          if (doc.status === 'Scanning') {
            const issueTypes = ['Missing Alt Text', 'Low Contrast', 'Empty Link', 'No Page Title', 'Untagged PDF'];
            const severities: Issue['severity'][] = ['Critical', 'Serious', 'Moderate', 'Minor'];
            const issues: Issue[] = [];
            const issueCount = Math.floor(Math.random() * 5);

            for (let i = 0; i < issueCount; i++) {
              issues.push({
                id: `issue-${doc.id}-${i}`,
                type: issueTypes[Math.floor(Math.random() * issueTypes.length)],
                description: 'This is a mock description of the accessibility issue that was found during the scan.',
                location: `Page ${Math.floor(Math.random() * 10) + 1}`,
                status: 'Needs Attention',
                severity: severities[Math.floor(Math.random() * severities.length)],
              });
            }

            const report: AccessibilityReport = {
              score: Math.max(0, 100 - issueCount * (Math.floor(Math.random() * 5) + 5)),
              issues,
            };
            return { ...doc, status: 'Scanned', accessibilityReport: report };
          }
          return doc;
        }),
      }));
    }, 2000);
  }, [currentProject, currentFolder, updateProjectFolder]);

  const handleScanFolder = useCallback(async () => {
    if (!currentProject || !currentFolder) return;

    if (!currentFolder.isRemote) {
      simulateLocalFolderScan();
      return;
    }

    const pendingDocuments = currentFolder.documents.filter((doc) => doc.status !== 'Scanning');
    if (pendingDocuments.length === 0) {
      showInfo('All documents in this folder have already been scanned.');
      return;
    }

    updateProjectFolder(currentProject.id, currentFolder.id, (folder) => ({
      ...folder,
      documents: folder.documents.map((doc) =>
        pendingDocuments.some((pending) => pending.id === doc.id)
          ? { ...doc, status: 'Scanning' as Document['status'] }
          : doc,
      ),
    }));

    try {
      for (const doc of pendingDocuments) {
        await http.post(API_ENDPOINTS.startScan(doc.id));
      }
      showSuccess(
        `Scan started for ${pendingDocuments.length} document${pendingDocuments.length === 1 ? '' : 's'}.`,
      );
      await ensureFolderDocuments(currentProject.id, currentFolder.id);
    } catch (error) {
      console.error('[App] Failed to trigger scan', error);
      showError('Failed to start scans for this folder.');
    }
  }, [currentProject, currentFolder, ensureFolderDocuments, showError, showInfo, showSuccess, simulateLocalFolderScan, updateProjectFolder]);

  const handleUpdateIssueStatus = useCallback(
    (docId: string, issueId: string, status: 'Needs Attention' | 'Fixed') => {
      if (!currentProject || !currentFolder) return;

      updateProjectFolder(currentProject.id, currentFolder.id, (folder) => ({
        ...folder,
        documents: folder.documents.map((doc) => {
          if (doc.id === docId && doc.accessibilityReport) {
            const updatedIssues = doc.accessibilityReport.issues.map((issue) =>
              issue.id === issueId ? { ...issue, status } : issue,
            );
            return { ...doc, accessibilityReport: { ...doc.accessibilityReport, issues: updatedIssues } };
          }
          return doc;
        }),
      }));
    },
    [currentProject, currentFolder, updateProjectFolder],
  );

  const handleBulkUpdateIssueStatus = useCallback(
    (updates: { docId: string; issueId: string; status: 'Needs Attention' | 'Fixed' }[]) => {
      if (!currentProject || !currentFolder || updates.length === 0) return;

      const updatesMap = new Map<string, Map<string, 'Needs Attention' | 'Fixed'>>();
      updates.forEach((update) => {
        if (!updatesMap.has(update.docId)) {
          updatesMap.set(update.docId, new Map());
        }
        updatesMap.get(update.docId)!.set(update.issueId, update.status);
      });

      updateProjectFolder(currentProject.id, currentFolder.id, (folder) => ({
        ...folder,
        documents: folder.documents.map((doc) => {
          const docUpdates = updatesMap.get(doc.id);
          if (docUpdates && doc.accessibilityReport) {
            const updatedIssues = doc.accessibilityReport.issues.map((issue) =>
              docUpdates.has(issue.id) ? { ...issue, status: docUpdates.get(issue.id)! } : issue,
            );
            return { ...doc, accessibilityReport: { ...doc.accessibilityReport, issues: updatedIssues } };
          }
          return doc;
        }),
      }));
    },
    [currentProject, currentFolder, updateProjectFolder],
  );

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <Header />
      <main className="flex-grow container mx-auto p-4 md:p-8 flex flex-col gap-4">
        {isBootstrapping && (
          <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm text-indigo-700">
            Syncing projects and folders with the backend&hellip;
          </div>
        )}
        {syncError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {syncError}
          </div>
        )}
        <div className="flex gap-8">
          <Sidebar
            projects={projects}
            currentProject={currentProject}
            currentFolder={currentFolder}
            onCreateProject={handleCreateProject}
            onSelectProject={handleSelectProject}
            onUpdateProject={handleUpdateProject}
            onDeleteProject={handleDeleteProject}
            onCreateFolder={handleCreateFolder}
            onSelectFolder={handleSelectFolder}
            onUpdateFolder={handleUpdateFolder}
            onDeleteFolder={handleDeleteFolder}
          />
          <div className="flex-1 min-w-0">
            {syncingFolderId && currentFolder?.id === syncingFolderId && (
              <div className="mb-3 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-700">
                Refreshing folder from the backend&hellip;
              </div>
            )}
            <DocumentsColumn
              currentProject={currentProject}
              currentFolder={currentFolder}
              onUpload={handleUploadDocuments}
              onScanFolder={handleScanFolder}
              onUpdateIssueStatus={handleUpdateIssueStatus}
              onBulkUpdateIssueStatus={handleBulkUpdateIssueStatus}
            />
          </div>
        </div>
      </main>
    </div>
  );
};

export default App;
