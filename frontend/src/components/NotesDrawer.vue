<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import { useChatStore } from '../stores/chat'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const chat = useChatStore()
const title = ref('')
const content = ref('')
const titleInput = ref<HTMLInputElement | null>(null)

watch(() => props.open, async (open) => {
  if (open) {
    await nextTick()
    titleInput.value?.focus()
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
        <h3>{{ note.title }}</h3>
        <p>{{ note.content }}</p>
      </article>
    </section>
  </aside>
</template>

<style scoped>
.notes-drawer[aria-hidden="true"] { display: none; }
button, input, textarea { min-height: 44px; }
</style>
