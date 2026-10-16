import { useEffect, useState, type ReactNode } from 'react'
import { getJobDetail } from '../api/client'
import OutreachSheet from './OutreachSheet'
import type { JobContract } from '../types'
import Icon from '../ui/Icon'
import { ago, LogoTile, Meter } from '../ui/kit'
import { relativeTime, sourceLine } from '../ui/source'
import { trustOf } from '../ui/trust'

type Props = {
  job: JobContract
  onClose: () => void
  // Shown in the footer; omitted on a card that is already decided.
  actions?: ReactNode
}

// What the ghost filter looked at for this listing, as plain yes/no checks.
function checksFor(job: JobContract): { ok: boolean; text: string }[] {
  const m = job.ghost_job_metrics
  return [
    { ok: m.posting_age_days <= 30, text: m.posting_age_days <= 30 ? 'Posted in the last month' : `Open for ${m.posting_age_days} days` },
    { ok: m.repost_count <= 1, text: m.repost_count <= 1 ? 'Not reposted over and over' : `Reposted ${m.repost_count} times` },
    { ok: Boolean(job.role.salary_range), text: job.role.salary_range ? 'Salary is disclosed' : 'Salary not disclosed' },
    {
      ok: !job.company.external_layoff_flag,
      text: job.company.external_layoff_flag ? 'Company is in recent layoff news' : 'No recent layoff news',
    },
    {
      ok: job.parsed_requirements.primary_skills.length >= 3,
      text:
        job.parsed_requirements.primary_skills.length >= 3
          ? 'Specific about the stack'
          : 'Vague about the actual work',
    },
  ]
}

export default function JobSheet({ job, onClose, actions }: Props) {
  const trust = trustOf(job.ghost_job_metrics)
  const [description, setDescription] = useState<string | null>(job.description ?? null)
  const [showAll, setShowAll] = useState(false)

  // Lists carry a short preview; the sheet shows the whole posting.
  useEffect(() => {
    let cancelled = false
    getJobDetail(job.job_id)
      .then((full) => {
        if (!cancelled && full.description) setDescription(full.description)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [job.job_id])

  const src = job.source
  const long = (description ?? '').length > 700
  const [writing, setWriting] = useState(false)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
    }
  }, [onClose])

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <aside
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sheet-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="sheet-head">
          <div className="job-company">
            <LogoTile name={job.company.name} />
            <div>
              <div className="job-company-name">{job.company.name}</div>
              <div className="job-company-sub">{job.company.domain ?? job.role.location}</div>
            </div>
          </div>
          <button type="button" className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close">
            <Icon name="x" size={18} />
          </button>
        </header>

        <div className="sheet-body">
          <div>
            <h2 id="sheet-title" style={{ fontSize: '1.45rem', letterSpacing: '-0.03em' }}>
              {job.role.title}
            </h2>
            <div className="job-row-meta" style={{ marginTop: 8 }}>
              <span>
                <Icon name="pin" size={14} />
                {job.role.location}
              </span>
              <span>
                <Icon name="clock" size={14} />
                {ago(job.ghost_job_metrics.posting_age_days)}
              </span>
            </div>
          </div>

          <dl className="facts" style={{ marginTop: 0 }}>
            <div>
              <dt>Salary</dt>
              <dd>{job.role.salary_range || 'Not disclosed'}</dd>
            </div>
            <div>
              <dt>Experience</dt>
              <dd>{job.parsed_requirements.experience_level || 'Not stated'}</dd>
            </div>
          </dl>

          <section className="source-box">
            <div className="row" style={{ gap: 8, flexWrap: 'nowrap', alignItems: 'flex-start' }}>
              <Icon name="link" size={15} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="small">
                  From <strong>{sourceLine(job)}</strong>
                </div>
                <div className="tiny muted" style={{ marginTop: 2 }}>
                  {src?.posted_at && <>Posted {relativeTime(src.posted_at)} · </>}
                  {src?.last_seen_at ? <>still listed {relativeTime(src.last_seen_at)}</> : <>added {relativeTime(job.created_at)}</>}
                </div>
              </div>
            </div>
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              {src?.apply_url && (
                <a href={src.apply_url} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
                  Open the original posting
                  <Icon name="external" size={13} />
                </a>
              )}
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setWriting(true)}>
                <Icon name="mail" size={13} />
                Write to the recruiter
              </button>
            </div>
          </section>

          {job.parsed_requirements.primary_skills.length > 0 && (
            <section>
              <h4 style={{ marginBottom: 10 }}>What they want</h4>
              <ul className="chip-list">
                {job.parsed_requirements.primary_skills.map((s) => (
                  <li key={s} className="chip">
                    {s}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {description && (
            <section>
              <h4 style={{ marginBottom: 8 }}>About the role</h4>
              <p className="small" style={{ whiteSpace: 'pre-line', color: 'var(--ink-2)', lineHeight: 1.65 }}>
                {long && !showAll ? `${description.slice(0, 700).trim()}…` : description}
              </p>
              {long && (
                <button type="button" className="link-btn small" style={{ marginTop: 6 }} onClick={() => setShowAll((v) => !v)}>
                  {showAll ? 'Show less' : 'Read the full description'}
                </button>
              )}
            </section>
          )}

          <section className={`verdict ${trust.tone}`} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
            <div className="row-between">
              <div>
                <h4>Is this job real?</h4>
                <p className="small" style={{ color: 'var(--ink-2)', marginTop: 2 }}>
                  Our filter puts the chance they’re actively hiring for this role at {trust.percent}%.
                </p>
              </div>
              <span className="big-number" style={{ fontSize: '1.9rem' }}>
                {trust.percent}%
              </span>
            </div>
            <Meter value={trust.percent} tone={trust.tone === 'bad' ? 'accent' : trust.tone} />
            <ul className="list-plain" style={{ marginTop: 6 }}>
              {checksFor(job).map((c) => (
                <li
                  key={c.text}
                  className="row"
                  style={{ padding: '7px 0', borderColor: 'rgba(17,17,19,.06)', gap: 10, fontSize: '0.86rem' }}
                >
                  <Icon name={c.ok ? 'check' : 'alert'} size={15} className={c.ok ? 'additions' : 'deletions'} />
                  {c.text}
                </li>
              ))}
            </ul>
          </section>
        </div>

        {actions && <footer className="sheet-foot">{actions}</footer>}
      </aside>
      {writing && (
        <div onClick={(e) => e.stopPropagation()}>
          <OutreachSheet jobId={job.job_id} company={job.company.name} role={job.role.title} onClose={() => setWriting(false)} />
        </div>
      )}
    </div>
  )
}
