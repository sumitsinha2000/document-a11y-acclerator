const FIRST_NON_EMPTY_FIELDS = ["description", "message", "title", "summary", "detail"]

const isPresent = (value) => {
  if (value === null || value === undefined) {
    return false
  }

  if (Array.isArray(value)) {
    return value.length > 0
  }

  if (typeof value === "string") {
    return value.trim().length > 0
  }

  return true
}

export const getIssuePrimaryText = (issue) => {
  if (!issue) {
    return "Issue details unavailable"
  }

  for (const field of FIRST_NON_EMPTY_FIELDS) {
    if (isPresent(issue[field])) {
      return typeof issue[field] === "string" ? issue[field].trim() : issue[field]
    }
  }

  if (isPresent(issue.clause)) {
    return `Clause: ${issue.clause}`
  }

  return "Issue details unavailable"
}

export const getIssueClause = (issue) => {
  if (!issue || !isPresent(issue.clause)) {
    return ""
  }
  return typeof issue.clause === "string" ? issue.clause.trim() : issue.clause
}

export const getIssueRecommendation = (issue) => {
  if (!issue) {
    return ""
  }

  if (isPresent(issue.recommendation)) {
    return typeof issue.recommendation === "string" ? issue.recommendation.trim() : issue.recommendation
  }

  if (isPresent(issue.remediation)) {
    return typeof issue.remediation === "string" ? issue.remediation.trim() : issue.remediation
  }

  return ""
}

export const getRecommendationLabel = (issue) => {
  if (!issue) {
    return ""
  }

  if (isPresent(issue.recommendation)) {
    return "Recommendation"
  }

  if (isPresent(issue.remediation)) {
    return "Remediation"
  }

  return ""
}

export const getIssuePagesText = (issue) => {
  if (!issue) {
    return "N/A"
  }

  if (Array.isArray(issue.pages) && issue.pages.length > 0) {
    return issue.pages.join(", ")
  }

  if (isPresent(issue.page)) {
    return issue.page
  }

  if (isPresent(issue.location)) {
    return issue.location
  }

  return "N/A"
}

export const buildDescriptionWithClause = (issue) => {
  const parts = [getIssuePrimaryText(issue)]
  const clause = getIssueClause(issue)
  if (clause) {
    parts.push(`Clause: ${clause}`)
  }
  return parts.filter(isPresent).join(" | ")
}

export const escapeCsvValue = (value) => {
  if (value === null || value === undefined) {
    return '""'
  }
  const stringValue = String(value).replace(/"/g, '""')
  return `"${stringValue}"`
}
