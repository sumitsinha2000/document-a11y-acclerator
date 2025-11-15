import { useState, useMemo } from 'react';
import type { FC } from 'react';
import { Project, Folder } from '../types';
import { FileIcon } from './icons/FileIcon';
import { SparklesIcon } from './icons/SparklesIcon';
import { WrenchIcon } from './icons/WrenchIcon';
import { SpinnerIcon } from './icons/SpinnerIcon';
import { RemediateView } from './RemediateView';
import UploadArea from './UploadArea';

interface DocumentsColumnProps {
  currentProject: Project | null;
  currentFolder: Folder | null;
  onUpload: (files: FileList) => void;
  onScanFolder: () => void;
  onUpdateIssueStatus: (docId: string, issueId: string, status: 'Needs Attention' | 'Fixed') => void;
  onBulkUpdateIssueStatus: (updates: {docId: string, issueId: string, status: 'Needs Attention' | 'Fixed'}[]) => void;
}

const DocumentsColumn: FC<DocumentsColumnProps> = ({ currentProject, currentFolder, onUpload, onScanFolder, onUpdateIssueStatus, onBulkUpdateIssueStatus }) => {
  const [view, setView] = useState<'list' | 'remediate'>('list');

  const folderStats = useMemo(() => {
    if (!currentFolder) return { hasUnscanned: false, isScanning: false, hasScanned: false };
    const hasUnscanned = currentFolder.documents.some(doc => doc.status === 'Not Scanned');
    const isScanning = currentFolder.documents.some(doc => doc.status === 'Scanning');
    const hasScanned = currentFolder.documents.some(doc => doc.status === 'Scanned');
    return { hasUnscanned, isScanning, hasScanned };
  }, [currentFolder]);

  if (!currentProject) {
    return (
       <div className="h-full bg-white rounded-lg border border-gray-200 p-4 flex items-center justify-center text-gray-500 text-sm">
        Select a project to get started.
      </div>
    );
  }

  if (!currentFolder) {
    return (
      <div className="h-full bg-white rounded-lg border border-gray-200 p-4 flex items-center justify-center text-gray-500 text-sm">
        Select or create a folder to manage documents.
      </div>
    );
  }
  
  if (view === 'remediate') {
    return <RemediateView folder={currentFolder} onBack={() => setView('list')} onUpdateIssueStatus={onUpdateIssueStatus} onBulkUpdateIssueStatus={onBulkUpdateIssueStatus} />
  }

  return (
    <div className="h-full bg-white rounded-lg border border-gray-200 p-4 flex flex-col space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h2 className="text-xl font-bold text-gray-800 tracking-tight truncate" title={`${currentProject.name} / ${currentFolder.name}`}>
            Documents in <span className="text-indigo-600">{currentFolder.name}</span>
        </h2>
        <div className="flex items-center gap-2">
           <button
            onClick={onScanFolder}
            disabled={!folderStats.hasUnscanned || folderStats.isScanning}
            className="flex items-center justify-center gap-2 bg-indigo-600 text-white font-semibold px-3 py-2 rounded-md hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition duration-200 text-sm"
          >
            {folderStats.isScanning ? <SpinnerIcon className="w-5 h-5"/> : <SparklesIcon className="w-5 h-5" />}
            <span>{folderStats.isScanning ? 'Scanning...' : 'Scan'}</span>
          </button>
          <button
            onClick={() => setView('remediate')}
            disabled={!folderStats.hasScanned}
            className="flex items-center justify-center gap-2 bg-gray-700 text-white font-semibold px-3 py-2 rounded-md hover:bg-gray-800 disabled:bg-gray-300 disabled:cursor-not-allowed transition duration-200 text-sm"
          >
            <WrenchIcon className="w-5 h-5" />
            <span>Remediate</span>
          </button>
        </div>
      </div>
      
      <UploadArea
        onUpload={onUpload}
        projectId={currentFolder.projectId ?? currentProject.id}
        projectName={currentProject.name}
      />
      
      <div className="flex-grow overflow-y-auto space-y-2 pr-1 -mr-1">
        {currentFolder.documents.length > 0 ? (
          <ul className="divide-y divide-gray-200">
            {currentFolder.documents
              .slice()
              .sort((a, b) => b.uploadDate.getTime() - a.uploadDate.getTime())
              .map(doc => (
              <li key={doc.id} className="py-3 flex items-center space-x-3">
                <FileIcon className="w-6 h-6 text-gray-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-gray-900 text-sm font-medium truncate">{doc.name}</p>
                  <p className="text-xs text-gray-500">
                    {doc.uploadDate.toLocaleDateString()}
                  </p>
                </div>
                <div className="flex-shrink-0 text-right w-28">
                  {doc.status === 'Not Scanned' && <span className="text-xs text-gray-500">Not Scanned</span>}
                  {doc.status === 'Scanning' && <div className="flex items-center justify-end gap-2"><SpinnerIcon className="w-4 h-4" /><span className="text-xs text-indigo-600">Scanning...</span></div>}
                  {doc.status === 'Scanned' && <span className="text-xs font-semibold text-green-600">Scanned</span>}
                </div>
                <div className="text-right text-xs flex-shrink-0 w-24">
                  {doc.status === 'Scanned' && doc.accessibilityReport != null ? (
                    <span className={`font-semibold ${
                      doc.accessibilityReport.issues.length > 0 ? 'text-red-600' : 'text-green-600'
                    }`}>
                      {doc.accessibilityReport.issues.length} {doc.accessibilityReport.issues.length === 1 ? 'issue' : 'issues'}
                    </span>
                  ) : (
                    <span className="text-gray-400">-</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-center py-12 text-gray-500 text-sm">
            <p>No documents yet. Upload one to get started.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default DocumentsColumn;
