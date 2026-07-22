import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { getJson, postFiles, postJson } from '../services/api'
import type {
  ConfigResponse,
  ConfigStatusResponse,
  Course,
  CourseDashboard,
  CourseDashboardResponse,
  CoursesResponse,
  IndexJob,
  IndexResult,
  MasteryResponse,
  MasteryState,
  SaveConfigResponse,
  SaveMasteryResponse,
  SaveStudyPlanResponse,
  StudyPlan,
  StudyPlanItem,
  StudyPlanResponse,
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
  const configStatus = ref<ConfigStatusResponse | null>(null)
  const configStatusLoading = ref(false)
  const configStatusRequestId = ref(0)
  const pendingRequests = ref(0)
  const indexing = ref(false)
  const indexStatus = ref<string | null>(null)
  const indexJobId = ref<string | null>(null)
  const indexRequestId = ref(0)
  const savingRoot = ref(false)
  const studyPlan = ref<StudyPlan | null>(null)
  const planLoading = ref(false)
  const planRequestId = ref(0)
  const dashboard = ref<CourseDashboard | null>(null)
  const dashboardLoading = ref(false)
  const dashboardRequestId = ref(0)
  const mastery = ref<MasteryState | null>(null)
  const masteryLoading = ref(false)
  const masteryRequestId = ref(0)

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
      resetStudyPlan()
      resetDashboard()
      resetMastery()
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

  function loadConfigStatus() {
    const requestId = ++configStatusRequestId.value
    const requestedConfigEpoch = configEpoch.value
    configStatusLoading.value = true
    return trackRequest(async () => {
      try {
        const result = await getJson<ConfigStatusResponse>('/api/config/status')
        if (
          requestId === configStatusRequestId.value &&
          requestedConfigEpoch === configEpoch.value
        ) {
          configStatus.value = result
        }
        return result
      } finally {
        if (
          requestId === configStatusRequestId.value &&
          requestedConfigEpoch === configEpoch.value
        ) {
          configStatusLoading.value = false
        }
      }
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
    resetStudyPlan()
    resetDashboard()
    resetMastery()
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
        resetStudyPlan()
        resetDashboard()
        resetMastery()
        resetConfigStatus()
        config.value = {
          ...(config.value ?? {}),
          root_folder: result.config.root_folder,
        }
        activeCourseId.value = null
        contextVersion.value += 1
        applyCourses([])

        const [, , coursesRefresh] = await Promise.allSettled([
          loadConfig(),
          loadConfigStatus(),
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

  function resetStudyPlan() {
    planRequestId.value += 1
    studyPlan.value = null
    planLoading.value = false
  }

  function resetDashboard() {
    dashboardRequestId.value += 1
    dashboard.value = null
    dashboardLoading.value = false
  }

  function resetMastery() {
    masteryRequestId.value += 1
    mastery.value = null
    masteryLoading.value = false
  }

  function resetConfigStatus() {
    configStatusRequestId.value += 1
    configStatus.value = null
    configStatusLoading.value = false
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

  function loadStudyPlan() {
    const courseId = activeCourseId.value
    if (courseId === null) {
      resetStudyPlan()
      return
    }
    const requestId = ++planRequestId.value
    const requestedRootVersion = rootVersion.value
    planLoading.value = true
    return trackRequest(async () => {
      try {
        const result = await getJson<StudyPlanResponse>(
          `/api/courses/${encodeURIComponent(courseId)}/plan`,
        )
        if (isCurrentPlanRequest(courseId, requestedRootVersion, requestId)) {
          studyPlan.value = result.plan
        }
        return result.plan
      } finally {
        if (isCurrentPlanRequest(courseId, requestedRootVersion, requestId)) {
          planLoading.value = false
        }
      }
    })
  }

  function loadDashboard() {
    const courseId = activeCourseId.value
    if (courseId === null) {
      resetDashboard()
      return
    }
    const requestId = ++dashboardRequestId.value
    const requestedRootVersion = rootVersion.value
    dashboardLoading.value = true
    return trackRequest(async () => {
      try {
        const result = await getJson<CourseDashboardResponse>(
          `/api/courses/${encodeURIComponent(courseId)}/dashboard`,
        )
        if (isCurrentDashboardRequest(courseId, requestedRootVersion, requestId)) {
          dashboard.value = result.dashboard
        }
        return result.dashboard
      } finally {
        if (isCurrentDashboardRequest(courseId, requestedRootVersion, requestId)) {
          dashboardLoading.value = false
        }
      }
    })
  }

  function loadMastery() {
    const courseId = activeCourseId.value
    if (courseId === null) {
      resetMastery()
      return
    }
    const requestId = ++masteryRequestId.value
    const requestedRootVersion = rootVersion.value
    masteryLoading.value = true
    return trackRequest(async () => {
      try {
        const result = await getJson<MasteryResponse>(
          `/api/courses/${encodeURIComponent(courseId)}/mastery`,
        )
        if (isCurrentMasteryRequest(courseId, requestedRootVersion, requestId)) {
          mastery.value = result.mastery
        }
        return result.mastery
      } finally {
        if (isCurrentMasteryRequest(courseId, requestedRootVersion, requestId)) {
          masteryLoading.value = false
        }
      }
    })
  }

  function addStudyPlanItem(title: string, kind: StudyPlanItem['kind'] = 'read') {
    const courseId = activeCourseId.value
    if (courseId === null || !title.trim()) return
    const requestedRootVersion = rootVersion.value
    return trackRequest(async () => {
      const result = await postJson<SaveStudyPlanResponse>(
        `/api/courses/${encodeURIComponent(courseId)}/plan`,
        { title: title.trim(), kind },
      )
      if (activeCourseId.value === courseId && rootVersion.value === requestedRootVersion) {
        studyPlan.value = result.plan
      }
      return result.plan
    })
  }

  function updateStudyPlanItem(
    item: StudyPlanItem,
    changes: Partial<Pick<StudyPlanItem, 'status' | 'title' | 'kind' | 'estimated_minutes'>>,
  ) {
    const courseId = activeCourseId.value
    if (courseId === null) return
    const requestedRootVersion = rootVersion.value
    return trackRequest(async () => {
      const result = await postJson<SaveStudyPlanResponse>(
        `/api/courses/${encodeURIComponent(courseId)}/plan/${encodeURIComponent(String(item.id))}`,
        changes,
      )
      if (activeCourseId.value === courseId && rootVersion.value === requestedRootVersion) {
        studyPlan.value = result.plan
      }
      return result.plan
    })
  }

  function cycleStudyPlanItem(item: StudyPlanItem) {
    const nextStatus: StudyPlanItem['status'] = item.status === 'todo'
      ? 'doing'
      : item.status === 'doing'
        ? 'done'
        : 'todo'
    return updateStudyPlanItem(item, { status: nextStatus })
  }

  function updateMastery(body: unknown) {
    const courseId = activeCourseId.value
    if (courseId === null) return
    const requestedRootVersion = rootVersion.value
    return trackRequest(async () => {
      const result = await postJson<SaveMasteryResponse>(
        `/api/courses/${encodeURIComponent(courseId)}/mastery`,
        body,
      )
      if (activeCourseId.value === courseId && rootVersion.value === requestedRootVersion) {
        mastery.value = result.mastery
      }
      return result.mastery
    })
  }

  function isCurrentPlanRequest(courseId: string, requestedRootVersion: number, requestId: number) {
    return activeCourseId.value === courseId &&
      rootVersion.value === requestedRootVersion &&
      requestId === planRequestId.value
  }

  function isCurrentDashboardRequest(courseId: string, requestedRootVersion: number, requestId: number) {
    return activeCourseId.value === courseId &&
      rootVersion.value === requestedRootVersion &&
      requestId === dashboardRequestId.value
  }

  function isCurrentMasteryRequest(courseId: string, requestedRootVersion: number, requestId: number) {
    return activeCourseId.value === courseId &&
      rootVersion.value === requestedRootVersion &&
      requestId === masteryRequestId.value
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
    configStatus,
    configStatusLoading,
    configStatusRequestId,
    pendingRequests,
    loading,
    indexing,
    indexStatus,
    indexJobId,
    indexRequestId,
    savingRoot,
    studyPlan,
    planLoading,
    planRequestId,
    dashboard,
    dashboardLoading,
    dashboardRequestId,
    mastery,
    masteryLoading,
    masteryRequestId,
    activeCourse,
    applyCourses,
    loadConfig,
    loadConfigStatus,
    loadCourses,
    saveRoot,
    selectCourse,
    uploadCourseFiles,
    indexActiveCourse,
    loadStudyPlan,
    loadDashboard,
    loadMastery,
    addStudyPlanItem,
    updateStudyPlanItem,
    cycleStudyPlanItem,
    updateMastery,
  }
})
