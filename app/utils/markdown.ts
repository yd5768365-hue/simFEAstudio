/** Minimal markdown → HTML renderer for learning reports.
 *
 * Handles the subset used by SimFEA Studio learning reports:
 * headings, code fences, tables, unordered lists, bold, inline code.
 * Deliberately does NOT handle HTML tags, images, or raw links — the
 * report is machine-generated so the input is controlled.
 */

export function renderMarkdown(md: string): string {
  const lines = md.split('\n')
  const out: string[] = []
  let inCodeBlock = false
  let inTable = false
  let inList = false
  let headingIndex = 0

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // Fenced code block
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        out.push('</code></pre>')
        inCodeBlock = false
        continue
      }
      closeTable()
      closeList()
      inCodeBlock = true
      out.push('<pre><code>')
      continue
    }
    if (inCodeBlock) {
      out.push(escapeHtml(line))
      continue
    }

    // Heading
    if (line.startsWith('# ')) {
      closeTable()
      closeList()
      const text = line.slice(2)
      out.push(`<h1 id="${headingId(text, headingIndex++)}">${inlineMarkup(text)}</h1>`)
      continue
    }
    if (line.startsWith('## ')) {
      closeTable()
      closeList()
      const text = line.slice(3)
      out.push(`<h2 id="${headingId(text, headingIndex++)}">${inlineMarkup(text)}</h2>`)
      continue
    }
    if (line.startsWith('### ')) {
      closeTable()
      closeList()
      const text = line.slice(4)
      out.push(`<h3 id="${headingId(text, headingIndex++)}">${inlineMarkup(text)}</h3>`)
      continue
    }

    // Table
    if (line.startsWith('|') && line.endsWith('|')) {
      if (!inTable) {
        closeList()
        inTable = true
        out.push('<table>')
      }
      const cells = line
        .slice(1, -1)
        .split('|')
        .map((c) => c.trim())
      const isHeader = cells.every((c) => /^-{2,}$/.test(c))
      if (isHeader) continue // separator row
      const tag = inTable && out[out.length - 1] === '<table>' ? 'th' : 'td'
      // first data row after table open: check if previous output was <table>
      const rowCells = cells.map((c) => `<${tag}>${inlineMarkup(c)}</${tag}>`).join('')
      out.push(`<tr>${rowCells}</tr>`)
      continue
    } else if (inTable) {
      closeTable()
    }

    // Unordered list
    if (/^[\s]*[-*]\s/.test(line)) {
      if (!inList) {
        closeTable()
        inList = true
        out.push('<ul>')
      }
      const text = line.replace(/^[\s]*[-*]\s/, '')
      out.push(`<li>${inlineMarkup(text)}</li>`)
      continue
    } else if (inList && line.trim() === '') {
      // blank line in a list — continue the list (common in markdown)
      continue
    } else if (inList) {
      closeList()
    }

    // Bold text that stands alone (observation lines)
    if (/^\*\*.*\*\*$/.test(line.trim())) {
      out.push(`<p><strong>${inlineMarkup(line.trim().slice(2, -2))}</strong></p>`)
      continue
    }

    // Empty line
    if (line.trim() === '') {
      continue
    }

    // Regular paragraph
    out.push(`<p>${inlineMarkup(line)}</p>`)
  }

  closeTable()
  closeList()
  if (inCodeBlock) out.push('</code></pre>')

  return out.join('\n')

  function closeTable() {
    if (inTable) {
      out.push('</table>')
      inTable = false
    }
  }
  function closeList() {
    if (inList) {
      out.push('</ul>')
      inList = false
    }
  }
}

export interface MarkdownHeading {
  id: string
  level: number
  text: string
}

export function extractMarkdownHeadings(md: string): MarkdownHeading[] {
  let headingIndex = 0
  return md
    .split('\n')
    .map((line) => {
      const match = /^(#{1,3})\s+(.+)$/.exec(line)
      if (!match) return null
      const text = match[2].trim()
      return {
        id: headingId(text, headingIndex++),
        level: match[1].length,
        text,
      }
    })
    .filter((heading): heading is MarkdownHeading => heading !== null)
}

function headingId(text: string, index: number): string {
  const ascii = text
    .toLowerCase()
    .replace(/`/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return ascii || `section-${index + 1}`
}

function inlineMarkup(text: string): string {
  // Bold
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // Inline code
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>')
  return text
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
