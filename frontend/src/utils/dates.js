const ISO_WITHOUT_TZ =
  /^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?)?$/

const safeParseNumber = (value, fallback = 0) => {
  const parsed = Number(value)
  return Number.isNaN(parsed) ? fallback : parsed
}

const parseIsoWithoutTimezone = (value) => {
  const match = value.match(ISO_WITHOUT_TZ)
  if (!match) {
    return null
  }

  const [, year, month, day, hours = "0", minutes = "0", seconds = "0", fraction = "0"] = match
  const milliseconds = safeParseNumber((fraction + "000").slice(0, 3))

  const date = new Date(
    Date.UTC(
      safeParseNumber(year),
      safeParseNumber(month) - 1,
      safeParseNumber(day),
      safeParseNumber(hours),
      safeParseNumber(minutes),
      safeParseNumber(seconds),
      milliseconds
    )
  )

  return Number.isNaN(date.getTime()) ? null : date
}

const containsTimezoneIndicator = (value) => /[Zz]|[+\-]\d{2}:?\d{2}$/.test(value)

export const parseBackendDate = (value) => {
  if (value instanceof Date) {
    return value
  }

  if (typeof value === "number") {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? null : date
  }

  if (typeof value !== "string") {
    return null
  }

  const trimmed = value.trim()
  if (!trimmed) {
    return null
  }

  if (containsTimezoneIndicator(trimmed)) {
    const parsed = new Date(trimmed)
    return Number.isNaN(parsed.getTime()) ? null : parsed
  }

  const isoParsed = parseIsoWithoutTimezone(trimmed)
  if (isoParsed) {
    return isoParsed
  }

  const fallback = new Date(trimmed)
  return Number.isNaN(fallback.getTime()) ? null : fallback
}
