import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getJobFeed, scoreJobOnDemand, swipeJob } from '../api/client'
import DiscoveryPanel from '../components/DiscoveryPanel'
import JobSheet from '../components/JobSheet'
import type { JobContract, ScoreJobResponse } from '../types'
import Icon from '../ui/Icon'
import { ago, Alert, EmptyState, errorMessage, LogoTile, Meter, PageHeader, useToast } from '../ui/kit'
import { relativeTime, sourceName } from '../ui/source'
import { health, SIGNALS, trustOf } from '../ui/trust'

const STRICTNESS = [
  { value: 0.6, label: 'Probably real (60%+)' },
  { value: 0.8, label: 'Very likely real (80%+)' },
  { value: 0.4, label: 'Show everything' },
] as const

const SORTS = [
  { value: 'match', label: 'Best match for me' },
  { value: 'newest', label: 'Newest' },
  { value: 'trust', label: 'Most trusted' },
]

const LEVELS = [
  { value: 'intern,entry', label: 'Intern / Fresher' },
  { value: 'entry', label: '0–2 years' },
  { value: 'mid', label: '2–5 years' },
  { value: 'senior', label: '5+ years' },
]

const POSTED = [
  { value: 1, label: 'Last 24 hours' },
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
]

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <label className={`filter${value ? ' on' : ''}`}>
      <span className="filter-label">{label}</span>
      <select className="filter-select" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}

const CITIES = ['Bengaluru', 'Hyderabad', 'Pune', 'Mumbai', 'Gurugram', 'Noida', 'Chennai', 'Delhi']
const PAGE = 30

