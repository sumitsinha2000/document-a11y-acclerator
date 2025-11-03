export default function StatCard({ label, value, change, changeLabel = "Vs last month", context }) {
  const isPositive = change >= 0
  const changeBgColor = isPositive ? "bg-green-500/10 dark:bg-green-500/20" : "bg-red-500/10 dark:bg-red-500/20"
  const changeTextColor = isPositive ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
      <div className="text-sm text-gray-500 dark:text-gray-400 mb-3">{label}</div>

      <div className="flex items-center gap-3">
        <div className="text-3xl font-bold text-gray-900 dark:text-white">{value}</div>
        {change !== undefined && (
          <span className={`px-2 py-1 rounded-md text-xs font-semibold ${changeBgColor} ${changeTextColor}`}>
            {isPositive ? "+" : ""}
            {change}%
          </span>
        )}
      </div>

      {context && (
        <div className="text-xs text-gray-500 dark:text-gray-400 mt-2">{context}</div>
      )}
    </div>
  )
}
