import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'

const api = vi.hoisted(() => ({
  getJson: vi.fn(),
  postFiles: vi.fn(),
  postJson: vi.fn(),
}))

vi.mock('./services/api', () => api)

describe('App', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })))
    api.getJson.mockImplementation((path: string) => {
      if (path === '/api/config') {
        return Promise.resolve({
          root_folder: '/courses',
          ai_provider: 'local',
          ai_configured: true,
          mineru_auto: true,
          mineru_configured: true,
        })
      }
      if (path === '/api/courses') return Promise.resolve({ courses: [] })
      return Promise.resolve(path.endsWith('/notes') ? { notes: [] } : { messages: [] })
    })
  })

  it('hydrates the semantic course workspace and loads its initial data', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(App, { global: { plugins: [pinia] } })
    await flushPromises()

    expect(wrapper.get('h1').text()).toContain('课程 Agent')
    expect(wrapper.get('aside[aria-label="课程与资料"]')).toBeTruthy()
    expect(wrapper.get('main[aria-label="课程对话"]')).toBeTruthy()
    expect(wrapper.get('aside[aria-label="资料预览"]')).toBeTruthy()
    expect(api.getJson).toHaveBeenCalledWith('/api/config')
    expect(api.getJson).toHaveBeenCalledWith('/api/courses')
  })
})
