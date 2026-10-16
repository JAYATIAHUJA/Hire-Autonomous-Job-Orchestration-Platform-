import type {
  AnalyzeResponse,
  ApplicationCard,
  BoardResponse,
  ConsentReceipt,
  DeckResponse,
  MailSyncResponse,
  PipelineStage,
  Profile,
  RecruiterMessage,
  SwipeResponse,
} from '../types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const url = (path: string) => `${API_BASE}${path}`
const BASE_URL = `${API_BASE}/api/profile`

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// Every call carries the session cookie and the CSRF header the API checks on
// state-changing requests (WP1); without them each route answers 401 or 403.
export function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  headers.set('X-Requested-With', 'hire-web')
  return fetch(input, { ...init, headers, credentials: 'include' })
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = typeof body.detail === 'string' ? body.detail : `Request failed (${res.status})`
    throw new ApiError(detail, res.status)
  }
  return res.json()
}

export async function analyzeProfile(username: string, token?: string): Promise<AnalyzeResponse> {
  const res = await apiFetch(`${BASE_URL}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, token: token || null }),
  })
  return handle<AnalyzeResponse>(res)
}

export async function getProfile(profileId: string): Promise<Profile> {
  return handle<Profile>(await apiFetch(`${BASE_URL}/${encodeURIComponent(profileId)}`))
}

export type FeedFilters = {
  q?: string
  city?: string
  remote?: boolean
  sort?: 'trust' | 'newest' | 'match'
  level?: string
  salaryShown?: boolean
  postedWithin?: number
}

export async function getJobFeed(
  limit: number = 20,
  page: number = 1,
  minLegitimacy: number = 0.6,
  filters: FeedFilters = {},
): Promise<import('../types').JobFeedResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    page: String(page),
    min_legitimacy: String(minLegitimacy),
  })
  if (filters.q?.trim()) params.set('q', filters.q.trim())
  if (filters.city) params.set('city', filters.city)
  if (filters.remote) params.set('remote', 'true')
  if (filters.sort) params.set('sort', filters.sort)
  if (filters.level) params.set('level', filters.level)
  if (filters.salaryShown) params.set('salary_shown', 'true')
  if (filters.postedWithin) params.set('posted_within', String(filters.postedWithin))
  return handle<import('../types').JobFeedResponse>(await apiFetch(url(`/api/jobs/feed?${params.toString()}`)))
}

export async function getJobDetail(jobId: string): Promise<import('../types').JobContract> {
  return handle<import('../types').JobContract>(await apiFetch(url(`/api/jobs/${encodeURIComponent(jobId)}`)))
}

export async function getDiscovery(): Promise<import('../types').DiscoveryStatus> {
  return handle(await apiFetch(url('/api/jobs/discovery')))
}

// Ask the worker to check the job boards now. Returns the status with the queued run.
export async function requestDiscovery(): Promise<import('../types').DiscoveryStatus> {
  return handle(await apiFetch(url('/api/jobs/discovery'), { method: 'POST' }))
}

export async function scoreJobOnDemand(
  payload: import('../types').ScoreJobRequest,
): Promise<import('../types').ScoreJobResponse> {
  const res = await apiFetch(url('/api/jobs/score'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return handle<import('../types').ScoreJobResponse>(res)
}

/* ---- Swipe deck, consent log and pipeline board ----
   All of these act for the logged-in account (the session cookie); the API ignores
   any candidate handle, so none is sent. */

export async function getDeck(limit = 20, minLegitimacy = 0.6): Promise<DeckResponse> {
  const params = new URLSearchParams({ limit: String(limit), min_legitimacy: String(minLegitimacy) })
  return handle<DeckResponse>(await apiFetch(url(`/api/applications/deck?${params.toString()}`)))
}

export async function swipeJob(jobId: string, direction: 'left' | 'right', purpose?: string): Promise<SwipeResponse> {
  const res = await apiFetch(url('/api/applications/swipe'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId, direction, purpose: purpose || null }),
  })
  return handle<SwipeResponse>(res)
}

export async function getBoard(): Promise<BoardResponse> {
  return handle<BoardResponse>(await apiFetch(url('/api/applications/board')))
}

export async function getConsentReceipt(applicationId: string): Promise<ConsentReceipt> {
  return handle<ConsentReceipt>(await apiFetch(url(`/api/applications/${encodeURIComponent(applicationId)}/consent`)))
}

export async function moveApplicationStage(
  applicationId: string,
  toStage: PipelineStage,
  detail?: string,
): Promise<ApplicationCard> {
  const res = await apiFetch(url(`/api/applications/${encodeURIComponent(applicationId)}/stage`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to_stage: toStage, detail: detail || null }),
  })
  return handle<ApplicationCard>(res)
}

// With no messages the API reads the connected mailbox; with messages it replays them.
export async function syncRecruiterMail(messages?: RecruiterMessage[]): Promise<MailSyncResponse> {
  const res = await apiFetch(url('/api/mail/sync'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(messages && messages.length ? { messages } : {}),
  })
  return handle<MailSyncResponse>(res)
}

export interface OutreachDraft {
  email_subject: string
  email_body: string
  linkedin_note: string
  highlights_used: string[]
  find_recruiter_url: string
  company_careers_url: string | null
}

// A note to the people hiring, written from the approved profile. Never sent by Hire.
export async function draftOutreach(jobId: string, note?: string, versionId?: number | null): Promise<OutreachDraft> {
  const res = await apiFetch(url(`/api/jobs/${encodeURIComponent(jobId)}/outreach`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note: note?.trim() || null, version_id: versionId ?? null }),
  })
  return handle<OutreachDraft>(res)
}

export async function getMailStatus(): Promise<{ connected: boolean }> {
  return handle(await apiFetch(url('/api/mail/status')))
}

// The candidate applied on the employer's site (or takes that back).
export async function markSubmitted(applicationId: string, sent = true): Promise<ApplicationCard> {
  const res = await apiFetch(url(`/api/applications/${encodeURIComponent(applicationId)}/submission`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sent }),
  })
  return handle<ApplicationCard>(res)
}

/* ---- Auto-fill: Hire fills the employer's form; the user reviews and confirms ---- */

export interface ApplyRun {
  id: number
  status: 'queued' | 'filling' | 'needs_answers' | 'ready_to_submit' | 'submit_requested' | 'submitting' | 'submitted' | 'failed' | 'captcha' | 'cancelled' | 'unconfirmed'
  step: string | null
  filled: { label: string; shown: string; source: string; required: boolean }[]
  missing: { label: string; field: string | null; type: string | null; options: string[] }[]
  error: string | null
  has_screenshot: boolean
  company: string
  role: string
}

const autofill = (id: string, path = '') => url(`/api/applications/${encodeURIComponent(id)}/autofill${path}`)

async function postJson<T>(target: string, body?: unknown): Promise<T> {
  return handle<T>(
    await apiFetch(target, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  )
}

export const startAutofill = (id: string) => postJson<ApplyRun>(autofill(id))
export const getAutofill = async (id: string): Promise<ApplyRun | null> => handle(await apiFetch(autofill(id)))
export const answerAutofill = (id: string, answers: Record<string, string>) => postJson<ApplyRun>(autofill(id, '/answers'), { answers })
export const confirmAutofill = (id: string, companyName: string) => postJson<ApplyRun>(autofill(id, '/submit'), { company_name: companyName })
export const cancelAutofill = (id: string) => postJson<ApplyRun>(autofill(id, '/cancel'))
export const autofillScreenshotUrl = (id: string, version: number | string) => `${autofill(id, '/screenshot')}?v=${version}`
