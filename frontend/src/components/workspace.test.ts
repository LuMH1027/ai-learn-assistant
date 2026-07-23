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

function masteryPayload(status: 'open' | 'resolved' = 'open') {
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
        score: 35,
        level: 'weak',
        attempts: 2,
        correct_count: 1,
        wrong_count: 1,
        streak: 0,
        last_result: 'wrong',
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
      status,
      review_count: status === 'resolved' ? 1 : 0,
      created_at: '2026-07-21 10:00:00',
      updated_at: status === 'resolved' ? '2026-07-22 10:00:00' : '2026-07-21 10:00:00',
      resolved_at: status === 'resolved' ? '2026-07-22 10:00:00' : '',
    }],
    created_at: '2026-07-21 10:00:00',
    updated_at: status === 'resolved' ? '2026-07-22 10:00:00' : '2026-07-21 10:00:00',
  }
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
    if (path.endsWith('/mastery/mistakes/mistake-1/resolve')) {
      return Promise.resolve({
        ok: true,
        mastery: masteryPayload('resolved'),
      })
    }
    if (path.endsWith('/mastery')) {
      return Promise.resolve({
        ok: true,
        mastery: masteryPayload(),
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
    if (path.endsWith('/mastery')) {
      return Promise.resolve({
        mastery: masteryPayload(),
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

  it('offers exactly three study modes', async () => {
    const { wrapper } = await mountWorkspace()
    const options = wrapper.findAll('#chat-mode option')

    expect(options.map((option) => option.attributes('value'))).toEqual(['answer', 'guide', 'review'])
    expect(options.map((option) => option.text())).toEqual(['答疑', '启发提示', '复习'])
  })

  it('keeps the sidebar focused on courses, conversations, files and settings', async () => {
    const { wrapper } = await mountWorkspace()
    await flushPromises()

    expect(wrapper.find('section[aria-labelledby="course-dashboard-title"]').exists()).toBe(false)
    expect(wrapper.find('form[aria-label="新增知识点"]').exists()).toBe(false)
    expect(wrapper.get('section[aria-labelledby="course-list-title"]').text()).toContain('操作系统')
    expect(wrapper.get('section[aria-labelledby="conversation-list-title"]').text()).toContain('对话')
    expect(wrapper.get('section[aria-labelledby="file-tree-title"]').text()).toContain('lesson.pdf')
    expect(wrapper.get('details.settings-menu').text()).toContain('资料根目录')
  })

  it('uses a hamburger settings trigger and closes it on outside click', async () => {
    const { wrapper } = await mountWorkspace()
    await flushPromises()

    const menu = wrapper.get('details.settings-menu').element as HTMLDetailsElement
    expect(wrapper.get('details.settings-menu > summary').text()).toBe('☰')

    menu.open = true
    document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
    expect(menu.open).toBe(false)
  })

  it('renders config health status in the sidebar', async () => {
    const { wrapper } = await mountWorkspace()
    await flushPromises()

    const health = wrapper.get('[aria-label="配置健康状态"]')
    expect(health.text()).toContain('配置：缺 RAG 索引')
    expect(health.text()).not.toContain('AI 生成')
    expect(health.text()).not.toContain('向量检索')
  })

  it('highlights the course drop zone while files are dragged over it', async () => {
    const { wrapper } = await mountWorkspace()
    await flushPromises()

    const dropZone = wrapper.get('.course-drop-zone')
    await dropZone.trigger('dragenter')
    expect(dropZone.attributes('data-dragging')).toBe('true')
    await dropZone.trigger('drop', {
      dataTransfer: {
        files: [new File(['x'], 'lesson.txt', { type: 'text/plain' })],
      },
    })
    expect(dropZone.attributes('data-dragging')).toBe('false')
  })

  it('does not render or auto-load the removed study plan feature', async () => {
    const { wrapper } = await mountWorkspace()
    await flushPromises()

    expect(wrapper.find('section[aria-labelledby="study-plan-title"]').exists()).toBe(false)
    expect(api.getJson.mock.calls.some(([path]) => String(path).endsWith('/plan'))).toBe(false)
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

  it('recalls previous user messages with ArrowUp and restores the draft with ArrowDown', async () => {
    const { wrapper } = await mountWorkspace()
    const chat = useChatStore()
    chat.messages = [
      { role: 'user', content: '第一问', citations: [], trace: [], created_at: '2026-07-16T00:00:00Z' },
      answer,
      { role: 'user', content: '第二问', citations: [], trace: [], created_at: '2026-07-16T00:01:00Z' },
    ]
    const composer = wrapper.get('textarea[aria-label="课程问题"]')
    await composer.setValue('当前草稿')
    const element = composer.element as HTMLTextAreaElement
    element.setSelectionRange(element.value.length, element.value.length)

    await composer.trigger('keydown', { key: 'ArrowUp' })
    expect(chat.draft).toBe('第二问')
    element.setSelectionRange(0, 0)
    await composer.trigger('keydown', { key: 'ArrowUp' })
    expect(chat.draft).toBe('第一问')
    element.setSelectionRange(element.value.length, element.value.length)
    await composer.trigger('keydown', { key: 'ArrowDown' })
    expect(chat.draft).toBe('第二问')
    element.setSelectionRange(element.value.length, element.value.length)
    await composer.trigger('keydown', { key: 'ArrowDown' })
    expect(chat.draft).toBe('当前草稿')
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
      stream_thoughts: ['course_search：需要课程资料 · 页表'],
    }]
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.stream-status').text()).toBe('正在生成回答…')
    expect(wrapper.get('.thinking-panel').text()).toContain('当前思考')
    expect(wrapper.get('.thinking-panel').text()).toContain('需要课程资料')
    expect(wrapper.get('.streaming-content').text()).toBe('正在形成')
  })

  it('renders assistant markdown while preserving user text', async () => {
    const { wrapper } = await mountWorkspace()
    const chat = useChatStore()
    chat.messages = [
      {
        role: 'user',
        content: '**不要渲染我**',
        citations: [],
        trace: [],
        created_at: '2026-07-16T02:00:00Z',
      },
      {
        role: 'assistant',
        content: '**重点**\n\n- 页表\n- TLB',
        citations: [],
        trace: [],
        created_at: '2026-07-16T02:00:01Z',
        streaming: true,
        stream_status: '正在生成回答…',
      },
    ]
    await wrapper.vm.$nextTick()

    expect(wrapper.get('article.user p').text()).toBe('**不要渲染我**')
    expect(wrapper.get('article.assistant strong').text()).toBe('重点')
    expect(wrapper.findAll('article.assistant li')).toHaveLength(2)
    expect(wrapper.get('article.assistant .message-markdown').classes()).toContain('streaming-content')
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
    const drawer = wrapper.get('aside[aria-labelledby="notes-title"]')

    const edit = drawer.findAll('button').find((button) => button.text() === '编辑')
    expect(edit).toBeTruthy()
    await edit!.trigger('click')
    await wrapper.get('input[aria-label="编辑笔记标题"]').setValue('更新重点')
    await wrapper.get('textarea[aria-label="编辑笔记内容"]').setValue('复习 TLB 与页表')
    await drawer.findAll('button').find((button) => button.text() === '保存修改')!.trigger('click')
    await flushPromises()

    expect(api.postJson).toHaveBeenCalledWith('/api/courses/os/notes/1', {
      title: '更新重点',
      content: '复习 TLB 与页表',
    })
    expect(wrapper.get('section[aria-label="已保存笔记"]').text()).toContain('更新重点')

    await drawer.findAll('button').find((button) => button.text() === '删除')!.trigger('click')
    await flushPromises()

    expect(api.postJson).toHaveBeenCalledWith('/api/courses/os/notes/1/delete')
    expect(wrapper.get('section[aria-label="已保存笔记"]').text()).not.toContain('更新重点')
  })

  it('clears current conversation messages and memory from the toolbar with a busy state', async () => {
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

    await wrapper.get('button[aria-label="清空当前对话和记忆"]').trigger('click')
    await wrapper.vm.$nextTick()

    const clearButton = wrapper.get('button[aria-label="清空当前对话和记忆"]')
    expect(clearButton.text()).toBe('清空中…')
    expect(clearButton.attributes('disabled')).toBeDefined()
    expect(window.confirm).toHaveBeenCalledWith('清空「历史对话」的消息和记忆？课程资料和课程笔记不会删除。')

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
