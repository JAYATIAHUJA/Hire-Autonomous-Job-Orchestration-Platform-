import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend origin the dev server proxies `/api` to. Defaults to the local
// backend on :8000; override with VITE_API_PROXY when it runs elsewhere.
const apiTarget = process.env.VITE_API_PROXY || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': apiTarget,
    },
  },
})
