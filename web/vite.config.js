import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const require = createRequire(import.meta.url)

// MapLibre loads its tile-parsing worker from a URL it builds AT RUNTIME out of
// `import.meta.url` - roughly `new URL('./maplibre-gl-worker.mjs', <this bundle's own URL>)`.
// A bundler cannot see that, so Vite emits nothing for it and the browser asks the server for
// /assets/maplibre-gl-worker.mjs, which is not there: "Worker failed to load."
//
// So it is copied beside the bundle and pointed at explicitly with setWorkerUrl (see
// FleetMap.jsx). Emitted as .js rather than .mjs on purpose: nginx has no MIME mapping for
// .mjs and serves it as application/octet-stream, which a browser will not run as a worker.
function maplibreWorker() {
  return {
    name: 'maplibre-worker',
    apply: 'build',
    generateBundle() {
      const from = require.resolve('maplibre-gl/dist/maplibre-gl-worker.mjs')
      this.emitFile({
        type: 'asset',
        fileName: 'assets/maplibre-gl-worker.js',
        source: readFileSync(from, 'utf8'),
      })
    },
  }
}

// In dev the API runs on :8000 and Vite proxies /api to it, so the browser sees one origin.
export default defineConfig({
  plugins: [react(), maplibreWorker()],
  server: {
    port: 5173,
    proxy: { '/api': process.env.API_URL || 'http://localhost:8000' },
  },
})
