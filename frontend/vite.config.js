import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The UI JSX files reference a GLOBAL `React` (no imports) — bootstrap-globals.js sets
// window.React before any component evaluates. We pin the CLASSIC JSX runtime EVERYWHERE
// (dev server, production build, AND Vitest) so JSX always compiles to `React.createElement(...)`
// against that one global — eliminating any dev-vs-prod runtime divergence (audit DEV-1).
// Why not the automatic runtime: its Babel transform emits a CJS `require("react/jsx-dev-runtime")`
// that the rolldown-vite *dev* server does not rewrite to ESM, so `npm run dev` blank-screened
// with "require is not defined"; classic sidesteps that with no import at all. Vitest (jsdom) has
// no bootstrap-globals, so it gets the global React from `./vitest.setup.js`.
export default defineConfig({
  plugins: [react({ jsxRuntime: 'classic', include: [/\.jsx?$/] })],
  server: {
    port: 5173,
    // The Flask BFF API (webapi) runs on :8000 in dev; prod serves SPA + /api
    // from the same origin (one Cloud Run service), so no CORS anywhere.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  // `vite preview` (serving the built dist) mirrors the dev proxy, so a production
  // build can be smoke-tested against the local webapi the same way `npm run dev` is.
  preview: {
    port: 4173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  // maplibre runs geojson-vt in a MODULE worker: it calls `new Worker(url, {type:'module'})`
  // unless the URL ends in `.cjs`. Vite's default worker format is `iife`, which would hand
  // that constructor a classic script. Emitting ES keeps the two halves in agreement.
  // BrazilChoropleth imports the worker with `?worker&url` and passes it to
  // `maplibregl.setWorkerUrl()`; see the comment there for why the plain `?url` form fails.
  worker: { format: 'es' },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // Split the heavy vendor code into separate, long-lived cacheable chunks so
    // the app shell isn't a single 1.6MB file: Plotly (~1MB) and React load in
    // parallel and stay cached across app-code deploys.
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/plotly.js')) return 'plotly';
          if (id.match(/node_modules\/(react|react-dom|scheduler)\//)) return 'react';
          return undefined;
        },
      },
    },
    chunkSizeWarningLimit: 1200, // Plotly is legitimately ~1MB; don't warn on it
  },
  // Vitest reads this `test` block from the Vite config. jsdom gives the data-layer
  // modules a real `window`; `vitest.setup.js` then sets the window.React/ReactDOM globals
  // the UI modules (and the classic JSX runtime) rely on — mirroring bootstrap-globals.js.
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
    globals: false,
    restoreMocks: true,
    // Coverage gate (checked under `--coverage`, i.e. `npm test` / CI; `npm run
    // test:fast` stays uninstrumented for the inner loop). The data/contract layer,
    // the view render-smoke-tests, and the AppShell chrome test reach ~88% of src/ui;
    // the Plotly chart wrappers (src/charts) are render-smoke-tested only (~64%),
    // since fully driving Plotly in jsdom is brittle. Whole-src is ~83.5% stmts /
    // 86% lines / 81% funcs / 70% branches — thresholds sit ~2% under that so a
    // regression (a new untested view/helper) fails CI without being knife-edge.
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{js,jsx}'],
      thresholds: {
        statements: 81,
        lines: 84,
        functions: 79,
        branches: 67,
      },
    },
  },
})
