import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],

  // Keep lowercase `src/frontend` so deployment works consistently on
  // case-sensitive Linux filesystems (Railway/Docker).
  root: path.resolve(import.meta.dirname, 'src/frontend'),

  envDir: path.resolve(import.meta.dirname),

  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
