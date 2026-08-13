import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],

  root: path.resolve(__dirname, 'src/frontend'),

  envDir: path.resolve(__dirname),

  server: {
    port: 5173,
  },
})