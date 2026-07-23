<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { useCourseStore } from '../stores/course'
import { usePreviewStore } from '../stores/preview'
import type {
  ConfigCapabilityStatus,
  FileLeafNode,
  MasteryDashboardItem,
  MasteryKnowledgePointInput,
  MistakeRecord,
} from '../types/api'
import FileTree from './FileTree.vue'
import MasteryPanel from './MasteryPanel.vue'

defineProps<{ sidebarOpen: boolean }>()

const emit = defineEmits<{
  close: []
}>()

const course = useCourseStore()
const preview = usePreviewStore()
const rootFolder = ref('')
const coursePicker = ref<HTMLInputElement | null>(null)
const error = ref<string | null>(null)
const masteryActionId = ref<string | null>(null)

const latestDashboardActivity = computed(() => course.dashboard?.recent_activity[0] ?? null)
const healthItems = computed(() => {
  const preferred = ['ai', 'rag_index', 'vector', 'material_root', 'data_dir', 'telemetry', 'backup']
  const items = course.configStatus?.capabilities ?? []
  return preferred
    .map((key) => items.find((item) => item.key === key))
    .filter((item): item is ConfigCapabilityStatus => item !== undefined)
})
const setupSteps = computed(() => course.configStatus?.setup_steps ?? [])
const degradationNotices = computed(() => course.configStatus?.degradation_notices ?? [])

watch(() => course.config?.root_folder, (value) => {
  rootFolder.value = value ?? ''
}, { immediate: true })