export default function JobsPage() {
  const toast = useToast()
  const [jobs, setJobs] = useState<JobContract[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [more, setMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [params] = useSearchParams()
  const [query, setQuery] = useState(() => params.get('q') ?? '')
  const [debounced, setDebounced] = useState(() => params.get('q') ?? '')
  const [city, setCity] = useState<string | null>(null)
  const [remote, setRemote] = useState(false)
  const [sort, setSort] = useState<'match' | 'newest' | 'trust'>('match')
  const [level, setLevel] = useState('')
  const [salaryShown, setSalaryShown] = useState(false)
  const [postedWithin, setPostedWithin] = useState(0)
  const [minLegit, setMinLegit] = useState<number>(0.6)
  const [selected, setSelected] = useState<JobContract | null>(null)
  const [applied, setApplied] = useState<Set<string>>(new Set())
  const [applying, setApplying] = useState(false)
  const [checker, setChecker] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  // Search as you type, without a request per keystroke.
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query), 300)
    return () => window.clearTimeout(id)
  }, [query])

  const filters = useMemo(
    () => ({
      q: debounced,
      city: city ?? undefined,
      remote,
      sort,
      level: level || undefined,
      salaryShown,
      postedWithin: postedWithin || undefined,
    }),
    [debounced, city, remote, sort, level, salaryShown, postedWithin],
  )

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getJobFeed(PAGE, 1, minLegit, filters)
      .then((data) => {
        if (cancelled) return
        setJobs(data.jobs)
        setTotal(data.total)
        setPage(1)
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, 'Could not load jobs.'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [minLegit, filters, reloadKey])

  async function loadMore() {
    setMore(true)
    try {
      const data = await getJobFeed(PAGE, page + 1, minLegit, filters)
      setJobs((all) => [...all, ...data.jobs.filter((j) => !all.some((x) => x.job_id === j.job_id))])
      setPage((p) => p + 1)
    } catch (err) {
      toast.show('Could not load more jobs', errorMessage(err, 'Try again.'))
    } finally {
      setMore(false)
    }
  }

  async function apply(job: JobContract) {
    setApplying(true)
    try {
      const res = await swipeJob(job.job_id, 'right')
      setApplied((prev) => new Set(prev).add(job.job_id))
      toast.show(
        res.already_recorded ? `${job.company.name} is already on your list` : `Saved: ${job.role.title}`,
        'Nothing is sent yet. Finish applying on the company’s site, then mark it applied on your pipeline.',
        job.source?.apply_url ? { label: 'Apply now ↗', href: job.source.apply_url } : undefined,
      )
      setSelected(null)
    } catch (err) {
      toast.show('Could not apply', errorMessage(err, 'Try again in a moment.'))
    } finally {
      setApplying(false)
    }
  }

  const filtered = Boolean(debounced || city || remote || level || salaryShown || postedWithin)
  const where = remote ? 'remote' : city ?? ''

  function clearAll() {
    setQuery('')
    setCity(null)
    setRemote(false)
    setLevel('')
    setSalaryShown(false)
    setPostedWithin(0)
  }

  // What's applied, as removable chips.
  const active: { label: string; clear: () => void }[] = [
    ...(debounced ? [{ label: `“${debounced}”`, clear: () => setQuery('') }] : []),
    ...(city ? [{ label: city, clear: () => setCity(null) }] : []),
    ...(remote ? [{ label: 'Remote', clear: () => setRemote(false) }] : []),
    ...(level ? [{ label: LEVELS.find((l) => l.value === level)?.label ?? level, clear: () => setLevel('') }] : []),
    ...(salaryShown ? [{ label: 'Salary shown', clear: () => setSalaryShown(false) }] : []),
    ...(postedWithin ? [{ label: POSTED.find((x) => x.value === postedWithin)?.label ?? '', clear: () => setPostedWithin(0) }] : []),
  ]

  return (
    <div className="page">
      <PageHeader
        eyebrow="All jobs"
        title="Every live opening we found"
        lede="Straight from company careers pages. Search, filter, open one to read the full posting and why we trust it, and apply from there."
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => setChecker(true)}>
            <Icon name="ghost" size={16} />
            Check any job posting
          </button>
        }
      />

      <DiscoveryPanel onFound={() => setReloadKey((k) => k + 1)} />

      <section className="filter-bar" aria-label="Filters">
        <Select label="Sort" value={sort} onChange={(v) => setSort(v as typeof sort)} options={SORTS} />
        <Select
          label="Location"
          value={where}
          onChange={(v) => {
            setRemote(v === 'remote')
            setCity(v && v !== 'remote' ? v : null)
          }}
          options={[{ value: '', label: 'Anywhere' }, { value: 'remote', label: 'Remote' }, ...CITIES.map((c) => ({ value: c, label: c }))]}
        />
        <Select label="Experience" value={level} onChange={setLevel} options={[{ value: '', label: 'Any level' }, ...LEVELS]} />
        <Select
          label="Salary"
          value={salaryShown ? 'shown' : ''}
          onChange={(v) => setSalaryShown(v === 'shown')}
          options={[{ value: '', label: 'Any' }, { value: 'shown', label: 'Salary shown' }]}
        />
        <Select
          label="Posted"
          value={String(postedWithin)}
          onChange={(v) => setPostedWithin(Number(v))}
          options={[{ value: '0', label: 'Any time' }, ...POSTED.map((x) => ({ value: String(x.value), label: x.label }))]}
        />
        <label className="search filter-search">
          <Icon name="search" size={15} />
          <span className="visually-hidden">Role or company</span>
          <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Role or company" />
        </label>
      </section>

      <div className="row-between" style={{ marginBottom: 10, alignItems: 'center' }}>
        <div className="row" style={{ gap: 6 }}>
          <span className="muted small">
            {loading ? 'Loading…' : `${total.toLocaleString('en-IN')} job${total === 1 ? '' : 's'}${filtered ? ' match' : ''}`}
          </span>
          {active.map((f) => (
            <button key={f.label} type="button" className="chip chip-outline" style={{ cursor: 'pointer' }} onClick={f.clear}>
              {f.label}
              <Icon name="x" size={11} />
            </button>
          ))}
          {active.length > 1 && (
            <button type="button" className="link-btn small" onClick={clearAll}>
              Clear all
            </button>
          )}
        </div>
        <label className="row small muted" style={{ gap: 8 }}>
          Hide likely ghosts
          <select className="select" style={{ minHeight: 32, padding: '4px 30px 4px 10px', width: 'auto', fontSize: '0.82rem' }} value={minLegit} onChange={(e) => setMinLegit(Number(e.target.value))}>
            {STRICTNESS.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <Alert tone="error">{error}</Alert>}

      {loading ? (
        <div className="card" style={{ padding: 8 }}>
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton" style={{ height: 60, margin: 10 }} />
          ))}
        </div>
      ) : jobs.length === 0 ? (
        <div className="card">
          <EmptyState
            icon="search"
            title={filtered ? 'Nothing matches' : 'No jobs yet'}
            actions={
              filtered ? (
                <button type="button" className="btn btn-secondary" onClick={() => { setQuery(''); setCity(null); setRemote(false) }}>
                  Clear filters
                </button>
              ) : undefined
            }
          >
            {filtered ? 'Try another search or place.' : 'Use “Check now” above to read the company boards.'}
          </EmptyState>
        </div>
      ) : (
        <>
          <ul className="card job-list" style={{ overflow: 'hidden' }}>
            {jobs.map((job) => {
              const trust = trustOf(job.ghost_job_metrics)
              return (
                <li key={job.job_id}>
                  <button type="button" className="job-row" onClick={() => setSelected(job)}>
                    <LogoTile name={job.company.name} small />
                    <span style={{ minWidth: 0 }}>
                      <span className="job-row-title">
                        {job.role.title}
                        {job.match && job.match.percent > 0 && <span className="match-percent row-match">{job.match.percent}% match</span>}
                      </span>
                      <span className="job-row-meta">
                        <span>{job.company.name}</span>
                        <span>
                          <Icon name="pin" size={13} />
                          {job.role.location}
                        </span>
                        {job.role.salary_range && (
                          <span>
                            <Icon name="wallet" size={13} />
                            {job.role.salary_range}
                          </span>
                        )}
                      </span>
                    </span>
                    <span className="job-row-right">
                      {applied.has(job.job_id) ? (
                        <span className="badge badge-ink badge-plain">
                          <Icon name="check" size={12} stroke={3} /> Saved
                        </span>
                      ) : (
                        <span className={`badge badge-${trust.tone}`}>{trust.percent}% real</span>
                      )}
                      <span className="tiny muted">
                        {relativeTime(job.source?.posted_at) || ago(job.ghost_job_metrics.posting_age_days)} · {sourceName(job)}
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
          {jobs.length < total && (
            <div className="row" style={{ justifyContent: 'center', marginTop: 16 }}>
              <button type="button" className="btn btn-secondary" onClick={loadMore} disabled={more}>
                {more ? 'Loading…' : `Show more (${(total - jobs.length).toLocaleString('en-IN')} left)`}
              </button>
            </div>
          )}
        </>
      )}

      {selected && (
        <JobSheet
          job={selected}
          onClose={() => setSelected(null)}
          actions={
            applied.has(selected.job_id) ? (
              <button type="button" className="btn btn-secondary btn-lg" onClick={() => setSelected(null)}>
                Saved · close
              </button>
            ) : (
              <>
                <button type="button" className="btn btn-secondary btn-lg" onClick={() => setSelected(null)}>
                  Not now
                </button>
                <button type="button" className="btn btn-primary btn-lg" disabled={applying} onClick={() => apply(selected)}>
                  <Icon name="check" size={16} />
                  {applying ? 'Saving…' : 'Save to apply'}
                </button>
              </>
            )
          }
        />
      )}

      {checker && <PostingChecker onClose={() => setChecker(false)} />}
    </div>
  )
}

/* ---- Check a job posting from anywhere -------------------------------------------- */

function PostingChecker({ onClose }: { onClose: () => void }) {
  const [company, setCompany] = useState('')
  const [domain, setDomain] = useState('')
  const [age, setAge] = useState('7')
  const [reposts, setReposts] = useState('0')
  const [salary, setSalary] = useState('')
  const [layoffs, setLayoffs] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ScoreJobResponse | null>(null)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      setResult(
        await scoreJobOnDemand({
          posting_age_days: Number(age) || 0,
          repost_count: Number(reposts) || 0,
          company_name: company,
          company_domain: domain || null,
          salary_range: salary || null,
          external_layoff_flag: layoffs,
          raw_description: text,
        }),
      )
    } catch (err) {
      setError(errorMessage(err, 'Could not check this posting.'))
    } finally {
      setBusy(false)
    }
  }

  const percent = result ? Math.round(result.legitimacy_probability * 100) : 0
  const tone = result ? (result.is_ghost ? 'bad' : percent >= 75 ? 'good' : 'warn') : 'good'

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <aside className="sheet" role="dialog" aria-modal="true" aria-labelledby="checker-title" onClick={(e) => e.stopPropagation()}>
        <header className="sheet-head">
          <div>
            <h2 id="checker-title">Is this job real?</h2>
            <p className="muted small" style={{ marginTop: 4 }}>
              Paste a posting from LinkedIn, Naukri or anywhere. We run it through the same filter as your deck.
            </p>
          </div>
          <button type="button" className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close">
            <Icon name="x" size={18} />
          </button>
        </header>
        <div className="sheet-body">
          <form className="form" onSubmit={onSubmit}>
            <label className="field">
              <span className="field-label">Job description</span>
              <textarea
                className="textarea"
                rows={6}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste the full description here"
                required
              />
            </label>
            <div className="grid grid-2" style={{ gap: 12 }}>
              <label className="field">
                <span className="field-label">Company</span>
                <input className="input" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Acme" required />
              </label>
              <label className="field">
                <span className="field-label">
                  Website<span className="optional">optional</span>
                </span>
                <input className="input" value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="acme.com" />
              </label>
              <label className="field">
                <span className="field-label">Days since posted</span>
                <input className="input" type="number" min={0} value={age} onChange={(e) => setAge(e.target.value)} />
              </label>
              <label className="field">
                <span className="field-label">Times reposted</span>
                <input className="input" type="number" min={0} value={reposts} onChange={(e) => setReposts(e.target.value)} />
              </label>
            </div>
            <label className="field">
              <span className="field-label">
                Salary shown<span className="optional">optional</span>
              </span>
              <input className="input" value={salary} onChange={(e) => setSalary(e.target.value)} placeholder="₹12–18 LPA" />
            </label>
            <label className={`switch-row${layoffs ? ' on' : ''}`}>
              <span className="switch-row-text">
                <strong>The company has had layoffs recently</strong>
                <span>Hiring “intent” is often paused during cuts.</span>
              </span>
              <input type="checkbox" role="switch" className="switch" checked={layoffs} onChange={(e) => setLayoffs(e.target.checked)} />
            </label>
            {error && <Alert tone="error">{error}</Alert>}
            <button type="submit" className="btn btn-primary btn-lg" disabled={busy || !text.trim() || !company.trim()}>
              {busy ? 'Checking…' : 'Check this posting'}
            </button>
          </form>

          {result && (
            <section className={`verdict ${tone}`} style={{ flexDirection: 'column', alignItems: 'stretch' }} aria-live="polite">
              <div className="row-between">
                <div>
                  <h3>{result.is_ghost ? 'Looks like a ghost job' : percent >= 75 ? 'Looks like real hiring' : 'Could go either way'}</h3>
                  <p className="small" style={{ color: 'var(--ink-2)', marginTop: 2 }}>
                    {percent}% chance they’re actively hiring for this role.
                  </p>
                </div>
                <span className="big-number">{percent}%</span>
              </div>
              <div className="score-explain" style={{ marginTop: 8 }}>
                {SIGNALS.map((s) => {
                  const h = health(result.features[s.key], s.higherIsBetter)
                  return (
                    <div key={s.key} className="signal">
                      <span>{s.label}</span>
                      <Meter value={h} tone={h >= 60 ? 'good' : h >= 30 ? 'warn' : 'accent'} />
                    </div>
                  )
                })}
              </div>
              {result.features.layoff_detail && (
                <p className="small" style={{ marginTop: 8, color: 'var(--bad-ink)' }}>
                  {result.features.layoff_detail}
                </p>
              )}
            </section>
          )}
        </div>
      </aside>
    </div>
  )
}
