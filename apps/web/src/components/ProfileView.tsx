import { useState } from 'react'
import type { Profile } from '../types'
import { Alert } from '../ui/kit'
import CommitTimelineChart from './CommitTimelineChart'
import ContributionItem from './ContributionItem'
import ProjectsTable from './ProjectsTable'
import SkillCard from './SkillCard'
import WorkMixBar from './WorkMixBar'

// The analysed GitHub profile: what you built, and the skills it proves.
export default function ProfileView({ profile }: { profile: Profile }) {
  const [allTop, setAllTop] = useState(false)
  const top = allTop ? profile.top_contributions : profile.top_contributions.slice(0, 5)
  const stats = [
    { label: 'Projects', value: profile.total_projects },
    { label: 'Your commits', value: profile.total_commits },
    { label: 'Lines you wrote', value: profile.meaningful_lines },
    { label: 'PRs merged elsewhere', value: profile.external_merged_prs },
  ]

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="stats">
        {stats.map((s) => (
          <div key={s.label}>
            <span className="v">{s.value.toLocaleString('en-IN')}</span>
            <span className="l">{s.label}</span>
          </div>
        ))}
      </div>

      <p className="muted small">
        From{' '}
        <a href={`https://github.com/${profile.username}`} target="_blank" rel="noreferrer" className="text-link">
          @{profile.username}
        </a>
        {profile.languages.length > 0 && <> · mostly {profile.languages.slice(0, 4).join(', ')}</>} · based on{' '}
        {profile.analyzed_contributions} commits and pull requests whose changes we read. Lockfiles, generated code and
        merges are ignored.
      </p>

      {profile.analysis_mode === 'limited' && (
        <Alert tone="warn">
          This is a limited analysis: without a GitHub token we could only read a few repositories. Link GitHub (or set{' '}
          <code>GITHUB_APP_TOKEN</code>) and run it again for the full picture.
        </Alert>
      )}

      {profile.top_contributions.length > 0 && (
        <section className="card card-pad">
          <h3>Your strongest proof</h3>
          <p className="muted small" style={{ margin: '4px 0 6px' }}>
            The contributions we lead with when you apply.
          </p>
          <ul className="contribution-list">
            {top.map((c) => (
              <ContributionItem key={c.url} contribution={c} />
            ))}
          </ul>
          {profile.top_contributions.length > 5 && (
            <button type="button" className="link-btn small" style={{ marginTop: 8 }} onClick={() => setAllTop((v) => !v)}>
              {allTop ? 'Show fewer' : `Show all ${profile.top_contributions.length}`}
            </button>
          )}
        </section>
      )}

      <div className="grid grid-2">
        <WorkMixBar mix={profile.work_mix} />
        <CommitTimelineChart timeline={profile.timeline} />
      </div>

      <ProjectsTable projects={profile.projects} />

      <section style={{ marginTop: 12 }}>
        <div className="section-head">
          <div>
            <h2>Skills, with the receipts</h2>
            <p className="muted small">
              Found only in changes you made: files you touched, libraries you imported, dependencies you added. The
              level shows how much evidence there is, not how good you are.
            </p>
          </div>
        </div>
        {profile.skills.length === 0 ? (
          <p className="muted">No skill evidence in the analysed contributions yet.</p>
        ) : (
          <div className="skill-grid">
            {profile.skills.map((skill) => (
              <SkillCard key={skill.name} skill={skill} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
