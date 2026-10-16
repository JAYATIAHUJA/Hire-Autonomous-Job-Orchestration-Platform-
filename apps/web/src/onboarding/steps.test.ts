import { describe, expect, it } from 'vitest'
import type { FactProposal, Me } from '../api/v1types'
import { NOTICE_VERSION } from '../privacy/notice'
import { conflictText, coverageLabel, defaultSelection, initialStep, nextStep, splitList, splitProposals, stepsFor } from './steps'

const purposes = (github: boolean, resume: boolean) => ({ github, resume, email: false })

function me(consented: { github: boolean; resume: boolean } | null, version = NOTICE_VERSION): Me {
  return {
    id: 'a1',
    email: null,
    display_name: null,
    role: 'user',
    identities: ['github'],
    consent: consented
      ? { notice_version: version, notice_hash: 'h', purposes: { ...consented, email: false }, accepted_at: 't' }
      : null,
    onboarding_completed_at: null,
  }
}

describe('stepsFor', () => {
  it('only includes GitHub and resume steps the user consented to', () => {
    expect(stepsFor(purposes(false, false))).toEqual(['consent', 'preferences', 'answers'])
    expect(stepsFor(purposes(true, false))).toEqual(['consent', 'github', 'preferences', 'answers'])
    expect(stepsFor(purposes(false, true))).toEqual(['consent', 'resume', 'facts', 'preferences', 'answers'])
    expect(stepsFor(purposes(true, true))).toHaveLength(6)
  })
})

describe('initialStep', () => {
  it('starts at the notice without a current consent', () => {
    expect(initialStep(me(null), 'answers')).toBe('consent')
    expect(initialStep(me({ github: true, resume: true }, 'v0'), 'answers')).toBe('consent')
  })

  it('resumes a saved step only if it still applies', () => {
    expect(initialStep(me({ github: true, resume: true }), 'facts')).toBe('facts')
    expect(initialStep(me({ github: false, resume: false }), 'github')).toBe('preferences')
    expect(initialStep(me({ github: true, resume: false }), null)).toBe('github')
    expect(initialStep(me({ github: true, resume: false }), 'consent')).toBe('github')
  })
})

describe('nextStep', () => {
  it('walks the list and ends with null', () => {
    const steps = stepsFor(purposes(false, false))
    expect(nextStep(steps, 'consent')).toBe('preferences')
    expect(nextStep(steps, 'answers')).toBeNull()
  })
})

describe('fact proposals', () => {
  const proposals: FactProposal[] = [
    { id: '1', kind: 'skill', text: 'Go', source: 'resume' },
    { id: '2', kind: 'skill', text: 'Kafka', source: 'resume', inferred: true },
    { id: '3', kind: 'identity', text: 'Pune', source: 'resume', conflict_with: { id: 'x', text: 'Bengaluru' } },
    { id: '4', kind: 'identity', text: 'B', source: 'resume', conflict_with: 'fact-9' },
  ]

  it('splits additive proposals from conflicts', () => {
    const { additive, conflicts } = splitProposals(proposals)
    expect(additive.map((p) => p.id)).toEqual(['1', '2'])
    expect(conflicts.map((p) => p.id)).toEqual(['3', '4'])
  })

  it('leaves inferred facts unticked', () => {
    expect([...defaultSelection(splitProposals(proposals).additive)]).toEqual(['1'])
  })

  it('describes what a conflict contradicts', () => {
    expect(conflictText(proposals[2])).toBe('Bengaluru')
    expect(conflictText(proposals[3])).toBe('a fact already in your profile')
  })
})

describe('labels', () => {
  it('formats sample coverage', () => {
    expect(coverageLabel({ sampled_commits: 640, total_commits: 2100 })).toBe('Based on 640 of 2,100 commits')
    expect(coverageLabel(null)).toBeNull()
  })

  it('splits comma or newline lists', () => {
    expect(splitList(' Backend, SRE\nPlatform ,, ')).toEqual(['Backend', 'SRE', 'Platform'])
  })
})
