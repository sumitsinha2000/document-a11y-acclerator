import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: process.env.VITE_BACKEND_URL || "http://localhost:5000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, "/api"),
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    minify: "esbuild",
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            // Split React and React-DOM separately
            if (id.includes("react") || id.includes("react-dom")) {
              return "react-vendor"
            }
            // Split PDF libraries
            if (id.includes("pdfjs") || id.includes("pdf-lib")) {
              return "pdf-libs"
            }
            // Split jsPDF and html2canvas
            if (id.includes("jspdf") || id.includes("html2canvas")) {
              return "export-libs"
            }
            // Split chart libraries
            if (id.includes("recharts") || id.includes("d3")) {
              return "chart-libs"
            }
            // Split axios
            if (id.includes("axios")) {
              return "axios"
            }
            // Split icons
            if (id.includes("lucide") || id.includes("react-icons")) {
              return "icons"
            }
            // All other node_modules
            return "vendor"
          }
        },
      },
    },
    chunkSizeWarningLimit: 600, // Lower threshold to catch large chunks earlier
  },
  optimizeDeps: {
    include: ["react", "react-dom", "axios"],
  },
})
