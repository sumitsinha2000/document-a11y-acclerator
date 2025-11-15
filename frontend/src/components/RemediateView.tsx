import { useMemo, useState, useEffect } from 'react';
import type { FC, ReactNode } from 'react';
import { Folder, Issue } from '../types';
import http from '../lib/http';
import { API_ENDPOINTS } from '../config/api';
import { useNotification } from '../contexts/NotificationContext';
import { ArrowLeftIcon } from './icons/ArrowLeftIcon';
import { FileIcon } from './icons/FileIcon';
import { AcademicCapIcon } from './icons/AcademicCapIcon';
import { ExclamationTriangleIcon } from './icons/ExclamationTriangleIcon';
import { BugAntIcon } from './icons/BugAntIcon';
import { DocumentArrowDownIcon } from './icons/DocumentArrowDownIcon';
import { MagicWandIcon } from './icons/MagicWandIcon';
import { SpinnerIcon } from './icons/SpinnerIcon';

interface RemediateViewProps {
  folder: Folder;
  onBack: () => void;
  onUpdateIssueStatus: (docId: string, issueId: string, status: 'Needs Attention' | 'Fixed') => void;
  onBulkUpdateIssueStatus: (updates: {docId: string, issueId: string, status: 'Needs Attention' | 'Fixed'}[]) => void;
}

interface IssueWithDoc extends Issue {
  docName: string;
  docId: string;
}

const severityConfig: Record<Issue['severity'], { color: string, badgeColor: string }> = {
  Critical: { color: 'text-red-700', badgeColor: 'bg-red-100' },
  Serious: { color: 'text-orange-700', badgeColor: 'bg-orange-100' },
  Moderate: { color: 'text-yellow-700', badgeColor: 'bg-yellow-100' },
  Minor: { color: 'text-gray-700', badgeColor: 'bg-gray-100' },
};

const allSeverities: Issue['severity'][] = ['Critical', 'Serious', 'Moderate', 'Minor'];
const allStatuses: Issue['status'][] = ['Needs Attention', 'Fixed'];

