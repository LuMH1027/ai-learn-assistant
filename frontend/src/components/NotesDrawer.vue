<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import { useChatStore } from '../stores/chat'
import type { Note } from '../types/api'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const chat = useChatStore()
const title = ref('')
const content = ref('')
const titleInput = ref<HTMLInputElement | null>(null)
const editingId = ref<number | null>(null)
const editingTitle = ref('')
const editingContent = ref('')

watch(() => props.open, async (open) => {
  if (open) {
    await nextTick()
    titleInput.value?.focus()
  } else {
    cancelEdit()
  }
})

function close() {
  emit('close')
  void nextTick(() => document.getElementById('notes-toggle')?.focus())
}

async function save() {
  const result = chat.saveNote(title.value, content.value)
  if (!result) return
  try {
    await result
    title.value = ''
    content.value = ''
  } catch {
    // The store exposes the failure next to this form.
  }
}

function startEdit(note: Note) {
  editingId.value = note.id
  editingTitle.value = note.title
  editingContent.value = note.content
}

function cancelEdit() {
  editingId.value = null
  editingTitle.value = ''
  editingContent.value = ''
}

async function saveEdit(noteId: number) {
  const result = chat.updateNote(noteId, editingTitle.value, editingContent.value)
  if (!result) return
  try {
    await result
    cancelEdit()
  } catch {
    // The store exposes the failure next to this form.
  }
}

async function remove(note: Note) {
  const result = chat.deleteNote(note.id)
  if (!result) return
  try {
    await result
    if (editingId.value === note.id) cancelEdit()
  } catch {
    // The store exposes the failure next to this form.
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
  }
}
</script>

<template>
  <aside
    class="notes-drawer"
    :class="{ open }"
    :aria-hidden="!open"
    aria-labelledby="notes-title"
    :inert="open ? undefined : true"
    @keydown="onKeydown"
  >
    <header>
      <h2 id="notes-title">课程笔记</h2>
      <button type="button" aria-label="关闭课程笔记" @click="close">×</button>
    </header>
    <label for="note-title">笔记标题</label>
    <input id="note-title" ref="titleInput" v-model="title" aria-label="笔记标题" />
    <label for="note-content">笔记内容</label>
    <textarea id="note-content" v-model="content" aria-label="笔记内容" />
    <button type="button" :disabled="chat.busy.note || !content.trim()" @click="save">
      {{ chat.busy.note ? '保存中…' : '保存笔记' }}
    </button>
    <p v-if="chat.error" role="alert">{{ chat.error }}</p>
    <section aria-label="已保存笔记">
      <article v-for="note in chat.notes" :key="note.id">
        <template v-if="editingId === note.id">
          <label :for="`note-title-${note.id}`">编辑标题</label>
          <input :id="`note-title-${note.id}`" v-model="editingTitle" aria-label="编辑笔记标题" />
          <label :for="`note-content-${note.id}`">编辑内容</label>
          <textarea :id="`note-content-${note.id}`" v-model="editingContent" aria-label="编辑笔记内容" />
          <div class="note-actions">
            <button
              type="button"
              :disabled="chat.busy.note || !editingContent.trim()"
              @click="saveEdit(note.id)"
            >
              {{ chat.busy.note ? '保存中…' : '保存修改' }}
            </button>
            <button type="button" :disabled="chat.busy.note" @click="cancelEdit">取消</button>
          </div>
        </template>
        <template v-else>
          <h3>{{ note.title }}</h3>
          <p>{{ note.content }}</p>
          <div class="note-actions">
            <button type="button" :disabled="chat.busy.note" @click="startEdit(note)">编辑</button>
            <button type="button" :disabled="chat.busy.note" @click="remove(note)">删除</button>
          </div>
        </template>
      </article>
    </section>
  </aside>
</template>

<style scoped>
.notes-drawer[aria-hidden="true"] { display: none; }
button, input, textarea { min-height: 44px; }
.note-actions { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
