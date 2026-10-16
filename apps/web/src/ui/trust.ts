import type { GhostJobMetricsContract } from '../types'

// The ghost filter in plain words. `legitimacy_probability` is the model's estimate
// that the company is actually hiring for this role right now.

export type TrustTone = 'good' | 'warn' | 'bad'

export function trustOf(metrics: Pick<GhostJobMetricsContract, 'legitimacy_probability' | 'risk_band'>): {
  label: string
  tone: TrustTone
  percent: number
} {
  const percent = Math.round(metrics.legitimacy_probability * 100)
  if (metrics.risk_band === 'High' || percent < 50) return { label: 'Likely a ghost job', tone: 'bad', percent }
  if (metrics.risk_band === 'Moderate' || percent < 75) return { label: 'Probably real', tone: 'warn', percent }
  return { label: 'Actively hiring', tone: 'good', percent }
}

// What each scorer signal means, for the "why we trust this" panel. Features are in [0, 1]
// but point different ways: age, reposts and layoff news are penalties (1 is worst), while
// description specificity and salary transparency are good signs (1 is best). `health`
// turns each into "how good is this" so every bar reads the same way.
type SignalKey = 'x_age' | 'x_repost' | 'x_quality' | 'x_salary' | 'x_news'

export const SIGNALS: { key: SignalKey; label: string; higherIsBetter: boolean }[] = [
  { key: 'x_age', label: 'Freshly posted', higherIsBetter: false },
  { key: 'x_repost', label: 'Not reposted over and over', higherIsBetter: false },
  { key: 'x_quality', label: 'Specific about the work and stack', higherIsBetter: true },
  { key: 'x_salary', label: 'Salary is disclosed', higherIsBetter: true },
  { key: 'x_news', label: 'No layoff news for the company', higherIsBetter: false },
]

export function health(value: number, higherIsBetter: boolean): number {
  const v = Math.max(0, Math.min(1, value))
  return Math.round((higherIsBetter ? v : 1 - v) * 100)
}
