import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  CONTENT_SHARE,
  LAYOUT_STORAGE_KEY,
  useLayoutStore,
} from './layout'

// Node 26 exposes an unconfigured localStorage that Vitest otherwise keeps over jsdom's.
const jsdom = (globalThis as typeof globalThis & {
  jsdom: { window: Window }
}).jsdom
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: jsdom.window.localStorage,
})

describe('layout store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('starts with the desktop layout defaults', () => {
    const store = useLayoutStore()

    expect(CONTENT_SHARE).toBe(98.8)
    expect(store.sidebarShare).toBe(22)
    expect(store.previewShare).toBe(31)
    expect(store.centerShare).toBeCloseTo(45.8)
    expect(store.previewOpen).toBe(true)
  })

  it('exposes the boundary action names used by layout components', () => {
    const store = useLayoutStore()

    store.moveLeftBoundary(-2)
    store.moveRightBoundary(2)
    expect(store.sidebarShare).toBe(20)
    expect(store.previewShare).toBe(29)

    store.resetLeftBoundary()
    store.resetRightBoundary()
    expect(store.sidebarShare).toBe(22)
    expect(store.previewShare).toBe(31)
  })

  it('moves only the left divider and preserves the minimum center share', () => {
    const store = useLayoutStore()

    store.moveLeft(20)

    expect(store.sidebarShare).toBe(32)
    expect(store.centerShare).toBeCloseTo(35.8)
    expect(store.previewShare).toBe(31)

    store.moveLeft(-100, 5.5)

    expect(store.sidebarShare).toBe(5.5)
    expect(store.centerShare).toBeCloseTo(62.3)
    expect(store.previewShare).toBe(31)
  })

  it('moves only the right divider within preview and center bounds', () => {
    const store = useLayoutStore()
    const sidebar = store.sidebarShare

    store.moveRight(100)

    expect(store.sidebarShare).toBe(sidebar)
    expect(store.previewShare).toBe(20)
    expect(store.centerShare).toBeCloseTo(56.8)

    store.moveRight(-100)

    expect(store.sidebarShare).toBe(sidebar)
    expect(store.previewShare).toBeCloseTo(42.8)
    expect(store.centerShare).toBe(34)
  })

  it('gives the closed preview share to the center and restores it on reopen', () => {
    const store = useLayoutStore()
    store.moveRight(4)
    const previewShare = store.previewShare

    store.setPreviewOpen(false)

    expect(store.centerShare).toBeCloseTo(CONTENT_SHARE - store.sidebarShare)
    expect(store.previewShare).toBe(previewShare)

    store.setPreviewOpen(true)

    expect(store.previewShare).toBe(previewShare)
    expect(store.centerShare).toBeCloseTo(
      CONTENT_SHARE - store.sidebarShare - previewShare,
    )
  })

  it('resets each divider independently', () => {
    const store = useLayoutStore()
    store.moveLeft(-5)
    store.moveRight(4)
    const movedPreview = store.previewShare

    store.resetLeft()

    expect(store.sidebarShare).toBe(22)
    expect(store.previewShare).toBe(movedPreview)

    store.moveLeft(-3)
    const movedSidebar = store.sidebarShare
    store.resetRight()

    expect(store.previewShare).toBe(31)
    expect(store.sidebarShare).toBe(movedSidebar)
  })

  it('keeps enough center space when resetting the preview after extreme moves', () => {
    const store = useLayoutStore()
    store.moveRight(100)
    store.moveLeft(100)
    const movedSidebar = store.sidebarShare

    store.resetRight()

    expect(store.previewShare).toBe(31)
    expect(store.sidebarShare).toBe(movedSidebar)
    expect(store.centerShare).toBeGreaterThanOrEqual(34)
  })

  it('keeps enough center space when resetting the sidebar after extreme moves', () => {
    const store = useLayoutStore()
    store.moveLeft(-100)
    store.moveRight(-100)
    const movedPreview = store.previewShare

    store.resetLeft()

    expect(store.sidebarShare).toBeCloseTo(20.8)
    expect(store.previewShare).toBe(movedPreview)
    expect(store.centerShare).toBeGreaterThanOrEqual(34)
  })

  it('persists user actions under the versioned layout key and hydrates them', () => {
    const firstStore = useLayoutStore()
    firstStore.moveLeft(-4)
    firstStore.moveRight(3)
    firstStore.setPreviewOpen(false)

    expect(LAYOUT_STORAGE_KEY).toBe('local-course-agent-layout-v1')
    expect(
      JSON.parse(window.localStorage.getItem(LAYOUT_STORAGE_KEY) ?? ''),
    ).toEqual({
      sidebarShare: 18,
      previewShare: 28,
      previewOpen: false,
    })

    setActivePinia(createPinia())
    const restoredStore = useLayoutStore()
    restoredStore.hydrate(false)

    expect(restoredStore.sidebarShare).toBe(18)
    expect(restoredStore.previewShare).toBe(28)
    expect(restoredStore.previewOpen).toBe(false)
  })

  it('hydrates layout settings saved by the existing web application', () => {
    window.localStorage.setItem(
      LAYOUT_STORAGE_KEY,
      JSON.stringify({ sidebar: 17, preview: 27, previewOpen: false }),
    )
    const store = useLayoutStore()

    store.hydrate(false)

    expect(store.sidebarShare).toBe(17)
    expect(store.previewShare).toBe(27)
    expect(store.previewOpen).toBe(false)
  })

  it('defaults to a closed preview on mobile only when nothing was saved', () => {
    const setItem = vi.spyOn(window.Storage.prototype, 'setItem')
    const store = useLayoutStore()

    store.hydrate(true)

    expect(store.sidebarShare).toBe(22)
    expect(store.previewShare).toBe(31)
    expect(store.previewOpen).toBe(false)
    expect(setItem).not.toHaveBeenCalled()

    window.localStorage.setItem(
      LAYOUT_STORAGE_KEY,
      JSON.stringify({
        sidebarShare: 19,
        previewShare: 29,
        previewOpen: true,
      }),
    )
    setActivePinia(createPinia())
    const restoredStore = useLayoutStore()
    restoredStore.hydrate(true)

    expect(restoredStore.sidebarShare).toBe(19)
    expect(restoredStore.previewShare).toBe(29)
    expect(restoredStore.previewOpen).toBe(true)
  })

  it('falls back to defaults when saved JSON is malformed', () => {
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, '{not-json')
    const store = useLayoutStore()

    store.hydrate(false)

    expect(store.sidebarShare).toBe(22)
    expect(store.previewShare).toBe(31)
    expect(store.previewOpen).toBe(true)
  })
})
