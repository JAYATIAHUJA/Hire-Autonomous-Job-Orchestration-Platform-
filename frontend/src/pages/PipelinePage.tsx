import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getBoard, moveApplicationStage, syncRecruiterMail } from '../api/client'
import type { ApplicationCard, BoardResponse, MailSyncResponse, PipelineStage } from '../types'
import { useCandidateRef } from '../hooks/useCandidateRef'

const MOVE_TARGETS: Record<string, { stage: PipelineStage; label: string }[]> = {
  applied: [
    { stage: 'interview_scheduled', label: 'Interview scheduled' },
    { stage: 'rejected', label: 'Rejected' },
  ],
  interview_scheduled: [
    { stage: 'rejected', label: 'Rejected' },
    { stage: 'applied', label: 'Back to applied' },
  ],
  rejected: [{ stage: 'applied', label: 'Reopen' }],
}

const DEMO_REPLY = {
  uid: `demo-${Date.now()}`,
  from_address: 'Talent Team <careers@swiggy.com>',
  subject: 'Interview invitation — Backend Software Engineer',
  body: 'Thanks for applying. We would like to invite you to a technical interview — please share your availability this week.',
}

export default function PipelinePage() {
  const [candidateRef] = useCandidateRef()
  const [board, setBoard] = useState<BoardResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [syncResult, setSyncResult] = useState<MailSyncResponse | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [openCard, setOpenCard] = useState<string | null>(null)
  const [reply, setReply] = useState(DEMO_REPLY)
  const [showReplayForm, setShowReplayForm] = useState(false)

  const loadBoard = useCallback(async () => {
    if (!candidateRef) return
    setLoading(true)
    try {
      setBoard(await getBoard(candidateRef))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the board.')
    } finally {
      setLoading(false)
    }
  }, [candidateRef])

  useEffect(() => {
    loadBoard()
  }, [loadBoard])

  async function runSync(messages?: typeof DEMO_REPLY[]) {
    setSyncing(true)
    setSyncResult(null)
    try {
      const result = await syncRecruiterMail(messages)
      setSyncResult(result)
      setError(null)
      await loadBoard()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Mail sync failed.')
    } finally {
      setSyncing(false)
    }
  }

  async function move(card: ApplicationCard, stage: PipelineStage) {
    try {
      await moveApplicationStage(card.application_id, stage, 'Moved by the candidate on the board.')
      await loadBoard()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That move was rejected.')
    }
  }

  if (!candidateRef) {
    return (
      <section className="pipeline-page">
        <h1>Pipeline</h1>
        <p className="subtitle">
          Your board tracks the jobs you consented to. Start on the deck to add the first card.
        </p>
        <Link to="/swipe" className="ghost-button">
          Open the swipe deck →
        </Link>
      </section>
    )
  }

  return (
    <section className="pipeline-page">
      <header className="swipe-head">
        <div>
          <h1>Pipeline</h1>
          <p className="muted small">
            {board ? `${board.total} tracked application${board.total === 1 ? '' : 's'}` : 'Loading…'} for{' '}
            <strong>{candidateRef}</strong>
          </p>
        </div>
        <div className="head-actions">
          <button type="button" onClick={() => runSync()} disabled={syncing}>
            {syncing ? 'Reading mailbox…' : 'Sync recruiter replies'}
          </button>
          <Link to="/swipe" className="ghost-button">
            Swipe deck →
          </Link>
        </div>
      </header>

      {error && <p className="error small">{error}</p>}

      {syncResult && (
        <p className="notice small">
          {syncResult.source === 'imap' ? 'Mailbox' : 'Replayed batch'}: {syncResult.fetched} read ·{' '}
          {syncResult.matched} matched · <strong>{syncResult.moved} card(s) moved</strong> · {syncResult.skipped}{' '}
          ignored.
        </p>
      )}

      <details className="replay-box" open={showReplayForm} onToggle={(e) => setShowReplayForm(e.currentTarget.open)}>
        <summary>No mailbox connected? Replay a recruiter reply</summary>
        <p className="hint">
          The background IMAP service reads real replies every few minutes once <code>IMAP_ENABLED</code> is set.
          This posts one message through the same classifier and matcher.
        </p>
        <div className="connect-form">
          <label>
            From
            <input value={reply.from_address} onChange={(e) => setReply({ ...reply, from_address: e.target.value })} />
          </label>
          <label>
            Subject
            <input value={reply.subject} onChange={(e) => setReply({ ...reply, subject: e.target.value })} />
          </label>
          <label>
            Body
            <textarea rows={3} value={reply.body} onChange={(e) => setReply({ ...reply, body: e.target.value })} />
          </label>
          <button
            type="button"
            disabled={syncing}
            onClick={() => runSync([{ ...reply, uid: `demo-${Date.now()}` }])}
          >
            Deliver this reply
          </button>
        </div>
      </details>

      {loading && !board && <p className="muted">Loading board…</p>}

      {board && (
        <div className="kanban">
          {board.columns.map((column) => (
            <section key={column.stage} className={`kanban-column stage-${column.stage}`}>
              <header>
                <h2>{column.label}</h2>
                <span className="count">{column.count}</span>
              </header>

              {column.cards.length === 0 && <p className="muted small empty-column">Nothing here yet.</p>}

              {column.cards.map((card) => (
                <article key={card.application_id} className="kanban-card">
                  <h3>{card.role_title}</h3>
                  <p className="muted small">
                    {card.employer_name}
                    {card.location ? ` · ${card.location}` : ''}
                  </p>

                  {card.consent && (
                    <p className="small consent-line" title={card.consent.purpose}>
                      {card.consent.verified ? '✓ consent verified' : '⚠ signature mismatch'} ·{' '}
                      {new Date(card.consent.granted_at).toLocaleDateString()}
                    </p>
                  )}

                  {card.last_event_summary && <p className="small muted">{card.last_event_summary}</p>}

                  <div className="card-actions">
                    {(MOVE_TARGETS[card.stage] || []).map((target) => (
                      <button
                        key={target.stage}
                        type="button"
                        className="mini-button"
                        onClick={() => move(card, target.stage)}
                      >
                        {target.label}
                      </button>
                    ))}
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => setOpenCard(openCard === card.application_id ? null : card.application_id)}
                    >
                      {openCard === card.application_id ? 'hide trail' : 'audit trail'}
                    </button>
                  </div>

                  {openCard === card.application_id && (
                    <ol className="event-trail">
                      {card.events.map((event, index) => (
                        <li key={index}>
                          <span className={`source-tag source-${event.source}`}>{event.source}</span>{' '}
                          {event.from_stage ? `${event.from_stage} → ` : ''}
                          {event.to_stage}
                          {event.detail ? ` — ${event.detail}` : ''}
                        </li>
                      ))}
                      {card.consent && (
                        <li className="muted">
                          <code>{card.consent.consent_id}</code> signed with {card.consent.algorithm}
                        </li>
                      )}
                    </ol>
                  )}
                </article>
              ))}
            </section>
          ))}
        </div>
      )}
    </section>
  )
}
