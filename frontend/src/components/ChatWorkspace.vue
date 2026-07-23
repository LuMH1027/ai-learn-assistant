<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { useChatStore } from '../stores/chat'
import { useCourseStore } from '../stores/course'
import { useLayoutStore } from '../stores/layout'
import { usePreviewStore } from '../stores/preview'
import { renderMarkdown } from '../services/markdown'
import type { FileLeafNode, FileNode } from '../types/api'

defineProps<{ sidebarOpen: boolean }>()

const emit = defineEmits<{
  'toggle-sidebar': []
  'open-notes': []
}>()

const chat = useChatStore()
const course = useCourseStore()
const layout = useLayoutStore()
const preview = usePreviewStore()
const chatPicker = ref<HTMLInputElement | null>(null)
const messagesPanel = ref<HTMLElement | null>(null)
const busy = computed(() => chat.busy.chat || chat.busy.summary || chat.busy.quiz || chat.busy.memory)

watch(
  () => {
    const latest = chat.messages.at(-1)
    return [chat.messages.length, latest?.content.length, latest?.stream_status, latest?.streaming] as const
  },
  (current, previous) => {
    const latest = chat.messages.at(-1)
    const messageCountChanged = current[0] !== previous?.[0]
    if (!latest?.streaming && !messageCountChanged) return
    if (messagesPanel.value) messagesPanel.value.scrollTop = messagesPanel.value.scrollHeight
  },
  { flush: 'post' },
)

function findFile(nodes: FileNode[], id: string): FileLeafNode | null {
  for (const node of nodes) {
    if (node.type === 'file' && node.id === id) return node
    if (node.type === 'folder') {
      const found = findFile(node.children, id)
      if (found) return found
    }
  }
  return null
}

function openCitation(fileId: string, citationIndex: number, messageIndex: number) {
  const citation = chat.messages[messageIndex]?.citations[citationIndex]
  const file = course.activeCourse && findFile(course.activeCourse.children, fileId)
  if (citation && file) void preview.openCitation(file, citation)?.catch(() => undefined)
}

function generate(kind: 'summary' | 'quiz') {
  void chat[kind]()?.catch(() => undefined)
}

function clearMemory() {
  const activeConversationName = chat.activeConversation?.title ?? '当前对话'
  if (!window.confirm(`清空「${activeConversationName}」的消息和记忆？课程资料和课程笔记不会删除。`)) return
  void chat.clearCourseMemory()?.catch(() => undefined)
}

async function send() {
  const value = chat.draft
  const result = chat.send(value)
  if (result) {
    chat.draft = ''
    await result.catch(() => undefined)
  }
}

function onComposerKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void send()
    return
  }
  if ((event.key === 'ArrowUp' || event.key === 'ArrowDown') && shouldNavigateHistory(event)) {
    const direction = event.key === 'ArrowUp' ? 'previous' : 'next'
    if (chat.navigateDraftHistory(direction)) event.preventDefault()
  }
}

function shouldNavigateHistory(event: KeyboardEvent) {
  if (event.shiftKey || event.altKey || event.ctrlKey || event.metaKey || event.isComposing) return false
  const target = event.target
  if (!(target instanceof HTMLTextAreaElement)) return false
  if (target.selectionStart !== target.selectionEnd) return false
  const beforeCursor = target.value.slice(0, target.selectionStart)
  const afterCursor = target.value.slice(target.selectionEnd)
  if (event.key === 'ArrowUp') return !beforeCursor.includes('\n')
  return !afterCursor.includes('\n')
}

function attach(files: File[]) {
  chat.pendingFiles = files
}

function filesFrom(target: EventTarget | null) {
  return target instanceof HTMLInputElement ? [...(target.files ?? [])] : []
}

function onDrop(event: DragEvent) {
  event.preventDefault()
  attach([...(event.dataTransfer?.files ?? [])])
}

function assistantMarkdown(content: string) {
  return renderMarkdown(content)
}
</script>

