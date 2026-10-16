import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon, { type IconName } from '../ui/Icon'
import '../landing.css'

// The public website: what Hire is, with live numbers from the job discovery.

type Stats = { live_jobs: number; companies_hiring: number; boards_tracked: number; ghosts_filtered: number }

function usePublicStats(): Stats | null {
  const [stats, setStats] = useState<Stats | null>(null)
  useEffect(() => {
    fetch('/v1/public/stats')
      .then((r) => (r.ok ? r.json() : null))
      .then(setStats)
      .catch(() => setStats(null))
  }, [])
  return stats
}

const fmt = (n: number) => n.toLocaleString('en-IN')
const round = (n: number) => (n >= 1000 ? `${fmt(Math.floor(n / 100) * 100)}+` : fmt(n))

const TIMELINE = [
  ['01', 'Drop in your resume'],
  ['02', 'We pull out everything'],
  ['03', 'Polish it once'],
  ['04', 'Swipe real jobs'],
  ['05', 'Reach out in your voice'],
  ['06', 'Track every reply'],
]

const STEPS: { icon: IconName; tone: string; title: string; body: string }[] = [
  { icon: 'file', tone: 'lilac', title: 'Your profile, built for you', body: 'Upload one resume or five. We extract your roles, pointers, projects and links into one profile you polish once.' },
  { icon: 'deck', tone: 'sky', title: 'A deck of real jobs', body: 'Openings straight from company careers pages, ghost-checked, and ranked by how well they fit you.' },
  { icon: 'mail', tone: 'butter', title: 'Reach out, not just apply', body: 'For every job you like, we draft a short, specific note to the recruiter from your actual work.' },
  { icon: 'board', tone: 'peach', title: 'Every reply, one board', body: 'Applied, interviewing, closed. Each card keeps a signed record of what you agreed to send.' },
]

const FAQ = [
  ['Where do the jobs come from?', 'From the official careers pages of 660+ companies hiring in India (their public Greenhouse, Lever and Ashby job boards), plus remote roles open to India. We check them every 30 minutes, and every job links to the original posting.'],
  ['What is a ghost job?', 'A listing with no real intent to hire: reposted for months, vague, no salary, at a company in layoff news. We score every listing on these signals and hide the likely ghosts.'],
  ['Does Hire apply without asking me?', 'Never. A right swipe is your consent for that one employer, recorded with a signed receipt. Nothing is sent without it.'],
  ['Is it free?', 'Yes, for students and engineers job hunting in India.'],
  ['What happens to my data?', 'You choose what we may use (GitHub, resume) on day one, and can change or delete it any time. We never sell it.'],
]

