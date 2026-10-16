import type { Project } from '../types'

export default function ProjectsTable({ projects }: { projects: Project[] }) {
  if (projects.length === 0) return null

  return (
    <section className="card card-pad">
      <h3>Projects and your role in them</h3>
      <p className="muted small" style={{ margin: '4px 0 12px' }}>
        “Share” is how much of the project’s code you wrote.
      </p>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Project</th>
              <th>Role</th>
              <th className="num">Share</th>
              <th className="num">Commits / PRs</th>
              <th className="num">Lines</th>
              <th>Language</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.full_name}>
                <td>
                  <a href={p.url} target="_blank" rel="noreferrer">
                    {p.full_name}
                  </a>
                </td>
                <td>
                  <span className={`badge badge-plain ${p.is_external ? 'badge-accent' : 'badge-neutral'}`}>{p.role}</span>
                </td>
                <td className="num">{p.ownership_share == null ? '—' : `${Math.round(p.ownership_share * 100)}%`}</td>
                <td className="num">{p.contribution_count}</td>
                <td className="num">{p.meaningful_lines.toLocaleString('en-IN')}</td>
                <td>{p.primary_language ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
