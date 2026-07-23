<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import { buildTextSearchParts, renderMarkdown } from '../services/markdown'
import { usePreviewStore, type PreviewTab } from '../stores/preview'

const preview = usePreviewStore()
const filePanel = ref<HTMLElement | null>(null)
const extension = computed(() => preview.activeFile?.extension.toLowerCase() ?? '')
const isPdf = computed(() => extension.value === '.pdf')
const isImage = computed(() => ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'].includes(extension.value))
const isMarkdown = computed(() => ['.md', '.markdown'].includes(extension.value))
const markdownHtml = computed(() => renderMarkdown(
  preview.content ?? '',
  preview.searchTerm
    ? { query: preview.searchTerm, activeIndex: preview.activeSearchIndex }
    : undefined,
))
const textSearchParts = computed(() => buildTextSearchParts(preview.content ?? '', preview.searchTerm))
const activeSearchKey = computed(() => [
  preview.activeFile?.id ?? '',
  preview.searchTerm,
  preview.activeSearchIndex,
  preview.searchMatchCount,
].join('\u0000'))

const tabs: Array<{ id: PreviewTab, label: string }> = [
  { id: 'file', label: '当前文件' },
  { id: 'sources', label: '引用来源' },
  { id: 'info', label: '信息' },
]

function setSearchQuery(event: Event) {
  preview.setSearchQuery((event.target as HTMLInputElement).value)
}

watch(activeSearchKey, async () => {
  if (preview.searchMatchCount === 0) return
  await nextTick()
  const activeMatch = filePanel.value?.querySelector('.preview-search-hit.active')
  if (activeMatch instanceof HTMLElement && typeof activeMatch.scrollIntoView === 'function') {
    activeMatch.scrollIntoView({ block: 'center', inline: 'nearest' })
  }
}, { flush: 'post' })
</script>

<template>
  <aside class="file-preview" aria-label="资料预览">
    <header>
      <div>
        <h2>{{ preview.activeFile?.name ?? '资料预览' }}</h2>
        <p>{{ preview.activeFile?.extension?.slice(1).toUpperCase() || '选择文件后在此阅读' }}</p>
      </div>
      <button type="button" aria-label="关闭资料预览" @click="preview.close">×</button>
    </header>
    <div role="tablist" aria-label="预览内容">
      <button
        v-for="item in tabs"
        :id="`preview-tab-${item.id}`"
        :key="item.id"
        type="button"
        role="tab"
        :aria-selected="preview.tab === item.id"
        :aria-controls="`preview-panel-${item.id}`"
        @click="preview.setTab(item.id)"
      >
        {{ item.label }}
      </button>
    </div>

    <section
      v-show="preview.tab === 'file'"
      id="preview-panel-file"
      ref="filePanel"
      role="tabpanel"
      aria-labelledby="preview-tab-file"
    >
      <p v-if="preview.error" role="alert">{{ preview.error }}</p>
      <p v-else-if="!preview.activeFile">选择左侧资料，或点击回答中的引用。</p>
      <template v-else>
        <form
          v-if="preview.supportsSearch"
          class="preview-search"
          role="search"
          aria-label="当前文件搜索"
          @submit.prevent="preview.nextSearchMatch"
        >
          <input
            type="search"
            :value="preview.searchQuery"
            placeholder="搜索当前文件"
            aria-label="搜索当前文件"
            @input="setSearchQuery"
          >
          <output aria-live="polite">{{ preview.currentSearchMatch }}/{{ preview.searchMatchCount }}</output>
          <button type="button" :disabled="preview.searchMatchCount === 0" @click="preview.previousSearchMatch">上一个</button>
          <button type="submit" :disabled="preview.searchMatchCount === 0">下一个</button>
        </form>
        <div v-if="isPdf">
          <iframe :src="preview.url ?? undefined" :title="preview.activeFile.name" />
          <a :href="preview.url ?? undefined" target="_blank" rel="noopener">在新窗口打开 PDF</a>
        </div>
        <img v-else-if="isImage" :src="preview.url ?? undefined" :alt="preview.activeFile.name" />
        <div v-else-if="isMarkdown" class="markdown-preview" v-html="markdownHtml" />
        <pre v-else class="text-preview"><template
          v-for="(part, index) in textSearchParts"
          :key="`${index}-${part.matchIndex ?? 'text'}`"
        ><mark
          v-if="part.matchIndex !== null"
          class="preview-search-hit"
          :class="{ active: part.matchIndex === preview.activeSearchIndex }"
          :data-search-index="part.matchIndex"
        >{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></pre>
      </template>
    </section>

    <section v-show="preview.tab === 'sources'" id="preview-panel-sources" role="tabpanel" aria-labelledby="preview-tab-sources">
      <template v-if="preview.citation">
        <blockquote>{{ preview.citation.quote || '该引用未提供原文片段。' }}</blockquote>
        <button type="button" @click="preview.setTab('file')">
          {{ preview.citation.file_name }}<template v-if="preview.citation.page"> · 第 {{ preview.citation.page }} 页</template>
        </button>
      </template>
      <p v-else>回答中的引用会显示在这里。</p>
    </section>

    <section v-show="preview.tab === 'info'" id="preview-panel-info" role="tabpanel" aria-labelledby="preview-tab-info">
      <dl v-if="preview.activeFile">
        <dt>文件名</dt><dd>{{ preview.activeFile.name }}</dd>
        <dt>类型</dt><dd>{{ preview.activeFile.extension || '未知' }}</dd>
        <dt>大小</dt><dd>{{ preview.activeFile.size }} B</dd>
      </dl>
      <p v-else>选择文件后显示文件信息。</p>
    </section>
  </aside>
</template>

<style scoped>
.file-preview { min-width: 0; }
iframe { width: 100%; min-height: 70dvh; border: 0; }
img { max-width: 100%; height: auto; }
button { min-height: 34px; }
.preview-search button { min-height: 34px; }
.markdown-preview { color: var(--text); font-size: 13px; line-height: 1.55; overflow-wrap: anywhere; }
.markdown-preview :deep(h1),
.markdown-preview :deep(h2),
.markdown-preview :deep(h3),
.markdown-preview :deep(h4) { margin: 1em 0 .38em; line-height: 1.25; }
.markdown-preview :deep(h1:first-child),
.markdown-preview :deep(h2:first-child),
.markdown-preview :deep(h3:first-child) { margin-top: 0; }
.markdown-preview :deep(h1) { border-bottom: 1px solid var(--line); padding-bottom: .28em; font-size: 1.5em; }
.markdown-preview :deep(h2) { border-bottom: 1px solid var(--line); padding-bottom: .24em; font-size: 1.24em; }
.markdown-preview :deep(h3) { font-size: 1.15em; }
.markdown-preview :deep(p),
.markdown-preview :deep(ul),
.markdown-preview :deep(ol),
.markdown-preview :deep(blockquote),
.markdown-preview :deep(pre),
.markdown-preview :deep(table) { margin: 0 0 .65em; }
.markdown-preview :deep(ul),
.markdown-preview :deep(ol) { padding-left: 1.35em; }
.markdown-preview :deep(li + li) { margin-top: .14em; }
.markdown-preview :deep(a) { color: var(--accent); text-underline-offset: 2px; }
.markdown-preview :deep(blockquote) { border-left: 3px solid var(--accent); background: var(--surface); padding: .38em .62em; color: var(--muted); }
.markdown-preview :deep(blockquote > :last-child) { margin-bottom: 0; }
.markdown-preview :deep(code) { border-radius: 4px; background: var(--surface); padding: .12em .32em; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .9em; }
.markdown-preview :deep(pre) { overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); padding: .58em .68em; white-space: pre; }
.markdown-preview :deep(pre code) { background: transparent; padding: 0; }
.markdown-preview :deep(table) { width: 100%; border-collapse: collapse; }
.markdown-preview :deep(th),
.markdown-preview :deep(td) { border: 1px solid var(--line); padding: .3em .45em; text-align: left; }
.markdown-preview :deep(th) { background: var(--surface); }
.markdown-preview :deep(hr) { margin: 1.5em 0; border: 0; border-top: 1px solid var(--line); }
.markdown-preview :deep(img) { max-width: 100%; }
</style>
