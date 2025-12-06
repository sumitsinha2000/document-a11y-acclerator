import { useMemo } from "react"
import CriteriaSummarySection from "./CriteriaSummarySection"

const WCAG_CRITERIA_DETAILS = {
  "1.1.1": {
    name: "Non-text Content",
    level: "A",
    summary: "Provide text alternatives for non-text content.",
  },
  "1.3.1": {
    name: "Info and Relationships",
    level: "A",
    summary: "Preserve semantics so assistive technology can convey relationships.",
  },
  "1.3.2": {
    name: "Meaningful Sequence",
    level: "A",
    summary: "Ensure reading order preserves intended meaning.",
  },
  "1.4.3": {
    name: "Contrast (Minimum)",
    level: "AA",
    summary: "Text/background contrast must be at least 4.5:1 for body text.",
  },
  "1.4.6": {
    name: "Contrast (Enhanced)",
    level: "AAA",
    summary: "Enhanced 7:1 contrast aids users with low vision.",
  },
  "2.4.1": {
    name: "Bypass Blocks",
    level: "A",
    summary:
      "Provide direct entry to main content (e.g., first H1 or bookmarks) so assistive tech can skip repeated content.",
  },
  "2.4.2": {
    name: "Page Titled",
    level: "A",
    summary: "Provide descriptive titles so users can identify content.",
  },
  "2.4.4": {
    name: "Link Purpose (In Context)",
    level: "AA",
    summary: "Ensure link text or alternative descriptions clearly explain the destination.",
  },
  "2.4.6": {
    name: "Headings and Labels",
    level: "AA",
    summary: "Use clear headings/labels for navigation.",
  },
  "3.1.1": {
    name: "Language of Page",
    level: "A",
    summary: "Declare the primary language for pronunciation support.",
  },
  "3.3.2": {
    name: "Labels or Instructions",
    level: "A",
    summary: "Provide instructions so users know required input.",
  },
  "4.1.2": {
    name: "Name, Role, Value",
    level: "A",
    summary: "Expose UI semantics programmatically.",
  },
}

const WCAG_ORDER = [
  "1.1.1",
  "1.3.1",
  "1.3.2",
  "1.4.3",
  "1.4.6",
  "2.4.1",
  "2.4.2",
  "2.4.4",
  "2.4.6",
  "3.1.1",
  "3.3.2",
  "4.1.2",
]

const SEVERITY_RANK = {
  critical: 3,
  high: 3,
  medium: 2,
  low: 1,
}

const STATUS_FAIL = "doesNotSupport"
const STATUS_PARTIAL = "partiallySupports"
const STATUS_PASS = "supports"

const determineStatus = (issues = []) => {
  if (!issues.length) return STATUS_PASS
  const highest = issues.reduce((score, issue) => {
    const normalized = String(issue?.severity || "").toLowerCase()
    return Math.max(score, SEVERITY_RANK[normalized] ?? 2)
  }, 0)
  return highest >= 3 ? STATUS_FAIL : STATUS_PARTIAL
}

const buildFallbackSummary = (results) => {
  const source = Array.isArray(results?.wcagIssues) ? results.wcagIssues : []
  if (!source.length) return null

  const grouped = new Map()
  source.forEach((issue) => {
    if (!issue || typeof issue !== "object") return
    const code = issue.criterion || issue.code
    if (!code) return
    const normalized = String(code).trim()
    if (!normalized) return
    if (!grouped.has(normalized)) {
      grouped.set(normalized, [])
    }
    grouped.get(normalized).push(issue)
  })

  const seen = new Set()
  const items = []

  const createItem = (code) => {
    const details = WCAG_CRITERIA_DETAILS[code] || {}
    const issues = grouped.get(code) || []
    return {
      code,
      name: details.name || "WCAG Criterion",
      level: details.level,
      summary: details.summary,
      issues,
      issueCount: issues.length,
      status: determineStatus(issues),
    }
  }

  WCAG_ORDER.forEach((code) => {
    seen.add(code)
    items.push(createItem(code))
  })

  Array.from(grouped.keys())
    .filter((code) => !seen.has(code))
    .sort()
    .forEach((code) => {
      seen.add(code)
      items.push(createItem(code))
    })

  return {
    items,
    statusCounts: {},
  }
}

const enrichWithMetadata = (data) => {
  if (!data || !Array.isArray(data.items)) {
    return data
  }
  const enrichedItems = data.items.map((item) => {
    const details = WCAG_CRITERIA_DETAILS[item.code] || {}
    return {
      ...item,
      name: item.name || details.name || "WCAG Criterion",
      level: item.level || details.level,
      summary: item.summary || details.summary,
    }
  })
  return { ...data, items: enrichedItems }
}

const ALT_TEXT_LIMITATION_TOOLTIP =
  "Professionally tagged PDFs may still show missing alt text when they use uncommon PDF/UA tagging; typical Word-to-PDF exports are supported."

const addAltTextTooltip = (data) => {
  if (!data || !Array.isArray(data.items)) {
    return data
  }
  return {
    ...data,
    items: data.items.map((item) =>
      item.code === "1.1.1" ? { ...item, infoTooltip: ALT_TEXT_LIMITATION_TOOLTIP } : item,
    ),
  }
}

export default function WcagCriteriaSummary({ criteriaSummary, results }) {
  const data = useMemo(() => {
    let baseData = null
    if (criteriaSummary && Array.isArray(criteriaSummary.items)) {
      baseData = enrichWithMetadata(criteriaSummary)
    }
    if (!baseData) {
      baseData = enrichWithMetadata(buildFallbackSummary(results))
    }
    return addAltTextTooltip(baseData)
  }, [criteriaSummary, results])

  if (!data) {
    return null
  }

  return (
    <CriteriaSummarySection
      title="WCAG Criteria Report"
      subtitle="Monitor how this file performs against key WCAG success criteria. Expand any card for issue-level details."
      data={data}
      sectionId="wcag-criteria"
    />
  )
}
