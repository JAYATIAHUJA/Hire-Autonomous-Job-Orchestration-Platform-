import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getJobFeed, scoreJobOnDemand } from '../api/client'
import type { JobContract, ScoreJobResponse } from '../types'

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobContract[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedLocation, setSelectedLocation] = useState('All')
  const [minLegitimacy, setMinLegitimacy] = useState(0.6)
  const [selectedJob, setSelectedJob] = useState<JobContract | null>(null)

  // Ghost Inspector Modal state
  const [showInspector, setShowInspector] = useState(false)
  const [inspectAge, setInspectAge] = useState(10)
  const [inspectReposts, setInspectReposts] = useState(0)
  const [inspectCompany, setInspectCompany] = useState('Acme Corp')
  const [inspectDomain, setInspectDomain] = useState('acme.io')
  const [inspectSalary, setInspectSalary] = useState('₹12,00,000 - ₹18,00,000 INR')
  const [inspectLayoff, setInspectLayoff] = useState(false)
  const [inspectText, setInspectText] = useState(
    'We are hiring a Backend Engineer to build microservices using Python, FastAPI, PostgreSQL, and Docker. Responsibilities include writing automated unit tests and designing scalable APIs.'
  )
  const [inspectResult, setInspectResult] = useState<ScoreJobResponse | null>(null)
  const [inspectLoading, setInspectLoading] = useState(false)

  useEffect(() => {
    loadJobs()
  }, [minLegitimacy])

  async function loadJobs() {
    setLoading(true)
    setError(null)
    try {
      const data = await getJobFeed(40, 1, minLegitimacy)
      setJobs(data.jobs)
      setTotal(data.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load jobs feed.')
    } finally {
      setLoading(false)
    }
  }

  async function handleInspect(e: React.FormEvent) {
    e.preventDefault()
    setInspectLoading(true)
    try {
      const res = await scoreJobOnDemand({
        posting_age_days: Number(inspectAge),
        repost_count: Number(inspectReposts),
        company_name: inspectCompany,
        company_domain: inspectDomain || null,
        salary_range: inspectSalary || null,
        external_layoff_flag: inspectLayoff,
        raw_description: inspectText,
      })
      setInspectResult(res)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Inspection failed')
    } finally {
      setInspectLoading(false)
    }
  }

  // Filter jobs by search and location
  const filteredJobs = jobs.filter((j) => {
    const q = searchQuery.toLowerCase()
    const matchesSearch =
      !q ||
      j.role.title.toLowerCase().includes(q) ||
      j.company.name.toLowerCase().includes(q) ||
      j.parsed_requirements.primary_skills.some((s) => s.toLowerCase().includes(q))

    const matchesLoc =
      selectedLocation === 'All' ||
      j.role.location.toLowerCase().includes(selectedLocation.toLowerCase())

    return matchesSearch && matchesLoc
  })

  return (
    <div className="jobs-page">
      <header className="jobs-hero">
        <div className="hero-content">
          <div className="badge-row">
            <span className="pill-badge pill-verified">Phase 2: Discovery &amp; NLP Filter</span>
            <span className="pill-badge pill-active">Ghost Score Purging Active</span>
          </div>
          <h1>Verified Tech Jobs Feed</h1>
          <p className="subtitle">
            Autonomous job stream purged of phantom postings, compliance listings, and resume harvesting.
            Every role is evaluated via our calibrated <strong>NLP &amp; Logistic Legitimacy Model</strong>.
          </p>
        </div>

        <button className="btn-inspector" onClick={() => setShowInspector(true)}>
          🔍 Open Ghost Inspector
        </button>
      </header>

      {/* Proof-of-Work Connection Banner */}
      <div className="card pow-connect-banner">
        <div className="pow-banner-content">
          <span className="pow-icon">⚡️</span>
          <div>
            <h4>Apply with Verified GitHub Proof-of-Work</h4>
            <p>
              Pair these ghost-free job listings with an objective, code-backed skills report from Phase 1.
            </p>
          </div>
        </div>
        <Link to="/" className="btn-pow-link">
          Connect GitHub Profile ➔
        </Link>
      </div>

      {/* Metric Cards */}
      <div className="stats-row">
        <div className="card stat-card">
          <span className="stat-num">{jobs.length}</span>
          <span className="stat-desc">Active Filtered Roles ({total} Total)</span>
        </div>
        <div className="card stat-card">
          <span className="stat-num stat-green">100%</span>
          <span className="stat-desc">Ghost-Purged (&lt;700 Score)</span>
        </div>
        <div className="card stat-card">
          <span className="stat-num">0–399</span>
          <span className="stat-desc">Low Risk Quality Band</span>
        </div>
        <div className="card stat-card">
          <span className="stat-num stat-blue">SHA-256</span>
          <span className="stat-desc">Global JD Cache Deduplicated</span>
        </div>
      </div>

      {/* Filter Controls */}
      <section className="card filter-bar">
        <div className="search-input-wrap">
          <input
            type="text"
            placeholder="Search by role, company, or tech stack (e.g. FastAPI, React, Docker)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="location-pills">
          {['All', 'Bengaluru', 'Hyderabad', 'Pune', 'Noida', 'Remote'].map((loc) => (
            <button
              key={loc}
              className={`pill-btn ${selectedLocation === loc ? 'active' : ''}`}
              onClick={() => setSelectedLocation(loc)}
            >
              {loc}
            </button>
          ))}
        </div>

        <div className="legitimacy-filter">
          <label>
            Min. Legitimacy: <strong>{Math.round(minLegitimacy * 100)}%</strong>
          </label>
          <input
            type="range"
            min="0.4"
            max="0.9"
            step="0.05"
            value={minLegitimacy}
            onChange={(e) => setMinLegitimacy(parseFloat(e.target.value))}
          />
        </div>
      </section>

      {/* Jobs Grid */}
      {loading ? (
        <p className="muted">Running autonomous discovery &amp; ghost filter...</p>
      ) : error ? (
        <p className="error">{error}</p>
      ) : filteredJobs.length === 0 ? (
        <p className="muted">No jobs matching your filter criteria.</p>
      ) : (
        <div className="jobs-grid">
          {filteredJobs.map((job) => {
            const isLowRisk = job.ghost_job_metrics.ghost_score < 400
            return (
              <article
                key={job.job_id}
                className="card job-card"
                onClick={() => setSelectedJob(job)}
              >
                <div className="job-card-header">
                  <div>
                    <span className="company-name">{job.company.name}</span>
                    <h3 className="job-title">{job.role.title}</h3>
                  </div>
                  <div
                    className={`ghost-badge ${
                      isLowRisk ? 'ghost-low' : 'ghost-moderate'
                    }`}
                  >
                    <span className="score-num">
                      Score: {job.ghost_job_metrics.ghost_score}
                    </span>
                    <span className="risk-label">
                      {job.ghost_job_metrics.risk_band} Risk
                    </span>
                  </div>
                </div>

                <div className="job-meta-row">
                  <span className="meta-pill">📍 {job.role.location}</span>
                  {job.role.salary_range && (
                    <span className="meta-pill meta-salary">
                      💰 {job.role.salary_range}
                    </span>
                  )}
                  <span className="meta-pill">
                    ⏱ {job.ghost_job_metrics.posting_age_days}d ago
                  </span>
                </div>

                <div className="legit-meter-wrap">
                  <div className="meter-label">
                    <span>Legitimacy Probability</span>
                    <strong>
                      {Math.round(
                        job.ghost_job_metrics.legitimacy_probability * 100
                      )}
                      %
                    </strong>
                  </div>
                  <div className="meter-track">
                    <div
                      className={`meter-fill ${
                        isLowRisk ? 'fill-green' : 'fill-amber'
                      }`}
                      style={{
                        width: `${Math.round(
                          job.ghost_job_metrics.legitimacy_probability * 100
                        )}%`,
                      }}
                    />
                  </div>
                </div>

                {job.parsed_requirements.primary_skills.length > 0 && (
                  <div className="skills-row">
                    {job.parsed_requirements.primary_skills.slice(0, 5).map((skill) => (
                      <span key={skill} className="skill-chip">
                        {skill}
                      </span>
                    ))}
                    {job.parsed_requirements.primary_skills.length > 5 && (
                      <span className="skill-chip-more">
                        +{job.parsed_requirements.primary_skills.length - 5}
                      </span>
                    )}
                  </div>
                )}

                <footer className="job-card-footer">
                  <span className="exp-tag">
                    🎓 {job.parsed_requirements.experience_level}
                  </span>
                  <span className="hash-tag" title="Global JD Cache Hash">
                    # {job.parsed_requirements.raw_description_hash.slice(0, 8)}
                  </span>
                </footer>
              </article>
            )
          })}
        </div>
      )}

      {/* Detail Modal */}
      {selectedJob && (
        <div className="modal-backdrop" onClick={() => setSelectedJob(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <span className="company-name">{selectedJob.company.name}</span>
                <h2>{selectedJob.role.title}</h2>
                <span className="muted">📍 {selectedJob.role.location}</span>
              </div>
              <button
                className="btn-close"
                onClick={() => setSelectedJob(null)}
              >
                ✕
              </button>
            </div>

            <div className="modal-metrics">
              <div className="metric-box">
                <span className="m-label">Ghost Score</span>
                <span
                  className={`m-val ${
                    selectedJob.ghost_job_metrics.ghost_score < 400
                      ? 'stat-green'
                      : 'stat-amber'
                  }`}
                >
                  {selectedJob.ghost_job_metrics.ghost_score} / 999
                </span>
              </div>
              <div className="metric-box">
                <span className="m-label">Legitimacy Probability</span>
                <span className="m-val stat-green">
                  {Math.round(
                    selectedJob.ghost_job_metrics.legitimacy_probability * 100
                  )}
                  %
                </span>
              </div>
              <div className="metric-box">
                <span className="m-label">Posting Age</span>
                <span className="m-val">
                  {selectedJob.ghost_job_metrics.posting_age_days} Days
                </span>
              </div>
              <div className="metric-box">
                <span className="m-label">Compensation</span>
                <span className="m-val">
                  {selectedJob.role.salary_range || 'Disclosed in Interview'}
                </span>
              </div>
            </div>

            <div className="modal-section">
              <h4>Required Tech Stack &amp; Skills</h4>
              <div className="skills-row">
                {selectedJob.parsed_requirements.primary_skills.map((s) => (
                  <span key={s} className="skill-chip">
                    {s}
                  </span>
                ))}
              </div>
            </div>

            <div className="modal-section">
              <h4>Shared Data Contract Details</h4>
              <p className="muted small">
                <strong>Job ID:</strong> {selectedJob.job_id} ·{' '}
                <strong>Cache Hash:</strong>{' '}
                {selectedJob.parsed_requirements.raw_description_hash}
              </p>
            </div>

            <div className="modal-actions">
              <button
                className="btn-primary"
                onClick={() =>
                  alert(
                    `Job payload ${selectedJob.job_id} ready for Student A RAG Tailoring & Student C Swipe!`
                  )
                }
              >
                🚀 Apply with Proof-of-Work
              </button>
              <button
                className="btn-secondary"
                onClick={() => setSelectedJob(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Ghost Inspector Modal */}
      {showInspector && (
        <div className="modal-backdrop" onClick={() => setShowInspector(false)}>
          <div
            className="modal-card inspector-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <h2>🕵️‍♂️ Real-Time Ghost Job Inspector</h2>
                <p className="muted">
                  Test any external job posting against our quantitative ML &amp; NLP
                  filter.
                </p>
              </div>
              <button
                className="btn-close"
                onClick={() => setShowInspector(false)}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleInspect} className="inspector-form">
              <div className="form-grid">
                <label>
                  Company Name
                  <input
                    value={inspectCompany}
                    onChange={(e) => setInspectCompany(e.target.value)}
                    required
                  />
                </label>
                <label>
                  Company Domain
                  <input
                    value={inspectDomain}
                    onChange={(e) => setInspectDomain(e.target.value)}
                  />
                </label>
                <label>
                  Posting Age (Days)
                  <input
                    type="number"
                    value={inspectAge}
                    onChange={(e) => setInspectAge(Number(e.target.value))}
                    min="0"
                  />
                </label>
                <label>
                  Repost Frequency
                  <input
                    type="number"
                    value={inspectReposts}
                    onChange={(e) => setInspectReposts(Number(e.target.value))}
                    min="0"
                  />
                </label>
                <label>
                  Salary Range Disclosed
                  <input
                    value={inspectSalary}
                    onChange={(e) => setInspectSalary(e.target.value)}
                    placeholder="e.g. ₹12,00,000 - ₹18,00,000"
                  />
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={inspectLayoff}
                    onChange={(e) => setInspectLayoff(e.target.checked)}
                  />
                  Company undergoing active layoffs / WARN notice
                </label>
              </div>

              <label>
                Job Description Text
                <textarea
                  rows={4}
                  value={inspectText}
                  onChange={(e) => setInspectText(e.target.value)}
                  required
                />
              </label>

              <button
                type="submit"
                className="btn-primary"
                disabled={inspectLoading}
              >
                {inspectLoading ? 'Evaluating Red Flags...' : 'Analyze Posting'}
              </button>
            </form>

            {inspectResult && (
              <div
                className={`card inspect-result ${
                  inspectResult.is_ghost ? 'result-ghost' : 'result-legit'
                }`}
              >
                <div className="result-header">
                  <div>
                    <h3>
                      {inspectResult.is_ghost
                        ? '🚨 High-Risk Ghost Job Detected'
                        : '✅ Verified Active Hiring Intent'}
                    </h3>
                    <p className="muted">
                      Risk Band:{' '}
                      <strong>{inspectResult.risk_band}</strong> · Legitimacy
                      Probability:{' '}
                      <strong>
                        {Math.round(
                          inspectResult.legitimacy_probability * 100
                        )}
                        %
                      </strong>
                    </p>
                  </div>
                  <span className="big-score">
                    {inspectResult.ghost_score} / 999
                  </span>
                </div>

                <div className="signals-breakdown">
                  <div className="sig-item">
                    <span>Posting Age Penalty (X_age):</span>
                    <strong>{inspectResult.features.x_age}</strong>
                  </div>
                  <div className="sig-item">
                    <span>Repost Penalty (X_repost):</span>
                    <strong>{inspectResult.features.x_repost}</strong>
                  </div>
                  <div className="sig-item">
                    <span>TF-IDF Specificity (X_quality):</span>
                    <strong>{inspectResult.features.x_quality}</strong>
                  </div>
                  <div className="sig-item">
                    <span>Salary Transparency (X_salary):</span>
                    <strong>{inspectResult.features.x_salary}</strong>
                  </div>
                  <div className="sig-item">
                    <span>Downsizing/Layoff Signal (X_news):</span>
                    <strong>{inspectResult.features.x_news}</strong>
                  </div>
                  {inspectResult.features.layoff_detail && (
                    <p className="error small">
                      ⚠️ {inspectResult.features.layoff_detail}
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
