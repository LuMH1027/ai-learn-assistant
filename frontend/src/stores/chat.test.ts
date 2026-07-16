import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  ArtifactResult,
  ChatResult,
  Course,
  MessagesResponse,
  NotesResponse,
  SaveNotesResponse,
} from '../types/api'

const api = vi.hoisted(() => ({
  getJson: vi.fn(),
  postFiles: vi.fn(),
  postJson: vi.fn(),
}))

vi.mock('../services/api', () => api)

import { useChatStore } from './chat'
import { useCourseStore } from './course'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, reject, resolve }
}

function message(content: string) {
  return {
    role: 'assistant' as const,
    content,
    citations: [],
    trace: [],
    created_at: '2026-07-16T00:00:00Z',
  }
}

function note(id: number, title: string) {
  return { id, title, content: title, created_at: '2026-07-16T00:00:00Z' }
}

function course(id: string, fileCount = 0): Course {
  return { id, name: id, path: `/courses/${id}`, children: [], file_count: fileCount }
}

describe('chat store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('clears course-bound state immediately, including pending attachments', () => {
    const store = useChatStore()
    store.messages = [message('old')]
    store.notes = [note(1, 'old')]
    store.pendingFiles = [new File(['x'], 'x.txt')]
    store.error = 'old error'

    store.beginCourse('b', 2)

    expect(store.messages).toEqual([])
    expect(store.notes).toEqual([])
    expect(store.pendingFiles).toEqual([])
    expect(store.error).toBeNull()
    expect(store.isCurrentContext('b', 2)).toBe(true)
  })

  it('accepts an empty course context and invalidates pending responses', async () => {
    const oldMessages = deferred<MessagesResponse>()
    api.getJson.mockReturnValue(oldMessages.promise)
    const store = useChatStore()
    store.beginCourse('a', 1)
    const pendingLoad = store.loadMessages()

    store.beginCourse(null, 2)
    oldMessages.resolve({ messages: [message('stale')] })
    await pendingLoad

    expect(store.courseId).toBeNull()
    expect(store.messages).toEqual([])
    expect(store.isCurrentContext(null, 2)).toBe(true)
  })

  it('ignores A responses that arrive after a fast switch to B', async () => {
    const messagesA = deferred<MessagesResponse>()
    const notesA = deferred<NotesResponse>()
    const messagesB = deferred<MessagesResponse>()
    const notesB = deferred<NotesResponse>()
    api.getJson.mockImplementation((path: string) => {
      if (path.endsWith('/a/messages')) return messagesA.promise
      if (path.endsWith('/a/notes')) return notesA.promise
      if (path.endsWith('/b/messages')) return messagesB.promise
      return notesB.promise
    })
    const store = useChatStore()

    store.beginCourse('a', 1)
    const oldLoads = Promise.all([store.loadMessages(), store.loadNotes()])
    store.beginCourse('b', 2)
    const currentLoads = Promise.all([store.loadMessages(), store.loadNotes()])

    messagesB.resolve({ messages: [message('B message')] })
    notesB.resolve({ notes: [note(2, 'B note')] })
    await currentLoads
    messagesA.resolve({ messages: [message('A message')] })
    notesA.resolve({ notes: [note(1, 'A note')] })
    await oldLoads

    expect(store.messages.map((item) => item.content)).toEqual(['B message'])
    expect(store.notes.map((item) => item.title)).toEqual(['B note'])
  })

  it('uses request tokens so an older same-course load cannot overwrite a newer one', async () => {
    const older = deferred<MessagesResponse>()
    const newer = deferred<MessagesResponse>()
    api.getJson.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise)
    const store = useChatStore()
    store.beginCourse('a', 1)

    const first = store.loadMessages()
    const second = store.loadMessages()
    newer.resolve({ messages: [message('newer')] })
    await second
    older.resolve({ messages: [message('older')] })
    await first

    expect(store.messages.map((item) => item.content)).toEqual(['newer'])
  })

  it('sends JSON once and ignores a duplicate write while chat is busy', async () => {
    const write = deferred<ChatResult>()
    api.postJson.mockReturnValue(write.promise)
    api.getJson.mockResolvedValue({ messages: [message('answer')] } satisfies MessagesResponse)
    const store = useChatStore()
    store.beginCourse('a', 1)

    const first = store.send('question')
    const duplicate = store.send('duplicate')

    expect(store.busy.chat).toBe(true)
    expect(duplicate).toBeUndefined()
    write.resolve({ answer: 'answer', citations: [], memory: '', mode: 'answer', trace: [] })
    await first

    expect(store.messages.map((item) => item.content)).toEqual(['answer'])
    expect(store.busy.chat).toBe(false)
    expect(api.postJson).toHaveBeenCalledOnce()
  })

  it('sends attachments as FormData and clears them after taking the request snapshot', async () => {
    api.postFiles.mockResolvedValue({
      answer: 'attachment answer', citations: [], memory: '', mode: 'answer', trace: [],
    } satisfies ChatResult)
    api.getJson.mockResolvedValue({ messages: [message('attachment answer')] } satisfies MessagesResponse)
    const store = useChatStore()
    store.beginCourse('a', 1)
    store.pendingFiles = [new File(['image'], 'screen.png', { type: 'image/png' })]

    await store.send('inspect')

    expect(store.pendingFiles).toEqual([])
    const form = api.postFiles.mock.calls[0]?.[1] as FormData
    expect(form.get('question')).toBe('inspect')
    expect((form.get('files') as File).name).toBe('screen.png')
    expect(store.messages[0]?.content).toBe('attachment answer')
  })

  it('mutually excludes summary and quiz and refreshes courses and messages', async () => {
    const artifact = deferred<ArtifactResult>()
    api.postJson.mockReturnValue(artifact.promise)
    api.getJson.mockResolvedValue({ messages: [message('summary saved')] } satisfies MessagesResponse)
    const courses = useCourseStore()
    courses.courses = [course('a')]
    courses.selectCourse('a')
    const store = useChatStore()
    store.beginCourse('a', courses.contextVersion)

    const summary = store.summary()
    const quiz = store.quiz()

    expect(store.busy.summary).toBe(true)
    expect(quiz).toBeUndefined()
    artifact.resolve({
      ok: true,
      content: 'summary',
      citations: [],
      artifact: { name: 'summary.md', path: '/courses/a/summary.md' },
      courses: [course('a', 1)],
    })
    await summary

    expect(store.busy.summary).toBe(false)
    expect(courses.activeCourse?.file_count).toBe(1)
    expect(store.messages[0]?.content).toBe('summary saved')
    expect(api.postJson).toHaveBeenCalledOnce()
  })

  it('mutually excludes chat and study artifact writes', async () => {
    const chatWrite = deferred<ChatResult>()
    api.postJson.mockReturnValue(chatWrite.promise)
    api.getJson.mockResolvedValue({ messages: [] } satisfies MessagesResponse)
    const store = useChatStore()
    store.beginCourse('a', 1)

    const chat = store.send('question')

    expect(store.summary()).toBeUndefined()
    expect(store.quiz()).toBeUndefined()
    chatWrite.resolve({ answer: 'answer', citations: [], memory: '', mode: 'answer', trace: [] })
    await chat

    const artifactWrite = deferred<ArtifactResult>()
    api.postJson.mockReturnValue(artifactWrite.promise)
    const summary = store.summary()

    expect(store.send('blocked')).toBeUndefined()
    artifactWrite.resolve({
      ok: true,
      content: 'summary',
      citations: [],
      artifact: { name: 'summary.md', path: '/courses/a/summary.md' },
      courses: [course('a', 1)],
    })
    await summary
    expect(api.postJson).toHaveBeenCalledTimes(2)
  })

  it('saves notes and applies the returned list only to the current context', async () => {
    api.postJson.mockResolvedValue({ ok: true, notes: [note(1, 'saved')] } satisfies SaveNotesResponse)
    const store = useChatStore()
    store.beginCourse('a', 1)

    await store.saveNote('', 'content')

    expect(store.notes.map((item) => item.title)).toEqual(['saved'])
  })
})
