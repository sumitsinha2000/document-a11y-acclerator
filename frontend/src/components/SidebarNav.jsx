"use client"

import { useState, useEffect } from "react"

export default function SidebarNav({ isOpen = true }) {
  const [activeSection, setActiveSection] = useState("overview")

  const sections = [
    { id: "overview", label: "Overview", icon: "📊" },
    { id: "stats", label: "Issue Statistics", icon: "📈" },
    { id: "issues", label: "Issues List", icon: "📋" },
    { id: "fixes", label: "Fix Suggestions", icon: "🔧" },
    { id: "export", label: "Export Options", icon: "⬇" },
  ]

  useEffect(() => {
    const handleScroll = () => {
      const scrollPosition = window.scrollY + 150

      for (const section of sections) {
        const element = document.getElementById(section.id)
        if (element) {
          const { offsetTop, offsetHeight } = element
          if (scrollPosition >= offsetTop && scrollPosition < offsetTop + offsetHeight) {
            setActiveSection(section.id)
            break
          }
        }
      }
    }

    window.addEventListener("scroll", handleScroll)
    return () => window.removeEventListener("scroll", handleScroll)
  }, [])

  const scrollToSection = (sectionId) => {
    const element = document.getElementById(sectionId)
    if (element) {
      const offset = 100
      const elementPosition = element.getBoundingClientRect().top
      const offsetPosition = elementPosition + window.pageYOffset - offset

      window.scrollTo({
        top: offsetPosition,
        behavior: "smooth",
      })
    }
  }

  return (
    <nav
      className={`fixed left-0 top-14 h-[calc(100vh-3.5rem)] bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 overflow-y-auto transition-transform duration-300 ease-in-out z-40 ${
        isOpen ? "translate-x-0" : "-translate-x-full"
      }`}
      style={{ width: "240px" }}
      aria-label="Report navigation"
    >
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          Report Sections
        </p>
      </div>
      <ul className="p-3 space-y-1">
        {sections.map((section) => (
          <li key={section.id}>
            <button
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${
                activeSection === section.id
                  ? "bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 font-medium"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50"
              }`}
              onClick={() => scrollToSection(section.id)}
              aria-current={activeSection === section.id ? "true" : undefined}
            >
              <span className="text-lg">
                {section.icon}
              </span>
              <span>{section.label}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  )
}
