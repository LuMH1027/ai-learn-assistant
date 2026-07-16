import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App.vue'
import { useChatStore } from '../stores/chat'
import { useCourseStore } from '../stores/course'
import { useLayoutStore } from '../stores/layout'
import type { Citation, Course, FileLeafNode, Message } from '../types/api'

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
  postJson: vi.fn(),
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

function mockApi() {
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
    if (path === '/api/courses') return Promise.resolve({ courses: [course] })
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

  it('disables course actions while busy and sends on Enter but not Shift+Enter', async () => {
    const { wrapper } = await mountWorkspace()
    const chat = useChatStore()
    chat.busy.chat = true
    await wrapper.vm.$nextTick()

    expect(wrapper.get('button[aria-label="发送问题"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="生成课程摘要"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="生成练习题"]').attributes('disabled')).toBeDefined()

    chat.busy.chat = false
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
    expect(wrapper.find('aside[aria-label="资料预览"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="打开资料预览"]').trigger('click')
    expect(wrapper.get('iframe').attributes('src')).toContain('#page=7')
    expect(wrapper.get('blockquote').text()).toContain(source.quote)
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
