import path from 'node:path'
import process from 'node:process'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import svgr from 'vite-plugin-svgr'
import jsx from '@svgr/plugin-jsx'
import { defineConfig, loadEnv } from 'vite'

function scopeSvg(code, _config, state) {
  const slug = path
    .basename(state.filePath, '.svg')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
  return code
    .replace(/\sid="Layer_1"/g, '')
    .replace(/\bcls-(\d+)\b/g, `${slug}-cls-$1`)
    .replace(/\bid="([^"]+)"/g, `id="${slug}-$1"`)
    .replace(/url\(#([^)]+)\)/g, `url(#${slug}-$1)`)
    .replace(/href="#([^"]+)"/g, `href="#${slug}-$1"`)
}

function apiPreconnectPlugin(apiUrl) {
  let origin = null
  try {
    if (apiUrl && /^https?:\/\//i.test(apiUrl)) {
      origin = new URL(apiUrl).origin
    }
  } catch {
    origin = null
  }
  if (!origin) return { name: 'ongsho-api-preconnect' }
  return {
    name: 'ongsho-api-preconnect',
    transformIndexHtml(html) {
      const tag = `<link rel="preconnect" href="${origin}" crossorigin />`
      return html.replace('</head>', `    ${tag}\n  </head>`)
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiUrl = env.VITE_API_URL

  const proxyApi = {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  }

  return {
    server: { proxy: proxyApi },
    preview: { proxy: proxyApi },
    plugins: [
      react(),
      tailwindcss(),
      svgr({ svgrOptions: { plugins: [scopeSvg, jsx] } }),
      apiPreconnectPlugin(apiUrl),
    ],
    resolve: {
      alias: { '@': path.resolve(import.meta.dirname, 'src') },
    },
    esbuild: {
      jsx: 'automatic',
      drop: mode === 'production' ? ['console', 'debugger'] : [],
    },
    build: {
      sourcemap: false,
      minify: true,
      target: 'es2022',
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return undefined
            if (id.includes('recharts') || id.includes('d3-')) return 'vendor-recharts'
            if (id.includes('@tanstack/react-query')) return 'vendor-react-query'
            if (id.includes('react-router')) return 'vendor-react-router'
            if (id.includes('axios')) return 'vendor-axios'
            if (
              id.includes('/react-dom/') ||
              id.includes('/react/') ||
              id.includes('scheduler') ||
              id.includes('use-sync-external-store')
            ) {
              return 'vendor-react'
            }
            return undefined
          },
        },
      },
    },
    test: {
      environment: 'node',
      include: ['src/**/*.test.{js,jsx}'],
      setupFiles: ['./src/test/setup.js'],
      environmentMatchGlobs: [['**/*.test.jsx', 'jsdom']],
    },
  }
})