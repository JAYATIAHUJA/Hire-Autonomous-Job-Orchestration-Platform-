import type { Profile } from '../types'

export default function StatsHeader({ profile }: { profile: Profile }) {
  const stats = [
    { label: 'Repos analyzed', value: profile.total_repos },
    { label: 'Authored commits', value: profile.total_commits },
    { label: 'Lines added (est.)', value: profile.total_additions },
    { label: 'Lines removed (est.)', value: profile.total_deletions },
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
      {profile.languages.length > 0 && <p className="muted">Primary languages: {profile.languages.join(' · ')}</p>}
    </section>
  )
}
