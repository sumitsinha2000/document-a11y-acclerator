"use client"

import { useState, useEffect } from "react"
import groupMasterService from "../services/GroupMasterService"

export default function GroupSelector({ selectedGroup, onGroupChange, required = true }) {
  const [groups, setGroups] = useState([])
  const [isCreatingNew, setIsCreatingNew] = useState(false)
  const [newGroupName, setNewGroupName] = useState("")
  const [newGroupDescription, setNewGroupDescription] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    console.log("[v0] GroupSelector mounted, fetching groups...")
    fetchGroups()

    const unsubscribe = groupMasterService.subscribe((event, data) => {
      if (event === "group:created") {
        setGroups((prev) => [...prev, data])
      } else if (event === "group:updated") {
        setGroups((prev) => prev.map((g) => (g.id === data.id ? data : g)))
      } else if (event === "group:deleted") {
        setGroups((prev) => prev.filter((g) => g.id !== data))
      }
    })

    return () => unsubscribe()
  }, [])

  const fetchGroups = async () => {
    try {
      console.log("[v0] Calling groupMasterService.fetchGroups()...")
      const fetchedGroups = await groupMasterService.fetchGroups()
      console.log("[v0] Fetched groups:", fetchedGroups)
      console.log("[v0] Number of groups:", fetchedGroups.length)
      setGroups(fetchedGroups)
    } catch (err) {
      console.error("[v0] Error fetching groups:", err)
      setError("Failed to load groups")
    }
  }

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) {
      setError("Group name is required")
      return
    }

    if (newGroupName.trim().length > 255) {
      setError("Group name must be less than 255 characters")
      return
    }

    setLoading(true)
    setError(null)

    try {
      console.log("[v0] Creating group via GroupMaster service...")

      const newGroup = await groupMasterService.createGroup(newGroupName, newGroupDescription)

      console.log("[v0] Group created successfully:", newGroup)
      console.log("[v0] Group ID:", newGroup.id)
      console.log("[v0] Group saved to 'groups' table in database")

      onGroupChange(newGroup.id)

      setNewGroupName("")
      setNewGroupDescription("")
      setIsCreatingNew(false)

      console.log("[v0] ✓ Group creation complete and selected")
    } catch (err) {
      console.error("[v0] Error creating group:", err)
      setError(err.message || "Failed to create group")
    } finally {
      setLoading(false)
    }
  }

  const handleCancelCreate = () => {
    setIsCreatingNew(false)
    setNewGroupName("")
    setNewGroupDescription("")
    setError(null)
  }

  return (
    <div className="space-y-3">
      <label className="block text-sm font-semibold text-gray-900 dark:text-white">
        Select Group {required && <span className="text-red-500">*</span>}
      </label>

      {!isCreatingNew ? (
        <div className="space-y-2">
          <select
            value={selectedGroup || ""}
            onChange={(e) => onGroupChange(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            required={required}
          >
            <option value="">-- Select a group --</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name} {group.file_count > 0 && `(${group.file_count} files)`}
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={() => setIsCreatingNew(true)}
            className="w-full px-4 py-2 text-sm font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors"
          >
            + Create New Group
          </button>
        </div>
      ) : (
        <div className="space-y-3 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              Group Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              placeholder="e.g., Q1 Reports, Legal Documents"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
              disabled={loading}
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              Description (Optional)
            </label>
            <textarea
              value={newGroupDescription}
              onChange={(e) => setNewGroupDescription(e.target.value)}
              placeholder="Brief description of this group"
              rows={2}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm resize-none"
              disabled={loading}
            />
          </div>

          {error && (
            <p className="text-xs text-red-600 dark:text-red-400" role="alert">
              {error}
            </p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleCreateGroup}
              disabled={loading || !newGroupName.trim()}
              className="flex-1 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Creating..." : "Create Group"}
            </button>
            <button
              type="button"
              onClick={handleCancelCreate}
              disabled={loading}
              className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
