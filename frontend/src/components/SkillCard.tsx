import type { Skill } from '../types'

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

export default function SkillCard({ skill }: { skill: Skill }) {
  return (
    <article className="card skill-card">
      <header>
        <h3>{skill.name}</h3>
        <span className={`tier-badge tier-${skill.confidence_tier.toLowerCase()}`}>
          {skill.confidence_tier} evidence
        </span>
      </header>

      <p className="skill-summary">
        {plural(skill.repo_count, 'repo')} · {plural(skill.commit_count, 'commit')} · {plural(skill.pr_count, 'PR')}
        {skill.first_active && skill.last_active && (
          <>
            {' · '}
            {new Date(skill.first_active).getFullYear()}–{new Date(skill.last_active).toLocaleDateString()}
          </>
        )}
      </p>

      <ul className="evidence-list">
        {skill.evidence.map((ev) => (
          <li key={ev.repo_full_name}>
            <a href={ev.repo_url} target="_blank" rel="noreferrer">
              {ev.repo_full_name}
            </a>
            <span className="muted"> — {plural(ev.commit_count, 'commit')}, {plural(ev.pr_count, 'PR')}</span>
            {ev.sample_commit_url && (
              <div className="sample-commit">
                <a href={ev.sample_commit_url} target="_blank" rel="noreferrer">
                  {ev.sample_commit_message || 'View commit'}
                </a>
              </div>
            )}
          </li>
        ))}
      </ul>
    </article>
  )
}
