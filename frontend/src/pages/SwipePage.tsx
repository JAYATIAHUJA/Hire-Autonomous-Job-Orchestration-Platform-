import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDeck, swipeJob } from '../api/client'
import type { ConsentReceipt, JobContract } from '../types'
import { CANDIDATE_STORAGE_KEY, useCandidateRef } from '../hooks/useCandidateRef'

const COMMIT_DISTANCE = 110 // px of travel before a drag counts as a decision

type Drag = { dx: number; dy: number; active: boolean }

const NO_DRAG: Drag = { dx: 0, dy: 0, active: false }

export default function SwipePage() {
  const [candidateRef, setCandidateRef] = useCandidateRef()
  const [handleDraft, setHandleDraft] = useState(candidateRef)
  const [deck, setDeck] = useState<JobContract[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [drag, setDrag] = useState<Drag>(NO_DRAG)
  const [flyOut, setFlyOut] = useState<'left' | 'right' | null>(null)
  const [receipt, setReceipt] = useState<ConsentReceipt | null>(null)
  const [skippedCount, setSkippedCount] = useState(0)

  const startRef = useRef<{ x: number; y: number } | null>(null)
  const busyRef = useRef(false)

  const loadDeck = useCallback(async () => {
    if (!candidateRef) return
    setLoading(true)
    setError(null)
    try {
      const data = await getDeck(candidateRef, 20)
      setDeck(data.jobs)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the deck.')
    } finally {
      setLoading(false)
    }
  }, [candidateRef])

  useEffect(() => {
    loadDeck()
  }, [loadDeck])

  const commit = useCallback(
    async (direction: 'left' | 'right') => {
      const job = deck[0]
      if (!job || busyRef.current || !candidateRef) return
      busyRef.current = true

      setFlyOut(direction)
      // Let the card leave the screen before it is removed from the stack.
      window.setTimeout(() => {
        setDeck((current) => current.slice(1))
        setDrag(NO_DRAG)
        setFlyOut(null)
      }, 220)

      try {
        const result = await swipeJob(job.job_id, direction, candidateRef)
        if (direction === 'right') {
          setReceipt(result.consent)
        } else {
          setSkippedCount((n) => n + 1)
          setReceipt(null)
        }
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'That swipe did not reach the server.')
        // Put the card back rather than silently losing it.
        setDeck((current) => [job, ...current])
      } finally {
        busyRef.current = false
      }
    },
    [candidateRef, deck],
  )

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'ArrowRight') commit('right')
      if (event.key === 'ArrowLeft') commit('left')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [commit])

  function onPointerDown(event: React.PointerEvent<HTMLElement>) {
    if (flyOut) return
    startRef.current = { x: event.clientX, y: event.clientY }
    event.currentTarget.setPointerCapture(event.pointerId)
    setDrag({ dx: 0, dy: 0, active: true })
  }

  function onPointerMove(event: React.PointerEvent<HTMLElement>) {
    if (!startRef.current || !drag.active) return
    setDrag({
      dx: event.clientX - startRef.current.x,
      dy: event.clientY - startRef.current.y,
      active: true,
    })
  }

  function onPointerUp() {
    if (!drag.active) return
    startRef.current = null

    if (drag.dx > COMMIT_DISTANCE) commit('right')
    else if (drag.dx < -COMMIT_DISTANCE) commit('left')
    else setDrag(NO_DRAG)
  }

  function saveHandle(event: React.FormEvent) {
    event.preventDefault()
    setCandidateRef(handleDraft.trim())
  }

  if (!candidateRef) {
    return (
      <section className="swipe-page">
        <h1>Swipe to apply</h1>
        <p className="subtitle">
          Every swipe right is an affirmative consent action: it writes a signed log naming the employer,
          the purpose and the moment you agreed. Tell us who is consenting.
        </p>
        <form className="connect-form" onSubmit={saveHandle}>
          <label>
            Your GitHub handle or email
            <input
              value={handleDraft}
              onChange={(e) => setHandleDraft(e.target.value)}
              placeholder="oshisharma1222"
              autoComplete="username"
            />
          </label>
          <button type="submit" disabled={!handleDraft.trim()}>
            Start swiping
          </button>
          <p className="hint">Stored in this browser only ({CANDIDATE_STORAGE_KEY}) — never sent anywhere else.</p>
        </form>
      </section>
    )
  }

  const top = deck[0]
  const next = deck[1]
  const offset = flyOut ? (flyOut === 'right' ? window.innerWidth : -window.innerWidth) : drag.dx
  const intent = offset > 60 ? 'apply' : offset < -60 ? 'skip' : null

  return (
    <section className="swipe-page">
      <header className="swipe-head">
        <div>
          <h1>Swipe to apply</h1>
          <p className="muted small">
            Swiping as <strong>{candidateRef}</strong> ·{' '}
            <button type="button" className="link-button" onClick={() => setCandidateRef('')}>
              change
            </button>
          </p>
        </div>
        <Link to="/pipeline" className="ghost-button">
          Pipeline board →
        </Link>
      </header>

      {error && <p className="error small">{error}</p>}

      <div className="deck">
        {loading && <p className="muted">Loading verified jobs…</p>}

        {!loading && !top && (
          <div className="card deck-empty">
            <h2>Deck cleared</h2>
            <p className="muted">
              You have ruled on every verified job we have right now
              {skippedCount > 0 ? `, skipping ${skippedCount}` : ''}. New listings appear as discovery runs.
            </p>
            <div className="deck-actions">
              <button type="button" onClick={loadDeck}>
                Refresh deck
              </button>
              <Link to="/pipeline" className="ghost-button">
                Track replies
              </Link>
            </div>
          </div>
        )}

        {next && <JobCardFace job={next} className="deck-card deck-card-behind" />}

        {top && (
          <JobCardFace
            job={top}
            className={`deck-card deck-card-top${drag.active ? ' dragging' : ''}`}
            style={{
              transform: `translate(${offset}px, ${flyOut ? -40 : drag.dy * 0.3}px) rotate(${offset / 22}deg)`,
              transition: drag.active ? 'none' : 'transform 0.22s ease-out',
            }}
            intent={intent}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          />
        )}
      </div>

      {top && (
        <div className="swipe-controls">
          <button type="button" className="swipe-btn swipe-skip" onClick={() => commit('left')}>
            ✕ Skip
          </button>
          <span className="muted small">{deck.length} left · drag, tap or use ← →</span>
          <button type="button" className="swipe-btn swipe-apply" onClick={() => commit('right')}>
            ✓ Apply
          </button>
        </div>
      )}

      {receipt && <ConsentBanner receipt={receipt} onDismiss={() => setReceipt(null)} />}
    </section>
  )
}

