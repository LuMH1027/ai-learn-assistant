<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import ChatWorkspace from './components/ChatWorkspace.vue'
import CourseSidebar from './components/CourseSidebar.vue'
import FilePreview from './components/FilePreview.vue'
import NotesDrawer from './components/NotesDrawer.vue'
import ResizableWorkspace from './components/ResizableWorkspace.vue'
import { useChatStore } from './stores/chat'
import { useCourseStore } from './stores/course'
import { useLayoutStore } from './stores/layout'
import { usePreviewStore } from './stores/preview'

const MOBILE_QUERY = '(max-width: 60rem)'

const course = useCourseStore()
const chat = useChatStore()
const layout = useLayoutStore()
const preview = usePreviewStore()
const isMobile = ref(false)
const sidebarOpen = ref(false)
const notesOpen = ref(false)
const toast = ref<string | null>(null)
let media: MediaQueryList | null = null

function showError(cause: unknown) {
  toast.value = cause instanceof Error ? cause.message : String(cause)
}

function syncMedia(event: MediaQueryListEvent | MediaQueryList) {
  isMobile.value = event.matches
  if (!event.matches) sidebarOpen.value = false
}

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
  if (isMobile.value && sidebarOpen.value && layout.previewOpen) {
    layout.setPreviewOpen(false)
  }
}

async function loadChatContext() {
  try {
    await chat.loadConversations()
  } catch {
    await chat.loadMessages()
    chat.error = null
  }
}

watch(
  () => [course.activeCourseId, course.contextVersion] as const,
  ([id, version]) => {
    chat.beginCourse(id, version)
    preview.beginCourse(id, version)
    notesOpen.value = false
    if (id !== null) {
      void Promise.allSettled([loadChatContext(), chat.loadNotes()]).then((results) => {
        const rejected = results.find((result) => result.status === 'rejected')
        if (rejected?.status === 'rejected') showError(rejected.reason)
      })
    }
  },
  { immediate: true },
)

onMounted(() => {
  media = window.matchMedia(MOBILE_QUERY)
  syncMedia(media)
  media.addEventListener?.('change', syncMedia)
  layout.hydrate(media.matches)
  void Promise.allSettled([course.loadConfig(), course.loadConfigStatus()]).then((results) => {
    const rejected = results.find((result) => result.status === 'rejected')
    if (rejected?.status === 'rejected') showError(rejected.reason)
  })
  void course.loadCourses().catch(showError)
})

onBeforeUnmount(() => {
  media?.removeEventListener?.('change', syncMedia)
})
</script>

<template>
  <a class="skip-link" href="#course-chat">跳到学习对话</a>
  <ResizableWorkspace :is-mobile="isMobile" :sidebar-open="sidebarOpen">
    <template #sidebar>
      <CourseSidebar
        :sidebar-open="sidebarOpen"
        :inert="isMobile && !sidebarOpen ? true : undefined"
        @close="sidebarOpen = false"
      />
    </template>
    <template #main>
      <ChatWorkspace
        id="course-chat"
        :sidebar-open="sidebarOpen"
        :inert="isMobile && layout.previewOpen ? true : undefined"
        @toggle-sidebar="toggleSidebar"
        @open-notes="notesOpen = true"
      />
    </template>
    <template #preview>
      <FilePreview
        :aria-hidden="layout.previewOpen ? undefined : true"
        :inert="!layout.previewOpen ? true : undefined"
      />
    </template>
  </ResizableWorkspace>
  <NotesDrawer :open="notesOpen" @close="notesOpen = false" />
  <div class="toast" role="status" aria-live="polite">{{ toast }}</div>
</template>

<style scoped>
.skip-link { position: absolute; transform: translateY(-200%); }
.skip-link:focus { transform: translateY(0); }
.toast:empty { display: none; }
</style>
