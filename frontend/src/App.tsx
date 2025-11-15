import React, { useState, useCallback, useEffect } from 'react';
import { Project, Document, Folder, AccessibilityReport, Issue } from './types';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import DocumentsColumn from './components/DocumentsColumn';
import { useNotification } from './contexts/NotificationContext';
import http from './lib/http';
import { API_ENDPOINTS } from './config/api';

const fallbackId = (prefix: string) => `${prefix}-${Date.now()}-${Math.round(Math.random() * 10000)}`;

const mapProjectFromApi = (raw: Record<string, unknown>): Project => {
  const id = String(raw.id ?? raw.group_id ?? fallbackId('project'));
  const name = (raw.name as string) || (raw.group_name as string) || 'Untitled Project';
  return {
    id,
    name,
    folders: [],
  };
};

const resolveDocumentStatus = (status?: string | null): Document['status'] => {
  if (!status) {
    return 'Not Scanned';
  }
  const normalized = status.toLowerCase();
  if (['uploaded', 'pending', 'unprocessed'].includes(normalized)) {
    return 'Not Scanned';
  }
  if (['processing', 'scan_pending', 'scanning'].includes(normalized)) {
    return 'Scanning';
  }
  return 'Scanned';
};

const toIssueSeverity = (value?: string): Issue['severity'] => {
  const normalized = value?.toLowerCase();
  if (normalized === 'critical') return 'Critical';
  if (normalized === 'serious' || normalized === 'high') return 'Serious';
  if (normalized === 'moderate' || normalized === 'medium') return 'Moderate';
  return 'Minor';
};

const flattenIssuesFromResults = (results: unknown, folderId: string, docId: string): Issue[] => {
  if (!results || typeof results !== 'object') {
    return [];
  }
  const issues: Issue[] = [];
  Object.entries(results as Record<string, unknown>).forEach(([category, value]) => {
    if (Array.isArray(value)) {
      value.forEach((rawIssue, index) => {
        const issue = rawIssue as Record<string, unknown>;
        issues.push({
          id: String(issue.id ?? `${docId}-${category}-${index}`),
          type: String(issue.ruleId ?? issue.type ?? category ?? 'Issue'),
          description: String(issue.description ?? issue.message ?? 'Accessibility issue detected.'),
          location: String(issue.location ?? issue.page ?? issue.selector ?? 'Unknown location'),
          status: 'Needs Attention',
          severity: toIssueSeverity(issue.severity as string),
        });
      });
    }
  });
  return issues;
};

const mapScanToDocument = (scan: Record<string, any>, folderId: string): Document => {
  const docId = String(scan.scanId ?? scan.id ?? fallbackId('doc'));
  const uploadDateRaw = scan.uploadDate ?? scan.createdAt ?? scan.created_at ?? new Date().toISOString();
  const uploadDate = new Date(uploadDateRaw);
  const summary = scan.summary || scan.initialSummary || {};
  const complianceScore = typeof summary.complianceScore === 'number' ? summary.complianceScore : undefined;
  const results = scan.results;
  const issues = flattenIssuesFromResults(results, folderId, docId);

  const accessibilityReport: AccessibilityReport | undefined =
    complianceScore !== undefined || issues.length > 0
      ? {
          score: Math.round(
            complianceScore !== undefined ? complianceScore : Math.max(0, 100 - issues.length * 5),
          ),
          issues,
        }
      : undefined;

  return {
    id: docId,
    name: scan.filename || scan.name || 'Document',
    size: Number(scan.fileSize || scan.size || 0),
    uploadDate: uploadDate,
    status: resolveDocumentStatus(scan.status),
    accessibilityReport,
  };
};

const mapBatchToFolder = (batch: Record<string, any>): Folder => {
  const folderId = String(batch.batchId ?? batch.id ?? fallbackId('folder'));
  const timestamp = batch.uploadDate ?? batch.createdAt;
  const readableDate = timestamp ? new Date(timestamp).toLocaleString() : '';
  return {
    id: folderId,
    name: batch.name || `Folder ${readableDate || folderId}`,
    documents: [],
    projectId: batch.groupId ?? batch.group_id ?? undefined,
    isRemote: true,
    lastSyncedAt: null,
  };
};

