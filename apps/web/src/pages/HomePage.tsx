import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { accountApi } from '../api/account'
import { getBoard, getDeck, getDiscovery } from '../api/client'
import type { CandidateProfile, Me, OnlinePresence, PowRun, Preferences } from '../api/v1types'
import { useAuth } from '../auth/AuthContext'
import FlowChart from '../components/FlowChart'
import { grantedPurposes } from '../privacy/consent'
import type { ApplicationCard, BoardResponse, DiscoveryStatus } from '../types'
import Icon, { type IconName } from '../ui/Icon'
import { firstName, initials, realName, shortDate } from '../ui/kit'
import { relativeTime } from '../ui/source'

type Data = {
  deckTotal: number
  swiped: number
  board: BoardResponse | null
  discovery: DiscoveryStatus | null
  profile: CandidateProfile | null
  prefs: Preferences | null
  presence: OnlinePresence | null
  pow: PowRun | null
}

const SOURCE_COLORS: Record<string, string> = {
  greenhouse: '#c9e3cf',
  ashby: '#d9cdf0',
  lever: '#c8dbe8',
  remoteok: '#f6d77a',
}
const SOURCE_NAMES: Record<string, string> = { greenhouse: 'Greenhouse', ashby: 'Ashby', lever: 'Lever', remoteok: 'RemoteOK' }

const TO_APPLY = { label: 'To apply', icon: 'arrowRight' as IconName, cls: 'st-todo' }
const STAGE: Record<string, { label: string; icon: IconName; cls: string }> = {
  applied: { label: 'Sent', icon: 'clock', cls: 'st-wait' },
  interview_scheduled: { label: 'Interview', icon: 'check', cls: 'st-good' },
  rejected: { label: 'Closed', icon: 'x', cls: 'st-bad' },
}

const safe = <T,>(p: Promise<T>) => p.catch(() => null)