type FaceProps = {
  job: JobContract
  className: string
  style?: React.CSSProperties
  intent?: 'apply' | 'skip' | null
  onPointerDown?: (event: React.PointerEvent<HTMLElement>) => void
  onPointerMove?: (event: React.PointerEvent<HTMLElement>) => void
  onPointerUp?: () => void
  onPointerCancel?: () => void
}

function JobCardFace({ job, className, style, intent, ...handlers }: FaceProps) {
  const metrics = job.ghost_job_metrics
  return (
    <article className={className} style={style} {...handlers}>
      {intent && <span className={`swipe-intent intent-${intent}`}>{intent === 'apply' ? 'APPLY' : 'SKIP'}</span>}

      <header className="deck-card-head">
        <div>
          <h2>{job.role.title}</h2>
          <p className="muted">
            {job.company.name} · {job.role.location}
          </p>
        </div>
        <span className={`risk-badge risk-${metrics.risk_band.toLowerCase()}`}>{metrics.risk_band} risk</span>
      </header>

      <dl className="deck-facts">
        <div>
          <dt>Salary</dt>
          <dd>{job.role.salary_range || 'Not disclosed'}</dd>
        </div>
        <div>
          <dt>Experience</dt>
          <dd>{job.parsed_requirements.experience_level}</dd>
        </div>
        <div>
          <dt>Legitimacy</dt>
          <dd>{Math.round(metrics.legitimacy_probability * 100)}%</dd>
        </div>
        <div>
          <dt>Posted</dt>
          <dd>{metrics.posting_age_days}d ago</dd>
        </div>
      </dl>

      <ul className="chip-row">
        {job.parsed_requirements.primary_skills.slice(0, 6).map((skill) => (
          <li key={skill} className="chip">
            {skill}
          </li>
        ))}
      </ul>
    </article>
  )
}

function ConsentBanner({ receipt, onDismiss }: { receipt: ConsentReceipt; onDismiss: () => void }) {
  return (
    <aside className="consent-banner" role="status">
      <header>
        <strong>Consent logged {receipt.verified ? '✓' : '⚠'}</strong>
        <button type="button" className="link-button" onClick={onDismiss}>
          dismiss
        </button>
      </header>
      <p className="small">
        <code>{receipt.consent_id}</code> · {new Date(receipt.granted_at).toLocaleString()} ·{' '}
        <strong>{receipt.employer_name}</strong>
      </p>
      <p className="small muted">{receipt.purpose}</p>
      <p className="small muted signature">
        {receipt.algorithm}: {receipt.signature.slice(0, 32)}…
      </p>
    </aside>
  )
}