<template>
  <main class="chat-workspace" aria-label="课程对话" @dragover.prevent @drop="onDrop">
    <header class="agent-header">
      <button
        type="button"
        :aria-label="sidebarOpen ? '关闭课程栏' : '打开课程栏'"
        :aria-expanded="sidebarOpen"
        @click="emit('toggle-sidebar')"
      >
        ☰
      </button>
      <div>
        <h1>{{ course.activeCourse?.name ?? '课程 Agent' }}</h1>
        <p>{{ course.activeCourse ? `${chat.activeConversation?.title ?? '未选择对话'} · ${course.activeCourse.file_count} 个课程文件` : '选择一门课程开始学习' }}</p>
      </div>
      <span role="status">{{ busy || course.indexing ? 'Running' : 'Idle' }}</span>
      <button
        type="button"
        :aria-label="layout.previewOpen ? '关闭资料预览' : '打开资料预览'"
        :aria-pressed="layout.previewOpen"
        @click="layout.setPreviewOpen(!layout.previewOpen)"
      >
        预览
      </button>
    </header>

    <nav class="study-toolbar" aria-label="学习工具">
      <button type="button" aria-current="page">对话</button>
      <button type="button" aria-label="生成课程摘要" :disabled="!course.activeCourse || busy" @click="generate('summary')">生成摘要</button>
      <button type="button" aria-label="生成练习题" :disabled="!course.activeCourse || busy" @click="generate('quiz')">生成练习</button>
      <button
        type="button"
        aria-label="清空当前对话和记忆"
        :disabled="!course.activeCourse || busy"
        @click="clearMemory"
      >
        {{ chat.busy.memory ? '清空中…' : '清空记忆' }}
      </button>
      <button id="notes-toggle" type="button" aria-label="打开课程笔记" :disabled="!course.activeCourse" @click="emit('open-notes')">课程笔记</button>
      <label for="chat-mode">模式</label>
      <select id="chat-mode" v-model="chat.mode" aria-label="问答模式">
        <option value="answer">答疑</option>
        <option value="guide">启发提示</option>
        <option value="review">复习</option>
      </select>
    </nav>

    <section ref="messagesPanel" class="messages" aria-label="对话消息" aria-live="polite">
      <article v-for="(message, messageIndex) in chat.messages" :key="`${message.created_at}-${messageIndex}`" :class="message.role">
        <p v-if="message.streaming" class="stream-status" role="status">{{ message.stream_status }}</p>
        <details v-if="message.stream_thoughts?.length" class="thinking-panel" :open="message.streaming">
          <summary>当前思考</summary>
          <p v-for="(thought, thoughtIndex) in message.stream_thoughts" :key="thoughtIndex">{{ thought }}</p>
        </details>
        <div
          v-if="message.content && message.role === 'assistant'"
          class="message-markdown"
          :class="{ 'streaming-content': message.streaming }"
          v-html="assistantMarkdown(message.content)"
        />
        <p v-else-if="message.content" :class="{ 'streaming-content': message.streaming }">{{ message.content }}</p>
        <details v-if="message.trace.length">
          <summary>处理过程</summary>
          <p v-for="step in message.trace" :key="step.label">{{ step.label }}：{{ step.detail }}</p>
        </details>
        <template v-for="(citation, citationIndex) in message.citations" :key="`${citation.file_id}-${citation.chunk_index}`">
          <a
            v-if="citation.source_type === 'web' && citation.url"
            :href="citation.url"
            :data-web-source="citation.url"
            target="_blank"
            rel="noopener noreferrer"
          >
            <template v-if="citation.reference_label">[{{ citation.reference_label }}] </template>网页来源：{{ citation.file_name }}
          </a>
          <button
            v-else
            type="button"
            :data-citation-file="citation.file_id"
            @click="openCitation(citation.file_id, citationIndex, messageIndex)"
          >
            <template v-if="citation.reference_label">[{{ citation.reference_label }}] </template>课程来源：{{ citation.file_name }}<template v-if="citation.page"> · 第 {{ citation.page }} 页</template>
          </button>
        </template>
      </article>
      <p v-if="chat.error" role="alert">{{ chat.error }}</p>
    </section>

    <div class="composer">
      <input ref="chatPicker" type="file" multiple hidden @change="attach(filesFrom($event.target))" />
      <button type="button" aria-label="添加聊天附件" :disabled="!course.activeCourse || busy" @click="chatPicker?.click()">添加附件</button>
      <label for="course-question">课程问题</label>
      <textarea
        id="course-question"
        v-model="chat.draft"
        aria-label="课程问题"
        placeholder="围绕当前课程资料提问…"
        @keydown="onComposerKeydown"
      />
      <button
        v-if="chat.busy.chat"
        type="button"
        class="stop-button"
        aria-label="停止回答"
        title="停止回答"
        @click="chat.stop()"
      >
        ■
      </button>
      <button v-else type="button" class="send-button" aria-label="发送问题" :disabled="!course.activeCourse || busy" @click="send">↑</button>
      <p v-if="chat.pendingFiles.length">已附加 {{ chat.pendingFiles.length }} 个文件</p>
    </div>
  </main>
