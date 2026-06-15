// Build pre-rendered HTML for all benchmark problem descriptions.
// Converts 问题描述.md → 问题描述.html with KaTeX math pre-rendered.
// Run: node scripts/build-benchmark-html.js

import { readFileSync, readdirSync, writeFileSync, existsSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import katex from 'katex'
import MarkdownIt from 'markdown-it'

const __dirname = dirname(fileURLToPath(import.meta.url))
const benchDir = join(__dirname, '..', 'learning', 'benchmarks')

const md = new MarkdownIt({ html: true, linkify: true, typographer: true })

function renderMath(text) {
  // Display math $$...$$
  let result = text.replace(/\$\$([\s\S]*?)\$\$/g, (_, formula) => {
    try {
      return katex.renderToString(formula.trim(), { displayMode: true, throwOnError: false })
    } catch {
      return `<pre class="katex-error">$${formula}$$</pre>`
    }
  })
  // Inline math $...$
  result = result.replace(/(?<!\$)\$(?!\$)([^$\n]+?)\$(?!\$)/g, (_, formula) => {
    try {
      return katex.renderToString(formula.trim(), { displayMode: false, throwOnError: false })
    } catch {
      return `$${formula}$`
    }
  })
  return result
}

const htmlWrapper = (title, body) => `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<style>
  :root { color-scheme: dark; }
  body {
    max-width: 960px; margin: 0 auto; padding: 40px 24px;
    background: #0f1116; color: #c4cad6;
    font-family: 'Microsoft YaHei', 'Segoe UI', system-ui, sans-serif;
    font-size: 0.92rem; line-height: 1.85;
  }
  h1 { font-size: 1.4rem; color: #edf2fb; border-bottom: 1px solid #2b3240; padding-bottom: 10px; }
  h2 { font-size: 1.1rem; color: #edf2fb; border-left: 3px solid #8b5cf6; padding-left: 12px; margin-top: 32px; }
  h3 { font-size: 0.95rem; color: #edf2fb; margin-top: 22px; }
  strong { color: #edf2fb; }
  a { color: #a78bfa; }
  code { background: #11141a; padding: 2px 7px; border-radius: 4px; font-size: 0.88em; color: #38bdf8; }
  pre { background: #11141a; border: 1px solid #2b3240; border-radius: 8px; padding: 16px 20px; overflow-x: auto; }
  pre code { background: none; padding: 0; }
  table { width: 100%; border-collapse: collapse; margin: 16px 0; border: 1px solid #2b3240; border-radius: 8px; overflow: hidden; }
  th { background: #151922; color: #9ca6b8; font-weight: 700; padding: 10px 14px; text-align: left; font-size: 0.72rem; text-transform: uppercase; }
  td { padding: 8px 14px; border-bottom: 1px solid #242936; }
  tr:nth-child(even) td { background: rgba(255,255,255,0.015); }
  blockquote { border-left: 3px solid #8b5cf6; margin: 16px 0; padding: 12px 18px; background: rgba(139,92,246,0.12); border-radius: 0 8px 8px 0; }
  hr { border: none; border-top: 1px solid #242936; margin: 28px 0; }
  ul, ol { padding-left: 24px; }
  li { margin: 5px 0; line-height: 1.75; }
  .katex { color: #c4cad6; }
  .katex-error { color: #ef4444; font-family: monospace; }
</style>
</head>
<body>
${body}
</body>
</html>`

let count = 0
for (const entry of readdirSync(benchDir)) {
  const caseDir = join(benchDir, entry)
  if (!existsSync(join(caseDir, '问题描述.md')) && !existsSync(join(caseDir, 'problem.md'))) continue

  const mdPath = existsSync(join(caseDir, '问题描述.md'))
    ? join(caseDir, '问题描述.md')
    : join(caseDir, 'problem.md')

  const mdText = readFileSync(mdPath, 'utf-8')
  const mathDone = renderMath(mdText)
  const htmlBody = md.render(mathDone)
  const htmlPath = join(caseDir, '问题描述.html')

  writeFileSync(htmlPath, htmlWrapper(entry, htmlBody), 'utf-8')
  console.log(`  ✓ ${entry}/问题描述.html`)
  count++
}

console.log(`\nDone — ${count} HTML files generated.`)
