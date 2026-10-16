// Shapes of the /v1 account, onboarding and profile endpoints (PLAN s7).
// WP1 (auth), WP2 (PoW runs) and WP6 (facts) own the server side; fields marked
// "not agreed" are this client's conservative guess and are listed as open
// questions in the WP5 PR.

export type AuthProvider = 'github' | 'google' | 'email'

export type AccountRole = 'user' | 'admin' | 'support'

export type ConsentPurposes = {
  github: boolean
  resume: boolean
  email: boolean
}

// What the user accepted: the notice version, the sha256 of its exact text, and
// one switch per purpose.
export type ConsentRecord = {
  notice_version: string
  notice_hash: string
  purposes: ConsentPurposes
  accepted_at: string
}

// POST /v1/me/consents (not agreed).
export type ConsentRequest = Omit<ConsentRecord, 'accepted_at'>

// GET /v1/me. `identities`, `consent` and `onboarding_completed_at` are not agreed.
export type Me = {
  id: string
  email: string | null
  display_name: string | null
  role: AccountRole
  identities: AuthProvider[]
  consent: ConsentRecord | null
  onboarding_completed_at: string | null
}

export type OtpSendResponse = {
  // Seconds before another code may be requested (not agreed; default 30).
  resend_after?: number
}

export type PowRunStatus = 'queued' | 'running' | 'done' | 'failed'

export type SampleCoverage = {
  sampled_commits: number
  total_commits: number
}

export type PowRun = {
  id: string
  status: PowRunStatus
  progress: number
  sample_coverage: SampleCoverage | null
  error?: string | null
}

export type FactKind = string

export type FactProposal = {
  id: string
  kind: FactKind
  text: string
  source: string
  // The approved fact this proposal contradicts. Agreed only as `conflict_with?`;
  // the client accepts either a fact id or {id, text}.
  conflict_with?: string | { id: string; text: string } | null
  // WP6 labels inferences; not in the agreed shape yet.
  inferred?: boolean
}

export type ResumeUploadResponse = {
  proposals: FactProposal[]
}

export type ExperienceBand = '0-1' | '1-3' | '3-5' | '5-8' | '8-12' | '12+'

export type Preferences = {
  roles: string[]
  locations: string[]
  remote_ok: boolean
  experience_band: ExperienceBand | null
  salary_floor: { amount: number; currency: 'INR' | 'USD'; period: 'year' } | null
  deal_breakers: string[]
}

// GET/PUT /v1/me/answer-bank. The answer bank is key/value (WP6 answer_bank);
// the wire shape {answers: {key: value}} is not agreed.
export type AnswerBank = Record<string, string>
