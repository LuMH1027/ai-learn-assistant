<script setup lang="ts">
import { computed } from 'vue'

import { usePreviewStore, type PreviewTab } from '../stores/preview'

const preview = usePreviewStore()
const extension = computed(() => preview.activeFile?.extension.toLowerCase() ?? '')
const isPdf = computed(() => extension.value === '.pdf')
const isImage = computed(() => ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'].includes(extension.value))

const tabs: Array<{ id: PreviewTab, label: string }> = [
  { id: 'file', label: '当前文件' },
  { id: 'sources', label: '引用来源' },
  { id: 'info', label: '信息' },
]
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

    <section v-show="preview.tab === 'file'" id="preview-panel-file" role="tabpanel" aria-labelledby="preview-tab-file">
      <p v-if="preview.error" role="alert">{{ preview.error }}</p>
      <p v-else-if="!preview.activeFile">选择左侧资料，或点击回答中的引用。</p>
      <div v-else-if="isPdf">
        <iframe :src="preview.url ?? undefined" :title="preview.activeFile.name" />
        <a :href="preview.url ?? undefined" target="_blank" rel="noopener">在新窗口打开 PDF</a>
      </div>
      <img v-else-if="isImage" :src="preview.url ?? undefined" :alt="preview.activeFile.name" />
      <pre v-else>{{ preview.content }}</pre>
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
button { min-height: 44px; }
</style>
