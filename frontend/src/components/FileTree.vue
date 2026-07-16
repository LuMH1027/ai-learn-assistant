<script setup lang="ts">
import type { FileLeafNode, FileNode } from '../types/api'

defineOptions({ name: 'FileTree' })

defineProps<{
  nodes: FileNode[]
  activeFileId?: string | null
}>()

const emit = defineEmits<{
  select: [file: FileLeafNode]
}>()
</script>

<template>
  <ul class="file-tree" role="tree">
    <li v-for="node in nodes" :key="node.id" role="treeitem">
      <details v-if="node.type === 'folder'" open>
        <summary :title="node.path">{{ node.name }}</summary>
        <FileTree
          :nodes="node.children"
          :active-file-id="activeFileId"
          @select="emit('select', $event)"
        />
      </details>
      <button
        v-else
        class="file-node"
        type="button"
        :class="{ active: node.id === activeFileId }"
        :aria-current="node.id === activeFileId ? 'true' : undefined"
        :title="node.path"
        @click="emit('select', node)"
      >
        {{ node.name }}
      </button>
    </li>
  </ul>
</template>

<style scoped>
.file-tree { list-style: none; margin: 0; padding-inline-start: 16px; }
.file-node { min-height: 44px; }
</style>
