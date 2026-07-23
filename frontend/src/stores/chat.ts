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
  const messages = ref<Message[]>([])
  const notes = ref<Note[]>([])
  const mode = ref<StudyMode>('answer')
  const pendingFiles = ref<File[]>([])
  const busy = reactive({ chat: false, summary: false, quiz: false, note: false, memory: false })
  const error = ref<string | null>(null)
  const courseId = ref<string | null>(null)
  const contextVersion = ref(0)
  const notesMutationEpoch = ref(0)

  let messagesRequestToken = 0
  let conversationsRequestToken = 0
  let notesRequestToken = 0
  let chatRequestToken = 0
  let artifactRequestToken = 0
  let noteRequestToken = 0
  let memoryRequestToken = 0
  let chatAbortController: AbortController | null = null

  function isCurrentContext(id: string | null, version: number) {
    return courseId.value === id && contextVersion.value === version
  }

  function isCurrentConversation(id: string | null, version: number, conversationId: string | null) {
    return isCurrentContext(id, version) && activeConversationId.value === conversationId
  }

  const activeConversation = computed(() =>
    conversations.value.find((item) => item.id === activeConversationId.value) ??
    (activeConversationId.value ? {
      id: activeConversationId.value,
      title: activeConversationId.value === 'default' ? '历史对话' : '新对话',
      created_at: '',
      updated_at: '',
      last_read_at: '',
      message_count: messages.value.length,
      unread_count: 0,
    } : null),
  )

  function beginCourse(id: string | null, version: number) {
    chatAbortController?.abort()
    chatAbortController = null
    courseId.value = id
    contextVersion.value = version
    notesMutationEpoch.value = 0
    conversations.value = []
    activeConversationId.value = id === null ? null : 'default'
    messages.value = []
    notes.value = []
    pendingFiles.value = []
    error.value = null
    busy.chat = false
    busy.summary = false
    busy.quiz = false
    busy.note = false
    busy.memory = false
    conversationsRequestToken += 1
    messagesRequestToken += 1
    notesRequestToken += 1
    chatRequestToken += 1
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

  function applyConversations(next: Conversation[], preferredId?: string | null) {
    if (!Array.isArray(next)) return activeConversationId.value
    conversations.value = next
    if (next.length === 0) {
      activeConversationId.value = null
      messages.value = []
      return null
    }
    const preferred = preferredId && next.some((item) => item.id === preferredId) ? preferredId : null
    const current = activeConversationId.value && next.some((item) => item.id === activeConversationId.value)
      ? activeConversationId.value
      : null
    activeConversationId.value = preferred ?? current ?? next[0]!.id
    return activeConversationId.value
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
          if (selected) await loadMessages()
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
    messages.value = []
    messagesRequestToken += 1
    void loadMessages()?.catch(() => undefined)
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
        applyConversations(result.conversations, result.conversation?.id)
        messages.value = []
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
    if (id === null || conversations.value.length <= 1) return
    return postJson<SaveConversationResponse>(`${conversationPath(id, conversationId)}/delete`)
      .then(async (result) => {
        if (isCurrentContext(id, version)) {
          const wasActive = activeConversationId.value === conversationId
          const selected = applyConversations(result.conversations)
          if (wasActive && selected) await loadMessages()
        }
        return result
      })
  }

  function loadMessages() {
    const id = courseId.value
    const version = contextVersion.value
    const conversationId = activeConversationId.value
    if (id === null || conversationId === null) return
    const token = ++messagesRequestToken

    return (async () => {
      try {
        const result = await getJson<MessagesResponse>(
          scopedCoursePath(id, conversationId, 'messages'),
        )
        if (isCurrentConversation(id, version, conversationId) && token === messagesRequestToken) {
          messages.value = result.messages
          conversations.value = conversations.value.map((item) =>
            item.id === conversationId ? { ...item, unread_count: 0 } : item,
          )
        }
        return result
      } catch (cause) {
        if (isCurrentConversation(id, version, conversationId) && token === messagesRequestToken) {
          error.value = errorMessage(cause)
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
    if (
      id === null ||
      conversationId === null ||
      busy.chat ||
      busy.summary ||
      busy.quiz ||
      (normalizedQuestion.length === 0 && pendingFiles.value.length === 0)
    ) return

    const files = [...pendingFiles.value]
    pendingFiles.value = []
    const token = ++chatRequestToken
    const controller = new AbortController()
    chatAbortController = controller
    busy.chat = true
    error.value = null
    messagesRequestToken += 1
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
    messages.value.push(userMessage, assistantMessage)
    const streamingMessage = messages.value[messages.value.length - 1]!

    return (async () => {
      try {
        let result: ChatResult | undefined
        const path = scopedCoursePath(id, conversationId, 'chat')
        const onEvent = async (event: ChatStreamEvent) => {
          if (controller.signal.aborted || !isCurrentConversation(id, version, conversationId) || token !== chatRequestToken) return
          if (event.type === 'status') {
            streamingMessage.stream_status = event.detail
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
              if (controller.signal.aborted || !isCurrentConversation(id, version, conversationId) || token !== chatRequestToken) return
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
          if (isCurrentContext(id, version) && token === chatRequestToken) {
            streamingMessage.streaming = false
            streamingMessage.stream_status = ''
            if (!streamingMessage.content) streamingMessage.content = '已停止生成。'
          }
          return undefined
        }
        if (isCurrentContext(id, version) && token === chatRequestToken) {
          error.value = errorMessage(cause)
          streamingMessage.streaming = false
          streamingMessage.stream_status = ''
          if (!streamingMessage.content) streamingMessage.content = '回答生成失败，请重试。'
        }
        throw cause
      } finally {
        if (chatAbortController === controller) chatAbortController = null
        if (isCurrentContext(id, version) && token === chatRequestToken) {
          busy.chat = false
          if (conversations.value.length > 0) void loadConversations(conversationId)?.catch(() => undefined)
        }
      }
    })()
  }

  function stop() {
    if (!busy.chat || !chatAbortController) return
    chatAbortController.abort()
    const latest = messages.value.at(-1)
    if (latest?.streaming) {
      latest.streaming = false
      latest.stream_status = ''
      if (!latest.content) latest.content = '已停止生成。'
    }
    busy.chat = false
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
          await loadMessages()
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
    messagesRequestToken += 1
    busy.memory = true
    error.value = null

    return (async () => {
      try {
        const result = await postJson<ClearCourseMemoryResponse>(
          scopedCoursePath(id, conversationId, 'memory/clear'),
        )
        if (
          isCurrentConversation(id, version, conversationId) &&
          token === memoryRequestToken
        ) {
          messages.value = result.messages
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
    pendingFiles,
    busy,
    error,
    courseId,
    contextVersion,
    notesMutationEpoch,
    beginCourse,
    isCurrentContext,
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
