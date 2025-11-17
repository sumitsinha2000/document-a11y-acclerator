import { Project, Document, Folder, AccessibilityReport, Issue } from '../types';

export const fallbackId = (prefix: string) => `${prefix}-${Date.now()}-${Math.round(Math.random() * 10000)}`;

export const mapProjectFromApi = (raw: Record<string, unknown>): Project => {
  const id = String(raw.id ?? raw.group_id ?? fallbackId('project'));
  const name = (raw.name as string) || (raw.group_name as string) || 'Untitled Project';
  return {
    id,
    name,
    folders: [],
  };
};

export const resolveDocumentStatus = (status?: string | null): Document['status'] => {
  if (!status) {
    return 'Not Scanned';
  }
  const normalized = status.toLowerCase();
  if (['uploaded', 'pending', 'unprocessed', 'draft'].includes(normalized)) {
    return 'Not Scanned';
  }
  if (['processing', 'scan_pending', 'scanning', 'running'].includes(normalized)) {
    return 'Scanning';
  }
  return 'Scanned';
};

export const toIssueSeverity = (value?: string): Issue['severity'] => {
  const normalized = value?.toLowerCase();
  if (normalized === 'critical') return 'Critical';
  if (normalized === 'serious' || normalized === 'high') return 'Serious';
  if (normalized === 'moderate' || normalized === 'medium') return 'Moderate';
  return 'Minor';
};

export const flattenIssuesFromResults = (results: unknown, folderId: string, docId: string): Issue[] => {
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

export const mapScanToDocument = (scan: Record<string, any>, folderId: string): Document => {
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

export const mapFolderDocumentEntry = (entry: Record<string, any>, folderId: string): Document => {
  if (entry.summary || entry.issues) {
    const docId = String(entry.id ?? fallbackId('doc'));
    const issues = Array.isArray(entry.issues)
      ? entry.issues.map((issue: Record<string, any>, index: number) => ({
          id: String(issue.id ?? `${docId}-issue-${index}`),
          type: String(issue.type ?? 'Issue'),
          description: String(issue.description ?? 'Accessibility issue detected.'),
          location: String(issue.location ?? 'Unknown location'),
          status: (issue.status === 'Fixed' ? 'Fixed' : 'Needs Attention') as Issue['status'],
          severity: toIssueSeverity(issue.severity as string),
        }))
      : [];
    const scoreSource =
      entry.summary?.complianceScore ?? entry.summary?.score ?? (issues.length ? Math.max(0, 100 - issues.length * 5) : 0);
    return {
      id: docId,
      name: entry.name ?? entry.filename ?? 'Document',
      size: Number(entry.size ?? entry.fileSize ?? 0),
      uploadDate: entry.uploadDate ? new Date(entry.uploadDate) : new Date(),
      status: resolveDocumentStatus(entry.status),
      accessibilityReport: issues.length
        ? {
            score: Math.round(Number(scoreSource) || 0),
            issues,
          }
        : undefined,
    };
  }
  return mapScanToDocument(entry, folderId);
};

export const mapBatchToFolder = (batch: Record<string, any>): Folder => {
  const folderId = String(batch.folderId ?? batch.batchId ?? batch.id ?? fallbackId('folder'));
  const timestamp = batch.uploadDate ?? batch.createdAt;
  const readableDate = timestamp ? new Date(timestamp).toLocaleString() : '';
  return {
    id: folderId,
    name: batch.name || `Folder ${readableDate || folderId}`,
    documents: [],
    projectId: batch.projectId ?? batch.groupId ?? batch.group_id ?? undefined,
    isRemote: true,
    lastSyncedAt: null,
  };
};

export const partitionBatchesByProject = (batches: Array<Record<string, any>>) => {
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

export const mergeFoldersWithExisting = (incoming: Folder[], existing: Map<string, Folder>): Folder[] =>
  incoming.map((folder) => {
    const stored = existing.get(folder.id);
    if (!stored) {
      return folder;
    }
    const combinedDocuments = folder.documents.length > 0 ? folder.documents : stored.documents;
    return {
      ...folder,
      documents: combinedDocuments,
      lastSyncedAt: folder.lastSyncedAt ?? stored.lastSyncedAt,
      isRemote: folder.isRemote ?? stored.isRemote,
    };
  });

export const mergeProjectsWithAssignments = (
  baseProjects: Project[],
  assignments: Map<string, Folder[]>,
  unattached: Folder[],
): Project[] => {
  const folderLookup = new Map<string, Folder>();
  baseProjects.forEach((project) => {
    project.folders.forEach((folder) => folderLookup.set(folder.id, folder));
  });

  const cleaned = baseProjects.filter((project) => project.id !== '__unassigned');

  const updatedProjects = cleaned.map((project) => {
    const assigned = assignments.get(project.id);
    if (!assigned) {
      return project;
    }
    return {
      ...project,
      folders: mergeFoldersWithExisting(assigned, folderLookup),
    };
  });

  const knownIds = new Set(updatedProjects.map((project) => project.id));
  assignments.forEach((folders, projectId) => {
    if (knownIds.has(projectId)) return;
    knownIds.add(projectId);
    updatedProjects.push({
      id: projectId,
      name: `Project ${projectId}`,
      folders: mergeFoldersWithExisting(folders, folderLookup),
    });
  });

  if (unattached.length > 0) {
    updatedProjects.push({
      id: '__unassigned',
      name: 'Unassigned Uploads',
      folders: mergeFoldersWithExisting(unattached, folderLookup),
    });
  }

  return updatedProjects;
};

export type SerializedDocument = Omit<Document, 'uploadDate'> & { uploadDate: string };

export interface CachedFolderDetails {
  documents: SerializedDocument[];
  folderName?: string;
  fetchedAt: number;
}

const FOLDER_CACHE_KEY = 'document-a11y-folder-cache';

export const serializeDocuments = (documents: Document[]): SerializedDocument[] =>
  documents.map((doc) => ({
    ...doc,
    uploadDate: doc.uploadDate.toISOString(),
  }));

export const deserializeDocuments = (records: SerializedDocument[]): Document[] =>
  records.map((record) => ({
    ...record,
    uploadDate: new Date(record.uploadDate),
  }));

export const readFolderCacheFromStorage = (): Record<string, CachedFolderDetails> => {
  if (typeof window === 'undefined') return {};
  const serialized = window.localStorage.getItem(FOLDER_CACHE_KEY);
  if (!serialized) return {};
  try {
    const parsed = JSON.parse(serialized ?? '{}');
    if (parsed && typeof parsed === 'object') {
      return parsed;
    }
  } catch {
    window.localStorage.removeItem(FOLDER_CACHE_KEY);
  }
  return {};
};

export const persistFolderCache = (cache: Record<string, CachedFolderDetails>) => {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(FOLDER_CACHE_KEY, JSON.stringify(cache));
  } catch {
    // best effort
  }
};
