import { ApiError } from './client'
import type { AccountApi } from './account'
import type { AnswerBank, ConsentRecord, FactProposal, Me, OnlinePresence, PowRun, Preferences } from './v1types'

// In-browser stand-in for the /v1 endpoints, enabled with VITE_USE_MOCKS=1.
// State lives in localStorage so a reload keeps the mock session. Dev only:
// nothing here is ever sent anywhere.
//
// Email OTP: any address, code 123456. Five wrong codes lock the address.

export const MOCK_OTP_CODE = '123456'
const STORAGE_KEY = 'hire.mock.v1'
const OTP_TRIES = 5
const POW_RUN_MS = 8000
const LATENCY_MS = 250

type MockState = {
  presence?: OnlinePresence
  me: Me | null
  otpTries: Record<string, number>
  powRun: { id: string; startedAt: number } | null
  preferences: Preferences | null
  answers: AnswerBank
}

const EMPTY: MockState = { me: null, otpTries: {}, powRun: null, preferences: null, answers: {} }

function load(): MockState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as Partial<MockState>) } : { ...EMPTY }
  } catch {
    return { ...EMPTY }
  }
}

function save(state: MockState) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Private browsing: the mock session lasts until reload.
  }
}

function update(fn: (state: MockState) => void): MockState {
  const state = load()
  fn(state)
  save(state)
  return state
}

const delay = <T>(value: T): Promise<T> => new Promise((resolve) => window.setTimeout(() => resolve(value), LATENCY_MS))

function requireMe(state: MockState): Me {
  if (!state.me) throw new ApiError('Not logged in', 401)
  return state.me
}

function newAccount(email: string | null, provider: Me['identities'][number]): Me {
  return {
    id: `acct_${Math.random().toString(36).slice(2, 10)}`,
    email,
    display_name: email ? email.split('@')[0] : 'octocat',
    role: 'user',
    identities: [provider],
    consent: null,
    onboarding_completed_at: null,
  }
}

const PROPOSALS: FactProposal[] = [
  { id: 'f1', kind: 'experience', text: 'Software Engineer at Acme Fintech, Bengaluru (Jun 2021 - present)', source: 'resume' },
  { id: 'f2', kind: 'education', text: 'B.Tech, Computer Science, VIT Vellore (2017 - 2021)', source: 'resume' },
  { id: 'f3', kind: 'skill', text: 'TypeScript', source: 'resume' },
  { id: 'f4', kind: 'skill', text: 'Kafka (used in payments pipeline)', source: 'resume', inferred: true },
  {
    id: 'f5',
    kind: 'identity',
    text: 'Location: Pune, India',
    source: 'resume',
    conflict_with: { id: 'old-1', text: 'Location: Bengaluru, India' },
  },
  {
    id: 'f6',
    kind: 'experience',
    text: 'Led a team of 4 engineers at Acme Fintech',
    source: 'resume',
    inferred: true,
    conflict_with: { id: 'old-2', text: 'Individual contributor at Acme Fintech' },
  },
]

