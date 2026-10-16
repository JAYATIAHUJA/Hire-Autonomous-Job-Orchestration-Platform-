import { useState } from 'react'
import type { Skill } from '../types'
import Icon from '../ui/Icon'
import ContributionItem from './ContributionItem'

function plural(n: number, word: string) {
  return `${n.toLocaleString('en-IN')} ${word}${n === 1 ? '' : 's'}`
}

const TIER_TONE: Record<string, string> = { Strong: 'badge-good', Moderate: 'badge-warn', Limited: 'badge-neutral' }

export default function SkillCard({ skill }: { skill: Skill }) {
  const [open, setOpen] = useState(false)
  return (
    <article className={`card skill-card${open ? ' open' : ''}`}>
      <header>
        <h3>{skill.name}</h3>
        <span className={`badge ${TIER_TONE[skill.confidence_tier] ?? 'badge-neutral'}`}>{skill.confidence_tier} evidence</span>
      </header>

      <p className="skill-summary">
        {plural(skill.contribution_count, 'contribution')} · {plural(skill.project_count, 'project')} · {plural(skill.lines, 'line')}
        {skill.external_pr_count > 0 && <> · {plural(skill.external_pr_count, 'merged PR')} elsewhere</>}
      </p>

      {skill.detected_via.length > 0 && (
        <ul className="chip-list" aria-label="Detected via">
          {skill.detected_via.slice(0, 2).map((reason) => (
            <li key={reason} className="chip">
              {reason}
            </li>
          ))}
        </ul>
      )}

      <details className="factors">
        <summary>Why “{skill.confidence_tier.toLowerCase()}”?</summary>
        <ul>
          {skill.factors.map((f) => (
            <li key={f.label} className={f.met ? 'met' : 'unmet'}>
              <Icon name={f.met ? 'check' : 'x'} size={14} className={f.met ? 'additions' : undefined} />
              <span>
                <strong>{f.label}</strong> <span className="muted">— {f.detail}</span>
              </span>
            </li>
          ))}
        </ul>
      </details>

      {skill.highlights.length > 0 && (
        <button type="button" className="link-btn small" style={{ alignSelf: 'flex-start' }} onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? 'Hide proof' : `Show proof (${Math.min(3, skill.highlights.length)})`}
        </button>
      )}
      {skill.highlights.length > 0 && (
        <ul className="contribution-list" style={{ borderTop: '1px solid var(--line)' }}>
          {skill.highlights.slice(0, 3).map((c) => (
            <ContributionItem key={c.url} contribution={c} />
          ))}
        </ul>
      )}
    </article>
  )
}
