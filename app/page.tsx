"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

export default function Page() {
  const router = useRouter()

  useEffect(() => {
    // Since the frontend runs on a separate Vite server, we redirect to it
    window.location.href = "http://localhost:3000"
  }, [])

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
      <div className="container mx-auto px-4 py-16">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="text-5xl font-bold text-slate-900 dark:text-slate-50 mb-4">Document A11y Accelerator</h1>
          <p className="text-xl text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
            Automated PDF accessibility scanning and remediation tool with WCAG 2.1, PDF/UA, and Section 508 compliance
            validation
          </p>
        </div>

        {/* Features Grid */}
        <div className="grid md:grid-cols-3 gap-8 mb-16">
          <div className="bg-white dark:bg-slate-800 p-6 rounded-lg shadow-lg">
            <div className="w-12 h-12 bg-indigo-100 dark:bg-indigo-900 rounded-lg flex items-center justify-center mb-4">
              <svg
                className="w-6 h-6 text-indigo-600 dark:text-indigo-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <h3 className="text-xl font-semibold text-slate-900 dark:text-slate-50 mb-2">Comprehensive Scanning</h3>
            <p className="text-slate-600 dark:text-slate-400">
              Built-in WCAG 2.1 and PDF/UA-1 validator with no external dependencies required
            </p>
          </div>

          <div className="bg-white dark:bg-slate-800 p-6 rounded-lg shadow-lg">
            <div className="w-12 h-12 bg-green-100 dark:bg-green-900 rounded-lg flex items-center justify-center mb-4">
              <svg
                className="w-6 h-6 text-green-600 dark:text-green-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h3 className="text-xl font-semibold text-slate-900 dark:text-slate-50 mb-2">Automated Fixes</h3>
            <p className="text-slate-600 dark:text-slate-400">
              Apply automated fixes or use manual editing tools to remediate accessibility issues
            </p>
          </div>

          <div className="bg-white dark:bg-slate-800 p-6 rounded-lg shadow-lg">
            <div className="w-12 h-12 bg-purple-100 dark:bg-purple-900 rounded-lg flex items-center justify-center mb-4">
              <svg
                className="w-6 h-6 text-purple-600 dark:text-purple-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"
                />
              </svg>
            </div>
            <h3 className="text-xl font-semibold text-slate-900 dark:text-slate-50 mb-2">Batch Processing</h3>
            <p className="text-slate-600 dark:text-slate-400">
              Process multiple PDFs at once with comprehensive history tracking and reporting
            </p>
          </div>
        </div>

        {/* CTA Section */}
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl p-8 text-center">
          <h2 className="text-3xl font-bold text-slate-900 dark:text-slate-50 mb-4">Get Started</h2>
          <p className="text-slate-600 dark:text-slate-400 mb-6 max-w-2xl mx-auto">
            To use the Document A11y Accelerator, you need to run both the frontend and backend servers locally.
          </p>

          <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-6 text-left max-w-3xl mx-auto mb-6">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-50 mb-3">Quick Start:</h3>
            <div className="space-y-3 text-sm">
              <div>
                <p className="text-slate-700 dark:text-slate-300 font-medium mb-1">1. Start the Backend (Flask):</p>
                <code className="block bg-slate-800 dark:bg-slate-950 text-slate-100 p-2 rounded">
                  cd backend && python app.py
                </code>
              </div>
              <div>
                <p className="text-slate-700 dark:text-slate-300 font-medium mb-1">
                  2. Start the Frontend (React + Vite):
                </p>
                <code className="block bg-slate-800 dark:bg-slate-950 text-slate-100 p-2 rounded">
                  cd frontend && npm run dev
                </code>
              </div>
              <div>
                <p className="text-slate-700 dark:text-slate-300 font-medium mb-1">3. Access the application:</p>
                <code className="block bg-slate-800 dark:bg-slate-950 text-slate-100 p-2 rounded">
                  http://localhost:3000
                </code>
              </div>
            </div>
          </div>

          <a
            href="https://github.com/your-repo/document-a11y-accelerator"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-6 py-3 rounded-lg transition-colors"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path
                fillRule="evenodd"
                d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                clipRule="evenodd"
              />
            </svg>
            View on GitHub
          </a>
        </div>

        {/* Standards Section */}
        <div className="mt-16 text-center">
          <h3 className="text-2xl font-bold text-slate-900 dark:text-slate-50 mb-6">Accessibility Standards</h3>
          <div className="flex flex-wrap justify-center gap-4">
            <span className="bg-white dark:bg-slate-800 px-4 py-2 rounded-full text-sm font-medium text-slate-700 dark:text-slate-300 shadow">
              WCAG 2.1
            </span>
            <span className="bg-white dark:bg-slate-800 px-4 py-2 rounded-full text-sm font-medium text-slate-700 dark:text-slate-300 shadow">
              PDF/UA-1
            </span>
            <span className="bg-white dark:bg-slate-800 px-4 py-2 rounded-full text-sm font-medium text-slate-700 dark:text-slate-300 shadow">
              Section 508
            </span>
          </div>
        </div>
      </div>
    </main>
  )
}
