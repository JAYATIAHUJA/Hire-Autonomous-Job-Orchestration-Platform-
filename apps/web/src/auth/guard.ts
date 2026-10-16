import type { Me } from '../api/v1types'
import { needsConsent } from '../privacy/consent'

export type AuthState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'anonymous' }
  | { status: 'authenticated'; me: Me }

// Which kind of page is being opened.
export type RouteKind = 'login' | 'onboarding' | 'app'

export type GuardDecision = { kind: 'wait' } | { kind: 'error'; message: string } | { kind: 'allow' } | { kind: 'redirect'; to: string }

export const LOGIN_PATH = '/login'
export const ONBOARDING_PATH = '/onboarding'
export const HOME_PATH = '/' // the home dashboard: it points the user at their next step

export function onboardingComplete(me: Me): boolean {
  return !needsConsent(me) && Boolean(me.onboarding_completed_at)
}

export type RouteContext = {
  path?: string // the page being opened, path + search
  next?: string | null // ?next= on the login page
}

// Logged out -> /login (remembering where the user was going); consent or
// onboarding outstanding -> /onboarding; otherwise the app. A newer notice
// version sends a finished user back through the consent step.
export function decideRoute(auth: AuthState, route: RouteKind, ctx: RouteContext = {}): GuardDecision {
  if (auth.status === 'loading') return { kind: 'wait' }
  if (auth.status === 'error') return { kind: 'error', message: auth.message }
  if (auth.status === 'anonymous') {
    if (route === 'login') return { kind: 'allow' }
    const next = route === 'app' ? safeNextPath(ctx.path) : null
    return { kind: 'redirect', to: next ? `${LOGIN_PATH}?${new URLSearchParams({ next }).toString()}` : LOGIN_PATH }
  }

  const done = onboardingComplete(auth.me)
  if (route === 'login') return { kind: 'redirect', to: done ? (safeNextPath(ctx.next) ?? HOME_PATH) : ONBOARDING_PATH }
  if (route === 'onboarding') return done ? { kind: 'redirect', to: HOME_PATH } : { kind: 'allow' }
  return done ? { kind: 'allow' } : { kind: 'redirect', to: ONBOARDING_PATH }
}

// Only same-app paths are honoured as a post-login destination, so a crafted
// ?next= cannot bounce the user to another site.
export function safeNextPath(next: string | null | undefined): string | null {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) return null
  if (next === LOGIN_PATH || next.startsWith(`${LOGIN_PATH}?`)) return null
  return next
}
