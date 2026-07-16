import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Citation, FileLeafNode } from '../types/api'
import { useLayoutStore } from './layout'
import { usePreviewStore } from './preview'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function file(id: string, extension = '.md'): FileLeafNode {
  return {
    id,
    name: `lesson${extension}`,
    path: `/course/lesson${extension}`,
    type: 'file',
    extension,
    size: 10,
  }
}

function citation(fileId: string, quote: string, page: number | null): Citation {
  return {
    file_id: fileId,
    file_name: 'lesson.pdf',
    quote,
    page,
    chunk_index: 1,
    score: 0.9,
  }
}

describe('preview store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('clears preview content when the course context changes', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('lesson text')))
    const store = usePreviewStore()
    store.beginCourse('a', 1)
    await store.openFile(file('notes'))

    store.beginCourse('b', 2)

    expect(store.activeFile).toBeNull()
    expect(store.citation).toBeNull()
    expect(store.content).toBeNull()
    expect(store.tab).toBe('file')
  })

  it('closes through layout state without clearing the preview', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('lesson text')))
    const layout = useLayoutStore()
    const store = usePreviewStore()
    store.beginCourse('a', 1)
    await store.openFile(file('notes'))

    store.close()

    expect(layout.previewOpen).toBe(false)
    expect(store.activeFile?.id).toBe('notes')
    expect(store.content).toBe('lesson text')
  })

  it('encodes file ids and includes citation pages in PDF URLs', async () => {
    const store = usePreviewStore()
    store.beginCourse('a', 1)
    const pdf = file('folder/lesson 1.pdf', '.pdf')

    await store.openCitation(pdf, citation(pdf.id, 'quoted passage', 7))

    expect(store.url).toBe('/api/files/preview?id=folder%2Flesson%201.pdf#page=7')
    expect(store.citation?.quote).toBe('quoted passage')
    expect(store.citation?.page).toBe(7)
    expect(store.tab).toBe('sources')
  })

  it('uses requestVersion when citations for the same file resolve out of order', async () => {
    const firstText = deferred<Response>()
    const secondText = deferred<Response>()
    const fetchMock = vi.fn()
      .mockReturnValueOnce(firstText.promise)
      .mockReturnValueOnce(secondText.promise)
    vi.stubGlobal('fetch', fetchMock)
    const store = usePreviewStore()
    store.beginCourse('a', 1)
    const markdown = file('same-file')

    const first = store.openCitation(markdown, citation(markdown.id, 'old quote', 1))
    const second = store.openCitation(markdown, citation(markdown.id, 'new quote', 2))
    secondText.resolve(new Response('new content'))
    await second
    firstText.resolve(new Response('old content'))
    await first

    expect(store.content).toBe('new content')
    expect(store.citation?.quote).toBe('new quote')
    expect(store.citation?.page).toBe(2)
    expect(store.requestVersion).toBe(3)
  })
})
