import { afterEach, describe, expect, it, vi } from 'vitest'

import type {
  MemoryResponse,
  SaveConfigResponse,
  SaveNotesResponse,
  StudyContentResponse,
} from '../types/api'
import { ApiError, postFiles, postJson, requestJson } from './api'

const responseTypeContract = {
  memory: { memory: '最近关注：虚拟内存' } satisfies MemoryResponse,
  studyContent: { content: '课程摘要', citations: [] } satisfies StudyContentResponse,
  savedConfig: { ok: true, config: { root_folder: '/courses' } } satisfies SaveConfigResponse,
  savedNotes: { ok: true, notes: [] } satisfies SaveNotesResponse,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('requestJson', () => {
  it('exposes the backend response type contract', () => {
    expect(responseTypeContract.memory.memory).toContain('虚拟内存')
    expect(responseTypeContract.studyContent.citations).toEqual([])
    expect(responseTypeContract.savedConfig.config.root_folder).toBe('/courses')
    expect(responseTypeContract.savedNotes.notes).toEqual([])
  })

  it('returns typed JSON from a successful response', async () => {
    interface GreetingResponse {
      greeting: string
    }

    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ greeting: 'hello' }), {
      headers: { 'Content-Type': 'application/json' },
      status: 200,
    })))

    const result = await requestJson<GreetingResponse>('/api/greeting')

    expect(result.greeting).toBe('hello')
  })

  it('throws ApiError with the backend error message for a non-2xx response', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ error: '课程不存在' }), {
      headers: { 'Content-Type': 'application/json' },
      status: 404,
      statusText: 'Not Found',
    })))

    const request = requestJson<never>('/api/courses/missing')

    await expect(request).rejects.toMatchObject({
      message: '课程不存在',
      status: 404,
    })
    await expect(request).rejects.toBeInstanceOf(ApiError)
  })

  it('uses a generic message when an error response is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('upstream unavailable', {
      status: 502,
      statusText: 'Bad Gateway',
    })))

    await expect(requestJson<never>('/api/courses')).rejects.toMatchObject({
      message: 'Request failed: 502 Bad Gateway',
      status: 502,
    })
  })
})

describe('postFiles', () => {
  it('sends FormData without manually setting Content-Type', async () => {
    const fetchStub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(new URL(String(input), window.location.origin), init)
      expect(request.method).toBe('POST')
      expect(request.body).not.toBeNull()
      expect(init?.body).toBeInstanceOf(FormData)
      expect(new Headers(init?.headers).has('Content-Type')).toBe(false)

      return new Response(JSON.stringify({ ok: true }), {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      })
    })
    vi.stubGlobal('fetch', fetchStub)
    const form = new FormData()
    form.append('files', new File(['lesson'], 'lesson.txt', { type: 'text/plain' }))

    const result = await postFiles<{ ok: boolean }>('/api/courses/course-1/files', form)

    expect(result).toEqual({ ok: true })
    expect(fetchStub).toHaveBeenCalledOnce()
  })
})

describe('postJson', () => {
  it('serializes the body and sets the JSON Content-Type', async () => {
    const fetchStub = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.method).toBe('POST')
      expect(new Headers(init?.headers).get('Content-Type')).toBe('application/json')
      expect(init?.body).toBe(JSON.stringify({ root_folder: '/courses' }))

      return new Response(JSON.stringify({ ok: true }), {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      })
    })
    vi.stubGlobal('fetch', fetchStub)

    await expect(postJson<{ ok: boolean }>('/api/config', { root_folder: '/courses' }))
      .resolves.toEqual({ ok: true })
  })
})
