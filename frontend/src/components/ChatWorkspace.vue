<script setup lang="ts">
import { computed, ref } from 'vue'

import { useChatStore } from '../stores/chat'
import { useCourseStore } from '../stores/course'
import { useLayoutStore } from '../stores/layout'
import { usePreviewStore } from '../stores/preview'
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
const question = ref('')
const chatPicker = ref<HTMLInputElement | null>(null)
const busy = computed(() => chat.busy.chat || chat.busy.summary || chat.busy.quiz)

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

async function send() {
  const value = question.value
  const result = chat.send(value)
  if (result) {
    question.value = ''
    await result.catch(() => undefined)
  }
}

function onComposerKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey) return
  event.preventDefault()
  void send()
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
        <p>{{ course.activeCourse ? `${course.activeCourse.file_count} 个文件 · 独立会话与记忆` : '选择一门课程开始学习' }}</p>
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
      <button id="notes-toggle" type="button" aria-label="打开课程笔记" :disabled="!course.activeCourse" @click="emit('open-notes')">课程笔记</button>
      <label for="chat-mode">模式</label>
      <select id="chat-mode" v-model="chat.mode" aria-label="问答模式">
        <option value="answer">答疑</option>
        <option value="socratic">启发</option>
        <option value="homework">作业提示</option>
        <option value="review">复习</option>
      </select>
    </nav>

    <section class="messages" aria-label="对话消息" aria-live="polite">
      <article v-for="(message, messageIndex) in chat.messages" :key="`${message.created_at}-${messageIndex}`" :class="message.role">
        <p>{{ message.content }}</p>
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
        v-model="question"
        aria-label="课程问题"
        placeholder="围绕当前课程资料提问…"
        @keydown="onComposerKeydown"
      />
      <button type="button" aria-label="发送问题" :disabled="!course.activeCourse || busy" @click="send">发送</button>
      <p v-if="chat.pendingFiles.length">已附加 {{ chat.pendingFiles.length }} 个文件</p>
    </div>
  </main>
</template>

<style scoped>
.chat-workspace { min-width: 0; }
button, select { min-height: 44px; }
</style>
