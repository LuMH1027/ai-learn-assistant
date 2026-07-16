import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  ConfigResponse,
  Course,
  CoursesResponse,
  IndexResult,
  SaveConfigResponse,
  UploadResult,
} from '../types/api'

const api = vi.hoisted(() => ({
  getJson: vi.fn(),
  postFiles: vi.fn(),
  postJson: vi.fn(),
}))

vi.mock('../services/api', () => api)

import { useCourseStore } from './course'

function course(id: string, name = id): Course {
  return { id, name, path: `/courses/${id}`, children: [], file_count: 0 }
}

describe('course store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loads config and courses and resolves the active course', async () => {
    const config: ConfigResponse = {
      root_folder: '/courses',
      ai_provider: 'openai_compatible',
      ai_configured: true,
      mineru_auto: true,
      mineru_configured: false,
    }
    api.getJson
      .mockResolvedValueOnce(config)
      .mockResolvedValueOnce({ courses: [course('a'), course('b')] } satisfies CoursesResponse)
    const store = useCourseStore()

    await store.loadConfig()
    await store.loadCourses()
    store.selectCourse('b')

    expect(store.config).toEqual(config)
    expect(store.activeCourse).toEqual(course('b'))
    expect(store.loading).toBe(false)
  })

  it('increments context only when the selected course actually changes', () => {
    const store = useCourseStore()
    store.courses = [course('a'), course('b')]

    store.selectCourse('a')
    expect(store.contextVersion).toBe(1)

    store.selectCourse('a')
    expect(store.contextVersion).toBe(1)

    store.selectCourse('b')
    expect(store.contextVersion).toBe(2)
  })

  it('saving a root clears the course context and reloads the course list', async () => {
    api.postJson.mockResolvedValue({
      ok: true,
      config: { root_folder: '/new-root' },
    } satisfies SaveConfigResponse)
    api.getJson.mockResolvedValue({ courses: [course('new')] } satisfies CoursesResponse)
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')
    const versionBeforeSave = store.contextVersion

    await store.saveRoot('/new-root')

    expect(store.activeCourseId).toBeNull()
    expect(store.contextVersion).toBe(versionBeforeSave + 1)
    expect(store.config?.root_folder).toBe('/new-root')
    expect(store.courses).toEqual([course('new')])
  })

  it('applies uploaded course files to the course tree', async () => {
    const updated = { ...course('a'), file_count: 1 }
    api.postFiles.mockResolvedValue({
      ok: true,
      saved: [{ name: 'lesson.md', path: '/courses/a/lesson.md' }],
      courses: [updated],
    } satisfies UploadResult)
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')

    const result = await store.uploadCourseFiles([
      new File(['lesson'], 'lesson.md', { type: 'text/markdown' }),
    ])

    expect(result?.saved[0]?.name).toBe('lesson.md')
    expect(store.activeCourse?.file_count).toBe(1)
  })

  it('ignores duplicate indexing while the first write is busy', async () => {
    let resolveIndex!: (result: IndexResult) => void
    api.postJson.mockReturnValue(new Promise<IndexResult>((resolve) => {
      resolveIndex = resolve
    }))
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')

    const first = store.indexActiveCourse()
    const duplicate = store.indexActiveCourse()

    expect(store.indexing).toBe(true)
    expect(duplicate).toBeUndefined()
    resolveIndex({ ok: true, indexed_files: 2, total_chunks: 8 })
    await first

    expect(store.indexing).toBe(false)
    expect(api.postJson).toHaveBeenCalledOnce()
  })
})