export const mockAccountApi: AccountApi = {
  getMe: async () => delay(load().me),

  async sendOtp(email) {
    if (!email.includes('@')) throw new ApiError('Enter a valid email address.', 422)
    update((s) => {
      s.otpTries[email.toLowerCase()] = 0
    })
    return delay({ resend_after: 30 })
  },

  async verifyOtp(email, code) {
    const key = email.toLowerCase()
    const state = load()
    const tries = state.otpTries[key] ?? 0
    if (tries >= OTP_TRIES) throw new ApiError('Too many attempts. Request a new code.', 429)
    if (code !== MOCK_OTP_CODE) {
      update((s) => {
        s.otpTries[key] = tries + 1
      })
      await delay(null)
      throw new ApiError('That code is incorrect or has expired.', 400)
    }
    const next = update((s) => {
      delete s.otpTries[key]
      s.me = s.me && s.me.email === email ? s.me : newAccount(email, 'email')
    })
    return delay(next.me!)
  },

  // There is no OAuth provider in mock mode: the "start" URL logs the user in
  // locally and lands them where they were going.
  oauthStartUrl(provider, returnTo) {
    update((s) => {
      if (!s.me) s.me = newAccount(provider === 'google' ? 'mock.user@gmail.com' : null, provider)
      else if (!s.me.identities.includes(provider)) s.me.identities.push(provider)
    })
    return returnTo
  },

  async logout() {
    update((s) => {
      s.me = null
      s.powRun = null
    })
    await delay(null)
  },

  async recordConsent(body) {
    const record: ConsentRecord = { ...body, accepted_at: new Date().toISOString() }
    update((s) => {
      requireMe(s).consent = record
    })
    return delay(record)
  },

  async completeOnboarding() {
    const state = update((s) => {
      requireMe(s).onboarding_completed_at = new Date().toISOString()
    })
    return delay(state.me!)
  },

  async startPowRefresh() {
    const state = update((s) => {
      const me = requireMe(s)
      if (!me.consent?.purposes.github) throw new ApiError('GitHub analysis needs your consent.', 403)
      if (!s.powRun) s.powRun = { id: `run_${Date.now()}`, startedAt: Date.now() }
    })
    return mockAccountApi.getPowRun(state.powRun!.id)
  },

  async getPowRun(id) {
    const run = load().powRun
    if (!run || run.id !== id) throw new ApiError('Run not found', 404)
    const progress = Math.min(100, Math.round(((Date.now() - run.startedAt) / POW_RUN_MS) * 100))
    const result: PowRun = {
      id,
      status: progress >= 100 ? 'done' : progress < 10 ? 'queued' : 'running',
      progress,
      sample_coverage: progress >= 10 ? { sampled_commits: Math.round(6.4 * progress), total_commits: 2100 } : null,
    }
    return delay(result)
  },

  async getLatestPowRun() {
    const run = load().powRun
    return run ? mockAccountApi.getPowRun(run.id) : delay(null)
  },

  getProfile: async () =>
    delay({
      profile: {
        identity: { name: { value: 'Priya Sharma' }, location: { value: 'Bengaluru, India' }, links: [] },
        experience: [{ text: PROPOSALS[0].text }],
        education: [{ text: PROPOSALS[1].text }],
        skills: [{ text: 'TypeScript' }],
        preferences: load().preferences ?? undefined,
      },
      pending_proposals: [],
      updated_at: new Date().toISOString(),
    }),

  getPreferences: async () => delay(load().preferences),

  listVersions: async () => delay([]),
  saveVersion: async (v, id) => delay({ ...v, id: id ?? Date.now() }),
  deleteVersion: async () => delay(undefined),

  getPresence: async () =>
    delay(
      load().presence ?? { github_username: null, github_token_saved: false, linkedin: null, website: null, portfolio: null, others: [] },
    ),

  async savePresence(changes) {
    const { github_token, clear_github_token, ...links } = changes
    const state = update((s) => {
      const before = s.presence?.github_token_saved ?? false
      s.presence = { ...links, github_token_saved: clear_github_token ? false : Boolean(github_token) || before }
    })
    return delay(state.presence!)
  },

  async uploadResume(file) {
    if (!requireMe(load()).consent?.purposes.resume) throw new ApiError('Resume parsing needs your consent.', 403)
    if (file.size > 5 * 1024 * 1024) throw new ApiError('Resume must be 5 MB or smaller.', 413)
    return delay({ proposals: PROPOSALS })
  },

  approveFacts: async () => delay(undefined),
  rejectFacts: async () => delay(undefined),
  addFact: async (kind, text, structured = {}) =>
    delay({ id: `f_${Date.now()}`, kind, text, source: 'user_confirmed', status: 'approved', structured: structured as Record<string, string> }),
  editFact: async (id, change) =>
    delay({ id, kind: 'skill', text: change.text ?? '', source: 'resume', status: 'approved', structured: {} }),

  async savePreferences(prefs) {
    update((s) => {
      s.preferences = prefs
    })
    await delay(null)
  },

  getAnswerBank: async () => delay(load().answers),

  async saveAnswerBank(answers) {
    update((s) => {
      s.answers = answers
    })
    await delay(null)
  },

  listAnswerMemory: async () => delay([]),

  async deleteAnswerMemory() {
    await delay(null)
  },
}