export default function HomePage() {
  const { auth } = useAuth()
  const me = auth.status === 'authenticated' ? auth.me : null
  const navigate = useNavigate()
  const [data, setData] = useState<Data | null>(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    let cancelled = false
    Promise.all([
      safe(getDeck(1)),
      safe(getBoard()),
      safe(getDiscovery()),
      safe(accountApi.getProfile()),
      safe(accountApi.getPreferences()),
      safe(accountApi.getPresence()),
      safe(accountApi.getLatestPowRun()),
    ]).then(([deck, board, discovery, profile, prefs, presence, pow]) => {
      if (cancelled) return
      setData({ deckTotal: deck?.total ?? 0, swiped: deck?.swiped_total ?? 0, board, discovery, profile, prefs, presence, pow })
    })
    return () => {
      cancelled = true
    }
  }, [])

  const count = (stage: string) => data?.board?.columns.find((c) => c.stage === stage)?.count ?? 0
  const interviews = count('interview_scheduled')
  const onBoard = count('applied') + interviews + count('rejected')
  const swipedRight = data?.board?.columns.find((c) => c.stage === 'applied')?.cards ?? []
  const toApply = swipedRight.filter((c) => c.submission_status !== 'sent').length
  const sent = onBoard - toApply
  const passed = Math.max(0, (data?.swiped ?? 0) - onBoard)
  const name = firstName(me?.display_name, me?.email) ?? 'there'

  function search(e: FormEvent) {
    e.preventDefault()
    navigate(q.trim() ? `/jobs?q=${encodeURIComponent(q.trim())}` : '/jobs')
  }

  return (
    <div className="page dash">
      <div className="dash-main">
        <header className="dash-head">
          <div>
            <h1 className="dash-hello">Hi, {name}</h1>
            <p className="muted small">{new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}</p>
          </div>
          <form className="search dash-search" onSubmit={search} role="search">
            <Icon name="search" size={16} />
            <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search jobs" aria-label="Search jobs" />
          </form>
        </header>

        <div className="stat-row">
          <StatCard tone="lilac" label="In your deck" value={data?.deckTotal} to="/swipe" cta="Swipe" />
          <StatCard tone="peach" label="Ready to apply" value={data ? toApply : undefined} to="/pipeline" cta="Apply" />
          <StatCard tone="sky" label="Applied" value={data ? sent : undefined} to="/pipeline" cta="Track" />
          <StatCard tone="butter" label="Interviews" value={data ? interviews : undefined} to="/pipeline" cta="Prepare" />
        </div>

        <section className="card dash-card">
          <div className="row-between" style={{ alignItems: 'flex-start' }}>
            <div>
              <h2 className="dash-card-title">Your job search</h2>
              <p className="muted small">Where today’s jobs come from, and what you’ve done with them.</p>
            </div>
            {data?.discovery?.last_run && (
              <div style={{ textAlign: 'right' }}>
                <div className="dash-delta">+{(data.discovery.last_run.jobs_added ?? 0).toLocaleString('en-IN')}</div>
                <div className="tiny muted">new jobs, {relativeTime(data.discovery.last_run.finished_at)}</div>
              </div>
            )}
          </div>
          {data?.discovery ? (
            <FlowChart
              left={Object.entries(data.discovery.by_source)
                .filter(([k, v]) => k in SOURCE_NAMES && v > 0)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => ({ label: SOURCE_NAMES[k], value: v, color: SOURCE_COLORS[k] }))}
              hubLabel={`${data.discovery.active_jobs} live jobs`}
              right={[
                { label: 'In your deck', value: data.deckTotal, color: '#d9cdf0' },
                { label: 'Ready to apply', value: toApply, color: '#f9dccb' },
                { label: 'Applied', value: sent, color: '#c9e3cf' },
                { label: 'Passed', value: passed, color: '#e7e5df' },
              ]}
            />
          ) : (
            <div className="skeleton" style={{ height: 240, marginTop: 16 }} />
          )}
          {data?.discovery && (
            <p className="tiny muted" style={{ textAlign: 'center', marginTop: 4 }}>
              {data.discovery.active_jobs.toLocaleString('en-IN')} live jobs from{' '}
              {data.discovery.companies_with_jobs.toLocaleString('en-IN')} companies ·{' '}
              <Link to="/jobs" className="text-link">
                browse all
              </Link>
            </p>
          )}
        </section>

        <section className="card dash-card">
          <div className="row-between" style={{ marginBottom: 8 }}>
            <h2 className="dash-card-title">Recent applications</h2>
            <Link to="/pipeline" className="btn btn-ghost btn-sm">
              Open pipeline
              <Icon name="arrowRight" size={14} />
            </Link>
          </div>
          <RecentTable board={data?.board ?? null} />
        </section>
      </div>

      <ProfilePanel data={data} me={me} />
    </div>
  )
}

function StatCard({ tone, label, value, to, cta }: { tone: string; label: string; value?: number; to: string; cta: string }) {
  return (
    <Link to={to} className={`stat-card tone-${tone}`}>
      <span className="stat-card-label">{label}</span>
      <span className="stat-card-value">{value === undefined ? '—' : value.toLocaleString('en-IN')}</span>
      <span className="stat-card-cta">{cta}</span>
    </Link>
  )
}