const partitionBatchesByProject = (batches: Array<Record<string, any>>) => {
  const assignments = new Map<string, Folder[]>();
  const unattached: Folder[] = [];
  batches.forEach((batch) => {
    const folder = mapBatchToFolder(batch);
    if (folder.projectId) {
      const next = assignments.get(folder.projectId) ?? [];
      next.push(folder);
      assignments.set(folder.projectId, next);
    } else {
      unattached.push(folder);
    }
  });
  return { assignments, unattached };
};

const App: React.FC = () => {
  const { showError, showSuccess, showInfo } = useNotification();
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [currentFolder, setCurrentFolder] = useState<Folder | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncingFolderId, setSyncingFolderId] = useState<string | null>(null);

  const ensureFolderDocuments = useCallback(async (projectId: string, folderId: string) => {
    setSyncingFolderId(folderId);
    try {
      const response = await http.get(API_ENDPOINTS.batchDetails(folderId));
      const remoteScans = Array.isArray(response.data?.scans) ? response.data.scans : [];
      const documents = remoteScans.map((scan: Record<string, any>) => mapScanToDocument(scan, folderId));

      let nextProjectState: Project | null = null;
      let nextFolderState: Folder | null = null;
      setProjects((prev) =>
        prev.map((project) => {
          if (project.id !== projectId) return project;
          const updatedFolders = project.folders.map((folder) => {
            if (folder.id !== folderId) return folder;
            const hydratedFolder: Folder = {
              ...folder,
              documents,
              lastSyncedAt: new Date(),
              isRemote: true,
            };
            nextFolderState = hydratedFolder;
            return hydratedFolder;
          });
          nextProjectState = { ...project, folders: updatedFolders };
          return nextProjectState;
        }),
      );

      if (nextProjectState) {
        setCurrentProject((prev) => (prev?.id === nextProjectState.id ? nextProjectState : prev ?? nextProjectState));
      }
      if (nextFolderState && currentFolder?.id === folderId) {
        setCurrentFolder(nextFolderState);
      }
    } catch (error) {
      console.error('[App] Failed to hydrate folder', error);
      showError('Unable to load folder details from the server.');
    } finally {
      setSyncingFolderId(null);
    }
  }, [currentFolder, showError]);

  const loadProjectsFromBackend = useCallback(async () => {
    setIsBootstrapping(true);
    setSyncError(null);
    try {
      const [projectsResponse, historyResponse] = await Promise.all([
        http.get(API_ENDPOINTS.projects),
        http.get(API_ENDPOINTS.history),
      ]);

      const remoteProjects = Array.isArray(projectsResponse.data?.groups)
        ? projectsResponse.data.groups.map((group: Record<string, any>) => mapProjectFromApi(group))
        : [];

      const batches = Array.isArray(historyResponse.data?.batches) ? historyResponse.data.batches : [];
      const { assignments, unattached } = partitionBatchesByProject(batches);

      const knownProjectIds = new Set(remoteProjects.map((project) => project.id));
      const merged: Project[] = remoteProjects.map((project) => ({
        ...project,
        folders: assignments.get(project.id) ?? [],
      }));

      assignments.forEach((folders, projectId) => {
        if (!knownProjectIds.has(projectId)) {
          merged.push({
            id: projectId,
            name: `Project ${projectId}`,
            folders,
          });
        }
      });

      if (unattached.length > 0) {
        merged.push({
          id: '__unassigned',
          name: 'Unassigned Uploads',
          folders: unattached,
        });
      }

      setProjects(merged);

      const nextProject = currentProject
        ? merged.find((project) => project.id === currentProject.id) ?? merged[0] ?? null
        : merged[0] ?? null;
      setCurrentProject(nextProject ?? null);

      const nextFolder =
        nextProject && currentFolder
          ? nextProject.folders.find((folder) => folder.id === currentFolder.id) ??
            nextProject.folders[0] ??
            null
          : nextProject?.folders[0] ?? null;
      setCurrentFolder(nextFolder ?? null);

      if (nextProject && nextFolder && nextFolder.isRemote && nextFolder.documents.length === 0) {
        void ensureFolderDocuments(nextProject.id, nextFolder.id);
      }
    } catch (error) {
      console.error('[App] Failed to load projects', error);
      setSyncError('Unable to load projects from the backend.');
      showError('Unable to load projects from the backend.');
    } finally {
      setIsBootstrapping(false);
    }
  }, [currentProject, currentFolder, ensureFolderDocuments, showError]);

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
  }, [projects, currentFolder, ensureFolderDocuments]);

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

  const handleUploadDocuments = useCallback((files: FileList) => {
    if (!currentProject || !currentFolder) return;

    if (currentFolder.isRemote) {
      void ensureFolderDocuments(currentProject.id, currentFolder.id);
      void loadProjectsFromBackend();
      return;
    }

    const newDocuments: Document[] = Array.from(files).map((file) => ({
      id: `doc-${Date.now()}-${Math.random()}`,
      name: file.name,
      size: file.size,
      uploadDate: new Date(),
      status: 'Not Scanned',
    }));

    let updatedProjectState: Project | null = null;
    let updatedFolderState: Folder | null = null;

    setProjects((prevProjects) =>
      prevProjects.map((project) => {
        if (project.id === currentProject.id) {
          const updatedFolders = project.folders.map((folder) => {
            if (folder.id === currentFolder.id) {
              updatedFolderState = { ...folder, documents: [...folder.documents, ...newDocuments] };
              return updatedFolderState;
            }
            return folder;
          });
          updatedProjectState = { ...project, folders: updatedFolders };
          return updatedProjectState;
        }
        return project;
      }),
    );

    if (updatedProjectState) setCurrentProject(updatedProjectState);
    if (updatedFolderState) setCurrentFolder(updatedFolderState);
  }, [currentProject, currentFolder, ensureFolderDocuments, loadProjectsFromBackend]);
  
  const handleScanFolder = useCallback(() => {
    if (!currentProject || !currentFolder) return;

    // Phase 1: Set status to 'Scanning' for unscanned docs
    let updatedProjectState: Project | null = null;
    let updatedFolderState: Folder | null = null;
    
    setProjects(prevProjects =>
      prevProjects.map(p => {
        if (p.id === currentProject.id) {
          const updatedFolders = p.folders.map(f => {
            if (f.id === currentFolder.id) {
              updatedFolderState = {
                ...f,
                documents: f.documents.map(doc =>
                  doc.status === 'Not Scanned' ? { ...doc, status: 'Scanning' } : doc
                ),
              };
              return updatedFolderState;
            }
            return f;
          });
          updatedProjectState = { ...p, folders: updatedFolders };
          return updatedProjectState;
        }
        return p;
      })
    );
    if (updatedProjectState) setCurrentProject(updatedProjectState);
    if (updatedFolderState) setCurrentFolder(updatedFolderState);
    
    // Phase 2: Simulate scan and set status to 'Scanned' with a report
    setTimeout(() => {
      let finalProjectState: Project | null = null;
      let finalFolderState: Folder | null = null;

      setProjects(prevProjects =>
        prevProjects.map(p => {
          if (p.id === currentProject.id) {
            const updatedFolders = p.folders.map(f => {
              if (f.id === currentFolder.id) {
                finalFolderState = {
                  ...f,
                  documents: f.documents.map(doc => {
                    if (doc.status === 'Scanning') {
                      // Mock report generation
                      const issueTypes = ['Missing Alt Text', 'Low Contrast', 'Empty Link', 'No Page Title', 'Untagged PDF'];
                      const severities: Issue['severity'][] = ['Critical', 'Serious', 'Moderate', 'Minor'];
                      const issues: Issue[] = [];
                      const issueCount = Math.floor(Math.random() * 5); // 0 to 4 issues
                      
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
                        score: Math.max(0, 100 - (issueCount * (Math.floor(Math.random() * 5) + 5))), // Simple scoring
                        issues,
                      };
                      return { ...doc, status: 'Scanned', accessibilityReport: report };
                    }
                    return doc;
                  }),
                };
                return finalFolderState;
              }
              return f;
            });
            finalProjectState = { ...p, folders: updatedFolders };
            return finalProjectState;
          }
          return p;
        })
      );
      if (finalProjectState) setCurrentProject(finalProjectState);
      if (finalFolderState) setCurrentFolder(finalFolderState);
    }, 2000); // Simulate a 2-second scan
  }, [currentProject, currentFolder]);

  const handleUpdateIssueStatus = useCallback((docId: string, issueId: string, status: 'Needs Attention' | 'Fixed') => {
    if (!currentProject || !currentFolder) return;

    let updatedProjectState: Project | null = null;
    let updatedFolderState: Folder | null = null;

    setProjects(prevProjects => 
        prevProjects.map(p => {
            if (p.id === currentProject.id) {
                const updatedFolders = p.folders.map(f => {
                    if (f.id === currentFolder.id) {
                        const updatedDocuments = f.documents.map(d => {
                            if (d.id === docId && d.accessibilityReport) {
                                const updatedIssues = d.accessibilityReport.issues.map(i => {
                                    if (i.id === issueId) {
                                        return { ...i, status };
                                    }
                                    return i;
                                });
                                return { ...d, accessibilityReport: { ...d.accessibilityReport, issues: updatedIssues } };
                            }
                            return d;
                        });
                        updatedFolderState = { ...f, documents: updatedDocuments };
                        return updatedFolderState;
                    }
                    return f;
                });
                updatedProjectState = { ...p, folders: updatedFolders };
                return updatedProjectState;
            }
            return p;
        })
    );

    if (updatedProjectState) setCurrentProject(updatedProjectState);
    if (updatedFolderState) setCurrentFolder(updatedFolderState);

  }, [currentProject, currentFolder]);

  const handleBulkUpdateIssueStatus = useCallback((updates: {docId: string, issueId: string, status: 'Needs Attention' | 'Fixed'}[]) => {
    if (!currentProject || !currentFolder || updates.length === 0) return;

    let updatedProjectState: Project | null = null;
    let updatedFolderState: Folder | null = null;
    
    const updatesMap = new Map<string, Map<string, 'Needs Attention' | 'Fixed'>>();
    updates.forEach(u => {
      if (!updatesMap.has(u.docId)) {
        updatesMap.set(u.docId, new Map());
      }
      updatesMap.get(u.docId)!.set(u.issueId, u.status);
    });

    setProjects(prevProjects => 
        prevProjects.map(p => {
            if (p.id === currentProject.id) {
                const updatedFolders = p.folders.map(f => {
                    if (f.id === currentFolder.id) {
                        const updatedDocuments = f.documents.map(d => {
                            const docUpdates = updatesMap.get(d.id);
                            if (docUpdates && d.accessibilityReport) {
                                const updatedIssues = d.accessibilityReport.issues.map(i => {
                                    if (docUpdates.has(i.id)) {
                                        return { ...i, status: docUpdates.get(i.id)! };
                                    }
                                    return i;
                                });
                                return { ...d, accessibilityReport: { ...d.accessibilityReport, issues: updatedIssues } };
                            }
                            return d;
                        });
                        updatedFolderState = { ...f, documents: updatedDocuments };
                        return updatedFolderState;
                    }
                    return f;
                });
                updatedProjectState = { ...p, folders: updatedFolders };
                return updatedProjectState;
            }
            return p;
        })
    );

    if (updatedProjectState) setCurrentProject(updatedProjectState);
    if (updatedFolderState) setCurrentFolder(updatedFolderState);

  }, [currentProject, currentFolder]);

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
