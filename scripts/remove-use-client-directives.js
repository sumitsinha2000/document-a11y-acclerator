const fs = require("fs")
const path = require("path")

const frontendSrcDir = path.join(__dirname, "../frontend/src")

function removeUseClientDirective(filePath) {
  try {
    let content = fs.readFileSync(filePath, "utf8")
    const originalContent = content

    // Remove "use client" or 'use client' at the start of the file
    content = content.replace(/^["']use client["'];?\s*\n/m, "")
    content = content.replace(/^["']use client["']\s*\n/m, "")

    if (content !== originalContent) {
      fs.writeFileSync(filePath, content, "utf8")
      console.log(`✓ Removed "use client" from: ${filePath}`)
      return true
    }
    return false
  } catch (error) {
    console.error(`✗ Error processing ${filePath}:`, error.message)
    return false
  }
}

function processDirectory(dir) {
  let count = 0
  const files = fs.readdirSync(dir)

  files.forEach((file) => {
    const filePath = path.join(dir, file)
    const stat = fs.statSync(filePath)

    if (stat.isDirectory()) {
      count += processDirectory(filePath)
    } else if (file.endsWith(".jsx") || file.endsWith(".js")) {
      if (removeUseClientDirective(filePath)) {
        count++
      }
    }
  })

  return count
}

console.log('Starting to remove "use client" directives from all frontend files...\n')
const totalRemoved = processDirectory(frontendSrcDir)
console.log(`\n✓ Complete! Removed "use client" from ${totalRemoved} file(s).`)
