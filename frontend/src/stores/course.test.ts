import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  ConfigResponse,
  ConfigStatusResponse,
  Course,
  CourseDashboard,
  CoursesResponse,
  IndexJob,
  IndexResult,
  MasteryState,
  MasteryUpdateRequest,
  ResolveMasteryMistakeResponse,
  SaveMasteryResponse,
  SaveConfigResponse,
  SaveStudyPlanResponse,
  StudyPlan,
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

function configStatus(rootFolder = '/courses', overall: ConfigStatusResponse['overall'] = 'ok'): ConfigStatusResponse {
  return {
    data_dir: '/project/data',
    root_folder: rootFolder,
    overall,
    capabilities: [
      {
        key: 'ai',
        label: 'AI 生成',
        status: 'ok',
        enabled: true,
        detail: 'AI 已配置',
        missing: [],
      },
      {
        key: 'rag_index',
        label: 'RAG 索引',
        status: 'ok',
        enabled: true,
        detail: '索引可用',
        missing: [],
        index_files: 1,
        total_chunks: 12,
      },
    ],
  }
}

function mockRootRefresh(rootFolder: string, nextCourses: Course[]) {
  api.getJson.mockImplementation((path: string) => {
    if (path === '/api/config') return Promise.resolve(config(rootFolder))
    if (path === '/api/config/status') return Promise.resolve(configStatus(rootFolder))
    return Promise.resolve({ courses: nextCourses } satisfies CoursesResponse)
  })
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

function indexJob(status: IndexJob['status'], result: IndexResult | null = null): IndexJob {
  return {
    id: 'job-1',
    course_id: 'a',
    status,
    result,
    error: '',
    started_at: status === 'queued' ? null : '2026-07-22T10:00:00',
    updated_at: '2026-07-22T10:00:00',
    finished_at: ['succeeded', 'failed'].includes(status) ? '2026-07-22T10:00:01' : null,
    progress: status === 'succeeded' ? 100 : 0,
    current_file: null,
    processed_files: status === 'succeeded' ? 1 : 0,
    total_files: status === 'queued' ? 0 : 1,
    error_files: [],
  }
}

function studyPlan(progress = 0): StudyPlan {
  return {
    items: [
      {
        id: 1,
        title: '阅读第一章',
        kind: 'read',
        status: progress >= 100 ? 'done' : 'todo',
        estimated_minutes: 30,
        source_file_id: 'f1',
        source_file_name: '第一章.md',
        created_at: '2026-07-21 10:00:00',
        updated_at: '2026-07-21 10:00:00',
        completed_at: progress >= 100 ? '2026-07-21 10:10:00' : '',
      },
    ],
    stats: {
      total: 1,
      completed: progress >= 100 ? 1 : 0,
      doing: 0,
      remaining_minutes: progress >= 100 ? 0 : 30,
      progress_percent: progress,
      next_item_id: progress >= 100 ? null : 1,
    },
  }
}

function dashboard(progress = 25): CourseDashboard {
  return {
    course: { id: 'a', name: 'a', path: '/courses/a' },
    learning_progress: {
      total: 4,
      done: 1,
      doing: 1,
      todo: 2,
      progress_percent: progress,
      remaining_minutes: 90,
      completed_minutes: 30,
      next_item_id: 2,
      next_item_title: '订正页表练习',
    },
    recent_activity: [{
      type: 'note',
      title: 'TLB 易错点',
      created_at: '2026-07-21 09:00:00',
    }],
    materials: {
      file_count: 3,
      generated_file_count: 2,
      total_bytes: 1024,
      by_extension: { '.pdf': 1, '.md': 2 },
      indexed_files: 2,
      indexed_chunks: 12,
      schema_version: 2,
      tokenizer_version: 'zh_ngrams_v2',
    },
    review_queue: [{
      id: 2,
      title: '订正页表练习',
      kind: 'practice',
      status: 'doing',
      estimated_minutes: 40,
      source_file_name: '复习题.txt',
    }],
    mastery: {
      knowledge_point_count: 2,
      tracked_count: 2,
      average_score: 58,
      weak_count: 1,
      building_count: 0,
      familiar_count: 1,
      mastered_count: 0,
      due_review_count: 1,
      open_mistake_count: 1,
      weakest_points: [{
        id: 'kp-page-table',
        type: 'weak_point',
        title: '页表地址转换',
        score: 35,
        level: 'weak',
        attempts: 2,
        wrong_count: 2,
        next_review_at: '2026-07-22 10:00:00',
      }],
      due_reviews: [{
        id: 'kp-page-table',
        type: 'mastery_review',
        title: '页表地址转换',
        score: 35,
        level: 'weak',
        attempts: 2,
        wrong_count: 2,
        next_review_at: '2026-07-22 10:00:00',
      }],
    },
    generated_artifacts: {
      total: 2,
      summaries: 1,
      quizzes: 1,
      other: 0,
      latest: {
        type: 'generated_artifact',
        title: '课程摘要.md',
        created_at: '2026-07-21 10:00:00',
      },
    },
  }
}

function masteryState(score = 35): MasteryState {
  return {
    schema_version: 1,
    knowledge_points: [{
      id: 'kp-page-table',
      title: '页表地址转换',
      aliases: [],
      source_refs: [],
      created_at: '2026-07-21 10:00:00',
      updated_at: '2026-07-21 10:00:00',
    }],
    mastery: {
      'kp-page-table': {
        point_id: 'kp-page-table',
        score,
        level: score < 40 ? 'weak' : 'familiar',
        attempts: 1,
        correct_count: score >= 40 ? 1 : 0,
        wrong_count: score < 40 ? 1 : 0,
        streak: score >= 40 ? 1 : 0,
        last_result: score >= 40 ? 'correct' : 'wrong',
        last_answered_at: '2026-07-21 10:00:00',
        next_review_at: '2026-07-22 10:00:00',
        review_interval_days: 1,
        updated_at: '2026-07-21 10:00:00',
      },
    },
    mistakes: [{
      id: 'mistake-1',
      point_id: 'kp-page-table',
      question: '解释页表地址转换。',
      user_answer: '直接访问物理地址。',
      expected_answer: '页号查页表得到页框号，再拼接偏移。',
      source_ref: {},
      status: 'open',
      review_count: 0,
      created_at: '2026-07-21 10:00:00',
      updated_at: '2026-07-21 10:00:00',
      resolved_at: '',
    }],
    created_at: '2026-07-21 10:00:00',
    updated_at: '2026-07-21 10:00:00',
  }
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

  it('loads config health status independently', async () => {
    api.getJson.mockResolvedValue(configStatus('/courses', 'warning'))
    const store = useCourseStore()

    await store.loadConfigStatus()

    expect(api.getJson).toHaveBeenCalledWith('/api/config/status')
    expect(store.configStatus?.overall).toBe('warning')
    expect(store.configStatus?.capabilities[0]?.key).toBe('ai')
    expect(store.configStatusLoading).toBe(false)
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
      if (path === '/api/config/status') return Promise.resolve(configStatus('/new-root'))
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
      if (path === '/api/config/status') return Promise.resolve(configStatus('/new-root'))
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

  it('still refreshes courses when the config refresh fails after saving a root', async () => {
    api.postJson.mockResolvedValue({
      ok: true,
      config: { root_folder: '/new-root' },
    } satisfies SaveConfigResponse)
    api.getJson.mockImplementation((path: string) => {
      if (path === '/api/config') return Promise.reject(new Error('config refresh failed'))
      if (path === '/api/config/status') return Promise.resolve(configStatus('/new-root'))
      return Promise.resolve({ courses: [course('new')] } satisfies CoursesResponse)
    })
    const store = useCourseStore()

    await expect(store.saveRoot('/new-root')).resolves.toMatchObject({ ok: true })

    expect(store.rootVersion).toBe(1)
    expect(store.config).toEqual({ root_folder: '/new-root' })
    expect(store.courses).toEqual([course('new')])
    expect(store.savingRoot).toBe(false)
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
    api.getJson.mockImplementation((path: string) => {
      if (path === '/api/config') return Promise.resolve(config('/new-root'))
      if (path === '/api/config/status') return Promise.resolve(configStatus('/new-root'))
      return newRootLoad.promise
    })
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
      if (path === '/api/config/status') return Promise.resolve(configStatus('/new-root'))
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
    let resolveIndex!: (result: IndexJob) => void
    api.postJson.mockReturnValue(new Promise<IndexJob>((resolve) => {
      resolveIndex = resolve
    }))
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')

    const first = store.indexActiveCourse()
    const duplicate = store.indexActiveCourse()

    expect(store.indexing).toBe(true)
    expect(duplicate).toBeUndefined()
    expect(store.indexStatus).toBe('正在启动索引任务…')
    resolveIndex(indexJob('succeeded', { ok: true, indexed_files: 2, total_chunks: 8 }))
    await first

    expect(store.indexing).toBe(false)
    expect(store.indexStatus).toBeNull()
    expect(api.postJson).toHaveBeenCalledOnce()
  })

  it('does not let a stale index job clear a newer course state', async () => {
    const started = deferred<IndexJob>()
    api.postJson.mockReturnValue(started.promise)
    const store = useCourseStore()
    store.courses = [course('a'), course('b')]
    store.selectCourse('a')

    const pending = store.indexActiveCourse()
    store.selectCourse('b')
    started.resolve(indexJob('succeeded', { ok: true, indexed_files: 1, total_chunks: 1 }))
    await pending

    expect(store.activeCourseId).toBe('b')
    expect(store.indexing).toBe(false)
    expect(store.indexStatus).toBeNull()
  })

  it('loads the active course study plan', async () => {
    api.getJson.mockResolvedValue({ plan: studyPlan(0) })
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')

    await store.loadStudyPlan()

    expect(api.getJson).toHaveBeenCalledWith('/api/courses/a/plan')
    expect(store.studyPlan?.stats.progress_percent).toBe(0)
    expect(store.planLoading).toBe(false)
  })

  it('loads the active course dashboard', async () => {
    api.getJson.mockResolvedValue({ dashboard: dashboard(33) })
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')

    await store.loadDashboard()

    expect(api.getJson).toHaveBeenCalledWith('/api/courses/a/dashboard')
    expect(store.dashboard?.learning_progress.progress_percent).toBe(33)
    expect(store.dashboard?.materials.indexed_chunks).toBe(12)
    expect(store.dashboardLoading).toBe(false)
  })

  it('loads and updates the active course mastery state', async () => {
    api.getJson.mockResolvedValue({ mastery: masteryState(35) })
    api.postJson.mockResolvedValue({
      ok: true,
      mastery: masteryState(65),
    } satisfies SaveMasteryResponse)
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')

    await store.loadMastery()
    const request: MasteryUpdateRequest = {
      answer_result: {
        point_id: 'kp-page-table',
        correct: true,
      },
    }

    await store.updateMastery(request)

    expect(api.getJson).toHaveBeenCalledWith('/api/courses/a/mastery')
    expect(api.postJson).toHaveBeenCalledWith('/api/courses/a/mastery', request)
    expect(store.mastery?.mastery['kp-page-table']?.score).toBe(65)
    expect(store.masteryLoading).toBe(false)
  })

  it('resolves an open mastery mistake for the active course', async () => {
    const resolvedState = masteryState(65)
    resolvedState.mistakes[0].status = 'resolved'
    resolvedState.mistakes[0].review_count = 1
    resolvedState.mistakes[0].resolved_at = '2026-07-22 10:00:00'
    api.postJson.mockResolvedValue({
      ok: true,
      mastery: resolvedState,
    } satisfies ResolveMasteryMistakeResponse)
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')

    await store.resolveMasteryMistake('mistake-1')

    expect(api.postJson).toHaveBeenCalledWith('/api/courses/a/mastery/mistakes/mistake-1/resolve')
    expect(store.mastery?.mistakes[0].status).toBe('resolved')
    expect(store.mastery?.mistakes[0].review_count).toBe(1)
  })

  it('drops a stale study plan response after switching courses', async () => {
    const oldPlan = deferred<{ plan: StudyPlan }>()
    api.getJson.mockReturnValue(oldPlan.promise)
    const store = useCourseStore()
    store.courses = [course('a'), course('b')]
    store.selectCourse('a')

    const pending = store.loadStudyPlan()
    store.selectCourse('b')
    oldPlan.resolve({ plan: studyPlan(0) })
    await pending

    expect(store.activeCourseId).toBe('b')
    expect(store.studyPlan).toBeNull()
    expect(store.planLoading).toBe(false)
  })

  it('drops a stale dashboard response after switching courses', async () => {
    const oldDashboard = deferred<{ dashboard: CourseDashboard }>()
    api.getJson.mockReturnValue(oldDashboard.promise)
    const store = useCourseStore()
    store.courses = [course('a'), course('b')]
    store.selectCourse('a')

    const pending = store.loadDashboard()
    store.selectCourse('b')
    oldDashboard.resolve({ dashboard: dashboard(50) })
    await pending

    expect(store.activeCourseId).toBe('b')
    expect(store.dashboard).toBeNull()
    expect(store.dashboardLoading).toBe(false)
  })

  it('drops a stale mastery response after switching courses', async () => {
    const oldMastery = deferred<{ mastery: MasteryState }>()
    api.getJson.mockReturnValue(oldMastery.promise)
    const store = useCourseStore()
    store.courses = [course('a'), course('b')]
    store.selectCourse('a')

    const pending = store.loadMastery()
    store.selectCourse('b')
    oldMastery.resolve({ mastery: masteryState(35) })
    await pending

    expect(store.activeCourseId).toBe('b')
    expect(store.mastery).toBeNull()
    expect(store.masteryLoading).toBe(false)
  })

  it('updates study plan status and applies returned stats', async () => {
    api.postJson.mockResolvedValue({
      ok: true,
      plan: studyPlan(100),
    } satisfies SaveStudyPlanResponse)
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')
    store.studyPlan = studyPlan(0)

    await store.cycleStudyPlanItem(store.studyPlan.items[0])

    expect(api.postJson).toHaveBeenCalledWith('/api/courses/a/plan/1', { status: 'doing' })
    expect(store.studyPlan?.stats.progress_percent).toBe(100)
  })

  it('updates study plan content fields', async () => {
    const updated = studyPlan(0)
    updated.items[0] = {
      ...updated.items[0],
      title: '订正页表练习',
      kind: 'practice',
      estimated_minutes: 45,
    }
    api.postJson.mockResolvedValue({
      ok: true,
      plan: updated,
    } satisfies SaveStudyPlanResponse)
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')
    store.studyPlan = studyPlan(0)

    await store.updateStudyPlanItem(store.studyPlan.items[0], {
      title: '订正页表练习',
      kind: 'practice',
      estimated_minutes: 45,
    })

    expect(api.postJson).toHaveBeenCalledWith('/api/courses/a/plan/1', {
      title: '订正页表练习',
      kind: 'practice',
      estimated_minutes: 45,
    })
    expect(store.studyPlan?.items[0]?.title).toBe('订正页表练习')
  })

  it('deletes a study plan item and applies returned plan', async () => {
    const updated = studyPlan(100)
    updated.items = []
    updated.stats.total = 0
    api.postJson.mockResolvedValue({
      ok: true,
      plan: updated,
    } satisfies SaveStudyPlanResponse)
    const store = useCourseStore()
    store.courses = [course('a')]
    store.selectCourse('a')
    store.studyPlan = studyPlan(0)

    await store.deleteStudyPlanItem(store.studyPlan.items[0])

    expect(api.postJson).toHaveBeenCalledWith('/api/courses/a/plan/1/delete')
    expect(store.studyPlan?.items).toEqual([])
  })
})
