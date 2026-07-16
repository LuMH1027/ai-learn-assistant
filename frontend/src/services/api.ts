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
