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

function config(rootFolder: string): ConfigResponse {
  return {
    root_folder: rootFolder,
    ai_provider: 'openai_compatible',
    ai_configured: true,
    mineru_auto: true,
    mineru_configured: false,
  }
}

function mockRootRefresh(rootFolder: string, nextCourses: Course[]) {
  api.getJson.mockImplementation((path: string) => path === '/api/config'
    ? Promise.resolve(config(rootFolder))
    : Promise.resolve({ courses: nextCourses } satisfies CoursesResponse))
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, reject, resolve }
}

describe('course store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
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

  it('does not let an old config GET overwrite a successful root save', async () => {
    const oldConfig = deferred<ConfigResponse>()
    let configRequests = 0
    api.getJson.mockImplementation((path: string) => {
      if (path === '/api/config') {
        configRequests += 1
        return configRequests === 1
          ? oldConfig.promise
          : Promise.resolve(config('/new-root'))
      }
      return Promise.resolve({ courses: [course('new')] } satisfies CoursesResponse)
    })
    api.postJson.mockResolvedValue({
      ok: true,
      config: { root_folder: '/new-root' },
    } satisfies SaveConfigResponse)
    const store = useCourseStore()

    const pendingConfig = store.loadConfig()
    await store.saveRoot('/new-root')
    oldConfig.resolve({
      root_folder: '/old-root',
      ai_provider: 'old-provider',
      ai_configured: false,
      mineru_auto: false,
      mineru_configured: false,
    })
    await pendingConfig

    expect(store.config?.root_folder).toBe('/new-root')
    expect(store.configEpoch).toBe(1)
  })

  it('refreshes the complete authoritative config after saving a root', async () => {
    const oldConfig = deferred<ConfigResponse>()
    const authoritativeConfig: ConfigResponse = {
      root_folder: '/new-root',
      ai_provider: 'custom-provider',
      ai_configured: true,
      mineru_auto: false,
      mineru_configured: true,
    }
    let configRequests = 0
    api.getJson.mockImplementation((path: string) => {
      if (path === '/api/config') {
        configRequests += 1
        return configRequests === 1
          ? oldConfig.promise
          : Promise.resolve(authoritativeConfig)
      }
      return Promise.resolve({ courses: [course('new')] } satisfies CoursesResponse)
    })
    api.postJson.mockResolvedValue({
      ok: true,
      config: { root_folder: '/new-root' },
    } satisfies SaveConfigResponse)
    const store = useCourseStore()

    const initialLoad = store.loadConfig()
    await store.saveRoot('/new-root')
    oldConfig.resolve({
      root_folder: '/old-root',
      ai_provider: 'stale-provider',
      ai_configured: false,
      mineru_auto: true,
      mineru_configured: false,
    })
    await initialLoad

    expect(configRequests).toBe(2)
    expect(store.config).toEqual(authoritativeConfig)
    expect(store.configEpoch).toBe(1)
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

  it('applies a course load across selection changes within the same root', async () => {
    const load = deferred<CoursesResponse>()
    api.getJson.mockReturnValue(load.promise)
    const store = useCourseStore()
    store.applyCourses([course('a'), course('b')])
    store.selectCourse('a')

    const pendingLoad = store.loadCourses()
    store.selectCourse('b')
    load.resolve({
      courses: [{ ...course('a'), file_count: 1 }, course('b')],
    })
    await pendingLoad

    expect(store.activeCourseId).toBe('b')
    expect(store.courses[0]?.file_count).toBe(1)
  })

  it('makes an older GET stale whenever the tree is applied directly', async () => {
    const oldLoad = deferred<CoursesResponse>()
    api.getJson.mockReturnValue(oldLoad.promise)
    const store = useCourseStore()
    expect(store.treeEpoch).toBe(0)

    const pendingLoad = store.loadCourses()
    store.applyCourses([course('artifact-tree')])
    expect(store.treeEpoch).toBe(1)
    oldLoad.resolve({ courses: [course('old-get')] })
    await pendingLoad

    expect(store.courses).toEqual([course('artifact-tree')])
  })

  it('lets only the latest course GET write the tree', async () => {
    const older = deferred<CoursesResponse>()
    const newer = deferred<CoursesResponse>()
    api.getJson.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise)
    const store = useCourseStore()

    const first = store.loadCourses()
    const second = store.loadCourses()
    newer.resolve({ courses: [course('newer')] })
    await second
    older.resolve({ courses: [course('older')] })
    await first

    expect(store.courses).toEqual([course('newer')])
  })

  it('keeps loading true until every overlapping request finishes', async () => {
    const firstLoad = deferred<CoursesResponse>()
    const secondLoad = deferred<CoursesResponse>()
    api.getJson
      .mockReturnValueOnce(firstLoad.promise)
      .mockReturnValueOnce(secondLoad.promise)
    const store = useCourseStore()

    const first = store.loadCourses()
    const second = store.loadCourses()
    secondLoad.resolve({ courses: [course('newer')] })
    await second

    expect(store.loading).toBe(true)
    firstLoad.resolve({ courses: [course('older')] })
    await first
    expect(store.loading).toBe(false)
  })

  it('saving a root clears the course context and reloads the course list', async () => {
    api.postJson.mockResolvedValue({
      ok: true,
      config: { root_folder: '/new-root' },
    } satisfies SaveConfigResponse)
    mockRootRefresh('/new-root', [course('new')])
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')
    const versionBeforeSave = store.contextVersion

    await store.saveRoot('/new-root')

    expect(store.activeCourseId).toBeNull()
    expect(store.contextVersion).toBe(versionBeforeSave + 1)
    expect(store.config?.root_folder).toBe('/new-root')
    expect(store.courses).toEqual([course('new')])
    expect(store.rootVersion).toBe(1)
  })

  it('clears the old tree after a successful save while the new root loads', async () => {
    const newRootLoad = deferred<CoursesResponse>()
    api.postJson.mockResolvedValue({
      ok: true,
      config: { root_folder: '/new-root' },
    } satisfies SaveConfigResponse)
    api.getJson.mockImplementation((path: string) => path === '/api/config'
      ? Promise.resolve(config('/new-root'))
      : newRootLoad.promise)
    const store = useCourseStore()
    store.applyCourses([course('old')])
    store.selectCourse('old')

    const save = store.saveRoot('/new-root')
    await vi.waitFor(() => expect(api.getJson).toHaveBeenCalledWith('/api/courses'))

    expect(store.rootVersion).toBe(1)
    expect(store.activeCourseId).toBeNull()
    expect(store.courses).toEqual([])
    newRootLoad.resolve({ courses: [course('new')] })
    await save
    expect(store.courses).toEqual([course('new')])
  })

  it('does not mutate root or tree request state when saving a root fails', async () => {
    api.postJson.mockRejectedValue(new Error('save failed'))
    const store = useCourseStore()
    store.applyCourses([course('a')])
    store.selectCourse('a')
    const treeEpoch = store.treeEpoch
    const loadRequestId = store.loadRequestId

    await expect(store.saveRoot('/broken')).rejects.toThrow('save failed')

    expect(store.rootVersion).toBe(0)
    expect(store.treeEpoch).toBe(treeEpoch)
    expect(store.loadRequestId).toBe(loadRequestId)
    expect(store.courses).toEqual([course('a')])
    expect(store.activeCourseId).toBe('a')
    expect(store.configEpoch).toBe(0)
    expect(store.savingRoot).toBe(false)
  })

  it('ignores a second root save while the first is pending', async () => {
    const rootSave = deferred<SaveConfigResponse>()
    api.postJson.mockReturnValue(rootSave.promise)
    mockRootRefresh('/first-root', [course('new-root-course')])
    const store = useCourseStore()

    const first = store.saveRoot('/first-root')
    const duplicate = store.saveRoot('/ignored-root')

    expect(store.savingRoot).toBe(true)
    expect(duplicate).toBeUndefined()
    expect(api.postJson).toHaveBeenCalledOnce()
    rootSave.resolve({ ok: true, config: { root_folder: '/first-root' } })
    await first

    expect(store.rootVersion).toBe(1)
    expect(store.config?.root_folder).toBe('/first-root')
    expect(store.courses).toEqual([course('new-root-course')])
    expect(store.contextVersion).toBe(1)
    expect(store.savingRoot).toBe(false)
  })

  it('ignores an old course load after saving a new root', async () => {
    const oldCourses = deferred<CoursesResponse>()
    let courseRequests = 0
    api.getJson.mockImplementation((path: string) => {
      if (path === '/api/config') return Promise.resolve(config('/new-root'))
      courseRequests += 1
      return courseRequests === 1
        ? oldCourses.promise
        : Promise.resolve({ courses: [course('new')] } satisfies CoursesResponse)
    })
    api.postJson.mockResolvedValue({
      ok: true,
      config: { root_folder: '/new-root' },
    } satisfies SaveConfigResponse)
    const store = useCourseStore()

    const oldLoad = store.loadCourses()
    await store.saveRoot('/new-root')
    oldCourses.resolve({ courses: [course('old')] })
    const oldResult = await oldLoad

    expect(oldResult).toEqual([course('old')])
    expect(store.courses).toEqual([course('new')])
    expect(store.activeCourseId).toBeNull()
  })

  it('applies uploaded course files to the course tree', async () => {
    const authoritative = { ...course('a'), file_count: 2 }
    api.postFiles.mockResolvedValue({
      ok: true,
      saved: [{ name: 'lesson.md', path: '/courses/a/lesson.md' }],
      courses: [{ ...course('a'), file_count: 99 }],
    } satisfies UploadResult)
    api.getJson.mockResolvedValue({ courses: [authoritative] } satisfies CoursesResponse)
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')

    const result = await store.uploadCourseFiles([
      new File(['lesson'], 'lesson.md', { type: 'text/markdown' }),
    ])

    expect(result?.saved[0]?.name).toBe('lesson.md')
    expect(store.activeCourse?.file_count).toBe(2)
  })

  it('applies an upload response after switching courses within the same root', async () => {
    const upload = deferred<UploadResult>()
    api.postFiles.mockReturnValue(upload.promise)
    api.getJson.mockResolvedValue({
      courses: [{ ...course('a'), file_count: 2 }, course('b')],
    } satisfies CoursesResponse)
    const store = useCourseStore()
    store.courses = [course('a'), course('b')]
    store.selectCourse('a')

    const pendingUpload = store.uploadCourseFiles([
      new File(['lesson'], 'lesson.md', { type: 'text/markdown' }),
    ])
    store.selectCourse('b')
    upload.resolve({
      ok: true,
      saved: [{ name: 'lesson.md', path: '/courses/a/lesson.md' }],
      courses: [{ ...course('a'), file_count: 1 }, course('b')],
    })
    const result = await pendingUpload

    expect(result?.saved[0]?.name).toBe('lesson.md')
    expect(store.activeCourseId).toBe('b')
    expect(store.courses[0]?.file_count).toBe(2)
    expect(store.contextVersion).toBe(2)
  })

  it('uses the latest authoritative GET after upload mutations finish out of order', async () => {
    const firstUpload = deferred<UploadResult>()
    const secondUpload = deferred<UploadResult>()
    const firstTreeLoad = deferred<CoursesResponse>()
    const secondTreeLoad = deferred<CoursesResponse>()
    api.postFiles
      .mockReturnValueOnce(firstUpload.promise)
      .mockReturnValueOnce(secondUpload.promise)
    api.getJson
      .mockReturnValueOnce(firstTreeLoad.promise)
      .mockReturnValueOnce(secondTreeLoad.promise)
    const store = useCourseStore()
    store.applyCourses([course('a')])
    store.selectCourse('a')

    const first = store.uploadCourseFiles([new File(['1'], 'one.md')])
    const second = store.uploadCourseFiles([new File(['2'], 'two.md')])
    secondUpload.resolve({ ok: true, saved: [], courses: [course('post-snapshot-2')] })
    await vi.waitFor(() => expect(api.getJson).toHaveBeenCalledTimes(1))
    firstUpload.resolve({ ok: true, saved: [], courses: [course('post-snapshot-1')] })
    await vi.waitFor(() => expect(api.getJson).toHaveBeenCalledTimes(2))

    secondTreeLoad.resolve({ courses: [{ ...course('a'), file_count: 2 }] })
    await first
    firstTreeLoad.resolve({ courses: [{ ...course('a'), file_count: 1 }] })
    await second

    expect(store.activeCourse?.file_count).toBe(2)
  })

  it('discards an upload tree from an older root', async () => {
    const upload = deferred<UploadResult>()
    api.postFiles.mockReturnValue(upload.promise)
    api.postJson.mockResolvedValue({
      ok: true,
      config: { root_folder: '/new-root' },
    } satisfies SaveConfigResponse)
    mockRootRefresh('/new-root', [course('new')])
    const store = useCourseStore()
    store.applyCourses([course('old')])
    store.selectCourse('old')

    const pendingUpload = store.uploadCourseFiles([new File(['x'], 'x.md')])
    await store.saveRoot('/new-root')
    upload.resolve({
      ok: true,
      saved: [{ name: 'x.md', path: '/old/x.md' }],
      courses: [course('stale-upload')],
    })
    await pendingUpload

    expect(store.rootVersion).toBe(1)
    expect(store.courses).toEqual([course('new')])
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
