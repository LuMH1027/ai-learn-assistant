import DOMPurify from 'dompurify'
import { marked } from 'marked'

export interface SearchHighlightOptions {
  query: string
  activeIndex: number
}

export interface TextSearchPart {
  text: string
  matchIndex: number | null
}

export function normalizedSearchQuery(query: string) {
  return query.trim()
}

export function countTextMatches(source: string, query: string) {
  const needle = normalizedSearchQuery(query).toLocaleLowerCase()
  if (!needle) return 0

  const haystack = source.toLocaleLowerCase()
  let count = 0
  let position = 0

  while (position < haystack.length) {
    const index = haystack.indexOf(needle, position)
    if (index === -1) break
    count += 1
    position = index + needle.length
  }

  return count
}

export function buildTextSearchParts(source: string, query: string): TextSearchPart[] {
  const needle = normalizedSearchQuery(query).toLocaleLowerCase()
  if (!needle) return [{ text: source, matchIndex: null }]

  const haystack = source.toLocaleLowerCase()
  const parts: TextSearchPart[] = []
  let position = 0
  let matchIndex = 0

  while (position < source.length) {
    const index = haystack.indexOf(needle, position)
    if (index === -1) break
    if (index > position) {
      parts.push({ text: source.slice(position, index), matchIndex: null })
    }
    parts.push({ text: source.slice(index, index + needle.length), matchIndex })
    matchIndex += 1
    position = index + needle.length
  }

  if (position < source.length) {
    parts.push({ text: source.slice(position), matchIndex: null })
  }

  return parts.length > 0 ? parts : [{ text: source, matchIndex: null }]
}

function sanitizedMarkdown(source: string) {
  const html = marked.parse(source, {
    async: false,
    gfm: true,
  })

  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
  })
}

function highlightHtmlText(html: string, options: SearchHighlightOptions) {
  const needle = normalizedSearchQuery(options.query)
  if (!needle || typeof document === 'undefined') return html

  const template = document.createElement('template')
  template.innerHTML = html

  const textNodes = textNodesIn(template.content)

  let globalMatchIndex = 0
  for (const textNode of textNodes) {
    const parts = buildTextSearchParts(textNode.data, needle)
    if (parts.every((part) => part.matchIndex === null)) continue

    const fragment = document.createDocumentFragment()
    for (const part of parts) {
      if (part.matchIndex === null) {
        fragment.append(document.createTextNode(part.text))
        continue
      }

      const mark = document.createElement('mark')
      mark.className = globalMatchIndex === options.activeIndex
        ? 'preview-search-hit active'
        : 'preview-search-hit'
      mark.dataset.searchIndex = String(globalMatchIndex)
      mark.textContent = part.text
      fragment.append(mark)
      globalMatchIndex += 1
    }
    textNode.replaceWith(fragment)
  }

  return template.innerHTML
}

function textNodesIn(root: Node) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const textNodes: Text[] = []
  let node = walker.nextNode()
  while (node) {
    textNodes.push(node as Text)
    node = walker.nextNode()
  }

  return textNodes
}

export function countMarkdownMatches(source: string, query: string) {
  const needle = normalizedSearchQuery(query)
  if (!needle || typeof document === 'undefined') return countTextMatches(source, needle)

  const template = document.createElement('template')
  template.innerHTML = sanitizedMarkdown(source)

  return textNodesIn(template.content)
    .reduce((count, textNode) => count + countTextMatches(textNode.data, needle), 0)
}

export function renderMarkdown(source: string, search?: SearchHighlightOptions) {
  const html = sanitizedMarkdown(source)
  return search ? highlightHtmlText(html, search) : html
}
