import { reactive, ref } from 'vue'
import { defineStore } from 'pinia'

import { getJson, postFilesStream, postJson, postJsonStream } from '../services/api'
import type {
  ArtifactResult,
  ChatResult,
  ChatStreamEvent,
  Message,
  MessagesResponse,
  Note,
  NotesResponse,
  SaveNotesResponse,
} from '../types/api'
import { useCourseStore } from './course'

type StudyArtifact = 'summary' | 'quiz'

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const notes = ref<Note[]>([])
  const mode = ref('answer')
  const pendingFiles = ref<File[]>([])
  const busy = reactive({ chat: false, summary: false, quiz: false, note: false })
  const error = ref<string | null>(null)
  const courseId = ref<string | null>(null)
  const contextVersion = ref(0)
  const notesMutationEpoch = ref(0)

  let messagesRequestToken = 0
  let notesRequestToken = 0
  let chatRequestToken = 0
  let artifactRequestToken = 0
  let noteRequestToken = 0

  function isCurrentContext(id: string | null, version: number) {
    return courseId.value === id && contextVersion.value === version
  }

  function beginCourse(id: string | null, version: number) {
    courseId.value = id
    contextVersion.value = version
    notesMutationEpoch.value = 0
    messages.value = []
    notes.value = []
    pendingFiles.value = []
    error.value = null
    busy.chat = false
    busy.summary = false
    busy.quiz = false
    busy.note = false
    messagesRequestToken += 1
    notesRequestToken += 1
    chatRequestToken += 1
    artifactRequestToken += 1
    noteRequestToken += 1
  }

  function loadMessages() {
    const id = courseId.value
    const version = contextVersion.value
    if (id === null) return
    const token = ++messagesRequestToken

    return (async () => {
      try {
        const result = await getJson<MessagesResponse>(
          `/api/courses/${encodeURIComponent(id)}/messages`,
        )
        if (isCurrentContext(id, version) && token === messagesRequestToken) {
          messages.value = result.messages
        }
        return result
      } catch (cause) {
        if (isCurrentContext(id, version) && token === messagesRequestToken) {
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
    const normalizedQuestion = question.trim()
    if (
      id === null ||
      busy.chat ||
      busy.summary ||
      busy.quiz ||
      (normalizedQuestion.length === 0 && pendingFiles.value.length === 0)
    ) return

    const files = [...pendingFiles.value]
    pendingFiles.value = []
    const token = ++chatRequestToken
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
    }
    messages.value.push(userMessage, assistantMessage)

    return (async () => {
      try {
        let result: ChatResult | undefined
        const path = `/api/courses/${encodeURIComponent(id)}/chat`
        const onEvent = (event: ChatStreamEvent) => {
          if (!isCurrentContext(id, version) || token !== chatRequestToken) return
          if (event.type === 'status') {
            assistantMessage.stream_status = event.detail
          } else if (event.type === 'delta') {
            assistantMessage.content += event.delta
            assistantMessage.stream_status = '正在生成回答…'
          } else if (event.type === 'done') {
            result = event.result
            assistantMessage.content = event.result.answer
            assistantMessage.citations = event.result.citations
            assistantMessage.trace = event.result.trace
            assistantMessage.streaming = false
            assistantMessage.stream_status = ''
          }
        }
        if (files.length > 0) {
          const form = new FormData()
          form.append('question', normalizedQuestion)
          form.append('mode', mode.value)
          for (const file of files) form.append('files', file, file.name)
          await postFilesStream<ChatStreamEvent>(path, form, onEvent)
        } else {
          await postJsonStream<ChatStreamEvent>(path, {
            question: normalizedQuestion,
            mode: mode.value,
          }, onEvent)
        }
        if (!result) {
          throw new Error('流式响应未正常完成')
        }
        return result
      } catch (cause) {
        if (isCurrentContext(id, version) && token === chatRequestToken) {
          error.value = errorMessage(cause)
          assistantMessage.streaming = false
          assistantMessage.stream_status = ''
          if (!assistantMessage.content) assistantMessage.content = '回答生成失败，请重试。'
        }
        throw cause
      } finally {
        if (isCurrentContext(id, version) && token === chatRequestToken) {
          busy.chat = false
        }
      }
    })()
  }

  function generateArtifact(kind: StudyArtifact) {
    const id = courseId.value
    const version = contextVersion.value
    if (id === null || busy.chat || busy.summary || busy.quiz) return

    const token = ++artifactRequestToken
    busy[kind] = true
    error.value = null

    return (async () => {
      try {
        const result = await postJson<ArtifactResult>(
          `/api/courses/${encodeURIComponent(id)}/${kind}`,
        )
        await useCourseStore().loadCourses()
        if (isCurrentContext(id, version) && token === artifactRequestToken) {
          await loadMessages()
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

  return {
    messages,
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
    loadMessages,
    loadNotes,
    send,
    summary,
    quiz,
    saveNote,
  }
})
