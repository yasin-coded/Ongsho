import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = path.join(path.dirname(fileURLToPath(import.meta.url)))

const DANGEROUS = [
  { pattern: /dangerouslySetInnerHTML/g, label: 'dangerouslySetInnerHTML' },
  { pattern: /\beval\s*\(/g, label: 'eval(' },
  { pattern: /new Function\s*\(/g, label: 'new Function(' },
  { pattern: /document\.write/g, label: 'document.write' },
  { pattern: /\.innerHTML\s*=/g, label: '.innerHTML assignment' },
]

const SESSION_KEY_OK = /ongsho:hasSession/

function walk(dir, out = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name)
    if (ent.isDirectory()) walk(p, out)
    else if (/\.(js|jsx)$/.test(ent.name) && !/\.test\.(js|jsx)$/.test(ent.name)) out.push(p)
  }
  return out
}

function storageViolations(text, file) {
  const hits = []
  const re = /(localStorage|sessionStorage)\.(getItem|setItem|removeItem)\(\s*['"]([^'"]+)['"]/g
  let m
  while ((m = re.exec(text))) {
    const key = m[3]
  if (m[1] === 'localStorage' && SESSION_KEY_OK.test(key)) continue
    hits.push(`${file}: forbidden storage key ${key}`)
  }
  return hits
}

describe('security static scan', () => {
  it('src has no dangerous DOM patterns', () => {
    const files = walk(SRC)
    const problems = []
    for (const file of files) {
      const text = fs.readFileSync(file, 'utf8')
      for (const { pattern, label } of DANGEROUS) {
        pattern.lastIndex = 0
        if (pattern.test(text)) problems.push(`${path.relative(SRC, file)}: ${label}`)
      }
      problems.push(...storageViolations(text, path.relative(SRC, file)))
    }
    expect(problems).toEqual([])
  })
})