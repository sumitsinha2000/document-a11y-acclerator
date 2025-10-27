export default function Page() {
  return (
    <main className="flex items-center justify-center min-h-screen bg-background">
      <div className="max-w-2xl mx-auto px-6 text-center">
        <h1 className="text-4xl font-bold text-foreground mb-4">Document a11y Accelerator</h1>
        <p className="text-lg text-muted-foreground mb-8">Welcome to your accessibility documentation tool</p>

        <div className="bg-card border border-border rounded-lg p-8 mb-8 text-left">
          <h2 className="text-2xl font-semibold text-foreground mb-4">Project Setup</h2>
          <p className="text-muted-foreground mb-6">
            This project consists of two separate applications that work together:
          </p>

          <div className="space-y-6">
            <div>
              <h3 className="text-xl font-semibold text-foreground mb-2">1. Flask Backend</h3>
              <p className="text-muted-foreground mb-3">Handles PDF processing and accessibility analysis</p>
              <pre className="bg-muted p-4 rounded text-sm text-foreground overflow-x-auto mb-2">
                <code>
                  cd backend{"\n"}pip install -r requirements.txt{"\n"}python app.py
                </code>
              </pre>
              <p className="text-sm text-muted-foreground">Runs on http://localhost:5000</p>
            </div>

            <div>
              <h3 className="text-xl font-semibold text-foreground mb-2">2. React + Vite Frontend</h3>
              <p className="text-muted-foreground mb-3">Interactive dashboard for uploading and analyzing PDFs</p>
              <pre className="bg-muted p-4 rounded text-sm text-foreground overflow-x-auto mb-2">
                <code>
                  cd frontend{"\n"}npm install{"\n"}npm run dev
                </code>
              </pre>
              <p className="text-sm text-muted-foreground">Runs on http://localhost:3000</p>
            </div>
          </div>
        </div>

        <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg p-6 text-left">
          <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-100 mb-2">Features</h3>
          <ul className="text-blue-800 dark:text-blue-200 space-y-2">
            <li>✓ PDF upload with drag-and-drop support</li>
            <li>✓ Comprehensive accessibility scanning (WCAG 2.1)</li>
            <li>✓ Interactive report visualization with charts</li>
            <li>✓ Multi-format export (JSON, CSV, HTML)</li>
            <li>✓ Scan history management</li>
            <li>✓ OCR detection and auto-fix suggestions</li>
          </ul>
        </div>
      </div>
    </main>
  )
}
