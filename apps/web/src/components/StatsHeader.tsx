import type { Profile } from '../types'

export default function StatsHeader({ profile }: { profile: Profile }) {
  const stats = [
    { label: 'Projects', value: profile.total_projects },
    { label: 'Authored commits', value: profile.total_commits },
    { label: 'Lines of own code analyzed', value: profile.meaningful_lines },
    { label: 'Merged PRs to others’ repos', value: profile.external_merged_prs },
  ]

  return (
    <section className="card stats-header">
      <h1>
        <a href={`https://github.com/${profile.username}`} target="_blank" rel="noreferrer">
          @{profile.username}
        </a>
      </h1>
      <div className="stats-grid">
        {stats.map((s) => (
          <div key={s.label} className="stat">
            <span className="stat-value">{s.value.toLocaleString()}</span>
            <span className="stat-label">{s.label}</span>
          </div>
        ))}
      </div>
      {profile.languages.length > 0 && <p className="muted">Mainly writes: {profile.languages.join(' · ')}</p>}
      {profile.analysis_mode === 'limited' && (
        <p className="notice">
          Limited analysis: without a GitHub token only a few repositories and commits could be read. Add a token for
          the full picture.
        </p>
      )}
      <p className="muted small">
        Based on {profile.analyzed_contributions} commits and pull requests whose diffs were read. Lockfiles,
        generated code and merge commits are ignored.
      </p>
    </section>
  )
}
