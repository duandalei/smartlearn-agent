/**
 * 轻量 Markdown 渲染（零依赖、先转义后渲染，防 XSS）。
 *
 * 支持 AI 回答中常见的子集：
 * - 标题 # ~ ######、粗体 **、斜体 * / _、删除线 ~~、行内代码 `code`
 * - 有序/无序列表、引用、水平线、围栏代码块、表格
 * - http/https 链接（target=_blank + rel=noopener noreferrer）
 *
 * 不引入 marked/markdown-it：项目要求零新增依赖；所有原始 HTML 先转义，
 * 只生成白名单标签与安全属性。
 */

const ESCAPE_MAP: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

/** HTML 文本转义（所有用户/模型文本进入渲染前后的统一入口）。 */
export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (char) => ESCAPE_MAP[char] ?? char)
}

/** 行内语法：代码 span → 链接 → 粗体/斜体/删除线。输入先转义。 */
function renderInline(raw: string): string {
  let text = escapeHtml(raw)
  const codeSpans: string[] = []
  text = text.replace(/`([^`\n]+)`/g, (_match, code: string) => {
    codeSpans.push(code)
    return `\u0000CODE${codeSpans.length - 1}\u0000`
  })
  text = text.replace(
    /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g,
    (_match, label: string, url: string) =>
      `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`,
  )
  text = text.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
  text = text.replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
  text = text.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  text = text.replace(/~~([^~\n]+)~~/g, '<del>$1</del>')
  text = text.replace(
    /\u0000CODE(\d+)\u0000/g,
    (_match, index: string) => `<code>${codeSpans[Number(index)]}</code>`,
  )
  return text
}

/** 行内 Markdown → 安全 HTML（来源卡片片段用；不生成块级标签）。 */
export function renderInlineMarkdown(raw: string): string {
  return renderInline(raw)
}

const RE_FENCE = /^\s*```([\w-]*)\s*$/
const RE_HEADING = /^(#{1,6})\s+(.*)$/
const RE_HR = /^\s*(?:---|\*\*\*|___)\s*$/
const RE_QUOTE = /^\s*>\s?(.*)$/
const RE_UL = /^\s*[-*+]\s+(.*)$/
const RE_OL = /^\s*(\d+)[.)]\s+(.*)$/
const RE_TABLE_SEPARATOR = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/

/** 当前行是否开启新的块（段落收集时用于断段）。 */
function startsBlock(line: string, next: string | undefined): boolean {
  return (
    RE_FENCE.test(line) ||
    RE_HEADING.test(line) ||
    RE_HR.test(line) ||
    RE_QUOTE.test(line) ||
    RE_UL.test(line) ||
    RE_OL.test(line) ||
    (line.includes('|') && next !== undefined && RE_TABLE_SEPARATOR.test(next))
  )
}

/** 表格行拆单元格：去掉首尾管道，保留空单元格。 */
function splitTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return trimmed.split('|').map((cell) => cell.trim())
}

/** Markdown → 安全 HTML。 */
export function renderMarkdown(raw: string): string {
  const lines = (raw ?? '').replace(/\r\n?/g, '\n').split('\n')
  const blocks: string[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    if (line.trim() === '') {
      i += 1
      continue
    }

    const fence = line.match(RE_FENCE)
    if (fence) {
      const language = fence[1] ?? ''
      const codeLines: string[] = []
      i += 1
      while (i < lines.length && !RE_FENCE.test(lines[i])) {
        codeLines.push(lines[i])
        i += 1
      }
      if (i < lines.length) i += 1
      const languageClass = language ? ` class="language-${escapeHtml(language)}"` : ''
      blocks.push(`<pre><code${languageClass}>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
      continue
    }

    if (
      line.includes('|') &&
      i + 1 < lines.length &&
      RE_TABLE_SEPARATOR.test(lines[i + 1])
    ) {
      const headers = splitTableRow(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].includes('|') && lines[i].trim() !== '') {
        rows.push(splitTableRow(lines[i]))
        i += 1
      }
      const headerHtml = headers
        .map((cell) => `<th>${renderInline(cell)}</th>`)
        .join('')
      const bodyHtml = rows
        .map(
          (row) =>
            `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join('')}</tr>`,
        )
        .join('')
      blocks.push(`<table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`)
      continue
    }

    const heading = line.match(RE_HEADING)
    if (heading) {
      const level = heading[1].length
      blocks.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      i += 1
      continue
    }

    if (RE_HR.test(line)) {
      blocks.push('<hr>')
      i += 1
      continue
    }

    if (RE_QUOTE.test(line)) {
      const quoteLines: string[] = []
      while (i < lines.length) {
        const quote = lines[i].match(RE_QUOTE)
        if (!quote) break
        quoteLines.push(quote[1])
        i += 1
      }
      blocks.push(`<blockquote>${renderMarkdown(quoteLines.join('\n'))}</blockquote>`)
      continue
    }

    if (RE_UL.test(line)) {
      const items: string[] = []
      while (i < lines.length) {
        const item = lines[i].match(RE_UL)
        if (!item) break
        items.push(`<li>${renderInline(item[1])}</li>`)
        i += 1
      }
      blocks.push(`<ul>${items.join('')}</ul>`)
      continue
    }

    if (RE_OL.test(line)) {
      const items: string[] = []
      while (i < lines.length) {
        const item = lines[i].match(RE_OL)
        if (!item) break
        items.push(`<li>${renderInline(item[2])}</li>`)
        i += 1
      }
      blocks.push(`<ol>${items.join('')}</ol>`)
      continue
    }

    const paragraph: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !startsBlock(lines[i], lines[i + 1])
    ) {
      paragraph.push(lines[i])
      i += 1
    }
    if (paragraph.length) {
      blocks.push(`<p>${renderInline(paragraph.join('\n')).replace(/\n/g, '<br>')}</p>`)
    } else {
      // 防御：某行命中块起始但未匹配分支时避免死循环。
      blocks.push(`<p>${renderInline(lines[i])}</p>`)
      i += 1
    }
  }

  return blocks.join('\n')
}
