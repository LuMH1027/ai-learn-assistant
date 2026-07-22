import { afterEach, describe, expect, it, vi } from 'vitest'

import type {
  MemoryResponse,
  MasteryResponse,
  SaveConfigResponse,
  SaveNotesResponse,
  StudyContentResponse,
} from '../types/api'
import { ApiError, postFiles, postJson, postJsonStream, requestJson } from './api'

const responseTypeContract = {
  memory: { memory: '最近关注：虚拟内存' } satisfies MemoryResponse,
  mastery: {
    mastery: {
      schema_version: 1,
      knowledge_points: [],
      mastery: {},
      mistakes: [],
      created_at: '2026-07-21 10:00:00',
      updated_at: '2026-07-21 10:00:00',
    },
  } satisfies MasteryResponse,
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
    expect(responseTypeContract.mastery.mastery.schema_version).toBe(1)
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

describe('postJsonStream', () => {
  it('awaits every SSE event before consuming the next token', async () => {
    const events: Array<{ type: string; delta?: string }> = []
    const body = [
      `data: ${JSON.stringify({ type: 'status', detail: '检索中' })}\n\n`,
      `data: ${JSON.stringify({ type: 'delta', delta: '你' })}\n\n`,
      `data: ${JSON.stringify({ type: 'delta', delta: '好' })}\n\n`,
    ].join('')
    let processing = false
    const controller = new AbortController()
    const fetchStub = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(new Headers(init?.headers).get('Accept')).toBe('text/event-stream')
      expect(init?.signal).toBe(controller.signal)
      return new Response(body, {
        headers: { 'Content-Type': 'text/event-stream' },
        status: 200,
      })
    })
    vi.stubGlobal('fetch', fetchStub)

    await postJsonStream<{ type: string; delta?: string }>(
      '/api/chat',
      { question: 'hello' },
      async (event) => {
        expect(processing).toBe(false)
        processing = true
        events.push(event)
        await Promise.resolve()
        processing = false
      },
      controller.signal,
    )

    expect(fetchStub).toHaveBeenCalledOnce()
    expect(events).toEqual([
      { type: 'status', detail: '检索中' },
      { type: 'delta', delta: '你' },
      { type: 'delta', delta: '好' },
    ])
  })

  it('parses SSE events split across response chunks', async () => {
    const encoder = new TextEncoder()
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"type":"delta","del'))
        controller.enqueue(encoder.encode('ta":"逐"}\n\ndata: {"type":"delta","delta":"字"}\n\n'))
        controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn(async () => new Response(body, {
      headers: { 'Content-Type': 'text/event-stream' },
      status: 200,
    })))
    const events: Array<{ type: string; delta: string }> = []

    await postJsonStream<{ type: string; delta: string }>(
      '/api/chat',
      { question: 'hello' },
      (event) => { events.push(event) },
    )

    expect(events).toEqual([
      { type: 'delta', delta: '逐' },
      { type: 'delta', delta: '字' },
    ])
  })
})
