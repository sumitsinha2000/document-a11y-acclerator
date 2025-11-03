"use client"

export default function Breadcrumb({ items }) {
  return (
    <nav className="mb-4" aria-label="Breadcrumb">
      <ol className="flex items-center gap-2 text-md">
        {items.map((item, index) => (
          <li key={index} className="flex items-center gap-2">
            {item.onClick ? (
              <>
                <button className="text-blue-600 dark:text-blue-400 hover:underline" onClick={item.onClick}>
                  {item.label}
                </button>
                {index < items.length - 1 && <span className="text-gray-400 dark:text-gray-600">/</span>}
              </>
            ) : (
              <span className="text-gray-700 dark:text-gray-300">{item.label}</span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  )
}
