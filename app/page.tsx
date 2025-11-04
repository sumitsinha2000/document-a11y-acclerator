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
    <main className="flex items-center justify-center min-h-screen bg-background">
      <div className="max-w-md mx-auto px-6 text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
        <h1 className="text-2xl font-bold text-foreground mb-2">Redirecting to Application...</h1>
        <p className="text-muted-foreground">
          If you are not redirected automatically,{" "}
          <a href="http://localhost:3000" className="text-indigo-600 hover:underline">
            click here
          </a>
          .
        </p>
      </div>
    </main>
  )
}
