import type { Contribution } from '../types'
import { WORK_TYPE_LABELS } from './WorkMixBar'

export default function ContributionItem({ contribution: c, showRepo = true }: { contribution: Contribution; showRepo?: boolean }) {
  return (
    <li className="contribution">
      <div className="contribution-title">
        <span className={`type-badge type-${c.type.replace('/', '-')}`}>{WORK_TYPE_LABELS[c.type]}</span>
        <a href={c.url} target="_blank" rel="noreferrer">
          {c.title}
        </a>
      </div>
      <div className="contribution-meta muted">
        {c.is_external && <span className="external-badge">Merged PR</span>}
        {showRepo && <span>{c.repo_full_name}</span>}
        <span className="additions">+{c.meaningful_additions.toLocaleString()}</span>
        <span className="deletions">−{c.meaningful_deletions.toLocaleString()}</span>
        <span>
          {c.files_touched} file{c.files_touched === 1 ? '' : 's'}
        </span>
        {c.date && <span>{new Date(c.date).toLocaleDateString()}</span>}
        {c.is_bulk && <span title="Very large change, likely an import or scaffold">bulk</span>}
      </div>
    </li>
  )
}
