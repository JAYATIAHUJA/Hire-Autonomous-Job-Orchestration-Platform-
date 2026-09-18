import { NavLink, Link, Outlet } from 'react-router-dom'

export default function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-brand-wrap">
          <Link to="/" className="brand">HIRE-UNPLUG</Link>
          <span className="tagline">Autonomous Job Orchestration Platform</span>
        </div>
        <nav className="header-nav">
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            Proof-of-Work (Phase 1)
          </NavLink>
          <NavLink to="/jobs" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            Verified Jobs Feed (Phase 2)
          </NavLink>
          <a href="http://localhost:8001/docs" target="_blank" rel="noreferrer" className="nav-link nav-link-ext">
            API Docs ↗
          </a>
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  )
}
