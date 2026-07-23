<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useChatStore } from '../stores/chat'
import { useCourseStore } from '../stores/course'
import { usePreviewStore } from '../stores/preview'
import type { ConfigCapabilityStatus, FileLeafNode } from '../types/api'
import FileTree from './FileTree.vue'

defineProps<{ sidebarOpen: boolean }>()

const emit = defineEmits<{
  close: []
}>()

const course = useCourseStore()
const chat = useChatStore()
const preview = usePreviewStore()
const rootFolder = ref('')
const coursePicker = ref<HTMLInputElement | null>(null)
const settingsMenu = ref<HTMLDetailsElement | null>(null)
const error = ref<string | null>(null)
const dropActive = ref(false)

const healthItems = computed(() => {
  const preferred = ['ai', 'rag_index', 'vector', 'material_root', 'data_dir', 'telemetry', 'backup']
  const items = course.configStatus?.capabilities ?? []
  return preferred
    .map((key) => items.find((item) => item.key === key))
    .filter((item): item is ConfigCapabilityStatus => item !== undefined)
})
const healthSummary = computed(() => {
  if (course.configStatusLoading) return '检查中'
  const missing = healthItems.value.filter((item) => item.status === 'warning' || item.status === 'error')
  if ((course.configStatus?.overall ?? 'warning') === 'ok' && missing.length === 0) return '正常'
  if (missing.length === 0) return '需关注'
  return `缺 ${missing.map((item) => item.label).join('、')}`
})

watch(() => course.config?.root_folder, (value) => {
  rootFolder.value = value ?? ''
}, { immediate: true })

function closeSettingsOnOutsideClick(event: PointerEvent) {
  const menu = settingsMenu.value
  if (!menu?.open) return
  if (event.target instanceof Node && menu.contains(event.target)) return
  menu.open = false
}

onMounted(() => {
  document.addEventListener('pointerdown', closeSettingsOnOutsideClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeSettingsOnOutsideClick)
})

async function run(action: () => unknown | Promise<unknown>) {
  error.value = null
  try {
    await action()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  }
}

function chooseFile(file: FileLeafNode) {
  void run(() => preview.openFile(file))
  emit('close')
}

function filesFrom(target: EventTarget | null) {
  return target instanceof HTMLInputElement ? [...(target.files ?? [])] : []
}

function upload(files: File[]) {
  if (files.length > 0) void run(() => course.uploadCourseFiles(files))
}

function createConversation() {
  void run(() => chat.createConversation())
}

function renameConversation(conversationId: string, currentTitle: string) {
  const next = window.prompt('对话名称', currentTitle)
  if (next === null || next.trim() === currentTitle.trim()) return
  void run(() => chat.renameConversation(conversationId, next))
}

function deleteConversation(conversationId: string, title: string) {
  if (!window.confirm(`删除对话「${title}」？课程资料不会删除。`)) return
  void run(() => chat.deleteConversation(conversationId))
}

function onDrop(event: DragEvent) {
  event.preventDefault()
  dropActive.value = false
  upload([...(event.dataTransfer?.files ?? [])])
}

function onDropLeave(event: DragEvent) {
  if (event.currentTarget !== event.target) return
  dropActive.value = false
}
</script>