export default function LandingPage() {
  const stats = usePublicStats()
  const [open, setOpen] = useState<number | null>(0)

  return (
    <div className="lp">
      <header className="lp-nav">
        <Link to="/" className="lp-brand">
          <span className="brand-mark" aria-hidden="true" />
          hire
        </Link>
        <nav className="lp-links" aria-label="Sections">
          <a href="#how">How it works</a>
          <a href="#numbers">Live numbers</a>
          <a href="#faq">FAQ</a>
        </nav>
        <div className="row" style={{ gap: 8 }}>
          <Link to="/login" className="lp-btn ghost">
            Sign in
          </Link>
          <Link to="/login" className="lp-btn solid">
            Get started
          </Link>
        </div>
      </header>

      {/* ---- Hero: dark, an orange glow, a poster-style run sheet -------------------- */}
      <section className="lp-hero">
        <div className="lp-glow" aria-hidden="true" />
        <div className="lp-ring" aria-hidden="true" />
        <span className="lp-code" aria-hidden="true">
          HR—26
        </span>

        <div className="lp-hero-copy">
          <span className="lp-live">
            <span className="lp-live-dot" aria-hidden="true" />
            {stats ? `${fmt(stats.live_jobs)} live jobs · checked every 30 min` : 'Live jobs · checked every 30 min'}
          </span>
          <h1 className="lp-title">
            Apply to <span className="lp-under">real</span> jobs.
            <span className="serif lp-title-accent">Skip the ghosts.</span>
          </h1>
          <p className="lp-sub">
            Hire turns your resume into a profile once, deals you real openings from company careers pages, and helps you
            reach the people hiring. Swipe right to apply. You approve everything.
          </p>
          <div className="row" style={{ gap: 12 }}>
            <Link to="/login" className="lp-btn solid lg">
              Start free
              <Icon name="arrowRight" size={18} />
            </Link>
            <a href="#how" className="lp-btn outline lg">
              See how it works
            </a>
          </div>
        </div>

        <div className="lp-poster" aria-label="How Hire works, step by step">
          <ol className="lp-run">
            {TIMELINE.map(([n, label], i) => (
              <li key={n} style={{ marginLeft: `${i * 7}%`, animationDelay: `${0.15 + i * 0.09}s` }}>
                <span className="lp-run-n">{n}</span>
                {label}
              </li>
            ))}
          </ol>
          <div className="lp-cards" aria-hidden="true">
            <div className="lp-card back">
              <div className="lp-card-co">
                <span className="logo-tile sm">Z</span>
                <span>
                  <strong>Data Engineer</strong>
                  <small>Hyderabad · 88% real</small>
                </span>
              </div>
            </div>
            <div className="lp-card front">
              <span className="deck-stamp apply" style={{ top: 14, left: 'auto', right: 14 }}>
                APPLY
              </span>
              <div className="lp-card-co">
                <span className="logo-tile sm">A</span>
                <span>
                  <strong>Backend Engineer</strong>
                  <small>Bengaluru · 94% real</small>
                </span>
              </div>
              <div className="chip-list" style={{ marginTop: 12 }}>
                <span className="chip match-chip">✓ Matches you</span>
                <span className="chip">Go</span>
                <span className="chip">Postgres</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="lp-marquee" aria-hidden="true">
        <div className="lp-marquee-track">
          {Array.from({ length: 2 }).map((_, k) => (
            <span key={k}>
              REAL JOBS ✦ GHOST-CHECKED ✦ GREENHOUSE ✦ LEVER ✦ ASHBY ✦ PROOF OF WORK ✦ SIGNED CONSENT ✦ ONE PROFILE ✦ REACH OUT ✦
              TRACK REPLIES ✦&nbsp;
            </span>
          ))}
        </div>
      </div>

      {/* ---- Live numbers ------------------------------------------------------------ */}
      <section className="lp-section" id="numbers">
        <div className="lp-numbers">
          <div>
            <span className="lp-num">{stats ? round(stats.live_jobs) : '—'}</span>
            <span className="lp-num-label">live jobs right now</span>
          </div>
          <div>
            <span className="lp-num">{stats ? round(stats.companies_hiring) : '—'}</span>
            <span className="lp-num-label">companies hiring</span>
          </div>
          <div>
            <span className="lp-num">{stats ? round(stats.ghosts_filtered) : '—'}</span>
            <span className="lp-num-label">ghost jobs filtered out</span>
          </div>
        </div>
        <p className="lp-note">Counted live from our job discovery, not made up for a slide.</p>
      </section>

      {/* ---- How it works -------------------------------------------------------------- */}
      <section className="lp-section" id="how">
        <span className="eyebrow">
          <span className="eyebrow-dot" aria-hidden="true" />
          How it works
        </span>
        <h2 className="lp-h2">
          One profile. Real jobs. <span className="serif">Your call, every time.</span>
        </h2>
        <div className="lp-steps">
          {STEPS.map((s, i) => (
            <article key={s.title} className={`lp-step tone-${s.tone}`}>
              <span className="lp-step-n">0{i + 1}</span>
              <span className="lp-step-icon">
                <Icon name={s.icon} size={20} />
              </span>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ---- FAQ ----------------------------------------------------------------------------- */}
      <section className="lp-section lp-faq-wrap" id="faq">
        <h2 className="lp-h2">Questions, answered</h2>
        <div className="lp-faq">
          {FAQ.map(([q, a], i) => (
            <div key={q} className={`lp-faq-item${open === i ? ' open' : ''}`}>
              <button type="button" onClick={() => setOpen(open === i ? null : i)} aria-expanded={open === i}>
                {q}
                <Icon name={open === i ? 'x' : 'plus'} size={16} />
              </button>
              {open === i && <p>{a}</p>}
            </div>
          ))}
        </div>
      </section>

      {/* ---- Closing call to action ------------------------------------------------------- */}
      <section className="lp-cta">
        <div className="lp-glow small" aria-hidden="true" />
        <h2>
          Let’s find your <span className="serif">next role.</span>
        </h2>
        <p>Three minutes to set up. Your first deck is waiting.</p>
        <Link to="/login" className="lp-btn solid lg">
          Get started free
          <Icon name="arrowRight" size={18} />
        </Link>
      </section>

      <footer className="lp-foot">
        <span className="lp-brand dark">
          <span className="brand-mark" aria-hidden="true" />
          hire
        </span>
        <span className="muted small">Real jobs, real proof. Made in India.</span>
        <Link to="/privacy" className="small text-link">
          Privacy
        </Link>
      </footer>
    </div>
  )
}
