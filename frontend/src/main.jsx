import ReactDOM from "react-dom/client"
import App from "./App"
import "./index.css"

console.log("Application starting...")

try {
  const root = ReactDOM.createRoot(document.getElementById("root"))
  console.log("Root element found, rendering App...")
  root.render(<App />)
  console.log("App rendered successfully")
} catch (error) {
  console.error("Fatal error during app initialization:", error)
  document.body.innerHTML = `
    <div style="display: flex; align-items: center; justify-center; min-height: 100vh; background: #f1f5f9; padding: 20px;">
      <div style="max-width: 600px; background: white; border-radius: 12px; padding: 32px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <h1 style="color: #dc2626; font-size: 24px; margin-bottom: 16px;">Application Failed to Start</h1>
        <p style="color: #64748b; margin-bottom: 16px;">The application encountered a fatal error during initialization.</p>
        <pre style="background: #fee2e2; border: 1px solid #fecaca; border-radius: 6px; padding: 12px; overflow: auto; font-size: 12px; color: #991b1b;">${error.toString()}</pre>
        <button onclick="window.location.reload()" style="margin-top: 16px; width: 100%; padding: 12px; background: #4f46e5; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer;">Reload Page</button>
      </div>
    </div>
  `
}
