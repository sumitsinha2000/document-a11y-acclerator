import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChangeEvent, DragEvent, FC, KeyboardEvent } from 'react';
import { API_ENDPOINTS } from '../config/api';
import { useNotification } from '../contexts/NotificationContext';
import http from '../lib/http';
import { UploadIcon } from './icons/UploadIcon';
import { SparklesIcon } from './icons/SparklesIcon';
import { SpinnerIcon } from './icons/SpinnerIcon';

type ScanMode = 'scan-now' | 'upload-only';

interface UploadTracker {
  id: string;
  fileName: string;
  status: 'queued' | 'uploading' | 'processing' | 'completed' | 'error';
  progress: number;
  message?: string;
}

interface ProjectOption {
  id: string;
  name: string;
}

interface UploadAreaProps {
  onUpload: (files: FileList) => void;
}

interface ProjectsResponse {
  projects?: Array<{ id?: string; name?: string; group_id?: string; group_name?: string }>;
}

const UploadArea: FC<UploadAreaProps> = ({ onUpload }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { showError, showSuccess, showInfo } = useNotification();

  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [scanMode, setScanMode] = useState<ScanMode>('scan-now');
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [uploadItems, setUploadItems] = useState<UploadTracker[]>([]);
  const [srAnnouncement, setSrAnnouncement] = useState('');

  const fetchProjects = useCallback(async () => {
    try {
      const response = await http.get<ProjectsResponse>(API_ENDPOINTS.projects);
      const payload = response.data?.projects ?? response.data?.groups ?? [];
      const parsed = payload
        .map((group) => {
          const id = group.id || group.group_id;
          const name = group.name || group.group_name || id;
          if (!id || !name) return null;
          return { id, name };
        })
        .filter((item): item is ProjectOption => Boolean(item));
      setProjects(parsed);
    } catch (error) {
      console.error('[UploadArea] Failed to load projects', error);
      showError('Could not load projects. Continue by typing a project ID manually.');
    }
  }, [showError]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const announce = (message: string) => {
    setSrAnnouncement(message);
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    if (event.currentTarget.contains(event.relatedTarget as Node)) {
      return;
    }
    setIsDragging(false);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    if (event.dataTransfer.files?.length) {
      handleFileSelection(event.dataTransfer.files);
    }
  };

  const handleBrowseClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files?.length) {
      handleFileSelection(event.target.files);
      event.target.value = '';
    }
  };

  const buildFileList = (file: File) => {
    if (typeof DataTransfer === 'undefined') {
      return null;
    }
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    return dataTransfer.files;
  };

  const uploadSingleFile = async (file: File, trackerId: string) => {
    const endpoint = scanMode === 'upload-only' ? API_ENDPOINTS.upload : API_ENDPOINTS.scan;
    const formData = new FormData();
    formData.append('file', file);
    const trimmedProjectId = selectedProjectId.trim();
    if (trimmedProjectId) {
      formData.append('project_id', trimmedProjectId);
      formData.append('group_id', trimmedProjectId);
    }
    if (scanMode === 'scan-now') {
      formData.append('scan_mode', 'scan_now');
    }
    try {
      setUploadItems((prev) =>
        prev.map((item) =>
          item.id === trackerId ? { ...item, status: 'uploading', message: undefined } : item,
        ),
      );

      const response = await http.post(endpoint, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (event) => {
          if (!event.total) return;
          const percent = Math.round((event.loaded * 100) / event.total);
          setUploadItems((prev) =>
            prev.map((item) =>
              item.id === trackerId ? { ...item, progress: percent } : item,
            ),
          );
        },
      });

      setUploadItems((prev) =>
        prev.map((item) =>
          item.id === trackerId
            ? {
                ...item,
                status: scanMode === 'upload-only' ? 'completed' : 'processing',
                progress: 100,
              }
            : item,
        ),
      );

      const successMessage =
        scanMode === 'upload-only'
          ? `${file.name} uploaded successfully.`
          : `${file.name} uploaded. Scan started.`;
      showSuccess(successMessage);
      announce(successMessage);

      const filesForParent = buildFileList(file);
      if (filesForParent) {
        onUpload(filesForParent);
      }

      setUploadItems((prev) =>
        prev.map((item) =>
          item.id === trackerId
            ? {
                ...item,
                status: 'completed',
                message:
                  scanMode === 'upload-only'
                    ? 'Ready for manual scan later.'
                    : 'Scan initiated.',
              }
            : item,
        ),
      );

      return response.data;
    } catch (error: unknown) {
      console.error('[UploadArea] Upload failed', error);
      const errorMessage =
        (error as { response?: { data?: { error?: string }; status?: number }; message?: string }).response?.data
          ?.error || (error as { message?: string }).message || 'Upload failed.';
      setUploadItems((prev) =>
        prev.map((item) =>
          item.id === trackerId
            ? { ...item, status: 'error', message: errorMessage, progress: 0 }
            : item,
        ),
      );
      showError(errorMessage);
      announce(`Upload failed for ${file.name}`);
      throw error;
    }
  };

  const processSequentialUploads = async (files: File[]) => {
    setIsUploading(true);
    for (const file of files) {
      const trackerId = `${file.name}-${Date.now()}-${Math.random()}`;
      setUploadItems((prev) => [
        ...prev,
        { id: trackerId, fileName: file.name, status: 'queued', progress: 0 },
      ]);
      try {
        await uploadSingleFile(file, trackerId);
      } catch {
        // Error already handled per file; continue to the next one.
      }
    }
    setIsUploading(false);
  };

  const handleFileSelection = (fileList: FileList | File[]) => {
    const files = Array.from(fileList);
    if (!files.length) return;

    const pdfFiles = files.filter((file) => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'));
    const rejected = files.length - pdfFiles.length;

    if (pdfFiles.length === 0) {
      showError('Please select at least one PDF file.');
      announce('Upload failed. Only PDF files are allowed.');
      return;
    }

    if (!selectedProjectId.trim()) {
      showError('Please enter a project ID before uploading.');
      announce('Project selection required.');
      return;
    }

    if (rejected > 0) {
      showInfo(`${rejected} non-PDF file(s) were ignored.`);
    }

    announce(`Uploading ${pdfFiles.length} file${pdfFiles.length > 1 ? 's' : ''}.`);
    void processSequentialUploads(pdfFiles);
  };

  const removeUploadItem = (id: string) => {
    setUploadItems((prev) => prev.filter((item) => item.id !== id));
  };

  return (
    <section aria-label="Upload documents" className="rounded-lg border border-gray-200 bg-gray-50/50 p-4">
      <div className="sr-only" role="status" aria-live="polite">
        {srAnnouncement}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="space-y-4">
          <div>
            <label htmlFor="project-input" className="text-sm font-semibold text-gray-700">
              Project ID
            </label>
            <input
              id="project-input"
              type="text"
              className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="Enter or select a project"
              list="project-suggestions"
              value={selectedProjectId}
              onChange={(event) => setSelectedProjectId(event.target.value)}
            />
            <datalist id="project-suggestions">
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </datalist>
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-700">Scan Mode</p>
            <div className="mt-2 flex items-center gap-2">
              <button
                type="button"
                className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium transition ${scanMode === 'scan-now' ? 'border-indigo-500 bg-indigo-50 text-indigo-600' : 'border-gray-300 bg-white text-gray-600 hover:border-gray-400'}`}
                onClick={() => setScanMode('scan-now')}
              >
                <span className="flex items-center justify-center gap-2">
                  <SparklesIcon className="h-4 w-4" />
                  Scan Now
                </span>
              </button>
              <button
                type="button"
                className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium transition ${scanMode === 'upload-only' ? 'border-indigo-500 bg-indigo-50 text-indigo-600' : 'border-gray-300 bg-white text-gray-600 hover:border-gray-400'}`}
                onClick={() => setScanMode('upload-only')}
              >
                Upload Only
              </button>
            </div>
          </div>
          <button
            type="button"
            onClick={fetchProjects}
            className="text-left text-xs font-medium text-indigo-600 hover:text-indigo-700"
          >
            Refresh projects
          </button>
        </div>

        <div
          className={`md:col-span-2 rounded-lg border-2 border-dashed bg-white p-6 text-center transition ${isDragging ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-indigo-400'}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={handleBrowseClick}
          role="button"
          tabIndex={0}
          onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              handleBrowseClick();
            }
          }}
          aria-disabled={isUploading}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            multiple
            className="hidden"
            onChange={handleFileInput}
            aria-hidden="true"
          />
          <div className="pointer-events-none flex flex-col items-center gap-2">
            <UploadIcon className="h-10 w-10 text-gray-400" />
            <p className="text-sm font-semibold text-gray-700">
              Drag & drop PDF files or <span className="text-indigo-600">browse</span>
            </p>
            <p className="text-xs text-gray-500">
              Files will be {scanMode === 'scan-now' ? 'uploaded and scanned immediately' : 'uploaded for later scanning'}.
            </p>
          </div>
        </div>
      </div>

      {uploadItems.length > 0 && (
        <div className="mt-4 space-y-2" aria-live="polite">
          {uploadItems.map((item) => (
            <div
              key={item.id}
              className="rounded-md border border-gray-200 bg-white p-3 text-sm text-gray-700 shadow-sm"
            >
              <div className="flex items-center justify-between">
                <p className="font-medium truncate" title={item.fileName}>
                  {item.fileName}
                </p>
                <button
                  type="button"
                  className="text-xs text-gray-400 hover:text-red-500"
                  onClick={() => removeUploadItem(item.id)}
                  aria-label={`Remove ${item.fileName} from list`}
                >
                  ✕
                </button>
              </div>
              <div className="mt-2 flex items-center gap-2">
                {item.status === 'uploading' && <SpinnerIcon className="h-4 w-4 text-indigo-500" />}
                <div className="flex-1 rounded-full bg-gray-100">
                  <div
                    className={`rounded-full py-0.5 text-xs text-white transition-all ${
                      item.status === 'error' ? 'bg-red-500' : 'bg-indigo-500'
                    }`}
                    style={{ width: `${Math.max(item.progress, item.status === 'completed' ? 100 : 10)}%` }}
                  ></div>
                </div>
                <span className="w-16 text-right text-xs text-gray-500">
                  {item.status === 'error' ? 'Failed' : `${item.progress}%`}
                </span>
              </div>
              {item.message && (
                <p className="mt-1 text-xs text-gray-500">
                  {item.message}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

export default UploadArea;
