/** Lightweight syntax highlighting for code files in SimFEA Studio.
 *
 * Supports: Python (.py), JSON (.json), CalculiX input (.inp), and plain text fallback.
 * Returns HTML string with <span class="syn-*"> tokens for CSS styling.
 */

type Lang = 'python' | 'json' | 'inp' | 'text'

function detectLang(filename: string): Lang {
  if (filename.endsWith('.py')) return 'python'
  if (filename.endsWith('.json')) return 'json'
  if (filename.endsWith('.inp')) return 'inp'
  return 'text'
}

export function highlightCode(code: string, filename: string): string {
  const lang = detectLang(filename)
  const escaped = escapeHtml(code)
  switch (lang) {
    case 'python':
      return highlightPython(escaped)
    case 'json':
      return highlightJson(escaped)
    case 'inp':
      return highlightInp(escaped)
    default:
      return `<pre class="syn-block"><code>${escaped}</code></pre>`
  }
}

// ── Python ──────────────────────────────────────

const PY_KEYWORDS = new Set([
  'def',
  'class',
  'import',
  'from',
  'return',
  'if',
  'elif',
  'else',
  'for',
  'while',
  'try',
  'except',
  'finally',
  'with',
  'as',
  'yield',
  'raise',
  'pass',
  'break',
  'continue',
  'and',
  'or',
  'not',
  'in',
  'is',
  'None',
  'True',
  'False',
  'async',
  'await',
  'lambda',
  'assert',
  'del',
  'global',
  'nonlocal',
])

const PY_BUILTINS = new Set([
  'print',
  'len',
  'range',
  'int',
  'float',
  'str',
  'list',
  'dict',
  'set',
  'tuple',
  'bool',
  'type',
  'isinstance',
  'hasattr',
  'getattr',
  'setattr',
  'open',
  'enumerate',
  'zip',
  'map',
  'filter',
  'sorted',
  'reversed',
  'min',
  'max',
  'sum',
  'abs',
  'round',
  'any',
  'all',
  'super',
  'self',
  'cls',
  'Exception',
  'ValueError',
  'TypeError',
  'KeyError',
  'RuntimeError',
  '__init__',
  '__name__',
  '__main__',
  '__file__',
])

