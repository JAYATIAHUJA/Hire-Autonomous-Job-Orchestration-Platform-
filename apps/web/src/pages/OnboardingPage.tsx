import { useEffect, useRef, useState } from 'react'
import { accountApi } from '../api/account'
import PresenceForm from '../components/PresenceForm'
import ProfileEditor from '../components/ProfileEditor'
import Icon from '../ui/Icon'
import type { FactProposal, Me, ResumeMerge } from '../api/v1types'
import { useAuth } from '../auth/AuthContext'
import AnswersStep from '../onboarding/AnswersStep'
import ConsentStep from '../onboarding/ConsentStep'
import FactsStep from '../onboarding/FactsStep'
import PreferencesStep from '../onboarding/PreferencesStep'
import ResumeStep from '../onboarding/ResumeStep'
import { initialStep, nextStep, stepsFor, type StepId } from '../onboarding/steps'
import { grantedPurposes } from '../privacy/consent'
import { firstName, Meter } from '../ui/kit'

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

// What each step is called in the rail, and what the card says about it.
const STEP_INFO: Record<StepId, { rail: string; railSub: string; title: string; lede: string; why?: string }> = {
  consent: {
    rail: 'Privacy & permissions',
    railSub: 'What we use, and why',
    title: 'Your data, your call',
    lede: 'Read how Hire uses your data, then switch on only what you want. Steps for anything you leave off are skipped.',
  },
  polish: {
    rail: 'Polish your profile',
    railSub: 'Fix pointers, add what’s missing',
    title: 'Make it read the way you’d say it',
    lede: 'This is your profile as recruiters will see it. Fix any pointer, add projects and wins the resume missed, and delete what’s wrong.',
    why: 'Strong pointers say what you built and what changed because of it: “Cut checkout latency by 40% by moving pricing to Redis.”',
  },
  presence: {
    rail: 'Basics & links',
    railSub: 'Contact, GitHub, LinkedIn',
    title: 'How recruiters find and reach you',
    lede: 'Check your contact details and links. Anything we found in your resume is already filled in; add your GitHub token for proof from your code.',
    why: 'A GitHub token lets us read your real commits and pull requests, so your skills come with proof. It is optional, read-only, and stored encrypted.',
  },
  resume: {
    rail: 'Upload resume',
    railSub: 'Pull in your history',
    title: 'Start with your resume',
    lede: 'We read it and pull out everything we can: contact details, LinkedIn and GitHub links, roles, projects, achievements and skills. Nothing is saved until you approve it.',
    why: 'So you don’t type it all again. Every later step is prefilled from it, and you can fix anything along the way.',
  },
  facts: {
    rail: 'Review facts',
    railSub: 'Keep only what’s right',
    title: 'Check what we found',
    lede: 'Untick anything that is wrong. Only what you approve becomes part of your profile.',
  },
  preferences: {
    rail: 'Job preferences',
    railSub: 'What reaches your deck',
    title: 'What are you looking for?',
    lede: 'This decides which jobs are dealt into your deck. You can change it any time from your profile.',
  },
  answers: {
    rail: 'Standard answers',
    railSub: 'Answer once, reuse',
    title: 'Answer the usual questions once',
    lede: 'Notice period, CTC, relocation: every form asks. Answer once and we prefill them. You still review every form, and every answer is optional.',
  },
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
  const [merge, setMerge] = useState<ResumeMerge | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const firstRender = useRef(true)
  const steps = stepsFor(grantedPurposes(me.consent))
  const index = steps.indexOf(step)
  const info = STEP_INFO[step]
  const name = firstName(me.display_name, me.email)

  useEffect(() => {
    writeSaved(me.id, step)
    // Move keyboard and screen-reader focus to the new step's heading.
    if (firstRender.current) firstRender.current = false
    else {
      window.scrollTo({ top: 0, behavior: 'smooth' })
      headingRef.current?.focus()
    }
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
    // The route guard sends a finished user home.
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
    case 'polish':
      body = (
        <div className="form">
          <ProfileEditor />
          <div className="form-actions">
            <button type="button" className="btn btn-primary btn-lg" onClick={() => advance()}>
              Looks good, continue
              <Icon name="arrowRight" size={16} />
            </button>
          </div>
        </div>
      )
      break
    case 'presence':
      body = (
        <PresenceForm
          githubAllowed={grantedPurposes(me.consent).github}
          submitLabel="Save and continue"
          onSaved={(saved) => {
            // Start the proof-of-work analysis now; it runs in the background while the
            // user carries on, and Home and Profile show its progress.
            if (grantedPurposes(me.consent).github && saved.github_username) accountApi.startPowRefresh().catch(() => undefined)
            advance()
          }}
          onSkip={() => advance()}
        />
      )
      break
    case 'resume':
      body = (
        <ResumeStep
          onUploaded={(result) => {
            setProposals(result.proposals)
            setMerge(result)
            advance()
          }}
          // Skipping the upload skips the review too.
          onSkip={() => advance('facts')}
        />
      )
      break
    case 'facts':
      body = <FactsStep proposals={proposals} merge={merge} onNext={() => advance()} />
      break
    case 'preferences':
      body = <PreferencesStep onSaved={() => advance()} submitLabel="Save and continue" />
      break
    case 'answers':
      body = <AnswersStep onSaved={finish} submitLabel="Finish setup" />
      break
  }

  return (
    <div className="onb">
      <aside className="onb-rail" aria-label="Setup progress">
        <div className="onb-rail-head">
          <h2>{name ? `Welcome, ${name}` : 'Welcome to Hire'}</h2>
          <p>About three minutes. Your progress is saved, so you can leave and come back.</p>
        </div>
        <ol className="onb-steps">
          {steps.map((s, i) => (
            <li
              key={s}
              className={`onb-step${i < index ? ' done' : i === index ? ' current' : ''}`}
              aria-current={s === step ? 'step' : undefined}
            >
              <span className="onb-step-dot">{i < index ? <Icon name="check" size={12} stroke={3} /> : i + 1}</span>
              <span className="onb-step-text">
                <strong>{STEP_INFO[s].rail}</strong>
                <span>{STEP_INFO[s].railSub}</span>
              </span>
            </li>
          ))}
        </ol>
        <div className="onb-mobile-progress">
          <div className="row-between small" style={{ marginBottom: 8 }}>
            <span className="muted">
              Step {index + 1} of {steps.length}
            </span>
            <span className="muted">{info.rail}</span>
          </div>
          <Meter value={((index + 1) / steps.length) * 100} tone="accent" />
        </div>
      </aside>

      <section className="card onb-card">
        <div className="onb-card-head">
          <span className="eyebrow">
            <span className="eyebrow-dot" aria-hidden="true" />
            Step {index + 1} of {steps.length}
          </span>
          <h1 ref={headingRef} tabIndex={-1} style={{ outline: 'none' }}>
            {info.title}
          </h1>
          <p className="lede">{info.lede}</p>
          {info.why && (
            <p className="why">
              <Icon name="info" size={15} />
              <span>{info.why}</span>
            </p>
          )}
        </div>
        {body}
      </section>
    </div>
  )
}
