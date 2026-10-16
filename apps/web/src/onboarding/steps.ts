import type { ConsentPurposes, FactProposal, Me, SampleCoverage } from '../api/v1types'
import { grantedPurposes, needsConsent } from '../privacy/consent'

export type StepId = 'consent' | 'github' | 'resume' | 'facts' | 'preferences' | 'answers'

export const STEP_LABELS: Record<StepId, string> = {
  consent: 'Privacy notice',
  github: 'Connect GitHub',
  resume: 'Upload resume',
  facts: 'Review facts',
  preferences: 'Preferences',
  answers: 'Standard answers',
}

// A step that needs a purpose only appears when the user switched that purpose
// on: no consent, no GitHub analysis and no resume parsing.
export function stepsFor(purposes: ConsentPurposes): StepId[] {
  const steps: StepId[] = ['consent']
  if (purposes.github) steps.push('github')
  if (purposes.resume) steps.push('resume', 'facts')
  steps.push('preferences', 'answers')
  return steps
}

// Where to resume: the notice first whenever consent is outstanding, else the
// saved step if it still applies, else the first step after the notice.
export function initialStep(me: Me, saved: string | null): StepId {
  if (needsConsent(me)) return 'consent'
  const steps = stepsFor(grantedPurposes(me.consent))
  const found = steps.find((s) => s === saved)
  return found && found !== 'consent' ? found : steps[1]
}

export function nextStep(steps: StepId[], current: StepId): StepId | null {
  const i = steps.indexOf(current)
  return i >= 0 && i < steps.length - 1 ? steps[i + 1] : null
}

export function splitProposals(proposals: FactProposal[]): { additive: FactProposal[]; conflicts: FactProposal[] } {
  return {
    additive: proposals.filter((p) => !p.conflict_with),
    conflicts: proposals.filter((p) => Boolean(p.conflict_with)),
  }
}

// Inferred facts start unticked: the user has to opt each one in.
export function defaultSelection(additive: FactProposal[]): Set<string> {
  return new Set(additive.filter((p) => !p.inferred).map((p) => p.id))
}

export function conflictText(p: FactProposal): string {
  const c = p.conflict_with
  if (!c) return ''
  return typeof c === 'string' ? 'a fact already in your profile' : c.text
}

export function coverageLabel(coverage: SampleCoverage | null): string | null {
  if (!coverage || !coverage.total_commits) return null
  const fmt = (n: number) => n.toLocaleString('en-IN')
  return `Based on ${fmt(coverage.sampled_commits)} of ${fmt(coverage.total_commits)} commits`
}

export const splitList = (value: string): string[] =>
  value
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean)
