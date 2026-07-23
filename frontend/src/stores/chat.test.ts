import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  ArtifactResult,
  ChatResult,
  ChatStreamEvent,
  Conversation,
  ClearCourseMemoryResponse,
  Course,
  CoursesResponse,
  MessagesResponse,
  NotesResponse,
  SaveNotesResponse,
} from '../types/api'

const api = vi.hoisted(() => ({
  getJson: vi.fn(),
  postFiles: vi.fn(),
  postJson: vi.fn(),
  postJsonStream: vi.fn(),
  postFilesStream: vi.fn(),
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

function conversation(id: string): Conversation {
  return {
    id,
    title: id,
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:00Z',
    last_read_at: '2026-07-16T00:00:00Z',
    message_count: 0,
    unread_count: 0,
  }
}

describe('chat store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
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

  it('shows status and token deltas immediately and ignores a duplicate write', async () => {
    const write = deferred<void>()
    let emit!: (event: ChatStreamEvent) => Promise<void>
    api.postJsonStream.mockImplementation((_path: string, _body: unknown, onEvent: typeof emit) => {
      emit = onEvent
      return write.promise
    })
    const store = useChatStore()
    store.beginCourse('a', 1)

    const first = store.send('question')
    const duplicate = store.send('duplicate')

    expect(store.busy.chat).toBe(true)
    expect(duplicate).toBeUndefined()
    expect(store.messages.map((item) => item.content)).toEqual(['question', ''])
    expect(store.messages[1]?.stream_status).toBe('正在发送…')
    await emit({ type: 'status', stage: 'retrieval', detail: '正在检索课程资料…' })
    expect(store.messages[1]?.stream_status).toBe('正在检索课程资料…')
    await emit({ type: 'status', stage: 'llm_retry', detail: 'LLM 调用失败 1/5，正在重试第 2 次…' })
    expect(store.messages[1]?.stream_status).toBe('LLM 调用失败 1/5，正在重试第 2 次…')
    expect(store.messages[1]?.stream_thoughts).toEqual(['LLM 调用失败 1/5，正在重试第 2 次…'])
    await emit({ type: 'thought', action: 'course_search', detail: '需要课程资料', query: '页表' })
    expect(store.messages[1]?.stream_status).toBe('需要课程资料')
    expect(store.messages[1]?.stream_thoughts).toEqual([
      'LLM 调用失败 1/5，正在重试第 2 次…',
      'course_search：需要课程资料 · 页表',
    ])
    await emit({ type: 'delta', delta: '答' })
    expect(store.messages[1]?.content).toBe('答')
    await emit({ type: 'delta', delta: '案' })
    expect(store.messages[1]?.content).toBe('答案')
    await emit({
      type: 'done',
      result: { answer: '答案', citations: [], memory: '', mode: 'answer', trace: [] },
    })
    write.resolve()
    await first

    expect(store.messages[1]?.content).toBe('答案')
    expect(store.messages[1]?.streaming).toBe(false)
    expect(store.busy.chat).toBe(false)
    expect(api.postJsonStream).toHaveBeenCalledOnce()
    expect(api.postJsonStream.mock.calls[0]?.[1]).toMatchObject({
      question: 'question',
      mode: 'answer',
      conversation_id: 'default',
    })
  })

  it('reveals a batched model delta as separate display tokens', async () => {
    const write = deferred<void>()
    let emit!: (event: ChatStreamEvent) => Promise<void>
    api.postJsonStream.mockImplementation((_path: string, _body: unknown, onEvent: typeof emit) => {
      emit = onEvent
      return write.promise
    })
    const store = useChatStore()
    store.beginCourse('a', 1)
    const request = store.send('question')

    const rendering = emit({ type: 'delta', delta: '逐字输出' })
    expect(store.messages[1]?.content).toBe('逐')
    await rendering
    expect(store.messages[1]?.content).toBe('逐字输出')

    await emit({
      type: 'done',
      result: { answer: '逐字输出', citations: [], memory: '', mode: 'answer', trace: [] },
    })
    write.resolve()
    await request
  })

  it('aborts an active request and preserves already rendered content', async () => {
    let emit!: (event: ChatStreamEvent) => Promise<void>
    let capturedSignal!: AbortSignal
    api.postJsonStream.mockImplementation(
      (_path: string, _body: unknown, onEvent: typeof emit, signal: AbortSignal) => {
        emit = onEvent
        capturedSignal = signal
        return new Promise<void>((_resolve, reject) => {
          signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
        })
      },
    )
    const store = useChatStore()
    store.beginCourse('a', 1)
    const request = store.send('question')
    await emit({ type: 'delta', delta: '已生成' })

    store.stop()
    await request

    expect(capturedSignal.aborted).toBe(true)
    expect(store.busy.chat).toBe(false)
    expect(store.error).toBeNull()
    expect(store.messages[1]?.content).toBe('已生成')
    expect(store.messages[1]?.streaming).toBe(false)
  })

  it('keeps streaming output attached to its conversation after switching away', async () => {
    const writes = new Map<string, ReturnType<typeof deferred<void>>>()
    const emitters = new Map<string, (event: ChatStreamEvent) => Promise<void>>()
    api.postJsonStream.mockImplementation((_path: string, body: { conversation_id: string }, onEvent: (event: ChatStreamEvent) => Promise<void>) => {
      const write = deferred<void>()
      writes.set(body.conversation_id, write)
      emitters.set(body.conversation_id, onEvent)
      return write.promise
    })
    const store = useChatStore()
    store.beginCourse('a', 1)
    store.conversations = [conversation('first'), conversation('second')]
    store.activeConversationId = 'first'

    const first = store.send('first question')
    store.activeConversationId = 'second'
    const second = store.send('second question')

    await emitters.get('first')!({ type: 'delta', delta: '甲' })
    expect(store.messages.map((item) => item.content)).toEqual(['second question', ''])
    store.activeConversationId = 'first'
    expect(store.messages[1]?.content).toBe('甲')

    await emitters.get('second')!({ type: 'done', result: { answer: '乙', citations: [], memory: '', mode: 'answer', trace: [] } })
    writes.get('second')!.resolve()
    await second
    await emitters.get('first')!({ type: 'done', result: { answer: '甲', citations: [], memory: '', mode: 'answer', trace: [] } })
    writes.get('first')!.resolve()
    await first

    expect(api.postJsonStream).toHaveBeenCalledTimes(2)
  })

  it('keeps streaming thoughts when switching back through selectConversation', async () => {
    let emit!: (event: ChatStreamEvent) => Promise<void>
    api.getJson.mockResolvedValue({ messages: [message('persisted history')] } satisfies MessagesResponse)
    api.postJson.mockResolvedValue({ conversations: [conversation('first'), conversation('second')] })
    api.postJsonStream.mockImplementation((_path: string, _body: unknown, onEvent: (event: ChatStreamEvent) => Promise<void>) => {
      emit = onEvent
      return new Promise<void>(() => undefined)
    })
    const store = useChatStore()
    store.beginCourse('a', 1)
    store.conversations = [conversation('first'), conversation('second')]
    store.activeConversationId = 'first'
    store.send('first question')
    await emit({ type: 'thought', action: 'course_search', detail: '正在查资料', query: '页表' })

    store.selectConversation('second')
    await store.loadMessages('second')
    store.selectConversation('first')

    expect(store.messages[1]?.stream_thoughts).toEqual(['course_search：正在查资料 · 页表'])
    expect(store.messages[1]?.streaming).toBe(true)
  })

  it('stops one conversation without aborting another running conversation', async () => {
    const signals = new Map<string, AbortSignal>()
    api.postJsonStream.mockImplementation((_path: string, body: { conversation_id: string }, _onEvent: unknown, signal: AbortSignal) => {
      signals.set(body.conversation_id, signal)
      return new Promise<void>((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      })
    })
    const store = useChatStore()
    store.beginCourse('a', 1)
    store.conversations = [conversation('first'), conversation('second')]
    store.activeConversationId = 'first'
    const first = store.send('first question')
    store.activeConversationId = 'second'
    const second = store.send('second question')

    store.stop('first')
    await first

    expect(signals.get('first')?.aborted).toBe(true)
    expect(signals.get('second')?.aborted).toBe(false)
    expect(store.isConversationStreaming('first')).toBe(false)
    expect(store.isConversationStreaming('second')).toBe(true)

    store.stop('second')
    await second
  })

  it('keeps drafts and pending attachments scoped per conversation', () => {
    const firstFile = new File(['a'], 'first.txt')
    const secondFile = new File(['b'], 'second.txt')
    const store = useChatStore()
    store.beginCourse('a', 1)
    store.conversations = [conversation('first'), conversation('second')]
    store.activeConversationId = 'first'
    store.draft = 'first draft'
    store.pendingFiles = [firstFile]

    store.activeConversationId = 'second'
    store.draft = 'second draft'
    store.pendingFiles = [secondFile]

    store.activeConversationId = 'first'
    expect(store.draft).toBe('first draft')
    expect(store.pendingFiles.map((file) => file.name)).toEqual(['first.txt'])
    store.activeConversationId = 'second'
    expect(store.draft).toBe('second draft')
    expect(store.pendingFiles.map((file) => file.name)).toEqual(['second.txt'])
  })

  it('navigates user message history per conversation and restores the current draft', () => {
    const store = useChatStore()
    store.beginCourse('a', 1)
    store.conversations = [conversation('first'), conversation('second')]
    store.activeConversationId = 'first'
    store.messages = [
      { role: 'user', content: '第一问', citations: [], trace: [], created_at: '2026-07-16T00:00:00Z' },
      message('answer'),
      { role: 'user', content: '第二问', citations: [], trace: [], created_at: '2026-07-16T00:01:00Z' },
    ]
    store.draft = '正在输入'

    expect(store.navigateDraftHistory('previous')).toBe(true)
    expect(store.draft).toBe('第二问')
    expect(store.navigateDraftHistory('previous')).toBe(true)
    expect(store.draft).toBe('第一问')
    expect(store.navigateDraftHistory('next')).toBe(true)
    expect(store.draft).toBe('第二问')
    expect(store.navigateDraftHistory('next')).toBe(true)
    expect(store.draft).toBe('正在输入')

    store.activeConversationId = 'second'
    expect(store.navigateDraftHistory('previous')).toBe(false)
    expect(store.draft).toBe('')
  })

  it('sends attachments as FormData and clears them after taking the request snapshot', async () => {
    api.postFilesStream.mockImplementation(async (_path: string, _form: FormData, onEvent: (event: ChatStreamEvent) => Promise<void>) => {
      await onEvent({ type: 'delta', delta: 'attachment answer' })
      await onEvent({
        type: 'done',
        result: { answer: 'attachment answer', citations: [], memory: '', mode: 'answer', trace: [] },
      })
    })
    const store = useChatStore()
    store.beginCourse('a', 1)
    store.mode = 'guide'
    store.pendingFiles = [new File(['image'], 'screen.png', { type: 'image/png' })]

    await store.send('inspect')

    expect(store.pendingFiles).toEqual([])
    const form = api.postFilesStream.mock.calls[0]?.[1] as FormData
    expect(form.get('question')).toBe('inspect')
    expect(form.get('mode')).toBe('guide')
    expect((form.get('files') as File).name).toBe('screen.png')
    expect(store.messages[1]?.content).toBe('attachment answer')
  })

  it('mutually excludes summary and quiz and refreshes courses and messages', async () => {
    const artifact = deferred<ArtifactResult>()
    api.postJson.mockReturnValue(artifact.promise)
    api.getJson.mockImplementation((path: string) => path === '/api/courses'
      ? Promise.resolve({ courses: [course('a', 2)] } satisfies CoursesResponse)
      : Promise.resolve({ messages: [message('summary saved')] } satisfies MessagesResponse))
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
      courses: [course('stale-artifact-snapshot', 99)],
    })
    await summary

    expect(store.busy.summary).toBe(false)
    expect(courses.activeCourse?.file_count).toBe(2)
    expect(store.messages[0]?.content).toBe('summary saved')
    expect(api.postJson).toHaveBeenCalledOnce()
  })

  it('mutually excludes chat and study artifact writes', async () => {
    const chatWrite = deferred<void>()
    let finishChat!: (event: ChatStreamEvent) => Promise<void>
    api.postJsonStream.mockImplementation((_path: string, _body: unknown, onEvent: typeof finishChat) => {
      finishChat = onEvent
      return chatWrite.promise
    })
    api.getJson.mockImplementation((path: string) => path === '/api/courses'
      ? Promise.resolve({ courses: [course('a', 1)] } satisfies CoursesResponse)
      : Promise.resolve({ messages: [] } satisfies MessagesResponse))
    const store = useChatStore()
    store.beginCourse('a', 1)

    const chat = store.send('question')

    expect(store.summary()).toBeUndefined()
    expect(store.quiz()).toBeUndefined()
    await finishChat({ type: 'done', result: { answer: 'answer', citations: [], memory: '', mode: 'answer', trace: [] } })
    chatWrite.resolve()
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
    expect(api.postJsonStream).toHaveBeenCalledOnce()
    expect(api.postJson).toHaveBeenCalledOnce()
  })

  it('saves notes and applies the returned list only to the current context', async () => {
    api.postJson.mockResolvedValue({ ok: true, notes: [note(1, 'saved')] } satisfies SaveNotesResponse)
    const store = useChatStore()
    store.beginCourse('a', 1)

    await store.saveNote('', 'content')

    expect(store.notes.map((item) => item.title)).toEqual(['saved'])
  })

  it('ignores a duplicate note save while the first write is busy', async () => {
    const noteSave = deferred<SaveNotesResponse>()
    api.postJson.mockReturnValue(noteSave.promise)
    const store = useChatStore()
    store.beginCourse('a', 1)

    const first = store.saveNote('note', 'content')
    const duplicate = store.saveNote('duplicate', 'content')

    expect(store.busy.note).toBe(true)
    expect(duplicate).toBeUndefined()
    expect(api.postJson).toHaveBeenCalledOnce()
    noteSave.resolve({ ok: true, notes: [note(1, 'saved')] })
    await first

    expect(store.busy.note).toBe(false)
    expect(store.notes.map((item) => item.title)).toEqual(['saved'])
  })

  it('does not let an in-flight notes GET overwrite a successful save', async () => {
    const oldNotes = deferred<NotesResponse>()
    api.getJson.mockReturnValue(oldNotes.promise)
    api.postJson.mockResolvedValue({ ok: true, notes: [note(2, 'saved')] } satisfies SaveNotesResponse)
    const store = useChatStore()
    store.beginCourse('a', 1)

    const pendingLoad = store.loadNotes()
    await store.saveNote('saved', 'content')
    oldNotes.resolve({ notes: [note(1, 'old')] })
    await pendingLoad

    expect(store.notes.map((item) => item.title)).toEqual(['saved'])
    expect(store.notesMutationEpoch).toBe(1)
  })

  it('keeps the notes epoch unchanged and allows an older load after save failure', async () => {
    const oldNotes = deferred<NotesResponse>()
    api.getJson.mockReturnValue(oldNotes.promise)
    api.postJson.mockRejectedValue(new Error('save failed'))
    const store = useChatStore()
    store.beginCourse('a', 1)

    const pendingLoad = store.loadNotes()
    await expect(store.saveNote('failed', 'content')).rejects.toThrow('save failed')
    oldNotes.resolve({ notes: [note(1, 'loaded')] })
    await pendingLoad

    expect(store.notesMutationEpoch).toBe(0)
    expect(store.notes.map((item) => item.title)).toEqual(['loaded'])
  })

  it('updates and deletes notes through course-scoped endpoints', async () => {
    api.postJson
      .mockResolvedValueOnce({ ok: true, notes: [note(1, 'updated')] } satisfies SaveNotesResponse)
      .mockResolvedValueOnce({ ok: true, notes: [] } satisfies SaveNotesResponse)
    const store = useChatStore()
    store.beginCourse('course/id', 1)
    store.notes = [note(1, 'old')]

    await store.updateNote(1, 'updated', 'updated content')
    await store.deleteNote(1)

    expect(api.postJson).toHaveBeenNthCalledWith(1, '/api/courses/course%2Fid/notes/1', {
      title: 'updated',
      content: 'updated content',
    })
    expect(api.postJson).toHaveBeenNthCalledWith(2, '/api/courses/course%2Fid/notes/1/delete')
    expect(store.notes).toEqual([])
    expect(store.notesMutationEpoch).toBe(2)
  })

  it('clears course messages and prevents an older messages load from restoring them', async () => {
    const oldMessages = deferred<MessagesResponse>()
    api.getJson.mockReturnValue(oldMessages.promise)
    api.postJson.mockResolvedValue({
      ok: true,
      messages: [],
      memory: '',
    } satisfies ClearCourseMemoryResponse)
    const store = useChatStore()
    store.beginCourse('a', 1)
    store.messages = [message('old')]

    const pendingLoad = store.loadMessages()
    await store.clearCourseMemory()
    oldMessages.resolve({ messages: [message('stale')] })
    await pendingLoad

    expect(api.postJson).toHaveBeenCalledWith('/api/courses/a/memory/clear')
    expect(store.messages).toEqual([])
    expect(store.busy.memory).toBe(false)
  })

  it('does not clear memory while chat is busy', () => {
    const store = useChatStore()
    store.beginCourse('a', 1)
    store.busy.chat = true

    expect(store.clearCourseMemory()).toBeUndefined()
    expect(api.postJson).not.toHaveBeenCalled()
  })
})
