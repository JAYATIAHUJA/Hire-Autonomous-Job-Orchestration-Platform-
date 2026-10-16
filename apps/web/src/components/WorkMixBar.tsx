import type { WorkMix, WorkType } from '../types'

export const WORK_TYPE_LABELS: Record<WorkType, string> = {
  feature: 'Features',
  fix: 'Fixes',
  refactor: 'Refactoring',
  test: 'Tests',
  'ci/infra': 'CI / infra',
  docs: 'Docs',
  chore: 'Chores',
}

export default function WorkMixBar({ mix }: { mix: WorkMix[] }) {
  const total = mix.reduce((sum, m) => sum + m.count, 0)
  if (total === 0) return null

  return (
    <section className="card card-pad">
      <h3>What kind of work you do</h3>
      <p className="muted small" style={{ margin: '4px 0 16px' }}>
        Each commit and pull request, sorted by what it changed.
      </p>
      <div className="mix-bar" role="img" aria-label={mix.map((m) => `${WORK_TYPE_LABELS[m.type]} ${Math.round((m.count / total) * 100)}%`).join(', ')}>
        {mix.map((m) => (
          <span key={m.type} className={`mix-segment type-${m.type.replace('/', '-')}`} style={{ flexGrow: m.count }} />
        ))}
      </div>
      <ul className="mix-legend">
        {mix.map((m) => (
          <li key={m.type}>
            <span className={`swatch type-${m.type.replace('/', '-')}`} />
            {WORK_TYPE_LABELS[m.type]} <strong>{Math.round((m.count / total) * 100)}%</strong>
          </li>
        ))}
      </ul>
    </section>
  )
}
