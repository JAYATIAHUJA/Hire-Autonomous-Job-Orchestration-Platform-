import type { Contribution } from '../types'
import { WORK_TYPE_LABELS } from './WorkMixBar'

export default function ContributionItem({ contribution: c, showRepo = true }: { contribution: Contribution; showRepo?: boolean }) {
  return (
    <li className="contribution">
      <div className="contribution-title">
        <span className={`type-dot type-${c.type.replace('/', '-')}`} title={WORK_TYPE_LABELS[c.type]} aria-hidden="true" />
        <a href={c.url} target="_blank" rel="noreferrer">
          {c.title}
        </a>
      </div>
      <div className="contribution-meta">
        <span>{WORK_TYPE_LABELS[c.type]}</span>
        {c.is_external && <span className="badge badge-accent badge-plain">Merged PR to another project</span>}
        {showRepo && <span>{c.repo_full_name}</span>}
        <span className="additions">+{c.meaningful_additions.toLocaleString('en-IN')}</span>
        <span className="deletions">−{c.meaningful_deletions.toLocaleString('en-IN')}</span>
        <span>
          {c.files_touched} file{c.files_touched === 1 ? '' : 's'}
        </span>
        {c.date && <span>{new Date(c.date).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })}</span>}
        {c.is_bulk && <span title="Very large change, likely an import or scaffold">bulk change</span>}
      </div>
    </li>
  )
}
