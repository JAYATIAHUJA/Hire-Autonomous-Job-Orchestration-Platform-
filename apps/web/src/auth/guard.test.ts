import { describe, expect, it } from 'vitest'
import type { Me } from '../api/v1types'
import { NOTICE_VERSION } from '../privacy/notice'
import { decideRoute, safeNextPath, type AuthState } from './guard'

const consent = { notice_version: NOTICE_VERSION, notice_hash: 'h', purposes: { github: false, resume: false, email: false }, accepted_at: 't' }

function me(overrides: Partial<Me> = {}): Me {
  return {
    id: 'a1',
    email: 'a@example.com',
    display_name: 'a',
    role: 'user',
    identities: ['email'],
    consent: null,
    onboarding_completed_at: null,
    ...overrides,
  }
}

const authed = (m: Me): AuthState => ({ status: 'authenticated', me: m })
const finished = me({ consent, onboarding_completed_at: '2026-10-16T00:00:00Z' })

describe('decideRoute', () => {
  it('waits while the session is loading and shows errors instead of logging out', () => {
    expect(decideRoute({ status: 'loading' }, 'app')).toEqual({ kind: 'wait' })
    expect(decideRoute({ status: 'error', message: 'offline' }, 'app')).toEqual({ kind: 'error', message: 'offline' })
  })

  it('sends a logged-out user to /login and remembers the page', () => {
    expect(decideRoute({ status: 'anonymous' }, 'app', { path: '/pipeline?x=1' })).toEqual({
      kind: 'redirect',
      to: '/login?next=%2Fpipeline%3Fx%3D1',
    })
    expect(decideRoute({ status: 'anonymous' }, 'onboarding')).toEqual({ kind: 'redirect', to: '/login' })
    expect(decideRoute({ status: 'anonymous' }, 'login')).toEqual({ kind: 'allow' })
  })

  it('sends a user without consent or unfinished onboarding to /onboarding', () => {
    expect(decideRoute(authed(me()), 'app')).toEqual({ kind: 'redirect', to: '/onboarding' })
    expect(decideRoute(authed(me({ consent })), 'app')).toEqual({ kind: 'redirect', to: '/onboarding' })
    // Finished before, but the notice changed: consent again first.
    const stale = me({ consent: { ...consent, notice_version: 'v0' }, onboarding_completed_at: 't' })
    expect(decideRoute(authed(stale), 'app')).toEqual({ kind: 'redirect', to: '/onboarding' })
    expect(decideRoute(authed(me()), 'onboarding')).toEqual({ kind: 'allow' })
    expect(decideRoute(authed(me()), 'login', { next: '/pipeline' })).toEqual({ kind: 'redirect', to: '/onboarding' })
  })

  it('lets a finished user into the app and keeps them out of login and onboarding', () => {
    expect(decideRoute(authed(finished), 'app')).toEqual({ kind: 'allow' })
    expect(decideRoute(authed(finished), 'onboarding')).toEqual({ kind: 'redirect', to: '/swipe' })
    expect(decideRoute(authed(finished), 'login')).toEqual({ kind: 'redirect', to: '/swipe' })
    expect(decideRoute(authed(finished), 'login', { next: '/pipeline' })).toEqual({ kind: 'redirect', to: '/pipeline' })
  })

  it('ignores an off-site ?next=', () => {
    expect(decideRoute(authed(finished), 'login', { next: '//evil.example' })).toEqual({ kind: 'redirect', to: '/swipe' })
  })
})

describe('safeNextPath', () => {
  it.each([
    ['/pipeline', '/pipeline'],
    ['/jobs?page=2', '/jobs?page=2'],
    ['https://evil.example', null],
    ['//evil.example', null],
    ['/\\evil.example', null],
    ['/login?next=/x', null],
    ['', null],
    [null, null],
  ])('%s -> %s', (input, expected) => {
    expect(safeNextPath(input)).toBe(expected)
  })
})
