import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')
const distDir = path.join(root, 'dist')
const indexPath = path.join(distDir, 'index.html')

function fail(msg) {
  console.error(`check:dist failed: ${msg}`)
  process.exit(1)
}

if (!fs.existsSync(indexPath)) {
  fail('dist/index.html not found — run npm run build first')
}

const html = fs.readFileSync(indexPath, 'utf8')

if (/<script(?![^>]*\bsrc=)[^>]*>[\s\S]*?<\/script>/i.test(html)) {
  fail('dist/index.html contains an inline <script> block (CSP script-src self only)')
}

if (/\son\w+\s*=/i.test(html)) {
  fail('dist/index.html contains an inline event handler attribute')
}

if (/https?:\/\//i.test(html)) {
  fail('dist/index.html contains an absolute http(s) URL')
}

console.log('check:dist ok')