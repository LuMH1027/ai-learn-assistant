import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

import { countMarkdownMatches, countTextMatches, normalizedSearchQuery } from '../services/markdown'
import type { Citation, FileLeafNode } from '../types/api'
import { useLayoutStore } from './layout'

export type PreviewTab = 'file' | 'sources' | 'info'

const IMAGE_EXTENSIONS = new Set([
  '.png',
  '.jpg',
  '.jpeg',
  '.webp',
  '.gif',
  '.bmp',
])

const MARKDOWN_EXTENSIONS = new Set(['.md', '.markdown'])

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}

export const usePreviewStore = defineStore('preview', () => {
  const activeFile = ref<FileLeafNode | null>(null)
  const citation = ref<Citation | null>(null)
  const tab = ref<PreviewTab>('file')
  const error = ref<string | null>(null)
  const requestVersion = ref(0)
  const courseId = ref<string | null>(null)
  const contextVersion = ref(0)
  const url = ref<string | null>(null)
  const content = ref<string | null>(null)
  const searchQuery = ref('')
  const activeSearchIndex = ref(0)

  const extension = computed(() => activeFile.value?.extension.toLowerCase() ?? '')
  const supportsSearch = computed(() => {
    return Boolean(
      activeFile.value &&
      content.value !== null &&
      !error.value &&
      extension.value !== '.pdf' &&
      !IMAGE_EXTENSIONS.has(extension.value),
    )
  })
  const searchTerm = computed(() => normalizedSearchQuery(searchQuery.value))
  const searchMatchCount = computed(() => {
    if (!supportsSearch.value || !content.value || !searchTerm.value) return 0
    return MARKDOWN_EXTENSIONS.has(extension.value)
      ? countMarkdownMatches(content.value, searchTerm.value)
      : countTextMatches(content.value, searchTerm.value)
  })
  const currentSearchMatch = computed(() => (
    searchMatchCount.value > 0 ? activeSearchIndex.value + 1 : 0
  ))

  function resetSearch() {
    searchQuery.value = ''
    activeSearchIndex.value = 0
  }

  function isCurrentContext(id: string | null, version: number) {
    return courseId.value === id && contextVersion.value === version
  }

  function beginCourse(id: string | null, version: number) {
    courseId.value = id
    contextVersion.value = version
    requestVersion.value += 1
    activeFile.value = null
    citation.value = null
    tab.value = 'file'
    error.value = null
    url.value = null
    content.value = null
    resetSearch()
  }

  function previewUrl(file: FileLeafNode, page?: number | null) {
    const base = `/api/files/preview?id=${encodeURIComponent(file.id)}`
    return file.extension.toLowerCase() === '.pdf' && page
      ? `${base}#page=${encodeURIComponent(page)}`
      : base
  }

  async function loadFile(
    file: FileLeafNode,
    page: number | null | undefined,
    request: number,
    id: string,
    version: number,
  ) {
    activeFile.value = file
    url.value = previewUrl(file, page)
    content.value = null
    error.value = null
    resetSearch()
    useLayoutStore().setPreviewOpen(true)

    const extension = file.extension.toLowerCase()
    if (extension === '.pdf' || IMAGE_EXTENSIONS.has(extension)) return true

    try {
      const response = await fetch(url.value)
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`)
      }
      const text = await response.text()
      if (
        request !== requestVersion.value ||
        !isCurrentContext(id, version)
      ) return false
      content.value = text
      return true
    } catch (cause) {
      if (request === requestVersion.value && isCurrentContext(id, version)) {
        error.value = errorMessage(cause)
      }
      throw cause
    }
  }

  function openFile(file: FileLeafNode, page?: number | null) {
    const id = courseId.value
    const version = contextVersion.value
    if (id === null) return
    const request = ++requestVersion.value
    citation.value = null
    tab.value = 'file'
    return loadFile(file, page, request, id, version)
  }

  function openCitation(file: FileLeafNode, source: Citation) {
    const id = courseId.value
    const version = contextVersion.value
    if (id === null) return
    const request = ++requestVersion.value

    return (async () => {
      const loaded = await loadFile(file, source.page, request, id, version)
      if (
        !loaded ||
        request !== requestVersion.value ||
        !isCurrentContext(id, version)
      ) return false
      citation.value = source
      tab.value = 'sources'
      return true
    })()
  }

  function setTab(nextTab: PreviewTab) {
    tab.value = nextTab
  }

  function setSearchQuery(query: string) {
    searchQuery.value = query
    activeSearchIndex.value = 0
  }

  function nextSearchMatch() {
    if (searchMatchCount.value === 0) return
    activeSearchIndex.value = (activeSearchIndex.value + 1) % searchMatchCount.value
    tab.value = 'file'
  }

  function previousSearchMatch() {
    if (searchMatchCount.value === 0) return
    activeSearchIndex.value = (
      activeSearchIndex.value + searchMatchCount.value - 1
    ) % searchMatchCount.value
    tab.value = 'file'
  }

  function close() {
    useLayoutStore().setPreviewOpen(false)
  }

  watch(searchMatchCount, (count) => {
    if (count === 0) {
      activeSearchIndex.value = 0
      return
    }
    if (activeSearchIndex.value >= count) {
      activeSearchIndex.value = 0
    }
  })

  return {
    activeFile,
    citation,
    tab,
    error,
    requestVersion,
    courseId,
    contextVersion,
    url,
    content,
    searchQuery,
    activeSearchIndex,
    supportsSearch,
    searchTerm,
    searchMatchCount,
    currentSearchMatch,
    beginCourse,
    isCurrentContext,
    openFile,
    openCitation,
    setTab,
    setSearchQuery,
    nextSearchMatch,
    previousSearchMatch,
    resetSearch,
    close,
  }
})
