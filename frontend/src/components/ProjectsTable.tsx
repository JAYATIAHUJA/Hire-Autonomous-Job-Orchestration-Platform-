import type { Project } from '../types'

export default function ProjectsTable({ projects }: { projects: Project[] }) {
  if (projects.length === 0) return null

  return (
    <section className="card">
      <h2>Projects &amp; role</h2>
      <div className="table-scroll">
        <table className="projects-table">
          <thead>
            <tr>
              <th>Project</th>
              <th>Role</th>
              <th className="num">Share</th>
              <th className="num">Commits / PRs</th>
              <th className="num">Own lines</th>
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
                  <span className={`role-badge${p.is_external ? ' role-external' : ''}`}>{p.role}</span>
                </td>
                <td className="num">{p.ownership_share == null ? '—' : `${Math.round(p.ownership_share * 100)}%`}</td>
                <td className="num">{p.contribution_count}</td>
                <td className="num">{p.meaningful_lines.toLocaleString()}</td>
                <td>{p.primary_language ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