watch(() => [course.activeCourseId, course.contextVersion] as const, ([id]) => {
  if (id !== null) void run(() => Promise.all([course.loadDashboard(), course.loadMastery()]))
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

function activityLabel(type: string) {
  if (type.startsWith('message:')) return '对话'
  if (type === 'note') return '笔记'
  if (type === 'generated_artifact') return '生成'
  return '活动'
}

function healthStatusLabel(status: ConfigCapabilityStatus['status']) {
  if (status === 'ok') return '正常'
  if (status === 'warning') return '需配置'
  if (status === 'error') return '异常'
  return '未启用'
}

function overallHealthLabel(status: 'ok' | 'warning' | 'error' | undefined) {
  if (status === 'ok') return '正常'
  if (status === 'error') return '异常'
  return '需关注'
}

function setupStepStatusLabel(status: 'done' | 'todo' | 'optional') {
  if (status === 'done') return '完成'
  if (status === 'optional') return '可选'
  return '待处理'
}

function recordMasteryAnswer(item: MasteryDashboardItem, correct: boolean) {
  if (masteryActionId.value !== null) return
  masteryActionId.value = item.id
  void run(async () => {
    await course.updateMastery({
      answer_result: {
        point_id: item.id,
        correct,
      },
    })
    await course.loadDashboard()
  }).finally(() => {
    masteryActionId.value = null
  })
}

function addMasteryPoint(point: MasteryKnowledgePointInput) {
  if (masteryActionId.value !== null) return
  masteryActionId.value = 'add-point'
  void run(async () => {
    await course.updateMastery({ knowledge_point: point })
    await course.loadDashboard()
  }).finally(() => {
    masteryActionId.value = null
  })
}

function resolveMasteryMistake(mistake: MistakeRecord) {
  if (masteryActionId.value !== null) return
  masteryActionId.value = mistake.id
  void run(async () => {
    await course.resolveMasteryMistake(mistake.id)
    await course.loadDashboard()
  }).finally(() => {
    masteryActionId.value = null
  })
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

    <section class="sidebar-section dashboard-section" aria-labelledby="course-dashboard-title">
      <div class="section-heading">
        <h2 id="course-dashboard-title">课程概览</h2>
        <button class="icon-button" type="button" aria-label="刷新课程概览" title="刷新课程概览" :disabled="!course.activeCourse || course.dashboardLoading" @click="run(course.loadDashboard)">↻</button>
      </div>
      <div v-if="course.activeCourse && course.dashboard" class="dashboard-panel">
        <div class="dashboard-metrics" aria-label="课程概览指标">
          <span><strong>{{ course.dashboard.materials.indexed_files }}/{{ course.dashboard.materials.file_count }}</strong>资料</span>
          <span><strong>{{ course.dashboard.materials.indexed_chunks }}</strong>片段</span>
          <span><strong>{{ course.dashboard.mastery?.average_score ?? 0 }}</strong>掌握</span>
        </div>
        <p v-if="latestDashboardActivity" class="dashboard-line">
          最近：{{ activityLabel(latestDashboardActivity.type) }} · {{ latestDashboardActivity.title }}
        </p>
        <details v-if="course.dashboard.mastery" class="mastery-details">
          <summary>
            <span>掌握度</span>
            <strong>{{ course.dashboard.mastery.average_score }}</strong>
            <small>{{ course.dashboard.mastery.due_review_count }} 待复习 · {{ course.dashboard.mastery.open_mistake_count }} 未订正</small>
          </summary>
          <MasteryPanel
            :mastery="course.dashboard.mastery"
            :state="course.mastery"
            :busy="masteryActionId !== null"
            @add-point="addMasteryPoint"
            @record="recordMasteryAnswer"
            @resolve-mistake="resolveMasteryMistake"
          />
        </details>
      </div>
      <p v-else-if="course.activeCourse">正在准备课程概览</p>
      <p v-else>选择课程后显示概览</p>
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
          <span>配置健康：{{ overallHealthLabel(course.configStatus?.overall) }}</span>
          <button class="icon-button" type="button" aria-label="刷新配置健康状态" title="刷新配置健康状态" :disabled="course.configStatusLoading" @click="run(course.loadConfigStatus)">↻</button>
        </div>
        <div v-if="healthItems.length > 0" class="health-grid">
          <span
            v-for="item in healthItems"
            :key="item.key"
            class="health-chip"
            :data-status="item.status"
            :title="item.detail"
          >
            <span aria-hidden="true"></span>{{ item.label }}：{{ healthStatusLabel(item.status) }}
          </span>
        </div>
        <span v-else>{{ course.configStatusLoading ? '正在检查配置…' : '尚未检查配置' }}</span>
        <div v-if="course.configStatus?.setup_required && setupSteps.length > 0" class="setup-guide" aria-label="首次启动清单">
          <strong>首次启动清单</strong>
          <span
            v-for="step in setupSteps"
            :key="step.key"
            class="setup-step"
            :data-status="step.status"
            :title="step.detail"
          >
            {{ setupStepStatusLabel(step.status) }} · {{ step.label }}
          </span>
        </div>
        <div v-if="degradationNotices.length > 0" class="degradation-list" aria-label="降级提示">
          <strong>降级提示</strong>
          <span
            v-for="notice in degradationNotices"
            :key="notice.key"
            :title="notice.detail"
          >
            {{ notice.label }}
          </span>
        </div>
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
.brand-block span { display: block; }
button { min-height: 44px; }
.dashboard-section {
  flex: 0 0 auto;
  border-bottom: 1px solid rgba(185, 191, 188, 0.68);
}
.dashboard-panel {
  display: grid;
  gap: 0.45rem;
  min-width: 0;
}
.dashboard-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.35rem;
}
.dashboard-metrics span {
  min-width: 0;
  border: 1px solid rgba(185, 191, 188, 0.55);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.55);
  padding: 0.4rem 0.45rem;
  color: var(--muted);
  font-size: 0.68rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dashboard-metrics strong {
  display: block;
  color: var(--text);
  font-size: 0.9rem;
  line-height: 1.1;
}
.dashboard-line {
  margin: 0;
  overflow: hidden;
  color: var(--muted);
  font-size: 0.74rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mastery-details {
  min-width: 0;
  border: 1px solid rgba(185, 191, 188, 0.65);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.5);
}
.mastery-details > summary {
  display: grid;
  min-height: 34px;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0 0.45rem;
  padding: 0.35rem 0.5rem;
  color: var(--text);
  cursor: pointer;
  list-style: none;
}
.mastery-details > summary::-webkit-details-marker {
  display: none;
}
.mastery-details > summary::after {
  grid-column: 2;
  grid-row: 1 / span 2;
  color: var(--faint);
  content: "展开";
  font-size: 0.7rem;
  font-weight: 650;
}
.mastery-details[open] > summary::after {
  content: "收起";
}
.mastery-details > summary span,
.mastery-details > summary small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mastery-details > summary strong {
  grid-column: 1;
  grid-row: 1;
  margin-left: 3.2rem;
  justify-self: start;
  color: var(--accent);
  font-size: 0.82rem;
}
.mastery-details > summary small {
  grid-column: 1;
  grid-row: 2;
  color: var(--muted);
  font-size: 0.68rem;
}
.mastery-details :deep(.mastery-panel) {
  margin: 0 0.5rem 0.55rem;
}
.setup-guide,
.degradation-list {
  display: grid;
  gap: 4px;
  min-width: 0;
  border-top: 1px solid rgba(185, 191, 188, 0.55);
  padding-top: 5px;
}
.setup-guide strong,
.degradation-list strong {
  color: var(--text);
  font-size: 10px;
}
.setup-step,
.degradation-list span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.setup-step[data-status="done"] {
  color: var(--accent);
}
.setup-step[data-status="todo"] {
  color: var(--danger);
}
.setup-step[data-status="optional"] {
  color: var(--muted);
}
</style>
