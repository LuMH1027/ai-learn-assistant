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
  StudyPlanItem,
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
const newPlanTitle = ref('')
const editingPlanItemId = ref<number | null>(null)
const planDraftTitle = ref('')
const planDraftKind = ref<StudyPlanItem['kind']>('read')
const planDraftMinutes = ref(25)
const planActionId = ref<number | null>(null)
const masteryActionId = ref<string | null>(null)

const planItems = computed(() => course.studyPlan?.items ?? [])
const nextPlanItem = computed(() =>
  course.studyPlan?.items.find((item) => item.id === course.studyPlan?.stats.next_item_id) ?? null,
)
const dashboardReviewItems = computed(() => course.dashboard?.review_queue.slice(0, 2) ?? [])
const latestDashboardActivity = computed(() => course.dashboard?.recent_activity[0] ?? null)
const healthItems = computed(() => {
  const preferred = ['ai', 'rag_index', 'vector', 'material_root', 'data_dir', 'telemetry', 'backup']
  const items = course.configStatus?.capabilities ?? []
  return preferred
    .map((key) => items.find((item) => item.key === key))
    .filter((item): item is ConfigCapabilityStatus => item !== undefined)
})

watch(() => course.config?.root_folder, (value) => {
  rootFolder.value = value ?? ''
}, { immediate: true })

watch(() => [course.activeCourseId, course.contextVersion] as const, ([id]) => {
  if (id !== null) void run(() => Promise.all([course.loadDashboard(), course.loadMastery()]))
}, { immediate: true })

