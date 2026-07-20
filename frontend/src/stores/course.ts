import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { getJson, postFiles, postJson } from '../services/api'
import type {
  ConfigResponse,
  Course,
  CoursesResponse,
  IndexJob,
  IndexResult,
  SaveConfigResponse,
  UploadResult,
} from '../types/api'

type CourseConfig = Pick<ConfigResponse, 'root_folder'> &
  Partial<Omit<ConfigResponse, 'root_folder'>>
const INDEX_POLL_MS = 250

function wait(ms: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, ms))
}

export const useCourseStore = defineStore('course', () => {
  const courses = ref<Course[]>([])
  const config = ref<CourseConfig | null>(null)
  const activeCourseId = ref<string | null>(null)
  const contextVersion = ref(0)
  const rootVersion = ref(0)
  const treeEpoch = ref(0)
  const loadRequestId = ref(0)
  const configEpoch = ref(0)
  const configRequestId = ref(0)
  const pendingRequests = ref(0)
  const indexing = ref(false)
  const indexStatus = ref<string | null>(null)
  const indexJobId = ref<string | null>(null)
  const indexRequestId = ref(0)
  const savingRoot = ref(false)

  const activeCourse = computed(() =>
    courses.value.find((course) => course.id === activeCourseId.value) ?? null,
  )
  const loading = computed(() => pendingRequests.value > 0)

  function applyCourses(nextCourses: Course[]) {
    treeEpoch.value += 1
    courses.value = nextCourses
    if (
      activeCourseId.value !== null &&
      !nextCourses.some((course) => course.id === activeCourseId.value)
    ) {
      activeCourseId.value = null
      contextVersion.value += 1
    }
  }

  async function trackRequest<T>(request: () => Promise<T>) {
    pendingRequests.value += 1
    try {
      return await request()
    } finally {
      pendingRequests.value -= 1
    }
  }

  function loadConfig() {
    const requestId = ++configRequestId.value
    const requestedConfigEpoch = configEpoch.value
    return trackRequest(async () => {
      const result = await getJson<ConfigResponse>('/api/config')
      if (
        requestId === configRequestId.value &&
        requestedConfigEpoch === configEpoch.value
      ) {
        config.value = result
      }
      return result
    })
  }

  function loadCourses() {
    const requestId = ++loadRequestId.value
    const requestedRootVersion = rootVersion.value
    const requestedTreeEpoch = treeEpoch.value
    return trackRequest(async () => {
      const result = await getJson<CoursesResponse>('/api/courses')
      if (
        requestId === loadRequestId.value &&
        requestedRootVersion === rootVersion.value &&
        requestedTreeEpoch === treeEpoch.value
      ) {
        applyCourses(result.courses)
      }
      return result.courses
    })
  }

  function selectCourse(course: Course | string | null) {
    const nextId = typeof course === 'string' ? course : course?.id ?? null
    if (nextId === activeCourseId.value) return

    resetIndexState()
    activeCourseId.value = nextId
    contextVersion.value += 1
  }

  function saveRoot(rootFolder: string) {
    if (savingRoot.value) return
    savingRoot.value = true
    return trackRequest(async () => {
      try {
        const result = await postJson<SaveConfigResponse>('/api/config', {
          root_folder: rootFolder,
        })

        rootVersion.value += 1
        configEpoch.value += 1
        resetIndexState()
        config.value = {
          ...(config.value ?? {}),
          root_folder: result.config.root_folder,
        }
        activeCourseId.value = null
        contextVersion.value += 1
        applyCourses([])

        const [, coursesRefresh] = await Promise.allSettled([
          loadConfig(),
          loadCourses(),
        ])
        if (coursesRefresh.status === 'rejected') {
          throw coursesRefresh.reason
        }
        return result
      } finally {
        savingRoot.value = false
      }
    })
  }

  function uploadCourseFiles(files: File[]) {
    const courseId = activeCourseId.value
    const requestedRootVersion = rootVersion.value
    if (courseId === null || files.length === 0) return

    return (async () => {
      const form = new FormData()
      for (const file of files) form.append('files', file, file.name)
      const result = await postFiles<UploadResult>(
        `/api/courses/${encodeURIComponent(courseId)}/files`,
        form,
      )
      if (
        requestedRootVersion === rootVersion.value
      ) {
        await loadCourses()
      }
      return result
    })()
  }

  function indexActiveCourse() {
    const courseId = activeCourseId.value
    if (courseId === null || indexing.value) return

    const requestId = ++indexRequestId.value
    const requestedRootVersion = rootVersion.value
    indexing.value = true
    indexStatus.value = '正在启动索引任务…'
    indexJobId.value = null
    return (async () => {
      try {
        const started = await postJson<IndexJob>(
          `/api/courses/${encodeURIComponent(courseId)}/index/jobs`,
        )
        if (!isCurrentIndexRequest(courseId, requestedRootVersion, requestId)) return undefined
        indexJobId.value = started.id
        return await waitForIndexJob(started, courseId, requestedRootVersion, requestId)
      } finally {
        if (isCurrentIndexRequest(courseId, requestedRootVersion, requestId)) {
          indexing.value = false
          indexStatus.value = null
          indexJobId.value = null
        }
      }
    })()
  }

  function resetIndexState() {
    indexRequestId.value += 1
    indexing.value = false
    indexStatus.value = null
    indexJobId.value = null
  }

  function isCurrentIndexRequest(courseId: string, requestedRootVersion: number, requestId: number) {
    return activeCourseId.value === courseId &&
      rootVersion.value === requestedRootVersion &&
      requestId === indexRequestId.value
  }

  async function waitForIndexJob(
    started: IndexJob,
    courseId: string,
    requestedRootVersion: number,
    requestId: number,
  ): Promise<IndexResult | undefined> {
    let job = started
    while (isCurrentIndexRequest(courseId, requestedRootVersion, requestId)) {
      if (job.status === 'succeeded') {
        indexStatus.value = '索引完成'
        return job.result ?? undefined
      }
      if (job.status === 'failed') {
        throw new Error(job.error || '索引任务失败')
      }
      indexStatus.value = job.status === 'queued' ? '索引排队中…' : '正在构建知识库…'
      await wait(INDEX_POLL_MS)
      if (!isCurrentIndexRequest(courseId, requestedRootVersion, requestId)) return undefined
      job = await getJson<IndexJob>(`/api/index-jobs/${encodeURIComponent(job.id)}`)
    }
    return undefined
  }

  return {
    courses,
    config,
    activeCourseId,
    contextVersion,
    rootVersion,
    treeEpoch,
    loadRequestId,
    configEpoch,
    configRequestId,
    pendingRequests,
    loading,
    indexing,
    indexStatus,
    indexJobId,
    indexRequestId,
    savingRoot,
    activeCourse,
    applyCourses,
    loadConfig,
    loadCourses,
    saveRoot,
    selectCourse,
    uploadCourseFiles,
    indexActiveCourse,
  }
})