function RecentTable({ board }: { board: BoardResponse | null }) {
  if (!board) return <div className="skeleton" style={{ height: 120 }} />
  const cards: ApplicationCard[] = board.columns
    .flatMap((c) => c.cards)
    .sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? ''))
    .slice(0, 6)
  if (cards.length === 0)
    return (
      <p className="muted small" style={{ padding: '16px 0' }}>
        Nothing yet.{' '}
        <Link to="/swipe" className="text-link">
          Swipe right on a job
        </Link>{' '}
        and it shows up here.
      </p>
    )
  return (
    <div className="table-scroll">
      <table className="table dash-table">
        <thead>
          <tr>
            <th>Company</th>
            <th>Role</th>
            <th>Status</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {cards.map((c) => {
            const st = c.stage === 'applied' && c.submission_status !== 'sent' ? TO_APPLY : STAGE[c.stage] ?? STAGE.applied
            return (
              <tr key={c.application_id}>
                <td>
                  <span className="row" style={{ gap: 10, flexWrap: 'nowrap' }}>
                    <span className="logo-tile sm">{c.employer_name[0]}</span>
                    {c.employer_name}
                  </span>
                </td>
                <td className="dash-role">{c.role_title}</td>
                <td>
                  <span className={`status-chip ${st.cls}`}>
                    <Icon name={st.icon} size={13} />
                    {st.label}
                  </span>
                </td>
                <td className="muted">{shortDate(c.updated_at)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ProfilePanel({ data, me }: { data: Data | null; me: Me | null }) {
  const identity = data?.profile?.profile.identity
  // An email-only account has no name yet: greet them by the mailbox name, show the address below.
  const name = identity?.name?.value || realName(me?.display_name) || firstName(me?.display_name, me?.email) || 'You'
  const headline = data?.prefs?.roles?.[0]
  const where = data?.prefs?.locations?.[0] ?? identity?.location?.value
  const presence = data?.presence
  const purposes = grantedPurposes(me?.consent ?? null)
  const skills = (data?.profile?.profile.skills ?? [])
    .map((s) => (typeof s.text === 'string' ? s.text.replace(/^skill:\s*/i, '').replace(/\.$/, '') : ''))
    .filter(Boolean)

  const p = data?.profile?.profile
  const checklist: { done: boolean; label: string; to: string }[] = [
    { done: Boolean(p?.experience?.length || p?.projects?.length), label: 'Experience & projects', to: '/profile?tab=facts' },
    { done: Boolean(presence?.linkedin || presence?.website || presence?.portfolio), label: 'LinkedIn & links', to: '/profile?tab=links' },
    { done: Boolean(presence?.github_username), label: 'GitHub', to: '/profile?tab=links' },
    { done: data?.pow?.status === 'done' || !purposes.github, label: 'Proof of work', to: '/profile' },
    { done: Boolean(data?.prefs), label: 'Job preferences', to: '/profile?tab=prefs' },
  ]
  const done = checklist.filter((c) => c.done).length

  const links: { icon: IconName; label: string; href: string | null }[] = [
    { icon: 'linkedin', label: 'LinkedIn', href: presence?.linkedin ?? null },
    { icon: 'github', label: 'GitHub', href: presence?.github_username ? `https://github.com/${presence.github_username}` : null },
    { icon: 'globe', label: 'Website', href: presence?.website ?? presence?.portfolio ?? null },
  ]

  return (
    <aside className="dash-side card">
      <div className="dash-avatar-wrap">
        <span className="dash-avatar">{initials(name)}</span>
        <span className="dash-online" aria-hidden="true" />
      </div>
      <h2 className="dash-name">{name}</h2>
      {me?.email && <p className="tiny muted" style={{ textAlign: 'center', marginTop: 2 }}>{me.email}</p>}
      {(headline || where) && (
        <p className="muted small" style={{ textAlign: 'center' }}>
          {headline ? `Looking for ${headline}` : ''}
          {headline && where ? ' · ' : ''}
          {where ?? ''}
        </p>
      )}
      <div className="dash-links">
        {links.map((l) =>
          l.href ? (
            <a key={l.label} href={l.href} target="_blank" rel="noreferrer" className={`dash-link link-${l.icon}`} aria-label={l.label} title={l.label}>
              <Icon name={l.icon} size={17} />
            </a>
          ) : (
            <Link key={l.label} to="/profile?tab=links" className="dash-link missing" aria-label={`Add ${l.label}`} title={`Add ${l.label}`}>
              <Icon name={l.icon} size={17} />
            </Link>
          ),
        )}
      </div>

      <hr className="divider" />
      <div className="row-between" style={{ marginBottom: 10 }}>
        <h3 className="small" style={{ fontWeight: 650 }}>
          Profile strength
        </h3>
        <span className="tiny muted">
          {done}/{checklist.length}
        </span>
      </div>
      <ol className="dash-checklist">
        {checklist.map((c) => (
          <li key={c.label} className={c.done ? 'done' : ''}>
            <span className="dash-check">{c.done ? <Icon name="check" size={12} stroke={3} /> : null}</span>
            {c.done ? (
              <span>{c.label}</span>
            ) : (
              <Link to={c.to} className="text-link">
                {c.label}
              </Link>
            )}
          </li>
        ))}
      </ol>

      {skills.length > 0 && (
        <>
          <hr className="divider" />
          <h3 className="small" style={{ fontWeight: 650, marginBottom: 10 }}>
            Top skills
          </h3>
          <ul className="chip-list">
            {skills.slice(0, 10).map((s) => (
              <li key={s} className="chip">
                {s}
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  )
}
