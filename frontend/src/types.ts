export interface Issue {
  id: string;
  type: string;
  description: string;
  location: string;
  status: 'Needs Attention' | 'Fixed';
  severity: 'Critical' | 'Serious' | 'Moderate' | 'Minor';
}

export interface AccessibilityReport {
  score: number; // 0-100
  issues: Issue[];
}

export interface Document {
  id: string;
  name: string;
  size: number; // in bytes
  uploadDate: Date;
  status: 'Not Scanned' | 'Scanning' | 'Scanned';
  accessibilityReport?: AccessibilityReport;
}

export interface Folder {
  id: string;
  name: string;
  documents: Document[];
  projectId?: string;
  isRemote?: boolean;
  lastSyncedAt?: Date | null;
}

export interface Project {
  id: string;
  name: string;
  folders: Folder[];
  folderCount?: number;
}
