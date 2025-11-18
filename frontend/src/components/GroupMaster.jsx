"use client"

import { useState, useEffect, useRef } from "react"
import axios from "axios"
import { useNotification } from "../contexts/NotificationContext"
import API_BASE_URL from "../config/api";
import { parseBackendDate } from "../utils/dates"

export default function GroupMaster({ onBack, onOpenGroupDashboard }) {
  const { showSuccess, showError, confirm } = useNotification()

  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isCreating, setIsCreating] = useState(false)
  const [editingGroup, setEditingGroup] = useState(null)

  // Form state
  const [formData, setFormData] = useState({
    name: "",
    description: "",
  })
  const [formError, setFormError] = useState(null)
  const [formLoading, setFormLoading] = useState(false)
  const [statusMessage, setStatusMessage] = useState(null)
  const statusMessageRef = useRef(null)
  const errorMessageRef = useRef(null)

  useEffect(() => {
    fetchGroups()
  }, [])

  useEffect(() => {
    if (statusMessage && statusMessageRef.current) {
      statusMessageRef.current.focus()
    }
  }, [statusMessage])

  useEffect(() => {
    if (formError && errorMessageRef.current) {
      errorMessageRef.current.focus()
    }
  }, [formError])

  const fetchGroups = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_BASE_URL}/api/groups`)
      setGroups(response.data.groups || [])
      setError(null)
    } catch (err) {
      console.error("[v0] Error fetching projects:", err)
      setError("Failed to load projects")
    } finally {
      setLoading(false)
    }
  }

  const handleCreateGroup = async (e) => {
    e.preventDefault()

    if (!formData.name.trim()) {
      setFormError("Project name is required")
      setStatusMessage(null)
      return
    }

    setStatusMessage(null)
    setFormLoading(true)
    setFormError(null)

    try {
      const response = await axios.post(`${API_BASE_URL}/api/groups`, {
        name: formData.name.trim(),
        description: formData.description.trim(),
      })

      const newGroup = response.data.group
      setGroups((prev) => [newGroup, ...prev])

      // Reset form
      setFormData({ name: "", description: "" })
      setIsCreating(false)
      showSuccess(`Project "${newGroup.name}" created successfully`)
      setStatusMessage({
        type: "success",
        text: `Project "${newGroup.name}" created successfully.`,
      })
    } catch (err) {
      console.error("[v0] Error creating project:", err)
      setFormError(err.response?.data?.error || "Failed to create project")
      setStatusMessage(null)
    } finally {
      setFormLoading(false)
    }
  }

  const handleUpdateGroup = async (e) => {
    e.preventDefault()

    if (!formData.name.trim()) {
      setFormError("Project name is required")
      setStatusMessage(null)
      return
    }

    setStatusMessage(null)
    setFormLoading(true)
    setFormError(null)

    try {
      const response = await axios.put(`${API_BASE_URL}/api/groups/${editingGroup.id}`, {
        name: formData.name.trim(),
        description: formData.description.trim(),
      })

      const updatedGroup = response.data.group
      setGroups((prev) =>
        prev.map((g) => (g.id === updatedGroup.id ? { ...g, ...updatedGroup } : g)),
      )

      try {
        await fetchGroups()
      } catch (refreshError) {
        console.error("[v0] Error refreshing groups after update:", refreshError)
      }

      // Reset form
      setFormData({ name: "", description: "" })
      setEditingGroup(null)
      setIsCreating(false)
      showSuccess(`Project "${updatedGroup.name}" updated successfully`)
      setStatusMessage({
        type: "success",
        text: `Project "${updatedGroup.name}" updated successfully.`,
      })
    } catch (err) {
      console.error("[v0] Error updating project:", err)
      setFormError(err.response?.data?.error || "Failed to update project")
      setStatusMessage(null)
    } finally {
      setFormLoading(false)
    }
  }

  const handleDeleteGroup = async (groupId, groupName) => {
    const confirmed = await confirm({
      title: "Delete Project",
      message: `Delete "${groupName}" and permanently remove all files and folders assigned to it? This action cannot be undone.`,
      confirmText: "Delete",
      cancelText: "Cancel",
      type: "danger",
    })

    if (!confirmed) {
      return
    }

    try {
      const response = await axios.delete(`${API_BASE_URL}/api/groups/${groupId}`)
      const data = response?.data || {}
      setGroups(groups.filter((g) => g.id !== groupId))
      const scanCount = data.deletedScans ?? 0
      const batchCount = data.deletedBatches ?? 0
      const fileCount = data.deletedFiles ?? 0
      const summaryBits = [
        batchCount ? `${batchCount} folder${batchCount === 1 ? "" : "s"}` : null,
        scanCount ? `${scanCount} scan${scanCount === 1 ? "" : "s"}` : null,
        fileCount ? `${fileCount} file${fileCount === 1 ? "" : "s"}` : null,
      ].filter(Boolean)
      const detail = summaryBits.length ? ` (${summaryBits.join(", ")} removed)` : ""
      showSuccess(`Project "${groupName}" deleted${detail}`)
    } catch (err) {
      console.error("[v0] Error deleting project:", err)
      showError(err.response?.data?.error || "Failed to delete project")
    }
  }

  const handleStartEdit = (group) => {
    setEditingGroup(group)
    setFormData({
      name: group.name,
      description: group.description || "",
    })
    setFormError(null)
  }

  const handleCancelForm = () => {
    setIsCreating(false)
    setEditingGroup(null)
    setFormData({ name: "", description: "" })
    setFormError(null)
  }

  const handleStartCreate = () => {
    setIsCreating(true)
    setEditingGroup(null)
    setFormData({ name: "", description: "" })
    setFormError(null)
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div
            className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"
            role="status"
            aria-label="Loading"
          >
            <span className="sr-only">Loading projects...</span>
          </div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">Loading projects...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Project Management</h1>
              <p className="mt-2 text-gray-600 dark:text-gray-400">
                Create and manage projects to organize your documents independently
              </p>
            </div>
            {onBack && (
              <button
                onClick={onBack}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
              >
                ← Back
              </button>
            )}
          </div>

          {/* Create New Project Button */}
          {!isCreating && !editingGroup && (
            <button
              onClick={handleStartCreate}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Create New Project
            </button>
          )}
        </div>

        {/* Create/Edit Form */}
        {(isCreating || editingGroup) && (
          <div className="mb-8 bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              {editingGroup ? "Edit Project" : "Create New Project"}
            </h2>

            <form onSubmit={editingGroup ? handleUpdateGroup : handleCreateGroup} className="space-y-4">
              {statusMessage && (
                <div
                  ref={statusMessageRef}
                  tabIndex={-1}
                  role="status"
                  aria-live="polite"
                  className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg focus:outline-none"
                >
                  <p className="text-sm text-green-700 dark:text-green-300">{statusMessage.text}</p>
                </div>
              )}

              <div>
                <label htmlFor="group-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Project Name <span className="text-red-500">*</span>
                </label>
                <input
                  id="group-name"
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g., Q1 Reports, Legal Documents, Marketing Materials"
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  disabled={formLoading}
                  required
                  aria-required="true"
                />
              </div>

              <div>
                <label
                  htmlFor="group-description"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Description (Optional)
                </label>
                <textarea
                  id="group-description"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Brief description of this project's purpose"
                  rows={3}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                  disabled={formLoading}
                />
              </div>

              {formError && (
                <div
                  ref={errorMessageRef}
                  tabIndex={-1}
                  className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg"
                  role="alert"
                  aria-live="assertive"
                  aria-atomic="true"
                >
                  <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={formLoading || !formData.name.trim()}
                  className="flex-1 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
                >
                  {formLoading ? "Saving..." : editingGroup ? "Update Project" : "Create Project"}
                </button>
                <button
                  type="button"
                  onClick={handleCancelForm}
                  disabled={formLoading}
                  className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div
            className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg"
            role="alert"
          >
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          </div>
        )}

        {/* Projects List */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">All Projects ({groups.length})</h2>
          </div>

          {groups.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <svg
                className="mx-auto h-12 w-12 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                />
              </svg>
              <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-white">No projects yet</h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Get started by creating your first project</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {groups.map((group) => {
                const createdDate = parseBackendDate(group.created_at || group.createdAt)
                return (
                  <div key={group.id} className="px-6 py-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                    <div className="flex items-start justify-between gap-4">
                      <button
                        type="button"
                        onClick={() => onOpenGroupDashboard && onOpenGroupDashboard(group.id)}
                        className="flex-1 min-w-0 text-left"
                        aria-label={`Open dashboard for ${group.name}`}
                      >
                        <h3 className="text-base font-semibold text-gray-900 dark:text-white truncate">{group.name}</h3>
                        {group.description && (
                          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                            {group.description}
                          </p>
                        )}
                        <div className="mt-2 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                          <span className="inline-flex items-center gap-1">
                            <svg
                              className="w-4 h-4"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                              aria-hidden="true"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                              />
                            </svg>
                            {group.file_count || 0} files
                          </span>
                          <span>Created {createdDate ? createdDate.toLocaleDateString() : "Unknown date"}</span>
                        </div>
                      </button>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleStartEdit(group)}
                          className="p-2 text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
                          aria-label={`Edit ${group.name}`}
                        >
                          <svg
                            className="w-5 h-5"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                            aria-hidden="true"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                            />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleDeleteGroup(group.id, group.name)}
                          className="p-2 text-gray-600 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
                          aria-label={`Delete ${group.name}`}
                        >
                          <svg
                            className="w-5 h-5"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                            aria-hidden="true"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                            />
                          </svg>
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Info Box */}
        <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
          <div className="flex gap-3">
            <svg
              className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <div>
              <h3 className="text-sm font-semibold text-blue-900 dark:text-blue-300">About Projects</h3>
              <p className="mt-1 text-sm text-blue-800 dark:text-blue-400">
                Projects help you organize and manage related documents together. Create projects here independently, then
                assign files to them during upload. You can track progress, view statistics, and manage files by
                project, department, or any category that suits your workflow.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