</template>

<style scoped>
.chat-workspace { min-width: 0; }
button, select { min-height: 44px; }
.stream-status { color: var(--muted); font-size: 12px; }
.stream-status::before { content: ''; display: inline-block; width: 6px; height: 6px; margin-right: 7px; border-radius: 50%; background: var(--accent); animation: pulse 1s ease-in-out infinite; }
.streaming-content::after { content: '▋'; margin-left: 2px; color: var(--accent); animation: pulse .8s steps(2, end) infinite; }
.message-markdown {
  overflow-wrap: anywhere;
}
.message-markdown :deep(h1),
.message-markdown :deep(h2),
.message-markdown :deep(h3),
.message-markdown :deep(h4) {
  margin: 0.85em 0 0.35em;
  line-height: 1.25;
}
.message-markdown :deep(h1:first-child),
.message-markdown :deep(h2:first-child),
.message-markdown :deep(h3:first-child),
.message-markdown :deep(p:first-child),
.message-markdown :deep(ul:first-child),
.message-markdown :deep(ol:first-child),
.message-markdown :deep(pre:first-child) {
  margin-top: 0;
}
.message-markdown :deep(h1) { font-size: 1.35em; }
.message-markdown :deep(h2) { font-size: 1.18em; }
.message-markdown :deep(h3) { font-size: 1.05em; }
.message-markdown :deep(p),
.message-markdown :deep(ul),
.message-markdown :deep(ol),
.message-markdown :deep(blockquote),
.message-markdown :deep(pre),
.message-markdown :deep(table) {
  margin: 0 0 0.58em;
}
.message-markdown :deep(ul),
.message-markdown :deep(ol) {
  padding-left: 1.28em;
}
.message-markdown :deep(li + li) {
  margin-top: 0.12em;
}
.message-markdown :deep(code) {
  border-radius: 4px;
  background: var(--surface-subtle);
  padding: 0.1em 0.3em;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 0.9em;
}
.message-markdown :deep(pre) {
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-subtle);
  padding: 0.58em 0.68em;
  white-space: pre;
}
.message-markdown :deep(pre code) {
  background: transparent;
  padding: 0;
}
.message-markdown :deep(blockquote) {
  border-left: 3px solid var(--accent);
  background: var(--surface-subtle);
  padding: 0.38em 0.62em;
  color: var(--muted);
}
.message-markdown :deep(table) {
  width: 100%;
  border-collapse: collapse;
}
.message-markdown :deep(th),
.message-markdown :deep(td) {
  border: 1px solid var(--line);
  padding: 0.3em 0.42em;
  text-align: left;
}
.message-markdown :deep(a) {
  color: var(--accent);
}
.message-markdown :deep(:last-child) {
  margin-bottom: 0;
}
.thinking-panel {
  margin: 0.25rem 0 0.38rem;
  border-left: 2px solid var(--accent);
  padding-left: 0.5rem;
  color: var(--muted);
  font-size: 0.78rem;
}
.thinking-panel summary {
  cursor: pointer;
  color: var(--text);
  font-weight: 650;
}
.thinking-panel p {
  margin: 0.16rem 0 0;
}
.stop-button { border-color: color-mix(in srgb, var(--danger) 35%, var(--line)); color: var(--danger); }
@keyframes pulse { 50% { opacity: .25; } }
</style>
