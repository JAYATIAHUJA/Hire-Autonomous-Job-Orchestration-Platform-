import { ApiError } from './client'
import { mockAccountApi } from './mock'
import type {
  AnswerBank,
  ConsentRecord,
  ConsentRequest,
  Me,
  OtpSendResponse,
  PowRun,
  Preferences,
  ResumeUploadResponse,
} from './v1types'

// The /v1 surface the logged-in app talks to. One interface, two implementations:
// the real API and an in-browser mock (VITE_USE_MOCKS=1) used until WP1, WP2 and
// WP6 land, so screens are never blocked on the backend.
export interface AccountApi {
  getMe(): Promise<Me | null> // null when logged out (401)
  sendOtp(email: string): Promise<OtpSendResponse>
  verifyOtp(email: string, code: string): Promise<Me>
  oauthStartUrl(provider: 'github' | 'google', returnTo: string): string
  logout(): Promise<void>
  recordConsent(body: ConsentRequest): Promise<ConsentRecord>
  completeOnboarding(): Promise<Me>
  startPowRefresh(): Promise<PowRun>
  getPowRun(id: string): Promise<PowRun>
  uploadResume(file: File): Promise<ResumeUploadResponse>
  approveFacts(ids: string[]): Promise<void>
  rejectFacts(ids: string[]): Promise<void>
  savePreferences(prefs: Preferences): Promise<void>
  getAnswerBank(): Promise<AnswerBank>
  saveAnswerBank(answers: AnswerBank): Promise<void>
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const v1 = (path: string) => `${API_BASE}/v1${path}`

// Every call carries the session cookie and the CSRF header WP1 checks on
// state-changing requests.
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('X-Requested-With', 'hire-web')
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const res = await fetch(v1(path), { ...init, headers, credentials: 'include' })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = typeof body.detail === 'string' ? body.detail : `Request failed (${res.status})`
    throw new ApiError(detail, res.status)
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) })

export const httpAccountApi: AccountApi = {
  async getMe() {
    try {
      return await request<Me>('/me')
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return null
      throw err
    }
  },
  sendOtp: (email) => request('/auth/otp/send', json('POST', { email })),
  verifyOtp: (email, code) => request('/auth/otp/verify', json('POST', { email, code })),
  oauthStartUrl: (provider, returnTo) =>
    `${v1(`/auth/${provider}/start`)}?${new URLSearchParams({ return_to: returnTo }).toString()}`,
  logout: () => request('/auth/logout', { method: 'POST' }),
  recordConsent: (body) => request('/me/consents', json('POST', body)),
  completeOnboarding: () => request('/me', json('PATCH', { onboarding_completed: true })),
  startPowRefresh: () => request('/profile/pow/refresh', { method: 'POST' }),
  getPowRun: (id) => request(`/profile/pow/runs/${encodeURIComponent(id)}`),
  uploadResume(file) {
    const form = new FormData()
    form.append('file', file)
    return request('/profile/resume', { method: 'POST', body: form })
  },
  approveFacts: (ids) => request('/profile/facts/approve', json('POST', { ids })),
  rejectFacts: (ids) => request('/profile/facts/reject', json('POST', { ids })),
  savePreferences: (prefs) => request('/me/preferences', json('PATCH', prefs)),
  async getAnswerBank() {
    const body = await request<{ answers?: AnswerBank }>('/me/answer-bank')
    return body?.answers ?? {}
  },
  saveAnswerBank: (answers) => request('/me/answer-bank', json('PUT', { answers })),
}

export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === '1'

export const accountApi: AccountApi = USE_MOCKS ? mockAccountApi : httpAccountApi