<template>
  <aside class="course-sidebar" aria-label="课程与资料">
    <header class="brand-block">
      <span class="brand-mark" aria-hidden="true">LC</span>
      <div><strong>Local Course</strong><span>课程学习助手</span></div>
      <details ref="settingsMenu" class="settings-menu">
        <summary aria-label="打开设置" title="设置">☰</summary>
        <div class="settings-panel">
          <label for="root-folder">资料根目录</label>
          <input id="root-folder" v-model="rootFolder" />
          <button type="button" :disabled="course.savingRoot" @click="run(() => course.saveRoot(rootFolder))">设置根目录</button>
          <button type="button" :disabled="!course.activeCourse || course.indexing" @click="run(course.indexActiveCourse)">{{ course.indexStatus ?? '构建知识库' }}</button>
          <input
            ref="coursePicker"
            type="file"
            multiple
            hidden
            @change="upload(filesFrom($event.target))"
          />
          <button type="button" :disabled="!course.activeCourse" @click="coursePicker?.click()">添加课程资料</button>
        </div>
      </details>
      <button type="button" aria-label="关闭课程栏" @click="emit('close')">×</button>
    </header>

    <section class="sidebar-section course-section" aria-labelledby="course-list-title">
      <div class="section-heading">
        <h2 id="course-list-title">课程</h2>
        <button class="icon-button" type="button" aria-label="刷新课程" title="刷新课程" :disabled="course.loading" @click="run(course.loadCourses)">↻</button>
      </div>
      <p v-if="course.courses.length === 0">请先设置资料根目录</p>
      <button
        v-for="item in course.courses"
        :key="item.id"
        type="button"
        class="course-button"
        :aria-pressed="item.id === course.activeCourseId"
        :title="item.path"
        @click="course.selectCourse(item)"
      >
        <span class="course-main"><span class="course-icon" aria-hidden="true">▤</span><span class="course-label">{{ item.name }}</span></span>
        <span class="course-count">{{ item.file_count }} 个</span>
      </button>
    </section>

    <section class="sidebar-section conversation-section" aria-labelledby="conversation-list-title">
      <div class="section-heading">
        <h2 id="conversation-list-title">对话</h2>
        <button class="icon-button" type="button" aria-label="新建对话" title="新建对话" :disabled="!course.activeCourse" @click="createConversation">+</button>
      </div>
      <p v-if="!course.activeCourse">选择课程后显示对话</p>
      <div
        v-for="item in chat.conversations"
        v-else
        :key="item.id"
        class="conversation-button"
      >
        <button
          type="button"
          class="conversation-select"
          :aria-pressed="item.id === chat.activeConversationId"
          :title="`${item.title}，${item.message_count} 条消息`"
          @click="chat.selectConversation(item.id)"
          @dblclick="renameConversation(item.id, item.title)"
        >
          <span class="conversation-title">
            <span v-if="item.unread_count > 0" class="unread-dot" aria-label="有未读消息"></span>
            <span v-if="chat.isConversationStreaming(item.id)" class="running-dot" aria-label="正在生成回答"></span>
            <span>{{ item.title }}</span>
          </span>
          <span class="conversation-meta">{{ chat.isConversationStreaming(item.id) ? '生成中' : item.message_count }}</span>
        </button>
        <button
          type="button"
          class="conversation-delete"
          aria-label="删除对话"
          :title="chat.isConversationStreaming(item.id) ? '回答生成中，不能删除' : '删除对话'"
          :disabled="chat.conversations.length <= 1 || chat.isConversationStreaming(item.id)"
          @click.stop="deleteConversation(item.id, item.title)"
        >
          ×
        </button>
      </div>
    </section>

    <section class="sidebar-section file-section" aria-labelledby="file-tree-title">
      <div class="section-heading"><h2 id="file-tree-title">当前资料</h2></div>
      <FileTree
        v-if="course.activeCourse"
        :nodes="course.activeCourse.children"
        :active-file-id="preview.activeFile?.id"
        @select="chooseFile"
      />
      <p v-else>选择课程后显示文件</p>
    </section>

    <footer class="sidebar-footer">
      <div class="service-status" aria-label="配置健康状态">
        <div class="status-heading">
          <span>配置：{{ healthSummary }}</span>
          <button class="icon-button" type="button" aria-label="刷新配置健康状态" title="刷新配置健康状态" :disabled="course.configStatusLoading" @click="run(course.loadConfigStatus)">↻</button>
        </div>
      </div>
      <div
        class="course-drop-zone"
        tabindex="0"
        :data-dragging="dropActive"
        @dragenter.prevent="dropActive = true"
        @dragover.prevent="dropActive = true"
        @dragleave="onDropLeave"
        @drop="onDrop"
      >
        拖入文件，加入当前课程
      </div>
      <p v-if="error" role="alert">{{ error }}</p>
    </footer>
  </aside>
</template>

<style scoped>
.course-sidebar { min-width: 0; }
.brand-block span { display: block; }
button { min-height: 32px; }
.conversation-section {
  flex: 1 1 30%;
  overflow: auto;
  border-bottom: 1px solid var(--line);
}
.settings-menu {
  position: relative;
  margin-left: auto;
}
.settings-menu > summary {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 7px;
  color: var(--muted);
  cursor: pointer;
  list-style: none;
}
.settings-menu > summary::-webkit-details-marker {
  display: none;
}
.settings-panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 15;
  display: grid;
  width: min(17rem, 78vw);
  gap: 7px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  padding: 9px;
  box-shadow: var(--shadow);
}
.settings-panel label {
  color: var(--muted);
  font-size: 11px;
}
.settings-panel input {
  width: 100%;
  min-width: 0;
  height: 32px;
  padding: 5px 7px;
}
.settings-panel button {
  width: 100%;
  border-color: var(--line);
  background: var(--surface);
  color: var(--text);
}
</style>
