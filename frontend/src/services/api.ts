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
  onEvent: (event: T) => void,
): Promise<void> {
  return requestNdjson(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/x-ndjson',
    },
    body: JSON.stringify(body),
  }, onEvent)
}

export function postFilesStream<T>(
  path: string,
  form: FormData,
  onEvent: (event: T) => void,
): Promise<void> {
  return requestNdjson(path, {
    method: 'POST',
    headers: { Accept: 'application/x-ndjson' },
    body: form,
  }, onEvent)
}

async function requestNdjson<T>(
  path: string,
  init: RequestInit,
  onEvent: (event: T) => void,
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
    buffer += decoder.decode(value, { stream: !done })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.trim()) continue
      const event = JSON.parse(line) as T
      if (isStreamError(event)) throw new Error(event.error)
      onEvent(event)
    }
    if (done) break
  }
  if (buffer.trim()) {
    const event = JSON.parse(buffer) as T
    if (isStreamError(event)) throw new Error(event.error)
    onEvent(event)
  }
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