watch(() => [course.activeCourseId, course.contextVersion] as const, () => {
  cancelPlanEdit()
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

function addPlanItem() {
  const title = newPlanTitle.value.trim()
  if (!title) return
  void run(async () => {
    await course.addStudyPlanItem(title)
    newPlanTitle.value = ''
  })
}

function beginPlanEdit(item: StudyPlanItem) {
  editingPlanItemId.value = item.id
  planDraftTitle.value = item.title
  planDraftKind.value = item.kind
  planDraftMinutes.value = item.estimated_minutes
}

function cancelPlanEdit() {
  editingPlanItemId.value = null
  planDraftTitle.value = ''
  planDraftKind.value = 'read'
  planDraftMinutes.value = 25
}

function savePlanEdit(item: StudyPlanItem) {
  if (planActionId.value !== null) return
  planActionId.value = item.id
  void run(async () => {
    await course.updateStudyPlanItem(item, {
      title: planDraftTitle.value,
      kind: planDraftKind.value,
      estimated_minutes: planDraftMinutes.value,
    })
    cancelPlanEdit()
  }).finally(() => {
    planActionId.value = null
  })
}

function cyclePlanItem(item: StudyPlanItem) {
  if (planActionId.value !== null) return
  planActionId.value = item.id
  void run(() => course.cycleStudyPlanItem(item)).finally(() => {
    planActionId.value = null
  })
}

function deletePlanItem(item: StudyPlanItem) {
  if (planActionId.value !== null) return
  if (!window.confirm(`删除学习项「${item.title}」？`)) return
  planActionId.value = item.id
  void run(async () => {
    await course.deleteStudyPlanItem(item)
    if (editingPlanItemId.value === item.id) cancelPlanEdit()
  }).finally(() => {
    planActionId.value = null
  })
}

function planKindLabel(kind: StudyPlanItem['kind']) {
  return kind === 'practice' ? '练' : kind === 'review' ? '复' : '读'
}

function planKindText(kind: StudyPlanItem['kind']) {
  return kind === 'practice' ? '练习' : kind === 'review' ? '复习' : '阅读'
}

function planStatusLabel(status: StudyPlanItem['status']) {
  return status === 'done' ? '完成' : status === 'doing' ? '进行中' : '待学'
}

function activityLabel(type: string) {
  if (type.startsWith('message:')) return '对话'
  if (type === 'note') return '笔记'
  if (type.startsWith('plan:')) return '计划'
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

    <section class="sidebar-section plan-section" aria-labelledby="study-plan-title">
      <div class="section-heading">
        <h2 id="study-plan-title">学习计划</h2>
        <button class="icon-button" type="button" aria-label="刷新学习计划" title="刷新学习计划" :disabled="!course.activeCourse || course.planLoading" @click="run(course.loadStudyPlan)">↻</button>
      </div>
      <div v-if="course.activeCourse && course.studyPlan" class="plan-panel">
        <div class="plan-progress" aria-label="学习进度">
          <strong>{{ course.studyPlan.stats.progress_percent }}%</strong>
          <progress :value="course.studyPlan.stats.progress_percent" max="100" />
          <span>{{ course.studyPlan.stats.completed }}/{{ course.studyPlan.stats.total }} 项 · {{ course.studyPlan.stats.remaining_minutes }} 分钟</span>
        </div>
        <p v-if="nextPlanItem" class="plan-next">{{ nextPlanItem.title }}</p>
        <div class="plan-list" aria-label="完整学习计划">
          <article
            v-for="item in planItems"
            :key="item.id"
            class="plan-item"
            :data-status="item.status"
            :title="item.source_file_name || item.title"
          >
            <button
              type="button"
              class="plan-status-button"
              :disabled="planActionId !== null"
              :aria-label="`切换学习项状态：${item.title}`"
              @click="cyclePlanItem(item)"
            >
              <span class="plan-kind" aria-hidden="true">{{ planKindLabel(item.kind) }}</span>
              <span class="plan-status">{{ planStatusLabel(item.status) }}</span>
            </button>
            <form
              v-if="editingPlanItemId === item.id"
              class="plan-edit-form"
              @submit.prevent="savePlanEdit(item)"
            >
              <input v-model="planDraftTitle" :aria-label="`编辑学习项标题：${item.title}`" />
              <select v-model="planDraftKind" :aria-label="`编辑学习项类型：${item.title}`">
                <option value="read">阅读</option>
                <option value="review">复习</option>
                <option value="practice">练习</option>
              </select>
              <input
                v-model.number="planDraftMinutes"
                type="number"
                min="5"
                max="240"
                step="5"
                :aria-label="`编辑预计分钟：${item.title}`"
              />
              <button type="submit" :disabled="planActionId !== null">保存</button>
              <button type="button" :disabled="planActionId !== null" @click="cancelPlanEdit">取消</button>
            </form>
            <template v-else>
              <span class="plan-title">{{ item.title }}</span>
              <span class="plan-meta">{{ planKindText(item.kind) }} · {{ item.estimated_minutes }} 分钟</span>
              <span class="plan-actions">
                <button type="button" :aria-label="`编辑学习项：${item.title}`" @click="beginPlanEdit(item)">编辑</button>
                <button
                  type="button"
                  :disabled="planActionId !== null"
                  :aria-label="`删除学习项：${item.title}`"
                  @click="deletePlanItem(item)"
                >
                  删除
                </button>
              </span>
            </template>
          </article>
        </div>
        <form class="plan-form" @submit.prevent="addPlanItem">
          <input v-model="newPlanTitle" aria-label="新增学习项" placeholder="新增学习项" />
          <button type="submit" aria-label="添加学习项">＋</button>
        </form>
      </div>
      <p v-else-if="course.activeCourse">正在准备学习计划</p>
      <p v-else>选择课程后显示计划</p>
    </section>

    <section class="sidebar-section dashboard-section" aria-labelledby="course-dashboard-title">
      <div class="section-heading">
        <h2 id="course-dashboard-title">课程概览</h2>
        <button class="icon-button" type="button" aria-label="刷新课程概览" title="刷新课程概览" :disabled="!course.activeCourse || course.dashboardLoading" @click="run(course.loadDashboard)">↻</button>
      </div>
      <div v-if="course.activeCourse && course.dashboard" class="dashboard-panel">
        <div class="dashboard-metrics" aria-label="课程概览指标">
          <span><strong>{{ course.dashboard.learning_progress.progress_percent }}%</strong>进度</span>
          <span><strong>{{ course.dashboard.materials.indexed_files }}/{{ course.dashboard.materials.file_count }}</strong>资料</span>
          <span><strong>{{ course.dashboard.materials.indexed_chunks }}</strong>片段</span>
          <span><strong>{{ course.dashboard.mastery?.average_score ?? 0 }}</strong>掌握</span>
        </div>
        <p v-if="course.dashboard.learning_progress.next_item_title" class="dashboard-line">
          下一步：{{ course.dashboard.learning_progress.next_item_title }}
        </p>
        <p v-if="dashboardReviewItems.length > 0" class="dashboard-line">
          待复习：{{ dashboardReviewItems.map((item) => item.title).join('、') }}
        </p>
        <MasteryPanel
          :mastery="course.dashboard.mastery ?? null"
          :state="course.mastery"
          :busy="masteryActionId !== null"
          @add-point="addMasteryPoint"
          @record="recordMasteryAnswer"
          @resolve-mistake="resolveMasteryMistake"
        />
        <p v-if="latestDashboardActivity" class="dashboard-line">
          最近：{{ activityLabel(latestDashboardActivity.type) }} · {{ latestDashboardActivity.title }}
        </p>
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
.dashboard-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.375rem;
}
.dashboard-metrics span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.dashboard-metrics strong {
  display: block;
}
.dashboard-line {
  overflow-wrap: anywhere;
}
.plan-list {
  display: grid;
  max-height: 320px;
  overflow-y: auto;
  gap: 6px;
  padding-right: 2px;
}
.plan-item {
  display: grid;
  grid-template-columns: minmax(68px, auto) minmax(0, 1fr) auto;
  gap: 6px;
  align-items: center;
  width: 100%;
  min-width: 0;
  border: 1px solid transparent;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.42);
  padding: 5px 7px;
}
.plan-item:hover { background: rgba(255, 255, 255, 0.82); }
.plan-item[data-status="doing"] { box-shadow: inset 3px 0 var(--accent); }
.plan-item[data-status="done"] { color: var(--muted); }
.plan-item[data-status="done"] .plan-title { text-decoration: line-through; }
.plan-status-button {
  display: grid;
  grid-template-columns: auto auto;
  align-items: center;
  gap: 5px;
  min-height: 32px;
  padding: 3px 6px;
  white-space: nowrap;
}
.plan-title {
  min-width: 0;
  overflow: hidden;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.plan-meta,
.plan-status {
  color: var(--muted);
  font-size: 11px;
  white-space: nowrap;
}
.plan-actions {
  display: flex;
  gap: 4px;
}
.plan-actions button,
.plan-edit-form button {
  min-height: 32px;
  padding: 4px 7px;
}
.plan-edit-form {
  display: grid;
  grid-column: 2 / -1;
  grid-template-columns: minmax(0, 1fr) 70px 64px auto auto;
  gap: 5px;
}
.plan-edit-form input,
.plan-edit-form select {
  min-width: 0;
  height: 32px;
  padding: 5px 7px;
}
@media (max-width: 760px) {
  .plan-item {
    grid-template-columns: 1fr;
  }
  .plan-status-button,
  .plan-actions,
  .plan-edit-form {
    width: 100%;
  }
  .plan-edit-form {
    grid-column: 1;
    grid-template-columns: 1fr 1fr;
  }
  .plan-edit-form input:first-child {
    grid-column: 1 / -1;
  }
}
</style>
