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
            // Don't split React separately - keep it with vendor to avoid initialization issues
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
            // All other node_modules including React
            return "vendor"
          }
        },
      },
    },
    chunkSizeWarningLimit: 1000,
  },
  optimizeDeps: {
    include: ["react", "react-dom", "axios"],
  },
})
