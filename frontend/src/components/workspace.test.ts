import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App.vue'
import { useChatStore } from '../stores/chat'
import { useCourseStore } from '../stores/course'
import { useLayoutStore } from '../stores/layout'
import type { ChatStreamEvent, Citation, Course, FileLeafNode, Message } from '../types/api'

const jsdom = (globalThis as typeof globalThis & {
  jsdom: { window: Window }
}).jsdom
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: jsdom.window.localStorage,
})

const api = vi.hoisted(() => ({
  getJson: vi.fn(),
  postFiles: vi.fn(),
  postFilesStream: vi.fn(),
  postJson: vi.fn(),
  postJsonStream: vi.fn(),
}))

vi.mock('../services/api', () => api)

const lesson: FileLeafNode = {
  id: 'lesson.pdf',
  name: 'lesson.pdf',
  path: '/courses/os/lesson.pdf',
  type: 'file',
  extension: '.pdf',
  size: 2048,
}

const course: Course = {
  id: 'os',
  name: '操作系统',
  path: '/courses/os',
  children: [{
    id: 'week-one',
    name: '第一周',
    path: '/courses/os/week-one',
    type: 'folder',
    children: [lesson],
  }],
  file_count: 1,
}

const source: Citation = {
  file_id: lesson.id,
  file_name: lesson.name,
  quote: '页表将虚拟页映射到物理页框。',
  page: 7,
  chunk_index: 2,
  score: 0.95,
}

const answer: Message = {
  role: 'assistant',
  content: '页表用于地址转换。',
  citations: [source],
  trace: [{ label: '检索', status: 'ok', detail: '命中课程资料' }],
  created_at: '2026-07-16T00:00:00Z',
}

function mockDesktop() {
  vi.stubGlobal('matchMedia', vi.fn(() => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })))
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

function mockApi() {
  api.postJson.mockImplementation((path: string) => {
    if (path.endsWith('/memory/clear')) {
      return Promise.resolve({
        ok: true,
        messages: [],
        memory: '',
      })
    }
    if (path.endsWith('/notes/1')) {
      return Promise.resolve({
        ok: true,
        notes: [{
          id: 1,
          title: '更新重点',
          content: '复习 TLB 与页表',
          created_at: '2026-07-16T00:00:00Z',
        }],
      })
    }
    if (path.endsWith('/notes/1/delete')) {
      return Promise.resolve({ ok: true, notes: [] })
    }
    if (path.endsWith('/mastery')) {
      return Promise.resolve({
        ok: true,
        mastery: {
          schema_version: 1,
          knowledge_points: [],
          mastery: {},
          mistakes: [],
          created_at: '2026-07-22 10:00:00',
          updated_at: '2026-07-22 10:00:00',
        },
      })
    }
    throw new Error(`Unexpected POST ${path}`)
  })
  api.getJson.mockImplementation((path: string) => {
    if (path === '/api/config') {
      return Promise.resolve({
        root_folder: '/courses',
        ai_provider: 'local',
        ai_configured: true,
        mineru_auto: true,
        mineru_configured: false,
      })
    }
    if (path === '/api/config/status') {
      return Promise.resolve({
        data_dir: '/project/data',
        root_folder: '/courses',
        overall: 'warning',
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
            status: 'warning',
            enabled: false,
            detail: '还没有索引。',
            missing: [],
            index_files: 0,
            total_chunks: 0,
          },
          {
            key: 'vector',
            label: '向量检索',
            status: 'ok',
            enabled: true,
            detail: '本地向量能力可用。',
            missing: [],
          },
          {
            key: 'material_root',
            label: '资料根目录',
            status: 'ok',
            enabled: true,
            detail: '/courses',
            missing: [],
          },
          {
            key: 'data_dir',
            label: '数据目录',
            status: 'ok',
            enabled: true,
            detail: '/project/data',
            missing: [],
          },
          {
            key: 'telemetry',
            label: '遥测诊断',
            status: 'ok',
            enabled: true,
            detail: '内存遥测记录器可用。',
            missing: [],
          },
          {
            key: 'backup',
            label: '备份恢复',
            status: 'ok',
            enabled: true,
            detail: '可备份 2 个数据文件。',
            missing: [],
          },
        ],
      })
    }
    if (path === '/api/courses') return Promise.resolve({ courses: [course] })
    if (path.endsWith('/dashboard')) {
      return Promise.resolve({
        dashboard: {
          course: { id: course.id, name: course.name, path: course.path },
          learning_progress: {
            total: 3,
            done: 1,
            doing: 1,
            todo: 1,
            progress_percent: 33,
            remaining_minutes: 60,
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
            total_bytes: 4096,
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
            knowledge_point_count: 1,
            tracked_count: 1,
            average_score: 35,
            weak_count: 1,
            building_count: 0,
            familiar_count: 0,
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
              wrong_count: 1,
              next_review_at: '2026-07-22 10:00:00',
            }],
            due_reviews: [{
              id: 'kp-page-table',
              type: 'mastery_review',
              title: '页表地址转换',
              score: 35,
              level: 'weak',
              attempts: 2,
              wrong_count: 1,
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
        },
      })
    }
    if (path.endsWith('/messages')) return Promise.resolve({ messages: [answer] })
    if (path.endsWith('/notes')) {
      return Promise.resolve({
        notes: [{
          id: 1,
          title: '重点',
          content: '复习页表',
          created_at: '2026-07-16T00:00:00Z',
        }],
      })
    }
    if (path.endsWith('/plan')) {
      return Promise.resolve({
        plan: {
          items: [],
          stats: {
            total: 0,
            completed: 0,
            doing: 0,
            remaining_minutes: 0,
            progress_percent: 0,
            next_item_id: null,
          },
        },
      })
    }
    throw new Error(`Unexpected GET ${path}`)
  })
}

