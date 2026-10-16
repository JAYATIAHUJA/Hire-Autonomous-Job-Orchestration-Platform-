import type { Skill } from '../types'
import ContributionItem from './ContributionItem'

function plural(n: number, word: string) {
  return `${n.toLocaleString()} ${word}${n === 1 ? '' : 's'}`
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
        {plural(skill.contribution_count, 'contribution')} · {plural(skill.project_count, 'project')} ·{' '}
        {plural(skill.lines, 'line')}
        {skill.external_pr_count > 0 && <> · {plural(skill.external_pr_count, 'merged external PR')}</>}
      </p>

      {skill.detected_via.length > 0 && (
        <ul className="chips" aria-label="Detected via">
          {skill.detected_via.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}

      <details className="factors">
        <summary>Why {skill.confidence_tier.toLowerCase()}?</summary>
        <ul>
          {skill.factors.map((f) => (
            <li key={f.label} className={f.met ? 'met' : 'unmet'}>
              <span aria-hidden>{f.met ? '✓' : '✗'}</span> <strong>{f.label}</strong>
              <span className="muted"> — {f.detail}</span>
            </li>
          ))}
        </ul>
      </details>

      {skill.highlights.length > 0 && (
        <>
          <h4>Proof</h4>
          <ul className="contribution-list">
            {skill.highlights.map((c) => (
              <ContributionItem key={c.url} contribution={c} />
            ))}
          </ul>
        </>
      )}
    </article>
  )
}