export const RemediateView: FC<RemediateViewProps> = ({ folder, onBack, onUpdateIssueStatus, onBulkUpdateIssueStatus }) => {
  const { showError } = useNotification();
  const [folderData, setFolderData] = useState<Folder>(folder);
  const [isLoadingRemote, setIsLoadingRemote] = useState(false);

  const deriveIssueSeverity = (value?: string): Issue['severity'] => {
    const normalized = value?.toLowerCase();
    if (normalized === 'critical') return 'Critical';
    if (normalized === 'serious' || normalized === 'high') return 'Serious';
    if (normalized === 'moderate' || normalized === 'medium') return 'Moderate';
    return 'Minor';
  };

  const adaptRemoteDocument = (doc: Record<string, any>): Folder['documents'][number] => {
    const docId = String(doc.id ?? doc.scanId ?? `${folder.id}-${Math.random()}`);
    const issues = Array.isArray(doc.issues)
      ? doc.issues.map((issue: Record<string, any>, index: number) => ({
          id: String(issue.id ?? `${docId}-issue-${index}`),
          type: String(issue.type ?? 'Issue'),
          description: String(issue.description ?? 'Accessibility issue detected.'),
          location: String(issue.location ?? 'Unknown location'),
          status: (issue.status === 'Fixed' ? 'Fixed' : 'Needs Attention') as Issue['status'],
          severity: deriveIssueSeverity(issue.severity as string),
        }))
      : [];
    const scoreValue =
      typeof doc.summary?.complianceScore === 'number'
        ? doc.summary.complianceScore
        : typeof doc.summary?.score === 'number'
          ? doc.summary.score
          : issues.length
            ? Math.max(0, 100 - issues.length * 5)
            : 0;
    const rawStatus = (doc.status || '').toLowerCase();
    const status: Folder['documents'][number]['status'] =
      rawStatus === 'scanned'
        ? 'Scanned'
        : rawStatus === 'processing' || rawStatus === 'scanning'
          ? 'Scanning'
          : 'Not Scanned';
    return {
      id: docId,
      name: doc.name ?? doc.filename ?? 'Document',
      size: Number(doc.size ?? doc.fileSize ?? 0),
      uploadDate: doc.uploadDate ? new Date(doc.uploadDate) : new Date(),
      status,
      accessibilityReport: issues.length ? { score: Math.round(scoreValue), issues } : undefined,
    };
  };

  useEffect(() => {
    let cancelled = false;
    if (!folder.isRemote) {
      setFolderData(folder);
      return;
    }
    setIsLoadingRemote(true);
    http
      .get(API_ENDPOINTS.folderRemediation(folder.id))
      .then((response) => {
        if (cancelled) return;
        const remoteDocs = Array.isArray(response.data?.documents) ? response.data.documents : [];
        const adaptedDocs = remoteDocs.map((doc: Record<string, any>) => adaptRemoteDocument(doc));
        setFolderData({
          ...folder,
          name: response.data?.folder?.name ?? folder.name,
          documents: adaptedDocs,
        });
      })
      .catch((error) => {
        if (cancelled) return;
        console.error('[RemediateView] Failed to load remediation data', error);
        showError('Failed to load remediation data for this folder.');
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingRemote(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [folder, showError]);

  const workingFolder = folder.isRemote ? folderData : folder;

  const allScannedDocs = useMemo(
    () => workingFolder.documents.filter((d) => d.status === 'Scanned' && d.accessibilityReport),
    [workingFolder.documents],
  );

  const allIssues = useMemo(() => {
    const issues: IssueWithDoc[] = [];
    allScannedDocs.forEach(doc => {
      if (doc.accessibilityReport?.issues) {
        doc.accessibilityReport.issues.forEach(issue => {
          issues.push({ ...issue, docName: doc.name, docId: doc.id });
        });
      }
    });
    return issues;
  }, [allScannedDocs]);

  const allIssueTypes = useMemo(() => {
    const types = new Set(allIssues.map(issue => issue.type));
    return Array.from(types).sort();
  }, [allIssues]);

  const [selectedIssueTypes, setSelectedIssueTypes] = useState<Set<string>>(new Set());
  const [selectedSeverities, setSelectedSeverities] = useState<Set<string>>(new Set(allSeverities));
  const [selectedStatuses, setSelectedStatuses] = useState<Set<string>>(new Set(allStatuses));
  const [isAutoFixing, setIsAutoFixing] = useState(false);

  // Initialize filters to all selected when the component loads or issue types change
  useEffect(() => {
    setSelectedIssueTypes(new Set(allIssueTypes));
    setSelectedSeverities(new Set(allSeverities));
    setSelectedStatuses(new Set(allStatuses));
  }, [allIssueTypes]);


  const filteredIssues = useMemo(() => {
    return allIssues.filter(issue => 
      selectedIssueTypes.has(issue.type) &&
      selectedSeverities.has(issue.severity) &&
      selectedStatuses.has(issue.status)
    );
  }, [allIssues, selectedIssueTypes, selectedSeverities, selectedStatuses]);

  const groupedIssues = useMemo(() => {
    return filteredIssues.reduce((acc, issue) => {
      if (!acc[issue.type]) {
        acc[issue.type] = [];
      }
      acc[issue.type].push(issue);
      return acc;
    }, {} as Record<string, IssueWithDoc[]>);
  }, [filteredIssues]);

  const sortedIssueTypes = Object.keys(groupedIssues).sort((a, b) => groupedIssues[b].length - groupedIssues[a].length);


  const dashboardStats = useMemo(() => {
    if (allScannedDocs.length === 0) {
      return { avgScore: 0, totalIssues: 0, openIssues: 0, topFailures: [] };
    }

    const totalScore = allScannedDocs.reduce((acc, doc) => acc + (doc.accessibilityReport?.score ?? 0), 0);
    const avgScore = Math.round(totalScore / allScannedDocs.length);
    
    const totalIssues = allIssues.length;
    const openIssues = allIssues.filter(i => i.status === 'Needs Attention').length;

    const failureCounts = allIssues.filter(i => i.status === 'Needs Attention').reduce((acc, issue) => {
      acc[issue.type] = (acc[issue.type] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    const topFailures = Object.entries(failureCounts)
      .sort((a: [string, number], b: [string, number]) => b[1] - a[1])
      .slice(0, 3)
      .map(([type, count]) => ({ type, count }));

    return { avgScore, totalIssues, openIssues, topFailures };
  }, [allScannedDocs, allIssues]);


  const handleIssueTypeFilterChange = (issueType: string) => {
    setSelectedIssueTypes(prev => {
      const newSet = new Set(prev);
      if (newSet.has(issueType)) {
        newSet.delete(issueType);
      } else {
        newSet.add(issueType);
      }
      return newSet;
    });
  };

  const handleSeverityFilterChange = (severity: string) => {
    setSelectedSeverities(prev => {
      const newSet = new Set(prev);
      if (newSet.has(severity)) {
        newSet.delete(severity);
      } else {
        newSet.add(severity);
      }
      return newSet;
    });
  };

  const handleStatusFilterChange = (status: string) => {
    setSelectedStatuses(prev => {
      const newSet = new Set(prev);
      if (newSet.has(status)) {
        newSet.delete(status);
      } else {
        newSet.add(status);
      }
      return newSet;
    });
  };
  
  const handleDownloadReport = () => {
    let reportContent = `Accessibility Remediation Report\n`;
    reportContent += `===================================\n\n`;
    reportContent += `Folder: ${workingFolder.name}\n`;
    reportContent += `Date: ${new Date().toLocaleString()}\n\n`;

    reportContent += `--- Summary ---\n`;
    reportContent += `Average Score: ${dashboardStats.avgScore}%\n`;
    reportContent += `Total Issues Found (in current filter): ${filteredIssues.length}\n\n`;
    reportContent += `===================================\n\n`;

    if (sortedIssueTypes.length > 0) {
        reportContent += `DETAILS (Filtered View):\n\n`;
        sortedIssueTypes.forEach(issueType => {
            reportContent += `Issue Type: ${issueType} (${groupedIssues[issueType].length} found)\n`;
            reportContent += `------------------------------------------\n`;
            groupedIssues[issueType].forEach((issue, index) => {
                reportContent += `  ${index + 1}. [${issue.status.toUpperCase()}] [${issue.severity.toUpperCase()}] ${issue.description}\n`;
                reportContent += `     Document: ${issue.docName}\n`;
                reportContent += `     Location: ${issue.location}\n\n`;
            });
        });
    } else {
        reportContent += `No issues found with the current filters.\n`;
    }

    const blob = new Blob([reportContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const safeFolderName = workingFolder.name.replace(/[^a-z0-9]/gi, '_').toLowerCase();
    link.download = `${safeFolderName}_accessibility_report.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleAutoFix = () => {
    const issuesToFix = filteredIssues.filter(i => i.status === 'Needs Attention');
    if(issuesToFix.length === 0) return;

    setIsAutoFixing(true);

    setTimeout(() => {
      // Simulate fixing about 70% of the issues
      const updates = issuesToFix
        .filter(() => Math.random() < 0.7)
        .map(issue => ({
          docId: issue.docId,
          issueId: issue.id,
          status: 'Fixed' as const,
        }));
      
      onBulkUpdateIssueStatus(updates);
      setIsAutoFixing(false);
    }, 2500);
  };

  const openFilteredIssuesCount = useMemo(() => {
    return filteredIssues.filter(i => i.status === 'Needs Attention').length;
  }, [filteredIssues]);

  return (
    <div className="h-full bg-white rounded-lg border border-gray-200 p-4 flex flex-col space-y-4">
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 border-b border-gray-200 pb-4">
        <div className="flex items-center gap-4">
            <button onClick={onBack} className="p-2 rounded-md hover:bg-gray-100 transition-colors">
                <ArrowLeftIcon className="w-5 h-5 text-gray-700" />
            </button>
            <h2 className="text-xl font-bold text-gray-800 tracking-tight">
          Remediation for <span className="text-indigo-600">{workingFolder.name}</span>
            </h2>
        </div>
        <div className="flex items-center gap-2">
            <button
                onClick={handleAutoFix}
                disabled={isAutoFixing || openFilteredIssuesCount === 0}
                className="flex items-center justify-center gap-2 bg-indigo-600 text-white font-semibold px-3 py-2 rounded-md hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition duration-200 text-sm"
            >
                {isAutoFixing ? <SpinnerIcon className="w-5 h-5" /> : <MagicWandIcon className="w-5 h-5" />}
                <span>{isAutoFixing ? 'Fixing...' : 'Auto-Fix'}</span>
            </button>
            <button
            onClick={handleDownloadReport}
            disabled={allIssues.length === 0 || isAutoFixing}
            className="flex items-center justify-center gap-2 bg-white text-gray-700 font-semibold px-3 py-2 rounded-md hover:bg-gray-100 border border-gray-300 transition duration-200 text-sm disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed"
            >
            <DocumentArrowDownIcon className="w-5 h-5" />
            <span>Download Report</span>
            </button>
        </div>
      </div>

      {folder.isRemote && isLoadingRemote && (
        <div className="flex items-center gap-2 rounded-md border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs text-indigo-700">
          <SpinnerIcon className="h-4 w-4 animate-spin" />
          <span>Refreshing remediation data for this folder…</span>
        </div>
      )}

      {/* Dashboard Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <DashboardCard icon={<AcademicCapIcon className="w-6 h-6 text-indigo-500"/>} title="Average Score" value={`${dashboardStats.avgScore}%`} />
        <DashboardCard icon={<ExclamationTriangleIcon className="w-6 h-6 text-red-500"/>} title="Open Issues" value={dashboardStats.openIssues.toString()} />
        <DashboardCard icon={<BugAntIcon className="w-6 h-6 text-yellow-600"/>} title="Common Failures" value={
          dashboardStats.topFailures.length > 0 ? (
            <ul className="text-xs space-y-1">
              {dashboardStats.topFailures.map(f => <li key={f.type} className="truncate"><strong>{f.count}x</strong> {f.type}</li>)}
            </ul>
          ) : 'None'
        } />
      </div>

      {allIssueTypes.length === 0 ? (
        <div className="flex-grow flex items-center justify-center">
            <p className="text-gray-500">No issues found in the scanned documents of this folder.</p>
        </div>
      ) : (
        <>
          {/* Filters Section */}
          <div className="border-t border-b border-gray-200 py-3 divide-y divide-gray-200">
              <div className="pb-3">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold text-gray-700">Filter by Issue Type</h3>
                  <div className="flex items-center gap-2">
                      <button onClick={() => setSelectedIssueTypes(new Set(allIssueTypes))} className="text-xs font-semibold text-indigo-600 hover:underline">Select All</button>
                      <span className="text-gray-300">|</span>
                      <button onClick={() => setSelectedIssueTypes(new Set())} className="text-xs font-semibold text-indigo-600 hover:underline">Deselect All</button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    {allIssueTypes.map(type => (
                        <label key={type} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer p-1.5 rounded-md hover:bg-gray-100 transition-colors">
                            <input 
                                type="checkbox" 
                                checked={selectedIssueTypes.has(type)}
                                onChange={() => handleIssueTypeFilterChange(type)}
                                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                            />
                            {type}
                        </label>
                    ))}
                </div>
              </div>
              <div className="py-3">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold text-gray-700">Filter by Status</h3>
                  <div className="flex items-center gap-2">
                      <button onClick={() => setSelectedStatuses(new Set(allStatuses))} className="text-xs font-semibold text-indigo-600 hover:underline">Select All</button>
                      <span className="text-gray-300">|</span>
                      <button onClick={() => setSelectedStatuses(new Set())} className="text-xs font-semibold text-indigo-600 hover:underline">Deselect All</button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    {allStatuses.map(status => (
                        <label key={status} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer p-1.5 rounded-md hover:bg-gray-100 transition-colors">
                            <input 
                                type="checkbox" 
                                checked={selectedStatuses.has(status)}
                                onChange={() => handleStatusFilterChange(status)}
                                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                            />
                            {status}
                        </label>
                    ))}
                </div>
              </div>
              <div className="pt-3">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold text-gray-700">Filter by Severity</h3>
                  <div className="flex items-center gap-2">
                      <button onClick={() => setSelectedSeverities(new Set(allSeverities))} className="text-xs font-semibold text-indigo-600 hover:underline">Select All</button>
                      <span className="text-gray-300">|</span>
                      <button onClick={() => setSelectedSeverities(new Set())} className="text-xs font-semibold text-indigo-600 hover:underline">Deselect All</button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    {allSeverities.map(severity => (
                        <label key={severity} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer p-1.5 rounded-md hover:bg-gray-100 transition-colors">
                            <input 
                                type="checkbox" 
                                checked={selectedSeverities.has(severity)}
                                onChange={() => handleSeverityFilterChange(severity)}
                                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                            />
                            {severity}
                        </label>
                    ))}
                </div>
              </div>
          </div>
          {/* Issues List */}
          <div className="flex-grow overflow-y-auto pr-2 -mr-2 space-y-6">
              {sortedIssueTypes.length > 0 ? sortedIssueTypes.map(issueType => (
                  <div key={issueType}>
                      <div className="flex items-baseline gap-3 mb-2">
                          <h3 className="text-lg font-semibold text-gray-800">{issueType}</h3>
                          <span className="text-sm font-medium text-white bg-red-500 rounded-full px-2 py-0.5">
                              {groupedIssues[issueType].length}
                          </span>
                      </div>
                      <ul className="space-y-2 border-l-2 border-gray-200 pl-4 ml-1">
                          {groupedIssues[issueType].map(issue => (
                              <li key={issue.id} className="bg-gray-50 p-3 rounded-md border border-gray-200">
                                <div className="flex items-start justify-between">
                                  <div className="flex-1 min-w-0 pr-4">
                                    <p className="text-sm text-gray-700 font-medium">{issue.description}</p>
                                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full font-medium ${severityConfig[issue.severity].badgeColor} ${severityConfig[issue.severity].color}`}>
                                          {issue.severity}
                                        </span>
                                        <div className="flex items-center gap-1.5">
                                            <FileIcon className="w-4 h-4" />
                                            <span className="truncate">{issue.docName}</span>
                                        </div>
                                        <span className="font-semibold">{issue.location}</span>
                                    </div>
                                  </div>
                                  <div className="flex-shrink-0">
                                    <span className="isolate inline-flex rounded-md shadow-sm">
                                      <button
                                        type="button"
                                        onClick={() => onUpdateIssueStatus(issue.docId, issue.id, 'Needs Attention')}
                                        className={`relative inline-flex items-center rounded-l-md px-2 py-1 text-xs font-semibold ring-1 ring-inset ring-gray-300 focus:z-10 transition-colors ${
                                            issue.status === 'Needs Attention' ? 'bg-red-100 text-red-700 ring-red-200' : 'bg-white text-gray-700 hover:bg-gray-50'
                                        }`}
                                        aria-pressed={issue.status === 'Needs Attention'}
                                      >
                                        Needs Attention
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => onUpdateIssueStatus(issue.docId, issue.id, 'Fixed')}
                                        className={`relative -ml-px inline-flex items-center rounded-r-md px-2 py-1 text-xs font-semibold ring-1 ring-inset ring-gray-300 focus:z-10 transition-colors ${
                                            issue.status === 'Fixed' ? 'bg-green-100 text-green-700 ring-green-200' : 'bg-white text-gray-700 hover:bg-gray-50'
                                        }`}
                                        aria-pressed={issue.status === 'Fixed'}
                                      >
                                        Fixed
                                      </button>
                                    </span>
                                  </div>
                                </div>
                              </li>
                          ))}
                      </ul>
                  </div>
              )) : (
                <div className="text-center py-12 text-gray-500 text-sm">
                  <p>No issues match your current filters.</p>
                </div>
              )}
          </div>
        </>
      )}
    </div>
  );
};


const DashboardCard: FC<{ icon: ReactNode; title: string; value: string | ReactNode }> = ({ icon, title, value }) => (
  <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 flex items-start gap-4">
    <div className="bg-white p-2 rounded-md border border-gray-200">
      {icon}
    </div>
    <div>
      <h4 className="text-sm font-medium text-gray-500">{title}</h4>
      <div className="text-xl font-bold text-gray-800">{value}</div>
    </div>
  </div>
);
