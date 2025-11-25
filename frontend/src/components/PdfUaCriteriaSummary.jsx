import { useMemo } from "react"
import CriteriaSummarySection from "./CriteriaSummarySection"

const CLAUSE_DETAILS = {
  "ISO 14289-1:7.1": {
    name: "Document Identification",
    summary: "Metadata, tagging, and document title requirements.",
  },
  "ISO 14289-1:7.2": {
    name: "Structure Tree",
    summary: "Structure semantics, RoleMap, and reading order.",
  },
  "ISO 14289-1:7.3": {
    name: "Artifacts",
    summary: "Artifacts must be separated from tagged content.",
  },
  "ISO 14289-1:7.4": {
    name: "Headings",
    summary: "Heading hierarchy and nesting rules.",
  },
  "ISO 14289-1:7.5": {
    name: "Tables",
    summary: "Tables require header associations and structure.",
  },
  "ISO 14289-1:7.18": {
    name: "Forms & Alt Text",
    summary: "Interactive elements need names and alternative text.",
  },
  "ISO 14289-1:7.18.1": {
    name: "Annotations",
    summary: "Annotations require descriptions for assistive tech.",
  },
}

const CLAUSE_ORDER = [
  "ISO 14289-1:7.1",
  "ISO 14289-1:7.2",
  "ISO 14289-1:7.3",
  "ISO 14289-1:7.4",
  "ISO 14289-1:7.5",
  "ISO 14289-1:7.18",
  "ISO 14289-1:7.18.1",
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
  const source = Array.isArray(results?.pdfuaIssues) ? results.pdfuaIssues : []
  if (!source.length) return null

  const grouped = new Map()
  source.forEach((issue) => {
    if (!issue || typeof issue !== "object") return
    const clause = issue.clause || issue.specification
    if (!clause) return
    const normalized = String(clause).trim()
    if (!normalized) return
    if (!grouped.has(normalized)) {
      grouped.set(normalized, [])
    }
    grouped.get(normalized).push(issue)
  })

  if (!grouped.size) {
    return null
  }

  const seen = new Set()
  const items = []

  const createItem = (code) => {
    const details = CLAUSE_DETAILS[code] || {}
    const issues = grouped.get(code) || []
    return {
      code,
      name: details.name || "PDF/UA Requirement",
      summary: details.summary,
      issues,
      issueCount: issues.length,
      status: determineStatus(issues),
    }
  }

  CLAUSE_ORDER.forEach((code) => {
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
    const details = CLAUSE_DETAILS[item.code] || {}
    return {
      ...item,
      name: item.name || details.name || "PDF/UA Requirement",
      summary: item.summary || details.summary,
    }
  })
  return { ...data, items: enrichedItems }
}

export default function PdfUaCriteriaSummary({ criteriaSummary, results }) {
  const data = useMemo(() => {
    if (criteriaSummary && Array.isArray(criteriaSummary.items)) {
      return enrichWithMetadata(criteriaSummary)
    }
    const fallback = buildFallbackSummary(results)
    return enrichWithMetadata(fallback)
  }, [criteriaSummary, results])

  if (!data) {
    return null
  }

  return (
    <CriteriaSummarySection
      title="PDF/UA Criteria Report"
      subtitle="Monitor how this file performs against key accessibility criteria. Expand any card for issue-level details."
      data={data}
      sectionId="pdfua-criteria"
    />
  )
}
