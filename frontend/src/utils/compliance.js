const HIGH_SEVERITIES = new Set(["high", "critical"])
const MEDIUM_SEVERITIES = new Set(["medium"])
const LOW_SEVERITIES = new Set(["low"])
const ISSUE_PENALTY = 5

const isNumber = (value) => typeof value === "number" && Number.isFinite(value)

const clamp = (value, min = 0, max = 100) => Math.min(max, Math.max(min, value))

const combineComplianceScores = (...scores) => {
  const numericScores = scores.filter((score) => isNumber(score))
  if (numericScores.length === 0) {
    return null
  }
  const average = numericScores.reduce((sum, value) => sum + value, 0) / numericScores.length
  return Math.round(average * 100) / 100
}

const getIssueCount = (results, key) => {
  if (!results || typeof results !== "object") {
    return 0
  }
  const issues = results[key]
  return Array.isArray(issues) ? issues.length : 0
}

const countCanonical = (results = {}, predicate) => {
  const issues = Array.isArray(results?.issues) ? results.issues : []
  if (!issues.length) return 0
  const seen = new Set()
  return issues.reduce((count, issue) => {
    if (!issue || typeof issue !== "object") return count
    const id = issue.issueId
    if (id && seen.has(id)) return count
    if (id) seen.add(id)
    if (predicate(issue)) return count + 1
    return count
  }, 0)
}

const computeScoreFromIssues = (issueCount) => clamp(100 - issueCount * ISSUE_PENALTY)

const deriveComplianceValue = (reportedValue, issueCount) => {
  if (isNumber(reportedValue)) {
    return clamp(reportedValue)
  }
  return computeScoreFromIssues(issueCount)
}

export const calculateComplianceSnapshot = (results = {}, verapdfStatus = {}) => {
  const canonicalWcag = countCanonical(results, (issue) => Boolean(issue.criterion))
  const canonicalPdfua = countCanonical(results, (issue) => Boolean(issue.clause))

  const wcagIssues = canonicalWcag || getIssueCount(results, "wcagIssues")
  const pdfuaIssues = canonicalPdfua || getIssueCount(results, "pdfuaIssues")

  const wcagCompliance = deriveComplianceValue(verapdfStatus?.wcagCompliance, wcagIssues)
  const pdfuaCompliance = deriveComplianceValue(verapdfStatus?.pdfuaCompliance, pdfuaIssues)

  const combined = combineComplianceScores(wcagCompliance, pdfuaCompliance)
  const totalVeraPDFIssues =
    typeof verapdfStatus?.totalVeraPDFIssues === "number"
      ? verapdfStatus.totalVeraPDFIssues
      : wcagIssues + pdfuaIssues

  return {
    ...verapdfStatus,
    isActive: Boolean(
      verapdfStatus?.isActive ||
        isNumber(wcagCompliance) ||
        isNumber(pdfuaCompliance),
    ),
    totalVeraPDFIssues,
    wcagCompliance,
    pdfuaCompliance,
    complianceScore: combined ?? 0,
  }
}

export const calculateSummaryFromResults = (results = {}, verapdfStatus = null) => {
  if (!results || typeof results !== "object") {
    const complianceSnapshot = calculateComplianceSnapshot({}, verapdfStatus || {})
    return {
      totalIssues: 0,
      highSeverity: 0,
      mediumSeverity: 0,
      lowSeverity: 0,
      complianceScore: complianceSnapshot.complianceScore,
      wcagCompliance: complianceSnapshot.wcagCompliance,
      pdfuaCompliance: complianceSnapshot.pdfuaCompliance,
    }
  }

  const canonicalIssues = Array.isArray(results?.issues) ? results.issues : null

  let totalIssues = 0
  let highSeverity = 0
  let mediumSeverity = 0
  let lowSeverity = 0

  const processIssues = (issues) => {
    const seen = new Set()
    issues.forEach((issue) => {
      if (!issue || typeof issue !== "object") {
        totalIssues += 1
        lowSeverity += 1
        return
      }
      const id = issue.issueId
      if (id && seen.has(id)) return
      if (id) seen.add(id)

      totalIssues += 1
      const severity = String(issue.severity || "").toLowerCase()
      if (HIGH_SEVERITIES.has(severity)) {
        highSeverity += 1
      } else if (MEDIUM_SEVERITIES.has(severity)) {
        mediumSeverity += 1
      } else if (LOW_SEVERITIES.has(severity)) {
        lowSeverity += 1
      } else {
        lowSeverity += 1
      }
    })
  }

  if (canonicalIssues) {
    processIssues(canonicalIssues)
  } else {
    Object.entries(results).forEach(([key, issues]) => {
      if (key === "issues" || !Array.isArray(issues) || issues.length === 0) {
        return
      }
      processIssues(issues)
    })
  }

  if (totalIssues > 0) {
    const classified = highSeverity + mediumSeverity + lowSeverity
    if (classified < totalIssues) {
      lowSeverity += totalIssues - classified
    }
  }

  const complianceSnapshot = calculateComplianceSnapshot(results, verapdfStatus || {})

  return {
    totalIssues,
    highSeverity,
    mediumSeverity,
    lowSeverity: Math.max(totalIssues - highSeverity - mediumSeverity, lowSeverity),
    complianceScore: complianceSnapshot.complianceScore,
    wcagCompliance: complianceSnapshot.wcagCompliance,
    pdfuaCompliance: complianceSnapshot.pdfuaCompliance,
  }
}

export const resolveSummary = ({ summary, results, verapdfStatus } = {}) => {
  const fallback = calculateSummaryFromResults(results, verapdfStatus)
  if (!summary || typeof summary !== "object") {
    return fallback
  }

  const merged = { ...fallback, ...summary }
  const numericKeys = ["totalIssues", "highSeverity", "mediumSeverity", "lowSeverity", "complianceScore"]
  numericKeys.forEach((key) => {
    if (!isNumber(merged[key])) {
      merged[key] = fallback[key]
    }
  })

  const complianceKeys = ["wcagCompliance", "pdfuaCompliance"]
  complianceKeys.forEach((key) => {
    if (!isNumber(merged[key]) && isNumber(fallback[key])) {
      merged[key] = fallback[key]
    }
  })

  merged.complianceScore = fallback.complianceScore

  return merged
}
