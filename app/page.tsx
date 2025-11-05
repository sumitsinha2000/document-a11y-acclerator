export default function Page() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-900 to-slate-900 flex items-center justify-center p-4">
      <div className="max-w-4xl w-full text-center space-y-8">
        {/* Logo */}
        <div className="flex justify-center">
          <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-2xl">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-10 w-10 text-white"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
              <path d="M14 2v4a2 2 0 0 0 2 2h4" />
            </svg>
          </div>
        </div>

        {/* Title */}
        <div className="space-y-4">
          <h1 className="text-5xl md:text-6xl font-bold text-white">Document A11y Accelerator</h1>
          <p className="text-xl md:text-2xl text-indigo-200">PDF Accessibility Scanner & Remediation Tool</p>
        </div>

        {/* Description */}
        <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 border border-white/20">
          <p className="text-lg text-white/90 leading-relaxed">
            This application is built with React + Vite and is configured to run as the main frontend. The React
            application includes a professional loading screen with feature showcase.
          </p>
        </div>

        {/* Setup Instructions */}
        <div className="bg-slate-800/50 backdrop-blur-lg rounded-2xl p-8 border border-slate-700 text-left">
          <h2 className="text-2xl font-bold text-white mb-4">Development Setup</h2>
          <div className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold text-indigo-300 mb-2">1. Start the Backend</h3>
              <code className="block bg-slate-900 text-green-400 p-3 rounded-lg font-mono text-sm">
                cd backend && python app.py
              </code>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-indigo-300 mb-2">2. Start the Frontend</h3>
              <code className="block bg-slate-900 text-green-400 p-3 rounded-lg font-mono text-sm">
                cd frontend && npm run dev
              </code>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-indigo-300 mb-2">3. Access the Application</h3>
              <p className="text-white/80">
                Open{" "}
                <a href="http://localhost:3000" className="text-indigo-400 hover:text-indigo-300 underline">
                  http://localhost:3000
                </a>{" "}
                in your browser
              </p>
            </div>
          </div>
        </div>

        {/* Production Note */}
        <div className="bg-indigo-500/20 backdrop-blur-lg rounded-2xl p-6 border border-indigo-400/30">
          <p className="text-indigo-200">
            <strong className="text-white">Production Deployment:</strong> The frontend is configured to deploy directly
            to Vercel. See DEPLOYMENT.md for details.
          </p>
        </div>
      </div>
    </div>
  )
}
