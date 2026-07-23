import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'

import { getJson, postFilesStream, postJson, postJsonStream } from '../services/api'
import type {
  ArtifactResult,
  ChatResult,
  ChatStreamEvent,
  ClearCourseMemoryResponse,
  Conversation,
  ConversationsResponse,
  Message,
  MessagesResponse,
  Note,
  NotesResponse,
  SaveConversationResponse,
  SaveNotesResponse,
  StudyMode,
} from '../types/api'
import { useCourseStore } from './course'

type StudyArtifact = 'summary' | 'quiz'
const STREAM_RENDER_DELAY_MS = 16

interface ConversationRuntime {
  messages: Message[]
  draft: string
  historyCursor: number | null
  historyScratch: string
  pendingFiles: File[]
  error: string | null
  messagesRequestToken: number
  mutationEpoch: number
  chatRequestToken: number
  isStreaming: boolean
  abortController: AbortController | null
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}

function isAbortError(error: unknown) {
  return typeof error === 'object' && error !== null &&
    'name' in error && error.name === 'AbortError'
}

function waitForStreamPaint() {
  return new Promise<void>((resolve) => window.setTimeout(resolve, STREAM_RENDER_DELAY_MS))
}

function displayUnits(text: string) {
  return text.match(/[\p{Script=Han}]|[A-Za-z0-9_]+|\s+|[^\s]/gu) ?? []
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const activeConversationId = ref<string | null>(null)
  const conversationRuntime = reactive<Record<string, ConversationRuntime>>({})
  const notes = ref<Note[]>([])
  const mode = ref<StudyMode>('answer')
  const busy = reactive({
    get chat() {
      return activeConversationId.value === null ? false : isConversationStreaming(activeConversationId.value)
    },
    set chat(value: boolean) {
      const conversationId = activeConversationId.value
      if (conversationId === null) return
      runtimeFor(conversationId).isStreaming = value
    },
    summary: false,
    quiz: false,
    note: false,
    memory: false,
  })
  const courseId = ref<string | null>(null)
  const contextVersion = ref(0)
  const notesMutationEpoch = ref(0)

  let conversationsRequestToken = 0
  let notesRequestToken = 0
  let artifactRequestToken = 0
  let noteRequestToken = 0
  let memoryRequestToken = 0

  function runtimeFor(conversationId: string) {
    conversationRuntime[conversationId] ??= {
      messages: [],
      draft: '',
      historyCursor: null,
      historyScratch: '',
      pendingFiles: [],
      error: null,
      messagesRequestToken: 0,
      mutationEpoch: 0,
      chatRequestToken: 0,
      isStreaming: false,
      abortController: null,
    }
    return conversationRuntime[conversationId]!
  }

  function activeRuntime() {
    return activeConversationId.value === null ? null : runtimeFor(activeConversationId.value)
  }

  function resetRuntime() {
    for (const item of Object.values(conversationRuntime)) item.abortController?.abort()
    for (const key of Object.keys(conversationRuntime)) delete conversationRuntime[key]
  }

  const messages = computed({
    get() {
      return activeRuntime()?.messages ?? []
    },
    set(value: Message[]) {
      const runtime = activeRuntime()
      if (runtime) {
        runtime.messages = value
        runtime.mutationEpoch += 1
        runtime.messagesRequestToken += 1
      }
    },
  })

  const pendingFiles = computed({
    get() {
      return activeRuntime()?.pendingFiles ?? []
    },
    set(value: File[]) {
      const runtime = activeRuntime()
      if (runtime) runtime.pendingFiles = value
    },
  })

  const draft = computed({
    get() {
      return activeRuntime()?.draft ?? ''
    },
    set(value: string) {
      const runtime = activeRuntime()
      if (runtime) {
        runtime.draft = value
        runtime.historyCursor = null
        runtime.historyScratch = ''
      }
    },
  })

  const error = computed({
    get() {
      return activeRuntime()?.error ?? null
    },
    set(value: string | null) {
      const runtime = activeRuntime()
      if (runtime) runtime.error = value
    },
  })

  function isCurrentContext(id: string | null, version: number) {
    return courseId.value === id && contextVersion.value === version
  }

  function isCurrentConversation(id: string | null, version: number, conversationId: string | null) {
    return isCurrentContext(id, version) && activeConversationId.value === conversationId
  }

  function isConversationStreaming(conversationId: string | null) {
    return conversationId === null ? false : conversationRuntime[conversationId]?.isStreaming === true
  }

  function userMessageHistory(runtime: ConversationRuntime) {
    return runtime.messages
      .filter((message) => message.role === 'user' && message.content.trim().length > 0)
      .map((message) => message.content)
  }

  function navigateDraftHistory(direction: 'previous' | 'next') {
    const runtime = activeRuntime()
    if (!runtime) return false
    const history = userMessageHistory(runtime)
    if (history.length === 0) return false

    if (direction === 'previous') {
      if (runtime.historyCursor === null) {
        runtime.historyScratch = runtime.draft
        runtime.historyCursor = history.length - 1
      } else {
        runtime.historyCursor = Math.max(0, runtime.historyCursor - 1)
      }
      runtime.draft = history[runtime.historyCursor]
      return true
    }

    if (runtime.historyCursor === null) return false
    if (runtime.historyCursor < history.length - 1) {
      runtime.historyCursor += 1
      runtime.draft = history[runtime.historyCursor]
    } else {
      runtime.historyCursor = null
      runtime.draft = runtime.historyScratch
      runtime.historyScratch = ''
    }
    return true
  }

  const activeConversation = computed(() =>
    conversations.value.find((item) => item.id === activeConversationId.value) ??
    (activeConversationId.value ? {
      id: activeConversationId.value,
      title: activeConversationId.value === 'default' ? '历史对话' : '新对话',
      created_at: '',
      updated_at: '',
      last_read_at: '',
      message_count: runtimeFor(activeConversationId.value).messages.length,
      unread_count: 0,
    } : null),
  )

  function beginCourse(id: string | null, version: number) {
    resetRuntime()
    courseId.value = id
    contextVersion.value = version
    notesMutationEpoch.value = 0
    conversations.value = []
    activeConversationId.value = id === null ? null : 'default'
    notes.value = []
    error.value = null
    busy.summary = false
    busy.quiz = false
    busy.note = false
    busy.memory = false
    conversationsRequestToken += 1
    notesRequestToken += 1
    artifactRequestToken += 1
    noteRequestToken += 1
    memoryRequestToken += 1
  }

  function conversationPath(id: string, conversationId: string) {
    return `/api/courses/${encodeURIComponent(id)}/conversations/${encodeURIComponent(conversationId)}`
  }

  function scopedCoursePath(id: string, conversationId: string, action: string) {
    if (conversations.value.length === 0 && conversationId === 'default') {
      return `/api/courses/${encodeURIComponent(id)}/${action}`
    }
    return `${conversationPath(id, conversationId)}/${action}`
  }

  function applyConversations(next: Conversation[], preferredId?: string | null, forcePreferred = false) {
    if (!Array.isArray(next)) return activeConversationId.value
    conversations.value = next
    if (next.length === 0) {
      activeConversationId.value = null
      return null
    }
    const preferred = preferredId && next.some((item) => item.id === preferredId) ? preferredId : null
    const current = activeConversationId.value && next.some((item) => item.id === activeConversationId.value)
      ? activeConversationId.value
      : null
    activeConversationId.value = forcePreferred ? preferred ?? current ?? next[0]!.id : current ?? preferred ?? next[0]!.id
    return activeConversationId.value
  }

  function hasLocalMessages(conversationId: string | null) {
    return conversationId !== null && (conversationRuntime[conversationId]?.messages.length ?? 0) > 0
  }

  function loadConversations(preferredId?: string | null) {
    const id = courseId.value
    const version = contextVersion.value
    if (id === null) return
    const token = ++conversationsRequestToken

    return (async () => {
      try {
        const result = await getJson<ConversationsResponse>(
          `/api/courses/${encodeURIComponent(id)}/conversations`,
        )
        if (isCurrentContext(id, version) && token === conversationsRequestToken) {
          const selected = applyConversations(result.conversations, preferredId)
          if (selected && !hasLocalMessages(selected)) await loadMessages(selected)
        }
        return result
      } catch (cause) {
        if (isCurrentContext(id, version) && token === conversationsRequestToken) {
          error.value = errorMessage(cause)
        }
        throw cause
      }
    })()
  }

  function selectConversation(conversationId: string) {
    const id = courseId.value
    const version = contextVersion.value
    if (id === null || conversationId === activeConversationId.value) return
    activeConversationId.value = conversationId
    const runtime = runtimeFor(conversationId)
    if (runtime.messages.length === 0) {
      runtime.messagesRequestToken += 1
      void loadMessages(conversationId)?.catch(() => undefined)
    }
    void postJson<SaveConversationResponse>(`${conversationPath(id, conversationId)}/read`)
      .then((result) => {
        if (isCurrentConversation(id, version, conversationId)) conversations.value = result.conversations
      })
      .catch(() => undefined)
  }

  function createConversation() {
    const id = courseId.value
    const version = contextVersion.value
    if (id === null) return
    return (async () => {
      const result = await postJson<SaveConversationResponse>(
        `/api/courses/${encodeURIComponent(id)}/conversations`,
        { title: '新对话' },
      )
      if (isCurrentContext(id, version)) {
        applyConversations(result.conversations, result.conversation?.id, true)
        if (result.conversation?.id) runtimeFor(result.conversation.id).messages = []
      }
      return result
    })()
  }

  function renameConversation(conversationId: string, title: string) {
    const id = courseId.value
    const version = contextVersion.value
    if (id === null) return
    return postJson<SaveConversationResponse>(conversationPath(id, conversationId), { title })
      .then((result) => {
        if (isCurrentContext(id, version)) conversations.value = result.conversations
        return result
      })
  }

  function deleteConversation(conversationId: string) {
    const id = courseId.value
    const version = contextVersion.value
    if (id === null || conversations.value.length <= 1 || isConversationStreaming(conversationId)) return
    return postJson<SaveConversationResponse>(`${conversationPath(id, conversationId)}/delete`)
      .then(async (result) => {
        if (isCurrentContext(id, version)) {
          const wasActive = activeConversationId.value === conversationId
          const runtime = conversationRuntime[conversationId]
          runtime?.abortController?.abort()
          delete conversationRuntime[conversationId]
          const selected = applyConversations(result.conversations)
          if (wasActive && selected) await loadMessages()
        }
        return result
      })
  }

  function loadMessages(targetConversationId = activeConversationId.value) {
    const id = courseId.value
    const version = contextVersion.value
    const conversationId = targetConversationId
    if (id === null || conversationId === null) return
    const runtime = runtimeFor(conversationId)
    const token = ++runtime.messagesRequestToken
    const requestedMutationEpoch = runtime.mutationEpoch

    return (async () => {
      try {
        const result = await getJson<MessagesResponse>(
          scopedCoursePath(id, conversationId, 'messages'),
        )
        if (
          isCurrentContext(id, version) &&
          token === runtime.messagesRequestToken &&
          requestedMutationEpoch === runtime.mutationEpoch
        ) {
          runtime.messages = result.messages
          conversations.value = conversations.value.map((item) =>
            item.id === conversationId ? { ...item, unread_count: 0 } : item,
          )
        }
        return result
      } catch (cause) {
        if (
          isCurrentContext(id, version) &&
          token === runtime.messagesRequestToken &&
          requestedMutationEpoch === runtime.mutationEpoch
        ) {
          runtime.error = errorMessage(cause)
        }
        throw cause
      }
    })()
  }

  function loadNotes() {
    const id = courseId.value
    const version = contextVersion.value
    if (id === null) return
    const token = ++notesRequestToken
    const requestedMutationEpoch = notesMutationEpoch.value

    return (async () => {
      try {
        const result = await getJson<NotesResponse>(
          `/api/courses/${encodeURIComponent(id)}/notes`,
        )
        if (
          isCurrentContext(id, version) &&
          token === notesRequestToken &&
          requestedMutationEpoch === notesMutationEpoch.value
        ) {
          notes.value = result.notes
        }
        return result
      } catch (cause) {
        if (
          isCurrentContext(id, version) &&
          token === notesRequestToken &&
          requestedMutationEpoch === notesMutationEpoch.value
        ) {
          error.value = errorMessage(cause)
        }
        throw cause
      }
    })()
  }

  function send(question: string) {
    const id = courseId.value
    const version = contextVersion.value
    const conversationId = activeConversationId.value
    const normalizedQuestion = question.trim()
    if (id === null || conversationId === null) return
    const runtime = runtimeFor(conversationId)
    if (
      runtime.isStreaming ||
      busy.summary ||
      busy.quiz ||
      (normalizedQuestion.length === 0 && runtime.pendingFiles.length === 0)
    ) return

    const files = [...runtime.pendingFiles]
    runtime.pendingFiles = []
    const token = ++runtime.chatRequestToken
    runtime.messagesRequestToken += 1
    runtime.mutationEpoch += 1
    const controller = new AbortController()
    runtime.abortController = controller
    runtime.isStreaming = true
    runtime.error = null
    const timestamp = new Date().toISOString()
    const userMessage: Message = {
      role: 'user',
      content: normalizedQuestion || `已发送 ${files.length} 个附件`,
      citations: [],
      trace: [],
      created_at: timestamp,
    }
    const assistantMessage: Message = {
      role: 'assistant',
      content: '',
      citations: [],
      trace: [],
      created_at: timestamp,
      streaming: true,
      stream_status: '正在发送…',
      stream_thoughts: [],
    }
    runtime.messages.push(userMessage, assistantMessage)
    const streamingMessage = runtime.messages[runtime.messages.length - 1]!

    return (async () => {
      try {
        let result: ChatResult | undefined
        const path = scopedCoursePath(id, conversationId, 'chat')
        const onEvent = async (event: ChatStreamEvent) => {
          if (controller.signal.aborted || !isCurrentContext(id, version) || token !== runtime.chatRequestToken) return
          if (event.type === 'status') {
            streamingMessage.stream_status = event.detail
            if (event.stage === 'llm_retry') {
              streamingMessage.stream_thoughts = [
                ...(streamingMessage.stream_thoughts ?? []),
                event.detail,
              ]
            }
          } else if (event.type === 'thought') {
            const query = event.query ? ` · ${event.query}` : ''
            streamingMessage.stream_status = event.detail
            streamingMessage.stream_thoughts = [
              ...(streamingMessage.stream_thoughts ?? []),
              `${event.action}：${event.detail}${query}`,
            ]
          } else if (event.type === 'delta') {
            streamingMessage.stream_status = '正在生成回答…'
            for (const unit of displayUnits(event.delta)) {
              if (controller.signal.aborted || !isCurrentContext(id, version) || token !== runtime.chatRequestToken) return
              streamingMessage.content += unit
              await waitForStreamPaint()
            }
          } else if (event.type === 'done') {
            result = event.result
            if (streamingMessage.content !== event.result.answer) {
              streamingMessage.content = event.result.answer
            }
            streamingMessage.citations = event.result.citations
            streamingMessage.trace = event.result.trace
            streamingMessage.streaming = false
            streamingMessage.stream_status = ''
          }
        }
        if (files.length > 0) {
          const form = new FormData()
          form.append('question', normalizedQuestion)
          form.append('mode', mode.value)
          for (const file of files) form.append('files', file, file.name)
          await postFilesStream<ChatStreamEvent>(path, form, onEvent, controller.signal)
        } else {
          await postJsonStream<ChatStreamEvent>(path, {
            question: normalizedQuestion,
            mode: mode.value,
            conversation_id: conversationId,
          }, onEvent, controller.signal)
        }
        if (!result) {
          throw new Error('流式响应未正常完成')
        }
        return result
      } catch (cause) {
        if (isAbortError(cause)) {
          if (isCurrentContext(id, version) && token === runtime.chatRequestToken) {
            streamingMessage.streaming = false
            streamingMessage.stream_status = ''
            if (!streamingMessage.content) streamingMessage.content = '已停止生成。'
          }
          return undefined
        }
        if (isCurrentContext(id, version) && token === runtime.chatRequestToken) {
          runtime.error = errorMessage(cause)
          streamingMessage.streaming = false
          streamingMessage.stream_status = ''
          if (!streamingMessage.content) streamingMessage.content = '回答生成失败，请重试。'
        }
        throw cause
      } finally {
        if (runtime.abortController === controller) runtime.abortController = null
        if (isCurrentContext(id, version) && token === runtime.chatRequestToken) {
          runtime.isStreaming = false
          if (conversations.value.length > 0) void loadConversations()?.catch(() => undefined)
        }
      }
    })()
  }

  function stop(conversationId = activeConversationId.value) {
    if (conversationId === null) return
    const runtime = conversationRuntime[conversationId]
    if (!runtime?.isStreaming || !runtime.abortController) return
    runtime.abortController.abort()
    const latest = runtime.messages.at(-1)
    if (latest?.streaming) {
      latest.streaming = false
      latest.stream_status = ''
      if (!latest.content) latest.content = '已停止生成。'
    }
    runtime.isStreaming = false
  }

  function generateArtifact(kind: StudyArtifact) {
    const id = courseId.value
    const version = contextVersion.value
    const conversationId = activeConversationId.value
    if (id === null || conversationId === null || busy.chat || busy.summary || busy.quiz) return

    const token = ++artifactRequestToken
    busy[kind] = true
    error.value = null

    return (async () => {
      try {
        const result = await postJson<ArtifactResult>(
          scopedCoursePath(id, conversationId, kind),
        )
        await useCourseStore().loadCourses()
        if (isCurrentContext(id, version) && token === artifactRequestToken) {
          await loadMessages(conversationId)
          if (conversations.value.length > 0) await loadConversations(conversationId)
        }
        return result
      } catch (cause) {
        if (isCurrentContext(id, version) && token === artifactRequestToken) {
          error.value = errorMessage(cause)
        }
        throw cause
      } finally {
        if (isCurrentContext(id, version) && token === artifactRequestToken) {
          busy[kind] = false
        }
      }
    })()
  }

  function summary() {
    return generateArtifact('summary')
  }

  function quiz() {
    return generateArtifact('quiz')
  }

  function saveNote(title: string, content: string) {
    const id = courseId.value
    const version = contextVersion.value
    const normalizedContent = content.trim()
    if (id === null || normalizedContent.length === 0 || busy.note) return
    const token = ++noteRequestToken
    busy.note = true
    error.value = null

    return (async () => {
      try {
        const result = await postJson<SaveNotesResponse>(
          `/api/courses/${encodeURIComponent(id)}/notes`,
          {
            title: title.trim() || '学习笔记',
            content: normalizedContent,
          },
        )
        if (
          isCurrentContext(id, version) &&
          token === noteRequestToken
        ) {
          notesMutationEpoch.value += 1
          notes.value = result.notes
        }
        return result
      } catch (cause) {
        if (
          isCurrentContext(id, version) &&
          token === noteRequestToken
        ) {
          error.value = errorMessage(cause)
        }
        throw cause
      } finally {
        if (
          isCurrentContext(id, version) &&
          token === noteRequestToken
        ) {
          busy.note = false
        }
      }
    })()
  }

  function updateNote(noteId: number, title: string, content: string) {
    const id = courseId.value
    const version = contextVersion.value
    const normalizedTitle = title.trim()
    const normalizedContent = content.trim()
    if (id === null || normalizedContent.length === 0 || busy.note) return
    const token = ++noteRequestToken
    busy.note = true
    error.value = null

    return (async () => {
      try {
        const result = await postJson<SaveNotesResponse>(
          `/api/courses/${encodeURIComponent(id)}/notes/${encodeURIComponent(String(noteId))}`,
          {
            title: normalizedTitle || '学习笔记',
            content: normalizedContent,
          },
        )
        if (
          isCurrentContext(id, version) &&
          token === noteRequestToken
        ) {
          notesMutationEpoch.value += 1
          notes.value = result.notes
        }
        return result
      } catch (cause) {
        if (
          isCurrentContext(id, version) &&
          token === noteRequestToken
        ) {
          error.value = errorMessage(cause)
        }
        throw cause
      } finally {
        if (
          isCurrentContext(id, version) &&
          token === noteRequestToken
        ) {
          busy.note = false
        }
      }
    })()
  }

  function deleteNote(noteId: number) {
    const id = courseId.value
    const version = contextVersion.value
    if (id === null || busy.note) return
    const token = ++noteRequestToken
    busy.note = true
    error.value = null

    return (async () => {
      try {
        const result = await postJson<SaveNotesResponse>(
          `/api/courses/${encodeURIComponent(id)}/notes/${encodeURIComponent(String(noteId))}/delete`,
        )
        if (
          isCurrentContext(id, version) &&
          token === noteRequestToken
        ) {
          notesMutationEpoch.value += 1
          notes.value = result.notes
        }
        return result
      } catch (cause) {
        if (
          isCurrentContext(id, version) &&
          token === noteRequestToken
        ) {
          error.value = errorMessage(cause)
        }
        throw cause
      } finally {
        if (
          isCurrentContext(id, version) &&
          token === noteRequestToken
        ) {
          busy.note = false
        }
      }
    })()
  }

  function clearCourseMemory() {
    const id = courseId.value
    const version = contextVersion.value
    const conversationId = activeConversationId.value
    if (id === null || conversationId === null || busy.chat || busy.summary || busy.quiz || busy.memory) return
    const token = ++memoryRequestToken
    const runtime = runtimeFor(conversationId)
    runtime.messagesRequestToken += 1
    runtime.mutationEpoch += 1
    busy.memory = true
    error.value = null

    return (async () => {
      try {
        const result = await postJson<ClearCourseMemoryResponse>(
          scopedCoursePath(id, conversationId, 'memory/clear'),
        )
        if (
          isCurrentContext(id, version) &&
          token === memoryRequestToken
        ) {
          runtime.messages = result.messages
          if (conversations.value.length > 0) await loadConversations(conversationId)
        }
        return result
      } catch (cause) {
        if (
          isCurrentContext(id, version) &&
          token === memoryRequestToken
        ) {
          error.value = errorMessage(cause)
        }
        throw cause
      } finally {
        if (
          isCurrentContext(id, version) &&
          token === memoryRequestToken
        ) {
          busy.memory = false
        }
      }
    })()
  }

  return {
    messages,
    conversations,
    activeConversationId,
    activeConversation,
    notes,
    mode,
    draft,
    pendingFiles,
    busy,
    error,
    courseId,
    contextVersion,
    notesMutationEpoch,
    beginCourse,
    isCurrentContext,
    isConversationStreaming,
    navigateDraftHistory,
    loadConversations,
    selectConversation,
    createConversation,
    renameConversation,
    deleteConversation,
    loadMessages,
    loadNotes,
    send,
    stop,
    summary,
    quiz,
    saveNote,
    updateNote,
    deleteNote,
    clearCourseMemory,
  }
})
