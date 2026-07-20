<script setup lang="ts">
import { ref, watch } from 'vue'

import { useCourseStore } from '../stores/course'
import { usePreviewStore } from '../stores/preview'
import type { FileLeafNode } from '../types/api'
import FileTree from './FileTree.vue'

defineProps<{ sidebarOpen: boolean }>()

const emit = defineEmits<{
  close: []
}>()

const course = useCourseStore()
const preview = usePreviewStore()
const rootFolder = ref('')
const coursePicker = ref<HTMLInputElement | null>(null)
const error = ref<string | null>(null)

watch(() => course.config?.root_folder, (value) => {
  rootFolder.value = value ?? ''
}, { immediate: true })

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

function onDrop(event: DragEvent) {
  event.preventDefault()
  upload([...(event.dataTransfer?.files ?? [])])
}
</script>

<template>
  <aside class="course-sidebar" aria-label="课程与资料">
    <header class="brand-block">
      <span class="brand-mark" aria-hidden="true">LC</span>
      <div><strong>Local Course</strong><span>课程学习助手</span></div>
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
      <div class="service-status" aria-label="服务状态">
        <span>AI：{{ course.config?.ai_configured ? '已配置' : '未配置' }}</span>
        <span>Web：{{ course.config?.web_search_configured ? '已配置' : '未配置' }}</span>
        <span>MinerU：{{ course.config?.mineru_configured ? '已配置' : '未配置' }}</span>
      </div>
      <label for="root-folder">资料根目录</label>
      <input id="root-folder" v-model="rootFolder" />
      <button type="button" :disabled="course.savingRoot" @click="run(() => course.saveRoot(rootFolder))">设置</button>
      <button type="button" :disabled="!course.activeCourse || course.indexing" @click="run(course.indexActiveCourse)">{{ course.indexStatus ?? '构建知识库' }}</button>
      <input
        ref="coursePicker"
        type="file"
        multiple
        hidden
        @change="upload(filesFrom($event.target))"
      />
      <button type="button" :disabled="!course.activeCourse" @click="coursePicker?.click()">添加课程资料</button>
      <div class="course-drop-zone" tabindex="0" @dragover.prevent @drop="onDrop">拖入文件，加入当前课程</div>
      <p v-if="error" role="alert">{{ error }}</p>
    </footer>
  </aside>
</template>

<style scoped>
.course-sidebar { min-width: 0; }
.brand-block span, [aria-label="服务状态"] span { display: block; }
button { min-height: 44px; }
</style>
