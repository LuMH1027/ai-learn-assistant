import DOMPurify from 'dompurify'
import { marked } from 'marked'

export function renderMarkdown(source: string) {
  const html = marked.parse(source, {
    async: false,
    gfm: true,
  })

  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
  })
}
