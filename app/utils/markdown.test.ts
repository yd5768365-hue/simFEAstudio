import { describe, expect, it } from 'vitest'
import { extractMarkdownHeadings, renderMarkdown } from './markdown'

describe('renderMarkdown', () => {
  it('adds stable heading anchors', () => {
    const html = renderMarkdown('# Report\n\n## Result Analysis\n\n## Study Notes')

    expect(html).toContain('<h1 id="report">Report</h1>')
    expect(html).toContain('<h2 id="result-analysis">Result Analysis</h2>')
    expect(html).toContain('<h2 id="study-notes">Study Notes</h2>')
  })

  it('renders KaTeX output instead of escaped HTML', () => {
    const html = renderMarkdown('Euler: $e^{i\\pi}+1=0$')

    expect(html).toContain('class="katex"')
    expect(html).not.toContain('&lt;span class=&quot;katex')
  })
})

describe('sanitizeHtml', () => {
  it('removes scripts and inline event handlers from benchmark HTML', async () => {
    const { sanitizeHtml } = await import('./markdown')

    const html = sanitizeHtml('<h1 onclick="alert(1)">Case</h1><script>alert(2)</script>')

    expect(html).toContain('<h1>Case</h1>')
    expect(html).not.toContain('onclick')
    expect(html).not.toContain('<script')
  })
})

describe('extractMarkdownHeadings', () => {
  it('returns headings with the same ids used by renderMarkdown', () => {
    const headings = extractMarkdownHeadings('# Report\n\n## Result Analysis\n\n### `case.inp`')

    expect(headings).toEqual([
      { id: 'report', level: 1, text: 'Report' },
      { id: 'result-analysis', level: 2, text: 'Result Analysis' },
      { id: 'case-inp', level: 3, text: '`case.inp`' },
    ])
  })
})