async function mountWorkspace(options: { mobile?: boolean } = {}) {
  vi.stubGlobal('matchMedia', vi.fn(() => ({
    matches: options.mobile ?? false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })))
  const pinia = createPinia()
  setActivePinia(pinia)
  const courses = useCourseStore()
  courses.applyCourses([course])
  courses.selectCourse(course.id)
  const wrapper = mount(App, { attachTo: document.body, global: { plugins: [pinia] } })
  await flushPromises()
  return { wrapper, pinia }
}

describe('course workspace components', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    window.localStorage.clear()
    vi.resetAllMocks()
    mockDesktop()
    mockApi()
  })

  it('renders three semantic regions, accessible resizers and both file pickers', async () => {
    const { wrapper } = await mountWorkspace()

    expect(wrapper.get('aside[aria-label="课程与资料"]')).toBeTruthy()
    expect(wrapper.get('main[aria-label="课程对话"]')).toBeTruthy()
    expect(wrapper.get('aside[aria-label="资料预览"]')).toBeTruthy()
    const separators = wrapper.findAll('[role="separator"]')
    expect(separators).toHaveLength(2)
    for (const separator of separators) {
      expect(separator.attributes('aria-orientation')).toBe('vertical')
      expect(separator.attributes('tabindex')).toBe('0')
      expect(separator.attributes('aria-valuemin')).toBeTruthy()
      expect(separator.attributes('aria-valuemax')).toBeTruthy()
      expect(separator.attributes('aria-valuenow')).toBeTruthy()
    }
    const fileInputs = wrapper.findAll('input[type="file"][multiple]')
    expect(fileInputs).toHaveLength(2)
    expect(fileInputs.every((input) => input.attributes('hidden') !== undefined)).toBe(true)
  })

  it('renders the compact course dashboard in the sidebar', async () => {
    const { wrapper } = await mountWorkspace()
    await flushPromises()

    const dashboard = wrapper.get('section[aria-labelledby="course-dashboard-title"]')
    expect(dashboard.text()).toContain('课程概览')
    expect(dashboard.text()).toContain('33%')
    expect(dashboard.text()).toContain('2/3')
    expect(dashboard.text()).toContain('12')
    expect(dashboard.text()).toContain('掌握度')
    expect(dashboard.text()).toContain('1 待复习 · 1 未订正')
    expect(dashboard.text()).toContain('下一步：订正页表练习')
    expect(dashboard.text()).toContain('薄弱点：页表地址转换 35')
    expect(dashboard.text()).toContain('最近：笔记 · TLB 易错点')
  })

  it('records a mastery answer from the sidebar and refreshes the dashboard', async () => {
    const { wrapper } = await mountWorkspace()
    await flushPromises()

    await wrapper.get('button[aria-label="记录页表地址转换回答正确"]').trigger('click')
    await flushPromises()

    expect(api.postJson).toHaveBeenCalledWith('/api/courses/os/mastery', {
      answer_result: {
        point_id: 'kp-page-table',
        correct: true,
      },
    })
    const dashboardLoads = api.getJson.mock.calls
      .filter(([path]) => String(path).endsWith('/dashboard'))
    expect(dashboardLoads.length).toBeGreaterThanOrEqual(2)
  })

  it('renders config health status in the sidebar', async () => {
    const { wrapper } = await mountWorkspace()
    await flushPromises()

    const health = wrapper.get('[aria-label="配置健康状态"]')
    expect(health.text()).toContain('配置健康：需关注')
    expect(health.text()).toContain('AI 生成：正常')
    expect(health.text()).toContain('RAG 索引：需配置')
    expect(health.text()).toContain('向量检索：正常')
    expect(health.text()).toContain('遥测诊断：正常')
    expect(health.text()).toContain('备份恢复：正常')
  })

  it('changes and resets a divider with keyboard and double click', async () => {
    const { wrapper } = await mountWorkspace()
    const layout = useLayoutStore()
    const separator = wrapper.findAll('[role="separator"]')[0]!

    await separator.trigger('keydown', { key: 'ArrowRight' })
    expect(layout.sidebarShare).toBe(23)
    await separator.trigger('dblclick')
    expect(layout.sidebarShare).toBe(22)
  })

  it('converts pointer movement into a percentage of the workspace width', async () => {
    const { wrapper } = await mountWorkspace()
    const layout = useLayoutStore()
    const shell = wrapper.get('.workspace-shell')
    vi.spyOn(shell.element, 'getBoundingClientRect').mockReturnValue({
      width: 1000,
      height: 800,
      x: 0,
      y: 0,
      top: 0,
      right: 1000,
      bottom: 800,
      left: 0,
      toJSON: () => ({}),
    })
    const separator = wrapper.findAll('[role="separator"]')[0]!

    await separator.trigger('pointerdown', { clientX: 100, pointerId: 1 })
    await separator.trigger('pointermove', { clientX: 120, pointerId: 1 })

    expect(layout.sidebarShare).toBe(24)
  })

  it('enters compact sidebar mode below fourteen percent', async () => {
    const { wrapper } = await mountWorkspace()
    const layout = useLayoutStore()

    layout.moveLeftBoundary(-10)
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.workspace-shell').classes()).toContain('sidebar-compact')
  })

  it('recalculates the compact minimum as a percentage of workspace width', async () => {
    const { wrapper } = await mountWorkspace()
    const layout = useLayoutStore()
    const shell = wrapper.get('.workspace-shell')
    vi.spyOn(shell.element, 'getBoundingClientRect').mockReturnValue({
      width: 1400, height: 800, x: 0, y: 0, top: 0, right: 1400,
      bottom: 800, left: 0, toJSON: () => ({}),
    })

    window.dispatchEvent(new Event('resize'))
    await wrapper.vm.$nextTick()

    expect(layout.minimumSidebarShare).toBeLessThan(5.5)
    expect(Number(wrapper.get('.left-resizer').attributes('aria-valuemin'))).toBeCloseTo(layout.minimumSidebarShare, 1)
  })

  it('disables course actions while busy and sends on Enter but not Shift+Enter', async () => {
    const { wrapper } = await mountWorkspace()
    const chat = useChatStore()
    chat.busy.chat = true
    await wrapper.vm.$nextTick()

    expect(wrapper.find('button[aria-label="发送问题"]').exists()).toBe(false)
    expect(wrapper.get('button[aria-label="停止回答"]')).toBeTruthy()
    expect(wrapper.get('button[aria-label="生成课程摘要"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="生成练习题"]').attributes('disabled')).toBeDefined()

    const stop = vi.spyOn(chat, 'stop')
    await wrapper.get('button[aria-label="停止回答"]').trigger('click')
    expect(stop).toHaveBeenCalledOnce()

    chat.busy.chat = false
    await wrapper.vm.$nextTick()
    const send = vi.spyOn(chat, 'send').mockResolvedValue(undefined)
    const composer = wrapper.get('textarea[aria-label="课程问题"]')
    await composer.setValue('什么是页表？')
    await composer.trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(send).not.toHaveBeenCalled()
    await composer.trigger('keydown', { key: 'Enter' })
    expect(send).toHaveBeenCalledWith('什么是页表？')
  })

  it('keeps a preview mounted across close/reopen and exposes citation quote and page', async () => {
    const { wrapper } = await mountWorkspace()
    const citationButton = wrapper.get('button[data-citation-file="lesson.pdf"]')
    await citationButton.trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="tablist"]').text()).toContain('当前文件')
    expect(wrapper.get('[role="tablist"]').text()).toContain('引用来源')
    expect(wrapper.get('[role="tablist"]').text()).toContain('信息')
    expect(wrapper.get('blockquote').text()).toContain(source.quote)
    expect(wrapper.text()).toContain('第 7 页')
    expect(wrapper.get('iframe').attributes('src')).toContain('#page=7')

    await wrapper.get('button[aria-label="关闭资料预览"]').trigger('click')
    expect(wrapper.find('aside[aria-label="资料预览"]').exists()).toBe(true)
    expect(useLayoutStore().previewOpen).toBe(false)
    await wrapper.get('button[aria-label="打开资料预览"]').trigger('click')
    expect(wrapper.get('iframe').attributes('src')).toContain('#page=7')
    expect(wrapper.get('blockquote').text()).toContain(source.quote)
  })

  it('renders web citations as external source links instead of preview buttons', async () => {
    const { wrapper } = await mountWorkspace()
    const chat = useChatStore()
    chat.messages = [{
      role: 'assistant',
      content: '这是联网补充。',
      citations: [{
        source_type: 'web',
        reference_label: 'W1',
        file_id: 'web-1',
        file_name: '官方资料',
        url: 'https://example.edu/reference',
        quote: '网页摘要',
        page: null,
        chunk_index: 0,
        score: 1,
      }],
      trace: [],
      created_at: '2026-07-16T01:00:00Z',
    }]
    await wrapper.vm.$nextTick()

    const link = wrapper.get('a[data-web-source="https://example.edu/reference"]')
    expect(link.text()).toContain('官方资料')
    expect(link.text()).toContain('[W1]')
    expect(link.attributes('target')).toBe('_blank')
    expect(wrapper.find('button[data-citation-file="web-1"]').exists()).toBe(false)
  })

  it('shows streaming progress and a cursor while an answer is arriving', async () => {
    const { wrapper } = await mountWorkspace()
    const chat = useChatStore()
    chat.messages = [{
      role: 'assistant',
      content: '正在形成',
      citations: [],
      trace: [],
      created_at: '2026-07-16T02:00:00Z',
      streaming: true,
      stream_status: '正在生成回答…',
    }]
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.stream-status').text()).toBe('正在生成回答…')
    expect(wrapper.get('.streaming-content').text()).toBe('正在形成')
  })

  it('repaints the actual chat component before a batched delta finishes', async () => {
    let emit!: (event: ChatStreamEvent) => Promise<void>
    let finish!: () => void
    api.postJsonStream.mockImplementation((_path: string, _body: unknown, onEvent: typeof emit) => {
      emit = onEvent
      return new Promise<void>((resolve) => { finish = resolve })
    })
    const { wrapper } = await mountWorkspace()
    const chat = useChatStore()
    const request = chat.send('测试流式')

    const rendering = emit({ type: 'delta', delta: '逐字显示' })
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.streaming-content').at(-1)?.text()).toBe('逐')
    await rendering
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.streaming-content').at(-1)?.text()).toBe('逐字显示')

    await emit({
      type: 'done',
      result: { answer: '逐字显示', citations: [], memory: '', mode: 'answer', trace: [] },
    })
    finish()
    await request
  })

  it('shows the newest message after history finishes loading', async () => {
    const { wrapper } = await mountWorkspace()
    const panel = wrapper.get('.messages').element as HTMLElement
    Object.defineProperty(panel, 'scrollHeight', { configurable: true, value: 1200 })
    panel.scrollTop = 0
    const chat = useChatStore()

    chat.messages = [...chat.messages, {
      role: 'assistant',
      content: '最新消息',
      citations: [],
      trace: [],
      created_at: '2026-07-16T03:00:00Z',
    }]
    await wrapper.vm.$nextTick()

    expect(panel.scrollTop).toBe(1200)
  })

  it('makes the notes drawer inert while closed and manages focus and Escape', async () => {
    const { wrapper } = await mountWorkspace()
    const drawer = wrapper.get('aside[aria-labelledby="notes-title"]')
    expect(drawer.attributes('aria-hidden')).toBe('true')
    expect(drawer.attributes('inert')).toBeDefined()

    const trigger = wrapper.get('button[aria-label="打开课程笔记"]')
    await trigger.trigger('click')
    await wrapper.vm.$nextTick()
    expect(drawer.attributes('aria-hidden')).toBe('false')
    expect(drawer.attributes('inert')).toBeUndefined()
    expect(document.activeElement).toBe(wrapper.get('input[aria-label="笔记标题"]').element)

    await drawer.trigger('keydown', { key: 'Escape' })
    expect(drawer.attributes('aria-hidden')).toBe('true')
    expect(document.activeElement).toBe(trigger.element)
  })

  it('edits and deletes saved notes from the drawer', async () => {
    const { wrapper } = await mountWorkspace()
    await wrapper.get('button[aria-label="打开课程笔记"]').trigger('click')
    await flushPromises()

    const edit = wrapper.findAll('button').find((button) => button.text() === '编辑')
    expect(edit).toBeTruthy()
    await edit!.trigger('click')
    await wrapper.get('input[aria-label="编辑笔记标题"]').setValue('更新重点')
    await wrapper.get('textarea[aria-label="编辑笔记内容"]').setValue('复习 TLB 与页表')
    await wrapper.findAll('button').find((button) => button.text() === '保存修改')!.trigger('click')
    await flushPromises()

    expect(api.postJson).toHaveBeenCalledWith('/api/courses/os/notes/1', {
      title: '更新重点',
      content: '复习 TLB 与页表',
    })
    expect(wrapper.get('section[aria-label="已保存笔记"]').text()).toContain('更新重点')

    await wrapper.findAll('button').find((button) => button.text() === '删除')!.trigger('click')
    await flushPromises()

    expect(api.postJson).toHaveBeenCalledWith('/api/courses/os/notes/1/delete')
    expect(wrapper.get('section[aria-label="已保存笔记"]').text()).not.toContain('更新重点')
  })

  it('clears course messages and memory from the toolbar with a busy state', async () => {
    const clearMemory = deferred<{ ok: boolean; messages: Message[]; memory: string }>()
    api.postJson.mockImplementation((path: string) => {
      if (path.endsWith('/memory/clear')) return clearMemory.promise
      return Promise.resolve({
        ok: true,
        mastery: {
          schema_version: 1,
          knowledge_points: [],
          mastery: {},
          mistakes: [],
          created_at: '2026-07-22 10:00:00',
          updated_at: '2026-07-22 10:00:00',
        },
      })
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { wrapper } = await mountWorkspace()
    await flushPromises()

    await wrapper.get('button[aria-label="清空课程会话和记忆"]').trigger('click')
    await wrapper.vm.$nextTick()

    const clearButton = wrapper.get('button[aria-label="清空课程会话和记忆"]')
    expect(clearButton.text()).toBe('清空中…')
    expect(clearButton.attributes('disabled')).toBeDefined()
    expect(window.confirm).toHaveBeenCalledWith('清空 操作系统 的会话和记忆？此操作不会删除课程笔记。')

    clearMemory.resolve({ ok: true, messages: [], memory: '' })
    await flushPromises()

    expect(api.postJson).toHaveBeenCalledWith('/api/courses/os/memory/clear')
    expect(useChatStore().messages).toEqual([])
    expect(clearButton.text()).toBe('清空记忆')
  })

  it('uses inert to isolate mobile sidebar and preview drawers', async () => {
    const { wrapper } = await mountWorkspace({ mobile: true })
    const sidebar = wrapper.get('aside[aria-label="课程与资料"]')
    const agent = wrapper.get('main[aria-label="课程对话"]')
    expect(sidebar.attributes('inert')).toBeDefined()
    expect(agent.attributes('inert')).toBeUndefined()

    await wrapper.get('button[aria-label="打开课程栏"]').trigger('click')
    expect(sidebar.attributes('inert')).toBeUndefined()
    await wrapper.get('button[aria-label="关闭课程栏"]').trigger('click')
    await wrapper.get('button[aria-label="打开资料预览"]').trigger('click')
    expect(agent.attributes('inert')).toBeDefined()
  })
})
