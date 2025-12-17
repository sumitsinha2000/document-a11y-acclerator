import axios from "axios"
import { API_ENDPOINTS } from "../config/api"

/**
 * GroupMasterService - Dedicated service for managing groups independently
 * Handles all group CRUD operations and ensures data integrity
 */
class GroupMasterService {
  constructor() {
    this.baseUrl = API_ENDPOINTS.projects
    this.cache = new Map()
    this.listeners = new Set()
  }

  /**
   * Subscribe to group changes
   */
  subscribe(callback) {
    this.listeners.add(callback)
    return () => this.listeners.delete(callback)
  }

  /**
   * Notify all listeners of changes
   */
  notifyListeners(event, data) {
    this.listeners.forEach((callback) => {
      try {
        callback(event, data)
      } catch (error) {
        console.error("[GroupMaster] Error in listener:", error)
      }
    })
  }

  /**
   * Fetch all groups from the database
   */
  async fetchGroups() {
    try {
      console.log("[GroupMaster] Fetching all groups...")
      const response = await axios.get(this.baseUrl)
      const groups = response.data.groups || []

      // Update cache
      this.cache.clear()
      groups.forEach((group) => {
        this.cache.set(group.id, group)
      })

      console.log(`[GroupMaster] ✓ Fetched ${groups.length} groups`)
      this.notifyListeners("groups:fetched", groups)
      return groups
    } catch (error) {
      console.error("[GroupMaster] ✗ Error fetching groups:", error)
      throw new Error(error.response?.data?.error || "Failed to fetch projects")
    }
  }

  /**
   * Create a new group - saves directly to database
   */
  async createGroup(name, description = "") {
    try {
      if (!name || !name.trim()) {
        throw new Error("Project name is required")
      }

      if (name.trim().length > 255) {
        throw new Error("Project name must be less than 255 characters")
      }

      console.log("[GroupMaster] Creating new group:", name)

      const response = await axios.post(this.baseUrl, {
        name: name.trim(),
        description: description.trim(),
      })

      const newGroup = response.data.group

      if (!newGroup || !newGroup.id || !newGroup.name) {
        throw new Error("Invalid project data received from server")
      }

      // Update cache
      this.cache.set(newGroup.id, newGroup)

      console.log(`[GroupMaster] ✓ Created group: ${newGroup.name} (${newGroup.id})`)
      console.log(`[GroupMaster] ✓ Group saved to database with ID: ${newGroup.id}`)

      this.notifyListeners("group:created", newGroup)

      return newGroup
    } catch (error) {
      console.error("[GroupMaster] ✗ Error creating group:", error)

      if (error.response?.status === 409) {
        throw new Error("A project with this name already exists")
      } else if (error.response?.status === 400) {
        throw new Error(error.response.data.error || "Invalid project data")
      } else {
        throw new Error(error.response?.data?.error || "Failed to create project. Please try again.")
      }
    }
  }

  /**
   * Get a single group by ID
   */
  async getGroup(groupId) {
    try {
      // Check cache first
      if (this.cache.has(groupId)) {
        return this.cache.get(groupId)
      }

      console.log("[GroupMaster] Fetching group:", groupId)
      const response = await axios.get(`${this.baseUrl}/${groupId}`)
      const group = response.data.group

      // Update cache
      this.cache.set(groupId, group)

      return group
    } catch (error) {
      console.error("[GroupMaster] ✗ Error fetching group:", error)
      throw new Error(error.response?.data?.error || "Failed to fetch project")
    }
  }

  /**
   * Update an existing group
   */
  async updateGroup(groupId, name, description = "") {
    try {
      if (!name || !name.trim()) {
        throw new Error("Project name is required")
      }

      console.log("[GroupMaster] Updating group:", groupId)

      const response = await axios.put(`${this.baseUrl}/${groupId}`, {
        name: name.trim(),
        description: description.trim(),
      })

      const updatedGroup = response.data.group

      // Update cache
      this.cache.set(groupId, updatedGroup)

      console.log(`[GroupMaster] ✓ Updated group: ${updatedGroup.name}`)
      this.notifyListeners("group:updated", updatedGroup)

      return updatedGroup
    } catch (error) {
      console.error("[GroupMaster] ✗ Error updating group:", error)
      throw new Error(error.response?.data?.error || "Failed to update project")
    }
  }

  /**
   * Delete a group
   */
  async deleteGroup(groupId) {
    try {
      console.log("[GroupMaster] Deleting group:", groupId)

      await axios.delete(`${this.baseUrl}/${groupId}`)

      // Remove from cache
      this.cache.delete(groupId)

      console.log(`[GroupMaster] ✓ Deleted group: ${groupId}`)
      this.notifyListeners("group:deleted", groupId)

      return true
    } catch (error) {
      console.error("[GroupMaster] ✗ Error deleting group:", error)
      throw new Error(error.response?.data?.error || "Failed to delete project")
    }
  }

  /**
   * Get group from cache
   */
  getCachedGroup(groupId) {
    return this.cache.get(groupId)
  }

  /**
   * Clear cache
   */
  clearCache() {
    this.cache.clear()
    console.log("[GroupMaster] Cache cleared")
  }
}

// Export singleton instance
const groupMasterService = new GroupMasterService()
export default groupMasterService
