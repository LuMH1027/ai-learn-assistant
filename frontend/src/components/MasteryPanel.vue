<script setup lang="ts">
import { computed, ref } from 'vue'

import type {
  DashboardMastery,
  MasteryDashboardItem,
  MasteryKnowledgePointInput,
  MasteryState,
  MistakeRecord,
} from '../types/api'

const props = defineProps<{
  mastery: DashboardMastery | null
  state: MasteryState | null
  busy: boolean
}>()

const emit = defineEmits<{
  record: [item: MasteryDashboardItem, correct: boolean]
  addPoint: [point: MasteryKnowledgePointInput]
  resolveMistake: [mistake: MistakeRecord]
}>()

const title = ref('')
const aliases = ref('')

const weakItems = computed(() => props.mastery?.weakest_points.slice(0, 2) ?? [])
const actionItems = computed(() => {
  const byId = new Map<string, MasteryDashboardItem>()
  for (const item of props.mastery?.due_reviews ?? []) byId.set(item.id, item)
  for (const item of props.mastery?.weakest_points ?? []) {
    if (!byId.has(item.id)) byId.set(item.id, item)
  }
  return [...byId.values()].slice(0, 3)
})
const pointsById = computed(() => {
  const points = new Map<string, string>()
  for (const point of props.state?.knowledge_points ?? []) points.set(point.id, point.title)
  return points
})
const openMistakes = computed(() =>
  (props.state?.mistakes ?? []).filter((mistake) => mistake.status === 'open').slice(0, 2),
)

function masteryLevelLabel(level: string) {
  if (level === 'weak') return '薄弱'
  if (level === 'building') return '建立中'
  if (level === 'familiar') return '熟悉'
  if (level === 'mastered') return '已掌握'
  return level
}

function pointTitle(pointId: string) {
  return pointsById.value.get(pointId) ?? pointId
}

function submitPoint() {
  const normalizedTitle = title.value.trim()
  if (!normalizedTitle || props.busy) return
  const aliasList = aliases.value
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean)
  emit('addPoint', { title: normalizedTitle, aliases: aliasList })
  title.value = ''
  aliases.value = ''
}
</script>

<template>
  <div v-if="mastery" class="mastery-panel" aria-label="掌握度">
    <div class="mastery-heading">
      <strong>掌握度</strong>
      <span>{{ mastery.due_review_count }} 待复习 · {{ mastery.open_mistake_count }} 未订正</span>
    </div>

    <details class="mastery-add">
      <summary>新增知识点</summary>
      <form class="mastery-form" aria-label="新增知识点" @submit.prevent="submitPoint">
        <input v-model="title" aria-label="知识点名称" placeholder="知识点名称" :disabled="busy" />
        <input v-model="aliases" aria-label="知识点别名" placeholder="别名，可选" :disabled="busy" />
        <button type="submit" aria-label="添加知识点" :disabled="busy || !title.trim()">＋</button>
      </form>
    </details>

    <p v-if="weakItems.length > 0" class="mastery-line">
      薄弱点：{{ weakItems.map((item) => `${item.title} ${item.score}`).join('、') }}
    </p>
    <div v-if="actionItems.length > 0" class="mastery-list">
      <div
        v-for="item in actionItems"
        :key="item.id"
        class="mastery-item"
        :title="item.title"
      >
        <span class="mastery-copy">
          <strong>{{ item.title }}</strong>
          <span>{{ item.score }} 分 · {{ masteryLevelLabel(item.level) }}</span>
        </span>
        <span class="mastery-actions">
          <button
            type="button"
            class="mastery-action"
            :aria-label="`记录${item.title}回答正确`"
            :disabled="busy"
            @click="emit('record', item, true)"
          >对</button>
          <button
            type="button"
            class="mastery-action danger"
            :aria-label="`记录${item.title}回答错误`"
            :disabled="busy"
            @click="emit('record', item, false)"
          >错</button>
        </span>
      </div>
    </div>
    <p v-else class="mastery-line">暂无待复习知识点</p>

    <div v-if="openMistakes.length > 0" class="mistake-list" aria-label="未订正错题">
      <div
        v-for="mistake in openMistakes"
        :key="mistake.id"
        class="mistake-item"
      >
        <span class="mastery-copy">
          <strong>{{ mistake.question }}</strong>
          <span>{{ pointTitle(mistake.point_id) }}</span>
          <span v-if="mistake.expected_answer">答案：{{ mistake.expected_answer }}</span>
          <span v-if="mistake.user_answer">作答：{{ mistake.user_answer }}</span>
        </span>
        <button
          type="button"
          class="mistake-resolve"
          :aria-label="`标记${mistake.question}已订正`"
          :disabled="busy"
          @click="emit('resolveMistake', mistake)"
        >订正</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mastery-panel {
  display: grid;
  min-width: 0;
  gap: 0.45rem;
  border-top: 1px solid var(--line);
  padding-top: 0.45rem;
}
.mastery-heading {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  color: var(--muted);
  font-size: 0.72rem;
}
.mastery-heading strong {
  color: var(--text);
  font-size: 0.78rem;
}
.mastery-heading span,
.mastery-line {
  min-width: 0;
  overflow-wrap: anywhere;
}
.mastery-line {
  margin: 0;
  color: var(--muted);
  font-size: 0.75rem;
}
.mastery-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.8fr) 2rem;
  gap: 0.25rem;
}
.mastery-add {
  min-width: 0;
}
.mastery-add > summary {
  width: fit-content;
  min-height: 1.75rem;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
  color: var(--text);
  padding: 0.28rem 0.5rem;
  cursor: pointer;
  font-size: 0.72rem;
  font-weight: 650;
  list-style: none;
}
.mastery-add > summary::-webkit-details-marker {
  display: none;
}
.mastery-add[open] > summary {
  margin-bottom: 0.3rem;
}
.mastery-form input {
  min-width: 0;
  height: 2rem;
  padding: 0 0.5rem;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
  color: var(--text);
  font-size: 0.75rem;
}
.mastery-form button {
  min-width: 2rem;
  min-height: 2rem;
  padding: 0;
  line-height: 1;
}
.mastery-list,
.mistake-list {
  display: grid;
  gap: 0.25rem;
}
.mastery-item,
.mistake-item {
  display: grid;
  min-width: 0;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.375rem;
}
.mistake-item {
  align-items: start;
  border-top: 1px solid var(--line);
  padding-top: 0.35rem;
}
.mastery-copy {
  display: grid;
  min-width: 0;
  gap: 0.05rem;
}
.mastery-copy strong {
  overflow: hidden;
  font-size: 0.78rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mastery-copy span {
  overflow: hidden;
  color: var(--muted);
  font-size: 0.7rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mastery-actions {
  display: inline-grid;
  grid-template-columns: repeat(2, 1.75rem);
  gap: 0.2rem;
}
.mastery-action,
.mistake-resolve {
  min-height: 1.75rem;
  padding: 0 0.45rem;
  border-color: var(--line);
  background: var(--surface);
  color: var(--accent);
  font-size: 0.75rem;
  line-height: 1;
}
.mastery-action {
  width: 1.75rem;
  min-width: 1.75rem;
  padding: 0;
}
.mastery-action:hover:not(:disabled),
.mistake-resolve:hover:not(:disabled) {
  background: var(--accent-soft);
}
.mastery-action.danger {
  color: var(--danger);
}
.mastery-action.danger:hover:not(:disabled) {
  background: #fceeee;
}
</style>
