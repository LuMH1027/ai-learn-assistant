interface ErrorResponse {
  error?: unknown
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)

  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }

  return response.json() as Promise<T>
}

export function getJson<T>(path: string): Promise<T> {
  return requestJson<T>(path)
}

export function postJson<T>(path: string, body?: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export function postFiles<T>(path: string, form: FormData): Promise<T> {
  return requestJson<T>(path, {
    method: 'POST',
    body: form,
  })
}

export function postJsonStream<T>(
  path: string,
  body: unknown,
  onEvent: (event: T) => void | Promise<void>,
  signal?: AbortSignal,
): Promise<void> {
  return requestEventStream(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
    signal,
  }, onEvent)
}

export function postFilesStream<T>(
  path: string,
  form: FormData,
  onEvent: (event: T) => void | Promise<void>,
  signal?: AbortSignal,
): Promise<void> {
  return requestEventStream(path, {
    method: 'POST',
    headers: { Accept: 'text/event-stream' },
    body: form,
    signal,
  }, onEvent)
}

async function requestEventStream<T>(
  path: string,
  init: RequestInit,
  onEvent: (event: T) => void | Promise<void>,
): Promise<void> {
  const response = await fetch(path, init)
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  if (!response.body) {
    throw new Error('浏览器未提供流式响应内容')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    buffer = await consumeEventBlocks(buffer, onEvent)
    if (done) break
  }
  if (buffer.trim()) {
    await consumeEventBlock(buffer, onEvent)
  }
}

async function consumeEventBlocks<T>(
  input: string,
  onEvent: (event: T) => void | Promise<void>,
): Promise<string> {
  let buffer = input
  let boundary = buffer.indexOf('\n\n')
  while (boundary >= 0) {
    await consumeEventBlock(buffer.slice(0, boundary), onEvent)
    buffer = buffer.slice(boundary + 2)
    boundary = buffer.indexOf('\n\n')
  }
  return buffer
}

async function consumeEventBlock<T>(
  block: string,
  onEvent: (event: T) => void | Promise<void>,
): Promise<void> {
  const data = block
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')
  if (!data || data === '[DONE]') return
  const event = JSON.parse(data) as T
  if (isStreamError(event)) throw new Error(event.error)
  await onEvent(event)
}

function isStreamError(value: unknown): value is { type: 'error'; error: string } {
  return typeof value === 'object' && value !== null &&
    (value as { type?: unknown }).type === 'error' &&
    typeof (value as { error?: unknown }).error === 'string'
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json() as ErrorResponse
    if (typeof payload.error === 'string' && payload.error) {
      return payload.error
    }
  } catch {
    // Fall back to the HTTP status when the backend does not return JSON.
  }

  const status = response.statusText
    ? `${response.status} ${response.statusText}`
    : String(response.status)
  return `Request failed: ${status}`
}
