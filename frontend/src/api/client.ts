import type { AnalyzeResponse, Profile } from '../types'

const BASE_URL = '/api/profile'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
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
  const res = await fetch(`${BASE_URL}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, token: token || null }),
  })
  return handle<AnalyzeResponse>(res)
}

export async function getProfile(profileId: string): Promise<Profile> {
  return handle<Profile>(await fetch(`${BASE_URL}/${encodeURIComponent(profileId)}`))
}
