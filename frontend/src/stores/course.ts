import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { getJson, postFiles, postJson } from '../services/api'
import type {
  ConfigResponse,
  Course,
  CoursesResponse,
  IndexResult,
  SaveConfigResponse,
  UploadResult,
} from '../types/api'

export const useCourseStore = defineStore('course', () => {
  const courses = ref<Course[]>([])
  const config = ref<ConfigResponse | null>(null)
  const activeCourseId = ref<string | null>(null)
  const contextVersion = ref(0)
  const rootVersion = ref(0)
  const treeEpoch = ref(0)
  const loadRequestId = ref(0)
  const configEpoch = ref(0)
  const configRequestId = ref(0)
  const pendingRequests = ref(0)
  const indexing = ref(false)
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
        config.value = {
          root_folder: result.config.root_folder,
          ai_provider: config.value?.ai_provider ?? 'openai_compatible',
          ai_configured: config.value?.ai_configured ?? false,
          mineru_auto: config.value?.mineru_auto ?? true,
          mineru_configured: config.value?.mineru_configured ?? false,
        }
        activeCourseId.value = null
        contextVersion.value += 1
        applyCourses([])

        await loadCourses()
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

    indexing.value = true
    return (async () => {
      try {
        return await postJson<IndexResult>(
          `/api/courses/${encodeURIComponent(courseId)}/index`,
        )
      } finally {
        indexing.value = false
      }
    })()
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
