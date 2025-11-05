import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import { terser } from "rollup-plugin-terser"   // 👈 add this import

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
    minify: false, 
    rollupOptions: {
      plugins: [
        terser({
          compress: {
            passes: 2,
          },
          mangle: true,
          format: {
            comments: false,
          },
          exclude: [/installHook\.js$/], // 👈 critical line
        }),
      ],
      output: {
        manualChunks: undefined,
      },
    },
    chunkSizeWarningLimit: 1500,
  },
  optimizeDeps: {
    include: ["react", "react-dom", "axios"],
  },
})
