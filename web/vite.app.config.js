import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The store app's build: the driver app alone, from app/index.html into dist-app, which is what
// Capacitor copies into the Android and iOS projects. Relative paths, because the pages are opened
// from the phone's own storage, not from a web server's root.
export default defineConfig({
  root: resolve(__dirname, 'app'),
  base: './',
  publicDir: resolve(__dirname, 'public'),
  plugins: [react()],
  build: { outDir: resolve(__dirname, 'dist-app'), emptyOutDir: true },
})
