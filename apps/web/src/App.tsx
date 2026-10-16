import { NavLink, Link, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { LOGIN_PATH, onboardingComplete } from './auth/guard'

export default function App() {
  const { auth, logout } = useAuth()
  const navigate = useNavigate()
  const me = auth.status === 'authenticated' ? auth.me : null
  // Until onboarding is done the app pages are guarded anyway; hide their links.
  const showNav = me !== null && onboardingComplete(me)

  async function onLogout() {
    await logout()
    navigate(LOGIN_PATH, { replace: true })
  }

  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="app-header">
        <div className="header-brand-wrap">
          <Link to="/" className="brand">
            <span className="brand-dot" />
            HIRE
            <span className="brand-badge">UNPLUG</span>
          </Link>
          <span className="tagline">Autonomous Job Orchestration Platform</span>
        </div>
        <nav className="header-nav" aria-label="Main">
          {showNav && (
            <>
              <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Proof-of-Work
              </NavLink>
              <NavLink to="/jobs" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Verified Jobs
              </NavLink>
              <NavLink to="/swipe" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Swipe Deck
              </NavLink>
              <NavLink to="/pipeline" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Pipeline Board
              </NavLink>
              <a href="http://localhost:8001/docs" target="_blank" rel="noreferrer" className="nav-link nav-link-ext">
                API Docs ↗
              </a>
            </>
          )}
          {me && (
            <button type="button" className="nav-link nav-logout" onClick={onLogout} title={me.email ?? undefined}>
              Log out
            </button>
          )}
        </nav>
      </header>
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
