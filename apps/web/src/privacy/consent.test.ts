import { createHash } from 'node:crypto'
import { describe, expect, it } from 'vitest'
import { buildConsentRequest, grantedPurposes, needsConsent, NO_PURPOSES, PURPOSES, sha256Hex } from './consent'
import { GRIEVANCE_CONTACT, NOTICE_SECTIONS, NOTICE_VERSION, noticeText } from './notice'

describe('notice', () => {
  it('serialises the rendered sections into the hashed text', () => {
    const text = noticeText()
    expect(text.startsWith(`How Hire uses your personal data\nVersion ${NOTICE_VERSION}\n\n`)).toBe(true)
    for (const section of NOTICE_SECTIONS) {
      expect(text).toContain(section.heading)
      for (const line of section.paragraphs ?? []) expect(text).toContain(line)
      for (const item of section.items ?? []) expect(text).toContain(`- ${item}`)
    }
  })

  it('covers the rights DPDP requires, including the grievance contact', () => {
    const text = noticeText()
    for (const word of ['Access', 'Correct', 'Erase', 'Withdraw consent', 'Grievance Officer', 'Data Protection Board']) {
      expect(text).toContain(word)
    }
    expect(text).toContain(GRIEVANCE_CONTACT)
  })
})

describe('consent', () => {
  it('starts with every purpose off', () => {
    expect(NO_PURPOSES).toEqual({ github: false, resume: false, email: false })
    expect(PURPOSES.map((p) => p.key)).toEqual(['github', 'resume', 'email'])
  })

  it('hashes the exact notice text with sha256', async () => {
    const expected = createHash('sha256').update(noticeText(), 'utf8').digest('hex')
    expect(await sha256Hex(noticeText())).toBe(expected)
    expect(await sha256Hex('abc')).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  })

  it('builds the request from the current version and a copy of the toggles', async () => {
    const purposes = { github: true, resume: false, email: false }
    const req = await buildConsentRequest(purposes)
    expect(req).toEqual({
      notice_version: NOTICE_VERSION,
      notice_hash: createHash('sha256').update(noticeText()).digest('hex'),
      purposes,
    })
    purposes.github = false
    expect(req.purposes.github).toBe(true)
  })

  it('a different notice text gives a different hash', async () => {
    const a = await buildConsentRequest(NO_PURPOSES, noticeText())
    const b = await buildConsentRequest(NO_PURPOSES, `${noticeText()} `)
    expect(a.notice_hash).not.toBe(b.notice_hash)
  })

  it('asks again when the accepted version is missing or stale', () => {
    const record = { notice_version: NOTICE_VERSION, notice_hash: 'h', purposes: { github: true, resume: true, email: false }, accepted_at: 't' }
    expect(needsConsent({ consent: null })).toBe(true)
    expect(needsConsent({ consent: { ...record, notice_version: 'v0' } })).toBe(true)
    expect(needsConsent({ consent: record })).toBe(false)
    expect(grantedPurposes(record)).toEqual({ github: true, resume: true, email: false })
    expect(grantedPurposes({ ...record, notice_version: 'v0' })).toEqual(NO_PURPOSES)
    expect(grantedPurposes(null)).toEqual(NO_PURPOSES)
  })
})
