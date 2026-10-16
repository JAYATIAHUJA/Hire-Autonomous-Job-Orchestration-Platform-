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
    <section className="card">
      <h2>What kind of work</h2>
      <div className="mix-bar" role="img" aria-label="Work mix">
        {mix.map((m) => (
          <span
            key={m.type}
            className={`mix-segment type-${m.type.replace('/', '-')}`}
            style={{ flexGrow: m.count }}
            title={`${WORK_TYPE_LABELS[m.type]}: ${m.count}`}
          />
        ))}
      </div>
      <ul className="mix-legend">
        {mix.map((m) => (
          <li key={m.type}>
            <span className={`swatch type-${m.type.replace('/', '-')}`} />
            {WORK_TYPE_LABELS[m.type]} <strong>{Math.round((m.count / total) * 100)}%</strong>
            <span className="muted"> · {m.count}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
