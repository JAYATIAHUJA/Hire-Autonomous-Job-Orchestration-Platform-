import { useEffect, useState } from 'react'
import { accountApi } from '../api/account'
import type { Me, PowRun } from '../api/v1types'
import { ONBOARDING_PATH } from '../auth/guard'
import { coverageLabel } from './steps'

const POLL_MS = 1500

type Props = { me: Me; onNext: () => void }

export default function GithubStep({ me, onNext }: Props) {
  const connected = me.identities.includes('github')
  const [run, setRun] = useState<PowRun | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  // Once GitHub is linked, start (or rejoin) the analysis and poll it. The run
  // continues on the server if the user moves on.
  useEffect(() => {
    if (!connected) return
    let cancelled = false
    let timer = 0
    setError(null)

    async function poll(id: string) {
      try {
        const next = await accountApi.getPowRun(id)
        if (cancelled) return
        setRun(next)
        if (next.status === 'queued' || next.status === 'running') timer = window.setTimeout(() => poll(id), POLL_MS)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Lost track of the analysis.')
      }
    }

    accountApi
      .startPowRefresh()
      .then((started) => {
        if (cancelled) return
        setRun(started)
        if (started.status === 'queued' || started.status === 'running') timer = window.setTimeout(() => poll(started.id), POLL_MS)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not start the analysis.')
      })

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [connected, attempt])

  if (!connected) {
    return (
      <div className="onboarding-step">
        <p className="subtitle">
          Link your GitHub account so we can read your public repositories, commits and pull requests and build your
          proof-of-work profile. We only ask GitHub for read access.
        </p>
        <div className="step-actions">
          <button type="button" onClick={() => window.location.assign(accountApi.oauthStartUrl('github', ONBOARDING_PATH))}>
            Connect GitHub
          </button>
          <button type="button" className="btn-secondary" onClick={onNext}>
            Skip for now
          </button>
        </div>
      </div>
    )
  }

  const progress = run ? Math.max(0, Math.min(100, Math.round(run.progress))) : 0
  const coverage = coverageLabel(run?.sample_coverage ?? null)
  const failed = run?.status === 'failed' || Boolean(error)
  const done = run?.status === 'done'

  return (
    <div className="onboarding-step">
      <p className="subtitle">We are reading your commits and pull requests. This usually takes a minute or two.</p>
      <div className="pow-progress">
        <div className="pow-progress-head">
          <span id="pow-progress-label">{done ? 'Analysis complete' : run?.status === 'queued' ? 'Waiting to start…' : 'Analysing your GitHub…'}</span>
          <span aria-hidden="true">{progress}%</span>
        </div>
        <div
          className="meter-track"
          role="progressbar"
          aria-labelledby="pow-progress-label"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
        >
          <div className="meter-fill fill-green" style={{ width: `${progress}%` }} />
        </div>
        {/* Reserve the line so the layout does not jump when coverage arrives. */}
        <p className="hint pow-coverage" aria-live="polite">
          {coverage ?? ' '}
        </p>
      </div>
      {failed && (
        <p className="error" role="alert">
          {error || run?.error || 'The analysis failed.'}
        </p>
      )}
      <div className="step-actions">
        {failed ? (
          <button type="button" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
        ) : (
          <button type="button" onClick={onNext}>
            {done ? 'Continue' : 'Continue while it runs'}
          </button>
        )}
        {failed && (
          <button type="button" className="btn-secondary" onClick={onNext}>
            Skip for now
          </button>
        )}
      </div>
    </div>
  )
}
