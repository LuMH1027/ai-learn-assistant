<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { useLayoutStore } from '../stores/layout'

const props = defineProps<{
  isMobile: boolean
  sidebarOpen: boolean
}>()

const layout = useLayoutStore()
const shell = ref<HTMLElement | null>(null)
const dragging = ref<'left' | 'right' | null>(null)
let lastX = 0

function measureCompactMinimum() {
  if (!shell.value || props.isMobile) return
  const width = shell.value.getBoundingClientRect().width || shell.value.clientWidth
  if (width <= 0) return
  const candidates = shell.value.querySelectorAll<HTMLElement>(
    '.brand-mark, .icon-button, .course-icon, .file-icon',
  )
  const widest = [...candidates].reduce(
    (value, element) => Math.max(value, element.getBoundingClientRect().width),
    34,
  )
  layout.setMinimumSidebarShare(((widest + 18) / width) * 100)
}

onMounted(() => {
  measureCompactMinimum()
  window.addEventListener('resize', measureCompactMinimum)
})

onBeforeUnmount(() => window.removeEventListener('resize', measureCompactMinimum))

const shellStyle = computed(() => ({
  '--sidebar-share': `${layout.sidebarShare}%`,
  '--preview-share': `${layout.previewShare}%`,
  '--center-share': `${layout.centerShare}%`,
}))

function move(side: 'left' | 'right', delta: number) {
  if (props.isMobile) return
  if (side === 'left') layout.moveLeftBoundary(delta)
  else if (layout.previewOpen) layout.moveRightBoundary(delta)
}

function onPointerDown(side: 'left' | 'right', event: PointerEvent) {
  if (props.isMobile) return
  dragging.value = side
  lastX = event.clientX
  event.currentTarget instanceof HTMLElement
    && event.currentTarget.setPointerCapture?.(event.pointerId)
}

function onPointerMove(side: 'left' | 'right', event: PointerEvent) {
  if (dragging.value !== side || !shell.value) return
  const width = shell.value.getBoundingClientRect().width || shell.value.clientWidth
  if (width <= 0) return
  const delta = ((event.clientX - lastX) / width) * 100
  lastX = event.clientX
  move(side, delta)
}

function finishPointer(event: PointerEvent) {
  if (event.currentTarget instanceof HTMLElement) {
    const target = event.currentTarget
    if (target.hasPointerCapture?.(event.pointerId)) {
      target.releasePointerCapture?.(event.pointerId)
    }
  }
  dragging.value = null
}

function onKeydown(side: 'left' | 'right', event: KeyboardEvent) {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  move(side, event.key === 'ArrowLeft' ? -1 : 1)
}
</script>

<template>
  <div
    ref="shell"
    class="workspace-shell"
    :class="{ 'is-mobile': isMobile, 'sidebar-open': sidebarOpen, 'preview-open': layout.previewOpen, 'sidebar-compact': !isMobile && layout.sidebarShare < 14 }"
    :style="shellStyle"
  >
    <slot name="sidebar" />
    <div
      class="column-resizer left-resizer"
      role="separator"
      aria-label="调整课程栏和对话栏宽度"
      aria-orientation="vertical"
      :aria-valuemin="layout.minimumSidebarShare.toFixed(1)"
      aria-valuemax="32"
      :aria-valuenow="Math.round(layout.sidebarShare)"
      tabindex="0"
      @pointerdown="onPointerDown('left', $event)"
      @pointermove="onPointerMove('left', $event)"
      @pointerup="finishPointer"
      @pointercancel="finishPointer"
      @keydown="onKeydown('left', $event)"
      @dblclick="layout.resetLeftBoundary()"
    />
    <slot name="main" />
    <div
      class="column-resizer right-resizer"
      role="separator"
      aria-label="调整对话栏和预览栏宽度"
      aria-orientation="vertical"
      aria-valuemin="20"
      aria-valuemax="44"
      :aria-valuenow="Math.round(layout.previewShare)"
      :aria-hidden="layout.previewOpen ? undefined : true"
      :tabindex="layout.previewOpen ? 0 : -1"
      @pointerdown="onPointerDown('right', $event)"
      @pointermove="onPointerMove('right', $event)"
      @pointerup="finishPointer"
      @pointercancel="finishPointer"
      @keydown="onKeydown('right', $event)"
      @dblclick="layout.resetRightBoundary()"
    />
    <slot name="preview" />
  </div>
</template>

<style scoped>
.workspace-shell {
  display: grid;
  grid-template-columns: var(--sidebar-share) 0.6% minmax(0, var(--center-share)) 0.6% var(--preview-share);
  min-height: 100dvh;
  transition: grid-template-columns var(--preview-transition);
}
.workspace-shell:not(.preview-open) {
  grid-template-columns: var(--sidebar-share) 0.6% minmax(0, var(--center-share)) 0% 0%;
}
.column-resizer { cursor: col-resize; min-width: 6px; touch-action: none; }
.is-mobile { display: block; }
</style>
