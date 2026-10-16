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
  github_username?: string | null
  // Set once the run is done: the analysed profile at GET /api/profile/{profile_id}.
  profile_id?: number | null
  finished_at?: string | null
}

// One approved fact as it sits in the assembled profile document.
export type ProfileEntry = { text?: string; fact_id?: string; inferred?: boolean; [field: string]: unknown }

export type Bullet = { text: string; fact_id: string; inferred?: boolean }

export type ExperienceEntry = ProfileEntry & {
  company?: string | null
  title?: string | null
  start?: string | null
  end?: string | null
  bullets?: Bullet[]
}

// A fact as the API returns it after an add or an edit.
export type Fact = FactProposal & { status: string; structured: Record<string, string> }

export type FactFields = Partial<Record<'company' | 'title' | 'start_date' | 'end_date' | 'institution' | 'degree' | 'name' | 'url', string | null>>

// GET /v1/profile: the profile built from approved facts only, plus proposals awaiting review.
export type CandidateProfile = {
  profile: {
    identity?: {
      name?: { value: string; fact_id?: string } | null
      email?: { value: string; fact_id?: string } | null
      phone?: { value: string; fact_id?: string } | null
      location?: { value: string; fact_id?: string } | null
      links?: ProfileEntry[]
    }
    experience?: ExperienceEntry[]
    education?: ProfileEntry[]
    projects?: ProfileEntry[]
    skills?: ProfileEntry[]
    certifications?: ProfileEntry[]
    achievements?: ProfileEntry[]
    languages?: ProfileEntry[]
    work_authorization?: ProfileEntry[]
    preferences?: Partial<Preferences>
  }
  pending_proposals: FactProposal[]
  updated_at: string | null
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
  skipped_duplicates?: number
  // Approved facts this resume leaves out: kept, shown so the user can drop any.
  kept_from_before?: FactProposal[]
}

// What several resumes uploaded together added up to.
export type ResumeMerge = { proposals: FactProposal[]; alreadyHad: number; kept: FactProposal[]; files: number }

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

// GET/PUT /v1/me/online-presence. The GitHub token is write-only: the API only says
// whether one is saved.
export type OtherLink = { label: string; url: string }

export type OnlinePresence = {
  github_username: string | null
  github_token_saved: boolean
  // Nothing saved yet: the links were found in the resume, for the user to check.
  from_resume?: boolean
  linkedin: string | null
  website: string | null
  portfolio: string | null
  others: OtherLink[]
}

export type OnlinePresenceUpdate = Omit<OnlinePresence, 'github_token_saved' | 'from_resume'> & {
  github_token?: string | null
  clear_github_token?: boolean
}

// GET/POST /v1/profile/versions: a targeted cut of the master profile.
export type ProfileVersion = {
  id: number
  name: string
  headline: string | null
  target_role: string | null
  fact_ids: string[]
  updated_at?: string | null
}

export type ProfileVersionInput = Omit<ProfileVersion, 'id' | 'updated_at'>
