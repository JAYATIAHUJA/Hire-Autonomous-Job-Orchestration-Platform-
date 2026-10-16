import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, getBoard, getMailStatus, markSubmitted, moveApplicationStage, syncRecruiterMail } from '../api/client'
import AutofillSheet from '../components/AutofillSheet'
import OutreachSheet from '../components/OutreachSheet'
import type { ApplicationCard, BoardResponse, PipelineEvent, PipelineStage } from '../types'
import Icon from '../ui/Icon'
import { Alert, EmptyState, errorMessage, Explainer, Loading, PageHeader, shortDate, useToast } from '../ui/kit'

const COLUMNS: Record<string, { title: string; desc: string; color: string }> = {
  ready: {
    title: 'Ready to apply',
    desc: 'You picked these. Nothing reaches the company until you apply on its site.',
    color: 'var(--accent)',
  },
  applied: { title: 'Applied', desc: 'Sent. Waiting to hear back.', color: 'var(--ink)' },
  interview_scheduled: { title: 'Interviewing', desc: 'A recruiter wants to talk. Time to prepare.', color: 'var(--good)' },
  rejected: { title: 'Closed', desc: 'Not this time. Reopen it if they come back.', color: 'var(--faint)' },
}

const MOVES: Record<string, { stage: PipelineStage; label: string }[]> = {
  applied: [
    { stage: 'interview_scheduled', label: 'Got an interview' },
    { stage: 'rejected', label: 'Rejected' },
  ],
  interview_scheduled: [
    { stage: 'rejected', label: 'Rejected' },
    { stage: 'applied', label: 'Back to applied' },
  ],
  rejected: [{ stage: 'applied', label: 'Reopen' }],
}

const STAGE_WORDS: Record<string, string> = {
  applied: 'Applied',
  interview_scheduled: 'Interviewing',
  rejected: 'Closed',
  skipped: 'Passed',
}

function describe(event: PipelineEvent): string {
  const to = STAGE_WORDS[event.to_stage] ?? event.to_stage
  if (event.source === 'swipe') return 'You swiped right and gave consent'
  if (event.source === 'imap') return `Recruiter email moved it to ${to}`
  return event.from_stage ? `You moved it to ${to}` : to
}

// The latest thing that happened to a card, in words. The API's own summary names the
// consent id for swipes, which means nothing to the user.
function lastNote(card: ApplicationCard): string {
  const last = card.events[card.events.length - 1]
  if (!last || last.source === 'swipe') return `You applied${card.created_at ? ` on ${shortDate(card.created_at)}` : ''}.`
  return card.last_event_summary || describe(last)
}

