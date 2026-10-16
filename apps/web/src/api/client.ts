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

export async function getJobFeed(
  limit: number = 20,
  page: number = 1,
  minLegitimacy: number = 0.6,
): Promise<import('../types').JobFeedResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    page: String(page),
    min_legitimacy: String(minLegitimacy),
  })
  return handle<import('../types').JobFeedResponse>(await apiFetch(url(`/api/jobs/feed?${params.toString()}`)))
}

export async function getJobDetail(jobId: string): Promise<import('../types').JobContract> {
  return handle<import('../types').JobContract>(await apiFetch(url(`/api/jobs/${encodeURIComponent(jobId)}`)))
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

/* ---- Objective 3: swipe deck, consent log and pipeline board ---- */

export async function getDeck(candidateRef: string, limit = 20, minLegitimacy = 0.6): Promise<DeckResponse> {
  const params = new URLSearchParams({
    candidate_ref: candidateRef,
    limit: String(limit),
    min_legitimacy: String(minLegitimacy),
  })
  return handle<DeckResponse>(await apiFetch(url(`/api/applications/deck?${params.toString()}`)))
}

export async function swipeJob(
  jobId: string,
  direction: 'left' | 'right',
  candidateRef: string,
  purpose?: string,
): Promise<SwipeResponse> {
  const res = await apiFetch(url('/api/applications/swipe'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId, direction, candidate_ref: candidateRef, purpose: purpose || null }),
  })
  return handle<SwipeResponse>(res)
}

export async function getBoard(candidateRef: string): Promise<BoardResponse> {
  const params = new URLSearchParams({ candidate_ref: candidateRef })
  return handle<BoardResponse>(await apiFetch(url(`/api/applications/board?${params.toString()}`)))
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

export async function syncRecruiterMail(candidateRef: string, messages?: RecruiterMessage[]): Promise<MailSyncResponse> {
  // Replies may only move this candidate's cards, so the API requires whose board it is.
  const res = await apiFetch(url('/api/mail/sync'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(messages && messages.length ? { messages, candidate_ref: candidateRef } : {}),
  })
  return handle<MailSyncResponse>(res)
}
