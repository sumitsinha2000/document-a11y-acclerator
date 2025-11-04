"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"

export default function Page() {
  const [isClient, setIsClient] = useState(false)
  const router = useRouter()

  useEffect(() => {
    setIsClient(true)
  }, [])

  const frontendUrl = process.env.NEXT_PUBLIC_FRONTEND_URL || "http://localhost:3000"
  const isProduction = process.env.NODE_ENV === "production"

  if (!isClient) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <p className="text-slate-600 dark:text-slate-400">Loading Document A11y Accelerator...</p>
        </div>
      </div>
    )
  }

  if (isProduction) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
        <div className="container mx-auto px-4 py-16">
          <div className="text-center mb-16">
            <h1 className="text-5xl font-bold text-slate-900 dark:text-slate-50 mb-4">Document A11y Accelerator</h1>
            <p className="text-xl text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
              Automated PDF accessibility scanning and remediation tool with WCAG 2.1, PDF/UA, and Section 508
              compliance validation
            </p>
          </div>

          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl p-8 max-w-4xl mx-auto">
            <h2 className="text-3xl font-bold text-slate-900 dark:text-slate-50 mb-6">Production Deployment</h2>
            <div className="space-y-6 text-slate-700 dark:text-slate-300">
              <p>
                This application requires both frontend and backend services to be running. To deploy to production:
              </p>

              <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-6">
                <h3 className="text-lg font-semibold mb-4">Option 1: Deploy Backend to Vercel</h3>
                <ol className="list-decimal list-inside space-y-2 text-sm">
                  <li>Deploy your Flask backend as a Vercel serverless function</li>
                  <li>
                    Update the{" "}
                    <code className="bg-slate-200 dark:bg-slate-800 px-2 py-1 rounded">NEXT_PUBLIC_BACKEND_URL</code>{" "}
                    environment variable
                  </li>
                  <li>Configure CORS settings in your backend</li>
                </ol>
              </div>

              <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-6">
                <h3 className="text-lg font-semibold mb-4">Option 2: Use External Backend</h3>
                <ol className="list-decimal list-inside space-y-2 text-sm">
                  <li>Deploy your Flask backend to a hosting service (Railway, Render, etc.)</li>
                  <li>Set the backend URL in Vercel environment variables</li>
                  <li>Ensure proper CORS configuration</li>
                </ol>
              </div>

              <div className="bg-indigo-50 dark:bg-indigo-950 border border-indigo-200 dark:border-indigo-800 rounded-lg p-6">
                <h3 className="text-lg font-semibold text-indigo-900 dark:text-indigo-100 mb-3">
                  Environment Variables Required:
                </h3>
                <ul className="space-y-2 text-sm font-mono">
                  <li className="bg-white dark:bg-slate-900 p-2 rounded">
                    NEXT_PUBLIC_BACKEND_URL=https://your-backend.vercel.app
                  </li>
                  <li className="bg-white dark:bg-slate-900 p-2 rounded">
                    NEON_DATABASE_URL=your-database-connection-string
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </main>
    )
  }

  return (
    <div className="fixed inset-0 w-full h-full">
      <iframe
        src={frontendUrl}
        className="w-full h-full border-0"
        title="Document A11y Accelerator"
        sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-modals"
      />
    </div>
  )
}
