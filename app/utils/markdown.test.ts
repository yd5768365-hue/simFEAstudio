import { describe, expect, it } from 'vitest'
import { extractMarkdownHeadings, renderMarkdown } from './markdown'

describe('renderMarkdown', () => {
  it('adds stable heading anchors', () => {
    const html = renderMarkdown('# Report\n\n## Result Analysis\n\n## 学习笔记')

    expect(html).toContain('<h1 id="report">Report</h1>')
    expect(html).toContain('<h2 id="result-analysis">Result Analysis</h2>')
    expect(html).toContain('<h2 id="section-3">学习笔记</h2>')
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