function highlightPython(code: string): string {
  const lines = code.split('\n')
  const out: string[] = []

  for (const line of lines) {
    // Comments
    const commentIdx = findCommentStart(line)
    let before = commentIdx >= 0 ? line.slice(0, commentIdx) : line
    const comment = commentIdx >= 0 ? line.slice(commentIdx) : ''

    // Strings (handle before keywords to preserve string content)
    before = highlightStrings(before)

    // Decorators
    before = before.replace(/^(\s*)(@\w+)(.*)$/, '$1<span class="syn-decorator">$2</span>$3')

    // Keywords
    before = before.replace(/\b([a-zA-Z_]\w*)\b/g, (match, word) => {
      if (PY_KEYWORDS.has(word)) return `<span class="syn-keyword">${word}</span>`
      return match
    })

    // Builtins (only if not already wrapped)
    before = before.replace(/\b([a-zA-Z_]\w*)\b/g, (match, word) => {
      if (PY_BUILTINS.has(word)) return `<span class="syn-builtin">${word}</span>`
      return match
    })

    // Numbers (after keywords/builtins to avoid conflicts)
    before = before.replace(/\b(\d+\.?\d*)\b/g, '<span class="syn-number">$1</span>')

    // Function calls: word followed by (
    before = before.replace(
      /<span class="syn-builtin">(\w+)<\/span>\(/g,
      '<span class="syn-funcall">$1</span>('
    )
    before = before.replace(/\b([a-zA-Z_]\w*)(\()/g, (match, name, paren) => {
      if (!match.startsWith('<span')) {
        return `<span class="syn-funcall">${name}</span>${paren}`
      }
      return match
    })

    if (comment) {
      out.push(`${before}<span class="syn-comment">${comment}</span>`)
    } else if (before.trim() === '') {
      out.push('')
    } else {
      out.push(before)
    }
  }

  return `<pre class="syn-block"><code>${out.join('\n')}</code></pre>`
}

function findCommentStart(line: string): number {
  let inStr: string | null = null
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (inStr) {
      if (ch === '\\') {
        i++
        continue
      }
      if (ch === inStr) inStr = null
      continue
    }
    if (ch === '"' || ch === "'") {
      inStr = ch
      continue
    }
    if (ch === '#') return i
  }
  return -1
}

function highlightStrings(line: string): string {
  let result = ''
  let i = 0
  while (i < line.length) {
    // Triple-quoted strings
    if (
      (line[i] === '"' && line[i + 1] === '"' && line[i + 2] === '"') ||
      (line[i] === "'" && line[i + 1] === "'" && line[i + 2] === "'")
    ) {
      const quote = line.slice(i, i + 3)
      const end = findStrEnd(line, i + 3, quote)
      if (end >= 0) {
        result += `<span class="syn-string">${line.slice(i, end + 3)}</span>`
        i = end + 3
        continue
      }
    }
    // F-strings and regular strings
    if (line[i] === 'f' && (line[i + 1] === '"' || line[i + 1] === "'")) {
      const quote = line[i + 1]
      const end = findStrEnd(line, i + 2, quote)
      if (end >= 0) {
        result += `<span class="syn-fstring">${line.slice(i, end + 1)}</span>`
        i = end + 1
        continue
      }
    }
    if (line[i] === '"' || line[i] === "'") {
      const quote = line[i]
      const end = findStrEnd(line, i + 1, quote)
      if (end >= 0) {
        result += `<span class="syn-string">${line.slice(i, end + 1)}</span>`
        i = end + 1
        continue
      }
    }
    result += line[i]
    i++
  }
  return result
}

function findStrEnd(line: string, start: number, quote: string): number {
  for (let i = start; i < line.length; i++) {
    if (line[i] === '\\') {
      i++
      continue
    }
    if (line.slice(i, i + quote.length) === quote) return i
  }
  return -1
}

// ── JSON ────────────────────────────────────────

function highlightJson(code: string): string {
  const out = code.replace(/("(?:[^"\\]|\\.)*")\s*:/g, '<span class="syn-json-key">$1</span>:')
  const withValues = out.replace(/:\s*("(?:[^"\\]|\\.)*")/g, ': <span class="syn-string">$1</span>')
  const withNums = withValues.replace(
    /:\s*(-?\d+\.?\d*(?:[eE][+-]?\d+)?)/g,
    ': <span class="syn-number">$1</span>'
  )
  const withBools = withNums.replace(/:\s*(true|false|null)/g, ': <span class="syn-keyword">$1</span>')
  return `<pre class="syn-block"><code>${withBools}</code></pre>`
}

// ── CalculiX .inp ───────────────────────────────

const INP_KEYWORDS = new Set([
  'NODE',
  'NSET',
  'ELSET',
  'ELEMENT',
  'TYPE',
  'MATERIAL',
  'ELASTIC',
  'SOLID',
  'SECTION',
  'BEAM',
  'SHELL',
  'BOUNDARY',
  'CLOAD',
  'DLOAD',
  'STEP',
  'STATIC',
  'FREQUENCY',
  'BUCKLE',
  'HEAT',
  'TRANSFER',
  'COUPLING',
  'EQUATION',
  'MPC',
  'ORIENTATION',
  'SURFACE',
  'END',
  'INCLUDE',
  'RESTART',
  'FILE',
  'OUTPUT',
  'NODE',
  'PRINT',
  'GENERAL',
  'PLASTIC',
  'DENSITY',
  'EXPANSION',
  'CONDUCTIVITY',
  'SPECIFIC',
  'HEAT',
  'AMPLITUDE',
  'PERIODIC',
  'MODAL',
  'DYNAMIC',
  'GREEN',
  'NLGEOM',
  'CONTACT',
  'PAIR',
  'TIE',
  'FRICTION',
  'NSET',
  'ELSET',
  'SURFACE',
  'RIGID',
  'BEAM',
  'GENERAL',
  'DISTRIBUTING',
  'UNIVERSAL',
  'GAS',
  'CAVITY',
])

function highlightInp(code: string): string {
  const lines = code.split('\n')
  const out: string[] = []

  for (const line of lines) {
    const trimmed = line.trimStart()
    const indent = line.slice(0, line.length - trimmed.length)

    // Comment line
    if (trimmed.startsWith('**')) {
      out.push(`${indent}<span class="syn-comment">${escapeHtml(trimmed)}</span>`)
      continue
    }

    let content = escapeHtml(trimmed)

    // Keywords (start of line, preceded by *)
    if (content.startsWith('*')) {
      const wordMatch = /^(\*\w+)/.exec(content)
      if (wordMatch) {
        const kw = wordMatch[1].toUpperCase()
        if (INP_KEYWORDS.has(kw.slice(1))) {
          content = content.replace(/^(\*\w+)/, '<span class="syn-inp-keyword">$1</span>')
        } else {
          content = content.replace(/^(\*\w+)/, '<span class="syn-decorator">$1</span>')
        }
      }
    }

    // Numbers (comma-separated values)
    content = content.replace(/(-?\d+\.?\d*(?:[eE][+-]?\d+)?)/g, '<span class="syn-number">$1</span>')

    out.push(indent ? `${indent}${content}` : content)
  }

  return `<pre class="syn-block"><code>${out.join('\n')}</code></pre>`
}

// ── Helpers ─────────────────────────────────────

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
