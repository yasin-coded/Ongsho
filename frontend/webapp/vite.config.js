import path from 'node:path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import svgr from 'vite-plugin-svgr'
import jsx from '@svgr/plugin-jsx'
import { defineConfig } from 'vite'

// The supplied Illustrator SVGs all reuse `.cls-N` classes and `linear-gradient`
// ids, so every file is scoped to its own name before it is inlined.
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

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    svgr({ svgrOptions: { plugins: [scopeSvg, jsx] } }),
  ],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  esbuild: {
    jsx: 'automatic',
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{js,jsx}'],
    setupFiles: ['./src/test/setup.js'],
    environmentMatchGlobs: [['**/*.test.jsx', 'jsdom']],
  },
})
