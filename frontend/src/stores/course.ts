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
  const loading = ref(false)
  const indexing = ref(false)

  const activeCourse = computed(() =>
    courses.value.find((course) => course.id === activeCourseId.value) ?? null,
  )

  function applyCourses(nextCourses: Course[]) {
    courses.value = nextCourses
    if (
      activeCourseId.value !== null &&
      !nextCourses.some((course) => course.id === activeCourseId.value)
    ) {
      activeCourseId.value = null
      contextVersion.value += 1
    }
  }

  async function loadConfig() {
    loading.value = true
    try {
      const result = await getJson<ConfigResponse>('/api/config')
      config.value = result
      return result
    } finally {
      loading.value = false
    }
  }

  async function loadCourses() {
    loading.value = true
    try {
      const result = await getJson<CoursesResponse>('/api/courses')
      applyCourses(result.courses)
      return result.courses
    } finally {
      loading.value = false
    }
  }

  function selectCourse(course: Course | string | null) {
    const nextId = typeof course === 'string' ? course : course?.id ?? null
    if (nextId === activeCourseId.value) return

    activeCourseId.value = nextId
    contextVersion.value += 1
  }

  async function saveRoot(rootFolder: string) {
    loading.value = true
    try {
      const result = await postJson<SaveConfigResponse>('/api/config', {
        root_folder: rootFolder,
      })
      config.value = {
        root_folder: result.config.root_folder,
        ai_provider: config.value?.ai_provider ?? 'openai_compatible',
        ai_configured: config.value?.ai_configured ?? false,
        mineru_auto: config.value?.mineru_auto ?? true,
        mineru_configured: config.value?.mineru_configured ?? false,
      }
      activeCourseId.value = null
      contextVersion.value += 1

      const coursesResult = await getJson<CoursesResponse>('/api/courses')
      applyCourses(coursesResult.courses)
      return result
    } finally {
      loading.value = false
    }
  }

  function uploadCourseFiles(files: File[]) {
    const courseId = activeCourseId.value
    if (courseId === null || files.length === 0) return

    return (async () => {
      const form = new FormData()
      for (const file of files) form.append('files', file, file.name)
      const result = await postFiles<UploadResult>(
        `/api/courses/${encodeURIComponent(courseId)}/files`,
        form,
      )
      applyCourses(result.courses)
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
    loading,
    indexing,
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
