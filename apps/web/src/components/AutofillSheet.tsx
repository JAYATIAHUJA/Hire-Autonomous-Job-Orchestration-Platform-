import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  answerAutofill,
  autofillScreenshotUrl,
  cancelAutofill,
  confirmAutofill,
  getAutofill,
  startAutofill,
  type ApplyRun,
} from '../api/client'
import Icon from '../ui/Icon'
import { Alert, errorMessage } from '../ui/kit'

type Props = { applicationId: string; company: string; role: string; applyUrl?: string | null; onClose: () => void; onChanged: () => void }

const WORKING = new Set(['queued', 'filling', 'submit_requested', 'submitting'])

// The run as five plain steps, so the user always sees where it is.
const STEPS = ['Read the form', 'Fill it in', 'Your review', 'Send', 'Sent'] as const

function stepIndex(run: ApplyRun | null): number {
  if (!run) return 0
  switch (run.status) {
    case 'queued':
      return 0
    case 'filling':
      return 1
    case 'needs_answers':
    case 'ready_to_submit':
      return 2
    case 'submit_requested':
    case 'submitting':
      return 3
    case 'submitted':
      return 4
    default:
      return 2
  }
}

export default function AutofillSheet({ applicationId, company, role, applyUrl, onClose, onChanged }: Props) {
  const [run, setRun] = useState<ApplyRun | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)

  // Start (or rejoin) the run when the sheet opens.
  useEffect(() => {
    let cancelled = false
    getAutofill(applicationId)
      .then(async (existing) => {
        const live = existing && !['cancelled', 'failed', 'captcha', 'unconfirmed'].includes(existing.status)
        const next = live ? existing : await startAutofill(applicationId)
        if (!cancelled) setRun(next)
        onChanged()
      })
      .catch((err) => !cancelled && setError(errorMessage(err, 'Could not start filling the form.')))
    return () => {
      cancelled = true
    }
  }, [applicationId, onChanged])

  // Follow it while the worker is busy.
  useEffect(() => {
    if (!run || !WORKING.has(run.status)) return
    const id = window.setTimeout(async () => {
      try {
        const next = await getAutofill(applicationId)
        setRun(next)
        if (next && !WORKING.has(next.status)) onChanged()
      } catch {
        /* keep polling */
      }
    }, 2000)
    return () => window.clearTimeout(id)
  }, [run, applicationId, onChanged])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const act = useCallback(
    async (fn: () => Promise<ApplyRun>) => {
      setBusy(true)
      setError(null)
      try {
        setRun(await fn())
        onChanged()
      } catch (err) {
        setError(errorMessage(err, 'That didn’t work.'))
      } finally {
        setBusy(false)
      }
    },
    [onChanged],
  )

  const current = stepIndex(run)
  const stopped = run && ['failed', 'captcha', 'unconfirmed', 'cancelled'].includes(run.status)

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <aside className="sheet" role="dialog" aria-modal="true" aria-labelledby="af-title" onClick={(e) => e.stopPropagation()}>
        <header className="sheet-head">
          <div>
            <h2 id="af-title">Applying to {company}</h2>
            <p className="muted small" style={{ marginTop: 4 }}>
              {role} · Hire fills the form from your profile. Nothing is sent until you confirm.
            </p>
          </div>
          <button type="button" className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close">
            <Icon name="x" size={18} />
          </button>
        </header>

        <div className="sheet-body">
          <ol className="af-steps" aria-label="Progress">
            {STEPS.map((label, i) => (
              <li key={label} className={i < current || run?.status === 'submitted' ? 'done' : i === current && !stopped ? 'now' : ''}>
                <span className="af-dot">{i < current || run?.status === 'submitted' ? <Icon name="check" size={11} stroke={3} /> : i + 1}</span>
                {label}
              </li>
            ))}
          </ol>

          {error && <Alert tone="error">{error}</Alert>}

          {!run || WORKING.has(run.status) ? (
            <div className="af-working" aria-live="polite">
              <span className="spinner" />
              <div>
                <strong>{run?.step ?? 'Starting…'}</strong>
                <p className="muted small">This usually takes under a minute. You can close this; it keeps going.</p>
              </div>
            </div>
          ) : run.status === 'needs_answers' ? (
            <form
              className="form"
              onSubmit={(e) => {
                e.preventDefault()
                act(() => answerAutofill(applicationId, answers))
              }}
            >
              {run.error ? (
                <Alert tone="warn">
                  {run.error}{' '}
                  <Link to="/profile?tab=links" className="text-link">
                    Open your profile
                  </Link>
                </Alert>
              ) : (
                <Alert tone="info">{company}’s form asks {run.missing.length === 1 ? 'one thing' : `${run.missing.length} things`} your profile doesn’t answer. We never guess.</Alert>
              )}
              {run.missing.map((m) =>
                m.type === 'unsupported' ? (
                  <p key={m.label} className="small muted">
                    “{m.label}” is a kind of question Hire can’t fill yet. Apply on their site instead.
                  </p>
                ) : (
                  <label key={m.label} className="field">
                    <span className="field-label">{m.label}</span>
                    {m.options.length ? (
                      <select className="select" value={answers[m.label] ?? ''} onChange={(e) => setAnswers({ ...answers, [m.label]: e.target.value })}>
                        <option value="">Choose…</option>
                        {m.options.map((o) => (
                          <option key={o} value={o}>
                            {o}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <textarea className="textarea" rows={2} value={answers[m.label] ?? ''} onChange={(e) => setAnswers({ ...answers, [m.label]: e.target.value })} />
                    )}
                  </label>
                ),
              )}
              {!run.error && (
                <button type="submit" className="btn btn-primary btn-lg" disabled={busy || run.missing.some((m) => m.type !== 'unsupported' && !answers[m.label]?.trim())}>
                  Continue filling
                </button>
              )}
            </form>
          ) : run.status === 'ready_to_submit' ? (
            <>
              <Alert tone="good">The form is filled. Check it, then send it.</Alert>
              {run.has_screenshot && (
                <a href={autofillScreenshotUrl(applicationId, run.id)} target="_blank" rel="noreferrer" className="af-shot">
                  <img src={autofillScreenshotUrl(applicationId, run.id)} alt={`The filled ${company} application form`} />
                </a>
              )}
              <section>
                <h4 style={{ marginBottom: 8 }}>What we filled in</h4>
                <dl className="kv">
                  {run.filled.map((f) => (
                    <FilledRow key={f.label} label={f.label} value={f.shown} />
                  ))}
                </dl>
              </section>
              <form
                className="source-box form"
                onSubmit={(e) => {
                  e.preventDefault()
                  act(() => confirmAutofill(applicationId, typed))
                }}
              >
                <label className="field">
                  <span className="field-label">
                    This sends a real application to {company}. Type <strong>{company}</strong> to confirm.
                  </span>
                  <input className="input" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={company} autoComplete="off" />
                </label>
                <div className="row" style={{ gap: 8 }}>
                  <button type="submit" className="btn btn-accent" disabled={busy || typed.trim().toLowerCase() !== company.trim().toLowerCase()}>
                    Send application
                  </button>
                  <button type="button" className="btn btn-ghost" onClick={() => act(() => cancelAutofill(applicationId))} disabled={busy}>
                    Don’t send
                  </button>
                </div>
              </form>
            </>
          ) : run.status === 'submitted' ? (
            <div className="empty">
              <span className="empty-icon" style={{ background: 'var(--good-soft)', color: 'var(--good-ink)' }}>
                <Icon name="check" size={22} />
              </span>
              <h3>Sent to {company}</h3>
              <p>It’s on your pipeline under Applied. Want to give it a push? Reach out to the recruiter from the card.</p>
            </div>
          ) : (
            <>
              <Alert tone={run.status === 'cancelled' ? 'info' : 'warn'}>
                {run.status === 'captcha'
                  ? `${company}’s site asked for a CAPTCHA. Hire never solves those: finish on their site.`
                  : run.status === 'cancelled'
                    ? 'Stopped. Nothing was sent.'
                    : run.status === 'unconfirmed'
                      ? 'We clicked send but saw no confirmation. Check your email before trying again.'
                      : `Filling stopped: ${run.error ?? 'something went wrong'}. Nothing was sent.`}
              </Alert>
              <div className="row" style={{ gap: 8 }}>
                {applyUrl && (
                  <a href={applyUrl} target="_blank" rel="noreferrer" className="btn btn-primary">
                    Apply on their site
                    <Icon name="external" size={13} />
                  </a>
                )}
                {run.status !== 'unconfirmed' && (
                  <button type="button" className="btn btn-secondary" onClick={() => act(() => startAutofill(applicationId))} disabled={busy}>
                    <Icon name="refresh" size={14} />
                    Try again
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </aside>
    </div>
  )
}

function FilledRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd style={{ overflowWrap: 'anywhere' }}>{value}</dd>
    </>
  )
}
