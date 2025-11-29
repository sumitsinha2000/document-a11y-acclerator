import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts"

export default function IssueStats({ results }) {

  // Prepare data for bar chart - issues by category
  const categoryData = Object.entries(results || {}).map(([category, issues]) => {
    const labels = {
      missingMetadata: "Metadata",
      untaggedContent: "Tagging",
      missingAltText: "Alt Text",
      poorContrast: "Contrast",
      missingLanguage: "Language",
      formIssues: "Forms",
      tableIssues: "Tables",
      linkIssues: "Link Purpose",
    }
    return {
      name: labels[category] || category,
      count: issues.length,
    }
  })

  // Prepare data for severity pie chart
  const severityData = []
  let highCount = 0
  let mediumCount = 0
  let lowCount = 0

  Object.values(results || {}).forEach((issues) => {
    issues.forEach((issue) => {
      if (issue.severity === "high") highCount++
      else if (issue.severity === "medium") mediumCount++
      else if (issue.severity === "low") lowCount++
    })
  })

  const severityChartData = [
    { name: "High", value: highCount, color: "#ef4444" },
    { name: "Medium", value: mediumCount, color: "#f59e0b" },
    { name: "Low", value: lowCount, color: "#10b981" },
  ].filter((item) => item.value > 0)

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6">
        <h4 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Issues by Category</h4>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={categoryData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
            <XAxis dataKey="name" stroke="#9ca3af" tick={{ fill: "#9ca3af" }} />
            <YAxis stroke="#9ca3af" tick={{ fill: "#9ca3af" }} />
            <Tooltip
              contentStyle={{
                backgroundColor: "#1f2937",
                border: "1px solid #374151",
                borderRadius: "0.5rem",
                color: "#f3f4f6",
              }}
              labelStyle={{ color: "#f3f4f6" }}
              itemStyle={{ color: "#f3f4f6" }}
            />
            <Bar dataKey="count" fill="#3b82f6" radius={[8, 8, 0, 0]} onMouseEnter={() => { }} tabIndex={0} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6">
        <h4 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Issues by Severity</h4>
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={severityChartData}
              cx="50%"
              cy="50%"
              labelLine={false}
              label={({ name, value }) => `${name}: ${value}`}
              outerRadius={80}
              fill="#8884d8"
              dataKey="value"
            >
              {severityChartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            {/* <Tooltip
              contentStyle={{
                backgroundColor: "#1f2937",
                border: "1px solid #374151",
                borderRadius: "0.5rem",
                color: "#f3f4f6",
              }}
              labelStyle={{ color: "#f3f4f6" }}
              itemStyle={{ color: "#f3f4f6" }}
            /> */}
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const { name, value } = payload[0];
                  return (
                    <div
                      style={{
                        backgroundColor: "#1f2937",
                        border: "1px solid #374151",
                        borderRadius: "0.5rem",
                        color: "#f3f4f6",
                        padding: "0.5rem 0.75rem",
                      }}
                    >
                      <p>{`${name}: ${value}`}</p>
                    </div>
                  );
                }
                return null;
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
