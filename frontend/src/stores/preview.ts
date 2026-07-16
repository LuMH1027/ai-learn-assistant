import { ref } from 'vue'
import { defineStore } from 'pinia'

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

  function isCurrentContext(id: string, version: number) {
    return courseId.value === id && contextVersion.value === version
  }

  function beginCourse(id: string, version: number) {
    courseId.value = id
    contextVersion.value = version
    requestVersion.value += 1
    activeFile.value = null
    citation.value = null
    tab.value = 'file'
    error.value = null
    url.value = null
    content.value = null
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

  function close() {
    useLayoutStore().setPreviewOpen(false)
  }

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
    beginCourse,
    isCurrentContext,
    openFile,
    openCitation,
    setTab,
    close,
  }
})
