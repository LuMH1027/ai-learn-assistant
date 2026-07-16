import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export const CONTENT_SHARE = 98.8
export const LAYOUT_STORAGE_KEY = 'local-course-agent-layout-v1'

const DEFAULT_SIDEBAR_SHARE = 22
const DEFAULT_PREVIEW_SHARE = 31
const MIN_SIDEBAR_SHARE = 5.5
const MAX_SIDEBAR_SHARE = 32
const MIN_CENTER_SHARE = 34
const MIN_PREVIEW_SHARE = 20
const MAX_PREVIEW_SHARE = 44

interface PersistedLayout {
  sidebarShare: number
  previewShare: number
  previewOpen: boolean
}

export function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum)
}

function parsePersistedLayout(value: unknown): PersistedLayout | null {
  if (!value || typeof value !== 'object') return null

  const layout = value as Partial<PersistedLayout> & {
    sidebar?: unknown
    preview?: unknown
  }
  const sidebarShare = layout.sidebarShare ?? layout.sidebar
  const previewShare = layout.previewShare ?? layout.preview
  if (
    typeof sidebarShare !== 'number' ||
    !Number.isFinite(sidebarShare) ||
    typeof previewShare !== 'number' ||
    !Number.isFinite(previewShare) ||
    typeof layout.previewOpen !== 'boolean'
  ) {
    return null
  }

  return { sidebarShare, previewShare, previewOpen: layout.previewOpen }
}

export const useLayoutStore = defineStore('layout', () => {
  const sidebarShare = ref(DEFAULT_SIDEBAR_SHARE)
  const previewShare = ref(DEFAULT_PREVIEW_SHARE)
  const previewOpen = ref(true)

  const centerShare = computed(() =>
    previewOpen.value
      ? CONTENT_SHARE - sidebarShare.value - previewShare.value
      : CONTENT_SHARE - sidebarShare.value,
  )

  function persist() {
    const layout: PersistedLayout = {
      sidebarShare: sidebarShare.value,
      previewShare: previewShare.value,
      previewOpen: previewOpen.value,
    }
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layout))
  }

  function moveLeft(delta: number, minimum = MIN_SIDEBAR_SHARE) {
    const maximum = Math.min(
      MAX_SIDEBAR_SHARE,
      CONTENT_SHARE - previewShare.value - MIN_CENTER_SHARE,
    )
    sidebarShare.value = clamp(sidebarShare.value + delta, minimum, maximum)
    persist()
  }

  function moveRight(delta: number) {
    const maximum = Math.min(
      MAX_PREVIEW_SHARE,
      CONTENT_SHARE - sidebarShare.value - MIN_CENTER_SHARE,
    )
    previewShare.value = clamp(
      previewShare.value - delta,
      MIN_PREVIEW_SHARE,
      maximum,
    )
    persist()
  }

  function setPreviewOpen(open: boolean) {
    previewOpen.value = open
    persist()
  }

  function resetLeft() {
    sidebarShare.value = DEFAULT_SIDEBAR_SHARE
    persist()
  }

  function resetRight() {
    previewShare.value = DEFAULT_PREVIEW_SHARE
    persist()
  }

  function resetToDefaults(isMobile: boolean) {
    sidebarShare.value = DEFAULT_SIDEBAR_SHARE
    previewShare.value = DEFAULT_PREVIEW_SHARE
    previewOpen.value = !isMobile
  }

  function hydrate(isMobile = false) {
    const savedLayout = window.localStorage.getItem(LAYOUT_STORAGE_KEY)
    if (savedLayout === null) {
      resetToDefaults(isMobile)
      return
    }

    try {
      const parsed: unknown = JSON.parse(savedLayout)
      const layout = parsePersistedLayout(parsed)
      if (layout === null) {
        resetToDefaults(isMobile)
        return
      }

      previewShare.value = clamp(
        layout.previewShare,
        MIN_PREVIEW_SHARE,
        MAX_PREVIEW_SHARE,
      )
      sidebarShare.value = clamp(
        layout.sidebarShare,
        MIN_SIDEBAR_SHARE,
        Math.min(
          MAX_SIDEBAR_SHARE,
          CONTENT_SHARE - previewShare.value - MIN_CENTER_SHARE,
        ),
      )
      previewShare.value = clamp(
        previewShare.value,
        MIN_PREVIEW_SHARE,
        CONTENT_SHARE - sidebarShare.value - MIN_CENTER_SHARE,
      )
      previewOpen.value = layout.previewOpen
    } catch {
      resetToDefaults(isMobile)
    }
  }

  return {
    sidebarShare,
    previewShare,
    previewOpen,
    centerShare,
    moveLeft,
    moveLeftBoundary: moveLeft,
    moveRight,
    moveRightBoundary: moveRight,
    setPreviewOpen,
    resetLeft,
    resetLeftBoundary: resetLeft,
    resetRight,
    resetRightBoundary: resetRight,
    persist,
    hydrate,
  }
})
