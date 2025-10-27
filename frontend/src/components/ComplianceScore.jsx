export default function ComplianceScore({ score }) {
  const getScoreColor = (score) => {
    if (score >= 80)
      return { bg: "bg-green-100 dark:bg-green-900", text: "text-green-600 dark:text-green-400", stroke: "#10b981" }
    if (score >= 60)
      return { bg: "bg-blue-100 dark:bg-blue-900", text: "text-blue-600 dark:text-blue-400", stroke: "#3b82f6" }
    if (score >= 40)
      return { bg: "bg-yellow-100 dark:bg-yellow-900", text: "text-yellow-600 dark:text-yellow-400", stroke: "#f59e0b" }
    return { bg: "bg-red-100 dark:bg-red-900", text: "text-red-600 dark:text-red-400", stroke: "#ef4444" }
  }

  const getScoreLabel = (score) => {
    if (score >= 80) return "Excellent"
    if (score >= 60) return "Good"
    if (score >= 40) return "Fair"
    return "Poor"
  }

  const colors = getScoreColor(score)
  const label = getScoreLabel(score)
  const circumference = 2 * Math.PI * 45
  const strokeDashoffset = circumference - (score / 100) * circumference

  return (
    <div className={`${colors.bg} rounded-2xl p-8 text-center`}>
      <div className="relative inline-block">
        <svg viewBox="0 0 100 100" className="w-48 h-48 transform -rotate-90">
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="currentColor"
            strokeWidth="8"
            className="text-gray-200 dark:text-gray-700"
          />
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke={colors.stroke}
            strokeWidth="8"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            className="transition-all duration-1000 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className={`text-5xl font-bold ${colors.text}`}>{Math.round(score)}</div>
          <div className={`text-2xl ${colors.text}`}>%</div>
        </div>
      </div>
      <div className={`text-2xl font-bold mt-4 ${colors.text}`}>{label}</div>
      <div className="text-sm text-gray-600 dark:text-gray-300 mt-2">Accessibility Compliance</div>
    </div>
  )
}
