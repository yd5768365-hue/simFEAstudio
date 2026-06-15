/** Markdown to HTML renderer for SimFEA Studio.
 *
 * Powered by markdown-it + KaTeX. Supports full CommonMark + tables,
 * linkify, typographer, and LaTeX math ($$ display / $ inline).
 * All renderers share the same heading anchor logic for TOC consistency.
 */

import katex from 'katex'
import MarkdownIt from 'markdown-it'

// ── Shared anchor ──

function anchor(text: string, idx: number): string {
  const a = text
    .toLowerCase()
    .replace(/`/g, '')
    .replace(/[^a-z0-9一-鿿]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return /[a-z0-9]/.test(a) ? a : `section-${idx + 1}`
}

// ── KaTeX math pre-processor ──

function renderMath(md: string): string {
  const replacements: string[] = []
  const stash = (html: string) => {
    const key = `@@SIMFEA_MATH_${replacements.length}@@`
    replacements.push(html)
    return key
  }

  // Display math $$...$$
  let result = md.replace(/\$\$([\s\S]*?)\$\$/g, (_match, formula: string) => {
    try {
      return stash(katex.renderToString(formula.trim(), { displayMode: true, throwOnError: false }))
    } catch {
      return stash(`<pre class="katex-error">$${escapeHtml(formula)}$$</pre>`)
    }
  })

  // Inline math $...$ (not $$, not inside code blocks or already rendered)
  result = result.replace(/(?<!\$)\$(?!\$)([^$\n]+?)\$(?!\$)/g, (_match, formula: string) => {
    try {
      return stash(katex.renderToString(formula.trim(), { displayMode: false, throwOnError: false }))
    } catch {
      return `$${escapeHtml(formula)}$`
    }
  })

  return createMd()
    .render(result)
    .replace(/@@SIMFEA_MATH_(\d+)@@/g, (_match, idx: string) => replacements[Number(idx)] ?? '')
}

// ── MarkdownIt factory ──

function createMd(): MarkdownIt {
  let headingIdx = 0

  const md = new MarkdownIt({
    html: false,
    breaks: false,
    linkify: true,
    typographer: true,
  })

  // Inject heading anchors matching the anchor() algorithm
  const defaultHeadingOpen =
    md.renderer.rules.heading_open ||
    ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

  md.renderer.rules.heading_open = (tokens, idx, options, env, self) => {
    const hToken = tokens[idx]
    const inlineToken = tokens[idx + 1]
    const text = inlineToken && inlineToken.type === 'inline' ? inlineToken.content : ''
    hToken.attrSet('id', anchor(text, headingIdx++))
    return defaultHeadingOpen(tokens, idx, options, env, self)
  }

  return md
}

// ── Public API ──

export function renderMarkdown(md: string): string {
  return renderMath(md)
}

export function sanitizeHtml(html: string): string {
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/\s+on[a-z]+\s*=\s*"[^"]*"/gi, '')
    .replace(/\s+on[a-z]+\s*=\s*'[^']*'/gi, '')
    .replace(/\s+on[a-z]+\s*=\s*[^\s>]+/gi, '')
    .replace(/\s+(href|src)\s*=\s*"javascript:[^"]*"/gi, '')
    .replace(/\s+(href|src)\s*=\s*'javascript:[^']*'/gi, '')
    .replace(/\s+(href|src)\s*=\s*javascript:[^\s>]+/gi, '')
}

export interface MarkdownHeading {
  id: string
  level: number
  text: string
}

export function extractMarkdownHeadings(md: string): MarkdownHeading[] {
  const tokens = new MarkdownIt().parse(md, {})
  const headings: MarkdownHeading[] = []
  let idx = 0

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i]
    if (token.type !== 'heading_open') continue
    const level = parseInt(token.tag.charAt(1), 10)
    const inlineToken = tokens[i + 1]
    const text = inlineToken && inlineToken.type === 'inline' ? inlineToken.content : ''
    headings.push({ id: anchor(text, idx++), level, text })
  }

  return headings
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
