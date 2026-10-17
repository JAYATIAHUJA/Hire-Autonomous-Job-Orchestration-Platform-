import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDeck, swipeJob } from '../api/client'
import DiscoveryPanel from '../components/DiscoveryPanel'
import JobSheet from '../components/JobSheet'
import type { JobContract } from '../types'
import Icon from '../ui/Icon'
import { ago, EmptyState, errorMessage, LogoTile, PageHeader, useToast } from '../ui/kit'
import { sourceName } from '../ui/source'
import { trustOf } from '../ui/trust'

const COMMIT_DISTANCE = 100 // px of drag that counts as a decision
const FLY_MS = 320
const REFILL_BELOW = 5

type Dir = 'left' | 'right'
type Leaving = { job: JobContract; dir: Dir; from: string }

export default function SwipePage() {
  const toast = useToast()
  const [deck, setDeck] = useState<JobContract[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [drag, setDrag] = useState({ dx: 0, dy: 0, active: false })
  const [leaving, setLeaving] = useState<Leaving[]>([])
  const [session, setSession] = useState({ applied: 0, skipped: 0 })
  const [details, setDetails] = useState<JobContract | null>(null)
  // Decided in this session (some still in flight): never deal these again.
  const decided = useRef<Set<string>>(new Set())
  const start = useRef<{ x: number; y: number } | null>(null)
  const fetching = useRef(false)
  // The drag offset at release, so a dragged card flies on from where it was let go.
  const dragNow = useRef({ dx: 0, dy: 0 })

  const load = useCallback(async (append: boolean) => {
    if (fetching.current) return
    fetching.current = true
    if (!append) setLoading(true)
    try {
      const data = await getDeck(30)
      const fresh = data.jobs.filter((j) => !decided.current.has(j.job_id))
      setTotal(Math.max(0, data.total - decided.current.size))
      setDeck((current) => {
        if (!append) return fresh
        const have = new Set(current.map((j) => j.job_id))
        return [...current, ...fresh.filter((j) => !have.has(j.job_id))]
      })
      setError(null)
    } catch (err) {
      setError(errorMessage(err, 'Could not load your deck.'))
    } finally {
      fetching.current = false
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(false)
  }, [load])

  // Keep the stack topped up so the deck never runs dry mid-session.
  useEffect(() => {
    if (!loading && deck.length < REFILL_BELOW && total > deck.length) load(true)
  }, [deck.length, total, loading, load])

  const commit = useCallback(
    (dir: Dir) => {
      const job = deck[0]
      if (!job) return
      setDetails(null)
      decided.current.add(job.job_id)
      // The card leaves at once; the server catches up in the background.
      const { dx, dy } = dragNow.current
      const from = `translate(${dx}px, ${dy * 0.2}px) rotate(${dx / 18}deg)`
      dragNow.current = { dx: 0, dy: 0 }
      setLeaving((l) => [...l, { job, dir, from }])
      setDeck((d) => d.slice(1))
      setTotal((t) => Math.max(0, t - 1))
      setDrag({ dx: 0, dy: 0, active: false })
      window.setTimeout(() => setLeaving((l) => l.filter((x) => x.job.job_id !== job.job_id)), FLY_MS)
      setSession((s) => (dir === 'right' ? { ...s, applied: s.applied + 1 } : { ...s, skipped: s.skipped + 1 }))

      swipeJob(job.job_id, dir)
        .then((res) => {
          if (dir !== 'right') return
          if (res.autofill_started) {
            toast.show(
              `Hire is filling ${job.company.name}’s form`,
              'Keep swiping. You review it before anything is sent.',
            )
            return
          }
          const link = job.source?.apply_url
          toast.show(
            res.already_recorded ? `${job.company.name} is already on your list` : `Saved: ${job.role.title}`,
            link ? `Nothing is sent yet. Finish applying on ${job.company.name}’s site.` : 'Nothing is sent yet. It’s on your pipeline under “Ready to apply”.',
            link ? { label: 'Apply now ↗', href: link } : undefined,
          )
        })
        .catch((err) => {
          // Put it back on top so nothing is silently lost.
          decided.current.delete(job.job_id)
          setDeck((d) => [job, ...d])
          setTotal((t) => t + 1)
          setSession((s) => (dir === 'right' ? { ...s, applied: s.applied - 1 } : { ...s, skipped: s.skipped - 1 }))
          toast.show('That swipe didn’t go through', errorMessage(err, 'Try again.'))
        })
    },
    [deck, toast],
  )

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (details) return
      const t = e.target as HTMLElement | null
      if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return
      if (e.key === 'ArrowRight') commit('right')
      if (e.key === 'ArrowLeft') commit('left')
      if (e.key === 'ArrowUp' && deck[0]) setDetails(deck[0])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [commit, deck, details])

  function onPointerDown(e: React.PointerEvent<HTMLElement>) {
    if ((e.target as HTMLElement).closest('button, a')) return
    start.current = { x: e.clientX, y: e.clientY }
    e.currentTarget.setPointerCapture(e.pointerId)
    setDrag({ dx: 0, dy: 0, active: true })
  }

  function onPointerMove(e: React.PointerEvent<HTMLElement>) {
    if (!start.current) return
    const next = { dx: e.clientX - start.current.x, dy: e.clientY - start.current.y }
    dragNow.current = next
    setDrag({ ...next, active: true })
  }

  function onPointerUp() {
    if (!start.current) return
    start.current = null
    if (drag.dx > COMMIT_DISTANCE) commit('right')
    else if (drag.dx < -COMMIT_DISTANCE) commit('left')
    else {
      if (Math.abs(drag.dx) < 5 && Math.abs(drag.dy) < 5 && deck[0]) setDetails(deck[0])
      dragNow.current = { dx: 0, dy: 0 }
      setDrag({ dx: 0, dy: 0, active: false })
    }
  }

  const visible = deck.slice(0, 3)
  const intent = drag.dx > 40 ? 'apply' : drag.dx < -40 ? 'skip' : null
  const top = deck[0]

  return (
    <div className="page swipe-page">
      <PageHeader
        eyebrow="Your deck"
        title="Swipe to apply"
        lede="Real openings from company careers pages, best fit for you first. Right to apply, left to pass, tap for details."
        actions={
          <Link to="/jobs" className="btn btn-secondary">
            <Icon name="briefcase" size={16} />
            See as a list
          </Link>
        }
      />
      <DiscoveryPanel compact onFound={() => load(true)} />

      {error && !top && <p className="error-text" style={{ marginBottom: 12 }}>{error}</p>}

      <div className="deck-layout">
        <div>
          <div className="deck" aria-live="polite">
            {loading && !top && <div className="skeleton deck-skeleton" />}

            {!loading && !top && leaving.length === 0 && (
              <div className="card deck-empty">
                <EmptyState
                  icon="check"
                  title={session.applied + session.skipped ? 'You’re through your deck' : 'No jobs for you right now'}
                  actions={
                    <>
                      <Link to="/pipeline" className="btn btn-primary">
                        Open pipeline
                      </Link>
                      <Link to="/profile?tab=prefs" className="btn btn-secondary">
                        Widen preferences
                      </Link>
                    </>
                  }
                >
                  {session.applied + session.skipped
                    ? `You applied to ${session.applied} and passed on ${session.skipped}. Use “Check now” above to look for new openings.`
                    : 'Use “Check now” above to read the company boards again, or widen your preferences.'}
                </EmptyState>
              </div>
            )}

            {/* Back to front, so the top card paints last. Keys keep each card's own element. */}
            {[...visible].reverse().map((job) => {
              const depth = visible.indexOf(job)
              const isTop = depth === 0
              // How sure the drag is (0 to 1): the outline and tint deepen with it.
              const pull = Math.min(1, Math.abs(drag.dx) / COMMIT_DISTANCE)
              const tone = drag.dx > 0 ? '21, 163, 74' : '229, 72, 77'
              const style: React.CSSProperties = isTop
                ? {
                    transform: `translate(${drag.dx}px, ${drag.dy * 0.2}px) rotate(${drag.dx / 18}deg)`,
                    transition: drag.active ? 'none' : 'transform 0.25s cubic-bezier(.2,.8,.2,1), border-color .2s, box-shadow .2s',
                    ...(pull > 0.08
                      ? {
                          borderColor: `rgba(${tone}, ${0.35 + pull * 0.65})`,
                          boxShadow: `0 0 0 ${2 + pull * 3}px rgba(${tone}, ${0.12 + pull * 0.25}), var(--shadow-3)`,
                          background: `linear-gradient(rgba(${tone}, ${pull * 0.07}), rgba(${tone}, ${pull * 0.07})), var(--surface)`,
                        }
                      : {}),
                  }
                : { transform: `translateY(${depth * 14}px) scale(${1 - depth * 0.045})`, opacity: depth === 2 ? 0.5 : 1 }
              return (
                <CardFace
                  key={job.job_id}
                  job={job}
                  className={`deck-card${isTop ? ' deck-card-top' : ''}${isTop && drag.active ? ' dragging' : ''}`}
                  style={{ ...style, zIndex: 10 - depth }}
                  intent={isTop ? intent : null}
                  onPointerDown={isTop ? onPointerDown : undefined}
                  onPointerMove={isTop ? onPointerMove : undefined}
                  onPointerUp={isTop ? onPointerUp : undefined}
                  onPointerCancel={isTop ? onPointerUp : undefined}
                />
              )
            })}

            {leaving.map(({ job, dir, from }) => (
              <CardFace
                key={`out-${job.job_id}`}
                job={job}
                className={`deck-card deck-card-leaving leave-${dir}`}
                style={{ zIndex: 20, ['--from' as string]: from } as React.CSSProperties}
                intent={dir === 'right' ? 'apply' : 'skip'}
              />
            ))}
          </div>

          {top && (
            <>
              <div className="swipe-controls">
                <button type="button" className="swipe-btn skip" onClick={() => commit('left')} aria-label={`Pass on ${top.role.title}`}>
                  <Icon name="x" size={26} stroke={2.4} />
                </button>
                <button type="button" className="swipe-btn info" onClick={() => setDetails(top)} aria-label="See details">
                  <Icon name="info" size={20} />
                </button>
                <button type="button" className="swipe-btn apply" onClick={() => commit('right')} aria-label={`Apply to ${top.role.title}`}>
                  <Icon name="check" size={30} stroke={2.6} />
                </button>
              </div>
              <div className="swipe-hint">
                <span>{total.toLocaleString('en-IN')} in your deck</span>
                <span className="keys">
                  <span className="kbd">←</span> pass <span className="kbd">↑</span> details <span className="kbd">→</span> apply
                </span>
              </div>
            </>
          )}
        </div>

        <aside className="deck-side">
          <div className="card card-pad">
            <h4 style={{ marginBottom: 14 }}>This session</h4>
            <div className="grid grid-2" style={{ gap: 10 }}>
              <div>
                <div className="tile-value" style={{ marginTop: 0 }}>{session.applied}</div>
                <div className="tile-sub">applied</div>
              </div>
              <div>
                <div className="tile-value" style={{ marginTop: 0 }}>{session.skipped}</div>
                <div className="tile-sub">passed</div>
              </div>
            </div>
            <hr className="divider" />
            <ul className="side-list">
              <li>
                <Icon name="target" size={16} />
                <span>
                  Ordered by fit with your{' '}
                  <Link to="/profile?tab=prefs" className="text-link">
                    preferences
                  </Link>
                  : role, city and experience.
                </span>
              </li>
              <li>
                <Icon name="shield" size={16} />
                <span>Every card passed the ghost-job filter and links to the company’s own posting.</span>
              </li>
              <li>
                <Icon name="lock" size={16} />
                <span>A right swipe records your consent. Passing is private.</span>
              </li>
            </ul>
          </div>
        </aside>
      </div>

      {details && (
        <JobSheet
          job={details}
          onClose={() => setDetails(null)}
          actions={
            details.job_id === top?.job_id ? (
              <>
                <button type="button" className="btn btn-secondary btn-lg" onClick={() => commit('left')}>
                  Pass
                </button>
                <button type="button" className="btn btn-primary btn-lg" onClick={() => commit('right')}>
                  <Icon name="check" size={16} />
                  Apply
                </button>
              </>
            ) : undefined
          }
        />
      )}
    </div>
  )
}

type FaceProps = {
  job: JobContract
  className: string
  style?: React.CSSProperties
  intent?: 'apply' | 'skip' | null
  onPointerDown?: (e: React.PointerEvent<HTMLElement>) => void
  onPointerMove?: (e: React.PointerEvent<HTMLElement>) => void
  onPointerUp?: () => void
  onPointerCancel?: () => void
}

function CardFace({ job, className, style, intent, ...handlers }: FaceProps) {
  const trust = trustOf(job.ghost_job_metrics)
  const skills = job.parsed_requirements.primary_skills
  const reasons = job.match?.reasons ?? []
  return (
    <article className={className} style={style} {...handlers}>
      {intent && (
        <span className={`deck-intent ${intent}`}>
          <Icon name={intent === 'apply' ? 'check' : 'x'} size={14} stroke={3} />
          {intent === 'apply' ? 'Apply' : 'Pass'}
        </span>
      )}

      <div className="job-company">
        <LogoTile name={job.company.name} />
        <div style={{ minWidth: 0 }}>
          <div className="job-company-name">{job.company.name}</div>
          <div className="job-company-sub">{job.role.location}</div>
        </div>
        <span className={`badge badge-${trust.tone}`} style={{ marginLeft: 'auto' }}>
          {trust.percent}% real
        </span>
      </div>

      <h2 className="deck-title">{job.role.title}</h2>

      {(job.match || reasons.length > 0) && (
        <ul className="chip-list" style={{ marginTop: 12 }}>
          {job.match && <li className="match-percent">{job.match.percent}% match</li>}
          {reasons.map((r) => (
            <li key={r} className="chip match-chip">
              <Icon name="check" size={12} stroke={2.6} />
              {r}
            </li>
          ))}
        </ul>
      )}

      <dl className="facts">
        <div>
          <dt>Salary</dt>
          <dd>{job.role.salary_range || 'Not disclosed'}</dd>
        </div>
        <div>
          <dt>Level</dt>
          <dd>{job.parsed_requirements.experience_level || 'Not stated'}</dd>
        </div>
      </dl>

      {skills.length > 0 && (
        <ul className="chip-list deck-skills">
          {skills.slice(0, 5).map((s) => (
            <li key={s} className="chip">
              {s}
            </li>
          ))}
          {skills.length > 5 && <li className="chip">+{skills.length - 5}</li>}
        </ul>
      )}

      <div className="deck-foot tiny muted">
        <span>{ago(job.ghost_job_metrics.posting_age_days)}</span>
        <span>via {sourceName(job)}</span>
      </div>
    </article>
  )
}
