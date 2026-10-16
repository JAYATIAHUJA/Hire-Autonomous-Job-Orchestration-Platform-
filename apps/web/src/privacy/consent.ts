import type { ConsentPurposes, ConsentRecord, ConsentRequest, Me } from '../api/v1types'
import { NOTICE_VERSION, noticeText } from './notice'

// Every optional purpose starts off: consent must be an affirmative act.
export const NO_PURPOSES: ConsentPurposes = { github: false, resume: false, email: false }

export const PURPOSES: { key: keyof ConsentPurposes; label: string; detail: string }[] = [
  {
    key: 'github',
    label: 'Analyse my GitHub',
    detail: 'Read my public repositories, commits and pull requests to build my proof-of-work profile.',
  },
  {
    key: 'resume',
    label: 'Parse my resume',
    detail: 'Read the resume I upload and suggest profile facts for me to approve.',
  },
  {
    key: 'email',
    label: 'Email ingest (coming later)',
    detail: 'Read recruiter replies in a mailbox I connect. Not available yet; this only records my choice.',
  },
]

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
}

export async function buildConsentRequest(purposes: ConsentPurposes, text: string = noticeText()): Promise<ConsentRequest> {
  return { notice_version: NOTICE_VERSION, notice_hash: await sha256Hex(text), purposes: { ...purposes } }
}

// The user has to see the current notice again when they never accepted one, or
// accepted an older version.
export function needsConsent(me: Pick<Me, 'consent'>): boolean {
  return !me.consent || me.consent.notice_version !== NOTICE_VERSION
}

export function grantedPurposes(consent: ConsentRecord | null): ConsentPurposes {
  if (!consent || consent.notice_version !== NOTICE_VERSION) return { ...NO_PURPOSES }
  return { ...NO_PURPOSES, ...consent.purposes }
}
