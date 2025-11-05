import { readFileSync, writeFileSync } from "fs"
import { join } from "path"
import { fileURLToPath } from "url"
import { dirname } from "path"

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// List of all files that need "use client" removed
const filesToClean = [
  "frontend/src/App.jsx",
  "frontend/src/components/AIFixStrategyModal.jsx",
  "frontend/src/components/AIRemediationPanel.jsx",
  "frontend/src/components/AlertModal.jsx",
  "frontend/src/components/BatchReportViewer.jsx",
  "frontend/src/components/Breadcrumb.jsx",
  "frontend/src/components/ConfirmDialog.jsx",
  "frontend/src/components/ExportDropdown.jsx",
  "frontend/src/components/ExportOptions.jsx",
  "frontend/src/components/FixHistory.jsx",
  "frontend/src/components/FixProgressStepper.jsx",
  "frontend/src/components/FixSuggestions.jsx",
  "frontend/src/components/GroupDashboard.jsx",
  "frontend/src/components/GroupMaster.jsx",
  "frontend/src/components/GroupSelector.jsx",
  "frontend/src/components/GroupTreeSidebar.jsx",
  "frontend/src/components/History.jsx",
  "frontend/src/components/IssueStats.jsx",
  "frontend/src/components/IssuesList.jsx",
  "frontend/src/components/LoadingScreen.jsx",
  "frontend/src/components/PDFEditor.jsx",
  "frontend/src/components/PDFGenerator.jsx",
  "frontend/src/components/ReportViewer.jsx",
  "frontend/src/components/ScanHistory.jsx",
  "frontend/src/components/ScanResults.jsx",
  "frontend/src/components/SidebarNav.jsx",
  "frontend/src/components/ThemeToggle.jsx",
  "frontend/src/components/Toast.jsx",
  "frontend/src/components/UploadArea.jsx",
  "frontend/src/components/UploadProgressToast.jsx",
  "frontend/src/components/ui/AlertBanner.jsx",
  "frontend/src/components/ui/Modal.jsx",
  "frontend/src/components/ui/Toast.jsx",
  "frontend/src/contexts/NotificationContext.jsx",
]

let cleanedCount = 0
let errorCount = 0

console.log('🧹 Starting cleanup of "use client" directives...\n')

filesToClean.forEach((filePath) => {
  try {
    const fullPath = join(__dirname, "..", filePath)
    let content = readFileSync(fullPath, "utf8")

    // Check if file contains "use client"
    if (content.includes('"use client"') || content.includes("'use client'")) {
      // Remove "use client" directive (with or without semicolon, with various quote styles)
      content = content.replace(/^["']use client["'];?\s*\n/m, "").replace(/^["']use client["'];?\s*\r?\n/m, "")

      writeFileSync(fullPath, content, "utf8")
      console.log(`✅ Cleaned: ${filePath}`)
      cleanedCount++
    } else {
      console.log(`⏭️  Skipped (already clean): ${filePath}`)
    }
  } catch (error) {
    console.error(`❌ Error processing ${filePath}:`, error.message)
    errorCount++
  }
})

console.log(`\n📊 Summary:`)
console.log(`   ✅ Files cleaned: ${cleanedCount}`)
console.log(`   ⏭️  Files skipped: ${filesToClean.length - cleanedCount - errorCount}`)
console.log(`   ❌ Errors: ${errorCount}`)
console.log("\n✨ Cleanup complete!")