export default function PipelinePage() {
  const toast = useToast()
  const [board, setBoard] = useState<BoardResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [mailNote, setMailNote] = useState<string | null>(null)
  const [openCard, setOpenCard] = useState<string | null>(null)
  const [writeTo, setWriteTo] = useState<ApplicationCard | null>(null)
  const [fillFor, setFillFor] = useState<ApplicationCard | null>(null)
  const [mailConnected, setMailConnected] = useState(false)

  useEffect(() => {
    getMailStatus()
      .then((m) => setMailConnected(m.connected))
      .catch(() => setMailConnected(false))
  }, [])

  const loadBoard = useCallback(async () => {
    try {
      const next = await getBoard()
      setBoard(next)
      setError(null)
      return next
    } catch (err) {
      setError(errorMessage(err, 'Could not load your pipeline.'))
      return null
    }
  }, [])

  useEffect(() => {
    loadBoard()
  }, [loadBoard])

  async function checkMail() {
    setSyncing(true)
    setMailNote(null)
    try {
      const r = await syncRecruiterMail()
      await loadBoard()
      toast.show(
        r.moved ? `${r.moved} application${r.moved === 1 ? '' : 's'} updated` : 'No new replies',
        `Read ${r.fetched} email${r.fetched === 1 ? '' : 's'}, matched ${r.matched}.`,
      )
    } catch (err) {
      if (err instanceof ApiError && (err.status === 503 || err.status === 404)) {
        setMailNote(
          'Your email isn’t connected yet, so we can’t read recruiter replies for you. When you hear back, move the card yourself with the buttons below.',
        )
      } else setError(errorMessage(err, 'Could not read the mailbox.'))
    } finally {
      setSyncing(false)
    }
  }

  async function move(card: ApplicationCard, stage: PipelineStage) {
    try {
      await moveApplicationStage(card.application_id, stage, 'Moved by the candidate on the board.')
      await loadBoard()
    } catch (err) {
      setError(errorMessage(err, 'That move was not allowed.'))
    }
  }

  // The API's "applied" stage holds every right swipe; split it by whether the
  // application was actually sent, so nobody thinks a swipe applied for them.
  const swiped = board?.columns.find((c) => c.stage === 'applied')?.cards ?? []
  const columns: { key: string; cards: ApplicationCard[] }[] = board
    ? [
        { key: 'ready', cards: swiped.filter((c) => c.submission_status !== 'sent') },
        { key: 'applied', cards: swiped.filter((c) => c.submission_status === 'sent') },
        ...board.columns.filter((c) => c.stage !== 'applied' && c.stage in COLUMNS).map((c) => ({ key: c.stage, cards: c.cards })),
      ]
    : []

  async function applied(card: ApplicationCard, sent: boolean) {
    try {
      await markSubmitted(card.application_id, sent)
      await loadBoard()
      if (sent) toast.show('Marked as applied', `Good luck with ${card.employer_name}!`)
    } catch (err) {
      setError(errorMessage(err, 'Could not update that card.'))
    }
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Pipeline"
        title="Where every application stands"
        lede="Everything you applied to, from the moment you swiped right. Reach out to the people hiring from any card, and move it along as you hear back."
        actions={
          mailConnected ? (
            <button type="button" className="btn btn-primary" onClick={checkMail} disabled={syncing || !board}>
              <Icon name="inbox" size={16} />
              {syncing ? 'Checking…' : 'Check for replies'}
            </button>
          ) : undefined
        }
      />

      <Explainer
        id="pipeline-how"
        title="How cards move"
        steps={[
          { title: 'You swipe right', body: 'The job lands in Applied with your signed consent attached.' },
          { title: 'Reach out', body: 'Write to the recruiter from the card: we draft a short note from your profile, you send it.' },
          { title: 'Move it as you hear back', body: 'Interview invite or a no? Use the buttons on the card.' },
        ]}
      />

      {error && (
        <div style={{ marginBottom: 16 }}>
          <Alert tone="error">{error}</Alert>
        </div>
      )}
      {mailNote && (
        <div style={{ marginBottom: 16 }}>
          <Alert tone="info">{mailNote}</Alert>
        </div>
      )}

      {!board ? (
        !error && <Loading label="Loading your pipeline…" />
      ) : board.total === 0 ? (
        <div className="card">
          <EmptyState
            icon="board"
            title="Nothing here yet"
            actions={
              <Link to="/swipe" className="btn btn-accent">
                Open your deck
                <Icon name="arrowRight" size={16} />
              </Link>
            }
          >
            Swipe right on a job in your deck and it shows up here, ready to track.
          </EmptyState>
        </div>
      ) : (
        <div className="board">
          {columns.map((column) => {
            const meta = COLUMNS[column.key]
            return (
              <section key={column.key} className={`column column-${column.key}`} aria-labelledby={`col-${column.key}`}>
                <header className="column-head">
                  <span className="column-dot" style={{ background: meta.color }} aria-hidden="true" />
                  <h2 id={`col-${column.key}`}>{meta.title}</h2>
                  <span className="count">{column.cards.length}</span>
                </header>
                <p className="column-desc">{meta.desc}</p>
                <div className="column-cards">
                  {column.cards.length === 0 && <div className="column-empty">Nothing here</div>}
                  {column.cards.map((card) => (
                    <article key={card.application_id} className="app-card">
                      <h3>{card.role_title}</h3>
                      <p className="app-card-sub">
                        {card.employer_name}
                        {card.location ? ` · ${card.location}` : ''}
                      </p>
                      {column.key === 'ready' ? (
                        <ApplySteps card={card} onApplied={() => applied(card, true)} onAutofill={() => setFillFor(card)} />
                      ) : (
                        <p className="app-card-last">{lastNote(card)}</p>
                      )}
                      <div className="row" style={{ marginTop: 10, gap: 6 }}>
                        {card.consent && (
                          <span
                            className={`badge ${card.consent.verified ? 'badge-good' : 'badge-bad'}`}
                            title={card.consent.purpose}
                          >
                            {card.consent.verified ? 'Consent verified' : 'Signature mismatch'}
                          </span>
                        )}
                        {card.updated_at && <span className="tiny muted">Updated {shortDate(card.updated_at)}</span>}
                      </div>
                      <div className="app-card-actions">
                        {column.key !== 'ready' && (MOVES[card.stage] || []).map((target) => (
                          <button key={target.stage} type="button" className="btn btn-secondary btn-sm" onClick={() => move(card, target.stage)}>
                            {target.label}
                          </button>
                        ))}
                        {card.stage !== 'rejected' && (
                          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setWriteTo(card)}>
                            <Icon name="mail" size={13} />
                            Reach out
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          aria-expanded={openCard === card.application_id}
                          onClick={() => setOpenCard(openCard === card.application_id ? null : card.application_id)}
                        >
                          History
                        </button>
                      </div>
                      {openCard === card.application_id && (
                        <ol className="timeline">
                          {card.events.map((event, index) => (
                            <li key={index}>
                              <span>
                                {describe(event)}
                                {event.detail && event.source === 'imap' ? ` — “${event.detail}”` : ''}
                                {event.occurred_at && <span className="when">{new Date(event.occurred_at).toLocaleString('en-IN')}</span>}
                              </span>
                            </li>
                          ))}
                          {card.consent && (
                            <li>
                              <span>
                                Consent receipt <code>{card.consent.consent_id.slice(0, 12)}…</code>
                                <span className="when">Signed with {card.consent.algorithm}</span>
                              </span>
                            </li>
                          )}
                        </ol>
                      )}
                    </article>
                  ))}
                </div>
              </section>
            )
          })}
        </div>
      )}

      {fillFor && (
        <AutofillSheet
          applicationId={fillFor.application_id}
          company={fillFor.employer_name}
          role={fillFor.role_title}
          applyUrl={fillFor.apply_url}
          onClose={() => setFillFor(null)}
          onChanged={loadBoard}
        />
      )}

      {writeTo && (
        <OutreachSheet jobId={writeTo.job_id} company={writeTo.employer_name} role={writeTo.role_title} onClose={() => setWriteTo(null)} />
      )}
    </div>
  )
}

/* What to do with a card you chose but have not sent yet. */
function ApplySteps({ card, onApplied, onAutofill }: { card: ApplicationCard; onApplied: () => void; onAutofill: () => void }) {
  const status = card.submission_status ?? 'not_sent'
  if (status === 'filling')
    return (
      <button type="button" className="apply-steps apply-live" onClick={onAutofill}>
        <span className="spinner" /> Hire is filling the form… <span className="text-link">watch</span>
      </button>
    )
  if (status === 'needs_review')
    return (
      <div className="apply-steps">
        <p className="apply-status">
          <Icon name="info" size={13} />
          Waiting for you: check the form or answer a question
        </p>
        <button type="button" className="btn btn-accent btn-sm" onClick={onAutofill}>
          Review &amp; send
        </button>
      </div>
    )
  return (
    <div className="apply-steps">
      <p className="apply-status">
        <Icon name="clock" size={13} />
        {status === 'failed' ? 'Auto-fill stopped. Apply on the company’s site instead.' : 'Not sent yet'}
      </p>
      <div className="row" style={{ gap: 6 }}>
        {card.can_autofill && (
          <button type="button" className="btn btn-accent btn-sm" onClick={onAutofill}>
            <Icon name="zap" size={13} />
            Fill it for me
          </button>
        )}
        {card.apply_url && (
          <a href={card.apply_url} target="_blank" rel="noreferrer" className={`btn btn-sm ${card.can_autofill ? 'btn-secondary' : 'btn-primary'}`}>
            Apply on their site
            <Icon name="external" size={12} />
          </a>
        )}
        <button type="button" className="btn btn-secondary btn-sm" onClick={onApplied}>
          <Icon name="check" size={13} />
          I’ve applied
        </button>
      </div>
    </div>
  )
}
