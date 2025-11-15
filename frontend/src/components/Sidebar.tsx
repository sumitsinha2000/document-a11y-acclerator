import { useState } from 'react';
import type { FC } from 'react';
import { Project, Folder } from '../types';
import { FolderIcon } from './icons/FolderIcon';
import { PlusIcon } from './icons/PlusIcon';
import { ChevronRightIcon } from './icons/ChevronRightIcon';
import { PencilIcon } from './icons/PencilIcon';
import { TrashIcon } from './icons/TrashIcon';
import { CheckIcon } from './icons/CheckIcon';
import { XMarkIcon } from './icons/XMarkIcon';

interface SidebarProps {
  projects: Project[];
  currentProject: Project | null;
  currentFolder: Folder | null;
  onCreateProject: (projectName: string) => void;
  onSelectProject: (projectId: string) => void;
  onUpdateProject: (projectId: string, newName: string) => void;
  onDeleteProject: (projectId: string) => void;
  onCreateFolder: (folderName: string) => void;
  onSelectFolder: (folderId: string) => void;
  onUpdateFolder: (folderId: string, newName: string) => void;
  onDeleteFolder: (folderId: string) => void;
}

const Sidebar: FC<SidebarProps> = ({
  projects,
  currentProject,
  currentFolder,
  onCreateProject,
  onSelectProject,
  onUpdateProject,
  onDeleteProject,
  onCreateFolder,
  onSelectFolder,
  onUpdateFolder,
  onDeleteFolder,
}) => {
  const [newProjectName, setNewProjectName] = useState('');
  const [newFolderName, setNewFolderName] = useState('');
  
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editingProjectName, setEditingProjectName] = useState('');
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);

  const [editingFolderId, setEditingFolderId] = useState<string | null>(null);
  const [editingFolderName, setEditingFolderName] = useState('');
  const [deletingFolderId, setDeletingFolderId] = useState<string | null>(null);


  const handleProjectSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCreateProject(newProjectName);
    setNewProjectName('');
  };

  const handleProjectEditSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingProjectId) {
      onUpdateProject(editingProjectId, editingProjectName);
    }
    setEditingProjectId(null);
    setEditingProjectName('');
  };

  const handleProjectEditClick = (project: Project) => {
    setEditingProjectId(project.id);
    setEditingProjectName(project.name);
    setDeletingProjectId(null);
  };

  const handleProjectEditCancel = () => {
    setEditingProjectId(null);
    setEditingProjectName('');
  };

  const handleProjectDeleteClick = (projectId: string) => {
    setDeletingProjectId(projectId);
    setEditingProjectId(null);
  };

  const handleProjectDeleteCancel = () => {
    setDeletingProjectId(null);
  };
  
  const handleProjectDeleteConfirm = () => {
    if(deletingProjectId) {
      onDeleteProject(deletingProjectId);
    }
    setDeletingProjectId(null);
  };


  const handleFolderSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCreateFolder(newFolderName);
    setNewFolderName('');
  };

  const handleFolderEditSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingFolderId) {
        onUpdateFolder(editingFolderId, editingFolderName);
    }
    setEditingFolderId(null);
    setEditingFolderName('');
  };

  const handleFolderEditClick = (folder: Folder) => {
    setEditingFolderId(folder.id);
    setEditingFolderName(folder.name);
    setDeletingFolderId(null);
  };

  const handleFolderEditCancel = () => {
    setEditingFolderId(null);
    setEditingFolderName('');
  };

  const handleFolderDeleteClick = (folderId: string) => {
    setDeletingFolderId(folderId);
    setEditingFolderId(null);
  };

  const handleFolderDeleteCancel = () => {
      setDeletingFolderId(null);
  };
  
  const handleFolderDeleteConfirm = () => {
      if(deletingFolderId) {
          onDeleteFolder(deletingFolderId);
      }
      setDeletingFolderId(null);
  };

  return (
    <aside className="w-full max-w-sm flex-shrink-0 bg-white rounded-lg border border-gray-200 p-4 flex flex-col space-y-4">
      <h2 className="text-xl font-bold text-gray-800 tracking-tight">Projects</h2>
      
      <form onSubmit={handleProjectSubmit} className="flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          value={newProjectName}
          onChange={(e) => setNewProjectName(e.target.value)}
          placeholder="New project name..."
          className="flex-grow bg-gray-100 border border-gray-300 rounded-md px-3 py-2 text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition duration-200 text-sm"
          aria-label="New project name"
        />
        <button
          type="submit"
          disabled={!newProjectName.trim()}
          className="flex items-center justify-center gap-2 bg-indigo-600 text-white font-semibold px-4 py-2 rounded-md hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition duration-200 text-sm"
        >
          <PlusIcon className="w-5 h-5" />
          <span>Create</span>
        </button>
      </form>

      <div className="flex-grow overflow-y-auto space-y-1 pr-1 -mr-1">
        {projects.length > 0 ? (
          projects.map(project => (
            <div key={project.id}>
              <div className="relative group/project">
                {editingProjectId === project.id ? (
                  <form onSubmit={handleProjectEditSubmit} className="flex gap-2 items-center p-2.5 bg-gray-200 rounded-md">
                    <input
                      type="text"
                      value={editingProjectName}
                      onChange={(e) => setEditingProjectName(e.target.value)}
                      className="flex-grow bg-white border border-gray-300 rounded-md px-2 py-1 text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition duration-200 text-sm"
                      autoFocus
                      onKeyDown={(e) => e.key === 'Escape' && handleProjectEditCancel()}
                    />
                    <button type="submit" className="p-1 text-green-600 hover:text-green-500"><CheckIcon className="w-4 h-4" /></button>
                    <button type="button" onClick={handleProjectEditCancel} className="p-1 text-red-600 hover:text-red-500"><XMarkIcon className="w-4 h-4" /></button>
                  </form>
                ) : deletingProjectId === project.id ? (
                  <div className="p-2.5 rounded-md bg-red-100 text-center">
                    <p className="text-xs text-gray-800 mb-2">Delete project?</p>
                    <div className="flex justify-center gap-2">
                      <button onClick={handleProjectDeleteConfirm} className="px-2 py-0.5 text-xs bg-red-600 hover:bg-red-700 rounded text-white">Yes</button>
                      <button onClick={handleProjectDeleteCancel} className="px-2 py-0.5 text-xs bg-gray-400 hover:bg-gray-500 rounded text-white">No</button>
                    </div>
                  </div>
                ) : (
                  <>
                    <button
                      onClick={() => onSelectProject(project.id)}
                      className={`w-full text-left p-2.5 rounded-md transition duration-200 group flex items-center gap-3 ${currentProject?.id === project.id ? 'bg-gray-200' : 'hover:bg-gray-100'}`}
                      aria-current={currentProject?.id === project.id}
                    >
                      <ChevronRightIcon className={`w-3 h-3 transition-transform text-gray-400 ${currentProject?.id === project.id ? 'rotate-90' : ''}`} />
                      <FolderIcon className={`w-5 h-5 flex-shrink-0 ${currentProject?.id === project.id ? 'text-indigo-600' : 'text-gray-400 group-hover:text-gray-500'}`} />
                      <div className="flex-1 overflow-hidden">
                        <h3 className="text-sm font-semibold text-gray-800 truncate">{project.name}</h3>
                      </div>
                    </button>
                    <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-2 opacity-0 group-hover/project:opacity-100 transition-opacity">
                      <button onClick={() => handleProjectEditClick(project)} className="p-1 text-gray-500 hover:text-gray-800" aria-label="Edit project name">
                          <PencilIcon className="w-4 h-4" />
                      </button>
                      <button onClick={() => handleProjectDeleteClick(project.id)} className="p-1 text-gray-500 hover:text-red-600" aria-label="Delete project">
                          <TrashIcon className="w-4 h-4" />
                      </button>
                    </div>
                  </>
                )}
              </div>
              
              {currentProject?.id === project.id && (
                <div className="pl-6 pt-2 pb-1 space-y-2">
                  {project.folders.map(folder => (
                     <div key={folder.id} className="relative group/folder">
                      {editingFolderId === folder.id ? (
                        <form onSubmit={handleFolderEditSubmit} className="flex gap-2 items-center p-2 bg-gray-200 rounded-md">
                          <input
                            type="text"
                            value={editingFolderName}
                            onChange={(e) => setEditingFolderName(e.target.value)}
                            className="flex-grow bg-white border border-gray-300 rounded-md px-2 py-1 text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition duration-200 text-sm"
                            autoFocus
                            onKeyDown={(e) => e.key === 'Escape' && handleFolderEditCancel()}
                          />
                           <button type="submit" className="p-1 text-green-600 hover:text-green-500"><CheckIcon className="w-4 h-4" /></button>
                           <button type="button" onClick={handleFolderEditCancel} className="p-1 text-red-600 hover:text-red-500"><XMarkIcon className="w-4 h-4" /></button>
                        </form>
                      ) : deletingFolderId === folder.id ? (
                        <div className="p-2 rounded-md bg-red-100 text-center">
                            <p className="text-xs text-gray-800 mb-2">Delete this folder?</p>
                            <div className="flex justify-center gap-2">
                                <button onClick={handleFolderDeleteConfirm} className="px-2 py-0.5 text-xs bg-red-600 hover:bg-red-700 rounded text-white">Yes</button>
                                <button onClick={handleFolderDeleteCancel} className="px-2 py-0.5 text-xs bg-gray-400 hover:bg-gray-500 rounded text-white">No</button>
                            </div>
                        </div>
                      ) : (
                        <>
                          <button
                            onClick={() => onSelectFolder(folder.id)}
                            className={`w-full text-left p-2 rounded-md transition duration-200 group flex items-center gap-3 ${currentFolder?.id === folder.id ? 'bg-indigo-600 text-white' : 'hover:bg-gray-100'}`}
                            aria-current={currentFolder?.id === folder.id}
                          >
                          <FolderIcon className={`w-5 h-5 flex-shrink-0 ${currentFolder?.id === folder.id ? 'text-white' : 'text-indigo-500 group-hover:text-indigo-600'}`} />
                            <div className="flex-1 overflow-hidden">
                              <h3 className={`text-sm font-medium truncate ${currentFolder?.id === folder.id ? 'text-white' : 'text-gray-800'}`}>{folder.name}</h3>
                              <p className={`text-xs ${currentFolder?.id === folder.id ? 'text-indigo-200' : 'text-gray-500'}`}>
                                {folder.documents.length} document{folder.documents.length !== 1 ? 's' : ''}
                              </p>
                            </div>
                          </button>
                          <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-2 opacity-0 group-hover/folder:opacity-100 transition-opacity">
                              <button onClick={() => handleFolderEditClick(folder)} className="p-1 text-gray-500 hover:text-gray-800" aria-label="Edit folder name">
                                  <PencilIcon className="w-4 h-4" />
                              </button>
                              <button onClick={() => handleFolderDeleteClick(folder.id)} className="p-1 text-gray-500 hover:text-red-600" aria-label="Delete folder">
                                  <TrashIcon className="w-4 h-4" />
                              </button>
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                   <form onSubmit={handleFolderSubmit} className="flex gap-2 pl-3 pt-2">
                      <input
                        type="text"
                        value={newFolderName}
                        onChange={(e) => setNewFolderName(e.target.value)}
                        placeholder="New folder..."
                        className="flex-grow bg-gray-100 border border-gray-300 rounded-md px-2 py-1.5 text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition duration-200 text-xs"
                        aria-label="New folder name"
                      />
                      <button
                        type="submit"
                        disabled={!newFolderName.trim()}
                        className="flex items-center justify-center bg-indigo-600 text-white font-semibold p-2 rounded-md hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition duration-200"
                      >
                        <PlusIcon className="w-4 h-4" />
                      </button>
                    </form>
                </div>
              )}
            </div>
          ))
        ) : (
          <div className="text-center py-12 text-gray-500 text-sm">
            <p>No projects yet. Create one to get started!</p>
          </div>
        )}
      </div>
    </aside>
  );
};

export default Sidebar;
