import { useEffect, useRef, useState } from 'react'
import { accountApi } from '../api/account'
import type { FactProposal, Me } from '../api/v1types'
import { useAuth } from '../auth/AuthContext'
import AnswersStep from '../onboarding/AnswersStep'
import ConsentStep from '../onboarding/ConsentStep'
import FactsStep from '../onboarding/FactsStep'
import GithubStep from '../onboarding/GithubStep'
import PreferencesStep from '../onboarding/PreferencesStep'
import ResumeStep from '../onboarding/ResumeStep'
import { initialStep, nextStep, STEP_LABELS, stepsFor, type StepId } from '../onboarding/steps'
import { grantedPurposes } from '../privacy/consent'

const stepKey = (accountId: string) => `hire.onboarding.step.${accountId}`

function readSaved(accountId: string): string | null {
  try {
    return window.localStorage.getItem(stepKey(accountId))
  } catch {
    return null
  }
}

function writeSaved(accountId: string, step: StepId) {
  try {
    window.localStorage.setItem(stepKey(accountId), step)
  } catch {
    // Private browsing: a reload restarts after the notice.
  }
}

// Only rendered for a signed-in user whose onboarding is unfinished (RouteGuard).
export default function OnboardingPage() {
  const { auth, setMe } = useAuth()
  const me = auth.status === 'authenticated' ? auth.me : null
  if (!me) return null
  return <Wizard me={me} setMe={setMe} />
}

function Wizard({ me, setMe }: { me: Me; setMe: (me: Me) => void }) {
  const [step, setStep] = useState<StepId>(() => initialStep(me, readSaved(me.id)))
  const [proposals, setProposals] = useState<FactProposal[]>([])
  const headingRef = useRef<HTMLHeadingElement>(null)
  const firstRender = useRef(true)
  const steps = stepsFor(grantedPurposes(me.consent))
  const index = steps.indexOf(step)

  useEffect(() => {
    writeSaved(me.id, step)
    // Move keyboard and screen-reader focus to the new step's heading.
    if (firstRender.current) firstRender.current = false
    else headingRef.current?.focus()
  }, [me.id, step])

  function advance(from: StepId = step, list: StepId[] = steps) {
    const next = nextStep(list, from)
    if (next) setStep(next)
  }

  async function finish() {
    const updated = await accountApi.completeOnboarding()
    try {
      window.localStorage.removeItem(stepKey(me.id))
    } catch {
      // Nothing to clean up.
    }
    // The route guard sends a finished user to the deck.
    setMe(updated)
  }

  let body
  switch (step) {
    case 'consent':
      body = (
        <ConsentStep
          me={me}
          onAccepted={(updated) => {
            setMe(updated)
            advance('consent', stepsFor(grantedPurposes(updated.consent)))
          }}
        />
      )
      break
    case 'github':
      body = <GithubStep me={me} onNext={() => advance()} />
      break
    case 'resume':
      body = (
        <ResumeStep
          onUploaded={(found) => {
            setProposals(found)
            advance()
          }}
          // Skipping the upload skips the review too.
          onSkip={() => advance('facts')}
        />
      )
      break
    case 'facts':
      body = <FactsStep proposals={proposals} onNext={() => advance()} />
      break
    case 'preferences':
      body = <PreferencesStep onNext={() => advance()} />
      break
    case 'answers':
      body = <AnswersStep onDone={finish} />
      break
  }

  return (
    <section className="onboarding-page">
      <ol className="step-dots" aria-label="Onboarding progress">
        {steps.map((s, i) => (
          <li key={s} className={i < index ? 'done' : i === index ? 'current' : ''} aria-current={s === step ? 'step' : undefined}>
            <span className="visually-hidden">
              {STEP_LABELS[s]}
              {i < index ? ' (done)' : ''}
            </span>
          </li>
        ))}
      </ol>
      <p className="step-count muted">
        Step {index + 1} of {steps.length}
      </p>
      <h1 ref={headingRef} tabIndex={-1} className="step-title">
        {STEP_LABELS[step]}
      </h1>
      <div className="card onboarding-card">{body}</div>
    </section>
  )
}
